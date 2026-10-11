"""Fakes and helpers shared by the parallel batch worker tests."""

from dataclasses import dataclass
import threading
from types import SimpleNamespace

from paths import PACKAGE_ROOT

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    RunMode,
    ValidationStatus,
    WorkerState,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.contracts.linux_cuda import (
    load_parallel_runtime_config_linux_cuda,
)

CONFIG = load_parallel_runtime_config_linux_cuda(
    PACKAGE_ROOT / "config/mujoco/parallel_batch_linux_cuda.yaml"
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
