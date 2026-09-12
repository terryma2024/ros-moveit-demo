"""Strict value contracts for the isolated parallel validation batch."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from enum import StrEnum
from numbers import Real
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import ClassVar, Mapping

import yaml


class ContractError(ValueError):
    """A closed parallel-validation contract was violated."""


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    PLAN_ONLY = "plan_only"
    EXECUTE = "execute"


class ExecutionKind(StrEnum):
    ATTEMPT = "attempt"
    VALIDATION = "validation"


class PointStatus(StrEnum):
    UNRUN = "UNRUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class ValidationStatus(StrEnum):
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_INVALID = "VALIDATION_INVALID"


class AttemptStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    INDETERMINATE = "INDETERMINATE"


class WorkerState(StrEnum):
    STARTING = "STARTING"
    AVAILABLE = "AVAILABLE"
    LEASED = "LEASED"
    INITIALIZING = "INITIALIZING"
    EXECUTING = "EXECUTING"
    FINALIZING = "FINALIZING"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"
    STOPPED = "STOPPED"


class ModelOutcome(StrEnum):
    QUALIFIED = "QUALIFIED"
    NORMAL_REJECTION = "NORMAL_REJECTION"
    MODEL_ERROR = "MODEL_ERROR"
    INFRA_ERROR = "INFRA_ERROR"
    QUEUE_TIMEOUT = "QUEUE_TIMEOUT"
    INFERENCE_TIMEOUT = "INFERENCE_TIMEOUT"
    CANCELLED = "CANCELLED"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

_FROZEN_MAX_WORKER_COUNT = 3
_FROZEN_MAX_POINTS_PER_WORKER = 20
_FROZEN_YOLO_WEIGHTS_SHA256 = (
    "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"
)
_FROZEN_GROUNDED_SAM_MANIFEST_SHA256 = (
    "0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775"
)


def _require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"EMPTY_ID: {name}")
    if _IDENTIFIER.fullmatch(value) is None:
        raise ContractError(f"INVALID_IDENTIFIER: {name}")
    return value


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"POSITIVE_INTEGER: {name}")
    return value


def _require_finite(name: str, value: object, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ContractError(f"FINITE: {name}")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ContractError(f"FINITE: {name}")
    return result


def _require_probability(name: str, value: object) -> float:
    result = _require_finite(name, value)
    if result > 1.0:
        raise ContractError(f"PROBABILITY: {name}")
    return result


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"SHA256: {name}")
    return value


def _require_safe_relative_path(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\\" in value
        or "\x00" in value
        or value.startswith("./")
        or value.endswith("/")
    ):
        raise ContractError(f"SAFE_RELATIVE_PATH: {name}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"SAFE_RELATIVE_PATH: {name}")
    return value


def _require_absolute_path(name: str, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ContractError(f"ABSOLUTE_EVIDENCE_ROOT: {name}")
    raw_path = str(value)
    path = Path(value)
    if (
        not path.is_absolute()
        or raw_path in {".", ".."}
        or "\x00" in raw_path
        or any(part in {".", ".."} for part in raw_path.split("/"))
    ):
        raise ContractError(f"ABSOLUTE_EVIDENCE_ROOT: {name}")
    return path


def _require_enum(name: str, value: object, enum_type: type[StrEnum]) -> StrEnum:
    if not isinstance(value, enum_type):
        raise ContractError(f"ENUM: {name}")
    return value


def validate_capacity(worker_count: int, max_points_per_worker: int, point_count: int) -> int:
    """Return the available immutable lease capacity or reject startup."""

    workers = _require_positive_int("worker_count", worker_count)
    per_worker = _require_positive_int("max_points_per_worker", max_points_per_worker)
    points = _require_positive_int("point_count", point_count)
    capacity = workers * per_worker
    if capacity < points:
        raise ContractError(
            f"INSUFFICIENT_CAPACITY: worker_count={workers}, "
            f"max_points_per_worker={per_worker}, point_count={points}"
        )
    return capacity


@dataclass(frozen=True, slots=True)
class LeaseIdentity:
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    attempt_id: str
    lease_generation: int
    lease_issued_monotonic_s: float
    lease_deadline_monotonic_s: float

    def __post_init__(self) -> None:
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        issued = _require_finite("lease_issued_monotonic_s", self.lease_issued_monotonic_s)
        deadline = _require_finite("lease_deadline_monotonic_s", self.lease_deadline_monotonic_s)
        if deadline <= issued:
            raise ContractError("LEASE_DEADLINE_ORDER")
        object.__setattr__(self, "lease_issued_monotonic_s", issued)
        object.__setattr__(self, "lease_deadline_monotonic_s", deadline)


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    attempt_id: str
    lease_generation: int

    def __post_init__(self) -> None:
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ValidationIdentity:
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    validation_id: str
    lease_generation: int

    def __post_init__(self) -> None:
        for name in ("batch_id", "worker_id", "point_id", "validation_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))


def _validate_execution_identity(
    *,
    execution_kind: ExecutionKind,
    attempt_id: str | None,
    validation_id: str | None,
) -> tuple[str | None, str | None]:
    _require_enum("execution_kind", execution_kind, ExecutionKind)
    if execution_kind is ExecutionKind.ATTEMPT:
        if validation_id is not None or attempt_id is None:
            raise ContractError("MIXED_EXECUTION_IDENTITY")
        return _require_id("attempt_id", attempt_id), None
    if attempt_id is not None or validation_id is None:
        raise ContractError("MIXED_EXECUTION_IDENTITY")
    return None, _require_id("validation_id", validation_id)


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    request_id: str
    model_id: str
    execution_kind: ExecutionKind
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    lease_generation: int
    reset_epoch: str
    image_timestamp_s: float
    input_relative_path: str
    input_sha256: str
    attempt_id: str | None = None
    validation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "model_id", "batch_id", "worker_id", "point_id", "reset_epoch"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        attempt_id, validation_id = _validate_execution_identity(
            execution_kind=self.execution_kind,
            attempt_id=self.attempt_id,
            validation_id=self.validation_id,
        )
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "validation_id", validation_id)
        object.__setattr__(
            self,
            "image_timestamp_s",
            _require_finite("image_timestamp_s", self.image_timestamp_s),
        )
        object.__setattr__(
            self,
            "input_relative_path",
            _require_safe_relative_path("input_relative_path", self.input_relative_path),
        )
        object.__setattr__(
            self, "input_sha256", _require_sha256("input_sha256", self.input_sha256)
        )


@dataclass(frozen=True, slots=True)
class NormalizedInferenceResponseIdentity:
    request_id: str
    execution_kind: ExecutionKind
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    lease_generation: int
    attempt_id: str | None = None
    validation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "batch_id", "worker_id", "point_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        attempt_id, validation_id = _validate_execution_identity(
            execution_kind=self.execution_kind,
            attempt_id=self.attempt_id,
            validation_id=self.validation_id,
        )
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "validation_id", validation_id)

    @classmethod
    def from_request(cls, request: InferenceRequest) -> "NormalizedInferenceResponseIdentity":
        if not isinstance(request, InferenceRequest):
            raise ContractError("INFERENCE_REQUEST")
        return cls(
            request_id=request.request_id,
            execution_kind=request.execution_kind,
            batch_id=request.batch_id,
            coordinator_epoch=request.coordinator_epoch,
            worker_id=request.worker_id,
            worker_generation=request.worker_generation,
            point_id=request.point_id,
            lease_generation=request.lease_generation,
            attempt_id=request.attempt_id,
            validation_id=request.validation_id,
        )


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfig:
    schema_version: int
    backend: str
    max_worker_count: int
    max_points_per_worker_upper_bound: int
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
    min_logical_cpu_per_worker: int
    available_ram_base_gib: int
    available_ram_per_worker_gib: int
    min_available_gpu_gib: int
    required_live_headroom_ratio: float

    FROZEN_YOLO_WEIGHTS_SHA256: ClassVar[str] = _FROZEN_YOLO_WEIGHTS_SHA256
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256: ClassVar[str] = (
        _FROZEN_GROUNDED_SAM_MANIFEST_SHA256
    )

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractError("SCHEMA_VERSION")
        if self.backend != "mujoco":
            raise ContractError("BACKEND")
        positive_ints = (
            "max_worker_count",
            "max_points_per_worker_upper_bound",
            "broker_max_frame_bytes",
            "broker_queue_capacity_per_model",
            "broker_inflight_per_worker_per_model",
            "yolo_imgsz",
            "grounding_max_candidates", "sam_min_mask_pixels", "min_logical_cpu_per_worker",
            "available_ram_base_gib", "available_ram_per_worker_gib", "min_available_gpu_gib",
        )
        for name in positive_ints:
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        if not isinstance(self.ros_domain_ids, (list, tuple)):
            raise ContractError("ROS_DOMAIN_IDS")
        domains = tuple(self.ros_domain_ids)
        for domain_id in domains:
            _require_positive_int("ros_domain_id", domain_id)
        object.__setattr__(self, "ros_domain_ids", domains)
        timeouts = (
            "heartbeat_interval_s",
            "heartbeat_timeout_s",
            "lease_duration_s",
            "lease_ack_timeout_s",
            "attempt_start_ack_timeout_s",
            "result_ack_timeout_s",
            "initializing_hard_timeout_s",
            "executing_hard_timeout_s",
            "finalizing_hard_timeout_s",
            "batch_hard_timeout_s",
            "worker_recovery_timeout_s",
            "broker_recovery_timeout_s",
            "yolo_queue_timeout_s",
            "yolo_inference_timeout_s",
            "grounded_sam_queue_timeout_s",
            "grounded_sam_inference_timeout_s",
        )
        for name in timeouts:
            object.__setattr__(
                self, name, _require_finite(name, getattr(self, name), minimum=0.000001)
            )
        for name in ("max_frame_age_s", "max_rgbd_skew_s", "max_tf_skew_s"):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))
        for name in (
            "grounding_box_threshold",
            "grounding_text_threshold",
            "grounding_duplicate_iou",
            "sam_mask_quality_threshold",
            "sam_max_mask_area_ratio",
            "required_live_headroom_ratio",
        ):
            object.__setattr__(self, name, _require_probability(name, getattr(self, name)))
        object.__setattr__(self, "yolo_model_id", _require_id("yolo_model_id", self.yolo_model_id))
        if self.requested_device != "cuda":
            raise ContractError("REQUESTED_DEVICE")
        if not isinstance(self.allow_cpu_fallback, bool) or self.allow_cpu_fallback:
            raise ContractError("ALLOW_CPU_FALLBACK")
        for name, expected in _FROZEN_RUNTIME_VALUES.items():
            if getattr(self, name) != expected:
                raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
        if len(domains) != self.max_worker_count or len(set(domains)) != len(domains):
            raise ContractError("ROS_DOMAIN_IDS")

    @property
    def yolo_weights_sha256(self) -> str:
        """Return the reviewed YOLO artifact identity bound to v1."""

        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        """Return the reviewed Grounded-SAM bundle identity bound to v1."""

        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256


_FROZEN_RUNTIME_VALUES = {
    "schema_version": 1,
    "backend": "mujoco",
    "max_worker_count": _FROZEN_MAX_WORKER_COUNT,
    "max_points_per_worker_upper_bound": _FROZEN_MAX_POINTS_PER_WORKER,
    "ros_domain_ids": (181, 182, 183),
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
    "min_logical_cpu_per_worker": 4,
    "available_ram_base_gib": 6,
    "available_ram_per_worker_gib": 4,
    "min_available_gpu_gib": 8,
    "required_live_headroom_ratio": 0.20,
}


def load_parallel_runtime_config(path: Path) -> ParallelRuntimeConfig:
    """Load the version-one YAML document without accepting schema drift."""

    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    if not isinstance(document, dict):
        raise ContractError("CONFIG_MAPPING")
    expected = {item.name for item in fields(ParallelRuntimeConfig)}
    actual = set(document)
    unknown = actual - expected
    missing = expected - actual
    if unknown:
        raise ContractError(f"UNKNOWN_CONFIG_FIELD: {sorted(unknown)!r}")
    if missing:
        raise ContractError(f"MISSING_CONFIG_FIELD: {sorted(missing)!r}")
    return ParallelRuntimeConfig(**document)


@dataclass(frozen=True, slots=True)
class BatchRequest:
    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    worker_count: int
    max_points_per_worker: int
    evidence_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_id", _require_id("batch_id", self.batch_id))
        _require_enum("run_mode", self.run_mode, RunMode)
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
        object.__setattr__(
            self,
            "max_points_per_worker",
            _require_positive_int("max_points_per_worker", self.max_points_per_worker),
        )
        if self.worker_count > _FROZEN_MAX_WORKER_COUNT:
            raise ContractError("MAX_WORKER_COUNT")
        if self.max_points_per_worker > _FROZEN_MAX_POINTS_PER_WORKER:
            raise ContractError("MAX_POINTS_PER_WORKER")
        object.__setattr__(
            self,
            "evidence_root",
            _require_absolute_path("evidence_root", self.evidence_root),
        )
        validate_capacity(self.worker_count, self.max_points_per_worker, len(point_ids))


@dataclass(frozen=True, slots=True)
class BatchSummary:
    run_mode: RunMode
    point_statuses: Mapping[str, PointStatus]
    batch_terminal: bool = False
    validation_statuses: Mapping[str, ValidationStatus] = field(default_factory=dict)
    batch_cleanup_complete: bool = False

    def __post_init__(self) -> None:
        _require_enum("run_mode", self.run_mode, RunMode)
        if not isinstance(self.batch_terminal, bool):
            raise ContractError("BOOLEAN: batch_terminal")
        if not isinstance(self.batch_cleanup_complete, bool):
            raise ContractError("BOOLEAN: batch_cleanup_complete")
        if not isinstance(self.point_statuses, Mapping):
            raise ContractError("POINT_STATUSES")
        if not isinstance(self.validation_statuses, Mapping):
            raise ContractError("VALIDATION_STATUSES")
        points = dict(self.point_statuses)
        validations = dict(self.validation_statuses)
        if not points:
            raise ContractError("POINT_STATUSES")
        for point_id, status in points.items():
            _require_id("point_id", point_id)
            _require_enum("point_status", status, PointStatus)
        for point_id, status in validations.items():
            _require_id("validation_point_id", point_id)
            _require_enum("validation_status", status, ValidationStatus)
        if self.run_mode is RunMode.EXECUTE:
            if validations:
                raise ContractError("EXECUTE_VALIDATION_MIX")
        else:
            if not set(validations).issubset(points) or any(
                status is not PointStatus.UNRUN for status in points.values()
            ):
                raise ContractError("VALIDATION_PHYSICAL_UNRUN")
        object.__setattr__(self, "point_statuses", MappingProxyType(points))
        object.__setattr__(self, "validation_statuses", MappingProxyType(validations))

    @property
    def coverage_complete(self) -> bool:
        return self.batch_terminal and self.run_mode is RunMode.EXECUTE and all(
            status in {PointStatus.PASSED, PointStatus.FAILED}
            for status in self.point_statuses.values()
        )

    @property
    def execution_complete(self) -> bool:
        return self.batch_terminal and self.run_mode is RunMode.EXECUTE

    @property
    def validation_complete(self) -> bool:
        return (
            self.batch_terminal
            and self.run_mode is not RunMode.EXECUTE
            and set(self.validation_statuses) == set(self.point_statuses)
        )

    @property
    def validation_passed(self) -> bool:
        return self.validation_complete and all(
            status is ValidationStatus.VALIDATION_PASSED
            for status in self.validation_statuses.values()
        )

    @property
    def qualification_applicable(self) -> bool:
        return self.run_mode is RunMode.EXECUTE

    @property
    def qualification_passed(self) -> bool:
        return self.coverage_complete and self.batch_cleanup_complete and all(
            status is PointStatus.PASSED for status in self.point_statuses.values()
        )
