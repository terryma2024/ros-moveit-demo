"""Scoped neck search port with optional shared-broker dispatch."""

import threading
import time
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from so101_demo.act.contracts import finite,identifier
from .ros_execution import RosControllerPort


class RosNeckSearchPort:
    def __init__(self,node,*,session_id,attempt_id,goal_duration_s,submit_lead_s,stop_timeout_s,
                 stop_velocity_rad_s,max_age_s,command_guard,monotonic=time.monotonic,
                 progress=lambda:time.sleep(.001),broker=None,ticket_port=None):
        identifier(session_id);identifier(attempt_id)
        self.node,self.identity=node,(session_id,attempt_id)
        self.duration,self.lead,self.stop_timeout,self.max_age=(finite(v) for v in
            (goal_duration_s,submit_lead_s,stop_timeout_s,max_age_s))
        finite(stop_velocity_rad_s)
        if min(self.duration,self.lead,self.stop_timeout,self.max_age)<=0 or not callable(command_guard):
            raise ValueError('NECK_CONFIG_INVALID')
        if (broker is None)!=(ticket_port is None) or (ticket_port is not None and not callable(ticket_port)):
            raise ValueError('NECK_BROKER_CONFIG_INVALID')
        self.monotonic,self.progress,self.guard=monotonic,progress,command_guard
        self.broker=broker
        self._lock=threading.RLock();self._position=None;self._received=None;self._goals=[]
        if broker is None:
            self.client=ActionClient(node,FollowJointTrajectory,'/neck_controller/follow_joint_trajectory')
            self.port=RosControllerPort(node,self.client,('neck_yaw_joint',),stop_velocity_rad_s=stop_velocity_rad_s,
                                        max_age_s=max_age_s,monotonic=monotonic)
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
        self.subscription=node.create_subscription(JointState,'/joint_states',self._joint,qos_profile_sensor_data)

    def _joint(self,message):
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
        with self._lock:
            if (session_id,attempt_id)!=self.identity:raise PermissionError('NECK_SCOPE_INVALID')
            now=self.monotonic();sim=self.node.get_clock().now().nanoseconds*1e-9
            if observation_time_s>sim:raise ValueError('NECK_OBSERVATION_FUTURE')
            if self._received is None or not 0<=now-self._received<=self.max_age:
                raise PermissionError('NECK_FEEDBACK_STALE')
            if not 0<=sim-self._stamp<=self.max_age:raise PermissionError('NECK_FEEDBACK_STALE')
            if not self.client.server_is_ready():raise RuntimeError('NECK_ACTION_SERVER_UNAVAILABLE')
            if self.guard(self._position,target) is not True:raise PermissionError('SEARCH_UNSAFE_MOTION')
            # Both positions are absolute measured/target radians. Search keeps
            # each motion until fresh settled feedback, then advances its budget.
            goal=dict(joint_names=('neck_yaw_joint',),header_stamp_s=sim+self.lead,
                      time_from_start_s=(0.,self.duration),positions=((self._position,),(target,)))
            gid=self.port.send(goal);self._goals.append(gid)
            return gid

    def stop_and_confirm(self):
        with self._lock:
            for gid in self._goals:self.port.cancel(gid)
        deadline=self.monotonic()+self.stop_timeout
        while True:
            if self.broker is not None:self.broker.driver.refresh_stop()
            if self.port.stopped():return True
            if self.monotonic()>=deadline:raise RuntimeError('SEARCH_STOP_UNCONFIRMED')
            self.progress()
