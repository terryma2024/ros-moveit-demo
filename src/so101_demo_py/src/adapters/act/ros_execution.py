"""Broker-owned ROS action port; cancellation requires terminal and velocity proof."""

import math
import secrets
import threading
import time
from collections import deque

from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import JointState
from rclpy.qos import qos_profile_sensor_data
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from so101_demo.act.contracts import finite
from so101_demo.act.head_feedback import FeedbackPolicy, OrderedStopConfirmation, decision_clocks


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
                 monotonic=time.monotonic,feedback_policy=None):
        self.client=action_client;self.names=tuple(names);self.monotonic=monotonic
        self.node=node
        self.feedback_policy=None if feedback_policy is None else FeedbackPolicy.parse(feedback_policy)
        self._stop_epoch=None;self._head_sequence=0;self._head_samples=deque(maxlen=4096)
        self._head_feedback=None;self._head_stop_proof=None
        self._head_source_watermark=None
        self.stop_predicate_observations=deque(maxlen=4096)
        self.stop_velocity=finite(stop_velocity_rad_s);self.max_age=finite(max_age_s)
        if self.stop_velocity<0 or self.max_age<=0: raise ValueError('STOP_CONFIG_INVALID')
        self._lock=threading.RLock();self._goals={};self._velocity=None;self._received=None
        self._subscription=node.create_subscription(JointState,'/joint_states',self._feedback,
                                                    qos_profile_sensor_data)

    def begin_stop(self,epoch):
        if self.feedback_policy is None:raise ValueError('HEAD_FEEDBACK_POLICY_REQUIRED')
        proof=OrderedStopConfirmation(epoch)
        with self._lock:
            if self._stop_epoch is not None and epoch['epoch']==self._stop_epoch['epoch']:
                if epoch!=self._stop_epoch:raise ValueError('HEAD_STOP_EPOCH_REUSED')
                return
            if (self._stop_epoch is not None
                    and epoch['request_wall_s']<self._stop_epoch['request_wall_s']):
                raise ValueError('HEAD_STOP_EPOCH_REGRESSED')
            proof.last_sequence=self._head_sequence
            self._stop_epoch=dict(epoch);self._head_stop_proof=proof

    def feedback_snapshot(self):
        with self._lock:sample=None if self._head_feedback is None else dict(self._head_feedback)
        decision=decision_clocks(self.node,self.monotonic)
        ages=self.feedback_policy.check_joint(sample,decision)
        return dict(sample,decision=decision,**ages)

    def _feedback(self,message):
        if self.feedback_policy is not None:
            self._head_feedback_message(message)
            return
        if (len(set(message.name))!=len(message.name)
                or len(message.velocity)!=len(message.name)): return
        try:
            velocities=dict(zip(message.name,message.velocity,strict=True))
            values=tuple(finite(velocities[name]) for name in self.names)
        except (ValueError,KeyError): return
        with self._lock:self._velocity=values;self._received=self.monotonic()

    def _head_feedback_message(self,message):
        received=self.monotonic()
        # Keep callback node time as metadata even when it precedes the source
        # stamp. Only a later snapshot-then-clock decision establishes age.
        callback_sim_ns=self.node.get_clock().now().nanoseconds
        source_ns=message.header.stamp.sec*1000000000+message.header.stamp.nanosec
        sample=dict(wall_s=received,callback_sim_ns=callback_sim_ns,
            valid=False,source_ns=source_ns,positions=(),velocities=(),
            raw_names=tuple(message.name),raw_positions=tuple(message.position),
            raw_velocities=tuple(message.velocity))
        try:
            if (len(set(message.name))!=len(message.name)
                    or len(message.position)!=len(message.name)
                    or len(message.velocity)!=len(message.name)):
                raise ValueError('HEAD_FEEDBACK_SHAPE_INVALID')
            indices=tuple(message.name.index(name) for name in self.names)
            positions=tuple(finite(message.position[index]) for index in indices)
            velocities=tuple(finite(message.velocity[index]) for index in indices)
            if source_ns<=0:raise ValueError('HEAD_FEEDBACK_SOURCE_INVALID')
            sample.update(source_ns=source_ns,positions=positions,velocities=velocities,valid=True)
        except (ValueError,KeyError,TypeError) as error:
            sample['error']=str(error)
        with self._lock:
            if sample['valid']:
                if (self._head_source_watermark is not None
                        and source_ns<=self._head_source_watermark):
                    sample['valid']=False;sample['error']='HEAD_FEEDBACK_SOURCE_NONADVANCING'
                else:self._head_source_watermark=source_ns
            self._head_sequence+=1;sample['sequence']=self._head_sequence
            self._head_samples.append(sample);self._head_feedback=sample

    def send(self,goal,*,goal_uuid=None):
        wire=trajectory_message(goal)
        if tuple(wire.joint_names)!=self.names: raise ValueError('CONTROLLER_JOINT_ORDER_INVALID')
        message=FollowJointTrajectory.Goal();message.trajectory=wire
        gid=secrets.token_hex(16)
        record=dict(accepted=None,handle=None,result=None,cancel_requested=False,
                    cancel_ack=False,error=None,goal=goal)
        with self._lock:self._goals[gid]=record
        try:
            options={}
            if goal_uuid is not None:
                options['goal_uuid']=goal_uuid
            response=self.client.send_goal_async(message,**options)
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
        if self.feedback_policy is not None:return self._head_stopped()
        with self._lock:
            if (self._received is None or not 0<=self.monotonic()-self._received<=self.max_age
                    or any(abs(value)>self.stop_velocity for value in self._velocity)):return False
            for record in self._goals.values():
                if record['accepted'] is None:return False
                if record['accepted'] is False:continue
                result=record['result']
                if result is None or result.status not in (4,5,6):return False
            return True

    def _head_stopped(self):
        with self._lock:
            latest=None if self._head_feedback is None else dict(self._head_feedback)
            samples=tuple(dict(sample) for sample in self._head_samples)
            proof=self._head_stop_proof
            states={gid:dict(accepted=record['accepted'],
                terminal_status=getattr(record.get('result'),'status',None))
                for gid,record in self._goals.items()}
        decision=None;error=None
        try:
            decision=decision_clocks(self.node,self.monotonic)
            self.feedback_policy.check_joint(latest,decision)
        except (TypeError,ValueError) as failure:
            error=str(failure)
        with self._lock:
            if proof is not self._head_stop_proof:return False
            current_states={gid:dict(accepted=record['accepted'],
                terminal_status=getattr(record.get('result'),'status',None))
                for gid,record in self._goals.items()}
            current_sequence=None if self._head_feedback is None else self._head_feedback['sequence']
            if (current_sequence!=(None if latest is None else latest['sequence'])
                    or current_states!=states):
                error='HEAD_STOP_SNAPSHOT_CHANGED'
            if proof is not None and decision is not None:
                if error!='HEAD_STOP_SNAPSHOT_CHANGED':
                    for sample in samples:
                        proof.observe(sample,decision,self.feedback_policy,self.stop_velocity)
            terminal=all(state['accepted'] is False or
                (state['accepted'] is True and state['terminal_status'] in (4,5,6))
                for state in states.values())
            physical=(error is None and proof is not None and proof.count>=3 and terminal)
            if (proof is not None and proof.confirmation_inventory is not None
                    and set(states)!=set(proof.confirmation_inventory)):
                proof.inventory_changed=True
            if physical and proof.confirmed_at is None and proof.within_deadline(decision):
                proof.confirmed_at=dict(decision)
                proof.confirmation_inventory=dict(states)
            # A timely proof is historical. Continue requiring fresh quiet
            # feedback and terminal inventory for the current hold predicate.
            # A missed deadline can never be repaired by late quiet samples.
            stopped=physical and proof.confirmed_at is not None and not proof.inventory_changed
            self.stop_predicate_observations.append(dict(
                epoch=None if proof is None else dict(proof.epoch),
                decision=None if decision is None else dict(decision),
                sample_sequence=None if latest is None else latest['sequence'],
                latest_sample=latest,error=error,
                quiet_count=0 if proof is None else proof.count,
                goal_states=states,stopped=stopped,
                confirmed_at=None if proof is None else proof.confirmed_at,
                confirmation_inventory=None if proof is None else proof.confirmation_inventory,
                inventory_changed=False if proof is None else proof.inventory_changed,
                confirming_samples=() if proof is None else tuple(proof.confirming_samples)))
            return stopped

    def result(self,gid):
        with self._lock:return self._goals[gid]['result']
