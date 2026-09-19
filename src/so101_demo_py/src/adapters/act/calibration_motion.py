"""Explicit small-envelope timing calibration; always excluded from formal data."""

from pathlib import Path
import math
from so101_demo.act.contracts import fields,finite,identifier,integer,vector,sha256,validate_action_prefix
from so101_demo.act.execution import bounded_positions

MOTION_KEYS=frozenset(('schema_version','kind','eligible_for_collection','session_id','model_path','model_sha256',
    'arm_center','max_delta_rad','neck_center_rad','max_neck_drift_rad','max_rows','path_step_s','path_clearance_m',
    'velocity_limit_rad_s','acceleration_limit_rad_s2','max_age_s','max_skew_s','stop_velocity_rad_s','submit_lead_s'))


def require_motion_manifest(value):
    fields(value,MOTION_KEYS)
    if type(value['schema_version']) is not int or value['schema_version']!=1 or value['kind']!='ACT_TIMING_CALIBRATION' or value['eligible_for_collection'] is not False:
        raise ValueError('MOTION_CALIBRATION_INVALID')
    identifier(value['session_id']);sha256(value['model_sha256'])
    if not isinstance(value['model_path'],str) or not Path(value['model_path']).is_absolute():raise ValueError('MOTION_MODEL_INVALID')
    bounded_positions(value['arm_center']);finite(value['neck_center_rad'])
    integer(value['max_rows'],minimum=1)
    if value['max_rows']>10:raise ValueError('MOTION_ENVELOPE_INVALID')
    delta=vector(value['max_delta_rad'],6)
    if not all(0<x<=.005 for x in delta):raise ValueError('MOTION_ENVELOPE_INVALID')
    for key in ('velocity_limit_rad_s','acceleration_limit_rad_s2'):
        if min(vector(value[key],6))<=0:raise ValueError('MOTION_LIMIT_INVALID')
    for key in ('path_step_s','path_clearance_m','max_neck_drift_rad','max_age_s','max_skew_s','stop_velocity_rad_s','submit_lead_s'):
        if finite(value[key])<=0:raise ValueError('MOTION_CALIBRATION_INVALID')
    return value


def within_calibration_envelope(prefix,reference,neck_yaw,manifest):
    try:
        require_motion_manifest(manifest);checked=validate_action_prefix(prefix);bounded_positions(reference)
        if checked['session_id']!=manifest['session_id'] or len(checked['positions'])>manifest['max_rows']:return False
        if abs(finite(neck_yaw)-manifest['neck_center_rad'])>manifest['max_neck_drift_rad']:return False
        return all(all(abs(q-center)<=limit for q,center,limit in zip(row,manifest['arm_center'],manifest['max_delta_rad'],strict=True))
                   for row in (reference,*checked['positions']))
    except (KeyError,TypeError,ValueError):return False


class RosCalibrationMotionGuard:
    """Sole broker-local calibration gate, armed by actual paused reset evidence."""
    def __init__(self,node,driver,broker,manifest,*,evidence_root,monotonic=None):
        import json,threading,time
        from collections import deque
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import JointState
        from so101_mujoco_support.msg import ScalarJointEvidence
        from so101_demo.backends.mujoco.observer import ATOMIC_EVIDENCE_QOS
        from .contact_evidence import RobotContactObserver,RosRobotContactAdapter
        from .scene_state import SceneStateObserver,RosSceneStateAdapter
        from .physics import MujocoPathProcess
        self.manifest=require_motion_manifest(manifest);self.driver,self.broker=driver,broker
        self.monotonic=monotonic or time.monotonic;self._lock=threading.RLock();self._joints=None
        self.audit=deque(maxlen=128);self._closed=False
        self.path=MujocoPathProcess(check_timeout_s=manifest['submit_lead_s'],start_timeout_s=2.,
            model_path=manifest['model_path'],protected_roots=('base',),cup_joint='cup_free_joint',
            gripper_body='gripper',path_step_s=manifest['path_step_s'],path_clearance_m=manifest['path_clearance_m'],
            velocity_limit_rad_s=manifest['velocity_limit_rad_s'],acceleration_limit_rad_s2=manifest['acceleration_limit_rad_s2'],
            allowed_pairs_by_phase={})
        if self.path.model_sha256!=manifest['model_sha256']:
            self.path.close();raise ValueError('MOTION_MODEL_HASH_INVALID')
        try:
            self.model=self.path.model
            known=set(self.path.names.values());known.discard(None)
            self.contact_observer=RobotContactObserver(known_geoms=known,allowed_pairs=set(),
                max_age_s=manifest['max_age_s'],max_sim_gap_s=float(self.model.opt.timestep)*1.01,monotonic=self.monotonic)
            root=Path(evidence_root);root.mkdir(parents=True,exist_ok=True)
            self._record=(root/'motion-calibration-robot-contacts.jsonl').open('x',encoding='utf-8')
            self._scene_record=(root/'motion-calibration-scene-state.jsonl').open('x',encoding='utf-8')
            self.scene_observer=SceneStateObserver(model_sha256=self.path.model_sha256,
                nq=self.model.nq,nv=self.model.nv,max_age_s=manifest['max_age_s'],monotonic=self.monotonic)
            self.scene_adapter=RosSceneStateAdapter(node,self.scene_observer,on_hazard=self._fail,
                record_port=self._record_scene,pending_reset_port=self._pending_scene_reset)
            self.contact_adapter=RosRobotContactAdapter(node,self.contact_observer,on_hazard=self._fail,record_port=self._record_frame)
            self.subscriptions=[node.create_subscription(JointState,'/joint_states',self.accept_joints,qos_profile_sensor_data),
                node.create_subscription(ScalarJointEvidence,'/so101/simulation/joints',self.accept_reset,ATOMIC_EVIDENCE_QOS)]
            self.timer=node.create_timer(.01,self.poll)
        except BaseException:
            self.path.close()
            if hasattr(self,'_record'):self._record.close()
            if hasattr(self,'_scene_record'):self._scene_record.close()
            raise

    def _record_scene(self,frame):
        import json
        with self._lock:
            if self._closed:raise OSError('SCENE_RECORDER_CLOSED')
            self._scene_record.write(json.dumps(frame,allow_nan=False,separators=(',',':'))+'\n')

    def _pending_scene_reset(self,frame):
        import mujoco
        try:
            with self.driver._lock:
                initial=self.driver._reset_initial;target=self.driver._reset_target
                acknowledged=self.driver._world_reset_ack
                if initial is None or target is None:return False
                if ((frame['simulation_session_id'],frame['reset_epoch'])!=
                        (initial.simulation_session_id,initial.reset_epoch+1)):
                    return False
                positions=dict(zip(target.name,target.position,strict=True))
                velocities=dict(zip(target.name,target.velocity,strict=True))
                from so101_demo.act.joints import ACT_JOINTS
                expected=tuple(self.manifest['arm_center'])+(self.manifest['neck_center_rad'],)
                for name,value in zip(ACT_JOINTS,expected,strict=True):
                    jid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,name)
                    if jid<0:return False
                    if (abs(positions[name]-value)>1e-9 or velocities[name]!=0.
                            or abs(frame['qpos'][self.model.jnt_qposadr[jid]]-value)>1e-9
                            or frame['qvel'][self.model.jnt_dofadr[jid]]!=0.):return False
            # A completed driver ACK is a retained trusted write receipt. Before
            # that ACK, the actual reset ticket must still be authorized.
            if acknowledged:return True
            with self.broker._lock:ticket=self.broker._reset_ticket
            if ticket is None or ticket[2]=='act' or ticket[3]!=self.manifest['session_id']:return False
            self.broker.ownership.require_ticket(ticket);return True
        except (AttributeError,KeyError,TypeError,ValueError,PermissionError):return False

    def _record_frame(self,frame):
        import json
        with self._lock:
            if self._closed:raise OSError('CONTACT_RECORDER_CLOSED')
            self._record.write(json.dumps(frame,allow_nan=False,separators=(',',':'))+'\n')

    def _fail(self,reason):
        with self.driver._lock:
            if self.driver.hazard_reason is None:self.driver.hazard_reason=reason
        self.broker.ownership.revoke(reason);self.broker.tick()

    def accept_reset(self,message):
        import threading
        from types import SimpleNamespace
        if not message.paused or message.simulation_step!=0:return
        if message.simulation_session_id!=self.manifest['session_id']:
            self._fail('CONTACT_RESET_IDENTITY_INVALID');return
        from so101_demo.act.joints import ACT_JOINTS
        try:
            if (len(set(message.joint_names))!=7 or set(message.joint_names)!=set(ACT_JOINTS)
                    or len(message.positions_rad)!=7 or len(message.velocities_rad_s)!=7):raise ValueError('names')
            positions=dict(zip(message.joint_names,message.positions_rad,strict=True));velocities=dict(zip(message.joint_names,message.velocities_rad_s,strict=True))
            expected=tuple(self.manifest['arm_center'])+(self.manifest['neck_center_rad'],)
            if any(abs(finite(positions[name])-q)>.002 or finite(velocities[name])!=0. for name,q in zip(ACT_JOINTS,expected,strict=True)):
                raise ValueError('reset vector')
            with self.contact_observer._lock:
                if self.contact_observer.epoch is not None and message.reset_epoch<=self.contact_observer.epoch:return
            stamp=finite(message.header.stamp.sec+message.header.stamp.nanosec*1e-9,nonnegative=True)
            self.contact_adapter.arm(SimpleNamespace(simulation_session_id=message.simulation_session_id,
                reset_epoch=message.reset_epoch,simulation_time_s=stamp,simulation_step=0,paused=True))
            self.scene_adapter.arm(SimpleNamespace(simulation_session_id=message.simulation_session_id,
                reset_epoch=message.reset_epoch,simulation_time_s=stamp,simulation_step=0,paused=True))
        except (KeyError,TypeError,ValueError):self._fail('CONTACT_RESET_SNAPSHOT_INVALID')

    def accept_joints(self,message):
        from so101_demo.act.joints import ACT_JOINTS
        try:
            if (len(set(message.name))!=len(message.name) or len(message.position)!=len(message.name)
                    or len(message.velocity)!=len(message.name) or not set(ACT_JOINTS)<=set(message.name)):return
            positions=dict(zip(message.name,message.position,strict=True));velocities=dict(zip(message.name,message.velocity,strict=True))
            q=tuple(finite(positions[name]) for name in ACT_JOINTS);v=tuple(finite(velocities[name]) for name in ACT_JOINTS)
            stamp=finite(message.header.stamp.sec+message.header.stamp.nanosec*1e-9,nonnegative=True)
            with self._lock:self._joints=(q,v,stamp,self.monotonic())
        except (KeyError,TypeError,ValueError):return

    def _snapshot(self,base,*,start,reference,reference_velocity):
        from so101_demo.act.joints import ACT_JOINTS
        import mujoco,numpy as np
        now=self.monotonic()
        with self._lock:joints=self._joints
        with self.driver._lock:epoch=self.driver._epoch;fault=self.driver.hazard_reason
        with self.contact_observer._lock:
            contact=self.contact_observer.last
            identity=(self.contact_observer.session,self.contact_observer.epoch)
        if fault or joints is None or epoch is None or contact is None or not self.contact_observer.safe():
            raise ValueError('MOTION_EVIDENCE_UNAVAILABLE')
        q,v,joint_stamp,joint_received=joints;cup,cup_received=epoch
        scene=self.scene_observer.snapshot()
        if (identity!=(self.manifest['session_id'],base['reset_epoch'])
                or (cup.simulation_session_id,cup.reset_epoch)!=identity or cup.paused
                or cup.truncated or cup.object_body!='plastic_cup' or base['reset_epoch']<1):
            raise ValueError('MOTION_EVIDENCE_IDENTITY_INVALID')
        if ((scene['simulation_session_id'],scene['reset_epoch'])!=identity or scene['paused']):
            raise ValueError('MOTION_SCENE_IDENTITY_INVALID')
        cup_stamp=cup.header.stamp.sec+cup.header.stamp.nanosec*1e-9
        stamps=(finite(base['sim_time_s']),joint_stamp,finite(cup_stamp),contact['simulation_time_s'],scene['simulation_time_s'])
        if max(stamps)-min(stamps)>self.manifest['max_skew_s'] or any(not 0<=now-r<=self.manifest['max_age_s'] for r in (joint_received,cup_received)):
            raise ValueError('MOTION_EVIDENCE_STALE')
        measured_prefix=dict(session_id=self.manifest['session_id'],attempt_id=base['attempt_id'],sequence=0,
            observation_time_s=0.,target_times_s=(.1,),positions=(q[:6],))
        if not within_calibration_envelope(measured_prefix,reference,q[6],self.manifest):raise ValueError('MOTION_ENVELOPE_INVALID')
        if abs(v[6])>self.manifest['stop_velocity_rad_s']:raise ValueError('MOTION_NECK_NOT_STOPPED')
        qpos=np.array(scene['qpos']);scene_q=[];scene_v=[]
        for name in ACT_JOINTS:
            jid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,name)
            if jid<0:raise ValueError('MOTION_MODEL_JOINT_INVALID')
            scene_q.append(float(qpos[self.model.jnt_qposadr[jid]]))
            scene_v.append(scene['qvel'][self.model.jnt_dofadr[jid]])
        measured_prefix['positions']=(tuple(scene_q[:6]),)
        if not within_calibration_envelope(measured_prefix,reference,scene_q[6],self.manifest):
            raise ValueError('MOTION_SCENE_ENVELOPE_INVALID')
        if abs(scene_v[6])>self.manifest['stop_velocity_rad_s']:raise ValueError('MOTION_SCENE_NECK_NOT_STOPPED')
        pose=cup.object_pose_world
        xyz=tuple(finite(getattr(pose.position,key)) for key in ('x','y','z'))
        quat=tuple(finite(getattr(pose.orientation,key)) for key in ('w','x','y','z'))
        if not math.isclose(sum(x*x for x in quat),1.,abs_tol=1e-6):raise ValueError('MOTION_CUP_POSE_INVALID')
        # Keep every actual coordinate, including independent free bodies.
        # Cup/named-joint streams independently establish scope/freshness;
        # they must never overwrite a partial nominal model reconstruction.
        address=self.path.cup_address
        if not math.isclose(sum(x*x for x in qpos[address+3:address+7]),1.,abs_tol=1e-6):
            raise ValueError('MOTION_SCENE_CUP_POSE_INVALID')
        return dict(model_qpos=tuple(qpos),model_sha256=self.path.model_sha256,phase='APPROACH',holding_state='EMPTY',
            sim_time_s=max(stamps),controller_bridge=dict(time_s=scene['simulation_time_s'],
                point=dict(positions=tuple(scene_q[:6]),velocities=tuple(scene_v[:6]),accelerations=())),
            controller_start_time_s=start,controller_start_positions=reference,controller_start_velocities=reference_velocity,
            cup_in_gripper_transform=None)

    def check_prefix(self,prefix,snapshot):
        began=self.monotonic()
        try:
            start=snapshot['sim_time_s']+self.manifest['submit_lead_s']
            reference=self.driver.reference_state(start)
            full=self._snapshot(snapshot,start=start,reference=reference['positions'],reference_velocity=reference['velocities'])
            if not within_calibration_envelope(prefix,reference['positions'],self._joints[0][6],self.manifest):return False
            safe=self.path.check_path(prefix,full)
            self.audit.append(dict(boundary='approve',safe=safe,path=dict(self.path.last_check),
                elapsed_wall_s=self.monotonic()-began,snapshot_sim_time_s=snapshot['sim_time_s']))
            return safe
        except (KeyError,TypeError,ValueError,RuntimeError) as error:
            self.audit.append(dict(boundary='approve',safe=False,error=repr(error),
                elapsed_wall_s=self.monotonic()-began,snapshot_sim_time_s=snapshot.get('sim_time_s')));return False

    def check_exact_goals(self,goals,prefix):
        try:
            if len(goals)!=2 or goals[0]['header_stamp_s']!=goals[1]['header_stamp_s'] or goals[0]['time_from_start_s']!=goals[1]['time_from_start_s']:
                return False
            base=dict(session_id=prefix['session_id'],attempt_id=prefix['attempt_id'],reset_epoch=self.contact_observer.epoch,
                sim_time_s=prefix['observation_time_s'])
            start=goals[0]['header_stamp_s'];held=goals[0]['positions'][0]+goals[1]['positions'][0]
            reference=self.driver.reference_state(start)
            if any(abs(a-b)>1e-9 for a,b in zip(reference['positions'],held,strict=True)):return False
            full=self._snapshot(base,start=start,reference=held,reference_velocity=reference['velocities'])
            if not within_calibration_envelope(prefix,held,self._joints[0][6],self.manifest):return False
            safe=self.path.check_path(prefix,full)
            self.audit.append(dict(boundary='exact_goals',safe=safe,path=dict(self.path.last_check)))
            return safe
        except (KeyError,TypeError,ValueError,RuntimeError) as error:
            self.audit.append(dict(boundary='exact_goals',safe=False,error=repr(error)));return False

    def poll(self):
        pair=self.broker.prefix_executor
        ticket=None if pair is None else pair._ticket
        if ticket is None:return
        try:self.broker.ownership.require_ticket(ticket)
        except PermissionError:return
        if not self.contact_observer.safe():self._fail(self.contact_observer.hazard or 'CONTACT_EVIDENCE_STALE')
        try:
            if self.scene_observer.snapshot()['paused']:raise ValueError('SCENE_STATE_PAUSED')
        except ValueError as error:self._fail(str(error))

    def close(self):
        import os
        try:
            with self._lock:
                self._closed=True
                for stream in (self._record,self._scene_record):
                    stream.flush();os.fsync(stream.fileno());stream.close()
        finally:self.path.close()
