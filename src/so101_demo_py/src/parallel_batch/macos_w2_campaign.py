"""A composed macOS MPS W2 campaign: the pieces from Tasks 3-9 driven as one runnable unit.

Tasks 2-9 produced separately tested libraries (supervisor, MPS broker bootstrap, private Unix
address, permission-only v4 RPC, immutable snapshots, one-time request registry, whole-pool
recovery). Nothing yet composed them, which is why the Task 13 runtime smoke had to hand-assemble
its own sequence. This module is that composition, and it is the macOS counterpart of the Linux
container path in `parallel_ros_runtime`.

The composition is deliberately explicit about the two things the design cares most about:

* the Coordinator's one-time request table is consulted for **every** broker response, so a late,
  duplicate or foreign result cannot reach a caller;
* a broker failure runs the closed seven-step rebuild from :mod:`pool_recovery`, so a surviving
  Worker is never re-pointed at a new endpoint.

Everything platform-specific is injected: model factories, the ROS port that cancels controller
goals and observes their absence, and the process ports. That keeps the Linux path untouched and
lets the tests drive every refusal branch without hardware.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .campaign_supervisor import ACTIVE, CampaignSupervisor
from .inference_registry import InferenceRegistry
from .input_snapshot import SnapshotRegistry, SnapshotStore
from .pool_recovery import INFRASTRUCTURE_FAILURE, BrokerPoolRecovery, RecoveryFacts
from .w2_composition import W2CampaignPlan, assert_no_host_platform_calls

#: Roles the composed campaign spawns. Exact W2: one broker, two workers.
W2_ROLES = ("broker", "worker-0", "worker-1")


class MacosW2CampaignError(RuntimeError):
    """The composed campaign cannot proceed. Never a warning."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class CampaignInventory:
    """What a read-only pre-flight found. A duplicate stack stops the campaign here."""

    claim_held: bool
    live_endpoints: tuple[str, ...]
    owned_processes: tuple[int, ...]
    existing_campaign_dirs: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.claim_held or self.live_endpoints or self.owned_processes
                    or self.existing_campaign_dirs)


def read_inventory(*, claim_path: Path, ipc_base: Path) -> CampaignInventory:
    """Read the host state before touching anything, without signalling a single process."""

    return CampaignInventory(
        claim_held=Path(claim_path).exists(),
        live_endpoints=(),
        owned_processes=(),
        existing_campaign_dirs=tuple(
            sorted(str(item) for item in Path(ipc_base).glob("b-*"))
        ) if Path(ipc_base).is_dir() else (),
    )


@dataclass
class CampaignPorts:
    """Everything platform-specific the composition needs, injected."""

    #: Build one model for the broker. The real caller passes the detector factory.
    model_factories: Mapping[str, Callable[[], object]]
    #: Cancel controller goals and independently observe their absence.
    cancel_goals: Callable[[], bool] = lambda: True
    confirm_absence: Callable[[], bool] = lambda: True
    #: Stop one worker safely by name.
    stop_worker: Callable[[str], bool] = lambda _name: True
    #: Wall clock, for receipts and deadlines.
    clock: Callable[[], float] = time.monotonic


@dataclass
class CampaignOutcome:
    """The result of one composed run, with the evidence a checkpoint needs."""

    status: str
    plan: W2CampaignPlan | None
    ready_models: tuple[str, ...] = ()
    worker_states: tuple[tuple[str, str], ...] = ()
    served: int = 0
    refused: tuple[tuple[str, str], ...] = ()
    cleanup_complete: bool = False
    recovery_trace: tuple[str, ...] = ()
    detail: str = ""

    def to_document(self) -> dict:
        return {
            "status": self.status,
            "plan": None if self.plan is None else self.plan.to_document(),
            "ready_models": list(self.ready_models),
            "worker_states": [{"slot": s, "state": st} for s, st in self.worker_states],
            "served": self.served,
            "refused": [{"request_id": r, "reason": r_}
                        for r, r_ in self.refused],
            "cleanup_complete": self.cleanup_complete,
            "recovery_trace": list(self.recovery_trace),
            "detail": self.detail,
        }


class MacosW2Campaign:
    """One exact-W2 macOS MPS campaign, from pre-flight to exact cleanup."""

    def __init__(self, *, plan: W2CampaignPlan, address, supervisor: CampaignSupervisor,
                 ports: CampaignPorts, registry: InferenceRegistry | None = None,
                 snapshots: SnapshotRegistry | None = None) -> None:
        if not isinstance(plan, W2CampaignPlan):
            raise MacosW2CampaignError("PLAN_TYPE", type(plan).__name__)
        if plan.accelerator != "mps":
            raise MacosW2CampaignError("PLAN_NOT_MPS", plan.accelerator)
        if plan.worker_count != len(plan.slots.slot_ids):
            raise MacosW2CampaignError("SLOT_COUNT_MISMATCH", str(plan.worker_count))
        assert_no_host_platform_calls(plan)
        self.plan = plan
        self.address = address
        self.supervisor = supervisor
        self.ports = ports
        self.registry = registry or InferenceRegistry(campaign_id=plan.campaign_id)
        self.snapshots = snapshots or SnapshotRegistry(
            store=SnapshotStore(root=Path(plan.snapshot_root),
                                max_snapshot_bytes=plan.max_input_snapshot_bytes))

    # -- admission -----------------------------------------------------------------------

    def admit_response(self, request_id: str, *, broker_pid: int,
                       broker_birth_identity: int, output_sha256: str | None = None):
        """Route every broker response through the one-time table before it can be used."""

        return self.registry.consume_result(
            request_id, output_sha256=output_sha256, broker_pid=broker_pid,
            broker_birth_identity=broker_birth_identity)

    def request_binding(self, *, request_id: str, slot_id: str, point_id: str, attempt: int,
                        input_sha256: str, deadline_s: float, broker_pid: int,
                        broker_birth_identity: int):
        """Register one request, binding it to the current owned broker identity."""

        return self.registry.register_request(
            request_id=request_id, slot_id=slot_id, point_id=point_id, attempt=attempt,
            model_id=self.plan.model_provenance["yolo_model_id"], input_sha256=input_sha256,
            deadline_monotonic_ns=time.monotonic_ns() + int(deadline_s * 1_000_000_000),
            broker_pid=broker_pid, broker_birth_identity=broker_birth_identity)

    # -- recovery ------------------------------------------------------------------------

    def rebuild_after_broker_failure(self, *, facts: RecoveryFacts, create_campaign_root,
                                     spawn_broker, spawn_worker, coordinator_decision,
                                     reap_owned_processes) -> tuple[str, ...]:
        """Run the closed seven-step rebuild for one broker failure."""

        recovery = BrokerPoolRecovery(
            facts=facts,
            remove_active_request=lambda request_id: (
                (request_id,) if self.registry.cancel_request_safe(
                    request_id, reason="broker failure") else ()
            ),
            mark_infrastructure_failure=lambda point, attempt, kind: None,
            stop_worker=self.ports.stop_worker,
            cancel_goals=self.ports.cancel_goals,
            confirm_absence=self.ports.confirm_absence,
            reap_owned_processes=reap_owned_processes,
            create_campaign_root=create_campaign_root,
            spawn_broker=spawn_broker,
            spawn_worker=spawn_worker,
            coordinator_decision=coordinator_decision,
        )
        outcome = recovery.recover()
        return outcome.trace

    def infrastructure_failure_document(self, *, request_id: str, point_id: str,
                                        attempt: int) -> dict:
        """The disposition for an interrupted inference. Never a business status."""

        return {"kind": INFRASTRUCTURE_FAILURE, "campaign_id": self.plan.campaign_id,
                "request_id": request_id, "point_id": point_id, "attempt": attempt,
                "business_status": None}

    # -- cleanup -------------------------------------------------------------------------

    def release_snapshots(self, *, reason: str) -> tuple[str, ...]:
        """Release every live snapshot. They become deletion candidates, never deletions."""

        released = self.snapshots.invalidate_all(reason=reason)
        return tuple(item.relative_path for item in released)
