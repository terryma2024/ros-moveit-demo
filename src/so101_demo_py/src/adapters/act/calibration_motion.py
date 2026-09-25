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


def diagnostic_motion_configuration(manifest):
    """Replay pinned sources before converting a contact run to broker-local limits."""
    from so101_demo.act.contact_diagnostic import require_contact_diagnostic_sources
    source=require_contact_diagnostic_sources(manifest)
    return dict(kind='ACT_CONTACT_DIAGNOSTIC',eligible_for_collection=False,
        session_id=source['session_id'],attempt_id=source['attempt_id'],
        model_path=source['scene_path'],model_sha256=source['model_sha256'],
        arm_center=tuple(source['joint_start_rad']),neck_center_rad=source['neck_start_rad'],
        max_neck_drift_rad=.002,max_rows=min(source['segment_rows']+1,len(source['target_positions'])+1),
        path_step_s=source['path_step_s'],path_clearance_m=source['path_clearance_m'],
        velocity_limit_rad_s=tuple(source['velocity_limit_rad_s']),
        acceleration_limit_rad_s2=tuple(source['acceleration_limit_rad_s2']),
        max_age_s=source['max_age_s'],max_skew_s=source['max_skew_s'],
        stop_velocity_rad_s=source['stop_velocity_rad_s'],
        submit_lead_s=source['submit_lead_s'],
        allowed_pairs=frozenset(tuple(pair) for pair in source['allowed_contact_pairs']),
        diagnostic_limits=source['diagnostic_limits'].copy(),
        manifest_sha256=source['manifest_sha256'])


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
        self.contact_mode=isinstance(manifest,dict) and manifest.get('kind')=='ACT_CONTACT_DIAGNOSTIC'
        self.contact_manifest=manifest if self.contact_mode else None
        self.manifest=(diagnostic_motion_configuration(manifest) if self.contact_mode
                       else require_motion_manifest(manifest))
        config=self.manifest
        self.node=node;self.driver,self.broker=driver,broker
        self.monotonic=monotonic or time.monotonic;self._lock=threading.RLock();self._joints=None
        self.audit=deque(maxlen=128);self._closed=False;self.live_observer=None;self.live_adapter=None
        self._cup_reset_verified=False
        self._next_segment=0
        allowed=config['allowed_pairs'] if self.contact_mode else frozenset()
        self.path=MujocoPathProcess(check_timeout_s=config['submit_lead_s'],start_timeout_s=2.,
            model_path=config['model_path'],protected_roots=('base',),cup_joint='cup_free_joint',
            gripper_body='gripper',path_step_s=config['path_step_s'],path_clearance_m=config['path_clearance_m'],
            velocity_limit_rad_s=config['velocity_limit_rad_s'],acceleration_limit_rad_s2=config['acceleration_limit_rad_s2'],
            allowed_pairs_by_phase={'APPROACH':allowed} if self.contact_mode else {})
        if self.path.model_sha256!=config['model_sha256']:
            self.path.close();raise ValueError('MOTION_MODEL_HASH_INVALID')
        try:
            self.model=self.path.model
            known=set(self.path.names.values());known.discard(None)
            self.contact_observer=RobotContactObserver(known_geoms=known,allowed_pairs=allowed,
                max_age_s=config['max_age_s'],max_sim_gap_s=float(self.model.opt.timestep)*1.01,monotonic=self.monotonic)
            root=Path(evidence_root);root.mkdir(parents=True,exist_ok=True);self.evidence_root=root
            stem='contact-diagnostic' if self.contact_mode else 'motion-calibration'
            self._record=(root/(stem+'-robot-contacts.jsonl')).open('x',encoding='utf-8')
            self._scene_record=(root/(stem+'-scene-state.jsonl')).open('x',encoding='utf-8')
            self._audit_record=(root/(stem+'-guard-rejections.jsonl')).open('x',encoding='utf-8')
            self.scene_observer=SceneStateObserver(model_sha256=self.path.model_sha256,
                nq=self.model.nq,nv=self.model.nv,max_age_s=config['max_age_s'],monotonic=self.monotonic)
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
            if hasattr(self,'_audit_record'):self._audit_record.close()
            raise

    def _start_safe(self,positions,neck_yaw):
        if not self.contact_mode:
            probe=dict(session_id=self.manifest['session_id'],attempt_id='start',sequence=0,
                observation_time_s=0.,target_times_s=(.1,),positions=(tuple(positions),))
            return within_calibration_envelope(
                probe,self.manifest['arm_center'],neck_yaw,self.manifest)
        try:
            start=self._next_segment*self.contact_manifest['segment_rows']
            expected=(self.manifest['arm_center'] if start==0 else
                      self.contact_manifest['target_positions'][start-1])
            return (abs(finite(neck_yaw)-self.manifest['neck_center_rad'])<=.002
                and all(abs(a-b)<=.002 for a,b in zip(
                    bounded_positions(positions),expected,strict=True)))
        except (KeyError,TypeError,ValueError):return False

    def _previous_segment_complete(self):
        if not self.contact_mode or self._next_segment==0:return True
        try:
            pair=self.broker.prefix_executor
            ids=pair.adapter.current_goal_ids
            if len(ids)!=2 or any(gid is None for gid in ids):
                return False
            states=[self.driver.goal_state(gid) for gid in ids]
            if not all(state['accepted'] is True and state['status']==4 and
                       state['result'] is not None and state['result']['error_code']==0
                       for state in states):
                return False
            # The paired goal status has already refreshed the negative
            # baseline. Starting another asynchronous refresh here would
            # clear that proof immediately before this synchronous check.
            return self.driver.stopped()
        except (AttributeError,KeyError,TypeError,ValueError,RuntimeError):return False

    def _within(self,prefix,reference,neck_yaw):
        if not self.contact_mode:
            return within_calibration_envelope(prefix,reference,neck_yaw,self.manifest)
        from so101_demo.act.contact_diagnostic import prefix_matches_diagnostic
        return (prefix['sequence']==self._next_segment and
            self._previous_segment_complete() and self._start_safe(reference,neck_yaw)
            and prefix_matches_diagnostic(
            prefix,self.contact_manifest)
        )

    def _live_ready(self):
        if not self.contact_mode:return True
        if not self._cup_reset_verified:return False
        observer=self.live_observer
        if observer is None or self.live_adapter is None:return False
        try:observer.start()
        except ValueError:return False
        return observer.hazard is None and observer.recorder.recorded_steps>0

    def _live_state(self):
        observer=self.live_observer
        return dict(cup_reset_verified=self._cup_reset_verified,
            observer_present=observer is not None,adapter_present=self.live_adapter is not None,
            observer_hazard=None if observer is None else observer.hazard,
            recorded_steps=0 if observer is None else observer.recorder.recorded_steps)

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
                if self.contact_mode:
                    address=self.path.cup_address
                    joint=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,'cup_free_joint')
                    if joint<0:return False
                    velocity_address=int(self.model.jnt_dofadr[joint])
                    if (any(abs(a-b)>1e-7 for a,b in zip(
                            frame['qpos'][address:address+3],
                            self.contact_manifest['cup_start_m'],strict=True))
                            or any(abs(a-b)>1e-7 for a,b in zip(
                                frame['qpos'][address+3:address+7],
                                (1.,0.,0.,0.),strict=True))
                            or any(abs(v)>1e-9 for v in frame['qvel'][velocity_address:velocity_address+6])):
                        return False
            # A completed driver ACK is a retained trusted write receipt. Before
            # that ACK, the actual reset ticket must still be authorized.
            if acknowledged:
                if self.contact_mode:self._cup_reset_verified=True
                return True
            with self.broker._lock:ticket=self.broker._reset_ticket
            if ticket is None or ticket[2]=='act' or ticket[3]!=self.manifest['session_id']:return False
            self.broker.ownership.require_ticket(ticket)
            if self.contact_mode:self._cup_reset_verified=True
            return True
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
            if self.contact_mode:
                if self.live_adapter is not None:
                    raise ValueError('CONTACT_DIAGNOSTIC_SECOND_RESET')
                from so101_demo.act.contact_live import (
                    LivePhysicsStream,LiveContactObserver,RosLiveContactAdapter)
                import mujoco
                joint=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,'cup_free_joint')
                if joint<0:raise ValueError('CONTACT_CUP_JOINT_INVALID')
                gripper_joint=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,'6')
                if gripper_joint<0:raise ValueError('CONTACT_GRIPPER_JOINT_INVALID')
                stream=LivePhysicsStream(session_id=self.manifest['session_id'],
                    reset_epoch=message.reset_epoch,model_sha256=self.path.model_sha256,
                    model_nq=self.model.nq,model_nv=self.model.nv,
                    cup_qpos_address=self.path.cup_address,
                    cup_qvel_address=int(self.model.jnt_dofadr[joint]),
                    release_qpos_address=int(self.model.jnt_qposadr[gripper_joint]),
                    release_qvel_address=int(self.model.jnt_dofadr[gripper_joint]),
                    release_open_q6=self.contact_manifest['joint_start_rad'][5],
                    release_stop_velocity_rad_s=self.manifest['stop_velocity_rad_s'],
                    diagnostic_limits=self.manifest['diagnostic_limits'],
                    output_path=self.evidence_root/'contact-live-physics.ndjson',
                    monotonic=self.monotonic)
                self.live_observer=LiveContactObserver(stream,
                    ros_clock=lambda:self.node.get_clock().now().nanoseconds*1e-9,
                    monotonic=self.monotonic,on_abort=self._fail)
                self.live_adapter=RosLiveContactAdapter(self.node,self.live_observer)
        except (KeyError,TypeError,ValueError,OSError,RuntimeError):self._fail('CONTACT_RESET_SNAPSHOT_INVALID')

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
        if self.contact_mode and not self._cup_reset_verified:
            raise ValueError('CONTACT_CUP_RESET_UNVERIFIED')
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
        if not self._start_safe(q[:6],q[6]) or not self._start_safe(reference,q[6]):
            raise ValueError('MOTION_ENVELOPE_INVALID')
        if abs(v[6])>self.manifest['stop_velocity_rad_s']:raise ValueError('MOTION_NECK_NOT_STOPPED')
        qpos=np.array(scene['qpos']);scene_q=[];scene_v=[]
        for name in ACT_JOINTS:
            jid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,name)
            if jid<0:raise ValueError('MOTION_MODEL_JOINT_INVALID')
            scene_q.append(float(qpos[self.model.jnt_qposadr[jid]]))
            scene_v.append(scene['qvel'][self.model.jnt_dofadr[jid]])
        if not self._start_safe(scene_q[:6],scene_q[6]):
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

    def _record_rejection(self,row):
        import json,os
        self.audit.append(row)
        self._audit_record.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n')
        self._audit_record.flush()
        os.fsync(self._audit_record.fileno())

    def check_prefix(self,prefix,snapshot):
        began=self.monotonic()
        try:
            if not self._live_ready():
                self._record_rejection(dict(boundary='approve',safe=False,reason='LIVE_NOT_READY',
                    snapshot_sim_time_s=snapshot.get('sim_time_s'),live_state=self._live_state()))
                return False
            start=snapshot['sim_time_s']+self.manifest['submit_lead_s']
            reference=self.driver.reference_state(start)
            full=self._snapshot(snapshot,start=start,reference=reference['positions'],reference_velocity=reference['velocities'])
            if not self._within(prefix,reference['positions'],self._joints[0][6]):
                self._record_rejection(dict(boundary='approve',safe=False,reason='PREFIX_WITHIN_INVALID',
                    snapshot_sim_time_s=snapshot['sim_time_s']))
                return False
            safe=self.path.check_path(prefix,full)
            row=dict(boundary='approve',safe=safe,path=dict(self.path.last_check),
                elapsed_wall_s=self.monotonic()-began,snapshot_sim_time_s=snapshot['sim_time_s'])
            if safe:self.audit.append(row)
            else:self._record_rejection(row)
            return safe
        except (KeyError,TypeError,ValueError,RuntimeError) as error:
            self._record_rejection(dict(boundary='approve',safe=False,error=repr(error),
                elapsed_wall_s=self.monotonic()-began,snapshot_sim_time_s=snapshot.get('sim_time_s')))
            return False

    def check_exact_goals(self,goals,prefix):
        def reject(reason):
            self._record_rejection(dict(boundary='exact_goals',safe=False,reason=reason))
            return False
        try:
            if not self._live_ready():return reject('LIVE_NOT_READY')
            if len(goals)!=2 or goals[0]['header_stamp_s']!=goals[1]['header_stamp_s'] or goals[0]['time_from_start_s']!=goals[1]['time_from_start_s']:
                return reject('GOAL_PAIR_MISMATCH')
            observation_time=finite(prefix['observation_time_s'],nonnegative=True)
            sample_time=observation_time
            if self.contact_mode:
                sample_time=finite(self.node.get_clock().now().nanoseconds*1e-9,nonnegative=True)
                if not 0<=sample_time-observation_time<=min(.1,self.manifest['max_age_s']):
                    return reject('OBSERVATION_STALE')
            base=dict(session_id=prefix['session_id'],attempt_id=prefix['attempt_id'],reset_epoch=self.contact_observer.epoch,
                sim_time_s=sample_time)
            start=goals[0]['header_stamp_s'];held=goals[0]['positions'][0]+goals[1]['positions'][0]
            reference=self.driver.reference_state(start)
            if any(abs(a-b)>1e-9 for a,b in zip(reference['positions'],held,strict=True)):
                return reject('REFERENCE_MISMATCH')
            full=self._snapshot(base,start=start,reference=held,reference_velocity=reference['velocities'])
            if not self._within(prefix,held,self._joints[0][6]):
                return reject('PREFIX_WITHIN_INVALID')
            safe=self.path.check_path(prefix,full)
            row=dict(boundary='exact_goals',safe=safe,path=dict(self.path.last_check))
            if safe:self.audit.append(row)
            else:self._record_rejection(row)
            if safe and self.contact_mode:self._next_segment+=1
            return safe
        except (KeyError,TypeError,ValueError,RuntimeError) as error:
            self._record_rejection(dict(boundary='exact_goals',safe=False,error=repr(error)))
            return False

    def poll(self):
        with self.scene_observer._lock:
            scene=self.scene_observer.last
            running=scene is not None and scene['paused'] is False
        if (self.contact_mode and not self._cup_reset_verified and scene is not None
                and scene['paused'] is True and scene['simulation_step']==0):
            self._pending_scene_reset(scene)
        if self.live_observer is not None:
            if running and getattr(self.live_observer, 'hazard', None) is None:
                self.live_observer.start()
                self.live_observer.poll()
            else:
                self.live_observer.suspend()
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
                if self.live_adapter is not None:self.live_adapter.close()
                for stream in (self._record,self._scene_record,self._audit_record):
                    stream.flush();os.fsync(stream.fileno());stream.close()
        finally:self.path.close()
