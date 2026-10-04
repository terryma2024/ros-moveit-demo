"""Scoped neck search port with optional shared-broker dispatch."""

import threading
import time
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from so101_demo.act.contracts import finite,identifier
from so101_demo.act.head_feedback import FeedbackPolicy
from .ros_execution import RosControllerPort


class RosNeckSearchPort:
    def __init__(self,node,*,session_id,attempt_id,goal_duration_s,submit_lead_s,stop_timeout_s,
                 stop_velocity_rad_s,max_age_s,command_guard,monotonic=time.monotonic,
                 progress=lambda:time.sleep(.001),broker=None,ticket_port=None,
                 controller_port=None,feedback_policy=None,head_trajectory_guard=None,
                 head_stop_handoff=None):
        identifier(session_id);identifier(attempt_id)
        self.node,self.identity=node,(session_id,attempt_id)
        self.feedback_policy=None if feedback_policy is None else FeedbackPolicy.parse(feedback_policy)
        self.duration,self.lead,self.stop_timeout,self.max_age=(finite(v) for v in
            (goal_duration_s,submit_lead_s,stop_timeout_s,max_age_s))
        finite(stop_velocity_rad_s)
        if min(self.duration,self.lead,self.stop_timeout,self.max_age)<=0 or not callable(command_guard):
            raise ValueError('NECK_CONFIG_INVALID')
        if (broker is None)!=(ticket_port is None) or (ticket_port is not None and not callable(ticket_port)):
            raise ValueError('NECK_BROKER_CONFIG_INVALID')
        if head_stop_handoff is not None and not callable(head_stop_handoff):
            raise ValueError('NECK_HEAD_STOP_HANDOFF_INVALID')
        self.monotonic,self.progress,self.guard=monotonic,progress,command_guard
        self.broker=broker
        self._lock=threading.RLock();self._position=None;self._received=None;self._goals=[]
        self._stopped=False;self._head_dispatching=False;self._head_trajectory_guard=None
        self._head_stop_handoff=head_stop_handoff
        self._head_stop_occurrence_ns=None;self._head_stop_deadline_ns=None
        self._head_stop_handoff_started=False;self._head_cancel_requested=set()
        self._head_stop_handoff_error=None
        if head_trajectory_guard is not None:
            from .head_trajectory_guard import HeadTrajectoryGuard
            if (type(head_trajectory_guard) is not HeadTrajectoryGuard or broker is not None
                    or controller_port is None or self.feedback_policy is None):
                raise ValueError('NECK_HEAD_TRAJECTORY_BINDING_INVALID')
            self._head_trajectory_guard=head_trajectory_guard
        if controller_port is not None:
            if broker is not None or self.feedback_policy is None:
                raise ValueError('NECK_INJECTED_PORT_SCOPE_INVALID')
            underlying=getattr(controller_port,'port',controller_port)
            self.client=underlying.client;self.port=controller_port
            if getattr(underlying,'feedback_policy',None)!=self.feedback_policy:
                raise ValueError('NECK_FEEDBACK_POLICY_MISMATCH')
        elif broker is None:
            self.client=ActionClient(node,FollowJointTrajectory,'/neck_controller/follow_joint_trajectory')
            self.port=RosControllerPort(node,self.client,('neck_yaw_joint',),stop_velocity_rad_s=stop_velocity_rad_s,
                                        max_age_s=max_age_s,monotonic=monotonic,
                                        feedback_policy=self.feedback_policy)
        else:
            from .broker_execution import BrokerControllerPort
            self.client=broker.driver.clients['neck']
            def scoped_ticket():
                ticket=ticket_port()
                if (not isinstance(ticket,tuple) or len(ticket)!=5
                        or ticket[2:]!=('act',*self.identity)):
                    raise PermissionError('NECK_SCOPE_INVALID')
                return ticket
            self.port=BrokerControllerPort(broker,'neck',scoped_ticket)
        self.subscription=None if self.feedback_policy is not None else node.create_subscription(
            JointState,'/joint_states',self._joint,qos_profile_sensor_data)

    def _joint(self,message):
        if self.feedback_policy is not None:
            # Direct input compatibility; Head v2 registers only the port's own
            # subscription, so no second callback forwards the same observation.
            self.port._feedback(message)
            return
        if (len(set(message.name))!=len(message.name) or len(message.position)!=len(message.name)
                or len(message.velocity)!=len(message.name) or 'neck_yaw_joint' not in message.name):return
        try:
            index=message.name.index('neck_yaw_joint');q=finite(message.position[index]);finite(message.velocity[index])
            stamp=finite(message.header.stamp.sec+message.header.stamp.nanosec*1e-9,nonnegative=True)
        except (KeyError,ValueError):return
        with self._lock:
            self._position,self._received,self._stamp=q,self.monotonic(),stamp
            if self.broker is None:self.port._feedback(message)

    def command_neck(self,target,*,session_id,attempt_id,observation_time_s):
        target=finite(target);observation_time_s=finite(observation_time_s,nonnegative=True)
        if self._head_trajectory_guard is not None:
            return self._command_prepared_head(target, session_id=session_id,
                attempt_id=attempt_id, observation_time_s=observation_time_s)
        if self.feedback_policy is not None:
            underlying=getattr(self.port,'port',self.port)
            snapshot=underlying.feedback_snapshot()
            with self._lock:
                self._position=snapshot['positions'][0]
                self._received=snapshot['wall_s'];self._stamp=snapshot['source_ns']*1e-9
        with self._lock:
            if (session_id,attempt_id)!=self.identity:raise PermissionError('NECK_SCOPE_INVALID')
            now=self.monotonic();sim=self.node.get_clock().now().nanoseconds*1e-9
            if observation_time_s>sim:raise ValueError('NECK_OBSERVATION_FUTURE')
            if self.feedback_policy is None and (
                    self._received is None or not 0<=now-self._received<=self.max_age):
                raise PermissionError('NECK_FEEDBACK_STALE')
            if self.feedback_policy is None and not 0<=sim-self._stamp<=self.max_age:
                raise PermissionError('NECK_FEEDBACK_STALE')
            if not self.client.server_is_ready():raise RuntimeError('NECK_ACTION_SERVER_UNAVAILABLE')
            if self.guard(self._position,target) is not True:raise PermissionError('SEARCH_UNSAFE_MOTION')
            # Both positions are absolute measured/target radians. Search keeps
            # each motion until fresh settled feedback, then advances its budget.
            goal=dict(joint_names=('neck_yaw_joint',),header_stamp_s=sim+self.lead,
                      time_from_start_s=(0.,self.duration),positions=((self._position,),(target,)))
            gid=self.port.send(goal);self._goals.append(gid)
            return gid

    def _command_prepared_head(self,target,*,session_id,attempt_id,observation_time_s):
        if (session_id,attempt_id)!=self.identity:
            raise PermissionError('NECK_SCOPE_INVALID')
        sim=self.node.get_clock().now().nanoseconds*1e-9
        if observation_time_s>sim:raise ValueError('NECK_OBSERVATION_FUTURE')
        with self._lock:
            if self._stopped:raise PermissionError('NECK_STOPPED')
            if self._head_dispatching:raise PermissionError('NECK_HEAD_DISPATCH_BUSY')
        # Snapshot, quintic construction, canonicalization and private MuJoCo
        # replay happen without holding the neck stop/cache lock.
        prepared=self._head_trajectory_guard.prepare(target)
        if not self.client.server_is_ready():
            raise RuntimeError('NECK_ACTION_SERVER_UNAVAILABLE')
        with self._lock:
            if self._stopped:raise PermissionError('NECK_STOPPED')
            if self._head_dispatching:raise PermissionError('NECK_HEAD_DISPATCH_BUSY')
            self._head_dispatching=True
        try:
            gid=self.port.send_prepared_head(prepared)
            with self._lock:
                # If stop raced the native/SDK boundary, retain the UUID so
                # stop_and_confirm can cancel and reconcile it before return.
                self._goals.append(gid)
            return gid
        finally:
            with self._lock:
                self._head_dispatching=False

    def stop_and_confirm(self):
        if self._head_trajectory_guard is not None:
            with self._lock:
                if self._head_stop_occurrence_ns is None:
                    self._head_stop_occurrence_ns=round(self.monotonic()*1e9)
                    self._head_stop_deadline_ns=(self._head_stop_occurrence_ns
                        + round(self.stop_timeout*1e9))
                self._stopped=True
                occurred_ns=self._head_stop_occurrence_ns
                deadline_ns=self._head_stop_deadline_ns
                start_handoff=not self._head_stop_handoff_started
                if start_handoff:self._head_stop_handoff_started=True
                handoff=self._head_stop_handoff
                handoff_error=self._head_stop_handoff_error
            self._head_trajectory_guard.stop()
            stop_admission=getattr(self.port,'stop_admission',None)
            if callable(stop_admission):stop_admission()
            if not callable(handoff):
                raise RuntimeError('SEARCH_STOP_HANDOFF_UNBOUND')
            if start_handoff:
                # This is only a local close initiation. Its return value is
                # diagnostic; raw terminal and quiet feedback still decide stop.
                # The injected callback must be bounded/nonblocking. If it
                # fails, retain that failure and still initiate every cancel.
                try:
                    handoff(occurred_ns,deadline_ns)
                except Exception as error:
                    handoff_error=type(error).__name__
                    with self._lock:self._head_stop_handoff_error=handoff_error
            cancelled=set()
            while True:
                with self._lock:
                    dispatching=self._head_dispatching
                    goals=tuple(self._goals)
                inventory=getattr(self.port,'inventory',{})
                if type(inventory) is dict:
                    goals=tuple(dict.fromkeys((*goals,*inventory.keys())))
                for gid in goals:
                    if gid in cancelled:continue
                    cancelled.add(gid)
                    try:self.port.cancel(gid)
                    except Exception:pass
                if handoff_error is None and not dispatching and self.port.stopped():return True
                if round(self.monotonic()*1e9)>=deadline_ns:
                    if handoff_error is not None:
                        raise RuntimeError('SEARCH_STOP_HANDOFF_FAILED')
                    raise RuntimeError('SEARCH_STOP_UNCONFIRMED')
                self.progress()
        with self._lock:
            for gid in self._goals:self.port.cancel(gid)
        deadline=self.monotonic()+self.stop_timeout
        while True:
            if self.broker is not None:self.broker.driver.refresh_stop()
            if self.port.stopped():return True
            if self.monotonic()>=deadline:raise RuntimeError('SEARCH_STOP_UNCONFIRMED')
            self.progress()
