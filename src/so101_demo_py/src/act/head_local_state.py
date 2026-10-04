"""Single-owner in-memory Head preparation inventory and fixed-window claims."""

import hashlib
import json
import re
import threading
import time
import uuid

from .head_evidence_identity import bounded_payload, canonical_bytes


_RECORD_FIELDS = {
    'goal_uuid', 'typed_goal', 'payload_sha256', 'generation', 'controller_identity',
    'attempt_epoch', 'session_id', 'role', 'operation_sequence',
    'claim_monotonic_ns', 'deadline_ns',
}
_MAX_INVENTORY = 128
_CLAIM_WINDOW_NS = 400_000_000


class HeadLocalState:
    """Own one attempt scope and retain every possibly reserved or sent UUID.

    Each 400 ms deadline bounds native admission and dispatch only. An expired
    claim never authorizes another send, but it does not expire motion state or
    remove the UUID needed for stop reconciliation.
    """

    _scope_lock = threading.Lock()
    _live_scopes = set()

    def __init__(self, scope, search_deadline_ns, *, clock_ns=time.monotonic_ns):
        required = {'epoch', 'generation', 'session_id', 'policy_sha256', 'controller_identity'}
        if (type(scope) is not dict or set(scope) != required
                or type(scope['epoch']) is not str
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', scope['epoch']) is None
                or type(scope['session_id']) is not str
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', scope['session_id']) is None
                or type(scope['generation']) is not int or not 0 < scope['generation'] < 2**64
                or type(scope['policy_sha256']) is not str
                or re.fullmatch(r'[0-9a-f]{64}', scope['policy_sha256']) is None
                or type(scope['controller_identity']) is not dict
                or set(scope['controller_identity']) != {'generation', 'incarnation', 'boot'}
                or type(scope['controller_identity']['generation']) is not int
                or scope['controller_identity']['generation'] != scope['generation']
                or any(type(scope['controller_identity'][key]) is not str
                       or re.fullmatch(r'[\x20-\x7e]{1,64}', scope['controller_identity'][key]) is None
                       for key in ('incarnation', 'boot'))
                or type(search_deadline_ns) is not int or not 0 < search_deadline_ns < 2**63
                or not callable(clock_ns)):
            raise ValueError('HEAD_LOCAL_SCOPE_INVALID')
        self._scope_json = canonical_bytes(scope)
        self._scope_key = hashlib.sha256(self._scope_json).hexdigest()
        with self._scope_lock:
            if self._scope_key in self._live_scopes:
                raise ValueError('HEAD_LOCAL_SCOPE_REUSED')
            self._live_scopes.add(self._scope_key)
        self._search_deadline_ns = search_deadline_ns
        self.clock_ns = clock_ns
        self.motion_epoch = 0
        self._records = {}
        self._cdrs = {}
        self._metadata = {}
        self._fault = None
        self._fault_body = None
        self._fault_token = None
        self._lock = threading.Lock()

    @property
    def search_deadline_ns(self):
        return self._search_deadline_ns

    @property
    def scope(self):
        return json.loads(self._scope_json)

    @property
    def faulted(self):
        with self._lock:
            return self._fault is not None

    @property
    def fault_occurrence_ns(self):
        """Return the immutable builtin-monotonic time of the first fault."""
        with self._lock:
            return None if self._fault is None else self._fault['occurred_ns']

    @property
    def inventory(self):
        with self._lock:
            records = tuple(self._records.items())
        return {goal_id: json.loads(body) for goal_id, body in records}

    def prepared_cdr(self, goal_uuid):
        with self._lock:
            payload = self._cdrs.get(goal_uuid) if type(goal_uuid) is str else None
            if payload is None:
                raise PermissionError('HEAD_LOCAL_UUID_UNKNOWN')
            return bytes(payload)

    @property
    def snapshot(self):
        with self._lock:
            records = tuple(self._records.items())
            fault_body = self._fault_body
            fault = self._fault
            motion_epoch = self.motion_epoch
        if fault_body is not None:
            fault = json.loads(fault_body)
        elif fault is not None:
            fault = {'reason': fault['reason'], 'evidence': None,
                     'occurred_ns': fault['occurred_ns']}
        return {'scope': self.scope, 'search_deadline_ns': self.search_deadline_ns,
                'motion_epoch': motion_epoch,
                'inventory': {goal_id: json.loads(body) for goal_id, body in records},
                'fault': fault}

    def _latch_fault_locked(self, reason):
        if self._fault is not None:
            return None
        occurred_ns = time.monotonic_ns()
        self._fault = {'reason': reason, 'evidence': None, 'occurred_ns': occurred_ns}
        self._fault_token = object()
        return self._fault_token

    def latch_fault(self, reason):
        """Latch the first builtin monotonic fault origin without processing evidence or invoking the claim clock."""
        if type(reason) is not str or not reason:
            raise ValueError('HEAD_LOCAL_FAULT_INVALID')
        with self._lock:
            return self._latch_fault_locked(reason)

    def finish_fault(self, token, evidence=None):
        """Consume the first-fault diagnostic token before bounded work."""
        if token is None:
            return self.snapshot['fault']
        with self._lock:
            if token is not self._fault_token or self._fault is None:
                claimed = None
            else:
                self._fault_token = None
                claimed = (self._fault['reason'], self._fault['occurred_ns'])
        if claimed is None:
            return self.snapshot['fault']
        reason, occurred_ns = claimed
        owned = bounded_payload({} if evidence is None else evidence)
        body = canonical_bytes({'reason': reason, 'evidence': owned,
                                'occurred_ns': occurred_ns})
        with self._lock:
            if (self._fault is not None and self._fault['reason'] == reason
                    and self._fault['occurred_ns'] == occurred_ns
                    and self._fault_body is None):
                self._fault_body = body
        return json.loads(body)

    def fault(self, reason, evidence=None):
        token = self.latch_fault(reason)
        if token is not None:
            self.finish_fault(token, evidence)
        return self.snapshot['fault']

    def _require_live(self):
        if self._fault is not None:
            raise PermissionError('HEAD_LOCAL_STATE_FAULTED')

    def _faulted_validation(self, reason):
        token = self.latch_fault(reason)
        if token is not None:
            try:
                self.finish_fault(token, {'reason': reason})
            except Exception:
                pass
        raise PermissionError(reason)

    def register_prepared(self, record, typed_goal_bytes):
        from so101_demo.adapters.act.head_goal_binding import validate_goal_inventory

        try:
            owned = validate_goal_inventory(record, typed_goal_bytes)
            scope = self.scope
            identity = owned.get('controller_identity')
            goal_id = owned.get('goal_uuid')
            parsed_uuid = uuid.UUID(goal_id) if type(goal_id) is str else None
            now_ns = self.clock_ns()
            if (set(owned) != _RECORD_FIELDS or type(goal_id) is not str
                    or parsed_uuid is None or str(parsed_uuid) != goal_id or parsed_uuid.version != 4
                    or type(owned.get('generation')) is not int
                    or owned['generation'] != scope['generation']
                    or owned.get('attempt_epoch') != scope['epoch']
                    or owned.get('session_id') != scope['session_id']
                    or owned.get('role') != 'neck'
                    or type(identity) is not dict or set(identity) != {'generation', 'incarnation', 'boot'}
                    or type(identity.get('generation')) is not int
                    or identity['generation'] != scope['generation']
                    or any(type(identity.get(key)) is not str
                           or re.fullmatch(r'[\x20-\x7e]{1,64}', identity[key]) is None
                           for key in ('incarnation', 'boot'))
                    or canonical_bytes(identity) != canonical_bytes(scope['controller_identity'])
                    or type(owned.get('operation_sequence')) is not int
                    or type(owned.get('claim_monotonic_ns')) is not int
                    or type(owned.get('deadline_ns')) is not int
                    or not 0 < owned['claim_monotonic_ns'] < owned['deadline_ns'] < 2**63
                    or owned['deadline_ns'] - owned['claim_monotonic_ns'] != _CLAIM_WINDOW_NS
                    or owned['deadline_ns'] > self.search_deadline_ns
                    or not owned['claim_monotonic_ns'] <= now_ns < owned['deadline_ns']
                    or now_ns >= self.search_deadline_ns):
                self._faulted_validation('HEAD_LOCAL_PREPARED_BINDING_INVALID')
            body = canonical_bytes(owned)
            payload = bytes(typed_goal_bytes)
        except PermissionError:
            raise
        except Exception:
            self._faulted_validation('HEAD_LOCAL_PREPARED_BINDING_INVALID')

        reason = None
        with self._lock:
            if self._fault is not None:
                raise PermissionError('HEAD_LOCAL_STATE_FAULTED')
            previous_sequence = max(
                (metadata['operation_sequence'] for metadata in self._metadata.values()), default=0)
            if (len(self._records) >= _MAX_INVENTORY or goal_id in self._records
                    or owned['operation_sequence'] != previous_sequence + 1):
                reason = 'HEAD_LOCAL_DUPLICATE_PREPARED'
                token = self._latch_fault_locked(reason)
            else:
                token = None
                self._records[goal_id] = body
                self._cdrs[goal_id] = payload
                self._metadata[goal_id] = {
                    'operation_sequence': owned['operation_sequence'],
                    'claim_monotonic_ns': owned['claim_monotonic_ns'],
                    'deadline_ns': owned['deadline_ns'],
                }
        if reason is not None:
            if token is not None:
                try:
                    self.finish_fault(token, {'reason': reason})
                except Exception:
                    pass
            raise PermissionError(reason)
        return json.loads(body)

    def _record(self, goal_uuid):
        if type(goal_uuid) is not str:
            raise PermissionError('HEAD_LOCAL_UUID_UNKNOWN')
        with self._lock:
            self._require_live()
            body = self._records.get(goal_uuid)
        if body is None:
            raise PermissionError('HEAD_LOCAL_UUID_UNKNOWN')
        return json.loads(body)

    def claim_state(self, goal_uuid, now_ns):
        record = self._record(goal_uuid)
        if type(now_ns) is not int or now_ns < record['claim_monotonic_ns']:
            raise PermissionError('HEAD_LOCAL_CLAIM_CLOCK_INVALID')
        return now_ns < record['deadline_ns'] and now_ns < self.search_deadline_ns

    def mark_reserve_attempt(self, goal_uuid, occurred_ns):
        self._mark(goal_uuid, 'reserve_attempt_ns', occurred_ns, prior=None)

    def mark_reserved(self, goal_uuid, occurred_ns):
        self._mark(goal_uuid, 'reserved_ns', occurred_ns, prior='reserve_attempt_ns')

    def mark_sdk_attempt(self, goal_uuid, occurred_ns):
        self._mark(goal_uuid, 'sdk_attempt_ns', occurred_ns, prior='reserved_ns')

    def _mark(self, goal_uuid, field, occurred_ns, *, prior):
        if type(occurred_ns) is not int or occurred_ns < 0:
            raise ValueError('HEAD_LOCAL_ATTEMPT_CLOCK_INVALID')
        for _ in range(3):
            with self._lock:
                self._require_live()
                body = self._records.get(goal_uuid)
                metadata = self._metadata.get(goal_uuid)
                if body is None or metadata is None:
                    raise PermissionError('HEAD_LOCAL_UUID_UNKNOWN')
                attempts = dict(metadata.get('attempts', {}))
                claim = metadata['claim_monotonic_ns']
                deadline = metadata['deadline_ns']
                if (field in attempts or (prior is not None and prior not in attempts)
                        or occurred_ns < claim
                        or (prior is not None and occurred_ns < attempts[prior])
                        or (field != 'reserved_ns' and
                            (occurred_ns >= deadline or occurred_ns >= self.search_deadline_ns))):
                    raise PermissionError('HEAD_LOCAL_ATTEMPT_ORDER_INVALID')
            record = json.loads(body)
            record[field] = occurred_ns
            updated_body = canonical_bytes(record)
            attempts[field] = occurred_ns
            with self._lock:
                self._require_live()
                current = self._metadata.get(goal_uuid)
                if self._records.get(goal_uuid) is not body or current is None:
                    continue
                if current.get('attempts', {}) != metadata.get('attempts', {}):
                    continue
                current['attempts'] = attempts
                self._records[goal_uuid] = updated_body
                return
        raise PermissionError('HEAD_LOCAL_ATTEMPT_ORDER_INVALID')

    def validate_current(self, goal_uuid, *, now_ns, authority_scope):
        record = self._record(goal_uuid)
        expected = self.scope
        if canonical_bytes(authority_scope) != canonical_bytes(expected):
            raise PermissionError('HEAD_LOCAL_AUTHORITY_SCOPE_MISMATCH')
        if not self.claim_state(goal_uuid, now_ns):
            return False
        return record
