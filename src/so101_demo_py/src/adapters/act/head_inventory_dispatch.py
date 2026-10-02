"""Calibration-only primary inventory ACK before native reserve and SDK send.

The owned composition supplies authenticated monitor transport, current guards
and independent fault closure. This adapter creates no node, model or authority.
"""
import base64
import hashlib
import json
import re
import threading
import uuid

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import serialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from unique_identifier_msgs.msg import UUID

from so101_demo.act.head_monitor import canonical_bytes
from .ros_execution import trajectory_message


class HeadInventoryDispatcher:
    def __init__(self,port,authority,monitor,*,epoch,generation,session_id,
                 controller_identity,guard,own_inventory,fault_callback,emit=lambda *args,**kw:None):
        if (any(type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value)
                for value in (epoch,session_id)) or type(generation) is not int or not 0<generation<2**64
                or type(controller_identity) is not dict or set(controller_identity)!={'generation','incarnation','boot'}
                or type(controller_identity['generation']) is not int or controller_identity['generation']!=generation
                or any(type(controller_identity[key]) is not str
                    or not re.fullmatch(r'[\x20-\x7e]{1,64}',controller_identity[key]) for key in ('incarnation','boot'))
                or any(not callable(value) for value in (guard,own_inventory,fault_callback,emit))
                or port.feedback_policy is None or port.names!=('neck_yaw_joint',)):
            raise ValueError('HEAD_INVENTORY_DISPATCH_CONFIG_INVALID')
        self.port=port;self.authority=authority;self.monitor=monitor
        self._scope=(epoch,generation,session_id,canonical_bytes(controller_identity))
        peer=monitor.identity
        if (type(peer) is not dict or set(peer)!={'uid','pid','start_ticks'}
                or any(type(value) is not int or value<0 for value in peer.values())
                or peer['pid']<=0 or peer['start_ticks']<=0):
            raise ValueError('HEAD_INVENTORY_MONITOR_PEER_INVALID')
        self._monitor_peer=canonical_bytes(peer)
        self._guard=guard;self._own=own_inventory;self._fault_callback=fault_callback;self._emit=emit
        self._failed=False;self._fault_handler_error=None;self._sequence=0
        self._inventory={};self._inventory_lock=threading.Lock();self._send_lock=threading.Lock()
        self._check_scope()

    @property
    def epoch(self):return self._scope[0]
    @property
    def generation(self):return self._scope[1]
    @property
    def session_id(self):return self._scope[2]
    @property
    def controller_identity(self):return json.loads(self._scope[3])
    @property
    def revoked(self):return self._failed
    @property
    def inventory(self):
        # The fault worker never waits for a stalled reservation/SDK worker.
        with self._inventory_lock:records=tuple(self._inventory.items())
        return {gid:json.loads(body) for gid,body in records}

    def _check_scope(self):
        if (self._failed or canonical_bytes(self.monitor.identity)!=self._monitor_peer
                or self.port._head_policy_binding_failed
                or self.authority.generation!=self.generation
                or self.authority.session_id!=self.session_id
                or 'neck' not in self.authority._armed
                or self.authority._identities.get('neck')!=self.controller_identity):
            raise PermissionError('HEAD_INVENTORY_DISPATCH_SCOPE_INVALID')

    def _current(self):
        self._check_scope()
        if self._guard() is not True:raise PermissionError('HEAD_INVENTORY_CURRENT_GUARD_REFUSED')
        self._check_scope()

    def _ack(self,reply,operation,**fields):
        expected=dict(request=operation,stage='ARMED_READY',epoch=self.epoch,generation=self.generation,
            session_id=self.session_id,purpose='calibration',motion_authority=False,
            monitor_peer=json.loads(self._monitor_peer),**fields)
        if type(reply) is not dict or any(key not in reply or canonical_bytes(reply[key])!=canonical_bytes(value)
                                         for key,value in expected.items()):
            raise PermissionError('HEAD_INVENTORY_ACK_INVALID')

    def _dispatch(self,gid,inventory_sha):
        self._current()
        reply=self.monitor.request_runtime(dict(operation='DISPATCH',
            binding=dict(goal_uuid=gid,inventory_sha256=inventory_sha)))
        self._ack(reply,'DISPATCH',goal_uuid=gid,inventory_sha256=inventory_sha)
        self._current()
        return True

    def _fault(self):
        self._failed=True;self.port._head_policy_binding_failed=True
        try:self._fault_callback('HEAD_INVENTORY_DISPATCH_FAILED')
        except Exception as error:self._fault_handler_error=type(error).__name__
        try:self._emit('DISPATCH_FAULT',epoch=self.epoch,generation=self.generation)
        except Exception:pass

    def send(self,goal):
        if self._failed:raise PermissionError('HEAD_INVENTORY_DISPATCH_REVOKED')
        if not self._send_lock.acquire(blocking=False):
            self._fault();raise PermissionError('HEAD_INVENTORY_DISPATCH_BUSY')
        try:
            self._current()
            message=FollowJointTrajectory.Goal(trajectory=trajectory_message(goal))
            parsed=uuid.uuid4();goal_uuid=UUID(uuid=list(parsed.bytes));gid=str(parsed)
            payload=serialize_message(message);typed=message_to_ordereddict(message)
            self._sequence+=1;inventory_sha=None
            def register(binding):
                nonlocal inventory_sha
                self._check_scope()
                if (binding.role!='neck' or binding.generation!=self.generation
                        or binding.session_id!=self.session_id or binding.goal_cdr!=payload
                        or binding.goal_uuid!=parsed.bytes
                        or binding.controller_incarnation!=self.controller_identity['incarnation']
                        or binding.controller_boot_incarnation!=self.controller_identity['boot']
                        or binding.deadline_ns-binding.claim_monotonic_ns!=400_000_000):
                    raise PermissionError('HEAD_INVENTORY_NATIVE_BINDING_INVALID')
                record=dict(goal_uuid=gid,typed_goal=typed,payload_sha256=hashlib.sha256(payload).hexdigest(),
                    generation=self.generation,controller_identity=self.controller_identity,
                    attempt_epoch=self.epoch,session_id=self.session_id,role='neck',
                    operation_sequence=self._sequence,claim_monotonic_ns=binding.claim_monotonic_ns,
                    deadline_ns=binding.deadline_ns)
                body=canonical_bytes(record);inventory_sha=hashlib.sha256(body).hexdigest()
                with self._inventory_lock:self._inventory[gid]=body
                if self._own(json.loads(body),payload) is not True:
                    raise PermissionError('HEAD_PRIMARY_INVENTORY_REFUSED')
                reply=self.monitor.request_runtime(dict(operation='REGISTER',inventory=dict(
                    record=json.loads(body),goal_cdr_base64=base64.b64encode(payload).decode('ascii'))))
                self._ack(reply,'REGISTER',goal_uuid=gid,operation_sequence=self._sequence,
                          inventory_sha256=inventory_sha)
                self._emit('INVENTORY_ACK',inventory=json.loads(body),ack=reply,
                    permit_uuid=str(uuid.UUID(bytes=binding.permit_uuid)))
                return self._dispatch(gid,inventory_sha)
            self.authority.reserve('neck',goal=payload,goal_uuid=parsed.bytes,before_reserve=register)
            if self._failed:raise PermissionError('HEAD_INVENTORY_DISPATCH_REVOKED')
            self._emit('NATIVE_RESERVATION_ACK',epoch=self.epoch,goal_uuid=gid,inventory_sha256=inventory_sha)
            sent=self.port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=payload,
                                        dispatch_guard=lambda:self._dispatch(gid,inventory_sha))
            if sent!=gid:raise PermissionError('HEAD_INVENTORY_SDK_UUID_MISMATCH')
            return sent
        except Exception:
            self._fault()
            raise
        finally:self._send_lock.release()

    def cancel(self,gid):return self.port.cancel(gid)
    def stopped(self):return self.port.stopped()
    def _feedback(self,message):return self.port._feedback(message)
