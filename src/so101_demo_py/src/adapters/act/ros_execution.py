"""Broker-owned ROS action port; cancellation requires terminal and velocity proof."""

import math
import secrets
import threading
import time
from collections import deque
from itertools import islice

from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import JointState
from rclpy.qos import qos_profile_sensor_data
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from so101_demo.act.contracts import finite
from so101_demo.act.head_feedback import FeedbackPolicy, OrderedStopConfirmation, decision_clocks
from .head_callback_io import HeadCallbackIO, exception_metadata


def _copy_current_original_candidates(latest,history):
    """Copy at most two raw originals under the caller's existing cache lock."""
    if latest is None:return ()
    candidates=[dict(latest)]
    if latest.get('valid') is True:
        for original in islice(reversed(history),2):
            if original is not latest and original!=latest:
                candidates.append(dict(original));break
    return tuple(candidates)


def _causal_current_original(candidates,sim_ns):
    """Select only a predecision copy; an invalid latest never falls back."""
    if not candidates:return None
    if candidates[0].get('valid') is not True:return candidates[0]
    return next((row for row in candidates if type(row.get('source_ns')) is int
                 and 0<row['source_ns']<=sim_ns),None)


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
                 monotonic=time.monotonic,feedback_policy=None,head_bootstrap=False,
                 head_fault_callback=None):
        self.client=action_client;self.names=tuple(names);self.monotonic=monotonic
        if type(head_bootstrap) is not bool or (head_bootstrap and feedback_policy is not None):
            raise ValueError('HEAD_BOOTSTRAP_CONFIG_INVALID')
        self._head_bootstrap=head_bootstrap
        self._head_policy_binding_failed=False
        if head_fault_callback is not None and not callable(head_fault_callback):
            raise ValueError('HEAD_CALLBACK_FAULT_HANDLER_INVALID')
        self._head_fault_callback=head_fault_callback
        self._head_original_sink=None
        self._head_action_sink=None
        self._head_fault_handler_error=None
        self._head_io=None if feedback_policy is None and not head_bootstrap else {
            'result':HeadCallbackIO('head-result-rpc'),
            'cancel':HeadCallbackIO('head-cancel-rpc')}
        self.node=node
        self._feedback_policy=None if feedback_policy is None else FeedbackPolicy.parse(feedback_policy)
        self._stop_epoch=None;self._head_sequence=0;self._head_samples=deque(maxlen=4096)
        self._head_feedback=None;self._head_stop_proof=None
        self._head_source_watermark=None
        self.stop_predicate_observations=deque(maxlen=4096)
        self.stop_velocity=finite(stop_velocity_rad_s);self.max_age=finite(max_age_s)
        if self.stop_velocity<0 or self.max_age<=0: raise ValueError('STOP_CONFIG_INVALID')
        self._lock=threading.RLock();self._goals={};self._velocity=None;self._received=None
        self._head_inventory_scope=None;self._head_inventory_sequence=0
        self._subscription=node.create_subscription(JointState,'/joint_states',self._feedback,
                                                    qos_profile_sensor_data)

    @property
    def feedback_policy(self):return self._feedback_policy

    def bind_head_original_sink(self,sink):
        if not callable(sink):raise ValueError('HEAD_ORIGINAL_SINK_INVALID')
        with self._lock:
            if (self._head_original_sink is not None or self._head_policy_binding_failed
                    or (not self._head_bootstrap and self.feedback_policy is None)):
                raise PermissionError('HEAD_ORIGINAL_SINK_REBOUND')
            self._head_original_sink=sink

    def bind_head_policy(self,values):
        """Freeze measured policy on the original stopped-bootstrap subscriber."""
        try:parsed=FeedbackPolicy.parse(values)
        except (TypeError,ValueError):
            with self._lock:self._head_policy_binding_failed=True
            raise
        with self._lock:
            if (not self._head_bootstrap or self.feedback_policy is not None
                    or self._head_policy_binding_failed):
                self._head_policy_binding_failed=True
                raise PermissionError('HEAD_FEEDBACK_POLICY_BINDING_REFUSED')
            self._feedback_policy=parsed

    def bind_head_action_sink(self,sink):
        if not callable(sink):raise ValueError('HEAD_ACTION_SINK_INVALID')
        with self._lock:
            if self._head_action_sink is not None or self.feedback_policy is None:
                raise PermissionError('HEAD_ACTION_SINK_REBOUND')
            self._head_action_sink=sink

    def record_head_action(self,kind,gid,original,*,callback_wall_s):
        """Record the actual reply outside the cache lock; failure closes admission."""
        if self._head_action_sink is None:return
        try:
            from rosidl_runtime_py.convert import message_to_ordereddict
            reply=original() if callable(original) else original
            if hasattr(reply,'get_fields_and_field_types'):
                reply=message_to_ordereddict(reply)
            record=dict(schema_version=1,goal_uuid=gid,callback_wall_ns=round(callback_wall_s*1e9),
                callback_sim_ns=self.node.get_clock().now().nanoseconds,original=reply)
            self._head_action_sink(kind,record,None)
        except Exception as error:
            self._head_io_failed(gid,error)
            # Logging failure has already latched admission closure. Completion
            # delivery must continue so independent cancellation/Stop can still
            # reconcile the real UUID, even with a permanently broken writer.
            return False
        return True

    @staticmethod
    def _head_result_reply(response):
        return dict(status=response.status,result=dict(error_code=response.result.error_code,
            error_string=getattr(response.result,'error_string',None)))

    @staticmethod
    def _head_cancel_reply(response):
        from rosidl_runtime_py.convert import message_to_ordereddict
        goals=getattr(response,'goals_canceling',None)
        return dict(return_code=response.return_code,goals_canceling=None if goals is None else
            [message_to_ordereddict(goal) for goal in goals])

    @staticmethod
    def _head_acceptance_reply(handle):
        from rosidl_runtime_py.convert import message_to_ordereddict
        stamp=getattr(handle,'stamp',None);goal_id=getattr(handle,'goal_id',None)
        return dict(accepted=handle.accepted,stamp=None if stamp is None else message_to_ordereddict(stamp),
            goal_id=None if goal_id is None else message_to_ordereddict(goal_id))

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

    def tighten_stop_fault(self, fault_wall_s):
        """Keep the original request and samples; only shorten its fault deadline."""
        from so101_demo.act.head_feedback import nanoseconds
        fault_ns=nanoseconds(fault_wall_s)
        with self._lock:
            if self._head_stop_proof is None:return False
            proof=self._head_stop_proof
            if fault_ns>=nanoseconds(proof.epoch['fault_wall_s']):return False
            proof.epoch['fault_wall_s']=fault_wall_s
            self._stop_epoch['fault_wall_s']=fault_wall_s
            return True

    def feedback_snapshot(self):
        if self.feedback_policy is None:raise PermissionError('HEAD_FEEDBACK_POLICY_REQUIRED')
        if self._head_policy_binding_failed:raise PermissionError('HEAD_FEEDBACK_POLICY_BINDING_REFUSED')
        original=self.original_feedback_snapshot()
        sample,decision=original['sample'],original['decision']
        ages=self.feedback_policy.check_joint(sample,decision)
        with self._lock:
            if self._head_policy_binding_failed:raise PermissionError('HEAD_FEEDBACK_POLICY_BINDING_REFUSED')
        return dict(sample,decision=decision,**ages)

    def original_feedback_snapshot(self):
        """Measurement-only originals; this does not establish fresh feedback."""
        with self._lock:
            candidates=_copy_current_original_candidates(self._head_feedback,self._head_samples)
        decision=decision_clocks(self.node,self.monotonic)
        sample=_causal_current_original(candidates,decision['sim_ns'])
        return dict(sample=sample,decision=decision,
            current_original_selection=dict(joint_candidate_sources_ns=[row['source_ns'] for row in candidates]))

    def _feedback(self,message):
        if self.feedback_policy is not None or self._head_bootstrap:
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
        if self._head_original_sink is not None:
            from copy import deepcopy
            try:self._head_original_sink('JOINT',deepcopy(sample))
            except Exception:
                self._head_policy_binding_failed=True
                if self._head_fault_callback is not None:
                    try:self._head_fault_callback('HEAD_ORIGINAL_SINK_FAILED')
                    except Exception:self._head_fault_handler_error='HEAD_ORIGINAL_FAULT_HANDLER_FAILED'

    def send(self,goal,*,goal_uuid=None):
        if self._head_policy_binding_failed:
            raise PermissionError('HEAD_FEEDBACK_POLICY_BINDING_REFUSED')
        if self._head_bootstrap and self.feedback_policy is None:
            raise PermissionError('HEAD_FEEDBACK_POLICY_REQUIRED')
        wire=trajectory_message(goal)
        if tuple(wire.joint_names)!=self.names: raise ValueError('CONTROLLER_JOINT_ORDER_INVALID')
        message=FollowJointTrajectory.Goal();message.trajectory=wire
        gid=secrets.token_hex(16)
        record=dict(accepted=None,handle=None,result=None,cancel_requested=False,
                    cancel_ack=False,error=None,goal=goal)
        with self._lock:
            if self._head_policy_binding_failed:raise PermissionError('HEAD_FEEDBACK_POLICY_BINDING_REFUSED')
            self._goals[gid]=record
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

    def inventory_prepared(self,record,payload):
        """Own an unknown UUID before native reservation, without sending it.

        This local inventory grants no native or CPU authority. The dispatcher
        separately freezes scope and requires local state admission.
        """
        import json
        import re
        import uuid
        from so101_demo.act.head_evidence_identity import canonical_bytes
        from .head_goal_binding import validate_goal_inventory
        try:
            if (self.feedback_policy is None or self.names!=('neck_yaw_joint',)
                    or self._head_policy_binding_failed or self._head_fault_callback is None):
                raise PermissionError('HEAD_PRIMARY_INVENTORY_POLICY_REQUIRED')
            required={'goal_uuid','typed_goal','payload_sha256','generation','controller_identity',
                'attempt_epoch','session_id','role','operation_sequence','claim_monotonic_ns','deadline_ns'}
            if type(record) is not dict or set(record)!=required:
                raise ValueError('HEAD_PRIMARY_INVENTORY_FIELDS_INVALID')
            owned=validate_goal_inventory(record,payload)
            gid=owned['goal_uuid'];parsed=uuid.UUID(gid)
            identity=owned['controller_identity'];generation=owned['generation']
            claim,deadline=owned['claim_monotonic_ns'],owned['deadline_ns']
            sequence=owned['operation_sequence']
            if (str(parsed)!=gid or parsed.version!=4 or owned['role']!='neck'
                    or type(generation) is not int or not 0<generation<2**64
                    or type(sequence) is not int or sequence<=0
                    or any(type(owned[key]) is not str
                        or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',owned[key])
                        for key in ('attempt_epoch','session_id'))
                    or type(identity) is not dict or set(identity)!={'generation','incarnation','boot'}
                    or type(identity['generation']) is not int or identity['generation']!=generation
                    or any(type(identity[key]) is not str or not re.fullmatch(r'[\x20-\x7e]{1,64}',identity[key])
                        for key in ('incarnation','boot'))
                    or type(claim) is not int or type(deadline) is not int
                    or not 0<claim<deadline<2**63 or deadline-claim!=400_000_000):
                raise ValueError('HEAD_PRIMARY_INVENTORY_SCOPE_INVALID')
            body=canonical_bytes(owned)
            if len(body)>65536:raise ValueError('HEAD_PRIMARY_INVENTORY_TOO_LARGE')
            scope=canonical_bytes({key:owned[key] for key in
                ('generation','controller_identity','attempt_epoch','session_id','role')})
            pending=dict(accepted=None,handle=None,result=None,cancel_requested=False,
                cancel_ack=False,error=None,goal=json.loads(canonical_bytes(owned['typed_goal'])),
                prepared_cdr_sha256=owned['payload_sha256'],primary_inventory=body,
                prepared_typed_goal_bytes=canonical_bytes(owned['typed_goal']),
                primary_claim_window_ns=(claim,deadline),sdk_claimed=False)
            with self._lock:
                if (self._head_policy_binding_failed or gid in self._goals or len(self._goals)>=128
                        or sequence!=self._head_inventory_sequence+1
                        or (self._head_inventory_scope is not None and self._head_inventory_scope!=scope)
                        or not claim<=time.monotonic_ns()<deadline):
                    raise PermissionError('HEAD_PRIMARY_INVENTORY_REFUSED')
                self._goals[gid]=pending
                self._head_inventory_scope=scope;self._head_inventory_sequence=sequence
            return True
        except Exception:
            self._head_policy_binding_failed=True
            if self._head_fault_callback is not None:
                try:self._head_fault_callback('HEAD_PRIMARY_INVENTORY_FAILED')
                except Exception as error:self._head_fault_handler_error=type(error).__name__
            raise

    def send_prepared(self,message,*,goal_uuid,expected_cdr,dispatch_guard):
        """Send the complete inventory/native-bound Head message without rebuilding it.

        The composition owns inventory/native admission. Its authenticated last
        guard is mandatory here; this method grants neither authority itself.
        """
        import hashlib
        import uuid
        from rclpy.serialization import serialize_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        from unique_identifier_msgs.msg import UUID
        gid=None
        try:
            if (self.feedback_policy is None or self.names!=('neck_yaw_joint',)
                    or self._head_policy_binding_failed):
                raise PermissionError('HEAD_PREPARED_POLICY_REQUIRED')
            if (not isinstance(message,FollowJointTrajectory.Goal)
                    or tuple(message.trajectory.joint_names)!=self.names
                    or type(expected_cdr) is not bytes or not 0<len(expected_cdr)<=1_048_576
                    or not callable(dispatch_guard)):
                raise ValueError('HEAD_PREPARED_GOAL_INVALID')
            parsed=uuid.UUID(bytes=bytes(goal_uuid.uuid))
            if parsed.version!=4:raise ValueError('HEAD_PREPARED_UUID_INVALID')
            gid=str(parsed)
            owned_uuid=UUID(uuid=list(parsed.bytes))
            with self._lock:inventoried=gid in self._goals
            # Native admission verifies the original CDR digest and every
            # decoded field. Re-encoding an identical Goal can change ROS CDR
            # padding/trailing bytes; the immutable inventory below binds its
            # original byte digest and complete typed identity instead.
            if not inventoried and serialize_message(message)!=expected_cdr:
                raise ValueError('HEAD_PREPARED_CDR_MISMATCH')
            record=dict(accepted=None,handle=None,result=None,cancel_requested=False,
                cancel_ack=False,error=None,goal=message_to_ordereddict(message),
                prepared_cdr_sha256=hashlib.sha256(expected_cdr).hexdigest())
            from so101_demo.act.head_evidence_identity import canonical_bytes
            typed=canonical_bytes(record['goal'])
            with self._lock:
                if self._head_policy_binding_failed:raise PermissionError('HEAD_PREPARED_REVOKED')
                if gid in self._goals:
                    existing=self._goals[gid]
                    if (type(existing.get('primary_inventory')) is not bytes
                            or existing.get('sdk_claimed') is not False
                            or existing.get('prepared_cdr_sha256')!=record['prepared_cdr_sha256']
                            or existing.get('prepared_typed_goal_bytes')!=typed):
                        raise PermissionError('HEAD_PREPARED_UUID_REUSED')
                    record=existing
                else:self._goals[gid]=record
                record['sdk_claimed']=True
            # No cache lock covers IPC, serialisation or the SDK call. Check the
            # original feedback after the guard, so guard latency adds no age.
            if dispatch_guard() is not True:raise PermissionError('HEAD_PREPARED_GUARD_REFUSED')
            if (canonical_bytes(message_to_ordereddict(message))!=typed if inventoried
                    else serialize_message(message)!=expected_cdr):
                raise ValueError('HEAD_PREPARED_CDR_MISMATCH')
            self.feedback_snapshot()
            if self._head_policy_binding_failed:raise PermissionError('HEAD_PREPARED_REVOKED')
            claim=record.get('primary_claim_window_ns')
            if claim is not None and not claim[0]<=time.monotonic_ns()<claim[1]:
                raise PermissionError('HEAD_PREPARED_CLAIM_EXPIRED')
            if self._head_action_sink is not None:
                record['sdk_dispatch_wall_s']=self.monotonic()
            response=self.client.send_goal_async(message,goal_uuid=owned_uuid)
            if self._head_action_sink is not None:
                record['sdk_returned_wall_s']=self.monotonic()
                self.record_head_action('HEAD_ACTION_SDK_RETURNED',gid,
                    lambda:dict(future_done=response.done(),accepted=record['accepted'],
                        sdk_dispatch_wall_s=record['sdk_dispatch_wall_s'],
                        sdk_returned_wall_s=record['sdk_returned_wall_s'],
                        prepared_cdr_sha256=record['prepared_cdr_sha256']),
                    callback_wall_s=record['sdk_returned_wall_s'])
            response.add_done_callback(lambda future:self._accepted(gid,future))
            return gid
        except Exception as error:
            # Unknown SDK acceptance remains unknown. Admission closes before
            # reporting, even if the reporter or SDK is unavailable.
            self._head_policy_binding_failed=True
            if self._head_fault_callback is not None:
                try:self._head_fault_callback('HEAD_PREPARED_DISPATCH_FAILED')
                except Exception as report_error:
                    with self._lock:self._head_fault_handler_error=type(report_error).__name__
            if gid is not None:
                with self._lock:
                    if gid in self._goals:self._goals[gid]['error']=type(error).__name__
            raise

    def _accepted(self,gid,future):
        if self._head_io is not None:
            callback_wall=self.monotonic()
            try:handle=future.result();accepted=bool(handle.accepted)
            except Exception as error:
                self._head_io_failed(gid,error)
                return
            with self._lock:
                record=self._goals[gid]
                record['handle']=handle;record['accepted']=accepted
                cancel=record['cancel_requested']
            if self._head_action_sink is not None:
                self.record_head_action('HEAD_ACTION_SDK_ACCEPTANCE',gid,
                    lambda:self._head_acceptance_reply(handle),callback_wall_s=callback_wall)
            if accepted:
                if cancel:self._cancel_handle(gid)
                self._head_dispatch_io(gid,'result',lambda:
                    handle.get_result_async().add_done_callback(lambda f:self._result(gid,f)))
            return
        with self._lock:
            record=self._goals[gid]
            try:
                handle=future.result();record['handle']=handle;record['accepted']=bool(handle.accepted)
                if handle.accepted:
                    handle.get_result_async().add_done_callback(lambda f:self._result(gid,f))
                    if record['cancel_requested']:self._cancel_handle(gid)
            except Exception as error:record['accepted']=None;record['error']=repr(error)

    def _result(self,gid,future):
        if self._head_io is not None:
            callback_wall=self.monotonic()
            try:result=future.result()
            except Exception as error:
                self._head_io_failed(gid,error)
                return
            with self._lock:self._goals[gid]['result']=result
            if self._head_action_sink is not None:
                self.record_head_action('HEAD_ACTION_SDK_RESULT',gid,
                    lambda:self._head_result_reply(result),callback_wall_s=callback_wall)
            return
        with self._lock:
            try:self._goals[gid]['result']=future.result()
            except Exception as error:self._goals[gid]['error']=repr(error)

    def accepted(self,gid):
        with self._lock:return self._goals[gid]['accepted']

    def _cancel_handle(self,gid):
        if self._head_io is not None:
            with self._lock:
                record=self._goals[gid]
                if record.get('cancel_enqueued'):return
                record['cancel_enqueued']=True;handle=record['handle']
            self._head_dispatch_io(gid,'cancel',lambda:
                handle.cancel_goal_async().add_done_callback(lambda f:self._cancel_ack(gid,f)))
            return
        record=self._goals[gid]
        try:
            record['handle'].cancel_goal_async().add_done_callback(lambda f:self._cancel_ack(gid,f))
        except Exception as error:record['error']=repr(error)

    def _cancel_ack(self,gid,future):
        if self._head_io is not None:
            callback_wall=self.monotonic()
            try:response=future.result();ack=response.return_code==0
            except Exception as error:
                self._head_io_failed(gid,error)
                return
            with self._lock:self._goals[gid]['cancel_ack']=ack
            if self._head_action_sink is not None:
                self.record_head_action('HEAD_ACTION_SDK_CANCEL',gid,
                    lambda:self._head_cancel_reply(response),callback_wall_s=callback_wall)
            return
        with self._lock:
            try:
                response=future.result()
                # This ACK alone never establishes stop; result and velocity
                # evidence below remain mandatory even for already terminal goals.
                self._goals[gid]['cancel_ack']=response.return_code==0
            except Exception as error:self._goals[gid]['error']=repr(error)

    def cancel(self,gid):
        if self._head_io is not None:
            with self._lock:
                record=self._goals[gid]
                if record['cancel_requested']:return
                record['cancel_requested']=True;accepted=record['accepted']
            if accepted is True:self._cancel_handle(gid)
            return
        with self._lock:
            record=self._goals[gid]
            if record['cancel_requested']:return
            record['cancel_requested']=True
            if record['accepted'] is True:self._cancel_handle(gid)

    def _head_dispatch_io(self,gid,kind,operation):
        def run():
            started=self.monotonic()
            with self._lock:self._goals[gid][kind+'_rpc_started_wall_s']=started
            operation()
            finished=self.monotonic()
            with self._lock:self._goals[gid][kind+'_rpc_returned_wall_s']=finished
        try:self._head_io[kind].submit(run,lambda error:self._head_io_failed(gid,error))
        except Exception as error:self._head_io_failed(gid,error)

    def _head_io_failed(self,gid,error):
        self._head_policy_binding_failed=True
        report_failure=None
        if self._head_fault_callback is not None:
            try:self._head_fault_callback('HEAD_CALLBACK_IO_FAILED')
            except Exception as report_error:report_failure=report_error
        diagnostic=exception_metadata(error)
        reporting=None if report_failure is None else exception_metadata(report_failure)
        with self._lock:
            self._goals[gid]['error']=diagnostic
            if reporting is not None:self._head_fault_handler_error=reporting

    def close_head_io(self,*,timeout_s):
        if self._head_io is None:return {}
        with self._lock:self._head_policy_binding_failed=True
        deadline=time.monotonic()+timeout_s
        return {kind:worker.close(timeout_s=max(0.,deadline-time.monotonic()))
                for kind,worker in self._head_io.items()}

    def stopped(self):
        if self._head_bootstrap and self.feedback_policy is None:return False
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
            proof=self._head_stop_proof
            samples=[]
            if proof is not None:
                # Callback sequences are strictly increasing. Keep the full
                # archive, but copy only originals this stop has not consumed.
                # All copies still precede the original decision clocks.
                for sample in reversed(self._head_samples):
                    if sample['sequence']<=proof.last_sequence:break
                    samples.append(dict(sample))
                samples.reverse()
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
            stopped=(physical and proof.confirmed_at is not None and not proof.inventory_changed
                     and proof.within_deadline(proof.confirmed_at))
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

    def raw_stop_confirmation(self):
        """The sim stamp of the decision that confirmed the raw stop, or None until it is confirmed."""
        with self._lock:
            proof=self._head_stop_proof
            if proof is None or proof.confirmed_at is None:return None
            samples=proof.confirming_samples
            return dict(sim_ns=proof.confirmed_at['sim_ns'],wall_s=proof.confirmed_at['wall_after_s'],
                        last_sample_source_ns=samples[-1].get('source_ns') if samples else None)

    def result(self,gid):
        with self._lock:return self._goals[gid]['result']
