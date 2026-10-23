"""Lease and attempt acknowledgements, the point gate, the watchdog and coordinator loss."""

from dataclasses import replace
import threading
import time

from parallel_batch_worker_support import CONFIG, Decision, Fake, event_names
import pytest

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    ExecutionKind,
    RunMode,
)
from so101_demo.parallel_batch.worker import ParallelWorker


def test_worker_waits_for_lease_ack_before_reset_or_point_inspection():
    fake = Fake()
    fake.coordinator.withhold_lease_ack = True
    ParallelWorker(fake.ports()).run_one()
    assert fake.runtime.calls == ["worker_ready_gate"]
    assert fake.runtime.ready_args == [()]
    assert fake.broker.calls == []


def test_worker_waits_for_attempt_ack_before_perception_or_motion():
    fake = Fake()
    fake.coordinator.withhold_start_ack = True
    ParallelWorker(fake.ports()).run_one()
    assert fake.runtime.calls == [
        "worker_ready_gate", "reset_point", "point_initial_gate",
    ]
    assert "request_model" not in fake.runtime.calls
    assert "submit_motion" not in fake.runtime.calls


@pytest.mark.parametrize(
    "mode,coordinator_events,runtime_calls,terminal",
    [
        (
            RunMode.EXECUTE,
            ["register_worker", "LEASE_REQUEST", "LEASE_GRANTED", "ATTEMPT_STARTED",
             "FINALIZING_STARTED", "RESULT_COMMITTED", "register_worker", "RECOVERY"],
            ["worker_ready_gate", "reset_point", "point_initial_gate", "inference_snapshot", "pose_admission",
             "submit_motion", "cancel_motion", "confirm_no_controller_goal", "recover",
             "worker_ready_gate"],
            "seal_attempt",
        ),
        (
            RunMode.PLAN_ONLY,
            ["register_worker", "LEASE_REQUEST", "LEASE_GRANTED", "VALIDATION_STARTED",
             "FINALIZING_STARTED", "VALIDATION_COMMITTED", "register_worker", "RECOVERY"],
            ["worker_ready_gate", "reset_point", "point_initial_gate", "inference_snapshot", "pose_admission",
             "submit_plan", "cancel_motion", "confirm_no_controller_goal", "recover",
             "worker_ready_gate"],
            "seal_validation",
        ),
        (
            RunMode.DRY_RUN,
            ["register_worker", "LEASE_REQUEST", "LEASE_GRANTED", "VALIDATION_STARTED",
             "FINALIZING_STARTED", "VALIDATION_COMMITTED", "register_worker", "RECOVERY"],
            ["worker_ready_gate", "scheduler_trace", "cancel_motion",
             "confirm_no_controller_goal", "recover", "worker_ready_gate"],
            "seal_validation",
        ),
    ],
)
def test_modes_have_distinct_authorization_and_terminal_paths(
        mode, coordinator_events, runtime_calls, terminal):
    fake = Fake(mode)
    ParallelWorker(fake.ports()).run_one()
    assert event_names(fake) == coordinator_events
    assert fake.runtime.calls == runtime_calls
    assert fake.results.calls[0][0] == terminal
    assert fake.runtime.physical_starts == (mode is not RunMode.DRY_RUN)
    assert ("submit_motion" in fake.runtime.calls) == (mode is RunMode.EXECUTE)
    if mode is not RunMode.EXECUTE:
        assert all(call[1] is ExecutionKind.VALIDATION for call in fake.broker.calls
                   if call[0] == "request_model")


def test_point_gate_binds_exact_reset_and_fresh_source_frame():
    fake = Fake(RunMode.PLAN_ONLY)
    ParallelWorker(fake.ports()).run_one()
    assert fake.runtime.ready_args == [(), ()]
    assert fake.runtime.chain.chain_id == "yolo-to-expert"


@pytest.mark.parametrize(
    "mode,event_id,event_type,execution_kind",
    [
        (
            RunMode.EXECUTE,
            "attempt-start-p1-lease-1",
            "ATTEMPT_STARTED",
            ExecutionKind.ATTEMPT,
        ),
        (
            RunMode.PLAN_ONLY,
            "validation-start-p1-lease-1",
            "VALIDATION_STARTED",
            ExecutionKind.VALIDATION,
        ),
    ],
)
def test_broker_receives_post_reset_snapshot_and_exact_committed_start_identity(
    mode, event_id, event_type, execution_kind
):
    fake = Fake(mode)

    ParallelWorker(fake.ports()).run_one()

    request = next(call for call in fake.broker.calls if call[0] == "request_model")
    assert request == (
        "request_model",
        execution_kind,
        1,
        fake.runtime.snapshot,
        event_id,
        event_type,
        "reset-1",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"point_id": "other"}, {"canonical_joints": False},
        {"no_controller_goal": False}, {"no_attachment": False},
        {"no_contact": False}, {"no_stale_node": False},
        {"reset_epoch": "old"}, {"simulation_session_id": "old"},
        {"source_frame_monotonic_s": 20.0},
    ],
)
def test_invalid_point_gate_never_reaches_model_or_motion(mutation):
    fake = Fake()
    original = fake.runtime.point_initial_gate

    def bad_gate(lease, reset):
        return replace(original(lease, reset), **mutation)

    fake.runtime.point_initial_gate = bad_gate
    ParallelWorker(fake.ports()).run_one()
    assert all(call[0] != "request_model" for call in fake.broker.calls)
    assert "submit_motion" not in fake.runtime.calls


def test_watchdog_heartbeats_while_model_call_is_blocked():
    fake = Fake(RunMode.PLAN_ONLY)
    release = threading.Event()
    fake.broker.block = release
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one)
    thread.start()
    assert fake.broker.entered.wait(1)
    before = sum(c[0] == "HEARTBEAT" for c in fake.coordinator.calls)
    time.sleep(CONFIG.heartbeat_interval_s + 0.1)
    after = sum(c[0] == "HEARTBEAT" for c in fake.coordinator.calls)
    release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert after > before


def test_missing_heartbeat_ack_uses_frozen_bound_and_stops_after_block():
    fake = Fake(RunMode.PLAN_ONLY)
    release_model = threading.Event()
    release_heartbeat = threading.Event()
    fake.broker.block = release_model
    fake.coordinator.block_watchdog_heartbeat = release_heartbeat
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one)
    thread.start()
    assert fake.broker.entered.wait(1)
    assert fake.coordinator.heartbeat_entered.wait(1)
    fake.clock.now += CONFIG.heartbeat_timeout_s - 0.1
    time.sleep(0.03)
    assert "pose_admission" not in fake.runtime.calls
    fake.clock.now += 0.1
    time.sleep(0.03)
    release_model.set()
    release_heartbeat.set()
    thread.join(2)
    assert not thread.is_alive()
    assert "pose_admission" not in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls


def _expert_blocked_with_a_lost_coordinator(fake):
    """An EXECUTE run whose Teacher child is blocked inside execute_expert while the Coordinator goes silent."""
    entered, release = threading.Event(), threading.Event()
    original_execute = fake.runtime.execute_expert
    original_heartbeat = fake.coordinator.heartbeat

    def blocked_execute(*args, **kwargs):
        entered.set()
        assert release.wait(5.0)
        return original_execute(*args, **kwargs)

    def lose_watchdog_heartbeat(lease):
        if (threading.current_thread().name.startswith("parallel-worker-heartbeat-rpc-")
                and entered.is_set()):
            raise RuntimeError("coordinator lost during expert execution")
        return original_heartbeat(lease)

    fake.runtime.execute_expert = blocked_execute
    fake.coordinator.heartbeat = lose_watchdog_heartbeat
    worker = ParallelWorker(fake.ports())
    result = []
    thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    thread.start()
    assert entered.wait(1.0)
    return worker, thread, result, release


def _wait_for_watchdog_fault(worker):
    deadline = time.monotonic() + CONFIG.heartbeat_interval_s + 1.0
    while worker._watchdog is None or not worker._watchdog.faulted:
        assert time.monotonic() < deadline, "the watchdog never noticed the lost Coordinator"
        time.sleep(0.01)


def test_coordinator_loss_during_the_teacher_run_does_not_cancel_it_and_its_result_stays_local():
    """A lost Coordinator is a coordination problem: the Teacher child finishes under its own deadline."""

    fake = Fake(RunMode.EXECUTE)
    worker, thread, result, release = _expert_blocked_with_a_lost_coordinator(fake)
    _wait_for_watchdog_fault(worker)
    time.sleep(0.2)
    assert thread.is_alive(), "expert execution was released before the Teacher finished"
    # Nothing cancelled, fenced or audited as a revocation while the Teacher is within its deadline.
    assert "cancel_motion" not in fake.runtime.calls and "confirm_no_controller_goal" not in fake.runtime.calls
    assert not [call for call in fake.broker.calls if call[0] == "cancel_generation"]
    assert not [call for call in fake.runtime.calls if isinstance(call, tuple) and call[0] == "revocation"]
    assert not worker._stop_requested.is_set()

    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    outcome = result[0]
    # The Teacher's own decision is sealed locally, unchanged; the commit never happens and is reported as a
    # coordination problem, with the Teacher status carried in the bounded failure message.
    assert [call[:2] for call in fake.results.calls if call[0] == "seal_attempt"] == [
        ("seal_attempt", AttemptStatus.PASSED)]
    assert "RESULT_COMMITTED" not in event_names(fake) and "FINALIZING_STARTED" not in event_names(fake)
    assert outcome.stopped_reason == "COORDINATOR_LOST_RESULT_UNCOMMITTED"
    assert outcome.terminal_status is None and outcome.recovered is False
    assert outcome.failure_boundary == "result_commit"
    assert "teacher_status=PASSED" in outcome.failure_message and "COORDINATOR_LOST" in outcome.failure_message
    # The worker stops scheduling: it takes no further lease.
    assert sum(call[0] == "LEASE_REQUEST" for call in fake.coordinator.calls) == 1
    assert worker.run_one().stopped_reason == "WORKER_NOT_READY"


def _expert_blocked_with_a_fenced_teacher_channel(fake, *, code="TEACHER_CHANNEL_FENCED", repeat=True):
    """An EXECUTE run whose Teacher child is blocked in execute_expert while the broker fences its channel.

    The Coordinator keeps answering; only the Teacher lifecycle's renewal hook refuses, as the live run's did."""
    from so101_demo.parallel_batch.contracts.common import TeacherChannelTerminal

    entered, release, hooks = threading.Event(), threading.Event(), []
    original_execute = fake.runtime.execute_expert

    def blocked_execute(*args, **kwargs):
        entered.set()
        assert release.wait(5.0)
        return original_execute(*args, **kwargs)

    def heartbeat_acknowledged(lease):
        hooks.append(lease)
        if entered.is_set():
            raise TeacherChannelTerminal(code)

    fake.runtime.execute_expert = blocked_execute
    fake.runtime.heartbeat_acknowledged = heartbeat_acknowledged
    worker = ParallelWorker(fake.ports())
    result = []
    thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    thread.start()
    assert entered.wait(1.0)
    return worker, thread, result, release, hooks


@pytest.mark.parametrize("status, reason", [(AttemptStatus.FAILED, "TEACHER_TASK_FAIL:FINAL_XY_OUT_OF_TOLERANCE"),
                                            (AttemptStatus.INDETERMINATE, "DYNAMIC_EXECUTION_FAILED")])
def test_a_fenced_teacher_channel_is_the_teachers_terminal_event_and_its_attempt_is_still_committed(status, reason):
    """A5: the broker fenced the Teacher's channel (its phase proof refused). The Worker stops renewing on that channel,
    lets the child finish and commits the Teacher's decision through the normal path; it is not COORDINATOR_LOST."""
    fake = Fake(RunMode.EXECUTE)
    fake.runtime.execute_decision = Decision(status, reason, physical_action_proven_absent=False)
    worker, thread, result, release, hooks = _expert_blocked_with_a_fenced_teacher_channel(fake)
    deadline = time.monotonic() + CONFIG.heartbeat_interval_s + 1.0
    while worker._teacher_channel_terminal is None:
        assert time.monotonic() < deadline, "the fenced channel was never noticed"
        time.sleep(0.01)
    assert not worker._watchdog.faulted, "a fenced Teacher channel is not a lost Coordinator"
    assert worker._coordinator_loss is None and not worker._stop_requested.is_set()
    seen = len(hooks)
    time.sleep(CONFIG.heartbeat_interval_s * 3)
    assert len(hooks) == seen, "no renewal is attempted on the fenced channel again"
    assert sum(call[0] == "HEARTBEAT" for call in fake.coordinator.calls) >= 3, "the Coordinator lease keeps being renewed"
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    outcome = result[0]
    assert outcome.stopped_reason != "COORDINATOR_LOST_RESULT_UNCOMMITTED" and outcome.failure_boundary is None
    assert outcome.terminal_status is status
    assert [call[:2] for call in fake.results.calls if call[0] == "seal_attempt"] == [("seal_attempt", status)]
    names = event_names(fake)
    assert "FINALIZING_STARTED" in names and "RESULT_COMMITTED" in names, "the started attempt is committed"


def test_a_fence_noticed_only_at_the_finalizing_acknowledgement_is_tolerated_too():
    from so101_demo.parallel_batch.contracts.common import TeacherChannelTerminal

    fake = Fake(RunMode.EXECUTE)
    fake.runtime.execute_decision = Decision(AttemptStatus.INDETERMINATE, "DYNAMIC_EXECUTION_FAILED",
                                             physical_action_proven_absent=False)
    fake.runtime.finalizing_acknowledged = lambda lease: (_ for _ in ()).throw(
        TeacherChannelTerminal("TEACHER_FENCE_CONTEXT_INVALID"))
    outcome = ParallelWorker(fake.ports()).run_one()
    assert outcome.terminal_status is AttemptStatus.INDETERMINATE and "RESULT_COMMITTED" in event_names(fake)


def test_a_teacher_lifecycle_failure_that_is_not_a_terminal_channel_still_fails_closed():
    """Only the broker's own channel-terminal refusals are the Teacher's event; any other hook failure is unchanged."""
    fake = Fake(RunMode.EXECUTE)
    entered, gate = threading.Event(), threading.Event()
    original = fake.runtime.execute_expert
    fake.runtime.execute_expert = lambda *a, **k: (entered.set(), gate.wait(5.0), original(*a, **k))[2]

    def refuse(lease):
        if entered.is_set():
            raise PermissionError("TEACHER_WORKER_HEARTBEAT_CHANGED")

    fake.runtime.heartbeat_acknowledged = refuse
    worker = ParallelWorker(fake.ports())
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(worker.run_one()))
    thread.start()
    assert entered.wait(1.0)
    _wait_for_watchdog_fault(worker)
    assert worker._teacher_channel_terminal is None
    gate.set()
    thread.join(3.0)
    assert outcome[0].stopped_reason == "COORDINATOR_LOST_RESULT_UNCOMMITTED", (
        "a lifecycle failure that is not a fenced channel keeps the A3b behaviour")


def test_a_user_stop_still_cancels_a_teacher_that_lost_its_coordinator():
    fake = Fake(RunMode.EXECUTE)
    worker, thread, result, release = _expert_blocked_with_a_lost_coordinator(fake)
    _wait_for_watchdog_fault(worker)
    assert "cancel_motion" not in fake.runtime.calls
    worker.request_stop()
    deadline = time.monotonic() + 2.0
    while "confirm_no_controller_goal" not in fake.runtime.calls:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert thread.is_alive(), "expert execution was released before cancellation"
    assert "cancel_motion" in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    assert result[0].terminal_status is None


def test_the_frozen_teacher_deadline_still_cancels_after_the_coordinator_is_lost():
    fake = Fake(RunMode.EXECUTE)
    worker, thread, result, release = _expert_blocked_with_a_lost_coordinator(fake)
    _wait_for_watchdog_fault(worker)
    time.sleep(0.1)
    assert "cancel_motion" not in fake.runtime.calls
    # The attempt's deadline is the frozen executing hard timeout counted from the start of the Teacher run.
    fake.clock.now += CONFIG.executing_hard_timeout_s - 1.0
    time.sleep(0.1)
    assert "cancel_motion" not in fake.runtime.calls, "cancelled before the deadline"
    fake.clock.now += 1.0
    deadline = time.monotonic() + 2.0
    while "confirm_no_controller_goal" not in fake.runtime.calls:
        assert time.monotonic() < deadline, "the deadline never cancelled the Teacher"
        time.sleep(0.01)
    assert thread.is_alive(), "expert execution was released before cancellation"
    assert "cancel_motion" in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls
    receipts = [call for call in fake.runtime.calls if isinstance(call, tuple) and call[0] == "revocation"]
    assert receipts[0][1] == "WATCHDOG_REVOKED" and dict(receipts[0][3])["reason"] == "TEACHER_EXECUTION_DEADLINE"
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()


def test_coordinator_loss_before_the_teacher_run_still_revokes_in_execute_mode():
    """Outside the Teacher run no child moves, and the earlier watchdog behaviour is unchanged."""

    fake = Fake(RunMode.EXECUTE)
    release_model, release_heartbeat = threading.Event(), threading.Event()
    fake.broker.block = release_model
    fake.coordinator.block_watchdog_heartbeat = release_heartbeat
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one)
    thread.start()
    assert fake.broker.entered.wait(1)
    assert fake.coordinator.heartbeat_entered.wait(1)
    fake.clock.now += CONFIG.heartbeat_timeout_s
    time.sleep(0.05)
    release_model.set()
    release_heartbeat.set()
    thread.join(2)
    assert not thread.is_alive()
    assert "submit_motion" not in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls


def test_revocation_does_not_wait_for_blocked_broker_fence_before_motion_cancel():
    """A slow Broker fence must not delay exact-lease controller cancellation."""

    fake = Fake(RunMode.EXECUTE)
    worker = ParallelWorker(fake.ports())
    lease = fake.coordinator.grant_lease(
        "w1", generation=1, request_key="lease-for-revocation"
    )
    with worker._lease_lock:
        worker._active_lease = lease

    broker_entered = threading.Event()
    release_broker = threading.Event()
    motion_cancelled = threading.Event()
    original_cancel_motion = fake.runtime.cancel_motion

    def blocked_broker_fence(worker_id, generation):
        fake.broker.calls.append(("cancel_generation", worker_id, generation))
        broker_entered.set()
        assert release_broker.wait(3.0)
        return True

    def observe_motion_cancel(current):
        motion_cancelled.set()
        return original_cancel_motion(current)

    fake.broker.cancel_generation = blocked_broker_fence
    fake.runtime.cancel_motion = observe_motion_cancel
    revocation = worker._start_revocation(lease)
    assert broker_entered.wait(1.0)
    try:
        assert motion_cancelled.wait(0.2), (
            "motion cancellation was serialized behind Broker fencing"
        )
    finally:
        release_broker.set()

    assert revocation["event"].wait(1.0)
    assert fake.broker.calls.count(("cancel_generation", "w1", 1)) == 1
    safety_calls = [call for call in fake.runtime.calls if isinstance(call, str)]
    assert safety_calls[-2:] == [
        "cancel_motion", "confirm_no_controller_goal"
    ]
    assert revocation == {
        "event": revocation["event"],
        "audit_event": revocation["audit_event"],
        "fenced": True,
        "stopped": True,
        "confirmed": True,
    }


def test_watchdog_revocation_never_waits_for_blocked_audit_before_motion_cancel():
    """A hung durable recorder must not precede the physical safety actions."""

    fake = Fake(RunMode.EXECUTE)
    worker = ParallelWorker(fake.ports())
    lease = fake.coordinator.grant_lease(
        "w1", generation=1, request_key="lease-for-blocked-audit"
    )
    with worker._lease_lock:
        worker._active_lease = lease

    audit_entered = threading.Event()
    release_audit = threading.Event()
    motion_cancelled = threading.Event()
    original_cancel_motion = fake.runtime.cancel_motion

    def blocked_audit(*_args, **_kwargs):
        audit_entered.set()
        assert release_audit.wait(3.0)
        return True

    def observe_motion_cancel(current):
        motion_cancelled.set()
        return original_cancel_motion(current)

    fake.runtime.record_revocation = blocked_audit
    fake.runtime.cancel_motion = observe_motion_cancel
    worker._watchdog_revoked(lease, "COORDINATOR_LOST")

    assert motion_cancelled.wait(0.2), "audit I/O delayed motion cancellation"
    assert audit_entered.wait(1.0)
    try:
        assert ("cancel_generation", "w1", 1) in fake.broker.calls
        assert "confirm_no_controller_goal" in fake.runtime.calls
    finally:
        release_audit.set()


def test_stop_revocation_never_waits_for_blocked_cancel_request_audit():
    """The non-watchdog CANCEL_REQUESTED receipt is also after safety actions."""

    fake = Fake(RunMode.EXECUTE)
    worker = ParallelWorker(fake.ports())
    lease = fake.coordinator.grant_lease(
        "w1", generation=1, request_key="lease-for-stop-audit"
    )
    with worker._lease_lock:
        worker._active_lease = lease
    audit_entered = threading.Event()
    release_audit = threading.Event()
    motion_cancelled = threading.Event()
    original_cancel_motion = fake.runtime.cancel_motion

    def blocked_audit(*_args, **_kwargs):
        audit_entered.set()
        assert release_audit.wait(3.0)
        return True

    def observe_motion_cancel(current):
        motion_cancelled.set()
        return original_cancel_motion(current)

    fake.runtime.record_revocation = blocked_audit
    fake.runtime.cancel_motion = observe_motion_cancel
    worker.request_stop()

    assert motion_cancelled.wait(0.2), "CANCEL_REQUESTED audit delayed safety"
    assert audit_entered.wait(1.0)
    release_audit.set()
