"""The macOS MPS two-worker runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
import math
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Mapping

from so101_demo.parallel_batch.contracts.common import (
    ContractError,
    _require_finite,
    _require_id,
    _require_positive_int,
    _require_probability,
)
from so101_demo.parallel_batch.contracts.identity import _closed_mapping_fields, _load_closed_yaml
from so101_demo.parallel_batch.contracts.linux_cuda import (
    _FROZEN_RUNTIME_VALUES_LINUX_CUDA,
    EXECUTION_LINUX_CUDA_FIELDS,
    START_GUARD_FIELDS,
    ClockRulesLinuxCuda,
)
from so101_demo.parallel_batch.frozen_models import (
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256 as _FROZEN_GROUNDED_SAM_MANIFEST_SHA256,
)
from so101_demo.parallel_batch.frozen_models import (
    FROZEN_YOLO_WEIGHTS_SHA256 as _FROZEN_YOLO_WEIGHTS_SHA256,
)
from so101_demo.parallel_batch.start_guard import StartGuardPolicy


class AcceleratorKind(StrEnum):
    """The accelerator family a v4 document may select."""

    MPS = "mps"


class IpcTransport(StrEnum):
    """The closed set of v4 AF_UNIX address strategies."""

    PROC_FD_UNIX = "proc_fd_unix"
    DARWIN_PRIVATE_PATH_UNIX = "darwin_private_path_unix"


#: value written for ``ipc_transport`` to mean "this platform's closed default".
IPC_TRANSPORT_AUTO = "auto"


#: Exactly the one admitted (accelerator, device, transport, GL) combination.
MACOS_MPS_TWO_WORKER_PLATFORM_COMBINATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("mps", "mps", "darwin_private_path_unix", "cgl"),
)


#: The only worker count this platform contract supports. single-worker/W4/W6/eight-worker are out of scope and
#: the design forbids extrapolating any cross-N qualification from this value.
MACOS_MPS_TWO_WORKER_PLATFORM_WORKER_COUNT = 2


#: v4 keeps the frozen functional timing, frame and model values of v3. It only replaces the
#: platform selection, so the freeze itself is restated here instead of being duplicated.
#:
#: Deliberately absent, because they are platform-selected rather than globally frozen:
#: - `ros_domain_ids` is a per-platform isolation choice (the Darwin combination uses two);
#: - `requested_device` / `allow_cpu_fallback` belong to the platform combination;
#: - `mps_process_memory_fraction` is the Darwin allocator cap;
#: - `mujoco_gl` / `ipc_transport` follow from the combination (or from a resolved `auto`).
#: The platform-specific pins live in FROZEN_DARWIN_VALUES_MACOS_MPS_TWO_WORKER.
FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER: Mapping[str, object] = MappingProxyType({
    **{
        name: value
        for name, value in _FROZEN_RUNTIME_VALUES_LINUX_CUDA.items()
        if name not in {"schema_version", "requested_device", "gpu_device", "ros_domain_ids"}
    },
    "schema_version": 4,
    "worker_count": MACOS_MPS_TWO_WORKER_PLATFORM_WORKER_COUNT,
})


#: The values the Darwin combination adds on top of the shared freeze.
FROZEN_DARWIN_VALUES_MACOS_MPS_TWO_WORKER: Mapping[str, object] = MappingProxyType({
    "requested_device": "mps",
    "accelerator_kind": "mps",
    "accelerator_selector": "default",
    "allow_cpu_fallback": False,
    "mps_process_memory_fraction": 0.8,
    "mujoco_gl": "cgl",
    "ipc_transport": "darwin_private_path_unix",
})


ACCELERATOR_FIELDS = frozenset({"kind", "selector"})


START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS = frozenset(set(START_GUARD_FIELDS) | {"mps_minimum_headroom_bytes"})


#: Everything the v4 ``execution`` section may carry: the v3 functional fields minus the
#: platform-specific device/GPU selection, which moved to the top-level ``accelerator`` block.
#: ``requested_device`` and ``allow_cpu_fallback`` moved to the top level as well: in v4 they
#: describe the selected platform combination, not a per-run execution knob.
EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS = frozenset(
    set(EXECUTION_LINUX_CUDA_FIELDS) - {"requested_device", "allow_cpu_fallback", "gpu_device"}
)


MACOS_MPS_TWO_WORKER_CONFIG_FIELDS = frozenset({
    "schema_version", "execution", "start_guard", "accelerator", "requested_device",
    "allow_cpu_fallback", "worker_count", "ipc_transport", "mujoco_gl",
    "mps_process_memory_fraction", "max_input_snapshot_bytes",
})


#: The independent data-plane limit. `broker_max_frame_bytes` bounds the control frame; this
#: bounds the immutable snapshot a descriptor points at. Neither substitutes for the other, so
#: the snapshot limit must be at least as large as one frame and is validated on its own.
DEFAULT_MAX_INPUT_SNAPSHOT_BYTES = 64 * 1024 * 1024


def _require_fraction(name: str, value: object) -> float:
    """A real number in (0, 1]. Booleans and numeric strings are refused, not coerced."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name}_INVALID")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0 or number > 1.0:
        raise ContractError(f"{name}_INVALID")
    return number


def _require_positive_bytes(name: str, value: object) -> int:
    """A strictly positive int. Booleans and numeric strings are refused, not coerced."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name}_INVALID")
    if value <= 0:
        raise ContractError(f"{name}_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class AcceleratorSelectionMacosMpsTwoWorker:
    """The explicit accelerator choice. There is no implicit host index and no CPU device."""

    kind: AcceleratorKind
    selector: str

    def __post_init__(self) -> None:
        try:
            kind = AcceleratorKind(self.kind)
        except ValueError as error:
            raise ContractError("ACCELERATOR_KIND") from error
        object.__setattr__(self, "kind", kind)
        if not isinstance(self.selector, str) or not self.selector:
            raise ContractError("ACCELERATOR_SELECTOR")
        # One Apple GPU: the only valid MPS selector is the explicit default.
        if self.selector != "default":
            raise ContractError("ACCELERATOR_SELECTOR")

    @property
    def resolved_selector(self) -> str:
        """The selector as the manifest records it, always explicit."""

        return "default"


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfigMacosMpsTwoWorker:
    """The closed version-four document: exact two-worker on the named macOS platform combination."""

    schema_version: int
    backend: str
    max_worker_count: int
    ros_domain_ids: tuple[int, ...]
    heartbeat_interval_s: float
    heartbeat_timeout_s: float
    lease_duration_s: float
    lease_ack_timeout_s: float
    attempt_start_ack_timeout_s: float
    result_ack_timeout_s: float
    initializing_hard_timeout_s: float
    executing_hard_timeout_s: float
    finalizing_hard_timeout_s: float
    batch_hard_timeout_s: float
    worker_recovery_timeout_s: float
    broker_recovery_timeout_s: float
    broker_max_frame_bytes: int
    broker_queue_capacity_per_model: int
    broker_inflight_per_worker_per_model: int
    yolo_queue_timeout_s: float
    yolo_inference_timeout_s: float
    grounded_sam_queue_timeout_s: float
    grounded_sam_inference_timeout_s: float
    max_frame_age_s: float
    max_rgbd_skew_s: float
    max_tf_skew_s: float
    yolo_model_id: str
    yolo_imgsz: int
    allow_cpu_fallback: bool
    grounding_box_threshold: float
    grounding_text_threshold: float
    grounding_duplicate_iou: float
    grounding_max_candidates: int
    sam_mask_quality_threshold: float
    sam_min_mask_pixels: int
    sam_max_mask_area_ratio: float
    clock: ClockRulesLinuxCuda
    start_guard: "StartGuardPolicy"
    accelerator: AcceleratorSelectionMacosMpsTwoWorker
    requested_device: str
    worker_count: int
    ipc_transport: IpcTransport
    mujoco_gl: str
    mps_process_memory_fraction: float | None
    max_input_snapshot_bytes: int

    FROZEN_YOLO_WEIGHTS_SHA256: ClassVar[str] = _FROZEN_YOLO_WEIGHTS_SHA256
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256: ClassVar[str] = (
        _FROZEN_GROUNDED_SAM_MANIFEST_SHA256
    )

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 4:
            raise ContractError("SCHEMA_VERSION")
        if self.backend != "mujoco":
            raise ContractError("BACKEND")
        if not isinstance(self.accelerator, AcceleratorSelectionMacosMpsTwoWorker):
            raise ContractError("ACCELERATOR_SELECTION")
        try:
            transport = IpcTransport(self.ipc_transport)
        except ValueError as error:
            raise ContractError("IPC_TRANSPORT") from error
        object.__setattr__(self, "ipc_transport", transport)

        combination = (
            str(self.accelerator.kind), self.requested_device, str(transport), self.mujoco_gl,
        )
        if combination not in MACOS_MPS_TWO_WORKER_PLATFORM_COMBINATIONS:
            raise ContractError("PLATFORM_COMBINATION_UNSUPPORTED")

        # Exact two-worker. Any other count is a different platform claim this contract does not make.
        if isinstance(self.worker_count, bool) or self.worker_count != MACOS_MPS_TWO_WORKER_PLATFORM_WORKER_COUNT:
            raise ContractError("PLATFORM_WORKER_COUNT_UNSUPPORTED")

        if not isinstance(self.allow_cpu_fallback, bool) or self.allow_cpu_fallback:
            raise ContractError("ALLOW_CPU_FALLBACK")

        for name in (
            "max_worker_count", "broker_max_frame_bytes", "broker_queue_capacity_per_model",
            "broker_inflight_per_worker_per_model", "yolo_imgsz", "grounding_max_candidates",
            "sam_min_mask_pixels", "max_input_snapshot_bytes",
        ):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        if not isinstance(self.ros_domain_ids, (list, tuple)):
            raise ContractError("ROS_DOMAIN_IDS")
        domains = tuple(self.ros_domain_ids)
        for domain_id in domains:
            _require_positive_int("ros_domain_id", domain_id)
        object.__setattr__(self, "ros_domain_ids", domains)
        for name in (
            "heartbeat_interval_s", "heartbeat_timeout_s", "lease_duration_s",
            "lease_ack_timeout_s", "attempt_start_ack_timeout_s", "result_ack_timeout_s",
            "initializing_hard_timeout_s", "executing_hard_timeout_s",
            "finalizing_hard_timeout_s", "batch_hard_timeout_s", "worker_recovery_timeout_s",
            "broker_recovery_timeout_s", "yolo_queue_timeout_s", "yolo_inference_timeout_s",
            "grounded_sam_queue_timeout_s", "grounded_sam_inference_timeout_s",
        ):
            object.__setattr__(
                self, name, _require_finite(name, getattr(self, name), minimum=0.000001)
            )
        for name in ("max_frame_age_s", "max_rgbd_skew_s", "max_tf_skew_s"):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))
        for name in (
            "grounding_box_threshold", "grounding_text_threshold",
            "grounding_duplicate_iou", "sam_mask_quality_threshold",
            "sam_max_mask_area_ratio",
        ):
            object.__setattr__(self, name, _require_probability(name, getattr(self, name)))
        object.__setattr__(self, "yolo_model_id", _require_id("yolo_model_id", self.yolo_model_id))
        if not isinstance(self.clock, ClockRulesLinuxCuda):
            raise ContractError("CLOCK_RULES")
        if not isinstance(self.start_guard, StartGuardPolicy):
            raise ContractError("START_GUARD_POLICY")

        # The allocator cap is set before any MPS allocation, so it must be a real fraction.
        object.__setattr__(
            self, "mps_process_memory_fraction",
            _require_fraction("MPS_PROCESS_MEMORY_FRACTION", self.mps_process_memory_fraction),
        )
        headroom = self.start_guard.mps_minimum_headroom_bytes
        if headroom is None:
            raise ContractError("MPS_MINIMUM_HEADROOM_BYTES")
        _require_positive_bytes("MPS_MINIMUM_HEADROOM_BYTES", headroom)

        platform_pins = FROZEN_DARWIN_VALUES_MACOS_MPS_TWO_WORKER
        for name, expected in FROZEN_RUNTIME_VALUES_MACOS_MPS_TWO_WORKER.items():
            actual: object = getattr(self, name, None)
            if actual != expected:
                raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
        for name, expected in platform_pins.items():
            if name == "accelerator_kind":
                actual = str(self.accelerator.kind)
            elif name == "accelerator_selector":
                actual = self.accelerator.resolved_selector
            else:
                actual = getattr(self, name, None)
            if actual != expected:
                raise ContractError(f"FROZEN_PLATFORM_VALUE: {name}")
        if len(domains) != self.worker_count or len(set(domains)) != len(domains):
            raise ContractError("ROS_DOMAIN_IDS")

    @property
    def mps_minimum_headroom_bytes(self) -> int | None:
        """The fixed unified-memory headroom, present only on the Darwin combination."""

        return self.start_guard.mps_minimum_headroom_bytes

    @property
    def yolo_weights_sha256(self) -> str:
        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256

    def resolved_manifest(self) -> dict:
        """The resolved platform values a manifest must record instead of ``auto``."""

        return {
            "schema_version": 4,
            "accelerator": str(self.accelerator.kind),
            "accelerator_selector": self.accelerator.resolved_selector,
            "requested_device": self.requested_device,
            "allow_cpu_fallback": self.allow_cpu_fallback,
            "ipc_transport": str(self.ipc_transport),
            "mujoco_gl": self.mujoco_gl,
            "worker_count": self.worker_count,
            "mps_process_memory_fraction": self.mps_process_memory_fraction,
            "mps_minimum_headroom_bytes": self.mps_minimum_headroom_bytes,
            "max_input_snapshot_bytes": self.max_input_snapshot_bytes,
            "yolo_model_id": self.yolo_model_id,
            "yolo_weights_sha256": self.yolo_weights_sha256,
            "grounded_sam_manifest_sha256": self.grounded_sam_manifest_sha256,
        }


def _resolve_macos_mps_two_worker_transport(
    value: object, accelerator: AcceleratorSelectionMacosMpsTwoWorker
) -> dict:
    """Resolve ``auto`` to the current platform's closed default; never to TCP."""

    if value == IPC_TRANSPORT_AUTO:
        return {"ipc_transport": "darwin_private_path_unix", "mujoco_gl": "cgl"}
    return {}


def parse_parallel_runtime_config_macos_mps_two_worker(document: object) -> ParallelRuntimeConfigMacosMpsTwoWorker:
    """Validate a version-four document against the closed platform-combination schema."""

    top = _closed_mapping_fields("CONFIG", document, set(MACOS_MPS_TWO_WORKER_CONFIG_FIELDS))
    if type(top["schema_version"]) is not int or top["schema_version"] != 4:
        raise ContractError("SCHEMA_VERSION")
    accelerator_fields = _closed_mapping_fields(
        "ACCELERATOR", top["accelerator"], set(ACCELERATOR_FIELDS)
    )
    execution = _closed_mapping_fields(
        "EXECUTION", top["execution"], set(EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS)
    )
    guard = _closed_mapping_fields(
        "START_GUARD", top["start_guard"], set(START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS),
        {"mps_minimum_headroom_bytes"},
    )
    clock = _closed_mapping_fields(
        "CLOCK", execution.pop("clock"), {item.name for item in fields(ClockRulesLinuxCuda)}
    )
    try:
        accelerator = AcceleratorSelectionMacosMpsTwoWorker(
            kind=AcceleratorKind(accelerator_fields["kind"]),
            selector=accelerator_fields["selector"],
        )
    except (ValueError, KeyError) as error:
        raise ContractError(f"ACCELERATOR_INVALID: {error}") from error

    resolved = _resolve_macos_mps_two_worker_transport(top["ipc_transport"], accelerator)
    try:
        guard_policy = StartGuardPolicy(**guard)
    except ValueError as error:
        raise ContractError(f"START_GUARD_INVALID: {error}") from error
    return ParallelRuntimeConfigMacosMpsTwoWorker(
        schema_version=4,
        clock=ClockRulesLinuxCuda(**clock),
        start_guard=guard_policy,
        accelerator=accelerator,
        requested_device=top["requested_device"],
        allow_cpu_fallback=top["allow_cpu_fallback"],
        worker_count=top["worker_count"],
        ipc_transport=resolved.get("ipc_transport", top["ipc_transport"]),
        mujoco_gl=resolved.get("mujoco_gl", top["mujoco_gl"]),
        mps_process_memory_fraction=top["mps_process_memory_fraction"],
        max_input_snapshot_bytes=top["max_input_snapshot_bytes"],
        **execution,
    )


def load_parallel_runtime_config_macos_mps_two_worker(path: Path) -> ParallelRuntimeConfigMacosMpsTwoWorker:
    """Load the closed version-four YAML document; any drift or cross-platform key is refused."""

    return parse_parallel_runtime_config_macos_mps_two_worker(_load_closed_yaml(path))


def require_macos_mps_two_worker_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for any contract version other than version four."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    if request_version != 4 or config_version != 4:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
