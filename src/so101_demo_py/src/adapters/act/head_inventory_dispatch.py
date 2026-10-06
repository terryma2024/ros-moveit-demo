"""Synchronous local inventory gate before native reserve and prepared SDK send."""

import copy
import hashlib
import json
import threading
import time
import uuid

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from unique_identifier_msgs.msg import UUID

from so101_demo.act.head_evidence_identity import canonical_bytes
from .head_trajectory_guard import HeadTrajectoryGuard, PreparedHeadTrajectory


class HeadInventoryDispatcher:
    """Keep exact prepared CDR and typed inventory under one local owner.

    ``own_inventory`` synchronously transfers the original typed record/CDR to
    the primary ROS action port. The local state registers first; the callback
    must then establish the matching port inventory before it returns True.
    """

    def __init__(self, port, authority, local_state, *, guard, own_inventory,
                 fault_callback, emit=lambda *args, **kwargs: None):
        from so101_demo.act.head_local_state import HeadLocalState

        if (not isinstance(local_state, HeadLocalState)
                or type(guard) is not HeadTrajectoryGuard
                or any(not callable(value) for value in (own_inventory, fault_callback, emit))
                or port.feedback_policy is None or port.names != ('neck_yaw_joint',)):
            raise ValueError('HEAD_INVENTORY_DISPATCH_CONFIG_INVALID')
        self.port = port
        self.authority = authority
        self.local_state = local_state
        self._trajectory_guard = guard
        self._guard = guard.is_current
        self._own = own_inventory
        self._fault_callback = fault_callback
        self._emit = emit
        self._failed = False
        self._stop_requested = threading.Event()
        self._fault_handler_error = None
        self._sequence = 0
        self._send_lock = threading.Lock()
        self._dispatch_traces = []
        if not local_state.controller_bound:
            raise PermissionError('HEAD_LOCAL_CONTROLLER_UNBOUND')
        self._scope = canonical_bytes(local_state.scope)
        self._check_scope()
        guard.bind_dispatcher(self, local_state)

    @property
    def epoch(self): return self.local_state.scope['epoch']

    @property
    def generation(self): return self.local_state.scope['generation']

    @property
    def session_id(self): return self.local_state.scope['session_id']

    @property
    def controller_identity(self): return copy.deepcopy(self.local_state.scope['controller_identity'])

    @property
    def revoked(self):
        return self._failed or self._stop_requested.is_set() or self.local_state.faulted

    @property
    def dispatch_traces(self): return copy.deepcopy(tuple(self._dispatch_traces))

    @property
    def inventory(self): return self.local_state.inventory

    def _authority_scope(self):
        return dict(epoch=self.epoch, generation=self.authority.generation,
            session_id=self.authority.session_id, policy_sha256=self.local_state.scope['policy_sha256'],
            controller_identity=self.authority._identities.get('neck'))

    def _check_scope(self):
        scope = self.local_state.scope
        if (self._failed or self.local_state.faulted
                or scope['controller_identity'] is None or canonical_bytes(scope) != self._scope
                or self.port._head_policy_binding_failed
                or self.authority.generation != scope['generation']
                or self.authority.session_id != scope['session_id']
                or 'neck' not in self.authority._armed
                or self.authority._identities.get('neck') != scope['controller_identity']):
            raise PermissionError('HEAD_INVENTORY_DISPATCH_SCOPE_INVALID')

    def _current(self, goal_uuid=None):
        if self._stop_requested.is_set():
            raise PermissionError('HEAD_INVENTORY_STOPPED')
        self._check_scope()
        if self._guard() is not True:
            raise PermissionError('HEAD_INVENTORY_CURRENT_GUARD_REFUSED')
        self._check_scope()
        if goal_uuid is not None:
            if not self.local_state.validate_current(goal_uuid, now_ns=time.monotonic_ns(),
                    authority_scope=self._authority_scope()):
                raise PermissionError('HEAD_INVENTORY_CLAIM_EXPIRED')

    def stop_admission(self):
        """Close future Head admission without faulting or doing external I/O."""
        self._stop_requested.set()
        self._trajectory_guard.stop()

    def _fault(self, reason='HEAD_INVENTORY_DISPATCH_FAILED'):
        self._failed = True
        self.port._head_policy_binding_failed = True
        token = self.local_state.latch_fault(reason)
        try: self._fault_callback(reason)
        except Exception as error: self._fault_handler_error = type(error).__name__
        try: self.local_state.finish_fault(token, {'reason': reason})
        except Exception as error: self._local_fault_handler_error = type(error).__name__
        try: self._emit('DISPATCH_FAULT', epoch=self.epoch, generation=self.generation)
        except Exception: pass

    def send(self, goal):
        """Reject the former position-only API for bound file-v1 Head dispatch."""
        raise PermissionError('HEAD_POSITION_ONLY_BYPASS_REFUSED')

    def send_prepared_head(self, prepared: PreparedHeadTrajectory):
        if type(prepared) is not PreparedHeadTrajectory:
            raise PermissionError('HEAD_PREPARED_TYPE_INVALID')
        if self.revoked:
            raise PermissionError('HEAD_INVENTORY_DISPATCH_REVOKED')
        if not self._send_lock.acquire(blocking=False):
            self._fault('HEAD_INVENTORY_DISPATCH_BUSY')
            raise PermissionError('HEAD_INVENTORY_DISPATCH_BUSY')
        trace = dict(goal_uuid=None, error_type=None, phases=[], inventory_record=None,
                     original_cdr_sha256=None, original_cdr=None)
        def mark(phase, **details):
            trace['phases'].append(dict(phase=phase, wall_s=time.monotonic(), **details))

        def revalidate(phase):
            started_ns = time.monotonic_ns()
            result = self._trajectory_guard.revalidate(prepared)
            mark(phase, elapsed_ns=time.monotonic_ns() - started_ns)
            return result
        mark('entry')
        try:
            self._current()
            proof = revalidate('guard_entry_revalidated')
            payload = bytes(prepared.original_cdr)
            message = deserialize_message(payload, FollowJointTrajectory.Goal)
            parsed = uuid.uuid4()
            goal_uuid = UUID(uuid=list(parsed.bytes))
            gid = str(parsed)
            trace['goal_uuid'] = gid
            typed = json.loads(canonical_bytes(message_to_ordereddict(message)))
            if (hashlib.sha256(payload).hexdigest() != proof.get('original_cdr_sha256')
                    or hashlib.sha256(canonical_bytes(typed)).hexdigest()
                    != proof.get('typed_goal_sha256')):
                raise PermissionError('HEAD_PREPARED_PROVENANCE_MISMATCH')
            trace['prepared_proof_sha256'] = hashlib.sha256(prepared.proof_bytes).hexdigest()
            mark('goal_encoded')
            self._sequence += 1
            inventory_sha = None

            def register(binding):
                nonlocal inventory_sha
                self._check_scope()
                identity = self.controller_identity
                if (binding.role != 'neck' or binding.generation != self.generation
                        or binding.session_id != self.session_id or binding.goal_cdr != payload
                        or binding.goal_uuid != parsed.bytes
                        or binding.controller_incarnation != identity['incarnation']
                        or binding.controller_boot_incarnation != identity['boot']
                        or binding.deadline_ns - binding.claim_monotonic_ns != 400_000_000
                        or not binding.claim_monotonic_ns <= time.monotonic_ns() < binding.deadline_ns):
                    raise PermissionError('HEAD_INVENTORY_NATIVE_BINDING_INVALID')
                record = dict(goal_uuid=gid, typed_goal=typed,
                    payload_sha256=hashlib.sha256(payload).hexdigest(), generation=self.generation,
                    controller_identity=identity, attempt_epoch=self.epoch,
                    session_id=self.session_id, role='neck', operation_sequence=self._sequence,
                    claim_monotonic_ns=binding.claim_monotonic_ns, deadline_ns=binding.deadline_ns)
                inventory_sha = hashlib.sha256(canonical_bytes(record)).hexdigest()
                self.local_state.register_prepared(record, payload)
                trace['inventory_record'] = copy.deepcopy(record)
                trace['original_cdr_sha256'] = record['payload_sha256']
                trace['original_cdr'] = bytes(payload)
                mark('local_inventory_registered')
                if self._own(json.loads(canonical_bytes(record)), payload) is not True:
                    raise PermissionError('HEAD_PRIMARY_INVENTORY_REFUSED')
                primary = self.port._goals.get(gid)
                if type(primary) is not dict:
                    raise PermissionError('HEAD_PRIMARY_INVENTORY_RECEIPT_MISSING')
                if type(primary.get('primary_inventory')) is not bytes:
                    raise PermissionError('HEAD_PRIMARY_INVENTORY_RECEIPT_MALFORMED')
                if hashlib.sha256(primary['primary_inventory']).hexdigest() != inventory_sha:
                    raise PermissionError('HEAD_PRIMARY_INVENTORY_DIGEST_MISMATCH')
                if primary.get('prepared_cdr_sha256') != record['payload_sha256']:
                    raise PermissionError('HEAD_PRIMARY_CDR_DIGEST_MISMATCH')
                mark('primary_inventory_owned')
                revalidate('guard_after_primary_inventory')
                self._current(gid)
                self.local_state.mark_reserve_attempt(gid, time.monotonic_ns())
                mark('native_reserve_ready')
                return True

            reserved = self.authority.reserve('neck', goal=payload, goal_uuid=parsed.bytes,
                before_reserve=register)
            if reserved is not True:
                raise PermissionError('HEAD_INVENTORY_NATIVE_RESERVATION_REFUSED')
            self.local_state.mark_reserved(gid, time.monotonic_ns())
            mark('native_reserved')
            self._current(gid)
            self.local_state.mark_sdk_attempt(gid, time.monotonic_ns())
            mark('sdk_attempt_recorded')

            def final_guard():
                revalidate('guard_before_sdk')
                self._current(gid)
                mark('sdk_final_guarded')
                return True

            sent = self.port.send_prepared(message, goal_uuid=goal_uuid,
                expected_cdr=payload, dispatch_guard=final_guard)
            if sent != gid:
                raise PermissionError('HEAD_INVENTORY_SDK_UUID_MISMATCH')
            mark('complete')
            return sent
        except Exception as error:
            trace['error_type'] = type(error).__name__
            mark('failed')
            if not self._stop_requested.is_set():
                self._fault()
            raise
        finally:
            self._dispatch_traces.append(trace)
            self._send_lock.release()

    def cancel(self, goal_uuid): return self.port.cancel(goal_uuid)
    def stopped(self): return self.port.stopped()
    def _feedback(self, message): return self.port._feedback(message)
