"""The durable coordinator port, gate summaries, heartbeats and recovery deadlines."""

from dataclasses import replace
import threading
import time

from parallel_batch_worker_support import CONFIG, Ack, Broker, Clock, Fake, Runtime, event_names
import pytest

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    RunMode,
    WorkerState,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.contracts.linux_cuda import (
    BatchKind,
    BatchRequest,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.worker import ParallelWorker


def expected_gate_summary(lease):
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
        "reset_completed_monotonic_s": 20.0,
        "source_frame_monotonic_s": 21.0,
        "canonical_joints": True,
        "no_controller_goal": True,
        "no_attachment": True,
        "no_contact": True,
        "no_stale_node": True,
    }


def expected_scheduler_summary(lease):
    return {
        "schema_version": 1,
        "kind": "SCHEDULER_START",
        "batch_id": lease.batch_id,
        "coordinator_epoch": lease.coordinator_epoch,
        "worker_id": lease.worker_id,
        "worker_generation": lease.worker_generation,
        "point_id": lease.point_id,
        "attempt_id": lease.attempt_id,
        "lease_generation": lease.lease_generation,
        "point_gate_applicable": False,
        "physical_runtime_started": False,
        "scheduler_only": True,
    }


def test_worker_composes_with_real_durable_coordinator_port(tmp_path):
    clock = Clock()
    request = BatchRequest("batch-a", RunMode.EXECUTE, ("p1",), 1, tmp_path, BatchKind.FIRST_PASS)
    journal = CoordinatorJournal.create(tmp_path, "batch-a")

    class DurableResults:
        def __init__(self):
            self.sealed = {}

        def seal_attempt(self, lease, decision):
            location = str(tmp_path / lease.attempt_id / "sealed")
            self.sealed[location] = (lease.attempt_id, decision.status)
            return location

        def verify(self, lease, location, run_mode):
            attempt_id, status = self.sealed[location]
            assert attempt_id == lease.attempt_id
            assert run_mode is RunMode.EXECUTE
            return {"status": status, "sha256": "c" * 64}

        def discover(self, lease, workspace):
            return None

        def write_recovery_receipt(
                self, lease, *, succeeded, generation,
                deadline_monotonic_s=None, clock=None):
            return str(tmp_path / "recoveries" / f"{lease.attempt_id}-{generation}")

        def verify_recovery_receipt(
                self, location, lease, *, succeeded, generation,
                deadline_monotonic_s=None, clock=None):
            return True

    results = DurableResults()
    coordinator = BatchCoordinator(
        journal, request, config=CONFIG, clock=clock, result_port=results,
    )
    real_commit = coordinator.commit_result
    committed_deadlines = []

    def advancing_commit(*args, **kwargs):
        response = real_commit(*args, **kwargs)
        committed_deadlines.append(response["recovery_deadline_monotonic_s"])
        clock.now += 1.0
        return response

    coordinator.commit_result = advancing_commit
    runtime = Runtime(RunMode.EXECUTE)
    broker = Broker()
    worker = ParallelWorker({
        "coordinator": coordinator,
        "broker": broker,
        "runtime": runtime,
        "results": results,
        "clock": clock,
        "config": CONFIG,
        "worker_id": "w1",
        "generation": 1,
    })
    try:
        result = worker.run_one()
        snapshot = coordinator.snapshot()
        assert result.terminal_status is AttemptStatus.PASSED
        assert result.recovered is True
        assert snapshot.points["p1"].status.value == "PASSED"
        assert snapshot.workers["w1"].generation == 2
        assert snapshot.workers["w1"].state is WorkerState.AVAILABLE
        assert committed_deadlines == [130.0]
        assert runtime.recovery_deadlines == [130.0]
    finally:
        journal.close()


def test_worker_passes_exact_locally_validated_gate_summary_to_start_ack():
    fake = Fake()
    ParallelWorker(fake.ports()).run_one()
    lease = next(value for value in fake.coordinator.calls
                 if value[0] == "LEASE_GRANTED")
    assert len(fake.coordinator.start_summaries) == 1
    assert fake.coordinator.start_summaries[0] == expected_gate_summary(
        LeaseIdentity(
            "batch-a", 1, "w1", 1, "p1", "p1-lease-1", 1, 10.0, 310.0,
        ))


def test_dry_run_passes_only_exact_scheduler_start_summary():
    fake = Fake(RunMode.DRY_RUN)
    ParallelWorker(fake.ports()).run_one()
    lease = LeaseIdentity(
        "batch-a", 1, "w1", 1, "p1", "p1-lease-1", 1, 10.0, 310.0,
    )
    assert fake.coordinator.start_summaries == [expected_scheduler_summary(lease)]
    assert "reset_point" not in fake.runtime.calls
    assert "point_initial_gate" not in fake.runtime.calls
    assert fake.runtime.physical_starts == 0


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("reset", "reset_epoch", ""),
        ("reset", "simulation_session_id", "   "),
        ("reset", "reset_completed_monotonic_s", True),
        ("reset", "attempt_id", "stale-attempt"),
        ("reset", "lease_generation", 2),
        ("gate", "batch_id", "other-batch"),
        ("gate", "worker_generation", 2),
        ("gate", "attempt_id", "stale-attempt"),
        ("gate", "lease_generation", 2),
        ("gate", "source_frame_monotonic_s", False),
    ],
)
def test_malformed_or_stale_gate_evidence_never_starts_attempt(target, field, value):
    fake = Fake()
    method_name = "reset_point" if target == "reset" else "point_initial_gate"
    real = getattr(fake.runtime, method_name)

    def malformed(*args, **kwargs):
        return replace(real(*args, **kwargs), **{field: value})

    setattr(fake.runtime, method_name, malformed)
    ParallelWorker(fake.ports()).run_one()
    assert all(event != "ATTEMPT_STARTED" for event in event_names(fake))
    assert fake.coordinator.start_summaries == []
    assert all(call[0] != "request_model" for call in fake.broker.calls)


def test_blocked_lease_ack_times_out_and_late_reply_never_authorizes_reset():
    fake = Fake()
    entered, release = threading.Event(), threading.Event()
    real = fake.coordinator.ack_lease

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(2)
        return real(*args, **kwargs)

    fake.coordinator.ack_lease = blocked
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one)
    thread.start()
    assert entered.wait(1)
    fake.clock.now += CONFIG.lease_ack_timeout_s
    time.sleep(0.05)
    timed_out_before_release = not thread.is_alive()
    release.set()
    thread.join(1)
    assert timed_out_before_release
    assert fake.runtime.calls == ["worker_ready_gate"]


def test_blocked_current_heartbeat_times_out_without_late_side_effect():
    fake = Fake()
    entered, release = threading.Event(), threading.Event()
    real = fake.coordinator.heartbeat

    def blocked(lease):
        if threading.current_thread().name == "parallel-worker-rpc-w1":
            entered.set()
            release.wait(2)
        return real(lease)

    fake.coordinator.heartbeat = blocked
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one, name="worker-main")
    thread.start()
    assert entered.wait(1)
    fake.clock.now += CONFIG.heartbeat_timeout_s
    time.sleep(0.05)
    timed_out_before_release = not thread.is_alive()
    release.set()
    thread.join(1)
    assert timed_out_before_release
    assert "reset_point" not in fake.runtime.calls


def test_current_heartbeat_reply_at_exact_five_second_boundary_is_rejected():
    fake = Fake()
    real = fake.coordinator.heartbeat
    crossed = False

    def exact_boundary(lease):
        nonlocal crossed
        if (threading.current_thread().name == "parallel-worker-rpc-w1"
                and not crossed):
            crossed = True
            fake.clock.now += CONFIG.heartbeat_timeout_s
        return real(lease)

    fake.coordinator.heartbeat = exact_boundary
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one, name="worker-main")
    thread.start()
    thread.join(1)
    assert not thread.is_alive()
    assert "reset_point" not in fake.runtime.calls


def test_watchdog_fault_while_current_heartbeat_is_in_flight_revokes_reply():
    fake = Fake()
    main_entered = threading.Event()
    release_main = threading.Event()
    real = fake.coordinator.heartbeat

    def racing_heartbeat(lease):
        name = threading.current_thread().name
        if name.startswith("parallel-worker-heartbeat-rpc-"):
            assert main_entered.wait(1)
            raise RuntimeError("watchdog lost coordinator")
        if name == "parallel-worker-rpc-w1":
            main_entered.set()
            assert release_main.wait(1)
        return real(lease)

    fake.coordinator.heartbeat = racing_heartbeat
    worker = ParallelWorker(fake.ports())
    thread = threading.Thread(target=worker.run_one, name="worker-main")
    thread.start()
    timeout = time.monotonic() + 1
    while (worker._watchdog is None or not worker._watchdog.faulted):
        time.sleep(0.01)
        assert time.monotonic() < timeout
    release_main.set()
    thread.join(1)
    assert not thread.is_alive()
    assert "reset_point" not in fake.runtime.calls


@pytest.mark.parametrize("lost_at", ["post-action-heartbeat", "finalizing"])
def test_coordinator_loss_after_authorization_still_seals_local_terminal(lost_at):
    fake = Fake()
    if lost_at == "post-action-heartbeat":
        real = fake.runtime.execute_expert

        def lose_after_action(*args, **kwargs):
            value = real(*args, **kwargs)
            fake.coordinator.heartbeat_reply = RuntimeError("coordinator lost")
            return value

        fake.runtime.execute_expert = lose_after_action
    else:
        fake.coordinator.begin_finalizing = (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("lost")))
    ParallelWorker(fake.ports()).run_one()
    seals = [call for call in fake.results.calls if call[0] == "seal_attempt"]
    assert len(seals) == 1
    if lost_at == "post-action-heartbeat":
        # The Teacher's own PASSED decision survives a Coordinator lost right after the run.
        assert seals[0][1] is AttemptStatus.PASSED
    assert fake.coordinator.recovery == []


@pytest.mark.parametrize(
    "boundary",
    ["recover", "ready", "receipt", "record", "register"],
)
def test_recovery_exact_deadline_at_each_blocking_boundary_never_readmits(boundary):
    fake = Fake()
    start = fake.clock.now
    deadline = start + CONFIG.worker_recovery_timeout_s
    if boundary == "recover":
        real = fake.runtime.recover

        def delayed(*args, **kwargs):
            fake.clock.now = deadline
            return real(*args, **kwargs)

        fake.runtime.recover = delayed
    elif boundary == "ready":
        real = fake.runtime.worker_ready_gate
        calls = 0

        def delayed():
            nonlocal calls
            calls += 1
            value = real()
            if calls == 2:
                fake.clock.now = deadline
            return value

        fake.runtime.worker_ready_gate = delayed
    elif boundary == "receipt":
        fake.results.advance_receipt_to_deadline = True
    elif boundary == "record":
        real = fake.coordinator.record_recovery

        def delayed(*args, **kwargs):
            fake.clock.now = deadline
            return real(*args, **kwargs)

        fake.coordinator.record_recovery = delayed
    else:
        real = fake.coordinator.register_worker

        def delayed(*args, **kwargs):
            if kwargs["generation"] == 2:
                fake.clock.now = deadline
            return real(*args, **kwargs)

        fake.coordinator.register_worker = delayed
    result = ParallelWorker(fake.ports()).run_one()
    assert result.recovered is False
    if boundary != "record":
        assert not any(call == ("register_worker", "w1", 2)
                       for call in fake.coordinator.calls)
    assert not any(facts["succeeded"] is True for facts in fake.coordinator.recovery)
    assert sum(call[0] == "LEASE_REQUEST" for call in fake.coordinator.calls) == 1


def test_recovery_receipt_is_read_back_before_successful_readmission():
    fake = Fake()
    result = ParallelWorker(fake.ports()).run_one()
    names = [call[0] for call in fake.results.calls]
    assert result.recovered is True
    assert names.index("recovery_receipt") < names.index("verify_recovery_receipt")


def test_pre_action_failure_recovery_accepts_trusted_absence_when_status_never_published():
    fake = Fake(RunMode.EXECUTE)
    fake.broker.raise_request = RuntimeError("TF unavailable before action")
    fake.runtime.cancel_motion = lambda lease: False
    fake.runtime.goal_confirmed = False

    result = ParallelWorker(fake.ports()).run_one()

    assert fake.results.calls[0][1] is AttemptStatus.INVALID
    assert result.recovered is True
    assert fake.coordinator.recovery[-1] == {
        "succeeded": True,
        "fenced": True,
        "owned_processes_stopped": True,
        "controllers_stopped": True,
        "readmitted": True,
        "generation": 2,
        "recovery_deadline_monotonic_s": 130.0,
    }


def test_recovery_emits_bounded_existing_gate_diagnostic_before_receipt(capsys):
    fake = Fake()
    fake.runtime.goal_confirmed = False
    real_write = fake.results.write_recovery_receipt
    observed_before_receipt = []

    def write(*args, **kwargs):
        observed_before_receipt.extend(capsys.readouterr().out.splitlines())
        return real_write(*args, **kwargs)

    fake.results.write_recovery_receipt = write

    result = ParallelWorker(fake.ports()).run_one()

    assert result.recovered is False
    assert observed_before_receipt == [
        '{"confirmed":false,"fenced":true,"kind":"RECOVERY_GATES",'
        '"physical_action_proven_absent":false,"ready":true,'
        '"recovered":true,"stopped":true,'
        '"worker_generation":1,"worker_id":"w1"}'
    ]


def test_worker_uses_commit_frozen_recovery_deadline_after_clock_advances():
    fake = Fake()
    fake.coordinator.advance_after_commit_s = 1.0
    result = ParallelWorker(fake.ports()).run_one()
    assert result.recovered is True
    assert fake.runtime.recovery_deadlines == [130.0]
    assert all(call[-1] == 130.0 for call in fake.results.calls
               if call[0] in {"recovery_receipt", "verify_recovery_receipt"})


@pytest.mark.parametrize(
    "reply",
    ["missing", True, float("nan"), "130.0", 10.0, 131.0],
)
def test_missing_malformed_stale_or_mismatched_recovery_deadline_fails_closed(reply):
    fake = Fake()
    if reply == "missing":
        fake.coordinator.omit_recovery_deadline = True
    else:
        fake.coordinator.recovery_deadline_reply = reply
    result = ParallelWorker(fake.ports()).run_one()
    assert result.recovered is False
    assert not any(call == ("register_worker", "w1", 2)
                   for call in fake.coordinator.calls)


@pytest.mark.parametrize("heartbeat_source", ["foreground", "watchdog"])
@pytest.mark.parametrize("stop_during_rpc", [False, True])
def test_original_heartbeat_acceptance_precedes_start_transition_without_blocking_stop(
        heartbeat_source, stop_during_rpc):
    """Actual Worker threads; explicit Coordinator/OWNER port doubles only."""
    fake = Fake(RunMode.EXECUTE)
    fake.runtime.requires_ordered_coordinator_receipts = True
    worker = ParallelWorker(fake.ports())
    lease = fake.coordinator.grant_lease("w1", generation=1, request_key="ordering")
    worker._active_lease = lease
    heartbeat_entered, release_heartbeat, start_entered = (
        threading.Event(), threading.Event(), threading.Event())
    accepted, errors = [], []

    def heartbeat(current):
        heartbeat_entered.set()
        assert release_heartbeat.wait(2)
        return current

    def start():
        start_entered.set()
        return Ack(WorkerState.EXECUTING, 1, lease)

    def invoke(call):
        try:
            call()
        except Exception as error:
            errors.append(error)

    fake.coordinator.heartbeat = heartbeat
    fake.runtime.heartbeat_acknowledged = lambda current: accepted.append("INITIALIZING_HEARTBEAT")
    fake.runtime.attempt_started_acknowledged = lambda current: accepted.append("ATTEMPT_STARTED")
    heartbeat_thread = None
    start_thread = threading.Thread(target=lambda: invoke(lambda: worker._request_ack(
        start, lease, WorkerState.EXECUTING, 5, fake.clock())), daemon=True)
    try:
        if heartbeat_source == "watchdog":
            worker._start_watchdog(lease)
        else:
            heartbeat_thread = threading.Thread(target=lambda: invoke(worker._current), daemon=True)
            heartbeat_thread.start()
        assert heartbeat_entered.wait(1)
        start_thread.start()
        if stop_during_rpc:
            began = time.monotonic()
            worker.request_stop()
            assert time.monotonic() - began < .1
            assert worker._stop_requested.is_set()
        assert not start_entered.wait(.1), "start RPC overtook an unaccepted original heartbeat"
    finally:
        release_heartbeat.set()
        start_thread.join(2)
        if heartbeat_thread is not None:
            heartbeat_thread.join(2)
        worker._stop_watchdog()
    assert not start_thread.is_alive()
    if stop_during_rpc:
        assert not start_entered.is_set()
        assert accepted == []
        assert errors
    else:
        assert start_entered.is_set()
        assert accepted[:2] == ["INITIALIZING_HEARTBEAT", "ATTEMPT_STARTED"]
        assert errors == []


def test_late_ordered_owner_hook_cannot_publish_a_phase_ack_after_its_original_deadline():
    from so101_demo.parallel_batch.worker_parts.contracts import WorkerError
    fake=Fake(RunMode.EXECUTE)
    fake.runtime.requires_ordered_coordinator_receipts=True
    worker=ParallelWorker(fake.ports())
    lease=fake.coordinator.grant_lease("w1",generation=1,request_key="late-owner")
    worker._active_lease=lease
    updated=replace(lease,lease_deadline_monotonic_s=lease.lease_deadline_monotonic_s+1)
    def late_hook(current):
        fake.clock.now+=5
    fake.runtime.attempt_started_acknowledged=late_hook
    with pytest.raises(WorkerError,match="ACK_TIMEOUT"):
        worker._request_ack(lambda:Ack(WorkerState.EXECUTING,1,updated),lease,WorkerState.EXECUTING,5,fake.clock())
    assert worker._active_lease is lease
