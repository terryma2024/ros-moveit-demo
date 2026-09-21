"""Compose a macOS W1 campaign: one slot, one Worker, one ROS domain, one named profile.

Task 7 of the macOS service campaign closure plan. The design's support matrix has exactly two W1
profiles - v5 is ``MPS_W1_FULL_RESTART_RETRY`` and v6 is ``MPS_W1_FIRST_PASS`` - and each admits
exactly one combination of ``(schema_version, execution_profile, batch_kind, worker_count)``. This
module is the W1 counterpart of :mod:`so101_demo.parallel_batch.w2_composition`, and it mirrors
that module's structure and its honesty:

* the loader is shared (`w2_composition.load_execution_config`), so the installed v5/v6 YAML takes
  the same MPS path the v4 document takes and a Linux host refuses all three;
* a W1 composition is **not** a capacity calculation. One slot exists because the platform claim
  is exactly one Worker, never because one point was selected: `selected_point_ids` is recorded
  and handed to the durable queue, and a plan is byte-identical whether one point or ten were
  chosen;
* nothing here invents a budget, qualification, promotion or forecast field. The manifest records
  the resolved platform values, the profile, the batch kind it admits, the Broker identity, the
  model provenance and the evidence paths - and nothing it cannot prove.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .contracts import (
    BatchKindV2,
    ExecutionProfile,
    ParallelRuntimeConfigV5,
    ParallelRuntimeConfigV6,
    require_v5_execution,
    require_v6_execution,
)
from .w2_composition import (
    CompositionError,
    _sha256_file,
)

#: Exact W1. Any other count is a different platform claim these profiles do not make.
EXACT_W1_WORKERS = 1

#: The profile names the routing table and the manifests use.
MPS_W1_FULL_RESTART_RETRY = str(ExecutionProfile.MPS_W1_FULL_RESTART_RETRY)
MPS_W1_FIRST_PASS = str(ExecutionProfile.MPS_W1_FIRST_PASS)

#: The only batch kind each profile admits. It is carried by the request, never inferred.
W1_RETRY_BATCH_KIND = str(BatchKindV2.FULL_RESTART_RETRY)
W1_FIRST_PASS_BATCH_KIND = str(BatchKindV2.FIRST_PASS)

#: The schema-v5/v6 document names, for the manifest's provenance fields.
V5_CONFIG_BASENAME = "parallel_batch_v5_macos_mps_w1_retry.yaml"
V6_CONFIG_BASENAME = "parallel_batch_v6_macos_mps_w1_first_pass.yaml"


@dataclass(frozen=True)
class W1Slots:
    """The single fixed slot as *capacity*. It owns no point.

    One slot exists because the platform claim is exact W1, so the campaign still runs one Worker
    even when nothing was selected. Which point that Worker executes is decided per lease by the
    durable shared queue (`parallel_batch.queue`), exactly as for W2.
    """

    slot_ids: tuple[str, ...]

    @property
    def assigned_points(self) -> tuple[tuple[str, str | None], ...]:
        """Compatibility view: capacity slots have no assigned point."""

        return tuple((slot, None) for slot in self.slot_ids)

    @property
    def idle_slots(self) -> tuple[str, ...]:
        return self.slot_ids

    def to_document(self) -> dict:
        return {
            "slot_ids": list(self.slot_ids),
            "assigned_points": [{"slot_id": slot, "point_id": None}
                                for slot in self.slot_ids],
            "idle_slots": list(self.idle_slots),
            "capacity_only": True,
        }


def exact_w1_slots() -> W1Slots:
    """Return the single W1 capacity slot; point assignment belongs to the queue."""

    return W1Slots(slot_ids=("slot-0",))


@dataclass(frozen=True)
class W1CampaignPlan:
    """The resolved W1 plan a supervisor can execute and a manifest can record."""

    schema_version: int
    execution_profile: str
    batch_kind: str
    campaign_id: str
    batch_id: str
    config_path: str
    config_sha256: str
    accelerator: str
    accelerator_selector: str
    requested_device: str
    allow_cpu_fallback: bool
    ipc_transport: str
    mujoco_gl: str
    worker_count: int
    slots: W1Slots
    broker_pid: int | None
    broker_birth_identity: int | None
    model_provenance: Mapping[str, object]
    snapshot_root: str
    supervisor_receipt_path: str
    start_guard_timeout_s: float
    mps_minimum_headroom_bytes: int | None
    mps_process_memory_fraction: float | None
    max_input_snapshot_bytes: int
    broker_max_frame_bytes: int
    ros_domain_ids: tuple[int, ...]
    config: object
    #: The ordered selection this campaign must execute. It is recorded by the composition and
    #: consumed by the durable shared queue; the single slot above holds no point.
    selected_point_ids: tuple[str, ...] = ()

    def to_document(self) -> dict:
        """The manifest projection: resolved values only, never `auto`, never a budget."""

        return {
            "schema_version": self.schema_version,
            "execution_profile": self.execution_profile,
            "batch_kind": self.batch_kind,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "config_path": self.config_path,
            "config_sha256": self.config_sha256,
            "accelerator": self.accelerator,
            "accelerator_selector": self.accelerator_selector,
            "requested_device": self.requested_device,
            "allow_cpu_fallback": self.allow_cpu_fallback,
            "ipc_transport": self.ipc_transport,
            "mujoco_gl": self.mujoco_gl,
            "worker_count": self.worker_count,
            "slots": self.slots.to_document(),
            "broker_pid": self.broker_pid,
            "broker_birth_identity": self.broker_birth_identity,
            "model_provenance": dict(self.model_provenance),
            "snapshot_root": self.snapshot_root,
            "supervisor_receipt_path": self.supervisor_receipt_path,
            "start_guard_timeout_s": self.start_guard_timeout_s,
            "mps_minimum_headroom_bytes": self.mps_minimum_headroom_bytes,
            "mps_process_memory_fraction": self.mps_process_memory_fraction,
            "max_input_snapshot_bytes": self.max_input_snapshot_bytes,
            "broker_max_frame_bytes": self.broker_max_frame_bytes,
            "ros_domain_ids": list(self.ros_domain_ids),
            "selected_point_ids": list(self.selected_point_ids),
        }


def _compose_w1(*, config, config_path: Path, campaign_id: str, batch_id: str,
                selected_point_ids: tuple[str, ...], evidence_root: Path,
                schema_version: int, execution_profile: str, batch_kind: str,
                config_class, config_basename: str,
                broker_pid: int | None, broker_birth_identity: int | None) -> W1CampaignPlan:
    """Resolve one W1 campaign. Refuses any other profile, schema or platform claim."""

    if not isinstance(config, config_class):
        raise CompositionError(
            "CONFIG_SCHEMA_MISMATCH",
            f"{execution_profile} requires {config_basename}, not {type(config).__name__}",
        )
    if schema_version == 5:
        require_v5_execution(5, config.schema_version)
    else:
        require_v6_execution(6, config.schema_version)
    if not isinstance(campaign_id, str) or not campaign_id:
        raise CompositionError("CAMPAIGN_ID", repr(campaign_id))
    root = Path(evidence_root)
    if not root.is_absolute():
        raise CompositionError("EVIDENCE_ROOT", "must be absolute")

    # Exact W1. The count comes from the profile, never from the length of the selection: that is
    # what keeps "a plan is the same plan whether one point or ten were selected" a checked fact.
    worker_count = EXACT_W1_WORKERS
    if config.worker_count != worker_count:
        raise CompositionError("PLATFORM_WORKER_COUNT_UNSUPPORTED", str(config.worker_count))
    slots = exact_w1_slots()
    if worker_count != len(slots.slot_ids):
        raise CompositionError(
            "SLOT_COUNT_MISMATCH", f"{worker_count} workers for {len(slots.slot_ids)} slots")
    if len(config.ros_domain_ids) != worker_count:
        raise CompositionError(
            "ROS_DOMAIN_IDS", f"{len(config.ros_domain_ids)} domains for {worker_count} workers")

    plan = W1CampaignPlan(
        schema_version=schema_version,
        execution_profile=execution_profile,
        batch_kind=batch_kind,
        campaign_id=campaign_id,
        batch_id=batch_id,
        config_path=str(config_path),
        config_sha256=_sha256_file(config_path),
        accelerator=str(config.accelerator.kind),
        accelerator_selector=config.accelerator.resolved_selector,
        requested_device=config.requested_device,
        allow_cpu_fallback=config.allow_cpu_fallback,
        ipc_transport=str(config.ipc_transport),
        mujoco_gl=config.mujoco_gl,
        worker_count=worker_count,
        slots=slots,
        broker_pid=broker_pid,
        broker_birth_identity=broker_birth_identity,
        model_provenance={
            "yolo_model_id": config.yolo_model_id,
            "yolo_weights_sha256": config.yolo_weights_sha256,
            "grounded_sam_manifest_sha256": config.grounded_sam_manifest_sha256,
            "yolo_imgsz": config.yolo_imgsz,
        },
        snapshot_root=str(root / "inference-inputs"),
        supervisor_receipt_path=str(root / "supervisor" / "owner-receipt.json"),
        start_guard_timeout_s=config.start_guard.timeout_s,
        mps_minimum_headroom_bytes=config.mps_minimum_headroom_bytes,
        mps_process_memory_fraction=config.mps_process_memory_fraction,
        max_input_snapshot_bytes=config.max_input_snapshot_bytes,
        broker_max_frame_bytes=config.broker_max_frame_bytes,
        ros_domain_ids=tuple(config.ros_domain_ids),
        config=config,
        selected_point_ids=tuple(selected_point_ids),
    )
    assert_no_host_platform_calls(plan)
    return plan


def compose_w1_retry(*, config, config_path: Path, campaign_id: str, batch_id: str,
                     selected_point_ids: tuple[str, ...], evidence_root: Path,
                     broker_pid: int | None = None,
                     broker_birth_identity: int | None = None) -> W1CampaignPlan:
    """Resolve the v5 W1 `FULL_RESTART_RETRY` campaign. Refuses every other document."""

    return _compose_w1(
        config=config, config_path=config_path, campaign_id=campaign_id, batch_id=batch_id,
        selected_point_ids=selected_point_ids, evidence_root=evidence_root, schema_version=5,
        execution_profile=MPS_W1_FULL_RESTART_RETRY, batch_kind=W1_RETRY_BATCH_KIND,
        config_class=ParallelRuntimeConfigV5, config_basename=V5_CONFIG_BASENAME,
        broker_pid=broker_pid, broker_birth_identity=broker_birth_identity)


def compose_w1_first_pass(*, config, config_path: Path, campaign_id: str, batch_id: str,
                          selected_point_ids: tuple[str, ...], evidence_root: Path,
                          broker_pid: int | None = None,
                          broker_birth_identity: int | None = None) -> W1CampaignPlan:
    """Resolve the v6 W1 `FIRST_PASS` campaign. Refuses every other document."""

    return _compose_w1(
        config=config, config_path=config_path, campaign_id=campaign_id, batch_id=batch_id,
        selected_point_ids=selected_point_ids, evidence_root=evidence_root, schema_version=6,
        execution_profile=MPS_W1_FIRST_PASS, batch_kind=W1_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigV6, config_basename=V6_CONFIG_BASENAME,
        broker_pid=broker_pid, broker_birth_identity=broker_birth_identity)


def assert_no_host_platform_calls(plan: W1CampaignPlan) -> None:
    """The Darwin plan must not claim an NVML or `/proc/self/fd` dependency, and vice versa."""

    from .contracts import IpcTransport

    if plan.accelerator == "mps":
        if plan.ipc_transport != str(IpcTransport.DARWIN_PRIVATE_PATH_UNIX):
            raise CompositionError("PLATFORM_COMBINATION", plan.ipc_transport)
        if plan.mujoco_gl != "cgl":
            raise CompositionError("PLATFORM_COMBINATION", plan.mujoco_gl)
        if plan.mps_minimum_headroom_bytes is None:
            raise CompositionError("PLATFORM_COMBINATION", "missing MPS headroom floor")
    elif plan.accelerator == "cuda":
        if plan.ipc_transport != str(IpcTransport.PROC_FD_UNIX):
            raise CompositionError("PLATFORM_COMBINATION", plan.ipc_transport)
        if plan.mujoco_gl != "egl":
            raise CompositionError("PLATFORM_COMBINATION", plan.mujoco_gl)
        if plan.mps_minimum_headroom_bytes is not None:
            raise CompositionError("PLATFORM_COMBINATION", "CUDA plan carries an MPS threshold")
    else:
        raise CompositionError("ACCELERATOR_KIND", plan.accelerator)
