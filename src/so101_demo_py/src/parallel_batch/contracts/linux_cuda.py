"""The batch request and the Linux CUDA runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from so101_demo.parallel_batch.contracts.common import (
    _FROZEN_MAX_WORKER_COUNT,
    ContractError,
    RunMode,
    _require_absolute_path,
    _require_enum,
    _require_finite,
    _require_id,
    _require_positive_int,
    _require_probability,
)
from so101_demo.parallel_batch.contracts.identity import _closed_mapping_fields, _load_closed_yaml
from so101_demo.parallel_batch.frozen_models import (
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256 as _FROZEN_GROUNDED_SAM_MANIFEST_SHA256,
)
from so101_demo.parallel_batch.frozen_models import (
    FROZEN_YOLO_WEIGHTS_SHA256 as _FROZEN_YOLO_WEIGHTS_SHA256,
)
from so101_demo.parallel_batch.start_guard import StartGuardPolicy


class BatchKind(StrEnum):
    FIRST_PASS = "FIRST_PASS"
    FULL_RESTART_RETRY = "FULL_RESTART_RETRY"
    ADAPTIVE_POOL = "ADAPTIVE_POOL"


@dataclass(frozen=True, slots=True)
class BatchRequest:
    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    worker_count: int
    evidence_root: Path
    batch_kind: BatchKind
    schema_version: int = 2

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ContractError("SCHEMA_VERSION")
        object.__setattr__(self, "batch_id", _require_id("batch_id", self.batch_id))
        _require_enum("run_mode", self.run_mode, RunMode)
        _require_enum("batch_kind", self.batch_kind, BatchKind)
        if not isinstance(self.selected_point_ids, (list, tuple)):
            raise ContractError("POINT_ID_SEQUENCE")
        point_ids = tuple(
            _require_id("point_id", point_id) for point_id in self.selected_point_ids
        )
        if not point_ids or len(point_ids) != len(set(point_ids)):
            raise ContractError("UNIQUE_POINT_IDS")
        object.__setattr__(self, "selected_point_ids", point_ids)
        object.__setattr__(
            self, "worker_count", _require_positive_int("worker_count", self.worker_count)
        )
        if self.worker_count > _FROZEN_MAX_WORKER_COUNT:
            raise ContractError("MAX_WORKER_COUNT")
        if self.worker_count != 1:
            # A native batch is one worker. Multi-worker collection exists only as container shards, whose
            # cap is `max_worker_count` of the runtime document (a different field, unchanged).
            raise ContractError("NATIVE_MULTI_WORKER_UNSUPPORTED")
        object.__setattr__(
            self,
            "evidence_root",
            _require_absolute_path("evidence_root", self.evidence_root),
        )
        if self.batch_kind is BatchKind.FULL_RESTART_RETRY and (
            len(point_ids) != 1 or self.worker_count != 1
        ):
            raise ContractError("RETRY_SINGLE_POINT_SINGLE_WORKER")


#: The closed set of ``execution`` fields for v3. Sampling, safety and coverage are gone;
#: the GPU selector moved next to the other device settings and the clock rules stay because
#: they describe functional simulation timing, not a resource budget.
EXECUTION_LINUX_CUDA_FIELDS = frozenset({
    "backend", "max_worker_count", "ros_domain_ids", "heartbeat_interval_s",
    "heartbeat_timeout_s", "lease_duration_s", "lease_ack_timeout_s",
    "attempt_start_ack_timeout_s", "result_ack_timeout_s",
    "initializing_hard_timeout_s", "executing_hard_timeout_s",
    "finalizing_hard_timeout_s", "batch_hard_timeout_s",
    "worker_recovery_timeout_s", "broker_recovery_timeout_s",
    "broker_max_frame_bytes", "broker_queue_capacity_per_model",
    "broker_inflight_per_worker_per_model", "yolo_queue_timeout_s",
    "yolo_inference_timeout_s", "grounded_sam_queue_timeout_s",
    "grounded_sam_inference_timeout_s", "max_frame_age_s", "max_rgbd_skew_s",
    "max_tf_skew_s", "yolo_model_id", "yolo_imgsz", "requested_device",
    "allow_cpu_fallback", "grounding_box_threshold", "grounding_text_threshold",
    "grounding_duplicate_iou", "grounding_max_candidates",
    "sam_mask_quality_threshold", "sam_min_mask_pixels",
    "sam_max_mask_area_ratio", "clock", "gpu_device",
})


_GPU_SELECTOR_KINDS = ("UUID", "INDEX")


@dataclass(frozen=True, slots=True)
class GpuDeviceSelector:
    """The explicitly chosen target device; there is no implicit host index 0."""

    selector_kind: str
    selector: str

    def __post_init__(self) -> None:
        if self.selector_kind not in _GPU_SELECTOR_KINDS:
            raise ContractError("GPU_SELECTOR_KIND")
        if not isinstance(self.selector, str) or not self.selector:
            raise ContractError("GPU_SELECTOR")
        if self.selector_kind == "INDEX":
            if not self.selector.isdigit():
                raise ContractError("GPU_SELECTOR_INDEX")
        elif not self.selector.startswith("GPU-"):
            raise ContractError("GPU_SELECTOR_UUID")


@dataclass(frozen=True, slots=True)
class ClockRulesLinuxCuda:
    """Functional simulation-clock rules; still only used for real RTF/frame evidence."""

    window_s: float
    stride_s: float
    minimum_consecutive_steady_windows: int
    maximum_clock_age_s: float
    pace_source: str

    def __post_init__(self) -> None:
        for name in ("window_s", "stride_s", "maximum_clock_age_s"):
            object.__setattr__(
                self, name, _require_finite(name, getattr(self, name), minimum=0.000001)
            )
        object.__setattr__(
            self,
            "minimum_consecutive_steady_windows",
            _require_positive_int(
                "minimum_consecutive_steady_windows",
                self.minimum_consecutive_steady_windows,
            ),
        )
        if self.pace_source != "FROZEN_SIM_SETTING":
            raise ContractError("CLOCK_PACE_SOURCE")


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfigLinuxCuda:
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
    requested_device: str
    allow_cpu_fallback: bool
    grounding_box_threshold: float
    grounding_text_threshold: float
    grounding_duplicate_iou: float
    grounding_max_candidates: int
    sam_mask_quality_threshold: float
    sam_min_mask_pixels: int
    sam_max_mask_area_ratio: float
    clock: ClockRulesLinuxCuda
    gpu_device: GpuDeviceSelector
    start_guard: "StartGuardPolicy"

    FROZEN_YOLO_WEIGHTS_SHA256: ClassVar[str] = _FROZEN_YOLO_WEIGHTS_SHA256
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256: ClassVar[str] = (
        _FROZEN_GROUNDED_SAM_MANIFEST_SHA256
    )

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 3:
            raise ContractError("SCHEMA_VERSION")
        if self.backend != "mujoco":
            raise ContractError("BACKEND")
        for name in (
            "max_worker_count",
            "broker_max_frame_bytes",
            "broker_queue_capacity_per_model",
            "broker_inflight_per_worker_per_model",
            "yolo_imgsz",
            "grounding_max_candidates",
            "sam_min_mask_pixels",
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
        if self.requested_device != "cuda":
            raise ContractError("REQUESTED_DEVICE")
        if not isinstance(self.allow_cpu_fallback, bool) or self.allow_cpu_fallback:
            raise ContractError("ALLOW_CPU_FALLBACK")
        if not isinstance(self.clock, ClockRulesLinuxCuda):
            raise ContractError("CLOCK_RULES")
        if not isinstance(self.gpu_device, GpuDeviceSelector):
            raise ContractError("GPU_DEVICE_SELECTOR")
        if not isinstance(self.start_guard, StartGuardPolicy):
            raise ContractError("START_GUARD_POLICY")
        for name, expected in _EXACT_RUNTIME_VALUES_LINUX_CUDA.items():
            if getattr(self, name) != expected:
                raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
        for name, floor in _MINIMUM_RUNTIME_VALUES_LINUX_CUDA.items():
            if getattr(self, name) < floor:
                raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
        if len(domains) != self.max_worker_count or len(set(domains)) != len(domains):
            raise ContractError("ROS_DOMAIN_IDS")

    @property
    def yolo_weights_sha256(self) -> str:
        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256


_FROZEN_RUNTIME_VALUES_LINUX_CUDA = {
    "schema_version": 3,
    "backend": "mujoco",
    "max_worker_count": _FROZEN_MAX_WORKER_COUNT,
    "ros_domain_ids": (181, 182, 183, 184, 185, 186, 187, 188),
    "heartbeat_interval_s": 1.0,
    "heartbeat_timeout_s": 5.0,
    "lease_duration_s": 300.0,
    "lease_ack_timeout_s": 5.0,
    "attempt_start_ack_timeout_s": 5.0,
    "result_ack_timeout_s": 10.0,
    "initializing_hard_timeout_s": 180.0,
    "executing_hard_timeout_s": 240.0,
    "finalizing_hard_timeout_s": 120.0,
    "batch_hard_timeout_s": 5400.0,
    "worker_recovery_timeout_s": 120.0,
    "broker_recovery_timeout_s": 90.0,
    "broker_max_frame_bytes": 8388608,
    "broker_queue_capacity_per_model": 3,
    "broker_inflight_per_worker_per_model": 1,
    "yolo_queue_timeout_s": 10.0,
    "yolo_inference_timeout_s": 20.0,
    "grounded_sam_queue_timeout_s": 10.0,
    "grounded_sam_inference_timeout_s": 60.0,
    "max_frame_age_s": 5.0,
    "max_rgbd_skew_s": 0.0,
    "max_tf_skew_s": 0.0,
    "yolo_model_id": "plastic-cup-yolo11n-seg-v1",
    "yolo_imgsz": 640,
    "requested_device": "cuda",
    "allow_cpu_fallback": False,
    "grounding_box_threshold": 0.35,
    "grounding_text_threshold": 0.25,
    "grounding_duplicate_iou": 0.85,
    "grounding_max_candidates": 16,
    "sam_mask_quality_threshold": 0.75,
    "sam_min_mask_pixels": 64,
    "sam_max_mask_area_ratio": 0.50,
}


#: Version three only. Two stage bounds and the campaign total are floors, not pins: a data pipeline with offline processing
#: after the Teacher needs the stage and the lease to last longer than the original values, and a one-campaign collection of all
#: scenes needs a longer campaign total (`batch_hard_timeout_s`, time budget only) (the Teacher's own execution deadline is a separate,
#: unchanged policy). The original values stay valid. Versions four to six keep the exact pins above.
_MINIMUM_RUNTIME_VALUES_LINUX_CUDA = {"lease_duration_s": 300.0, "executing_hard_timeout_s": 240.0,
                                       "batch_hard_timeout_s": 5400.0}


_EXACT_RUNTIME_VALUES_LINUX_CUDA = {name: value for name, value in _FROZEN_RUNTIME_VALUES_LINUX_CUDA.items()
                            if name not in _MINIMUM_RUNTIME_VALUES_LINUX_CUDA}


START_GUARD_FIELDS = frozenset({"timeout_s", "cpu_busy_warn_fraction", "ram_minimum_bytes",
                                "ram_minimum_fraction", "gpu_minimum_bytes"})


def parse_parallel_runtime_config_linux_cuda(document: object) -> ParallelRuntimeConfigLinuxCuda:
    """Validate a version-three document against the closed, budget-free schema."""

    top = _closed_mapping_fields("CONFIG", document, {"schema_version", "execution", "start_guard"})
    if type(top["schema_version"]) is not int or top["schema_version"] != 3:
        raise ContractError("SCHEMA_VERSION")
    execution = _closed_mapping_fields("EXECUTION", top["execution"], set(EXECUTION_LINUX_CUDA_FIELDS))
    guard = _closed_mapping_fields("START_GUARD", top["start_guard"], set(START_GUARD_FIELDS))
    clock = _closed_mapping_fields(
        "CLOCK", execution.pop("clock"), {item.name for item in fields(ClockRulesLinuxCuda)}
    )
    gpu_device = _closed_mapping_fields(
        "GPU_DEVICE", execution.pop("gpu_device"), {"selector_kind", "selector"}
    )
    try:
        guard_policy = StartGuardPolicy(**guard)
        selector = GpuDeviceSelector(**gpu_device)
    except ValueError as error:
        raise ContractError(f"START_GUARD_INVALID: {error}") from error
    return ParallelRuntimeConfigLinuxCuda(
        schema_version=3,
        clock=ClockRulesLinuxCuda(**clock),
        gpu_device=selector,
        start_guard=guard_policy,
        **execution,
    )


def load_parallel_runtime_config_linux_cuda(path: Path) -> ParallelRuntimeConfigLinuxCuda:
    """Load the closed version-three YAML document; any drift or legacy key is refused."""

    return parse_parallel_runtime_config_linux_cuda(_load_closed_yaml(path))


#: The bound on one Teacher execution (the wait for the Teacher child, the Worker's `TEACHER_EXECUTION_DEADLINE` guard, the
#: perception broker's RPC deadlines, the pose wait). It is the frozen value of the original coupling and it is not a stage bound:
#: raising `executing_hard_timeout_s` (the Coordinator's stage) for offline processing must not raise it.
TEACHER_EXECUTION_BOUND_S = 240.0


def teacher_execution_bound_s(config, default: float = 180.0) -> float:
    """The Teacher's execution bound for `config`: its stage bound `executing_hard_timeout_s`, never more than the frozen 240 s
    (every configuration that keeps the original coupling is unchanged; a smaller bound is honoured; `default` if it has none)."""

    return min(float(getattr(config, "executing_hard_timeout_s", default)), TEACHER_EXECUTION_BOUND_S)


def require_linux_cuda_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for any contract version other than the active one."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    if request_version != 3 or config_version != 3:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
