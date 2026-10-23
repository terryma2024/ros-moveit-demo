"""Acknowledgement deadlines, callback fencing, results and recovery."""

from dataclasses import replace

from parallel_batch_worker_support import CONFIG, Decision, Fake
import pytest

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    RunMode,
    ValidationStatus,
)
from so101_demo.parallel_batch.worker import ParallelWorker


@pytest.mark.parametrize("mode", [RunMode.EXECUTE, RunMode.PLAN_ONLY, RunMode.DRY_RUN])
def test_ack_deadlines_use_frozen_values_from_first_entry(mode):
    fake = Fake(mode)
    real_ack = fake.coordinator.ack_lease

    def late_ack(*args, **kwargs):
        fake.clock.now += CONFIG.lease_ack_timeout_s
        return real_ack(*args, **kwargs)

    fake.coordinator.ack_lease = late_ack
    ParallelWorker(fake.ports()).run_one()
    assert fake.runtime.calls == ["worker_ready_gate"]


def test_attempt_and_result_ack_deadlines_fail_closed():
    attempt = Fake()
    real_start = attempt.coordinator.ack_attempt_started

    def late_start(*args, **kwargs):
        attempt.clock.now += CONFIG.attempt_start_ack_timeout_s
        return real_start(*args, **kwargs)

    attempt.coordinator.ack_attempt_started = late_start
    ParallelWorker(attempt.ports()).run_one()
    assert "submit_motion" not in attempt.runtime.calls

    result = Fake()
    real_commit = result.coordinator.commit_result

    def late_commit(*args, **kwargs):
        result.clock.now += CONFIG.result_ack_timeout_s
        return real_commit(*args, **kwargs)

    result.coordinator.commit_result = late_commit
    ParallelWorker(result.ports()).run_one()
    assert result.results.calls[0][0] == "seal_attempt"
    assert result.coordinator.recovery == []


def test_result_ack_deadline_is_not_reset_after_finalizing_ack():
    fake = Fake()
    real_finalizing = fake.coordinator.begin_finalizing
    real_commit = fake.coordinator.commit_result

    def slow_finalizing(*args, **kwargs):
        fake.clock.now += CONFIG.result_ack_timeout_s - 1.0
        return real_finalizing(*args, **kwargs)

    def slow_commit(*args, **kwargs):
        fake.clock.now += 1.0
        return real_commit(*args, **kwargs)

    fake.coordinator.begin_finalizing = slow_finalizing
    fake.coordinator.commit_result = slow_commit
    first = ParallelWorker(fake.ports()).run_one()
    assert first.recovered is False
    assert first.stopped_reason == "TERMINAL_ACK_FAILED"
    assert fake.coordinator.recovery == []


def test_clock_regression_stops_before_next_side_effect():
    fake = Fake()
    real_reset = fake.runtime.reset_point

    def rewind(lease):
        fake.clock.now -= 1
        return real_reset(lease)

    fake.runtime.reset_point = rewind
    ParallelWorker(fake.ports()).run_one()
    assert fake.runtime.calls[:2] == ["worker_ready_gate", "reset_point"]
    assert all(call[0] != "request_model" for call in fake.broker.calls)


@pytest.mark.parametrize("boundary", ["model", "pose", "motion"])
def test_fencing_at_each_callback_boundary_stops_next_side_effect(boundary):
    fake = Fake()
    if boundary == "model":
        real = fake.broker.request_model

        def fenced(*args):
            value = real(*args)
            fake.coordinator.active = replace(fake.coordinator.active, lease_generation=2)
            return value

        fake.broker.request_model = fenced
    elif boundary == "pose":
        real = fake.runtime.admit_pose

        def fenced(*args):
            value = real(*args)
            fake.coordinator.active = replace(fake.coordinator.active, lease_generation=2)
            return value

        fake.runtime.admit_pose = fenced
    else:
        real = fake.runtime.execute_expert

        def fenced(*args):
            value = real(*args)
            fake.coordinator.active = replace(fake.coordinator.active, lease_generation=2)
            return value

        fake.runtime.execute_expert = fenced
    ParallelWorker(fake.ports()).run_one()
    if boundary == "model":
        assert "pose_admission" not in fake.runtime.calls
    if boundary == "pose":
        assert "submit_motion" not in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls


@pytest.mark.parametrize(
    "mode,boundary,forbidden",
    [
        (RunMode.EXECUTE, "reset_point", "point_initial_gate"),
        (RunMode.EXECUTE, "point_initial_gate", "submit_motion"),
        (RunMode.PLAN_ONLY, "plan_expert", "VALIDATION_COMMITTED"),
        (RunMode.DRY_RUN, "scheduler_trace", "VALIDATION_COMMITTED"),
    ],
)
def test_fencing_at_reset_gate_plan_and_scheduler_boundaries(mode, boundary, forbidden):
    fake = Fake(mode)
    owner = fake.runtime
    real = getattr(owner, boundary)

    def fenced(*args, **kwargs):
        value = real(*args, **kwargs)
        fake.coordinator.active = replace(fake.coordinator.active, lease_generation=2)
        return value

    setattr(owner, boundary, fenced)
    ParallelWorker(fake.ports()).run_one()
    if forbidden != "VALIDATION_COMMITTED":
        assert forbidden not in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls
    assert "confirm_no_controller_goal" in fake.runtime.calls


def test_lease_expiry_while_model_blocks_prevents_pose_and_motion():
    fake = Fake()
    real = fake.broker.request_model

    def expired(*args, **kwargs):
        value = real(*args, **kwargs)
        fake.clock.now = fake.coordinator.active.lease_deadline_monotonic_s
        return value

    fake.broker.request_model = expired
    ParallelWorker(fake.ports()).run_one()
    assert "pose_admission" not in fake.runtime.calls
    assert "submit_motion" not in fake.runtime.calls
    assert ("cancel_generation", "w1", 1) in fake.broker.calls


@pytest.mark.parametrize(
    "mode,wrong_status",
    [
        (RunMode.EXECUTE, ValidationStatus.VALIDATION_FAILED),
        (RunMode.PLAN_ONLY, AttemptStatus.FAILED),
        (RunMode.DRY_RUN, AttemptStatus.INVALID),
    ],
)
def test_physical_and_validation_results_cannot_be_converted(mode, wrong_status):
    fake = Fake(mode)
    wrong = Decision(wrong_status)
    if mode is RunMode.EXECUTE:
        fake.runtime.execute_decision = wrong
    elif mode is RunMode.PLAN_ONLY:
        fake.runtime.plan_decision = wrong
    else:
        fake.runtime.scheduler_decision = wrong
    result = ParallelWorker(fake.ports()).run_one()
    assert result.terminal_status is None
    assert fake.results.calls == []
    assert fake.coordinator.recovery == []


def test_failure_is_sealed_before_recovery_and_success_reuses_slot_at_new_generation():
    fake = Fake(point_count=2)
    fake.runtime.execute_decision = Decision(
        AttemptStatus.FAILED, "PLANNING_FAILED", physical_action_proven_absent=True)
    worker = ParallelWorker(fake.ports())
    worker.run()
    ordered = [call[0] for call in fake.results.calls]
    assert ordered == [
        "seal_attempt", "recovery_receipt", "verify_recovery_receipt",
        "seal_attempt", "recovery_receipt", "verify_recovery_receipt",
    ]
    assert [c for c in fake.coordinator.calls if c[0] == "register_worker"] == [
        ("register_worker", "w1", 1), ("register_worker", "w1", 2),
        ("register_worker", "w1", 3),
    ]
    assert [c for c in fake.broker.calls if c[0] == "cancel_generation"] == [
        ("cancel_generation", "w1", 1), ("cancel_generation", "w1", 2),
    ]


def test_failed_recovery_quarantines_and_prevents_another_lease():
    fake = Fake(point_count=2)
    fake.runtime.recovery_succeeds = False
    ParallelWorker(fake.ports()).run()
    assert sum(c[0] == "LEASE_REQUEST" for c in fake.coordinator.calls) == 1
    assert fake.coordinator.recovery[-1]["succeeded"] is False


def test_recovered_initial_gate_failure_continues_to_unique_remaining_point():
    fake = Fake(point_count=2)
    original_gate = fake.runtime.point_initial_gate
    gate_calls = 0

    def fail_first_gate(lease, reset):
        nonlocal gate_calls
        gate_calls += 1
        if gate_calls == 1:
            raise RuntimeError("first point initial gate rejected")
        return original_gate(lease, reset)

    fake.runtime.point_initial_gate = fail_first_gate

    results = ParallelWorker(fake.ports()).run()

    assert [result.stopped_reason for result in results] == [
        "INITIAL_GATE_FAILED",
        "POINT_TERMINAL",
        "NO_POINT",
    ]
    assert [result.point_id for result in results if result.point_id] == ["p1", "p2"]
    assert results[0].terminal_status is AttemptStatus.INVALID
    assert results[0].recovered is True
    assert sum(
        call[0] == "LEASE_REQUEST" for call in fake.coordinator.calls
    ) == 3
    assert fake.coordinator.next_point == 3


def test_adaptive_recovered_initial_gate_failure_stops_before_another_lease():
    fake = Fake(point_count=2)
    fake.runtime.raise_at = "point_initial_gate"
    ports = {**fake.ports(), "adaptive_workers": True}

    results = ParallelWorker(ports).run()

    assert [result.stopped_reason for result in results] == [
        "INITIAL_GATE_FAILED"
    ]
    assert results[0].terminal_status is AttemptStatus.INVALID
    assert results[0].recovered is True
    assert sum(
        call[0] == "LEASE_REQUEST" for call in fake.coordinator.calls
    ) == 1


def test_adaptive_business_failure_recovers_and_takes_the_next_point():
    fake = Fake(point_count=2)
    fake.runtime.execute_decision = Decision(
        AttemptStatus.FAILED,
        "PLANNING_FAILED",
        physical_action_proven_absent=True,
    )
    ports = {**fake.ports(), "adaptive_workers": True}

    results = ParallelWorker(ports).run()

    assert [result.terminal_status for result in results[:2]] == [
        AttemptStatus.FAILED,
        AttemptStatus.FAILED,
    ]
    assert results[-1].stopped_reason == "NO_POINT"
    assert sum(
        call[0] == "LEASE_REQUEST" for call in fake.coordinator.calls
    ) == 3


def test_recovery_deadline_starts_once_and_cannot_be_extended():
    fake = Fake()
    observed = []

    def delayed_recovery(worker_id, generation, deadline_monotonic_s):
        observed.append(deadline_monotonic_s)
        fake.clock.now += CONFIG.worker_recovery_timeout_s
        return False

    fake.runtime.recover = delayed_recovery
    result = ParallelWorker(fake.ports()).run_one()
    assert observed == [10.0 + CONFIG.worker_recovery_timeout_s]
    assert result.recovered is False
    assert fake.coordinator.recovery == []
    assert not any(call == ("register_worker", "w1", 2)
                   for call in fake.coordinator.calls)


def test_last_point_recovery_failure_does_not_rewrite_sealed_result():
    fake = Fake()
    fake.runtime.recovery_succeeds = False
    ParallelWorker(fake.ports()).run_one()
    assert [c[1] for c in fake.results.calls if c[0] == "seal_attempt"] == [
        AttemptStatus.PASSED,
    ]
    assert fake.coordinator.sealed_statuses == [AttemptStatus.PASSED]


def test_uncertain_physical_exception_is_indeterminate_but_validation_stays_validation():
    physical = Fake()
    physical.runtime.raise_at = "submit_motion"
    physical.runtime.goal_confirmed = False
    ParallelWorker(physical.ports()).run_one()
    assert physical.results.calls[0][1] is AttemptStatus.INDETERMINATE

    validation = Fake(RunMode.PLAN_ONLY)
    validation.broker.raise_request = RuntimeError("broker down")
    ParallelWorker(validation.ports()).run_one()
    assert validation.results.calls[0][1] is ValidationStatus.VALIDATION_INVALID
    assert all(call[0] != "seal_attempt" for call in validation.results.calls)


def test_zero_current_goals_does_not_prove_an_authorized_action_never_happened():
    fake = Fake()
    fake.runtime.raise_at = "submit_motion"
    fake.runtime.goal_confirmed = True
    ParallelWorker(fake.ports()).run_one()
    assert fake.results.calls[0][1] is AttemptStatus.INDETERMINATE


def test_duplicate_reentrant_ack_cannot_consume_k_or_advance_twice():
    fake = Fake(point_count=2)
    worker = ParallelWorker(fake.ports())
    fake.coordinator.reenter = worker.run_one
    worker.run_one()
    assert sum(c[0] == "LEASE_REQUEST" for c in fake.coordinator.calls) == 1
    assert len(fake.coordinator.sealed_statuses) == 1


def test_reentrant_seal_cannot_overwrite_first_terminal_result():
    fake = Fake(point_count=2)
    worker = ParallelWorker(fake.ports())
    real_seal = fake.results.seal_attempt

    def reentrant_seal(*args, **kwargs):
        nested = worker.run_one()
        assert nested.stopped_reason == "REENTRANT_CALL_REJECTED"
        return real_seal(*args, **kwargs)

    fake.results.seal_attempt = reentrant_seal
    worker.run_one()
    assert fake.coordinator.sealed_statuses == [AttemptStatus.PASSED]
    assert sum(c[0] == "LEASE_REQUEST" for c in fake.coordinator.calls) == 1


@pytest.mark.parametrize(
    "mutator",
    [
        lambda lease: replace(lease, coordinator_epoch=2),
        lambda lease: replace(lease, worker_generation=2),
        lambda lease: replace(lease, lease_generation=2),
        lambda lease: replace(lease, attempt_id="replayed"),
    ],
)
def test_stale_ack_identity_never_authorizes_reset(mutator):
    fake = Fake()
    real_ack = fake.coordinator.ack_lease

    def stale_ack(*args, **kwargs):
        ack = real_ack(*args, **kwargs)
        return replace(ack, lease=mutator(ack.lease))

    fake.coordinator.ack_lease = stale_ack
    ParallelWorker(fake.ports()).run_one()
    assert fake.runtime.calls == ["worker_ready_gate"]


@pytest.mark.parametrize("failure", ["coordinator", "broker", "runtime", "seal", "recovery"])
def test_port_exceptions_fail_closed_and_never_escape_as_authorization(failure):
    fake = Fake()
    if failure == "coordinator":
        fake.coordinator.heartbeat_reply = RuntimeError("lost")
    elif failure == "broker":
        fake.broker.raise_request = RuntimeError("lost")
    elif failure == "runtime":
        fake.runtime.raise_at = "reset_point"
    elif failure == "seal":
        fake.results.seal_attempt = lambda *_: (_ for _ in ()).throw(OSError("disk"))
    else:
        fake.runtime.recover = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad"))
    ParallelWorker(fake.ports()).run_one()
    assert len(fake.coordinator.sealed_statuses) <= 1
    assert "submit_motion" not in fake.runtime.calls or failure in {"seal", "recovery"}
