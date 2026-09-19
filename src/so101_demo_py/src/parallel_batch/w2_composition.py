"""Compose an exact-W2 macOS MPS campaign: the resolved plan and the manifest it must record.

Task 10 of the macOS MPS / private IPC plan. Neither the CLI nor the resource allocator may keep
its v3-only schema gate, because that would make the whole v4 contract unreachable; but widening
that gate must not change one byte of v3 behavior. This module does both:

* `load_execution_config` keeps the v3 document exactly as it was and adds the v4 branch;
* `load_execution_config_for_schema` refuses a v4 *platform* claim on a host that cannot honour it,
  which is what makes "Linux v4 is not executed here" a checked fact;
* `compose_w2_campaign` produces the resolved plan and the manifest fields the design requires:
  resolved accelerator, IPC transport, GL backend, exact worker count, Broker identity, model
  provenance, snapshot root and the supervisor receipt.

The composition is deliberately a pure function over a config object. Spawning belongs to the
supervisor and the recovery path; deciding *what* to spawn and *what to record* belongs here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .contracts import (
    AcceleratorKind,
    ContractError,
    IpcTransport,
    ParallelRuntimeConfigV3,
    ParallelRuntimeConfigV4,
    load_parallel_runtime_config_v3,
    load_parallel_runtime_config_v4,
    require_v3_execution,
    require_v4_execution,
)

#: Exact W2. The design's platform claim is this number and no other.
EXACT_W2_WORKERS = 2

#: The schema-v4 document name, for the manifest's provenance fields.
V4_CONFIG_BASENAME = "parallel_batch_v4_macos_mps_w2.yaml"


class CompositionError(RuntimeError):
    """An exact-W2 campaign cannot be composed from these inputs."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def load_execution_config(path: Path):
    """Load the active execution document: v3 unchanged, v4 added, nothing else widened."""

    import yaml

    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    version = document.get("schema_version") if isinstance(document, dict) else None
    if version == 3:
        return load_parallel_runtime_config_v3(Path(path))
    if version == 4:
        return load_parallel_runtime_config_v4(Path(path))
    raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")


def load_execution_config_for_schema(path: Path, *, platform: str | None = None):
    """Load a document and refuse a platform combination this host cannot execute.

    The Darwin `mps + darwin_private_path_unix` combination may only be executed on Darwin, and
    the Linux `cuda + proc_fd_unix` combination may only be executed on Linux. This is what keeps
    "the Linux v4 combination is retained in the contract but not executed in this task" honest:
    asking for it here fails loudly instead of silently attempting an impossible launch.
    """

    config = load_execution_config(path)
    if not isinstance(config, ParallelRuntimeConfigV4):
        return config
    host = sys.platform if platform is None else platform
    darwin_combination = config.accelerator.kind is AcceleratorKind.MPS
    if darwin_combination and host != "darwin":
        raise CompositionError(
            "PLATFORM_HOST_MISMATCH",
            f"the MPS combination cannot be executed on {host!r}",
        )
    if not darwin_combination and host == "darwin":
        raise CompositionError(
            "PLATFORM_HOST_MISMATCH",
            f"the CUDA/NVML combination cannot be executed on {host!r}",
        )
    return config


@dataclass(frozen=True)
class W2Slots:
    """The two fixed slots. They exist even when there are fewer points than slots."""

    slot_ids: tuple[str, ...]
    assigned_points: tuple[tuple[str, str | None], ...]

    @property
    def idle_slots(self) -> tuple[str, ...]:
        return tuple(slot for slot, point in self.assigned_points if point is None)

    def to_document(self) -> dict:
        return {
            "slot_ids": list(self.slot_ids),
            "assigned_points": [{"slot_id": slot, "point_id": point}
                                for slot, point in self.assigned_points],
            "idle_slots": list(self.idle_slots),
        }


def exact_w2_slots(selected_point_ids: tuple[str, ...]) -> W2Slots:
    """Always two slots; points are assigned in order and the rest stay idle.

    The design is explicit that this is not a capacity calculation: two slots exist because the
    platform claim is exact W2, so a one-point campaign still runs two Workers and leaves one
    idle rather than silently becoming W1.
    """

    ids = tuple(selected_point_ids)
    assignments = []
    for index, slot in enumerate(("slot-0", "slot-1")):
        assignments.append((slot, ids[index] if index < len(ids) else None))
    return W2Slots(slot_ids=("slot-0", "slot-1"), assigned_points=tuple(assignments))


@dataclass(frozen=True)
class W2CampaignPlan:
    """The resolved plan a supervisor can execute and a manifest can record."""

    schema_version: int
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
    slots: W2Slots
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

    def to_document(self) -> dict:
        """The manifest projection: resolved values only, never `auto`."""

        return {
            "schema_version": self.schema_version,
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
        }


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compose_w2_campaign(*, config, config_path: Path, campaign_id: str, batch_id: str,
                        selected_point_ids: tuple[str, ...], evidence_root: Path,
                        broker_pid: int | None = None,
                        broker_birth_identity: int | None = None) -> W2CampaignPlan:
    """Resolve one exact-W2 campaign. Refuses anything that is not exact W2."""

    if not isinstance(config, (ParallelRuntimeConfigV3, ParallelRuntimeConfigV4)):
        raise CompositionError("CONFIG_TYPE", type(config).__name__)
    if not isinstance(campaign_id, str) or not campaign_id:
        raise CompositionError("CAMPAIGN_ID", repr(campaign_id))
    root = Path(evidence_root)
    if not root.is_absolute():
        raise CompositionError("EVIDENCE_ROOT", "must be absolute")

    if isinstance(config, ParallelRuntimeConfigV4):
        require_v4_execution(4, config.schema_version)
        if config.worker_count != EXACT_W2_WORKERS:
            raise CompositionError(
                "PLATFORM_WORKER_COUNT_UNSUPPORTED", str(config.worker_count))
        accelerator = str(config.accelerator.kind)
        selector = config.accelerator.resolved_selector
        ipc_transport = str(config.ipc_transport)
        mujoco_gl = config.mujoco_gl
        worker_count = config.worker_count
        headroom = config.mps_minimum_headroom_bytes
        fraction = config.mps_process_memory_fraction
        snapshot_limit = config.max_input_snapshot_bytes
        requested_device = config.requested_device
        allow_cpu_fallback = config.allow_cpu_fallback
    else:
        require_v3_execution(3, config.schema_version)
        accelerator = "cuda"
        selector = f"{config.gpu_device.selector_kind}:{config.gpu_device.selector}"
        ipc_transport = str(IpcTransport.PROC_FD_UNIX)
        mujoco_gl = "egl"
        worker_count = EXACT_W2_WORKERS
        headroom = None
        fraction = None
        snapshot_limit = 0
        requested_device = config.requested_device
        allow_cpu_fallback = config.allow_cpu_fallback

    slots = exact_w2_slots(tuple(selected_point_ids))
    if worker_count != len(slots.slot_ids):
        raise CompositionError(
            "SLOT_COUNT_MISMATCH", f"{worker_count} workers for {len(slots.slot_ids)} slots")

    model_provenance = {
        "yolo_model_id": config.yolo_model_id,
        "yolo_weights_sha256": config.yolo_weights_sha256,
        "grounded_sam_manifest_sha256": config.grounded_sam_manifest_sha256,
        "yolo_imgsz": config.yolo_imgsz,
    }

    return W2CampaignPlan(
        schema_version=config.schema_version,
        campaign_id=campaign_id,
        batch_id=batch_id,
        config_path=str(config_path),
        config_sha256=_sha256_file(config_path),
        accelerator=accelerator,
        accelerator_selector=selector,
        requested_device=requested_device,
        allow_cpu_fallback=allow_cpu_fallback,
        ipc_transport=ipc_transport,
        mujoco_gl=mujoco_gl,
        worker_count=worker_count,
        slots=slots,
        broker_pid=broker_pid,
        broker_birth_identity=broker_birth_identity,
        model_provenance=model_provenance,
        snapshot_root=str(root / "inference-inputs"),
        supervisor_receipt_path=str(root / "supervisor" / "owner-receipt.json"),
        start_guard_timeout_s=config.start_guard.timeout_s,
        mps_minimum_headroom_bytes=headroom,
        mps_process_memory_fraction=fraction,
        max_input_snapshot_bytes=snapshot_limit,
        broker_max_frame_bytes=config.broker_max_frame_bytes,
        ros_domain_ids=tuple(config.ros_domain_ids),
        config=config,
    )


def assert_no_host_platform_calls(plan: W2CampaignPlan) -> None:
    """The Darwin plan must not claim an NVML or `/proc/self/fd` dependency, and vice versa."""

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
