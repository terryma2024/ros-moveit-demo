"""Broker-owned ROS action port; cancellation requires terminal and velocity proof."""

import math
import secrets
import threading
import time

from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import JointState
from rclpy.qos import qos_profile_sensor_data
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from so101_demo.act.contracts import finite


def seconds_message(value,message):
    ns=round(finite(value,nonnegative=True)*1e9)
    message.sec,message.nanosec=divmod(ns,1000000000)
    return message


def trajectory_message(goal):
    names=tuple(goal['joint_names']); rows=tuple(goal['positions']); times=tuple(goal['time_from_start_s'])
    if (not names or len(set(names))!=len(names) or len(rows)!=len(times) or not rows
            or any(len(row)!=len(names) for row in rows)):
        raise ValueError('CONTROLLER_GOAL_INVALID')
    wire=JointTrajectory(joint_names=list(names))
    seconds_message(goal['header_stamp_s'],wire.header.stamp)
    previous=-1.
    for offset,row in zip(times,rows,strict=True):
        offset=finite(offset,nonnegative=True)
        if offset<=previous: raise ValueError('CONTROLLER_TIME_INVALID')
        previous=offset
        point=JointTrajectoryPoint(positions=[finite(value) for value in row])
        seconds_message(offset,point.time_from_start); wire.points.append(point)
    return wire


class RosControllerPort:
    """Inject the sole underlying broker action client, never create a bypass."""

    def __init__(self,node,action_client,names,*,stop_velocity_rad_s,max_age_s,
                 monotonic=time.monotonic):
        self.client=action_client;self.names=tuple(names);self.monotonic=monotonic
        self.stop_velocity=finite(stop_velocity_rad_s);self.max_age=finite(max_age_s)
        if self.stop_velocity<0 or self.max_age<=0: raise ValueError('STOP_CONFIG_INVALID')
        self._lock=threading.RLock();self._goals={};self._velocity=None;self._received=None
        self._subscription=node.create_subscription(JointState,'/joint_states',self._feedback,
                                                    qos_profile_sensor_data)

    def _feedback(self,message):
        if (len(set(message.name))!=len(message.name)
                or len(message.velocity)!=len(message.name)): return
        try:
            velocities=dict(zip(message.name,message.velocity,strict=True))
            values=tuple(finite(velocities[name]) for name in self.names)
        except (ValueError,KeyError): return
        with self._lock:self._velocity=values;self._received=self.monotonic()

    def send(self,goal):
        wire=trajectory_message(goal)
        if tuple(wire.joint_names)!=self.names: raise ValueError('CONTROLLER_JOINT_ORDER_INVALID')
        message=FollowJointTrajectory.Goal();message.trajectory=wire
        gid=secrets.token_hex(16)
        record=dict(accepted=None,handle=None,result=None,cancel_requested=False,
                    cancel_ack=False,error=None,goal=goal)
        with self._lock:self._goals[gid]=record
        try:
            response=self.client.send_goal_async(message)
            response.add_done_callback(lambda future:self._accepted(gid,future))
        except Exception as error:
            with self._lock:record['accepted']=None;record['error']=repr(error)
            raise
        return gid

    def _accepted(self,gid,future):
        with self._lock:
            record=self._goals[gid]
            try:
                handle=future.result();record['handle']=handle;record['accepted']=bool(handle.accepted)
                if handle.accepted:
                    handle.get_result_async().add_done_callback(lambda f:self._result(gid,f))
                    if record['cancel_requested']:self._cancel_handle(gid)
            except Exception as error:record['accepted']=None;record['error']=repr(error)

    def _result(self,gid,future):
        with self._lock:
            try:self._goals[gid]['result']=future.result()
            except Exception as error:self._goals[gid]['error']=repr(error)

    def accepted(self,gid):
        with self._lock:return self._goals[gid]['accepted']

    def _cancel_handle(self,gid):
        record=self._goals[gid]
        try:
            record['handle'].cancel_goal_async().add_done_callback(lambda f:self._cancel_ack(gid,f))
        except Exception as error:record['error']=repr(error)

    def _cancel_ack(self,gid,future):
        with self._lock:
            try:
                response=future.result()
                # This ACK alone never establishes stop; result and velocity
                # evidence below remain mandatory even for already terminal goals.
                self._goals[gid]['cancel_ack']=response.return_code==0
            except Exception as error:self._goals[gid]['error']=repr(error)

    def cancel(self,gid):
        with self._lock:
            record=self._goals[gid]
            if record['cancel_requested']:return
            record['cancel_requested']=True
            if record['accepted'] is True:self._cancel_handle(gid)

    def stopped(self):
        with self._lock:
            if (self._received is None or not 0<=self.monotonic()-self._received<=self.max_age
                    or any(abs(value)>self.stop_velocity for value in self._velocity)):return False
            for record in self._goals.values():
                if record['accepted'] is None:return False
                if record['accepted'] is False:continue
                result=record['result']
                if result is None or result.status not in (4,5,6):return False
            return True

    def result(self,gid):
        with self._lock:return self._goals[gid]['result']
