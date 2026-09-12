"""Durable scheduling for isolated parallel validation workers.

The journal alone is authoritative. Every transition holds one state lock and
appends a projection delta before applying it or acknowledging authorization.
The injected result port verifies sealed artifacts and discovers a completed
artifact in the workspace reserved by LEASE_GRANTED. It must not call back into
the coordinator or authorize worker actions; Task 4 supplies the disk adapter.
"""

import hashlib
import json
import math
import os
import tempfile
import threading
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from functools import wraps
from pathlib import Path
from typing import Protocol

from .contracts import (
    AttemptStatus, BatchSummary, LeaseIdentity, ParallelRuntimeConfig,
    PointStatus, RunMode, ValidationStatus, WorkerState,
)


_START_AUTHORIZATION_FROM_PROJECTION = object()


class SealedResultPort(Protocol):
    """Verify identity, manifest and status; discover only inside the given workspace.

    verify returns {status: str, sha256: lowercase 64-character digest} or raises
    ValueError. discover returns a sealed location or None, never an unsealed
    candidate. Journal commits take precedence over both methods.
    """

    def verify(self, lease: LeaseIdentity, location: str, run_mode: RunMode) -> dict:
        """Read and validate a sealed result without modifying it."""

    def discover(self, lease: LeaseIdentity, workspace: Path) -> str | None:
        """Find a sealed result whose identity is the reserved lease."""


@dataclass(frozen=True)
class PointProjection:
    """A selected point and its physical or validation disposition."""

    status: PointStatus = PointStatus.UNRUN
    terminal: bool = False
    validation_status: ValidationStatus | None = None
    active_attempt: str | None = None
    blocked_by: str | None = None
    attempts: int = 0


@dataclass(frozen=True)
class WorkerProjection:
    """Detached worker state; authorization is also bounded by heartbeat ACK loss."""

    generation: int
    state: WorkerState
    lease_count: int = 0
    lease: LeaseIdentity | None = None
    workspace: Path | None = None
    stage_started_monotonic_s: float | None = None
    stage_deadline_monotonic_s: float | None = None
    heartbeat_deadline_monotonic_s: float | None = None
    action_allowed: bool = False
    reset_allowed: bool = False
    inference_allowed: bool = False
    stop_requested: bool = False
    invalid_point: str | None = None
    recovery_deadline_monotonic_s: float | None = None


@dataclass(frozen=True)
class CoordinatorSnapshot:
    """Replayable projection with qualification derived from frozen contracts."""

    workers: dict[str, WorkerProjection]
    points: dict[str, PointProjection]
    batch_started_monotonic_s: float
    batch_deadline_monotonic_s: float
    broker_healthy: bool
    broker_recovery_deadline_monotonic_s: float | None
    broker_recovery_failed: bool
    terminal_reason: str | None
    batch_cleanup_complete: bool
    summary: BatchSummary


def _locked(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class BatchCoordinator:
    """Own durable grants, K debits, deadlines and terminal point accounting.

    This object does not run processes. Its transport consumer must observe the
    returned ACK before reset/inference/action, stop on missing heartbeat ACK
    after five seconds, and provide verified cleanup/re-admission facts. A lease
    identity is a fencing token, not permission to execute by itself.
    """

    def __init__(
            self, journal, request, *, config, clock=time.monotonic, result_port,
            fault_hook=None, recovery_start_authorization=None):
        """Restore durable state or initialize one immutable batch."""
        self._lock = threading.RLock()
        self.journal, self.request = journal, request
        self.clock, self.result_port = clock, result_port
        if fault_hook is not None and not callable(fault_hook):
            raise ValueError('FAULT_HOOK_CALLABLE')
        if (recovery_start_authorization is not None
                and not callable(recovery_start_authorization)):
            raise ValueError('RECOVERY_AUTHORIZATION_CALLABLE')
        self._fault_hook = fault_hook
        self._recovery_start_authorization = recovery_start_authorization
        if not isinstance(config, ParallelRuntimeConfig):
            raise ValueError('FROZEN_CONFIG_REQUIRED')
        self.config = config
        self._state = {'workers': {}, 'points': {}}
        self._events = {}
        with self._lock:
            replay = journal.replay()
            for event in replay.events:
                self._apply(event)
            frozen = asdict(request)
            frozen['evidence_root'] = str(request.evidence_root)
            frozen['selected_point_ids'] = list(request.selected_point_ids)
            if self._events:
                if self._state.get('request') != frozen:
                    raise ValueError('BATCH_REQUEST_CHANGED')
                # Older review-clean journal prefixes did not need these fields.
                # Their absence means no Broker failure had yet been observed.
                self._state.setdefault('broker_recovery_deadline_monotonic_s', None)
                self._state.setdefault('broker_recovery_failed', False)
                self._recover_interrupted_leases(replay.events)
                self._audit_late_seals(replay.events)
            else:
                now = self.clock()
                self._emit('BATCH_STARTED', {
                    'request': frozen, 'batch_started_monotonic_s': now,
                    'batch_deadline_monotonic_s': now + self.config.batch_hard_timeout_s,
                    'broker_healthy': True,
                    'broker_recovery_deadline_monotonic_s': None,
                    'broker_recovery_failed': False,
                    'terminal_reason': None,
                    'batch_cleanup_complete': False,
                    'points': {p: asdict(PointProjection()) for p in request.selected_point_ids},
                })

    def _fault(self, boundary, phase):
        if self._fault_hook is not None:
            self._fault_hook(boundary, phase)

    def _apply(self, event):
        if event.idempotency_key in self._events:
            return
        delta = deepcopy(event.payload['delta'])
        for name in ('points', 'workers'):
            self._state[name].update(delta.pop(name, {}))
        self._state.update(delta)
        self._events[event.idempotency_key] = event

    def _emit(self, kind, delta, *, request_key=None, identity=None, response=None):
        key = request_key or f'coordinator-{len(self._events) + 1}'
        if key in self._events:
            raise ValueError('REQUEST_KEY_CONFLICT')
        self._fault(kind, 'before_fsync')
        event = self.journal.append(kind, key, {
            'delta': delta, 'identity': identity, 'response': response,
        })
        self._fault(kind, 'after_fsync')
        self._apply(event)
        self._write_aggregate()
        self._fault(kind, 'before_ack')
        return response

    @staticmethod
    def _event_authorized_start(lease, events):
        expected = BatchCoordinator._identity(lease)
        for event in events:
            if event.type != 'ATTEMPT_STARTED':
                continue
            identity = event.payload.get('identity')
            if (type(identity) is dict
                    and all(identity.get(key) == value
                            for key, value in expected.items())):
                return True
        return False

    def _recover_interrupted_leases(self, events):
        """Adjudicate every active lease issued by a previous coordinator epoch."""
        # Non-physical validation has no motion ambiguity and remains resumable;
        # Task 12's conservative crash adjudication is the physical ATTEMPT boundary.
        if self.request.run_mode is not RunMode.EXECUTE:
            return
        for worker in tuple(deepcopy(self._state['workers']).values()):
            if not worker.get('lease'):
                continue
            lease = LeaseIdentity(**worker['lease'])
            if lease.coordinator_epoch == self.journal.coordinator_epoch:
                continue
            durable_start = self._event_authorized_start(lease, events)
            if durable_start:
                # An injected diagnostic port may add uncertainty but can never
                # erase the journal's durable authorization boundary.
                started = True
            elif self._recovery_start_authorization is None:
                started = False
            else:
                started = self._recovery_start_authorization(lease, tuple(events))
                if started not in (True, False, None):
                    raise ValueError('RECOVERY_AUTHORIZATION_PROOF')
            location = None
            if started is True:
                try:
                    location = self.result_port.discover(
                        lease, Path(worker['workspace']))
                except (OSError, ValueError):
                    location = None
            if location is not None:
                try:
                    self._commit(
                        lease,
                        location,
                        None,
                        validation=self.request.run_mode != RunMode.EXECUTE,
                        discovered=True,
                    )
                    continue
                except ValueError:
                    pass
            self._expire(
                lease,
                force=True,
                start_authorized=started,
                allow_discovery=False,
            )
        self._evaluate()

    @staticmethod
    def _late_result_identity(lease, location, kind):
        return {
            **BatchCoordinator._identity(lease),
            'location': str(location),
            'rejected_kind': kind,
        }

    def _audit_late_result(self, lease, location, kind):
        identity = self._late_result_identity(lease, location, kind)
        digest = hashlib.sha256(json.dumps(
            identity, sort_keys=True, separators=(',', ':'), allow_nan=False,
        ).encode()).hexdigest()
        key = f'late-result-{digest}'
        existing = self._events.get(key)
        if existing is not None:
            if (existing.type != 'LATE_RESULT_REJECTED'
                    or existing.payload.get('identity') != identity):
                raise ValueError('REQUEST_KEY_CONFLICT')
            return
        delta = {}
        point = self._state['points'].get(lease.point_id)
        if (self.request.run_mode is RunMode.EXECUTE
                and point is not None
                and not point['terminal']
                and point['active_attempt'] is None):
            point = deepcopy(point)
            blocked_by = point['blocked_by']
            point.update(
                status=PointStatus.INDETERMINATE,
                terminal=True,
                blocked_by=None,
            )
            delta['points'] = {lease.point_id: point}
            worker = self._state['workers'].get(blocked_by)
            if worker is not None and worker.get('invalid_point') == lease.point_id:
                worker = deepcopy(worker)
                worker['invalid_point'] = None
                delta['workers'] = {blocked_by: worker}
        self._emit(
            'LATE_RESULT_REJECTED', delta, request_key=key, identity=identity)
        self._evaluate()

    def _audit_late_seals(self, events):
        grants = {}
        for event in events:
            if event.type != 'LEASE_GRANTED':
                continue
            response = event.payload.get('response')
            try:
                lease = LeaseIdentity(**response)
                workspace = event.payload['delta']['workers'][lease.worker_id]['workspace']
            except (KeyError, TypeError, ValueError):
                continue
            grants[tuple(self._identity(lease).items())] = (lease, workspace)
        for event in events:
            if event.type != 'LEASE_EXPIRED':
                continue
            identity = event.payload.get('identity')
            if type(identity) is not dict:
                continue
            granted = grants.get(tuple(identity.items()))
            if granted is None:
                # Canonical dict order is not authority; compare by value too.
                granted = next((
                    value for value in grants.values()
                    if self._identity(value[0]) == identity
                ), None)
            if granted is None:
                continue
            lease, workspace = granted
            try:
                location = self.result_port.discover(lease, Path(workspace))
            except (OSError, ValueError):
                location = None
            if location is not None:
                kind = ('RESULT_COMMITTED' if self.request.run_mode is RunMode.EXECUTE
                        else 'VALIDATION_COMMITTED')
                self._audit_late_result(lease, location, kind)

    def _duplicate(self, key, kind, identity):
        if key is None or key not in self._events:
            return None
        event = self._events[key]
        if event.type != kind or event.payload['identity'] != identity:
            raise ValueError('REQUEST_KEY_CONFLICT')
        return event

    def _write_aggregate(self):
        root = self.journal.root
        fd, name = tempfile.mkstemp(prefix='.aggregate_results-', dir=root)
        data = deepcopy(self._state)
        summary = self.snapshot().summary
        data.update({field: getattr(summary, field) for field in (
            'coverage_complete', 'execution_complete', 'validation_complete',
            'validation_passed', 'qualification_applicable', 'qualification_passed')})
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / 'aggregate_results.json')
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    def _worker(self, worker_id, generation):
        worker = self._state['workers'].get(worker_id)
        if worker is None or worker['generation'] != generation:
            raise ValueError('STALE_WORKER_GENERATION')
        return deepcopy(worker)

    def _check_recovery_deadline(self, worker, supplied):
        deadline = worker.get('recovery_deadline_monotonic_s')
        if (worker.get('state') != 'RECOVERING'
                or isinstance(supplied, bool)
                or not isinstance(supplied, (int, float))
                or not math.isfinite(supplied)
                or supplied != deadline
                or deadline != worker.get('stage_deadline_monotonic_s')
                or self.clock() >= deadline):
            raise ValueError('RECOVERY_DEADLINE_INVALID')

    @staticmethod
    def _identity(lease):
        value = asdict(lease)
        value.pop('lease_issued_monotonic_s')
        value.pop('lease_deadline_monotonic_s')
        return value

    @staticmethod
    def _gate_summary(lease, value):
        """Return a detached canonical initial-gate proof bound to ``lease``."""
        required = {
            'schema_version', 'kind', 'batch_id', 'coordinator_epoch', 'worker_id',
            'worker_generation', 'point_id', 'attempt_id', 'lease_generation',
            'reset_epoch', 'simulation_session_id',
            'reset_completed_monotonic_s', 'source_frame_monotonic_s',
            'canonical_joints', 'no_controller_goal', 'no_attachment',
            'no_contact', 'no_stale_node',
        }
        if type(value) is not dict or set(value) != required:
            raise ValueError('GATE_SUMMARY_SCHEMA')
        expected = {
            'batch_id': lease.batch_id,
            'coordinator_epoch': lease.coordinator_epoch,
            'worker_id': lease.worker_id,
            'worker_generation': lease.worker_generation,
            'point_id': lease.point_id,
            'attempt_id': lease.attempt_id,
            'lease_generation': lease.lease_generation,
        }
        if type(value['schema_version']) is not int or value['schema_version'] != 1:
            raise ValueError('GATE_SUMMARY_SCHEMA')
        if type(value['kind']) is not str or value['kind'] != 'POINT_INITIAL_GATE':
            raise ValueError('GATE_SUMMARY_SCHEMA')
        for field, expected_value in expected.items():
            if type(value[field]) is not type(expected_value) or value[field] != expected_value:
                raise ValueError('GATE_SUMMARY_IDENTITY')
        for field in ('reset_epoch', 'simulation_session_id'):
            if type(value[field]) is not str or not value[field].strip():
                raise ValueError('GATE_SUMMARY_RESET_IDENTITY')
        for field in ('reset_completed_monotonic_s', 'source_frame_monotonic_s'):
            timestamp = value[field]
            if (isinstance(timestamp, bool)
                    or not isinstance(timestamp, (int, float))
                    or not math.isfinite(timestamp)):
                raise ValueError('GATE_SUMMARY_TIMESTAMP')
        if value['source_frame_monotonic_s'] <= value['reset_completed_monotonic_s']:
            raise ValueError('GATE_SUMMARY_TIMESTAMP')
        for field in ('canonical_joints', 'no_controller_goal', 'no_attachment',
                      'no_contact', 'no_stale_node'):
            if value[field] is not True:
                raise ValueError('GATE_SUMMARY_FACT')
        try:
            encoded = json.dumps(
                value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError('GATE_SUMMARY_NOT_CANONICAL') from error
        return json.loads(encoded)

    @staticmethod
    def _scheduler_summary(lease, value):
        required = {
            'schema_version', 'kind', 'batch_id', 'coordinator_epoch',
            'worker_id', 'worker_generation', 'point_id', 'attempt_id',
            'lease_generation', 'point_gate_applicable',
            'physical_runtime_started', 'scheduler_only',
        }
        if type(value) is not dict or set(value) != required:
            raise ValueError('GATE_SUMMARY_SCHEMA')
        expected = {
            'schema_version': 1,
            'kind': 'SCHEDULER_START',
            'batch_id': lease.batch_id,
            'coordinator_epoch': lease.coordinator_epoch,
            'worker_id': lease.worker_id,
            'worker_generation': lease.worker_generation,
            'point_id': lease.point_id,
            'attempt_id': lease.attempt_id,
            'lease_generation': lease.lease_generation,
            'point_gate_applicable': False,
            'physical_runtime_started': False,
            'scheduler_only': True,
        }
        for field, expected_value in expected.items():
            if type(value[field]) is not type(expected_value) or value[field] != expected_value:
                raise ValueError('GATE_SUMMARY_IDENTITY')
        try:
            encoded = json.dumps(
                value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError('GATE_SUMMARY_NOT_CANONICAL') from error
        return json.loads(encoded)

    def _start_summary(self, lease, value):
        if self.request.run_mode is RunMode.DRY_RUN:
            return self._scheduler_summary(lease, value)
        return self._gate_summary(lease, value)

    def _start_transition(self, lease, request_key, kind, gate_summary):
        """Resolve duplicate start identity before validating a changed payload."""
        self._tick()
        identity = self._identity(lease)
        identity['gate_summary'] = deepcopy(gate_summary)
        duplicate = self._duplicate(request_key, kind, identity)
        if duplicate:
            self._active(lease)
            return self.snapshot().workers[lease.worker_id]
        summary = self._start_summary(lease, gate_summary)
        return self._transition(
            lease, request_key, kind, 'INITIALIZING', 'EXECUTING',
            gate_summary=summary)

    def _active(self, lease, *, current_epoch=True):
        if current_epoch and lease.coordinator_epoch != self.journal.coordinator_epoch:
            raise ValueError('STALE_COORDINATOR_EPOCH')
        worker = self._worker(lease.worker_id, lease.worker_generation)
        if (worker['lease'] is None
                or self._identity(LeaseIdentity(**worker['lease'])) != self._identity(lease)):
            raise ValueError('STALE_LEASE')
        return worker

    def _duration(self, state):
        return {
            'LEASED': self.config.lease_ack_timeout_s,
            'INITIALIZING': self.config.initializing_hard_timeout_s,
            'EXECUTING': self.config.executing_hard_timeout_s,
            'FINALIZING': self.config.finalizing_hard_timeout_s,
            'RECOVERING': self.config.worker_recovery_timeout_s,
        }[state]

    def _stage(self, worker, state):
        now = self.clock()
        # Reconnect, generation and repeated phase requests must not restart time.
        if worker['state'] != state:
            worker.update(state=state, stage_started_monotonic_s=now,
                          stage_deadline_monotonic_s=min(
                              now + self._duration(state),
                              self._state['batch_deadline_monotonic_s']))
            worker['recovery_deadline_monotonic_s'] = (
                worker['stage_deadline_monotonic_s']
                if state == 'RECOVERING' else None)
        worker['action_allowed'] = (
            state == 'EXECUTING' and self.request.run_mode == RunMode.EXECUTE)
        worker['inference_allowed'] = state == 'EXECUTING'
        worker['reset_allowed'] = state == 'INITIALIZING'
        worker['stop_requested'] = state == 'RECOVERING'
        return worker

    @_locked
    def register_worker(
            self, worker_id, *, generation, recovery_deadline_monotonic_s=None):
        """Register an admitted slot; a restart never replenishes its K budget."""
        # Validate identifiers/generations using the shared immutable identity.
        LeaseIdentity(self.request.batch_id, self.journal.coordinator_epoch,
                      worker_id, generation, self.request.selected_point_ids[0],
                      'registration', 1, 0, 1)
        old = self._state['workers'].get(worker_id)
        if (
            self._state['terminal_reason'] is not None
            and recovery_deadline_monotonic_s is None
            and old is None
        ):
            raise ValueError('STOP_REQUESTED')
        if old:
            if generation < old['generation']:
                raise ValueError('STALE_WORKER_GENERATION')
            if generation == old['generation']:
                if recovery_deadline_monotonic_s is not None:
                    self._check_recovery_deadline(old, recovery_deadline_monotonic_s)
                return self.snapshot().workers[worker_id]
            if old['lease']:
                raise ValueError('ACTIVE_LEASE_REQUIRES_FENCING')
            if old['state'] == 'RECOVERING':
                if generation != old['generation'] + 1:
                    raise ValueError('WORKER_GENERATION_SEQUENCE')
                self._check_recovery_deadline(
                    old, recovery_deadline_monotonic_s)
            elif recovery_deadline_monotonic_s is not None:
                raise ValueError('RECOVERY_DEADLINE_UNEXPECTED')
            worker = deepcopy(old)
            worker['generation'] = generation
        else:
            if recovery_deadline_monotonic_s is not None:
                raise ValueError('RECOVERY_DEADLINE_UNEXPECTED')
            if len(self._state['workers']) >= self.request.worker_count:
                raise ValueError('WORKER_SLOTS_FULL')
            worker = asdict(WorkerProjection(generation, WorkerState.AVAILABLE))
        self._emit('WORKER_REGISTERED', {'workers': {worker_id: worker}})
        return self.snapshot().workers[worker_id]

    @_locked
    def grant_lease(self, worker_id, *, generation, request_key=None):
        """Atomically reserve the next eligible point and debit one immutable slot."""
        self._tick()
        identity = {'worker_id': worker_id, 'generation': generation}
        duplicate = self._duplicate(request_key, 'LEASE_GRANTED', identity)
        if duplicate:
            lease = LeaseIdentity(**duplicate.payload['response'])
            self._active(lease)
            return lease
        if self._state['terminal_reason'] or not self._state['broker_healthy']:
            return None
        worker = self._worker(worker_id, generation)
        if (worker['state'] != 'AVAILABLE'
                or worker['lease_count'] >= self.request.max_points_per_worker):
            return None
        point_id = next((p for p in self.request.selected_point_ids
                         if not self._state['points'][p]['terminal']
                         and not self._state['points'][p]['active_attempt']
                         and not self._state['points'][p]['blocked_by']), None)
        if point_id is None:
            return None
        point = deepcopy(self._state['points'][point_id])
        now = self.clock()
        attempt = f'{point_id}-lease-{point["attempts"] + 1}'
        lease = LeaseIdentity(
            self.request.batch_id, self.journal.coordinator_epoch, worker_id, generation,
            point_id, attempt, point['attempts'] + 1, now,
            min(now + self.config.lease_duration_s, now + self.config.lease_ack_timeout_s,
                self._state['batch_deadline_monotonic_s']))
        roots = getattr(self.result_port, 'worker_roots', None)
        result_mode = getattr(self.result_port, 'run_mode', None)
        if (isinstance(roots, dict) and worker_id in roots
                and result_mode is self.request.run_mode):
            collection = ('attempts' if self.request.run_mode is RunMode.EXECUTE
                          else 'validations')
            workspace = Path(roots[worker_id]) / collection / point_id / attempt
        else:
            # Compatibility for abstract result ports used outside the production
            # composition. Production always supplies the exact WorkerRoot map.
            workspace = self.request.evidence_root / 'attempts' / attempt
        worker.update(lease=asdict(lease), lease_count=worker['lease_count'] + 1,
                      workspace=str(workspace),
                      heartbeat_deadline_monotonic_s=now + self.config.heartbeat_timeout_s)
        self._stage(worker, 'LEASED')
        point.update(active_attempt=attempt, attempts=point['attempts'] + 1)
        self._emit('LEASE_GRANTED', {'workers': {worker_id: worker}, 'points': {point_id: point}},
                   request_key=request_key, identity=identity, response=asdict(lease))
        return lease

    def _transition(self, lease, request_key, kind, expected, target, *, gate_summary=None):
        self._tick()
        identity = self._identity(lease)
        if gate_summary is not None:
            identity['gate_summary'] = gate_summary
        duplicate = self._duplicate(request_key, kind, identity)
        if duplicate:
            self._active(lease)
            return self.snapshot().workers[lease.worker_id]
        worker = self._active(lease)
        if worker['stop_requested']:
            raise ValueError('STOP_REQUESTED')
        if worker['state'] != expected:
            raise ValueError('WRONG_STAGE')
        self._stage(worker, target)
        self._renew(worker)
        self._emit(kind, {'workers': {lease.worker_id: worker}},
                   request_key=request_key, identity=identity)
        return self.snapshot().workers[lease.worker_id]

    @_locked
    def ack_lease(self, lease, *, request_key):
        """ACK the grant before the worker may reset or run its initial gate."""
        return self._transition(lease, request_key, 'LEASE_ACKNOWLEDGED', 'LEASED', 'INITIALIZING')

    @_locked
    def ack_attempt_started(self, lease, *, request_key, gate_summary=None):
        """Durably authorize physical execution only after the initial gate."""
        if self.request.run_mode != RunMode.EXECUTE:
            raise ValueError('WRONG_EXECUTION_MODE')
        return self._start_transition(
            lease, request_key, 'ATTEMPT_STARTED', gate_summary)

    @_locked
    def ack_validation_started(self, lease, *, request_key, gate_summary=None):
        """Durably authorize nonphysical validation in dry-run or plan-only."""
        if self.request.run_mode == RunMode.EXECUTE:
            raise ValueError('WRONG_EXECUTION_MODE')
        return self._start_transition(
            lease, request_key, 'VALIDATION_STARTED', gate_summary)

    @_locked
    def begin_finalizing(self, lease, *, request_key):
        """Enter finalization once, stopping further inference and physical actions."""
        return self._transition(
            lease, request_key, 'FINALIZING_STARTED', 'EXECUTING', 'FINALIZING')

    def _renew(self, worker):
        now = self.clock()
        lease = LeaseIdentity(**worker['lease'])
        deadline = min(now + self.config.lease_duration_s,
                       worker['stage_deadline_monotonic_s'],
                       self._state['batch_deadline_monotonic_s'])
        worker['lease'] = asdict(replace(lease, lease_deadline_monotonic_s=deadline))
        worker['heartbeat_deadline_monotonic_s'] = now + self.config.heartbeat_timeout_s

    @_locked
    def heartbeat(self, lease):
        """Renew within immutable phase/batch bounds; the returned value is the ACK."""
        self._tick()
        worker = self._active(lease)
        if worker["stop_requested"]:
            raise ValueError("STOP_REQUESTED")
        self._renew(worker)
        self._emit('LEASE_RENEWED', {'workers': {lease.worker_id: worker}})
        return LeaseIdentity(**worker['lease'])

    def _commit(self, lease, location, request_key, *, validation, discovered=False):
        kind = 'VALIDATION_COMMITTED' if validation else 'RESULT_COMMITTED'
        identity = {**self._identity(lease), 'location': str(location)}
        duplicate = self._duplicate(request_key, kind, identity)
        if duplicate:
            self._worker(lease.worker_id, lease.worker_generation)
            if lease.coordinator_epoch != self.journal.coordinator_epoch:
                raise ValueError('STALE_COORDINATOR_EPOCH')
            return deepcopy(duplicate.payload['response'])
        point = self._state['points'].get(lease.point_id)
        worker_state = self._state['workers'].get(lease.worker_id)
        if (point is None or point.get('active_attempt') != lease.attempt_id
                or worker_state is None or worker_state.get('lease') is None):
            self._audit_late_result(lease, location, kind)
            raise ValueError('LATE_RESULT_REJECTED')
        worker = self._active(lease, current_epoch=not discovered)
        result = self.result_port.verify(lease, str(location), self.request.run_mode)
        status = (ValidationStatus if validation else AttemptStatus)(result['status'])
        digest = result['sha256']
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('INVALID_SEAL_DIGEST')
        if worker['state'] not in ('EXECUTING', 'FINALIZING') and status not in (
                AttemptStatus.INVALID, ValidationStatus.VALIDATION_INVALID):
            raise ValueError('RESULT_BEFORE_STARTED')
        point = deepcopy(self._state['points'][lease.point_id])
        point['active_attempt'] = None
        if validation:
            point.update(validation_status=status, terminal=True)
        elif status == AttemptStatus.INVALID:
            point['blocked_by'] = lease.worker_id
            worker['invalid_point'] = lease.point_id
        else:
            point.update(status=status, terminal=True)
        worker['lease'] = None
        self._stage(worker, 'RECOVERING')
        response = {
            'status': status,
            'sha256': digest,
            'location': str(location),
            'recovery_deadline_monotonic_s': worker[
                'recovery_deadline_monotonic_s'],
        }
        self._emit(kind, {'points': {lease.point_id: point}, 'workers': {lease.worker_id: worker}},
                   request_key=request_key, identity=identity, response=response)
        self._evaluate()
        return response

    @_locked
    def commit_result(self, lease, sealed_location, *, request_key):
        """Commit a verifier-approved physical outcome; a journal commit wins expiry."""
        if self.request.run_mode != RunMode.EXECUTE:
            raise ValueError('WRONG_EXECUTION_MODE')
        return self._commit(lease, sealed_location, request_key, validation=False)

    @_locked
    def commit_validation(self, lease, sealed_location, *, request_key):
        """Commit separate validation evidence without promoting physical point status."""
        if self.request.run_mode == RunMode.EXECUTE:
            raise ValueError('WRONG_EXECUTION_MODE')
        return self._commit(lease, sealed_location, request_key, validation=True)

    def _expire(
            self, lease, *, force=False,
            start_authorized=_START_AUTHORIZATION_FROM_PROJECTION,
            allow_discovery=True):
        worker = self._active(lease, current_epoch=False)
        now = self.clock()
        deadline = min(worker['lease']['lease_deadline_monotonic_s'],
                       worker['stage_deadline_monotonic_s'],
                       worker['heartbeat_deadline_monotonic_s'],
                       self._state['batch_deadline_monotonic_s'])
        if not force and now < deadline:
            return False
        # The known workspace was journaled at grant. Scan it only while the
        # lease remains active in authoritative history, under this state lock.
        location = (self.result_port.discover(lease, Path(worker['workspace']))
                    if allow_discovery else None)
        if location is not None:
            try:
                self._commit(lease, location, None,
                             validation=self.request.run_mode != RunMode.EXECUTE,
                             discovered=True)
                return True
            except ValueError:
                # An invalid/unsealed artifact cannot suppress lease expiry.
                pass
        point = deepcopy(self._state['points'][lease.point_id])
        point['active_attempt'] = None
        if self.request.run_mode != RunMode.EXECUTE:
            point.update(validation_status=ValidationStatus.VALIDATION_INVALID, terminal=True)
        elif (start_authorized is True
              or (start_authorized is _START_AUTHORIZATION_FROM_PROJECTION
                  and worker['state'] in ('EXECUTING', 'FINALIZING'))):
            point.update(status=PointStatus.INDETERMINATE, terminal=True)
        elif start_authorized is None:
            # An unavailable proof is never optimistic, even when the replayed
            # projection happens to resemble a pre-start phase.
            point.update(status=PointStatus.INDETERMINATE, terminal=True)
        else:
            point['blocked_by'] = lease.worker_id
            worker['invalid_point'] = lease.point_id
        worker['lease'] = None
        self._stage(worker, 'RECOVERING')
        self._emit('LEASE_EXPIRED', {'points': {lease.point_id: point},
                                     'workers': {lease.worker_id: worker}},
                   identity=self._identity(lease))
        return True

    @_locked
    def expire_lease(self, lease):
        """Settle an expired lease after consulting registered sealed evidence."""
        # A previously journaled terminal result is stronger than a directory scan.
        point = self._state['points'].get(lease.point_id)
        if point and point['active_attempt'] != lease.attempt_id:
            return False
        changed = self._expire(lease)
        self._evaluate()
        return changed

    def _tick(self):
        now = self.clock()
        batch_due = now >= self._state['batch_deadline_monotonic_s']
        if (batch_due and not self._state['batch_cleanup_complete']
                and self._state['terminal_reason'] != 'BATCH_DEADLINE_EXCEEDED'):
            workers = deepcopy(self._state['workers'])
            for worker in workers.values():
                worker.update(stop_requested=True, action_allowed=False,
                              reset_allowed=False, inference_allowed=False)
            self._emit('BATCH_DEADLINE_EXCEEDED', {
                'terminal_reason': 'BATCH_DEADLINE_EXCEEDED', 'workers': workers})
        for worker_id in list(self._state['workers']):
            worker = deepcopy(self._state['workers'][worker_id])
            if worker['lease']:
                self._expire(LeaseIdentity(**worker['lease']), force=batch_due)
            elif worker['state'] == 'RECOVERING' and now >= worker['stage_deadline_monotonic_s']:
                worker.update(state='QUARANTINED', stop_requested=True)
                self._emit('RECOVERY_EXPIRED', {'workers': {worker_id: worker}})
        broker_deadline = self._state.get('broker_recovery_deadline_monotonic_s')
        if (not self._state['broker_healthy']
                and broker_deadline is not None
                and now >= broker_deadline
                and not self._state.get('broker_recovery_failed')):
            self._emit('BROKER_RECOVERY_EXPIRED', {
                'broker_recovery_failed': True,
            })
        self._evaluate()

    @_locked
    def tick(self):
        """Enforce missing heartbeat, phase, recovery and batch deadlines."""
        self._tick()
        return self.snapshot()

    def _evaluate(self):
        if self._state['terminal_reason']:
            return
        if (self._state.get('broker_recovery_failed')
                and not any(worker['lease'] for worker in self._state['workers'].values())):
            reason = 'SHARED_DEPENDENCY_UNAVAILABLE'
        elif all(p['terminal'] for p in self._state['points'].values()):
            reason = 'POINTS_COMPLETE'
        else:
            workers = self._state['workers']
            if any(w['lease'] for w in workers.values()):
                return
            capacity = len(self._state['workers']) < self.request.worker_count or any(
                w['state'] in ('AVAILABLE', 'RECOVERING')
                and w['lease_count'] < self.request.max_points_per_worker
                for w in workers.values())
            runnable = any(
                not p['terminal'] and (
                    not p['blocked_by'] or workers[p['blocked_by']]['state'] == 'RECOVERING')
                for p in self._state['points'].values())
            if capacity and runnable:
                return
            reason = 'CAPACITY_EXHAUSTED'
        self._emit('BATCH_STOPPING', {'terminal_reason': reason})

    @_locked
    def record_recovery(self, worker_id, *, generation, succeeded, fenced=False,
                        owned_processes_stopped=False, controllers_stopped=False,
                        readmitted=False, recovery_deadline_monotonic_s=None):
        """Re-admit capacity; INVALID needs all four explicit fencing/stop gates."""
        if any(type(value) is not bool for value in (
                succeeded, fenced, owned_processes_stopped, controllers_stopped, readmitted)):
            raise ValueError('BOOLEAN_RECOVERY_CONFIRMATIONS')
        self._tick()
        worker = self._worker(worker_id, generation)
        if worker['lease']:
            raise ValueError('ACTIVE_LEASE_REQUIRES_EXPIRY')
        if succeeded and worker['state'] != 'RECOVERING':
            raise ValueError('NOT_RECOVERING')
        self._check_recovery_deadline(
            worker, recovery_deadline_monotonic_s)
        point_id = worker['invalid_point']
        if succeeded and point_id and not all((
                fenced, owned_processes_stopped, controllers_stopped, readmitted)):
            raise ValueError('INVALID_REQUIRES_FENCING_AND_READMISSION')
        delta = {'workers': {worker_id: worker}}
        if succeeded:
            worker.update(
                state='AVAILABLE', stop_requested=False, invalid_point=None,
                recovery_deadline_monotonic_s=None)
            if point_id:
                point = deepcopy(self._state['points'][point_id])
                point['blocked_by'] = None
                delta['points'] = {point_id: point}
        else:
            worker.update(state='QUARANTINED', stop_requested=True)
        self._emit('WORKER_RECOVERED' if succeeded else 'WORKER_QUARANTINED', delta)
        self._evaluate()
        return self.snapshot().workers[worker_id]

    @_locked
    def mark_broker_health(self, healthy):
        """Pause new grants on broker failure without spending worker capacity."""
        if type(healthy) is not bool:
            raise ValueError('BOOLEAN_BROKER_HEALTH')
        self._tick()
        if healthy:
            deadline = self._state.get('broker_recovery_deadline_monotonic_s')
            if (self._state.get('broker_recovery_failed')
                    or (deadline is not None and self.clock() >= deadline)):
                raise ValueError('BROKER_RECOVERY_DEADLINE_EXCEEDED')
            if self._state['broker_healthy']:
                return self.snapshot()
            delta = {
                'broker_healthy': True,
                'broker_recovery_deadline_monotonic_s': None,
                'broker_recovery_failed': False,
            }
        else:
            if not self._state['broker_healthy']:
                return self.snapshot()
            now = self.clock()
            delta = {
                'broker_healthy': False,
                'broker_recovery_deadline_monotonic_s': min(
                    now + self.config.broker_recovery_timeout_s,
                    self._state['batch_deadline_monotonic_s'],
                ),
                'broker_recovery_failed': False,
            }
        self._emit('BROKER_HEALTH_CHANGED', delta)
        return self.snapshot()

    @_locked
    def request_stop(self, *, reason):
        """Fence every new lease/action while preserving active lease identity for recovery."""
        if not isinstance(reason, str) or not reason:
            raise ValueError('STOP_REASON_REQUIRED')
        if self._state['terminal_reason'] is not None:
            return self.snapshot()
        workers = deepcopy(self._state['workers'])
        for worker in workers.values():
            worker.update(
                stop_requested=True,
                action_allowed=False,
                reset_allowed=False,
                inference_allowed=False,
            )
        self._emit('BATCH_STOPPING', {
            'workers': workers,
            'terminal_reason': reason,
            'broker_healthy': False,
        })
        return self.snapshot()

    @_locked
    def complete_cleanup(self, *, owned_processes_stopped, controllers_stopped):
        """Finalize unstarted selections only after owned processes/controllers stop."""
        if any(type(value) is not bool for value in (
                owned_processes_stopped, controllers_stopped)):
            raise ValueError('BOOLEAN_CLEANUP_CONFIRMATIONS')
        self._tick()
        if not self._state['terminal_reason'] or not all((
                owned_processes_stopped, controllers_stopped)):
            raise ValueError('CLEANUP_NOT_CONFIRMED')
        if self._state['batch_cleanup_complete']:
            return self.snapshot()
        points, workers = deepcopy(self._state['points']), deepcopy(self._state['workers'])
        for point in points.values():
            if not point['terminal']:
                point.update(status='UNRUN', terminal=True, active_attempt=None)
        for worker in workers.values():
            worker.update(state='STOPPED', stop_requested=True, lease=None,
                          action_allowed=False, reset_allowed=False, inference_allowed=False)
        self._emit('BATCH_CLEANUP_COMPLETE', {
            'points': points, 'workers': workers, 'batch_cleanup_complete': True})
        return self.snapshot()

    @_locked
    def snapshot(self):
        """Return detached values; aggregate JSON is never read back as authority."""
        value = deepcopy(self._state)
        workers = {}
        for worker_id, worker in value['workers'].items():
            worker['state'] = WorkerState(worker['state'])
            if worker['lease']:
                worker['lease'] = LeaseIdentity(**worker['lease'])
            if worker['workspace']:
                worker['workspace'] = Path(worker['workspace'])
            workers[worker_id] = WorkerProjection(**worker)
        points = {}
        for point_id, point in value['points'].items():
            point['status'] = PointStatus(point['status'])
            if point['validation_status']:
                point['validation_status'] = ValidationStatus(point['validation_status'])
            points[point_id] = PointProjection(**point)
        summary = BatchSummary(
            self.request.run_mode, {p: v.status for p, v in points.items()},
            batch_terminal=all(point.terminal for point in points.values()),
            validation_statuses={p: v.validation_status for p, v in points.items()
                                 if v.validation_status is not None},
            batch_cleanup_complete=value['batch_cleanup_complete'])
        return CoordinatorSnapshot(
            workers, points, value['batch_started_monotonic_s'],
            value['batch_deadline_monotonic_s'], value['broker_healthy'],
            value.get('broker_recovery_deadline_monotonic_s'),
            value.get('broker_recovery_failed', False),
            value['terminal_reason'], value['batch_cleanup_complete'], summary)
