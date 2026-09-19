"""Independent pinned MuJoCo path reconstruction, including a held cup's volume.

ACT controller messages contain positions only, so the installed Jazzy
Trajectory::interpolate_between_points uses linear segments. Derivative-rich
teacher trajectories require their separately validated controller interpolation.
This checker never removes the cup or mutates the live simulator data.
"""

import hashlib
import math
import multiprocessing
import os
from pathlib import Path
import threading

import mujoco
import numpy as np
from so101_demo.act.contracts import finite,identifier,vector,validate_action_prefix
from so101_demo.act.execution import bounded_positions
from so101_demo.act.joints import ARM_JOINTS
from so101_demo.act.trajectory import controller_point
from so101_demo.act.contracts import fields


def model_sha256(model):
    buffer=np.empty(mujoco.mj_sizeModel(model),dtype=np.uint8)
    mujoco.mj_saveModel(model,None,buffer)
    return hashlib.sha256(buffer.tobytes()).hexdigest()


class MujocoPathChecker:
    def __init__(self,model_path,*,protected_roots,cup_joint,gripper_body,path_step_s,path_clearance_m,
                 velocity_limit_rad_s,acceleration_limit_rad_s2,allowed_pairs_by_phase,max_samples=50000):
        if mujoco.mj_versionString()!='3.4.0':raise ValueError('PHYSICS_VERSION_INVALID')
        self.model=mujoco.MjModel.from_xml_path(str(Path(model_path).resolve()))
        self.model_sha256=model_sha256(self.model)
        self.step,self.clearance=finite(path_step_s),finite(path_clearance_m)
        self.velocity_limits=vector(velocity_limit_rad_s,6);self.acceleration_limits=vector(acceleration_limit_rad_s2,6)
        if min(self.step,self.clearance,*self.velocity_limits,*self.acceleration_limits)<=0:
            raise ValueError('PATH_CONFIG_INVALID')
        if type(max_samples) is not int or max_samples<2:raise ValueError('PATH_CONFIG_INVALID')
        self.max_samples=max_samples;self._lock=threading.RLock();self.last_check=None
        self._data=mujoco.MjData(self.model)
        self.joints=[]
        for name in ARM_JOINTS:
            jid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,name)
            if jid<0 or self.model.jnt_type[jid]!=mujoco.mjtJoint.mjJNT_HINGE:raise ValueError('PATH_JOINT_INVALID')
            self.joints.append(int(self.model.jnt_qposadr[jid]))
        self.cup_joint=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,cup_joint)
        self.gripper=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,gripper_body)
        if self.cup_joint<0 or self.gripper<0 or self.model.jnt_type[self.cup_joint]!=mujoco.mjtJoint.mjJNT_FREE:
            raise ValueError('PATH_BODY_INVALID')
        self.cup_address=int(self.model.jnt_qposadr[self.cup_joint])
        self.names={i:mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_GEOM,i) for i in range(self.model.ngeom)}
        self.protected=set();roots=set()
        for root in protected_roots:
            jid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,root)
            if jid<1:raise ValueError('PATH_ROOT_INVALID')
            roots.add(jid)
        if not roots:raise ValueError('PATH_ROOT_INVALID')
        for body in range(1,self.model.nbody):
            parent=body
            while parent and parent not in roots:parent=int(self.model.body_parentid[parent])
            if parent in roots:self.protected.update(np.flatnonzero(self.model.geom_bodyid==body).tolist())
        cup_body=int(self.model.jnt_bodyid[self.cup_joint])
        self.cup_geoms=set(np.flatnonzero(self.model.geom_bodyid==cup_body).tolist())
        self._protected_mask=np.zeros(self.model.ngeom,dtype=bool)
        self._protected_mask[list(self.protected)]=True
        self._cup_mask=np.zeros(self.model.ngeom,dtype=bool)
        self._cup_mask[list(self.cup_geoms)]=True
        self.allowed={}
        known=set(self.names.values());known.discard(None)
        for phase,pairs in allowed_pairs_by_phase.items():
            identifier(phase)
            if phase not in ('APPROACH','CONTACT','LIFT','TRANSPORT','RELEASE','RETREAT','FINAL'):
                raise ValueError('PATH_CONTACT_CONFIG_INVALID')
            checked=set()
            for pair in pairs:
                if (not isinstance(pair,tuple) or len(pair)!=2 or tuple(sorted(pair))!=pair
                        or not set(pair)<=known):raise ValueError('PATH_CONTACT_CONFIG_INVALID')
                checked.add(pair)
            self.allowed[phase]=frozenset(checked)
        # Inflate collision detection margins in this independent model only.
        # Actual live per-step contacts provide the complementary execution gate.
        self.model.geom_margin[:]=np.maximum(self.model.geom_margin,self.clearance)

    def _reject(self,reason,**details):
        self.last_check=dict(safe=False,reason=reason,**details);return False

    def _contact_violation(self,held,allowed):
        # Aggregate arrays avoid constructing a Python mjContact wrapper for
        # every contact at every physics sample. Re-fetch after each position
        # stage because the engine can change the contact count/storage.
        contacts=self._data.contact;geoms=contacts.geom;distances=contacts.dist
        relevant=self._protected_mask[geoms].any(axis=1)
        if held:relevant|=self._cup_mask[geoms].any(axis=1)
        candidates=np.flatnonzero(relevant&(~np.isfinite(distances)|(distances<=self.clearance)))
        for index in candidates:
            a,b=geoms[index];pair=tuple(sorted((self.names[int(a)],self.names[int(b)])))
            distance=float(distances[index])
            if not math.isfinite(distance) or pair not in allowed:return pair,distance
        return None

    def check_path(self,prefix,snapshot):
        with self._lock:
            try:return self._check(prefix,snapshot)
            except (KeyError,TypeError,ValueError,IndexError,OverflowError) as error:
                return self._reject('PATH_INPUT_INVALID',error=repr(error))

    def _check(self,prefix,snapshot):
        checked=validate_action_prefix(prefix)
        if snapshot['model_sha256']!=self.model_sha256:return self._reject('PATH_MODEL_INVALID')
        if snapshot['holding_state'] not in ('EMPTY','HOLDING'):return self._reject('HOLDING_UNKNOWN')
        if snapshot['phase'] not in ('APPROACH','CONTACT','LIFT','TRANSPORT','RELEASE','RETREAT','FINAL'):
            return self._reject('PATH_PHASE_INVALID')
        start=finite(snapshot['controller_start_time_s'],nonnegative=True)
        if not checked['observation_time_s']<start<checked['target_times_s'][0]:
            return self._reject('PATH_TIMING_INVALID',observation_time_s=checked['observation_time_s'],
                start_time_s=start,first_target_time_s=checked['target_times_s'][0])
        positions=(bounded_positions(snapshot['controller_start_positions']),)+tuple(
            bounded_positions(row) for row in checked['positions'])
        times=(start,)+checked['target_times_s']
        bridge=snapshot['controller_bridge'];fields(bridge,('time_s','point'))
        before=finite(bridge['time_s'],nonnegative=True)
        point=controller_point(bridge['point'])
        bounded_positions(point['positions'])
        if before>=start or before>snapshot.get('sim_time_s',checked['observation_time_s']):
            return self._reject('PATH_BRIDGE_TIME_INVALID')
        positions=(point['positions'],)+positions;times=(before,)+times
        qpos=vector(snapshot['model_qpos'],self.model.nq)
        vector(snapshot['controller_start_velocities'],6)
        previous_velocity=np.array(point['velocities'] or (0.,)*6)
        attachment=None
        if snapshot['holding_state']=='HOLDING':
            attachment=np.array(snapshot['cup_in_gripper_transform'],dtype=float)
            if (attachment.shape!=(4,4) or not np.isfinite(attachment).all()
                    or not np.allclose(attachment[3],(0,0,0,1),atol=1e-9)
                    or not np.allclose(attachment[:3,:3].T@attachment[:3,:3],np.eye(3),atol=1e-6)
                    or not math.isclose(np.linalg.det(attachment[:3,:3]),1.,abs_tol=1e-6)):
                return self._reject('PATH_ATTACHMENT_INVALID')
        allowed=self.allowed.get(snapshot['phase'],frozenset())
        sample_count=1+sum(math.ceil((b-a)/self.step) for a,b in zip(times,times[1:]))
        if sample_count>self.max_samples:return self._reject('PATH_SAMPLE_BUDGET')
        sample_times=[np.array((before,))];sample_positions=[np.array((positions[0],))]
        for begin,end,q0,q1 in zip(times,times[1:],positions,positions[1:],strict=False):
            n=math.ceil((end-begin)/self.step)
            fractions=np.arange(1,n+1,dtype=float)/n
            sample_times.append(begin+(end-begin)*fractions)
            sample_positions.append(np.array(q0)+(np.array(q1)-q0)*fractions[:,None])
        sample_times=np.concatenate(sample_times);sample_positions=np.concatenate(sample_positions)
        intervals=np.diff(sample_times)
        if np.any(intervals<=0):return self._reject('PATH_TIMING_INVALID')
        velocities=np.diff(sample_positions,axis=0)/intervals[:,None]
        if np.any(np.abs(velocities)>np.array(self.velocity_limits)+1e-9):return self._reject('PATH_VELOCITY_LIMIT')
        accelerations=np.diff(np.vstack((previous_velocity,velocities)),axis=0)/intervals[:,None]
        if np.any(np.abs(accelerations)>np.array(self.acceleration_limits)+1e-9):return self._reject('PATH_ACCELERATION_LIMIT')
        if np.any(np.abs(velocities[-1])/self.step>np.array(self.acceleration_limits)+1e-9):
            return self._reject('PATH_ACCELERATION_LIMIT')
        mujoco.mj_resetData(self.model,self._data)
        for stamp,q in zip(sample_times,sample_positions,strict=True):
            self._data.qpos[:]=qpos
            self._data.qpos[self.joints]=q
            if attachment is not None:
                mujoco.mj_kinematics(self.model,self._data)
                gripper=np.eye(4);gripper[:3,:3]=self._data.xmat[self.gripper].reshape(3,3)
                gripper[:3,3]=self._data.xpos[self.gripper];cup=gripper@attachment
                self._data.qpos[self.cup_address:self.cup_address+3]=cup[:3,3]
                quat=np.empty(4);mujoco.mju_mat2Quat(quat,np.ascontiguousarray(cup[:3,:3]).reshape(9))
                self._data.qpos[self.cup_address+3:self.cup_address+7]=quat
            # Contact distances, geometry and FK are position-stage outputs.
            # Do not solve forces/accelerations or integrate the independent data.
            mujoco.mj_fwdPosition(self.model,self._data)
            violation=self._contact_violation(attachment is not None,allowed)
            if violation is not None:
                pair,distance=violation
                return self._reject('ROBOT_PATH_CONTACT',contact_pair=pair,sample_time_s=stamp,signed_distance_m=distance)
        self.last_check=dict(safe=True,reason=None,samples=sample_count,model_sha256=self.model_sha256,
            path_step_s=self.step,path_clearance_m=self.clearance,start_time_s=start,end_time_s=times[-1])
        return True


def _path_worker(connection,configuration):
    """Private spawned worker: no ROS node, command clients or permit authority."""
    try:
        checker=MujocoPathChecker(**configuration)
        connection.send(dict(pid=os.getpid(),model_sha256=checker.model_sha256))
        while True:
            request=connection.recv()
            if request is None:return
            prefix,snapshot=request
            safe=checker.check_path(prefix,snapshot)
            connection.send(dict(safe=safe,details=checker.last_check))
    except (EOFError,BrokenPipeError,OSError):
        return
    finally:
        connection.close()


class MujocoPathProcess:
    """Bounded IPC around the same checker, with a compiled-model handshake.

    The local model serves snapshot reconstruction only. Every path check runs
    in the spawned process, whose GIL is independent of ROS callback threads.
    Worker loss is permanent for this instance; it never silently restarts.
    """
    def __init__(self,*,check_timeout_s,start_timeout_s,**configuration):
        self.timeout=finite(check_timeout_s);startup=finite(start_timeout_s)
        if min(self.timeout,startup)<=0:raise ValueError('PATH_WORKER_CONFIG_INVALID')
        local=MujocoPathChecker(**configuration)
        self.model,self.model_sha256,self.cup_address=local.model,local.model_sha256,local.cup_address
        self.names=local.names;self.last_check=None
        self._lock=threading.Lock();self._closed=False
        context=multiprocessing.get_context('spawn')
        self._connection,child=context.Pipe()
        self.process=context.Process(target=_path_worker,args=(child,configuration),daemon=True)
        try:
            self.process.start();child.close()
            if not self._connection.poll(startup):raise ValueError('PATH_WORKER_START_TIMEOUT')
            ready=self._connection.recv()
            if (not isinstance(ready,dict) or set(ready)!=set(('pid','model_sha256'))
                    or type(ready['pid']) is not int or ready['pid']!=self.process.pid
                    or ready['model_sha256']!=self.model_sha256):
                raise ValueError('PATH_WORKER_MODEL_INVALID')
        except BaseException:
            child.close();self._dispose();raise

    @property
    def worker_pid(self):return self.process.pid

    def _reject(self,reason):
        self.last_check=dict(safe=False,reason=reason);return False

    def _dispose(self):
        self._closed=True;self._connection.close()
        if self.process.pid is not None:
            if self.process.is_alive():self.process.terminate()
            self.process.join(timeout=.2)
            if self.process.is_alive():
                self.process.kill();self.process.join(timeout=.2)

    def check_path(self,prefix,snapshot):
        if not self._lock.acquire(timeout=self.timeout):return self._reject('PATH_WORKER_BUSY')
        try:
            if self._closed or not self.process.is_alive():
                return self._reject('PATH_WORKER_UNAVAILABLE')
            # Only broker-local typed inputs enter this private pipe. Public
            # clients cannot supply serialized worker requests or snapshots.
            self._connection.send((prefix,snapshot))
            if not self._connection.poll(self.timeout):
                self._dispose();return self._reject('PATH_CHECK_TIMEOUT')
            reply=self._connection.recv()
            if (not isinstance(reply,dict) or set(reply)!=set(('safe','details'))
                    or type(reply['safe']) is not bool or not isinstance(reply['details'],dict)
                    or reply['details'].get('safe') is not reply['safe']):
                self._dispose();return self._reject('PATH_WORKER_RESPONSE_INVALID')
            self.last_check=reply['details'];return reply['safe']
        except (EOFError,BrokenPipeError,OSError,ValueError,TypeError):
            self._dispose();return self._reject('PATH_WORKER_UNAVAILABLE')
        finally:self._lock.release()

    def close(self):
        with self._lock:
            if self._closed:return
            try:
                self._connection.send(None);self.process.join(timeout=.05)
            except (BrokenPipeError,EOFError,OSError):pass
            self._dispose()
