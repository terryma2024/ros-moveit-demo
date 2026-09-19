"""The common broker's sole ROS action driver and closed message boundary."""

import json
import copy
import secrets
import threading
import time

from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTrajectoryControllerState
from control_msgs.srv import QueryTrajectoryState
from .ros_execution import seconds_message
from so101_mujoco_support.msg import SimulationEvidence, ScalarJointEvidence
from controller_manager_msgs.srv import SwitchController,ListControllers
from so101_demo.backends.mujoco.observer import ATOMIC_EVIDENCE_QOS
from moveit_msgs.action import ExecuteTrajectory
from mujoco_ros2_control_msgs.srv import ResetWorld,SetPause
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_action_status_default, qos_profile_sensor_data
from sensor_msgs.msg import JointState

from so101_demo.act.contracts import finite, fields
from so101_demo.act.joints import ARM_JOINTS, ACT_JOINTS, JOINT_LIMITS
from .leased_action_client import ACTIONS, message_dict, decoded

ACTION_TYPES={'arm':FollowJointTrajectory,'gripper':FollowJointTrajectory,'execute_trajectory':ExecuteTrajectory}
NAMES={'arm':ARM_JOINTS[:5],'gripper':ARM_JOINTS[5:],'execute_trajectory':ARM_JOINTS[:5]}


def validated_goal(kind,values):
    if kind not in ACTION_TYPES or not isinstance(values,dict):raise ValueError('ACTION_KIND_INVALID')
    allowed=(('trajectory','controller_names','controllers') if kind=='execute_trajectory' else
             ('trajectory','multi_dof_trajectory','path_tolerance','goal_tolerance','goal_time_tolerance','component_path_tolerance','component_goal_tolerance'))
    template=ACTION_TYPES[kind].Goal()
    allowed=set(allowed)&set(template.get_fields_and_field_types())
    if not set(values)<=allowed or 'trajectory' not in values:raise ValueError('GOAL_FIELDS_INVALID')
    try:
        json.dumps(values,allow_nan=False)
        goal=decoded(ACTION_TYPES[kind].Goal,values)
    except (AssertionError,AttributeError,TypeError,ValueError,OverflowError) as error:
        raise ValueError('GOAL_MESSAGE_INVALID') from error
    if kind=='execute_trajectory':
        if goal.trajectory.multi_dof_joint_trajectory.points or goal.trajectory.multi_dof_joint_trajectory.joint_names:
            raise ValueError('MULTI_DOF_NOT_ALLOWED')
        if any(name!='arm_controller' for name in getattr(goal,'controller_names',getattr(goal,'controllers',()))):raise ValueError('CONTROLLER_NOT_ALLOWED')
        trajectory=goal.trajectory.joint_trajectory
    else:
        if goal.multi_dof_trajectory.points or goal.multi_dof_trajectory.joint_names:
            raise ValueError('MULTI_DOF_NOT_ALLOWED')
        if goal.component_path_tolerance or goal.component_goal_tolerance:
            raise ValueError('COMPONENT_TOLERANCE_NOT_ALLOWED')
        trajectory=goal.trajectory
    if tuple(trajectory.joint_names)!=NAMES[kind] or not trajectory.points:
        raise ValueError('GOAL_JOINT_ORDER_INVALID')
    if trajectory.header.stamp.sec<0:raise ValueError('GOAL_STAMP_INVALID')
    previous=-1.
    for point in trajectory.points:
        when=point.time_from_start.sec+point.time_from_start.nanosec*1e-9
        if when<0 or when<=previous:raise ValueError('GOAL_TIME_INVALID')
        previous=when
        if len(point.positions)!=len(NAMES[kind]):raise ValueError('GOAL_POSITIONS_INVALID')
        for name,value in zip(NAMES[kind],point.positions,strict=True):
            if not JOINT_LIMITS[name][0]<=finite(value)<=JOINT_LIMITS[name][1]:raise ValueError('JOINT_LIMIT_INVALID')
        for values in (point.velocities,point.accelerations,point.effort):
            if values and len(values)!=len(NAMES[kind]):raise ValueError('GOAL_VECTOR_INVALID')
            for value in values:finite(value)
    if kind!='execute_trajectory':
        for tolerances in (goal.path_tolerance,goal.goal_tolerance):
            if any(item.name not in NAMES[kind] for item in tolerances):raise ValueError('TOLERANCE_JOINT_INVALID')
            for item in tolerances:
                for value in (item.position,item.velocity,item.acceleration):finite(value)
    return goal


class RosBrokerDriver:
    """Owns all three underlying action clients; status covers MoveIt downstream goals."""

    def __init__(self,node,*,stop_velocity_rad_s,max_age_s,monotonic=time.monotonic):
        self.node,self.monotonic=node,monotonic
        self.stop_velocity=finite(stop_velocity_rad_s);self.max_age=finite(max_age_s)
        if self.stop_velocity<0 or self.max_age<=0:raise ValueError('STOP_CONFIG_INVALID')
        self._lock=threading.RLock();self._records={};self._velocity=None;self._received=None
        self._statuses={};self._status_received={};self._cancel_all=[]
        self._pending_writes=[]
        self._baseline_futures={};self._stop_confirmed_at=None
        self._baseline_allow_existing=False
        self._positions=None;self._epoch=None;self._references={};self._scalar=None
        self.reference_timeout_s=min(.03,self.max_age)
        self._query_clients={kind:node.create_client(QueryTrajectoryState,'/'+('arm_controller' if kind=='arm' else 'gripper_controller')+'/query_state') for kind in ('arm','gripper')}
        self._disabled_ack=self._paused_ack=self._world_reset_ack=self._activated_ack=False
        self._reset_target=None;self._reset_initial=None;self._neck_velocity=None
        self._snapshot_refresh=None;self._write_records=[];self._write_receipts={}
        self.reset_client=node.create_client(ResetWorld,"/mujoco_ros2_control_node/reset_world")
        self._write_clients={'reset_world':self.reset_client,
            'pause':node.create_client(SetPause,'/mujoco_ros2_control_node/set_pause'),
            'switch_controllers':node.create_client(SwitchController,'/controller_manager/switch_controller'),
            'finish_reset':node.create_client(ListControllers,'/controller_manager/list_controllers')}
        self.unknown_goal_seen=False;self.hazard_reason=None
        self.clients={kind:ActionClient(node,ACTION_TYPES[kind],name) for name,kind in ACTIONS.items()}
        self.cancel_clients={kind:node.create_client(CancelGoal,name+'/_action/cancel_goal')
                             for name,kind in ACTIONS.items()}
        self.subscriptions=[node.create_subscription(JointState,'/joint_states',self._joints,qos_profile_sensor_data)]
        self.subscriptions.append(node.create_subscription(SimulationEvidence,'/so101/simulation/evidence',self._live_epoch,qos_profile_sensor_data))
        self.subscriptions.append(node.create_subscription(ScalarJointEvidence,'/so101/simulation/joints',self._scalar_joints,ATOMIC_EVIDENCE_QOS))
        for kind in ('arm','gripper'):
            self.subscriptions.append(node.create_subscription(JointTrajectoryControllerState,
                '/'+('arm_controller' if kind=='arm' else 'gripper_controller')+'/controller_state',
                lambda message,kind=kind:self._reference(kind,message),qos_profile_sensor_data))
        for name,kind in ACTIONS.items():
            self.subscriptions.append(node.create_subscription(GoalStatusArray,name+'/_action/status',
                lambda message,kind=kind:self._status(kind,message),qos_profile_action_status_default))

    def ready(self,kind):return self.clients[kind].server_is_ready()

    def _joints(self,message):
        if len(set(message.name))!=len(message.name) or len(message.velocity)!=len(message.name):return
        try:
            values=dict(zip(message.name,message.velocity,strict=True));ordered=tuple(finite(values[name]) for name in ARM_JOINTS)
        except (KeyError,ValueError):return
        try:
            positions=dict(zip(message.name,message.position,strict=True));positions=tuple(finite(positions[name]) for name in ARM_JOINTS)
        except (KeyError,ValueError):return
        with self._lock:
            self._velocity=ordered;self._positions=positions;self._received=self.monotonic()
            self._neck_velocity=values.get('neck_yaw_joint')

    def _scalar_joints(self,message):
        with self._lock:self._scalar=(message,self.monotonic())

    def _live_epoch(self,message):
        with self._lock:self._epoch=(message,self.monotonic())

    def _reference(self,kind,message):
        if tuple(message.joint_names)!=NAMES[kind]:return
        try:
            values=tuple(finite(value) for value in message.reference.positions)
            velocities=tuple(finite(value) for value in message.reference.velocities)
            if len(values)!=len(NAMES[kind]):return
        except ValueError:return
        stamp=message.header.stamp.sec+message.header.stamp.nanosec*1e-9
        if len(velocities)!=len(NAMES[kind]) or not 0<=stamp:return
        with self._lock:self._references[kind]=(values,velocities,self.monotonic(),stamp)

    def _reference_interval(self,kind):
        candidates=[]
        for gid,record in self._records.items():
            matches=(record['kind']==kind or (kind=='arm' and record['kind']=='execute_trajectory'))
            if not matches:continue
            result=record['result']
            if record['accepted'] is None:return None
            if record['accepted'] is True and result is None and not record.get('cancel_requested',False):
                candidates.append((gid,record.get('ros_goal_id')))
        return tuple(candidates) or None

    def current_reference(self,when):
        return self.reference_state(when)['positions']

    def reference_state(self,when):
        when=finite(when,nonnegative=True);rows=[];vrows=[];arows=[]
        # A ROS service wait must never hold the driver lock: the same executor
        # delivers joint/status updates and query responses needed by Stop.
        for kind in ('arm','gripper'):
            with self._lock:
                now=self.monotonic()
                if kind not in self._references:raise RuntimeError('REFERENCE_UNAVAILABLE')
                values,velocities,received,stamp=self._references[kind]
                if not 0<=now-received<=self.max_age:raise RuntimeError('REFERENCE_STALE')
                moving=any(abs(value)>self.stop_velocity for value in velocities)
                interval=self._reference_interval(kind)
                pending=any(record['accepted'] is None and (record['kind']==kind or (kind=='arm' and record['kind']=='execute_trajectory')) for record in self._records.values())
                if interval is None:
                    if when<stamp:raise RuntimeError('REFERENCE_TIME_INVALID')
                    if moving or pending:raise RuntimeError('REFERENCE_INTERVAL_INVALID')
                    rows.extend(values);vrows.extend(velocities);arows.extend((0.,)*len(values));continue
                if when<stamp:
                    # Publication can advance during the first controller's
                    # query. An exact query remains valid inside the same
                    # proven accepted interval; a stationary cache cannot
                    # reconstruct the past. Missing acceptance stamps deny it.
                    accepted=[self._records[gid].get('accepted_sim_s') for gid,_ in interval]
                    if any(value is None or when<finite(value,nonnegative=True) for value in accepted):
                        raise RuntimeError('REFERENCE_TIME_INVALID')
                client=self._query_clients[kind]
            if not client.service_is_ready():raise RuntimeError('REFERENCE_QUERY_UNAVAILABLE')
            request=QueryTrajectoryState.Request();seconds_message(when,request.time)
            future=client.call_async(request);deadline=self.monotonic()+self.reference_timeout_s
            while not future.done():
                with self._lock:
                    if self._reference_interval(kind)!=interval:raise RuntimeError('REFERENCE_INTERVAL_INVALID')
                if self.monotonic()>=deadline:raise RuntimeError('REFERENCE_QUERY_TIMEOUT')
                time.sleep(.001)
            try:
                result=future.result()
                positions=tuple(finite(v) for v in result.position)
                if (result.success is not True or tuple(result.name)!=NAMES[kind]
                        or len(positions)!=len(NAMES[kind])
                        or len(result.velocity)!=len(positions) or len(result.acceleration)!=len(positions)):
                    raise ValueError('response')
                for v in (*result.velocity,*result.acceleration):finite(v)
            except (AttributeError,TypeError,ValueError) as error:raise RuntimeError('REFERENCE_QUERY_INVALID') from error
            with self._lock:
                if self._reference_interval(kind)!=interval:raise RuntimeError('REFERENCE_INTERVAL_INVALID')
                if not 0<=self.monotonic()-received<=self.max_age:raise RuntimeError('REFERENCE_STALE')
                rows.extend(positions);vrows.extend(result.velocity);arows.extend(result.acceleration)
        return dict(positions=tuple(rows),velocities=tuple(vrows),accelerations=tuple(arows),requested_sim_time_s=when)

    def approval_snapshot(self,ticket):
        with self._lock:
            if self._epoch is None:raise RuntimeError('RESET_EPOCH_UNAVAILABLE')
            scalar,received=self._epoch
            if scalar.simulation_session_id!=ticket[3]:raise PermissionError('SESSION_MISMATCH')
            now=self.monotonic()
            if not 0<=now-received<=self.max_age or self._received is None or not 0<=now-self._received<=self.max_age:
                raise RuntimeError('SNAPSHOT_STALE')
            sim_time=self.node.get_clock().now().nanoseconds*1e-9
            snapshot=dict(session_id=ticket[3],attempt_id=ticket[4],reset_epoch=scalar.reset_epoch,
                          sim_time_s=sim_time,positions=self._positions,velocities=self._velocity)
        snapshot['reference']=self.current_reference(sim_time)
        with self._lock:
            if self._epoch[0].reset_epoch!=snapshot['reset_epoch']:raise RuntimeError('RESET_EPOCH_CHANGED')
        return snapshot

    def _reconcile_status(self,kind):
        active=self._statuses.get(kind,{})
        known={record.get('ros_goal_id') for record in self._records.values() if record['kind']==kind}
        for record in self._records.values():
            known.update(record.get('downstream_goal_ids',{}).get(kind,{}))
        unknown=active.keys()-known
        teachers=[record for record in self._records.values() if record['kind']=='execute_trajectory'
                  and record['accepted'] is True and record['result'] is None]
        pending=any(record['kind'] in (kind,'execute_trajectory') and record['accepted'] is None
                    for record in self._records.values())
        if unknown and kind in ('arm','gripper') and teachers:
            chain=teachers[-1].setdefault('downstream_goal_ids',{}).setdefault(kind,{})
            for goal_id in unknown:chain[goal_id]=dict(status=active[goal_id],seen_wall_s=self.monotonic())
        elif unknown and not pending:
            self.unknown_goal_seen=True;self.hazard_reason='UNKNOWN_ACTIVE_GOAL'

    def _status(self,kind,message):
        with self._lock:
            self._statuses[kind]={bytes(item.goal_info.goal_id.uuid).hex():item.status
                    for item in message.status_list if item.status in (1,2,3)}
            self._status_received[kind]=self.monotonic()
            self._reconcile_status(kind)

    def validate(self,kind,goal):return validated_goal(kind,goal)

    def submit(self,kind,goal):
        if self.hazard_reason:raise RuntimeError(self.hazard_reason)
        if any(not future.done() for future in self._pending_writes):raise RuntimeError('RESET_PENDING')
        if not self.ready(kind):raise RuntimeError('ACTION_SERVER_UNAVAILABLE')
        gid=secrets.token_hex(16)
        record=dict(kind=kind,accepted=None,handle=None,result=None,feedback=None,
                    cancel_requested=False,cancel_response=None,error=None,submitted_goal=copy.deepcopy(goal),
                    submitted_sim_s=self.node.get_clock().now().nanoseconds*1e-9)
        with self._lock:self._records[gid]=record
        try:
            future=self.clients[kind].send_goal_async(goal,
                feedback_callback=lambda message:self._feedback(gid,message))
            future.add_done_callback(lambda response:self._accepted(gid,response))
        except Exception as error:
            with self._lock:record['accepted']=None;record['error']=repr(error);self.hazard_reason='GOAL_SEND_UNCERTAIN'
            raise
        return gid

    def _feedback(self,gid,message):
        with self._lock:self._records[gid]['feedback']=message_dict(message.feedback)

    def _accepted(self,gid,future):
        with self._lock:
            record=self._records[gid]
            try:
                handle=future.result();record['handle']=handle;record['accepted']=bool(handle.accepted)
                if hasattr(self,'node'):record['accepted_sim_s']=self.node.get_clock().now().nanoseconds*1e-9
                if handle.accepted:
                    record['ros_goal_id']=bytes(handle.goal_id.uuid).hex()
                    handle.get_result_async().add_done_callback(lambda result:self._result(gid,result))
                    if record['cancel_requested']:self._cancel(gid)
            except Exception as error:record['error']=repr(error);self.hazard_reason='GOAL_RESPONSE_LOST'
            for kind in ACTION_TYPES:self._reconcile_status(kind)

    def _result(self,gid,future):
        with self._lock:
            try:self._records[gid]['result']=future.result()
            except Exception as error:self._records[gid]['error']=repr(error);self.hazard_reason='GOAL_RESULT_LOST'
            for kind in ACTION_TYPES:self._reconcile_status(kind)

    def _cancel(self,gid):
        record=self._records[gid]
        try:record['handle'].cancel_goal_async().add_done_callback(lambda f:self._cancel_result(gid,f))
        except Exception as error:record['error']=repr(error);self.hazard_reason='CANCEL_RESPONSE_LOST'

    def _cancel_result(self,gid,future):
        with self._lock:
            try:self._records[gid]['cancel_response']=message_dict(future.result())
            except Exception as error:self._records[gid]['error']=repr(error);self.hazard_reason='CANCEL_RESPONSE_LOST'

    def cancel(self,gid):
        with self._lock:
            record=self._records[gid]
            if record['cancel_requested']:return
            record['cancel_requested']=True
            if record['accepted'] is True:self._cancel(gid)
            elif record['accepted'] is False:
                # No actual accepted goal exists. Preserve the real rejected
                # response, rather than claiming a controller cancellation ACK.
                record['cancel_response']=message_dict(CancelGoal.Response(return_code=2))

    def stop_all(self,reason):
        with self._lock:
            for gid in self._records:self.cancel(gid)
            # Authorized MoveIt executes send their own downstream controller
            # goals. Cancel those controlled-stack goals too, and observe status
            # and fresh measured velocity before releasing the ownership barrier.
            self._request_stop_baseline(allow_existing=True)

    def _request_stop_baseline(self,*,allow_existing):
        if self._baseline_futures and any(not f.done() for f in self._baseline_futures.values()):return
        if not all(client.service_is_ready() for client in self.cancel_clients.values()):return
        self._stop_confirmed_at=None;self._baseline_allow_existing=allow_existing
        self._baseline_futures={kind:client.call_async(CancelGoal.Request())
                                for kind,client in self.cancel_clients.items()}
        self._cancel_all.extend(self._baseline_futures.values())

    def _read_stop_baseline(self):
        if not self._baseline_futures or any(not f.done() for f in self._baseline_futures.values()):return
        if self._stop_confirmed_at is not None:return
        try:
            responses=[future.result() for future in self._baseline_futures.values()]
            if any(response.return_code!=0 for response in responses):return
            if not self._baseline_allow_existing and any(response.goals_canceling for response in responses):
                self.unknown_goal_seen=True;self.hazard_reason='UNKNOWN_ACTIVE_GOAL';return
            self._stop_confirmed_at=self.monotonic()
        except Exception:self.hazard_reason='CANCEL_RESPONSE_LOST'

    def refresh_idle(self):
        with self._lock:
            self._read_stop_baseline()
            self._refresh_paused_audit()
            if any(record['accepted'] is not False and record['result'] is None
                   for record in self._records.values()):return
            if self._stop_confirmed_at is None or self.monotonic()-self._stop_confirmed_at>=self.max_age*.5:
                self._request_stop_baseline(allow_existing=False)

    def refresh_stop(self):
        with self._lock:
            self._read_stop_baseline()
            self._refresh_paused_audit()
            if self._stop_confirmed_at is None or self.monotonic()-self._stop_confirmed_at>=self.max_age*.5:
                self._request_stop_baseline(allow_existing=True)

    def stopped(self):
        with self._lock:
            now=self.monotonic()
            if any(not future.done() for future in self._pending_writes):return False
            if any(not event.is_set() for event in getattr(self,'_write_receipts',{}).values()):return False
            for future in self._pending_writes:
                try:future.result()
                except Exception:return False
            velocities=self._velocity if self._received is not None and 0<=now-self._received<=self.max_age else None
            scalar=getattr(self,'_scalar',None)
            if scalar is not None:
                message,received=scalar
                if message.paused and 0<=now-received<=self.max_age and self._epoch is not None:
                    epoch=self._epoch[0]
                    if message.reset_epoch==epoch.reset_epoch and message.simulation_session_id==epoch.simulation_session_id:
                        if len(message.joint_names)==7 and set(message.joint_names)==set(ACT_JOINTS) and len(message.velocities_rad_s)==7:
                            named=dict(zip(message.joint_names,message.velocities_rad_s,strict=True))
                            try:velocities=tuple(finite(named[name]) for name in ARM_JOINTS)
                            except ValueError:return False
            if velocities is None or any(abs(value)>self.stop_velocity for value in velocities):return False
            if any(not future.done() for future in self._cancel_all):return False
            for future in self._cancel_all:
                try:future.result()
                except Exception:return False
            if self._stop_confirmed_at is None or not 0<=now-self._stop_confirmed_at<=self.max_age:return False
            for kind in ACTION_TYPES:
                if not self.ready(kind) or self._statuses.get(kind):return False
            for record in self._records.values():
                if record['accepted'] is None:return False
                if record['accepted'] is False:continue
                if record['result'] is None or record['result'].status not in (4,5,6):return False
            return True

    def goal_state(self,gid):
        with self._lock:
            record=self._records[gid];wrapped=record['result']
            return dict(accepted=record['accepted'],status=None if wrapped is None else wrapped.status,
                result=None if wrapped is None else message_dict(wrapped.result),
                feedback=record['feedback'],cancel_response=record['cancel_response'],
                driver_error=record['error'],ros_goal_uuid=record.get('ros_goal_id'),
                downstream_goal_ids=record.get('downstream_goal_ids',{}))


    def diagnostics(self):
        with self._lock:
            cancel=[]
            for future in self._cancel_all:
                row={'done':future.done()}
                if future.done():
                    try:row['response']=message_dict(future.result())
                    except Exception as error:row['error']=repr(error)
                cancel.append(row)
            return dict(wall_monotonic_s=self.monotonic(),positions_rad=self._positions,
                velocities_rad_s=self._velocity,joint_received_wall_s=self._received,
                active_statuses=self._statuses,status_received_wall_s=self._status_received,
                stop_confirmed_at_wall_s=self._stop_confirmed_at,cancel_confirmations=cancel,
                goals={gid:self.goal_state(gid) for gid in self._records},
                writes=list(self._write_records),hazard_reason=self.hazard_reason,
                paused_scalar=None if self._scalar is None else message_dict(self._scalar[0]),
                paused_scalar_received_wall_s=None if self._scalar is None else self._scalar[1])

    def validate_reset(self,values):
        fields(values,('keyframe','state_overrides'))
        try:request=decoded(ResetWorld.Request,values)
        except (AssertionError,ValueError,TypeError,AttributeError) as error:
            raise ValueError('RESET_MESSAGE_INVALID') from error
        if request.keyframe not in ('task_start','cup_test_forward_5cm','cup_test_left_5cm','cup_test_right_5cm'):
            raise ValueError('RESET_KEYFRAME_INVALID')
        joints=request.state_overrides.joint_states
        if (len(set(joints.name))!=7 or set(joints.name)!=set(ACT_JOINTS)
                or len(joints.position)!=7 or len(joints.velocity)!=7 or joints.effort):
            raise ValueError('RESET_JOINTS_INVALID')
        for name,position,velocity in zip(joints.name,joints.position,joints.velocity,strict=True):
            position=finite(position);finite(velocity)
            if velocity!=0.:raise ValueError('RESET_VELOCITY_NOT_ZERO')
            if name in JOINT_LIMITS and not JOINT_LIMITS[name][0]<=position<=JOINT_LIMITS[name][1]:
                raise ValueError('RESET_JOINT_LIMIT_INVALID')
        if len(request.state_overrides.free_joints)>1:raise ValueError('RESET_FREE_JOINT_INVALID')
        for joint in request.state_overrides.free_joints:
            if joint.name!='cup_free_joint':raise ValueError('RESET_FREE_JOINT_INVALID')
            pose=joint.pose.pose;twist=joint.twist.twist
            for point in (pose.position,twist.linear,twist.angular):
                for key in ('x','y','z'):finite(getattr(point,key))
            quaternion=tuple(finite(getattr(pose.orientation,key)) for key in ('x','y','z','w'))
            if abs(sum(x*x for x in quaternion)-1.)>1e-6:raise ValueError('RESET_QUATERNION_INVALID')
            if any(getattr(vector,key)!=0. for vector in (twist.linear,twist.angular) for key in ('x','y','z')):
                raise ValueError('RESET_FREE_VELOCITY_NOT_ZERO')
        return request

    def pause_idempotent(self,paused):
        with self._lock:
            return type(paused) is bool and self._epoch is not None and self._epoch[0].paused is paused

    def _refresh_paused_audit(self):
        if self._epoch is None or not self._epoch[0].paused:return
        if self._scalar is not None and self.monotonic()-self._scalar[1]<self.max_age*.5:return
        if self._snapshot_refresh is not None and not self._snapshot_refresh.done():return
        if any(not future.done() for future in self._pending_writes):return
        client=self._write_clients['pause']
        if client.service_is_ready():
            self._snapshot_refresh=self.begin_write('pause',SetPause.Request(paused=True))

    def prepare_reset(self):
        with self._lock:
            if self._epoch is None:raise RuntimeError('RESET_EPOCH_UNAVAILABLE')
            if not self.stopped():raise PermissionError('CONTROL_NOT_STOPPED')
            self._reset_initial=self._epoch[0]
            self._reset_target=None
            self._disabled_ack=self._paused_ack=self._world_reset_ack=self._activated_ack=False

    def validate_write(self,operation,values):
        if operation=='reset_world':
            fields(values,('reset_request',))
            return self.validate_reset(values['reset_request'])
        if operation=='pause':
            fields(values,('paused',))
            if type(values['paused']) is not bool:raise ValueError('PAUSE_INVALID')
            return SetPause.Request(paused=values['paused'])
        if operation=='switch_controllers':
            fields(values,('activate','deactivate'))
            activate,deactivate=values['activate'],values['deactivate']
            names={'arm_controller','gripper_controller','neck_controller'}
            if not isinstance(activate,list) or not isinstance(deactivate,list):raise ValueError('RESET_CONTROLLERS_INVALID')
            if ((activate and (set(activate)!=names or len(activate)!=3 or deactivate))
                    or (deactivate and (set(deactivate)!=names or len(deactivate)!=3 or activate))
                    or not (activate or deactivate)):
                raise ValueError('RESET_CONTROLLERS_INVALID')
            request=SwitchController.Request(activate_controllers=activate,deactivate_controllers=deactivate,
                strictness=SwitchController.Request.STRICT,activate_asap=True)
            request.timeout.sec=5
            return request
        if operation=='finish_reset':
            fields(values,())
            return ListControllers.Request()
        raise ValueError('WRITE_OPERATION_INVALID')

    def begin_write(self,operation,request):
        with self._lock:
            if any(not future.done() for future in self._pending_writes):raise RuntimeError('SERVICE_WRITE_PENDING')
            if operation=='reset_world':
                if not self._disabled_ack or not self._paused_ack:
                    raise PermissionError('RESET_CONTROLLERS_NOT_ACKNOWLEDGED')
                self._reset_target=request.state_overrides.joint_states
            if operation=='switch_controllers':
                if self._paused_ack:raise PermissionError('SWITCH_WHILE_PAUSED')
                if request.activate_controllers and not self._world_reset_ack:
                    raise PermissionError('RESET_NOT_APPLIED')
            client=self._write_clients[operation]
            if not client.service_is_ready():raise RuntimeError('SERVICE_UNAVAILABLE')
            record={'operation':operation,'request':message_dict(request),'submitted_wall_s':self.monotonic(),
                    'response':None,'received_wall_s':None}
            self._write_records.append(record)
            future=client.call_async(request);self._pending_writes.append(future)
            self._write_receipts[future]=threading.Event()
            future.add_done_callback(lambda result:self._write_completed(operation,request,record,result))
            return future

    def _write_completed(self,operation,request,record,future):
        with self._lock:
            try:
                response=future.result();record['response']=message_dict(response);record['received_wall_s']=self.monotonic()
                if operation=='pause' and response.success:self._paused_ack=request.paused
                if operation=='switch_controllers' and response.ok:
                    self._disabled_ack=bool(request.deactivate_controllers)
                    self._activated_ack=bool(request.activate_controllers)
                if operation=='reset_world' and response.success:self._world_reset_ack=True
                if operation!='finish_reset' and not getattr(response,'success',getattr(response,'ok',False)):
                    self.hazard_reason='SERVICE_WRITE_REJECTED'
            except Exception as error:record['error']=repr(error);self.hazard_reason='SERVICE_RESPONSE_LOST'
            finally:self._write_receipts[future].set()

    def await_write(self,future):
        deadline=self.monotonic()+5.
        while (not future.done() or not self._write_receipts[future].is_set()) and self.monotonic()<deadline:time.sleep(.001)
        if not future.done() or not self._write_receipts[future].is_set():self.hazard_reason='SERVICE_RESPONSE_LOST';raise RuntimeError('SERVICE_RESPONSE_LOST')
        try:return message_dict(future.result())
        except Exception as error:self.hazard_reason='SERVICE_RESPONSE_LOST';raise RuntimeError('SERVICE_RESPONSE_LOST') from error

    def finish_reset(self,controller_readback):
        with self._lock:
            if not self._world_reset_ack or not self._activated_ack or not self._paused_ack:return False
            if self._scalar is None or self._reset_target is None or self._reset_initial is None:return False
            frame,received=self._scalar
            if not 0<=self.monotonic()-received<=self.max_age or not frame.paused:return False
            if (frame.simulation_session_id!=self._reset_initial.simulation_session_id
                    or frame.reset_epoch!=self._reset_initial.reset_epoch+1):return False
            if len(set(frame.joint_names))!=7 or set(frame.joint_names)!=set(ACT_JOINTS):return False
            if len(frame.positions_rad)!=7 or len(frame.velocities_rad_s)!=7:return False
            q=dict(zip(frame.joint_names,frame.positions_rad,strict=True))
            expected=dict(zip(self._reset_target.name,self._reset_target.position,strict=True))
            if any(abs(finite(q[name])-expected[name])>.002 for name in ACT_JOINTS):return False
            if any(abs(finite(value))>self.stop_velocity for value in frame.velocities_rad_s):return False
            states={item['name']:item['state'] for item in controller_readback['controller']}
            return all(states.get(name)=='active' for name in ('arm_controller','gripper_controller','neck_controller'))
