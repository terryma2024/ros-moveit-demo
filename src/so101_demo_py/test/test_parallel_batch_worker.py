"""Behavioral contract for the fenced parallel Worker state machine."""

from dataclasses import dataclass, replace
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.contracts import (
    AttemptStatus,
    BatchRequest,
    ExecutionKind,
    LeaseIdentity,
    RunMode,
    ValidationStatus,
    WorkerState,
    load_parallel_runtime_config,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.worker import ParallelWorker


CONFIG = load_parallel_runtime_config(
    Path(__file__).resolve().parents[1] / "config/mujoco/parallel_batch_v1.yaml"
)


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


@dataclass(frozen=True)
class Ack:
    state: WorkerState
    generation: int
    lease: LeaseIdentity | None


@dataclass(frozen=True)
class ResetEvidence:
    point_id: str
    reset_epoch: str
    simulation_session_id: str
    reset_completed_monotonic_s: float
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    attempt_id: str
    lease_generation: int


@dataclass(frozen=True)
class GateEvidence:
    point_id: str
    canonical_joints: bool
    no_controller_goal: bool
    no_attachment: bool
    no_contact: bool
    no_stale_node: bool
    reset_epoch: str
    simulation_session_id: str
    source_frame_monotonic_s: float
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    attempt_id: str
    lease_generation: int


@dataclass(frozen=True)
class Chain:
    chain_id: str
    candidate: object


@dataclass(frozen=True)
class Decision:
    status: AttemptStatus | ValidationStatus
    reason: str = "OK"
    physical_action_proven_absent: bool = True


class Coordinator:
    def __init__(self, mode, clock, *, point_count=1):
        self.mode = mode
        self.clock = clock
        self.generation = 1
        self.point_count = point_count
        self.next_point = 1
        self.active = None
        self.calls = []
        self.withhold_lease_ack = False
        self.withhold_start_ack = False
        self.withhold_result_ack = False
        self.heartbeat_reply = True
        self.block_watchdog_heartbeat = None
        self.heartbeat_entered = threading.Event()
        self.reenter = None
        self.sealed_statuses = []
        self.recovery = []
        self.start_summaries = []
        self.recovery_deadline = None
        self.recovery_deadline_reply = None
        self.omit_recovery_deadline = False
        self.advance_after_commit_s = 0.0

    def register_worker(
            self, worker_id, *, generation,
            recovery_deadline_monotonic_s=None):
        if (recovery_deadline_monotonic_s is not None
                and self.clock() >= recovery_deadline_monotonic_s):
            raise TimeoutError("recovery registration deadline")
        if (recovery_deadline_monotonic_s is not None
                and recovery_deadline_monotonic_s != self.recovery_deadline):
            raise ValueError("recovery registration deadline mismatch")
        self.calls.append(("register_worker", worker_id, generation))
        self.generation = generation
        state = (WorkerState.RECOVERING if recovery_deadline_monotonic_s is not None
                 else WorkerState.AVAILABLE)
        return Ack(state, generation, None)

    def grant_lease(self, worker_id, *, generation, request_key):
        self.calls.append(("LEASE_REQUEST", request_key))
        if self.next_point > self.point_count:
            return None
        point_id = f"p{self.next_point}"
        self.next_point += 1
        self.active = LeaseIdentity(
            "batch-a", 1, worker_id, generation, point_id,
            f"{point_id}-lease-1", 1, self.clock(), self.clock() + 300.0,
        )
        return self.active

    def ack_lease(self, lease, *, request_key):
        self.calls.append(("LEASE_GRANTED", request_key))
        if self.reenter:
            callback, self.reenter = self.reenter, None
            callback()
        if self.withhold_lease_ack:
            return None
        return Ack(WorkerState.INITIALIZING, self.generation, self.active)

    def ack_attempt_started(self, lease, *, request_key, gate_summary=None):
        self.calls.append(("ATTEMPT_STARTED", request_key))
        self.start_summaries.append(gate_summary)
        if self.withhold_start_ack:
            return None
        return Ack(WorkerState.EXECUTING, self.generation, self.active)

    def ack_validation_started(self, lease, *, request_key, gate_summary=None):
        self.calls.append(("VALIDATION_STARTED", request_key))
        self.start_summaries.append(gate_summary)
        if self.withhold_start_ack:
            return None
        return Ack(WorkerState.EXECUTING, self.generation, self.active)

    def heartbeat(self, lease):
        self.calls.append(("HEARTBEAT", lease.worker_generation))
        if (self.block_watchdog_heartbeat is not None
                and threading.current_thread().name.startswith(
                    "parallel-worker-heartbeat-rpc-")):
            self.heartbeat_entered.set()
            self.block_watchdog_heartbeat.wait(3)
        if isinstance(self.heartbeat_reply, Exception):
            raise self.heartbeat_reply
        if self.heartbeat_reply is False:
            return None
        return self.active

    def begin_finalizing(self, lease, *, request_key):
        self.calls.append(("FINALIZING_STARTED", request_key))
        return Ack(WorkerState.FINALIZING, self.generation, self.active)

    def commit_result(self, lease, location, *, request_key):
        self.calls.append(("RESULT_COMMITTED", request_key))
        if self.withhold_result_ack:
            return None
        self.active = None
        self.recovery_deadline = self.clock() + CONFIG.worker_recovery_timeout_s
        deadline = (self.recovery_deadline if self.recovery_deadline_reply is None
                    else self.recovery_deadline_reply)
        response = {
            "status": self.sealed_statuses[-1], "location": location,
            "sha256": "a" * 64,
            "recovery_deadline_monotonic_s": deadline,
        }
        if self.omit_recovery_deadline:
            del response["recovery_deadline_monotonic_s"]
        self.clock.now += self.advance_after_commit_s
        return response

    def commit_validation(self, lease, location, *, request_key):
        self.calls.append(("VALIDATION_COMMITTED", request_key))
        if self.withhold_result_ack:
            return None
        self.active = None
        self.recovery_deadline = self.clock() + CONFIG.worker_recovery_timeout_s
        deadline = (self.recovery_deadline if self.recovery_deadline_reply is None
                    else self.recovery_deadline_reply)
        response = {
            "status": self.sealed_statuses[-1], "location": location,
            "sha256": "b" * 64,
            "recovery_deadline_monotonic_s": deadline,
        }
        if self.omit_recovery_deadline:
            del response["recovery_deadline_monotonic_s"]
        self.clock.now += self.advance_after_commit_s
        return response

    def record_recovery(self, worker_id, **facts):
        deadline = facts["recovery_deadline_monotonic_s"]
        if self.clock() >= deadline:
            raise TimeoutError("recovery record deadline")
        if deadline != self.recovery_deadline:
            raise ValueError("recovery record deadline mismatch")
        self.calls.append(("RECOVERY", facts["generation"], facts["succeeded"]))
        self.recovery.append(facts)
        state = (WorkerState.AVAILABLE if facts["succeeded"]
                 else WorkerState.QUARANTINED)
        return Ack(state, facts["generation"], None)


def test_stop_is_atomic_fence_before_worker_can_start_new_work():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())

    worker.request_stop()
    outcome = worker.run_one()

    assert outcome.stopped_reason == "STOP_REQUESTED"
    assert fake.coordinator.calls == []
    assert fake.runtime.calls == []
    assert fake.broker.calls == []


def test_stop_racing_lease_reply_fences_all_runtime_and_broker_side_effects():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())
    entered, release = threading.Event(), threading.Event()
    original = fake.coordinator.grant_lease

    def blocked_grant(*args, **kwargs):
        entered.set()
        release.wait(1.0)
        return original(*args, **kwargs)

    fake.coordinator.grant_lease = blocked_grant
    result = []
    thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    thread.start()
    assert entered.wait(1.0)
    worker.request_stop()
    release.set()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert result[0].stopped_reason == "LEASE_ACK_FAILED"
    assert fake.runtime.calls == ["worker_ready_gate"]
    assert fake.broker.calls == []


def test_stop_ack_does_not_wait_for_blocked_broker_boundary():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())
    fake.broker.block = threading.Event()
    result = []
    run_thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    run_thread.start()
    assert fake.broker.entered.wait(1.0)

    stopped = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (worker.request_stop(), stopped.set())
    )
    stop_thread.start()
    assert stopped.wait(0.1), "stop ACK waited for the Broker boundary"

    fake.broker.block.set()
    run_thread.join(timeout=1.0)
    stop_thread.join(timeout=1.0)
    assert "pose_admission" not in fake.runtime.calls
    assert "submit_plan" not in fake.runtime.calls
    assert "submit_motion" not in fake.runtime.calls


def test_stop_ack_does_not_wait_for_blocked_action_or_allow_later_boundary():
    fake = Fake(RunMode.EXECUTE)
    worker = ParallelWorker(fake.ports())
    entered, release = threading.Event(), threading.Event()
    original = fake.runtime.execute_expert

    def blocked_action(*args, **kwargs):
        entered.set()
        release.wait(1.0)
        return original(*args, **kwargs)

    fake.runtime.execute_expert = blocked_action
    result = []
    run_thread = threading.Thread(target=lambda: result.append(worker.run_one()))
    run_thread.start()
    assert entered.wait(1.0)

    stopped = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (worker.request_stop(), stopped.set())
    )
    stop_thread.start()
    assert stopped.wait(0.1), "stop ACK waited for the action boundary"

    release.set()
    run_thread.join(timeout=1.0)
    stop_thread.join(timeout=1.0)
    assert fake.runtime.calls.count("submit_motion") == 1
    assert "capture_terminal" not in fake.runtime.calls


class Broker:
    def __init__(self):
        self.calls = []
        self.block = None
        self.entered = threading.Event()
        self.raise_request = None

    def request_model(
        self,
        lease,
        execution_kind,
        *,
        snapshot,
        start_event_id,
        start_event_type,
        reset_epoch,
    ):
        self.calls.append((
            "request_model",
            execution_kind,
            lease.worker_generation,
            snapshot,
            start_event_id,
            start_event_type,
            reset_epoch,
        ))
        if self.block:
            self.entered.set()
            self.block.wait(2)
        if self.raise_request:
            raise self.raise_request
        return Chain("yolo-to-expert", object())

    def cancel_generation(self, worker_id, generation):
        self.calls.append(("cancel_generation", worker_id, generation))
        return True


class Runtime:
    def __init__(self, mode):
        self.mode = mode
        self.calls = []
        self.physical_starts = 0
        self.ready_args = []
        self.chain = None
        self.execute_decision = Decision(AttemptStatus.PASSED, physical_action_proven_absent=False)
        self.plan_decision = Decision(ValidationStatus.VALIDATION_PASSED)
        self.scheduler_decision = Decision(ValidationStatus.VALIDATION_PASSED)
        self.recovery_succeeds = True
        self.recovery_deadlines = []
        self.goal_confirmed = True
        self.raise_at = None
        self.snapshot = SimpleNamespace(
            path="/inputs/w1/attempts/p1/p1-lease-1/working/perception/input/rgb.npy",
            source_stamp_monotonic_s=21.0,
            source_stamp_ns=21_000_000_000,
            source_frame_id="task_camera_frame",
            shape=(4, 5, 3),
            input_sha256="a" * 64,
        )

    def start_physical_runtime(self):
        self.physical_starts += 1

    def worker_ready_gate(self):
        self.calls.append("worker_ready_gate")
        self.ready_args.append(())
        return True

    def reset_point(self, lease):
        self.calls.append("reset_point")
        if self.raise_at == "reset_point":
            raise RuntimeError("reset failed")
        return ResetEvidence(
            lease.point_id, "reset-1", "session-1", 20.0,
            lease.batch_id, lease.coordinator_epoch, lease.worker_id,
            lease.worker_generation, lease.attempt_id, lease.lease_generation,
        )

    def point_initial_gate(self, lease, reset):
        self.calls.append("point_initial_gate")
        if self.raise_at == "point_initial_gate":
            raise RuntimeError("initial gate rejected\nsecond line")
        return GateEvidence(
            lease.point_id, True, True, True, True, True,
            reset.reset_epoch, reset.simulation_session_id, 21.0,
            lease.batch_id, lease.coordinator_epoch, lease.worker_id,
            lease.worker_generation, lease.attempt_id, lease.lease_generation,
        )

    def inference_snapshot(self, lease):
        self.calls.append("inference_snapshot")
        return self.snapshot

    def admit_pose(self, lease, chain):
        self.calls.append("pose_admission")
        self.chain = chain
        return chain

    def execute_expert(self, lease, admitted):
        self.calls.append("submit_motion")
        assert admitted is self.chain
        if self.raise_at == "submit_motion":
            raise RuntimeError("transport uncertain")
        return self.execute_decision

    def plan_expert(self, lease, admitted):
        self.calls.append("submit_plan")
        assert admitted is self.chain
        return self.plan_decision

    def scheduler_trace(self, lease):
        self.calls.append("scheduler_trace")
        return self.scheduler_decision

    def cancel_motion(self, lease):
        self.calls.append("cancel_motion")
        if self.raise_at == "cancel_motion":
            raise RuntimeError("cancel failed")
        return True

    def record_revocation(self, lease, phase, **details):
        self.calls.append(("revocation", phase, lease.attempt_id, details))
        return True

    def confirm_no_controller_goal(self, lease):
        self.calls.append("confirm_no_controller_goal")
        return self.goal_confirmed

    def recover(self, worker_id, generation, deadline_monotonic_s):
        self.calls.append("recover")
        self.recovery_deadlines.append(deadline_monotonic_s)
        return self.recovery_succeeds


class Results:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.calls = []
        self.advance_receipt_to_deadline = False

    def seal_attempt(self, lease, decision):
        self.calls.append(("seal_attempt", decision.status, decision.reason))
        self.coordinator.sealed_statuses.append(decision.status)
        return f"/{lease.attempt_id}/sealed"

    def seal_validation(self, lease, decision):
        self.calls.append(("seal_validation", decision.status, decision.reason))
        self.coordinator.sealed_statuses.append(decision.status)
        return f"/{lease.attempt_id}/sealed-validation"

    def write_recovery_receipt(
            self, lease, *, succeeded, generation,
            deadline_monotonic_s=None, clock=None):
        if self.advance_receipt_to_deadline and deadline_monotonic_s is not None:
            self.coordinator.clock.now = deadline_monotonic_s
            if clock() >= deadline_monotonic_s:
                raise TimeoutError("receipt deadline")
        self.calls.append((
            "recovery_receipt", succeeded, generation, deadline_monotonic_s))
        return f"/recoveries/{lease.attempt_id}-{generation}"

    def verify_recovery_receipt(
            self, location, lease, *, succeeded, generation,
            deadline_monotonic_s=None, clock=None):
        self.calls.append((
            "verify_recovery_receipt", succeeded, generation,
            deadline_monotonic_s,
        ))
        return True


class Fake:
    def __init__(self, mode=RunMode.EXECUTE, *, point_count=1):
        self.clock = Clock()
        self.coordinator = Coordinator(mode, self.clock, point_count=point_count)
        self.broker = Broker()
        self.runtime = Runtime(mode)
        self.results = Results(self.coordinator)

    def ports(self):
        return {
            "coordinator": self.coordinator,
            "broker": self.broker,
            "runtime": self.runtime,
            "results": self.results,
            "clock": self.clock,
            "config": CONFIG,
            "worker_id": "w1",
            "generation": 1,
        }


def event_names(fake):
    return [entry[0] for entry in fake.coordinator.calls if entry[0] != "HEARTBEAT"]


def test_a_committed_status_that_differs_from_the_teacher_decision_is_refused_not_adopted():
    """The old contract let an authoritative failing QC turn the worker's PASSED into FAILED (a `qc_downgrade`).

    The committed status is the Teacher's own; a commit that disagrees with the sealed decision is a protocol fault.
    """
    fake=Fake()
    original=fake.coordinator.commit_result
    def committed_failure(lease,location,*,request_key):
        reply=original(lease,location,request_key=request_key)
        reply['status']=AttemptStatus.FAILED
        return reply
    fake.coordinator.commit_result=committed_failure
    result=ParallelWorker(fake.ports()).run_one()
    assert fake.coordinator.sealed_statuses==[AttemptStatus.PASSED]
    assert result.terminal_status is None and result.stopped_reason=='TERMINAL_ACK_FAILED'
    assert result.recovered is False


def test_the_worker_has_no_qc_downgrade_path_left():
    import inspect
    from so101_demo.parallel_batch import worker as worker_module
    assert 'qc_downgrade' not in inspect.getsource(worker_module)


@pytest.mark.parametrize('claim,committed',[(AttemptStatus.FAILED,AttemptStatus.PASSED),
    (AttemptStatus.PASSED,AttemptStatus.INVALID),(AttemptStatus.INDETERMINATE,AttemptStatus.FAILED)])
def test_a_commit_ack_that_disagrees_with_the_sealed_decision_is_never_accepted(claim,committed):
    fake=Fake()
    fake.runtime.execute_decision=Decision(claim)
    original=fake.coordinator.commit_result
    def wrong_reply(lease,location,*,request_key):
        reply=original(lease,location,request_key=request_key);reply['status']=committed
        return reply
    fake.coordinator.commit_result=wrong_reply
    result=ParallelWorker(fake.ports()).run_one()
    assert result.terminal_status is None and result.stopped_reason=='TERMINAL_ACK_FAILED'


@pytest.mark.parametrize('prior_execution_failure', [False, True])
def test_terminal_seal_failure_preserves_first_bounded_original_refusal(prior_execution_failure):
    fake = Fake()
    if prior_execution_failure:
        fake.broker.raise_request = PermissionError('first request rejected\n' + 'é' * 600)
    def broken_seal(lease, decision):
        fake.results.calls.append(('seal_attempt', decision.status, decision.reason))
        raise OSError('terminal seal rejected\n' + 'é' * 600)
    fake.results.seal_attempt = broken_seal
    worker = ParallelWorker(fake.ports())
    result = worker.run_one()
    assert result.terminal_status is None and result.stopped_reason == 'TERMINAL_ACK_FAILED'
    assert result.recovered is False and worker._quarantined is True
    assert result.failure_boundary == ('request_model' if prior_execution_failure else 'seal_and_commit')
    assert result.failure_type == ('PermissionError' if prior_execution_failure else 'OSError')
    assert result.failure_message.startswith('first request rejected ' if prior_execution_failure
        else 'terminal seal rejected ')
    assert len(result.failure_message.encode('utf-8')) <= 512 and '\n' not in result.failure_message
    assert fake.results.calls[0][0] == 'seal_attempt' and fake.coordinator.recovery == []
    assert 'RESULT_COMMITTED' not in event_names(fake)


def test_worker_rejects_unregistered_workload_object():
    fake = Fake()
    ports = fake.ports()
    ports["workload"] = object()
    with pytest.raises(Exception, match="WORKLOAD_PORT_INVALID"):
        ParallelWorker(ports)


def test_prepare_for_start_is_idempotent_and_never_requests_a_lease():
    fake = Fake(RunMode.PLAN_ONLY)
    worker = ParallelWorker(fake.ports())

    assert worker.prepare_for_start() is True
    assert worker.prepare_for_start() is True
    assert fake.coordinator.calls == [("register_worker", "w1", 1)]
    assert fake.runtime.calls == ["worker_ready_gate"]


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (SimpleNamespace(point_id=None, terminal_status=None, recovered=False,
                         stopped_reason="NO_POINT"), False),
        (SimpleNamespace(point_id=None, terminal_status=None, recovered=False,
                         stopped_reason="STOP_REQUESTED"), False),
        (SimpleNamespace(point_id="p1", terminal_status=AttemptStatus.FAILED,
                         recovered=True, stopped_reason="POINT_TERMINAL"), False),
        (SimpleNamespace(point_id="p1", terminal_status=AttemptStatus.INVALID,
                         recovered=True, stopped_reason="INITIAL_GATE_FAILED"), True),
        (SimpleNamespace(point_id="p1", terminal_status=AttemptStatus.PASSED,
                         recovered=False, stopped_reason="POINT_TERMINAL"), True),
        (SimpleNamespace(point_id=None, terminal_status=None, recovered=False,
                         stopped_reason="WORKER_NOT_READY"), True),
    ],
)
def test_adaptive_worker_result_infrastructure_classification(result, expected):
    from so101_demo.parallel_batch.worker import adaptive_result_is_infrastructure

    assert adaptive_result_is_infrastructure(result) is expected


@pytest.mark.parametrize(
    "boundary,message",
    [
        ("reset_point", "reset failed"),
        ("point_initial_gate", "initial gate rejected second line"),
    ],
)
def test_initial_boundary_failure_reports_bounded_structured_diagnostic(
    boundary, message
):
    fake = Fake(RunMode.EXECUTE)
    fake.runtime.raise_at = boundary

    result = ParallelWorker(fake.ports()).run_one()

    assert result.stopped_reason == "INITIAL_GATE_FAILED"
    assert result.failure_boundary == boundary
    assert result.failure_type == "RuntimeError"
    assert result.failure_message == message
    assert len(result.failure_message.encode("utf-8")) <= 512
    assert "\n" not in result.failure_message


@pytest.mark.parametrize(
    "mode,boundary,target",
    [
        (RunMode.EXECUTE, "inference_snapshot", "runtime"),
        (RunMode.EXECUTE, "request_model", "broker"),
        (RunMode.EXECUTE, "admit_pose", "runtime"),
        (RunMode.EXECUTE, "execute_expert", "runtime"),
        (RunMode.PLAN_ONLY, "plan_expert", "runtime"),
    ],
)
def test_authorized_boundary_failure_reports_bounded_structured_diagnostic(
    mode, boundary, target
):
    fake = Fake(mode)
    message = "request rejected\n" + "é" * 600
    error = RuntimeError(message)
    if target == "broker":
        fake.broker.raise_request = error
    else:
        setattr(
            fake.runtime,
            boundary,
            lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
        )

    result = ParallelWorker(fake.ports()).run_one()

    assert result.stopped_reason == "POINT_TERMINAL"
    assert result.failure_boundary == boundary
    assert result.failure_type == "RuntimeError"
    assert result.failure_message.startswith("request rejected ")
    assert len(result.failure_message.encode("utf-8")) <= 512
    assert "\n" not in result.failure_message
    assert fake.results.calls[0][2] == "AUTHORIZATION_OR_PORT_FAILURE"


def test_broker_terminal_diagnostic_is_projected_without_changing_result_reason():
    fake = Fake(RunMode.EXECUTE)
    terminal = SimpleNamespace(
        perception_terminal=True,
        failure_type="BrokerResponse.INFRA_ERROR",
        failure_message="INPUT_OPENED_OWNER_MODE\n" + "é" * 600,
    )
    fake.broker.request_model = lambda *_args, **_kwargs: terminal
    fake.runtime.execute_decision = Decision(
        AttemptStatus.INVALID,
        reason="PERCEPTION_INFRA_ERROR",
        physical_action_proven_absent=True,
    )

    result = ParallelWorker(fake.ports()).run_one()

    assert result.failure_boundary == "request_model"
    assert result.failure_type == "BrokerResponse.INFRA_ERROR"
    assert result.failure_message.startswith("INPUT_OPENED_OWNER_MODE ")
    assert len(result.failure_message.encode("utf-8")) <= 512
    assert "\n" not in result.failure_message
    assert fake.results.calls[0][2] == "PERCEPTION_INFRA_ERROR"


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
    from so101_demo.parallel_batch.contracts import TeacherChannelTerminal

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
    from so101_demo.parallel_batch.contracts import TeacherChannelTerminal

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


def test_worker_composes_with_real_durable_coordinator_port(tmp_path):
    clock = Clock()
    request = BatchRequest(
        "batch-a", RunMode.EXECUTE, ("p1",), 1, 2, tmp_path,
    )
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
    from so101_demo.parallel_batch.worker import WorkerError
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


def _diagnostic_lines(captured, tag):
    return [json.loads(line[len(tag) + 1:]) for line in captured.splitlines()
            if line.startswith(tag + " ")]


def _watchdog_lease():
    return LeaseIdentity("batch-a", 1, "w1", 1, "p1", "p1-lease-1", 1, 10.0, 310.0)


def _watchdog_owner(revoked, **overrides):
    values = dict(
        _stop_requested=threading.Event(),
        _now=time.monotonic,
        _config=SimpleNamespace(heartbeat_timeout_s=0.05, heartbeat_interval_s=1.0),
        _ordered_receipts=False,
        _worker_id="w1",
        _heartbeat_transaction=lambda lease, deadline: lease,
        _accept_heartbeat=lambda ack, lease: True,
        _watchdog_revoked=lambda lease, reason: revoked.append(reason),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _run_watchdog(owner):
    from so101_demo.parallel_batch.worker import _HeartbeatWatchdog

    watchdog = _HeartbeatWatchdog(owner, _watchdog_lease())
    watchdog.start()
    watchdog._thread.join(2)
    assert not watchdog._thread.is_alive()
    return watchdog


def test_watchdog_exception_line_is_emitted_and_reason_is_unchanged(capfd):
    revoked = []

    def raising_acknowledged(ack, lease):
        raise PermissionError("X")

    owner = _watchdog_owner(revoked, _accept_heartbeat=raising_acknowledged)
    watchdog = _run_watchdog(owner)
    assert revoked == ["COORDINATOR_LOST"]
    assert watchdog.reason == "COORDINATOR_LOST"
    lines = _diagnostic_lines(capfd.readouterr().err, "WORKER_WATCHDOG_EXCEPTION")
    assert len(lines) == 1
    line = lines[0]
    assert line["reason"] == "COORDINATOR_LOST"
    assert line["worker_id"] == "w1"
    assert line["error_type"] == "PermissionError"
    assert line["error_message"] == "X"
    assert any(frame.endswith(":raising_acknowledged") for frame in line["frames"])
    assert len(line["frames"]) <= 12
    assert line["elapsed_s"] >= 0
    assert "now_s" in line


def test_watchdog_exception_line_uses_heartbeat_thread_traceback_and_bounds_message(capfd):
    revoked = []

    def failing_transaction(lease, deadline):
        raise RuntimeError("Y" * 1000)

    owner = _watchdog_owner(revoked, _heartbeat_transaction=failing_transaction)
    _run_watchdog(owner)
    assert revoked == ["COORDINATOR_LOST"]
    err = capfd.readouterr().err
    (line,) = _diagnostic_lines(err, "WORKER_WATCHDOG_EXCEPTION")
    assert line["error_type"] == "RuntimeError"
    assert line["error_message"] == "Y" * 300
    assert any(frame.endswith(":failing_transaction") for frame in line["frames"])
    assert all(len(row) < 4096 for row in err.splitlines())


def test_watchdog_timeout_line_is_emitted_without_frames(capfd):
    revoked = []
    release = threading.Event()

    def blocked(lease, deadline):
        release.wait(2)
        return lease

    owner = _watchdog_owner(revoked, _heartbeat_transaction=blocked)
    try:
        _run_watchdog(owner)
    finally:
        release.set()
    assert revoked == ["HEARTBEAT_ACK_TIMEOUT"]
    (line,) = _diagnostic_lines(capfd.readouterr().err, "WORKER_WATCHDOG_EXCEPTION")
    assert line["reason"] == "HEARTBEAT_ACK_TIMEOUT"
    assert line["worker_id"] == "w1"
    assert "frames" not in line
    assert line["elapsed_s"] >= 0.05


def test_watchdog_invalid_ack_line_is_emitted_without_frames(capfd):
    revoked = []
    owner = _watchdog_owner(revoked, _accept_heartbeat=lambda ack, lease: False)
    _run_watchdog(owner)
    assert revoked == ["HEARTBEAT_ACK_INVALID"]
    (line,) = _diagnostic_lines(capfd.readouterr().err, "WORKER_WATCHDOG_EXCEPTION")
    assert line["reason"] == "HEARTBEAT_ACK_INVALID"
    assert "frames" not in line


def test_watchdog_diagnostic_never_raises_when_stderr_is_broken(monkeypatch):
    class Broken:
        def write(self, text):
            raise OSError("closed")

        def flush(self):
            raise OSError("closed")

    monkeypatch.setattr("sys.stderr", Broken())
    revoked = []

    def raising_acknowledged(ack, lease):
        raise PermissionError("X")

    _run_watchdog(_watchdog_owner(revoked, _accept_heartbeat=raising_acknowledged))
    assert revoked == ["COORDINATOR_LOST"]


def test_current_heartbeat_exception_emits_one_line_and_reraises_same_object(capfd):
    fake = Fake()
    error = RuntimeError("coordinator down")
    fake.coordinator.heartbeat_reply = error
    worker = ParallelWorker(fake.ports())
    worker._active_lease = _watchdog_lease()
    with pytest.raises(RuntimeError) as raised:
        worker._current()
    assert raised.value is error
    (line,) = _diagnostic_lines(capfd.readouterr().err, "WORKER_CURRENT_HEARTBEAT_EXCEPTION")
    assert line["worker_id"] == "w1"
    assert line["error_type"] == "RuntimeError"
    assert line["error_message"] == "coordinator down"
    assert line["frames"]
    assert "elapsed_s" in line and "now_s" in line


def test_current_heartbeat_exception_lines_are_bounded_per_worker(capfd):
    fake = Fake()
    fake.coordinator.heartbeat_reply = RuntimeError("down")
    worker = ParallelWorker(fake.ports())
    worker._active_lease = _watchdog_lease()
    for _ in range(25):
        with pytest.raises(RuntimeError):
            worker._current()
    lines = _diagnostic_lines(capfd.readouterr().err, "WORKER_CURRENT_HEARTBEAT_EXCEPTION")
    assert len(lines) == 20


# ---- D8f: a fence or terminal enable failure after the start ACK and before motion is a started attempt ----

def _capture_sealed_decisions(fake):
    sealed = []
    original = fake.results.seal_attempt
    def seal(lease, decision):
        sealed.append(decision)
        return original(lease, decision)
    fake.results.seal_attempt = seal
    return sealed


def test_a_pre_motion_teacher_refusal_after_the_start_ack_is_committed_as_a_teacher_attempt_that_did_not_pass():
    from so101_demo.parallel_batch.contracts import TeacherPreMotionRefused
    from so101_demo.parallel_batch.dynamic_manifest import teacher_attempt_status
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    diagnostics = {"start_acknowledged": True, "broker_motion_enabled": False, "goal_dispatched": False}
    def refuse(lease, chain):
        raise TeacherPreMotionRefused("TEACHER_RESET_BINDING_SOURCE_INVALID", diagnostics)
    fake.runtime.admit_pose = refuse
    result = ParallelWorker(fake.ports()).run_one()
    assert result.stopped_reason == "POINT_TERMINAL" and result.failure_boundary == "admit_pose"
    (decision,) = sealed
    assert decision.status is AttemptStatus.INDETERMINATE
    assert (decision.teacher_execution_status, decision.teacher_task_result) == ("INDETERMINATE", "UNCONFIRMED")
    assert teacher_attempt_status(decision.teacher_execution_status, decision.teacher_task_result) is decision.status
    assert decision.act_data_status == "INVALID"
    assert decision.reason.startswith("TEACHER_FENCED_BEFORE_MOTION:TEACHER_RESET_BINDING_SOURCE_INVALID")
    assert decision.act_data_reason == decision.reason
    assert result.terminal_status is AttemptStatus.INDETERMINATE
    names = event_names(fake)
    assert "ATTEMPT_STARTED" in names or any("START" in name for name in names)
    assert "FINALIZING_STARTED" in names and "RESULT_COMMITTED" in names, "committed through the normal path"
    assert "submit_motion" not in fake.runtime.calls, "no motion was ever submitted"


def test_started_non_pass_outcomes_count_in_the_teacher_attempt_denominator_and_invalid_does_not():
    from so101_demo.parallel_batch import contracts
    assert AttemptStatus.INDETERMINATE in contracts._TEACHER_STARTED and AttemptStatus.FAILED in contracts._TEACHER_STARTED
    assert AttemptStatus.INVALID not in contracts._TEACHER_STARTED


def test_the_pre_motion_result_is_exactly_the_manifest_free_contract_the_result_store_already_accepts(tmp_path):
    from so101_demo.act.result_store import _check_teacher_manifest, _teacher_claim
    claim = _teacher_claim({"execution_status": "INDETERMINATE", "task_result": "UNCONFIRMED",
                            "data_status": "INVALID", "data_reason": "TEACHER_FENCED_BEFORE_MOTION:X"})
    # an INDETERMINATE/UNCONFIRMED claim asserts nothing positive and needs no Teacher manifest
    assert _check_teacher_manifest(tmp_path / "dynamic" / "dynamic-execute-manifest.json", claim) is None


@pytest.mark.parametrize("boundary,patch", [("reset_point", "reset_point"), ("point_initial_gate", "point_initial_gate")])
def test_a_failure_before_the_start_ack_stays_invalid_even_for_a_teacher_refusal(boundary, patch):
    from so101_demo.parallel_batch.contracts import TeacherPreMotionRefused
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    def refuse(*args, **kwargs):
        raise TeacherPreMotionRefused("TEACHER_CHANNEL_FENCED")
    setattr(fake.runtime, patch, refuse)
    result = ParallelWorker(fake.ports()).run_one()
    assert result.stopped_reason == "INITIAL_GATE_FAILED" and result.failure_boundary == boundary
    (decision,) = sealed
    assert decision.status is AttemptStatus.INVALID
    assert not hasattr(decision, "teacher_execution_status")
    assert "submit_motion" not in fake.runtime.calls


def test_an_ordinary_pose_admission_failure_keeps_its_invalid_path():
    fake = Fake(RunMode.EXECUTE)
    sealed = _capture_sealed_decisions(fake)
    def refuse(lease, chain):
        raise RuntimeError("TEACHER_CONSUMER_START_AUTHORITY_UNAVAILABLE")
    fake.runtime.admit_pose = refuse
    ParallelWorker(fake.ports()).run_one()
    (decision,) = sealed
    assert decision.status is AttemptStatus.INVALID and not hasattr(decision, "teacher_task_result")
