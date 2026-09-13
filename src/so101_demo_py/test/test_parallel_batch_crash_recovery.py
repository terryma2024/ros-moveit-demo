"""Crash-window recovery tests over the real append-only coordinator journal."""

import os
from dataclasses import asdict
from pathlib import Path

import pytest

from so101_demo.parallel_batch import artifacts
from so101_demo.parallel_batch.contracts import (
    AttemptIdentity,
    AttemptStatus,
    BatchRequest,
    PointStatus,
    RunMode,
    WorkerState,
    load_parallel_runtime_config,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal


CONFIG = load_parallel_runtime_config(
    Path(__file__).resolve().parents[1] / "config/mujoco/parallel_batch_v1.yaml"
)


class Clock:
    """Deterministic coordinator clock."""

    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


class InjectedCrash(RuntimeError):
    """Deterministic abrupt stop raised only from a dependency-injected hook."""


class CrashHook:
    """Arm one exact coordinator journal boundary after setup is durable."""

    def __init__(self):
        self.target = None

    def arm(self, boundary, phase):
        self.target = (boundary, phase)

    def __call__(self, boundary, phase):
        if self.target == (boundary, phase):
            self.target = None
            raise InjectedCrash(f"injected crash at {boundary}:{phase}")


class Results:
    """Real coordinator port with explicit working/sealed publication states."""

    def __init__(self):
        self.working = {}
        self.sealed = {}

    def write_working(self, lease, status=AttemptStatus.PASSED):
        location = f"/{lease.worker_id}/{lease.attempt_id}/sealed"
        self.working[location] = (lease.attempt_id, status)
        return location

    def publish(self, location):
        self.sealed[location] = self.working.pop(location)

    def verify(self, lease, location, run_mode):
        assert run_mode is RunMode.EXECUTE
        value = self.sealed.get(str(location))
        if value is None or value[0] != lease.attempt_id:
            raise ValueError("unverified seal")
        return {"status": value[1], "sha256": "d" * 64}

    def discover(self, lease, workspace):
        location = f"/{lease.worker_id}/{lease.attempt_id}/sealed"
        return location if location in self.sealed else None


def gate_summary(lease):
    """Return a literal valid start proof independent of coordinator helpers."""
    return {
        "schema_version": 1,
        "kind": "POINT_INITIAL_GATE",
        "batch_id": lease.batch_id,
        "coordinator_epoch": lease.coordinator_epoch,
        "worker_id": lease.worker_id,
        "worker_generation": lease.worker_generation,
        "point_id": lease.point_id,
        "attempt_id": lease.attempt_id,
        "lease_generation": lease.lease_generation,
        "reset_epoch": "reset-1",
        "simulation_session_id": "session-1",
        "reset_completed_monotonic_s": 11.0,
        "source_frame_monotonic_s": 12.0,
        "canonical_joints": True,
        "no_controller_goal": True,
        "no_attachment": True,
        "no_contact": True,
        "no_stale_node": True,
    }


class Harness:
    def __init__(self, root):
        self.root = root
        self.clock = Clock()
        self.results = Results()
        self.crash_hook = CrashHook()
        self.request = BatchRequest(
            "batch-crash", RunMode.EXECUTE, ("p1", "p2"), 1, 4, root
        )
        self.journal = CoordinatorJournal.create(root, self.request.batch_id)
        self.coordinator = BatchCoordinator(
            self.journal,
            self.request,
            config=CONFIG,
            clock=self.clock,
            result_port=self.results,
            fault_hook=self.crash_hook,
        )
        self.coordinator.register_worker("worker-01", generation=1)

    def grant(self):
        return self.coordinator.grant_lease(
            "worker-01", generation=1, request_key="grant-p1"
        )

    def acknowledge(self, lease):
        self.coordinator.ack_lease(lease, request_key="ack-p1")

    def start(self, lease):
        self.acknowledge(lease)
        self.coordinator.ack_attempt_started(
            lease, request_key="start-p1", gate_summary=gate_summary(lease)
        )

    def restart(self, *, start_authorization=None):
        self.journal.close()
        self.journal = CoordinatorJournal.create(self.root, self.request.batch_id)
        kwargs = {}
        if start_authorization is not None:
            kwargs["recovery_start_authorization"] = start_authorization
        self.coordinator = BatchCoordinator(
            self.journal,
            self.request,
            config=CONFIG,
            clock=self.clock,
            result_port=self.results,
            **kwargs,
        )
        return self.coordinator

    def close(self):
        self.journal.close()


@pytest.fixture
def harness(tmp_path):
    value = Harness(tmp_path)
    yield value
    value.close()


@pytest.mark.parametrize(
    "boundary,phase,expected_status,expected_event_count,expected_k",
    [
        ("LEASE_GRANTED", "before_fsync", PointStatus.UNRUN, 0, 0),
        ("LEASE_GRANTED", "after_fsync", PointStatus.UNRUN, 1, 1),
        ("LEASE_GRANTED", "before_ack", PointStatus.UNRUN, 1, 1),
        ("ATTEMPT_STARTED", "before_fsync", PointStatus.UNRUN, 0, 1),
        ("ATTEMPT_STARTED", "after_fsync", PointStatus.INDETERMINATE, 1, 1),
        ("ATTEMPT_STARTED", "before_ack", PointStatus.INDETERMINATE, 1, 1),
        ("RESULT_COMMITTED", "before_fsync", PointStatus.PASSED, 1, 1),
        ("RESULT_COMMITTED", "after_fsync", PointStatus.PASSED, 1, 1),
        ("RESULT_COMMITTED", "before_ack", PointStatus.PASSED, 1, 1),
        ("LEASE_EXPIRED", "before_fsync", PointStatus.INDETERMINATE, 1, 1),
        ("LEASE_EXPIRED", "after_fsync", PointStatus.INDETERMINATE, 1, 1),
        ("LEASE_EXPIRED", "before_ack", PointStatus.INDETERMINATE, 1, 1),
    ],
)
def test_real_journal_fault_hook_replays_the_exact_durable_prefix(
    harness, boundary, phase, expected_status, expected_event_count, expected_k
):
    """Every journal fsync/ACK edge is interrupted, closed, and replayed."""
    lease = None
    if boundary != "LEASE_GRANTED":
        lease = harness.grant()
    if boundary in {"ATTEMPT_STARTED", "RESULT_COMMITTED", "LEASE_EXPIRED"}:
        harness.acknowledge(lease)
    if boundary in {"RESULT_COMMITTED", "LEASE_EXPIRED"}:
        harness.coordinator.ack_attempt_started(
            lease, request_key="start-p1", gate_summary=gate_summary(lease)
        )
    location = None
    if boundary == "RESULT_COMMITTED":
        location = harness.results.write_working(lease)
        harness.results.publish(location)
    if boundary == "LEASE_EXPIRED":
        harness.clock.now = 15.0

    harness.crash_hook.arm(boundary, phase)
    with pytest.raises(RuntimeError, match="injected crash"):
        if boundary == "LEASE_GRANTED":
            harness.grant()
        elif boundary == "ATTEMPT_STARTED":
            harness.coordinator.ack_attempt_started(
                lease, request_key="start-p1", gate_summary=gate_summary(lease)
            )
        elif boundary == "RESULT_COMMITTED":
            harness.coordinator.commit_result(
                lease, location, request_key="result-p1"
            )
        else:
            harness.coordinator.expire_lease(lease)

    recovered = harness.restart()
    snapshot = recovered.snapshot()
    assert snapshot.points["p1"].status is expected_status
    assert snapshot.workers["worker-01"].lease_count == expected_k
    assert sum(
        event.type == boundary for event in harness.journal.replay().events
    ) == expected_event_count


def _attempt_identity(lease):
    return AttemptIdentity(
        lease.batch_id,
        lease.coordinator_epoch,
        lease.worker_id,
        lease.worker_generation,
        lease.point_id,
        lease.attempt_id,
        lease.lease_generation,
    )


@pytest.mark.parametrize(
    "boundary,phase,sealed_visible,expected_status",
    [
        ("WORKING_TREE_FSYNC", "before", False, PointStatus.INDETERMINATE),
        ("WORKING_TREE_FSYNC", "after", False, PointStatus.INDETERMINATE),
        ("ATOMIC_SEAL", "before", False, PointStatus.INDETERMINATE),
        ("ATOMIC_SEAL", "after", True, PointStatus.UNRUN),
    ],
)
def test_real_artifact_crash_is_adjudicated_from_fsync_and_seal_state(
    tmp_path, boundary, phase, sealed_visible, expected_status
):
    """Coordinator restart consumes real immutable artifact publication state."""
    clock = Clock()
    worker_root = tmp_path / "workers/worker-01"
    result_port = artifacts.SealedResultAdapter(
        {"worker-01": worker_root}, RunMode.EXECUTE
    )
    request = BatchRequest(
        "batch-real-seal", RunMode.EXECUTE, ("p1",), 1, 1, tmp_path
    )
    journal = CoordinatorJournal.create(tmp_path, request.batch_id)
    coordinator = BatchCoordinator(
        journal, request, config=CONFIG, clock=clock, result_port=result_port
    )
    coordinator.register_worker("worker-01", generation=1)
    lease = coordinator.grant_lease("worker-01", generation=1)
    coordinator.ack_lease(lease, request_key="ack")
    coordinator.ack_attempt_started(
        lease, request_key="start", gate_summary=gate_summary(lease)
    )
    work = artifacts.AttemptWorkspace.create(
        worker_root,
        _attempt_identity(lease),
        reset_epoch="reset-1",
        source_stamp={"source": "real-crash-matrix"},
        run_mode=RunMode.EXECUTE,
    )
    # This matrix exercises publication crash windows, not physical success.
    # INVALID is a complete reset-stage outcome and therefore needs no forged
    # execution evidence under the verifier-owned evidence contract.
    work.write_json("attempt-result.json", {"status": "INVALID"})

    def crash(observed_boundary, observed_phase):
        if (observed_boundary, observed_phase) == (boundary, phase):
            raise RuntimeError("injected artifact crash")

    with pytest.raises(RuntimeError, match="injected artifact crash"):
        work.seal(fault_hook=crash)
    sealed = work.path.parent / "sealed"
    assert sealed.exists() is sealed_visible
    journal.close()

    with CoordinatorJournal.create(tmp_path, request.batch_id) as recovered_journal:
        recovered = BatchCoordinator(
            recovered_journal,
            request,
            config=CONFIG,
            clock=clock,
            result_port=result_port,
        )
        snapshot = recovered.snapshot()
        assert snapshot.points["p1"].status is expected_status
        assert snapshot.workers["worker-01"].lease_count == 1
        assert sum(
            event.type == "RESULT_COMMITTED"
            for event in recovered_journal.replay().events
        ) == (1 if sealed_visible else 0)


def test_real_prestart_late_seal_is_terminal_and_cannot_be_released_for_retry(
        tmp_path):
    """A real seal appearing after expiry permanently consumes the old point."""
    clock = Clock()
    worker_root = tmp_path / "workers/worker-01"
    result_port = artifacts.SealedResultAdapter(
        {"worker-01": worker_root}, RunMode.EXECUTE
    )
    request = BatchRequest(
        "batch-real-late", RunMode.EXECUTE, ("p1", "p2"), 1, 2, tmp_path
    )
    journal = CoordinatorJournal.create(tmp_path, request.batch_id)
    coordinator = BatchCoordinator(
        journal, request, config=CONFIG, clock=clock, result_port=result_port
    )
    coordinator.register_worker("worker-01", generation=1)
    lease = coordinator.grant_lease("worker-01", generation=1)
    coordinator.ack_lease(lease, request_key="ack")
    clock.now = 15.0
    assert coordinator.expire_lease(lease) is True
    work = artifacts.AttemptWorkspace.create(
        worker_root,
        _attempt_identity(lease),
        reset_epoch="reset-1",
        source_stamp={"source": "late-real-seal"},
        run_mode=RunMode.EXECUTE,
    )
    work.write_json("attempt-result.json", {"status": "INVALID"})
    work.seal()
    journal.close()

    with CoordinatorJournal.create(tmp_path, request.batch_id) as recovered_journal:
        recovered = BatchCoordinator(
            recovered_journal,
            request,
            config=CONFIG,
            clock=clock,
            result_port=result_port,
        )
        first = recovered.snapshot().points["p1"]
        assert first.status is PointStatus.INDETERMINATE
        assert first.terminal is True
        assert first.blocked_by is None
        worker = recovered.snapshot().workers["worker-01"]
        recovered.register_worker(
            "worker-01",
            generation=2,
            recovery_deadline_monotonic_s=worker.recovery_deadline_monotonic_s,
        )
        recovered.record_recovery(
            "worker-01",
            generation=2,
            succeeded=True,
            fenced=True,
            owned_processes_stopped=True,
            controllers_stopped=True,
            readmitted=True,
            recovery_deadline_monotonic_s=worker.recovery_deadline_monotonic_s,
        )
        retry = recovered.grant_lease("worker-01", generation=2)
        assert retry.point_id == "p2"
        assert retry.attempt_id != lease.attempt_id
        assert sum(
            event.type == "LATE_RESULT_REJECTED"
            for event in recovered_journal.replay().events
        ) == 1


@pytest.mark.parametrize(
    "window,prepare,expected_status,expected_blocked,expected_events",
    [
        (
            "grant_is_durable",
            lambda h, lease: None,
            PointStatus.UNRUN,
            "worker-01",
            {"LEASE_GRANTED", "LEASE_EXPIRED"},
        ),
        (
            "lease_ack_is_durable",
            lambda h, lease: h.acknowledge(lease),
            PointStatus.UNRUN,
            "worker-01",
            {"LEASE_GRANTED", "LEASE_ACKNOWLEDGED", "LEASE_EXPIRED"},
        ),
        (
            "start_is_durable",
            lambda h, lease: h.start(lease),
            PointStatus.INDETERMINATE,
            None,
            {"ATTEMPT_STARTED", "LEASE_EXPIRED"},
        ),
        (
            "unsealed_working_state_exists",
            lambda h, lease: (h.start(lease), h.results.write_working(lease)),
            PointStatus.INDETERMINATE,
            None,
            {"ATTEMPT_STARTED", "LEASE_EXPIRED"},
        ),
    ],
)
def test_restart_adjudicates_each_precommit_durable_state_once(
    harness, window, prepare, expected_status, expected_blocked, expected_events
):
    """An old epoch cannot retain or optimistically recycle an uncertain lease."""
    lease = harness.grant()
    prepare(harness, lease)

    recovered = harness.restart()

    snapshot = recovered.snapshot()
    assert snapshot.points["p1"].status is expected_status, window
    assert snapshot.points["p1"].blocked_by == expected_blocked, window
    assert snapshot.workers["worker-01"].lease is None, window
    assert snapshot.workers["worker-01"].lease_count == 1, window
    assert snapshot.workers["worker-01"].state is WorkerState.RECOVERING, window
    names = {event.type for event in harness.journal.replay().events}
    assert expected_events <= names, window


@pytest.mark.parametrize(
    "window,publish,commit",
    [
        ("sealed_without_result_event", True, False),
        ("result_event_is_durable", True, True),
    ],
)
def test_restart_admits_one_first_seal_and_never_recommits(
    harness, window, publish, commit
):
    """A durable seal or result event wins exactly once across restart windows."""
    lease = harness.grant()
    harness.start(lease)
    location = harness.results.write_working(lease)
    if publish:
        harness.results.publish(location)
    if commit:
        harness.coordinator.commit_result(lease, location, request_key="result-p1")
    before = sum(
        event.type == "RESULT_COMMITTED" for event in harness.journal.replay().events
    )

    recovered = harness.restart()

    snapshot = recovered.snapshot()
    assert snapshot.points["p1"].status is PointStatus.PASSED, window
    assert snapshot.workers["worker-01"].lease_count == 1, window
    assert snapshot.workers["worker-01"].lease is None, window
    committed = [
        event for event in harness.journal.replay().events
        if event.type == "RESULT_COMMITTED"
    ]
    assert len(committed) == max(1, before), window
    assert committed[0].payload["response"]["status"] == AttemptStatus.PASSED.value


def test_expired_then_late_seal_then_restart_is_never_accepted(harness):
    """A seal published after durable expiry is audit-only and stays indeterminate."""
    lease = harness.grant()
    harness.start(lease)
    harness.clock.now = 15.0
    assert harness.coordinator.expire_lease(lease) is True
    location = harness.results.write_working(lease)
    harness.results.publish(location)

    recovered = harness.restart()

    assert recovered.snapshot().points["p1"].status is PointStatus.INDETERMINATE
    names = [event.type for event in harness.journal.replay().events]
    assert names.count("LEASE_EXPIRED") == 1
    assert names.count("LATE_RESULT_REJECTED") == 1
    assert "RESULT_COMMITTED" not in names


def test_prestart_expiry_then_late_seal_becomes_indeterminate_and_never_requeues(
    harness,
):
    """A post-expiry seal is uncertain even when START was not yet durable."""
    lease = harness.grant()
    harness.acknowledge(lease)
    harness.clock.now = 15.0
    assert harness.coordinator.expire_lease(lease) is True
    location = harness.results.write_working(lease)
    harness.results.publish(location)

    recovered = harness.restart()

    point = recovered.snapshot().points["p1"]
    assert point.status is PointStatus.INDETERMINATE
    assert point.terminal is True
    assert point.blocked_by is None
    worker = recovered.snapshot().workers["worker-01"]
    recovered.register_worker(
        "worker-01",
        generation=2,
        recovery_deadline_monotonic_s=worker.recovery_deadline_monotonic_s,
    )
    recovered.record_recovery(
        "worker-01",
        generation=2,
        succeeded=True,
        fenced=True,
        owned_processes_stopped=True,
        controllers_stopped=True,
        readmitted=True,
        recovery_deadline_monotonic_s=worker.recovery_deadline_monotonic_s,
    )
    retry = recovered.grant_lease("worker-01", generation=2)
    assert retry.point_id == "p2"
    assert recovered.snapshot().workers["worker-01"].lease_count == 2


def test_old_prestart_seal_fences_a_newer_active_retry_for_the_same_point(harness):
    """A late old seal cannot coexist with a newly authorized retry."""
    expired = harness.grant()
    harness.acknowledge(expired)
    harness.clock.now = 15.0
    assert harness.coordinator.expire_lease(expired) is True
    worker = harness.coordinator.snapshot().workers["worker-01"]
    harness.coordinator.register_worker(
        "worker-01",
        generation=2,
        recovery_deadline_monotonic_s=worker.recovery_deadline_monotonic_s,
    )
    harness.coordinator.record_recovery(
        "worker-01",
        generation=2,
        succeeded=True,
        fenced=True,
        owned_processes_stopped=True,
        controllers_stopped=True,
        readmitted=True,
        recovery_deadline_monotonic_s=worker.recovery_deadline_monotonic_s,
    )
    retry = harness.coordinator.grant_lease("worker-01", generation=2)
    assert retry.point_id == expired.point_id
    location = harness.results.write_working(expired)
    harness.results.publish(location)

    with pytest.raises(ValueError, match="LATE_RESULT_REJECTED"):
        harness.coordinator.commit_result(
            expired, location, request_key="late-old-seal-during-retry"
        )

    snapshot = harness.coordinator.snapshot()
    point = snapshot.points[expired.point_id]
    assert point.status is PointStatus.INDETERMINATE
    assert point.terminal is True
    assert point.active_attempt is None
    assert point.blocked_by is None
    current = snapshot.workers["worker-01"]
    assert current.state is WorkerState.RECOVERING
    assert current.lease is None
    assert current.lease_count == 2
    assert harness.coordinator.grant_lease("worker-01", generation=2) is None
    harness.coordinator.register_worker(
        "worker-01",
        generation=3,
        recovery_deadline_monotonic_s=current.recovery_deadline_monotonic_s,
    )
    harness.coordinator.record_recovery(
        "worker-01",
        generation=3,
        succeeded=True,
        fenced=True,
        owned_processes_stopped=True,
        controllers_stopped=True,
        readmitted=True,
        recovery_deadline_monotonic_s=current.recovery_deadline_monotonic_s,
    )
    following = harness.coordinator.grant_lease("worker-01", generation=3)
    assert following.point_id == "p2"
    assert harness.coordinator.snapshot().workers["worker-01"].lease_count == 3
    assert sum(
        event.type == "LEASE_GRANTED" for event in harness.journal.replay().events
    ) == 3


def test_repeated_late_result_submission_replays_one_rejection(harness):
    """A retry after expiry cannot change the audit trail or failure class."""
    lease = harness.grant()
    harness.start(lease)
    harness.clock.now = 15.0
    assert harness.coordinator.expire_lease(lease) is True
    location = harness.results.write_working(lease)
    harness.results.publish(location)
    for _ in range(2):
        with pytest.raises(ValueError, match="LATE_RESULT_REJECTED"):
            harness.coordinator.commit_result(
                lease, location, request_key="late-result"
            )
    assert sum(
        event.type == "LATE_RESULT_REJECTED"
        for event in harness.journal.replay().events
    ) == 1


def test_restart_requeues_only_when_trusted_journal_proves_start_absent(harness):
    """No durable START permits INVALID recovery, but K remains spent."""
    lease = harness.grant()
    harness.acknowledge(lease)
    recovered = harness.restart()
    worker = recovered.snapshot().workers["worker-01"]
    deadline = worker.recovery_deadline_monotonic_s
    recovered.register_worker(
        "worker-01", generation=2, recovery_deadline_monotonic_s=deadline
    )
    recovered.record_recovery(
        "worker-01",
        generation=2,
        succeeded=True,
        fenced=True,
        owned_processes_stopped=True,
        controllers_stopped=True,
        readmitted=True,
        recovery_deadline_monotonic_s=deadline,
    )

    retry = recovered.grant_lease(
        "worker-01", generation=2, request_key="retry-p1"
    )
    assert retry.point_id == "p1"
    assert retry.attempt_id != lease.attempt_id
    assert recovered.snapshot().workers["worker-01"].lease_count == 2


def test_unknown_start_authorization_is_indeterminate_and_never_requeued(harness):
    """An injected unavailable proof must choose the conservative terminal result."""
    lease = harness.grant()
    harness.acknowledge(lease)

    recovered = harness.restart(start_authorization=lambda _lease, _events: None)

    point = recovered.snapshot().points["p1"]
    assert point.status is PointStatus.INDETERMINATE
    assert point.terminal is True
    assert point.blocked_by is None
    assert recovered.snapshot().workers["worker-01"].lease_count == 1


def test_durable_start_cannot_be_downgraded_by_an_injected_recovery_proof(harness):
    """A test port may make facts less certain, never erase a durable START."""
    lease = harness.grant()
    harness.start(lease)

    recovered = harness.restart(
        start_authorization=lambda _lease, _events: False
    )

    point = recovered.snapshot().points["p1"]
    assert point.status is PointStatus.INDETERMINATE
    assert point.terminal is True
    assert point.blocked_by is None


def test_committed_result_has_priority_over_mutable_directory_after_restart(harness):
    """Changing a directory fixture cannot overwrite the first journaled result."""
    lease = harness.grant()
    harness.start(lease)
    location = harness.results.write_working(lease, AttemptStatus.FAILED)
    harness.results.publish(location)
    harness.coordinator.commit_result(lease, location, request_key="result-p1")
    harness.results.sealed[location] = (lease.attempt_id, AttemptStatus.PASSED)

    recovered = harness.restart()

    assert recovered.snapshot().points["p1"].status is PointStatus.FAILED
    assert sum(
        event.type == "RESULT_COMMITTED" for event in harness.journal.replay().events
    ) == 1


def test_coordinator_fault_hook_brackets_durable_events_without_becoming_authority(
    tmp_path,
):
    """The injected hook observes boundaries; journal state still owns recovery."""
    observed = []
    request = BatchRequest(
        "batch-hook", RunMode.EXECUTE, ("p1",), 1, 1, tmp_path
    )
    results = Results()
    with CoordinatorJournal.create(tmp_path, request.batch_id) as journal:
        coordinator = BatchCoordinator(
            journal,
            request,
            config=CONFIG,
            clock=Clock(),
            result_port=results,
            fault_hook=lambda boundary, phase: observed.append((boundary, phase)),
        )
        coordinator.register_worker("worker-01", generation=1)
        lease = coordinator.grant_lease("worker-01", generation=1)
        coordinator.ack_lease(lease, request_key="ack")
        coordinator.ack_attempt_started(
            lease, request_key="start", gate_summary=gate_summary(lease)
        )
    assert ("LEASE_GRANTED", "before_fsync") in observed
    assert ("LEASE_GRANTED", "after_fsync") in observed
    assert ("LEASE_GRANTED", "before_ack") in observed
    assert ("ATTEMPT_STARTED", "before_fsync") in observed
    assert ("ATTEMPT_STARTED", "after_fsync") in observed
    assert ("ATTEMPT_STARTED", "before_ack") in observed


def test_fault_hook_crash_after_fsync_replays_one_k_debit(tmp_path):
    """A hook exception after durable grant cannot erase or duplicate its debit."""
    fired = False

    def crash(boundary, phase):
        nonlocal fired
        if not fired and (boundary, phase) == ("LEASE_GRANTED", "after_fsync"):
            fired = True
            raise RuntimeError("injected crash")

    request = BatchRequest(
        "batch-after-fsync", RunMode.EXECUTE, ("p1",), 1, 2, tmp_path
    )
    results = Results()
    journal = CoordinatorJournal.create(tmp_path, request.batch_id)
    coordinator = BatchCoordinator(
        journal,
        request,
        config=CONFIG,
        clock=Clock(),
        result_port=results,
        fault_hook=crash,
    )
    coordinator.register_worker("worker-01", generation=1)
    with pytest.raises(RuntimeError, match="injected crash"):
        coordinator.grant_lease(
            "worker-01", generation=1, request_key="grant-p1"
        )
    journal.close()

    with CoordinatorJournal.create(tmp_path, request.batch_id) as restarted_journal:
        restarted = BatchCoordinator(
            restarted_journal,
            request,
            config=CONFIG,
            clock=Clock(),
            result_port=results,
        )
        assert restarted.snapshot().workers["worker-01"].lease_count == 1
        assert sum(
            event.type == "LEASE_GRANTED"
            for event in restarted_journal.replay().events
        ) == 1
