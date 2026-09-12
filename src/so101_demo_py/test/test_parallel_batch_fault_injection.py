"""Process-free fault contracts for shared dependencies and generation fencing."""

from pathlib import Path

import pytest

from so101_demo.parallel_batch.contracts import (
    BatchRequest,
    ExecutionKind,
    InferenceRequest,
    ModelOutcome,
    RunMode,
    load_parallel_runtime_config,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal


CONFIG = load_parallel_runtime_config(
    Path(__file__).resolve().parents[1] / "config/mujoco/parallel_batch_v1.yaml"
)
YOLO = CONFIG.yolo_model_id
GROUNDED = "grounded-sam"


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class NoResults:
    def verify(self, *_args):
        raise ValueError("no result")

    def discover(self, *_args):
        return None


def request(generation=1, request_id="request-1"):
    return InferenceRequest(
        request_id=request_id,
        model_id=YOLO,
        execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-broker",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=generation,
        point_id="p1",
        attempt_id="p1-attempt-1",
        lease_generation=1,
        reset_epoch="reset-1",
        image_timestamp_s=1.0,
        input_relative_path="workers/worker-01/input.npy",
        input_sha256="a" * 64,
    )


def make_coordinator(tmp_path, clock, points=("p1", "p2")):
    journal = CoordinatorJournal.create(tmp_path, "batch-broker")
    coordinator = BatchCoordinator(
        journal,
        BatchRequest(
            "batch-broker", RunMode.EXECUTE, points, 1, 2, tmp_path
        ),
        config=CONFIG,
        clock=clock,
        result_port=NoResults(),
    )
    coordinator.register_worker("worker-01", generation=1)
    return coordinator, journal


def gate_summary(lease):
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
        "reset_completed_monotonic_s": 101.0,
        "source_frame_monotonic_s": 102.0,
        "canonical_joints": True,
        "no_controller_goal": True,
        "no_attachment": True,
        "no_contact": True,
        "no_stale_node": True,
    }


def test_broker_crash_pauses_grants_without_spending_capacity_and_valid_recovery_resumes(
    tmp_path,
):
    """The first unhealthy edge freezes one deadline and leaves K untouched."""
    clock = Clock()
    coordinator, journal = make_coordinator(tmp_path, clock)
    try:
        coordinator.mark_broker_health(False)
        first = coordinator.snapshot()
        assert first.broker_healthy is False
        assert first.broker_recovery_deadline_monotonic_s == 190.0
        assert coordinator.grant_lease("worker-01", generation=1) is None
        assert coordinator.snapshot().workers["worker-01"].lease_count == 0
        clock.now = 150.0
        coordinator.mark_broker_health(False)
        assert coordinator.snapshot().broker_recovery_deadline_monotonic_s == 190.0
        coordinator.mark_broker_health(True)
        assert coordinator.snapshot().broker_recovery_deadline_monotonic_s is None
        assert coordinator.grant_lease("worker-01", generation=1).point_id == "p1"
    finally:
        journal.close()


def test_expired_broker_recovery_deadline_stops_with_shared_dependency_reason(tmp_path):
    """An unrecovered shared Broker failure has one explicit terminal reason."""
    clock = Clock()
    coordinator, journal = make_coordinator(tmp_path, clock)
    try:
        coordinator.mark_broker_health(False)
        clock.now = 190.0
        snapshot = coordinator.tick()
        assert snapshot.terminal_reason == "SHARED_DEPENDENCY_UNAVAILABLE"
        assert snapshot.broker_healthy is False
        assert coordinator.grant_lease("worker-01", generation=1) is None
        with pytest.raises(ValueError, match="BROKER_RECOVERY_DEADLINE"):
            coordinator.mark_broker_health(True)
        assert coordinator.snapshot().workers["worker-01"].lease_count == 0
    finally:
        journal.close()


def test_broker_deadline_waits_for_existing_lease_to_reach_a_terminal_boundary(tmp_path):
    """Shared failure does not rewrite an already leased attempt as a new grant."""
    clock = Clock()
    coordinator, journal = make_coordinator(tmp_path, clock)
    try:
        lease = coordinator.grant_lease("worker-01", generation=1)
        coordinator.ack_lease(lease, request_key="ack")
        coordinator.ack_attempt_started(
            lease, request_key="start", gate_summary=gate_summary(lease)
        )
        coordinator.mark_broker_health(False)
        for now in range(104, 190, 4):
            clock.now = float(now)
            lease = coordinator.heartbeat(lease)
        clock.now = 190.0
        snapshot = coordinator.tick()
        assert snapshot.workers["worker-01"].lease is not None
        assert snapshot.terminal_reason is None
        clock.now = lease.lease_deadline_monotonic_s
        snapshot = coordinator.tick()
        assert snapshot.terminal_reason == "SHARED_DEPENDENCY_UNAVAILABLE"
        assert snapshot.workers["worker-01"].lease_count == 1
    finally:
        journal.close()


def test_missed_broker_and_last_lease_deadlines_keep_shared_failure_reason(tmp_path):
    """One late tick must not let point completion hide the shared outage."""
    clock = Clock()
    coordinator, journal = make_coordinator(tmp_path, clock, points=("p1",))
    try:
        lease = coordinator.grant_lease("worker-01", generation=1)
        coordinator.ack_lease(lease, request_key="ack")
        coordinator.ack_attempt_started(
            lease, request_key="start", gate_summary=gate_summary(lease)
        )
        coordinator.mark_broker_health(False)
        for now in range(104, 190, 4):
            clock.now = float(now)
            coordinator.heartbeat(lease)
        clock.now = 194.0

        snapshot = coordinator.tick()

        assert snapshot.terminal_reason == "SHARED_DEPENDENCY_UNAVAILABLE"
        assert snapshot.workers["worker-01"].lease is None
    finally:
        journal.close()


@pytest.mark.parametrize("crash_phase", ["before", "after"])
def test_broker_restart_hook_never_allows_old_generation_result(crash_phase):
    """A restart boundary permanently fences old queued and cached responses."""
    from so101_demo.parallel_batch.broker import ModelResult, PerceptionBroker

    events = []

    def hook(boundary, phase):
        events.append((boundary, phase))

    clock = Clock()
    broker = PerceptionBroker(
        CONFIG,
        grounded_model_id=GROUNDED,
        authorize=lambda _request: True,
        clock=clock,
        fault_hook=hook,
    )
    broker.set_model_ready(YOLO, True)
    broker.set_model_ready(GROUNDED, True)
    old = request()
    assert broker.submit(old).accepted
    assert broker.next_ready_request() == old
    assert broker.complete(
        old, ModelResult(ModelOutcome.QUALIFIED, {"mask": [1]})
    ).candidate == {"mask": [1]}

    assert broker.restart() == 2
    broker.set_model_ready(YOLO, True)
    broker.set_model_ready(GROUNDED, True)
    stale = broker.poll_response(old)
    assert stale.outcome is ModelOutcome.CANCELLED
    assert stale.candidate is None
    assert ("BROKER_RESTART", crash_phase) in events
    assert broker.submit(request(generation=2, request_id="fresh")).accepted


def test_worker_fault_hook_is_optional_and_brackets_seal_and_recovery_receipt():
    """Tests may stop at a boundary without adding a production CLI switch."""
    from test_parallel_batch_worker import Fake
    from so101_demo.parallel_batch.worker import ParallelWorker

    observed = []
    fake = Fake(RunMode.EXECUTE)
    ports = fake.ports() | {
        "fault_hook": lambda boundary, phase: observed.append((boundary, phase))
    }

    result = ParallelWorker(ports).run_one()

    assert result.recovered is True
    assert observed == [
        ("RESULT_SEAL", "before"),
        ("RESULT_SEAL", "after"),
        ("RECOVERY_RECEIPT", "before"),
        ("RECOVERY_RECEIPT", "after"),
    ]


def test_worker_fault_after_local_seal_never_sends_terminal_commit():
    """A crash hook after publication cannot fabricate a coordinator ACK."""
    from test_parallel_batch_worker import Fake
    from so101_demo.parallel_batch.worker import ParallelWorker

    fake = Fake(RunMode.EXECUTE)

    def crash(boundary, phase):
        if (boundary, phase) == ("RESULT_SEAL", "after"):
            raise RuntimeError("injected post-seal crash")

    outcome = ParallelWorker(fake.ports() | {"fault_hook": crash}).run_one()

    assert outcome.recovered is False
    assert outcome.stopped_reason == "TERMINAL_ACK_FAILED"
    assert [call[0] for call in fake.results.calls] == ["seal_attempt"]
    assert not any(call[0] == "RESULT_COMMITTED" for call in fake.coordinator.calls)
