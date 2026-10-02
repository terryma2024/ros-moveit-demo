"""Immutable attempt/readiness and pre-dispatch inventory for Head's monitor.

The exec transport authenticates the peer before calling this boundary. This
object grants no native arm, action send, or new-generation authority.
"""

import hashlib
import json
import re
import math
import threading
import time
import uuid

from .head_feedback import FeedbackPolicy


def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class HeadMonitorEpoch:
    def __init__(self, *, epoch, generation, session_id, clock_ns=time.monotonic_ns):
        identifiers=(epoch,session_id)
        if (any(type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value)
                for value in identifiers)
                or type(generation) is not int or not 0<generation<2**64
                or not callable(clock_ns)):
            raise ValueError('HEAD_MONITOR_SCOPE_INVALID')
        self._scope=(epoch,generation,session_id)
        self._stage='PRESENT';self._policy_hash=None;self._policy=None;self._identity=None
        self._sequence=0;self._inventory={};self._fault=None
        self._lock=threading.Lock();self.clock_ns=clock_ns

    @property
    def epoch(self):return self._scope[0]

    @property
    def generation(self):return self._scope[1]

    @property
    def session_id(self):return self._scope[2]

    @property
    def stage(self):return self._stage

    @property
    def identity(self):return None if self._identity is None else dict(self._identity)

    @property
    def policy(self):return self._policy

    @property
    def policy_hash(self):return self._policy_hash

    @property
    def sequence(self):return self._sequence

    @property
    def fault(self):return None if self._fault is None else dict(self._fault)

    @property
    def inventory(self):
        with self._lock:records=tuple(self._inventory.items())
        return {goal_uuid:json.loads(body) for goal_uuid,(body,_) in records}

    def _refuse(self,reason):
        # Called with the short state lock. No I/O, callbacks or logger.
        if self._fault is None:
            self._fault=dict(reason=reason,fault_wall_s=self.clock_ns()*1e-9)
        self._stage='REVOKED'
        raise PermissionError(reason)

    def _require(self,stage):
        if self.stage!=stage:self._refuse('HEAD_MONITOR_STAGE_INVALID')

    def bind_policy(self, values, policy_hash):
        with self._lock:self._require('PRESENT')
        try:parsed=FeedbackPolicy.parse(values)
        except (TypeError,ValueError):
            self.revoke('HEAD_MONITOR_POLICY_INVALID',fault_wall_s=self.clock_ns()*1e-9)
            raise
        if type(policy_hash) is not str or not re.fullmatch(r'[0-9a-f]{64}',policy_hash):
            self.revoke('HEAD_MONITOR_POLICY_INVALID',fault_wall_s=self.clock_ns()*1e-9)
            raise ValueError('HEAD_MONITOR_POLICY_INVALID')
        with self._lock:
            self._require('PRESENT')
            self._policy=parsed;self._policy_hash=policy_hash;self._stage='POLICY_READY'
            return dict(epoch=self.epoch,policy_sha256=self.policy_hash,state=self.stage)

    def armed_ready(self, primary_identity, monitor_identity):
        with self._lock:
            self._require('POLICY_READY')
            if (not isinstance(primary_identity,dict) or not isinstance(monitor_identity,dict)
                    or set(monitor_identity)!={'generation','incarnation','boot'}
                    or primary_identity!=monitor_identity
                    or type(monitor_identity['generation']) is not int
                    or monitor_identity['generation']!=self.generation
                    or any(type(monitor_identity[key]) is not str
                           or not re.fullmatch(r'[\x20-\x7e]{1,64}',monitor_identity[key])
                           for key in ('incarnation','boot'))):
                self._refuse('HEAD_MONITOR_NATIVE_IDENTITY_MISMATCH')
            self._identity=dict(monitor_identity);self._stage='ARMED_READY'
            return dict(epoch=self.epoch,state=self.stage,identity=dict(self.identity))

    def register(self, record):
        required={'goal_uuid','typed_goal','payload_sha256','generation','controller_identity',
                  'attempt_epoch','session_id','role','operation_sequence','claim_monotonic_ns','deadline_ns'}
        try:
            if not isinstance(record,dict) or set(record)!=required:
                raise ValueError('HEAD_MONITOR_INVENTORY_FIELDS_INVALID')
            body=canonical_bytes(record)
            if len(body)>65536:raise ValueError('HEAD_MONITOR_INVENTORY_TOO_LARGE')
            original=json.loads(body)
            goal_uuid=original['goal_uuid']
            parsed=uuid.UUID(goal_uuid)
            if str(parsed)!=goal_uuid or parsed.version!=4:
                raise ValueError('HEAD_MONITOR_UUID_INVALID')
            if (not isinstance(original['typed_goal'],dict)
                    or original['typed_goal'].get('trajectory',{}).get('joint_names')!=['neck_yaw_joint']
                    or type(original['payload_sha256']) is not str
                    or not re.fullmatch(r'[0-9a-f]{64}',original['payload_sha256'])):
                raise ValueError('HEAD_MONITOR_GOAL_INVALID')
            claim,deadline=original['claim_monotonic_ns'],original['deadline_ns']
            if (type(claim) is not int or type(deadline) is not int
                    or not 0<claim<deadline<2**63 or deadline-claim!=400_000_000):
                raise ValueError('HEAD_MONITOR_CLAIM_INVALID')
            inventory_sha=hashlib.sha256(body).hexdigest()
        except (TypeError,ValueError,AttributeError) as error:
            self.revoke('HEAD_MONITOR_INVENTORY_INVALID',fault_wall_s=self.clock_ns()*1e-9)
            raise ValueError('HEAD_MONITOR_INVENTORY_INVALID') from error
        with self._lock:
            self._require('ARMED_READY')
            if (original['attempt_epoch']!=self.epoch or original['session_id']!=self.session_id
                    or original['role']!='neck' or type(original['generation']) is not int
                    or original['generation']!=self.generation
                    or original['controller_identity']!=self.identity
                    or type(original['operation_sequence']) is not int
                    or original['operation_sequence']!=self.sequence+1
                    or goal_uuid in self._inventory or len(self._inventory)>=128
                    or not claim<=self.clock_ns()<=deadline):
                self._refuse('HEAD_MONITOR_INVENTORY_SCOPE_INVALID')
            self._inventory[goal_uuid]=(body,inventory_sha)
            self._sequence=original['operation_sequence']
            return dict(epoch=self.epoch,operation_sequence=self.sequence,
                        goal_uuid=goal_uuid,inventory_sha256=inventory_sha)

    def revoke(self, reason, *, fault_wall_s):
        if (type(reason) is not str or not reason or type(fault_wall_s) not in (int,float)
                or not math.isfinite(fault_wall_s) or fault_wall_s<0):
            raise ValueError('HEAD_MONITOR_FAULT_INVALID')
        with self._lock:
            self._stage='REVOKED'
            if self._fault is None or fault_wall_s<self._fault['fault_wall_s']:
                self._fault=dict(reason=reason,fault_wall_s=fault_wall_s)
            return dict(epoch=self.epoch,state=self.stage,fault=dict(self.fault))

    def require_dispatch(self, goal_uuid, inventory_sha256):
        with self._lock:
            self._require('ARMED_READY')
            registered=self._inventory.get(goal_uuid)
            if registered is None or registered[1]!=inventory_sha256:
                self._refuse('HEAD_MONITOR_INVENTORY_ACK_REQUIRED')
            body=registered[0]
        # Decode the bounded immutable record outside the revocation lock.
        record=json.loads(body)
        with self._lock:
            self._require('ARMED_READY')
            now=self.clock_ns()
            if not record['claim_monotonic_ns']<=now<=record['deadline_ns']:
                self._refuse('HEAD_MONITOR_CLAIM_EXPIRED')
            return True
