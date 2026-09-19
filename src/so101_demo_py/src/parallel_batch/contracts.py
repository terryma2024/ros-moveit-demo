"""Strict value contracts for the isolated parallel validation batch."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field, fields
from enum import StrEnum
from numbers import Real
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import ClassVar, Mapping

import yaml

from .start_guard import StartGuardPolicy


class ContractError(ValueError):
    """A closed parallel-validation contract was violated."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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

_FROZEN_MAX_WORKER_COUNT = 8
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
    image_timestamp_s: float
    input_relative_path: str
    input_sha256: str
    deadline_s: float
    execution_kind: ExecutionKind | None = None
    batch_id: str | None = None
    coordinator_epoch: int | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    point_id: str | None = None
    lease_generation: int | None = None
    reset_epoch: str | None = None
    attempt_id: str | None = None
    validation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "model_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        scheduling = (
            self.execution_kind,
            self.batch_id,
            self.coordinator_epoch,
            self.worker_id,
            self.worker_generation,
            self.point_id,
            self.lease_generation,
            self.reset_epoch,
            self.attempt_id,
            self.validation_id,
        )
        if any(value is not None for value in scheduling):
            for name in ("batch_id", "worker_id", "point_id", "reset_epoch"):
                object.__setattr__(
                    self, name, _require_id(name, getattr(self, name))
                )
            for name in (
                "coordinator_epoch",
                "worker_generation",
                "lease_generation",
            ):
                object.__setattr__(
                    self,
                    name,
                    _require_positive_int(name, getattr(self, name)),
                )
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
        deadline_s = _require_finite("deadline_s", self.deadline_s)
        if deadline_s <= 0:
            raise ContractError("deadline_s")
        object.__setattr__(self, "deadline_s", deadline_s)
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
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        _require_enum("run_mode", self.run_mode, RunMode)
        if not isinstance(self.batch_terminal, bool):
            raise ContractError("BOOLEAN: batch_terminal")
        if not isinstance(self.batch_cleanup_complete, bool):
            raise ContractError("BOOLEAN: batch_cleanup_complete")
        if self.terminal_reason is not None:
            object.__setattr__(
                self,
                "terminal_reason",
                _require_id("terminal_reason", self.terminal_reason),
            )
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
        return (
            self.terminal_reason == "POINTS_COMPLETE"
            and self.validation_complete
            and all(
                status is ValidationStatus.VALIDATION_PASSED
                for status in self.validation_statuses.values()
            )
        )

    @property
    def qualification_applicable(self) -> bool:
        return self.run_mode is RunMode.EXECUTE

    @property
    def qualification_passed(self) -> bool:
        return (
            self.terminal_reason == "POINTS_COMPLETE"
            and self.coverage_complete
            and self.batch_cleanup_complete
            and all(
                status is PointStatus.PASSED for status in self.point_statuses.values()
            )
        )


# --- Version-two execution contract -------------------------------------------------
#
# v2 keeps the v1 execution/flow values but removes the lifetime point quota and the
# old resource formulas. v1 documents stay byte-identical and are readable only through
# HistoricalContractView; every new execution entry point must call require_v2_execution.

_V2_REMOVED_V1_FIELDS = (
    "max_points_per_worker_upper_bound",
    "min_logical_cpu_per_worker",
    "available_ram_base_gib",
    "available_ram_per_worker_gib",
    "min_available_gpu_gib",
    "required_live_headroom_ratio",
)

_V2_EXECUTION_SCALARS = tuple(
    name for name in (item.name for item in fields(ParallelRuntimeConfig))
    if name not in _V2_REMOVED_V1_FIELDS and name != "schema_version"
)

_COVERAGE_CELLS = (
    "COLD_START",
    "STEADY_YOLO",
    "STEADY_GROUNDED_SAM",
    "STEADY_MIXED",
    "MOTION_RELEASE",
    "BROKER_RELOAD_WITH_N_RESIDENT",
    "WORKER_RECOVERY_WITH_N_RESIDENT",
    "FINALIZATION_CLEANUP",
)

_DEPLOYMENT_REFERENCE_FIELDS = (
    "approved_profile_path",
    "approved_profile_sha256",
    "promotion_record_path",
)

# Public field lists bound by the normalization rule L (resource_identity).
V2_EXECUTION_SCALAR_FIELDS = _V2_EXECUTION_SCALARS
V2_DEPLOYMENT_REFERENCE_FIELDS = _DEPLOYMENT_REFERENCE_FIELDS


class _ClosedSafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of last-one-wins."""


def _closed_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, (str, int, float, bool, type(None))):
            raise ContractError("MAPPING_KEY_TYPE")
        if key in mapping:
            raise ContractError("DUPLICATE_KEY")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_ClosedSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _closed_mapping
)


def _reject_nonfinite(value: object, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"NONFINITE: {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}[{index}]")


def _load_closed_yaml(path: Path) -> object:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    try:
        document = yaml.load(text, Loader=_ClosedSafeLoader)
    except ContractError:
        raise
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    _reject_nonfinite(document)
    return document


# Fields removed from the authoritative policy by the CPU/RAM/GPU-only amendment
# (dispatch 74d6b781-840d-474b-b997-f2dc24907792). Accepted when present as
# deprecated compatibility data, never required and never consulted.
_DEPRECATED_SAFETY_FIELDS = frozenset({"abort_on_swap_activity", "abort_on_psi_full_stall"})


def _closed_mapping_fields(name: str, document: object, expected: set[str],
                           deprecated: set[str] | None = None) -> dict:
    """Validate a closed mapping, allowing named deprecated keys to be absent.

    A deprecated key is accepted when present (old documents still parse) and is not
    required (the CPU/RAM/GPU-only amendment drops it from the authoritative policy).
    """

    optional = set(deprecated or ())
    if not isinstance(document, Mapping):
        raise ContractError(f"{name}_MAPPING")
    unknown = set(document) - expected
    missing = (expected - optional) - set(document)
    if unknown:
        raise ContractError(f"UNKNOWN_{name}_FIELD: {sorted(unknown)!r}")
    if missing:
        raise ContractError(f"MISSING_{name}_FIELD: {sorted(missing)!r}")
    return dict(document)


def require_v2_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for legacy or unknown contract versions."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("LEGACY_CONTRACT_EXECUTION_FORBIDDEN")
    if request_version != 2 or config_version != 2:
        raise ContractError("LEGACY_CONTRACT_EXECUTION_FORBIDDEN")


class BatchKindV2(StrEnum):
    FIRST_PASS = "FIRST_PASS"
    FULL_RESTART_RETRY = "FULL_RESTART_RETRY"
    ADAPTIVE_POOL = "ADAPTIVE_POOL"


@dataclass(frozen=True, slots=True)
class FixedExecutionConfigV2:
    schema_version: int
    execution_mode: str
    worker_count: int

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ContractError("SCHEMA_VERSION")
        if self.execution_mode not in {"SEQUENTIAL", "PARALLEL"}:
            raise ContractError("EXECUTION_MODE")
        object.__setattr__(
            self, "worker_count", _require_positive_int("worker_count", self.worker_count)
        )
        if self.execution_mode == "SEQUENTIAL":
            if self.worker_count != 1:
                raise ContractError("SEQUENTIAL_WORKER_COUNT")
        elif not 2 <= self.worker_count <= _FROZEN_MAX_WORKER_COUNT:
            raise ContractError("PARALLEL_WORKER_COUNT")


@dataclass(frozen=True, slots=True)
class SamplingRulesV2:
    resource_sample_interval_s: float
    fast_channel_interval_s: float
    pss_sample_interval_s: float
    primary_cpu_window_s: float
    review_cpu_window_s: float
    cgroup_cpu_period_us: int
    baseline_minimum_s: float
    post_cleanup_quiet_s: float
    maximum_sample_gap_s: float

    def __post_init__(self) -> None:
        for name in (
            "resource_sample_interval_s",
            "fast_channel_interval_s",
            "pss_sample_interval_s",
            "primary_cpu_window_s",
            "review_cpu_window_s",
            "baseline_minimum_s",
            "post_cleanup_quiet_s",
            "maximum_sample_gap_s",
        ):
            object.__setattr__(
                self, name, _require_finite(name, getattr(self, name), minimum=0.000001)
            )
        object.__setattr__(
            self,
            "cgroup_cpu_period_us",
            _require_positive_int("cgroup_cpu_period_us", self.cgroup_cpu_period_us),
        )
        if self.fast_channel_interval_s > self.resource_sample_interval_s:
            raise ContractError("FAST_CHANNEL_SLOWER_THAN_PRIMARY")


@dataclass(frozen=True, slots=True)
class ClockRulesV2:
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
class SafetyRulesV2:
    capacity_fraction: float
    minimum_free_fraction: float
    gpu_device_index: int
    throttling_disqualifies_run: bool
    require_complete_attribution: bool
    # Deprecated compatibility fields from the pre-amendment policy (dispatch
    # 74d6b781-840d-474b-b997-f2dc24907792). Documents that still carry them parse, but
    # they are never consulted: swap and PSI are not policy dimensions any more.
    abort_on_swap_activity: bool | None = None
    abort_on_psi_full_stall: bool | None = None

    def __post_init__(self) -> None:
        for name in ("capacity_fraction", "minimum_free_fraction"):
            object.__setattr__(
                self, name, _require_probability(name, getattr(self, name))
            )
        if self.capacity_fraction != 0.8 or self.minimum_free_fraction != 0.2:
            raise ContractError("SAFETY_ENVELOPE")
        for name in (
            "throttling_disqualifies_run",
            "require_complete_attribution",
        ):
            if getattr(self, name) is not True:
                raise ContractError(f"SAFETY_RULE_DISABLED: {name}")
        if type(self.gpu_device_index) is not int or self.gpu_device_index < 0:
            raise ContractError("GPU_DEVICE_INDEX")


@dataclass(frozen=True, slots=True)
class CoverageRulesV2:
    policy: str
    required_normal_runs: int
    required_full_restart: bool
    qualification_point_count: int
    cells: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.policy != "EXACT_N_V2":
            raise ContractError("COVERAGE_POLICY")
        if self.required_normal_runs != 5:
            raise ContractError("COVERAGE_NORMAL_RUNS")
        if self.required_full_restart is not True:
            raise ContractError("COVERAGE_FULL_RESTART")
        if self.qualification_point_count != 20:
            raise ContractError("COVERAGE_POINT_COUNT")
        cells = tuple(self.cells)
        if cells != _COVERAGE_CELLS:
            raise ContractError("COVERAGE_CELLS")
        object.__setattr__(self, "cells", cells)


@dataclass(frozen=True, slots=True)
class MeasurementRulesV2:
    sampling: SamplingRulesV2
    clock: ClockRulesV2
    safety: SafetyRulesV2
    coverage: CoverageRulesV2

    def __post_init__(self) -> None:
        for name in ("sampling", "clock", "safety", "coverage"):
            if not isinstance(getattr(self, name), {
                "sampling": SamplingRulesV2, "clock": ClockRulesV2,
                "safety": SafetyRulesV2, "coverage": CoverageRulesV2,
            }[name]):
                raise ContractError(f"MEASUREMENT_RULE_TYPE: {name}")


@dataclass(frozen=True, slots=True)
class DeploymentReferencesV2:
    approved_profile_path: str | None
    approved_profile_sha256: str | None
    promotion_record_path: str | None

    def __post_init__(self) -> None:
        path = self.approved_profile_path
        digest = self.approved_profile_sha256
        promotion = self.promotion_record_path
        if path is not None and (not isinstance(path, str) or not Path(path).is_absolute()):
            raise ContractError("APPROVED_PROFILE_PATH")
        if promotion is not None and (
            not isinstance(promotion, str) or not Path(promotion).is_absolute()
        ):
            raise ContractError("PROMOTION_RECORD_PATH")
        if digest is not None:
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                raise ContractError("APPROVED_PROFILE_SHA256")
        if any(value is not None for value in (path, digest, promotion)) and not all(
            value is not None for value in (path, digest, promotion)
        ):
            raise ContractError("DEPLOYMENT_REFERENCE_INCOMPLETE")

    @property
    def is_candidate(self) -> bool:
        return self.approved_profile_path is None

    @property
    def is_complete(self) -> bool:
        return all(
            getattr(self, name) is not None for name in _DEPLOYMENT_REFERENCE_FIELDS
        )


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfigV2:
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
    measurement: MeasurementRulesV2
    deployment: DeploymentReferencesV2

    FROZEN_YOLO_WEIGHTS_SHA256: ClassVar[str] = _FROZEN_YOLO_WEIGHTS_SHA256
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256: ClassVar[str] = (
        _FROZEN_GROUNDED_SAM_MANIFEST_SHA256
    )

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
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
        ):
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
        ):
            object.__setattr__(self, name, _require_probability(name, getattr(self, name)))
        object.__setattr__(self, "yolo_model_id", _require_id("yolo_model_id", self.yolo_model_id))
        if self.requested_device != "cuda":
            raise ContractError("REQUESTED_DEVICE")
        if not isinstance(self.allow_cpu_fallback, bool) or self.allow_cpu_fallback:
            raise ContractError("ALLOW_CPU_FALLBACK")
        if not isinstance(self.measurement, MeasurementRulesV2):
            raise ContractError("MEASUREMENT_RULES")
        if not isinstance(self.deployment, DeploymentReferencesV2):
            raise ContractError("DEPLOYMENT_REFERENCES")
        for name, expected in _FROZEN_RUNTIME_VALUES_V2.items():
            if getattr(self, name) != expected:
                raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
        if len(domains) != self.max_worker_count or len(set(domains)) != len(domains):
            raise ContractError("ROS_DOMAIN_IDS")

    @property
    def yolo_weights_sha256(self) -> str:
        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256


_FROZEN_RUNTIME_VALUES_V2 = {
    **{
        name: value for name, value in _FROZEN_RUNTIME_VALUES.items()
        if name not in _V2_REMOVED_V1_FIELDS
    },
    "schema_version": 2,
}


def parse_parallel_runtime_config_v2(document: object) -> ParallelRuntimeConfigV2:
    """Validate an already-parsed version-two document against the closed schema."""

    top = _closed_mapping_fields("CONFIG", document, {"schema_version", "execution", "deployment"})
    if type(top["schema_version"]) is not int or top["schema_version"] != 2:
        raise ContractError("SCHEMA_VERSION")
    execution = _closed_mapping_fields(
        "EXECUTION", top["execution"], set(_V2_EXECUTION_SCALARS) | {"sampling", "clock", "safety", "coverage"}
    )
    deployment = _closed_mapping_fields(
        "DEPLOYMENT", top["deployment"], set(_DEPLOYMENT_REFERENCE_FIELDS)
    )
    sampling = _closed_mapping_fields(
        "SAMPLING", execution.pop("sampling"), {item.name for item in fields(SamplingRulesV2)}
    )
    clock = _closed_mapping_fields(
        "CLOCK", execution.pop("clock"), {item.name for item in fields(ClockRulesV2)}
    )
    safety = _closed_mapping_fields(
        "SAFETY", execution.pop("safety"), {item.name for item in fields(SafetyRulesV2)},
        deprecated=_DEPRECATED_SAFETY_FIELDS,
    )
    coverage = _closed_mapping_fields(
        "COVERAGE", execution.pop("coverage"), {item.name for item in fields(CoverageRulesV2)}
    )
    return ParallelRuntimeConfigV2(
        schema_version=2,
        measurement=MeasurementRulesV2(
            sampling=SamplingRulesV2(**sampling),
            clock=ClockRulesV2(**clock),
            safety=SafetyRulesV2(**safety),
            coverage=CoverageRulesV2(**coverage),
        ),
        deployment=DeploymentReferencesV2(**deployment),
        **execution,
    )


def load_runtime_config_any_schema(path: Path):
    """Load a v1 or v2 runtime document, choosing the parser by its declared schema.

    The broker and its transport are shared by both generations: a v2 measurement hands them a
    v2 document, and the v1 parser refuses it by design (`UNKNOWN_CONFIG_FIELD`), so the
    selection has to be explicit here rather than assumed.
    """

    import yaml

    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    if not isinstance(document, dict):
        raise ContractError("CONFIG_MAPPING")
    version = document.get("schema_version")
    if version == 4:
        return load_parallel_runtime_config_v4(Path(path))
    if version == 3:
        return load_parallel_runtime_config_v3(Path(path))
    if version == 2:
        return load_parallel_runtime_config_v2(Path(path))
    if version == 1:
        return load_parallel_runtime_config(Path(path))
    raise ContractError(f"SCHEMA_VERSION: {version!r}")


def load_parallel_runtime_config_v2(path: Path) -> ParallelRuntimeConfigV2:
    """Load the closed version-two YAML document; reject any drift or legacy quota."""

    return parse_parallel_runtime_config_v2(_load_closed_yaml(path))


@dataclass(frozen=True, slots=True)
class HistoricalContractView:
    """Read-only view of a retained legacy document; it never authorizes execution."""

    version: int
    raw_sha256: str
    payload: Mapping[str, object]

    @property
    def readonly(self) -> bool:
        return True


def read_historical_contract(path: Path) -> HistoricalContractView:
    """Read a legacy contract only for history, audit and recovery checks."""

    raw = Path(path).read_bytes()
    document = _load_closed_yaml(path)
    if not isinstance(document, Mapping) or type(document.get("schema_version")) is not int:
        raise ContractError("SCHEMA_VERSION")
    version = document["schema_version"]
    if version != 1:
        raise ContractError("UNKNOWN_SCHEMA_VERSION")
    return HistoricalContractView(
        version=version,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        payload=MappingProxyType(dict(document)),
    )


@dataclass(frozen=True, slots=True)
class BatchRequestV2:
    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    worker_count: int
    evidence_root: Path
    batch_kind: BatchKindV2
    schema_version: int = 2

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ContractError("SCHEMA_VERSION")
        object.__setattr__(self, "batch_id", _require_id("batch_id", self.batch_id))
        _require_enum("run_mode", self.run_mode, RunMode)
        _require_enum("batch_kind", self.batch_kind, BatchKindV2)
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
        object.__setattr__(
            self,
            "evidence_root",
            _require_absolute_path("evidence_root", self.evidence_root),
        )
        if self.batch_kind is BatchKindV2.FULL_RESTART_RETRY and (
            len(point_ids) != 1 or self.worker_count != 1
        ):
            raise ContractError("RETRY_SINGLE_POINT_N1")

# --------------------------------------------------------------------------------------
# Version 3: the active budget-free contract
#
# New execution uses exactly this closed document. Version 1 and version 2 stay readable for
# history, audit and recovery only, and every new execution entry point must call
# require_v3_execution so a legacy document can never silently carry the new semantics.
# --------------------------------------------------------------------------------------

#: The closed set of ``execution`` fields for v3. Sampling, safety and coverage are gone;
#: the GPU selector moved next to the other device settings and the clock rules stay because
#: they describe functional simulation timing, not a resource budget.
EXECUTION_V3_FIELDS = frozenset({
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
class ClockRulesV3:
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
class ParallelRuntimeConfigV3:
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
    clock: ClockRulesV3
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
        if not isinstance(self.clock, ClockRulesV3):
            raise ContractError("CLOCK_RULES")
        if not isinstance(self.gpu_device, GpuDeviceSelector):
            raise ContractError("GPU_DEVICE_SELECTOR")
        if not isinstance(self.start_guard, StartGuardPolicy):
            raise ContractError("START_GUARD_POLICY")
        for name, expected in _FROZEN_RUNTIME_VALUES_V3.items():
            if getattr(self, name) != expected:
                raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
        if len(domains) != self.max_worker_count or len(set(domains)) != len(domains):
            raise ContractError("ROS_DOMAIN_IDS")

    @property
    def yolo_weights_sha256(self) -> str:
        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256


_FROZEN_RUNTIME_VALUES_V3 = {
    **{
        name: value for name, value in _FROZEN_RUNTIME_VALUES.items()
        if name not in _V2_REMOVED_V1_FIELDS
    },
    "schema_version": 3,
}

START_GUARD_FIELDS = frozenset({"timeout_s", "cpu_busy_warn_fraction", "ram_minimum_bytes",
                                "ram_minimum_fraction", "gpu_minimum_bytes"})


def parse_parallel_runtime_config_v3(document: object) -> ParallelRuntimeConfigV3:
    """Validate a version-three document against the closed, budget-free schema."""

    top = _closed_mapping_fields("CONFIG", document, {"schema_version", "execution", "start_guard"})
    if type(top["schema_version"]) is not int or top["schema_version"] != 3:
        raise ContractError("SCHEMA_VERSION")
    execution = _closed_mapping_fields("EXECUTION", top["execution"], set(EXECUTION_V3_FIELDS))
    guard = _closed_mapping_fields("START_GUARD", top["start_guard"], set(START_GUARD_FIELDS))
    clock = _closed_mapping_fields(
        "CLOCK", execution.pop("clock"), {item.name for item in fields(ClockRulesV3)}
    )
    gpu_device = _closed_mapping_fields(
        "GPU_DEVICE", execution.pop("gpu_device"), {"selector_kind", "selector"}
    )
    try:
        guard_policy = StartGuardPolicy(**guard)
        selector = GpuDeviceSelector(**gpu_device)
    except ValueError as error:
        raise ContractError(f"START_GUARD_INVALID: {error}") from error
    return ParallelRuntimeConfigV3(
        schema_version=3,
        clock=ClockRulesV3(**clock),
        gpu_device=selector,
        start_guard=guard_policy,
        **execution,
    )


def load_parallel_runtime_config_v3(path: Path) -> ParallelRuntimeConfigV3:
    """Load the closed version-three YAML document; any drift or legacy key is refused."""

    return parse_parallel_runtime_config_v3(_load_closed_yaml(path))


def require_v3_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for any contract version other than the active one."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    if request_version != 3 or config_version != 3:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")


#: Version three keeps the functional batch-kind semantics of version two.
BatchKindV3 = BatchKindV2


@dataclass(frozen=True, slots=True)
class BatchRequestV3:
    """A new execution request. It carries no budget hash, profile or approval reference."""

    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    worker_count: int
    evidence_root: Path
    batch_kind: BatchKindV3
    schema_version: int = 3

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 3:
            raise ContractError("SCHEMA_VERSION")
        object.__setattr__(self, "batch_id", _require_id("batch_id", self.batch_id))
        _require_enum("run_mode", self.run_mode, RunMode)
        _require_enum("batch_kind", self.batch_kind, BatchKindV2)
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
        object.__setattr__(
            self,
            "evidence_root",
            _require_absolute_path("evidence_root", self.evidence_root),
        )
        if self.batch_kind is BatchKindV2.FULL_RESTART_RETRY and (
            len(point_ids) != 1 or self.worker_count != 1
        ):
            raise ContractError("RETRY_SINGLE_POINT_N1")


REQUEST_V3_FIELDS = ("schema_version", "batch_id", "run_mode", "selected_point_ids",
                     "worker_count", "evidence_root", "batch_kind")


def batch_request_to_document(request: BatchRequestV3) -> dict:
    """Serialize an active request for the CLI/Web producer and the allocator consumer."""

    if not isinstance(request, BatchRequestV3):
        raise ContractError("REQUEST_TYPE")
    return {
        "schema_version": 3,
        "batch_id": request.batch_id,
        "run_mode": str(request.run_mode),
        "selected_point_ids": list(request.selected_point_ids),
        "worker_count": request.worker_count,
        "evidence_root": str(request.evidence_root),
        "batch_kind": str(request.batch_kind),
    }


def batch_request_from_document(document: object, *, for_execution: bool
                                ) -> "BatchRequestV3 | dict":
    """Read a request record.

    ``for_execution=True`` accepts only the active version and is the only path that can
    produce something the allocator will run. ``for_execution=False`` is the history reader:
    version 1 and 2 documents are returned as plain read-only mappings and are never
    converted into an active request.
    """

    if not isinstance(document, Mapping):
        raise ContractError("REQUEST_MAPPING")
    version = document.get("schema_version")
    if not for_execution:
        if version in (1, 2):
            return dict(document)
        if version != 3:
            raise ContractError(f"UNKNOWN_SCHEMA_VERSION: {version!r}")
    elif version != 3:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    unknown = set(document) - set(REQUEST_V3_FIELDS)
    missing = set(REQUEST_V3_FIELDS) - set(document)
    if unknown:
        raise ContractError(f"UNKNOWN_REQUEST_FIELD: {sorted(unknown)!r}")
    if missing:
        raise ContractError(f"MISSING_REQUEST_FIELD: {sorted(missing)!r}")
    return BatchRequestV3(
        batch_id=document["batch_id"],
        run_mode=RunMode(document["run_mode"]),
        selected_point_ids=tuple(document["selected_point_ids"]),
        worker_count=document["worker_count"],
        evidence_root=Path(document["evidence_root"]),
        batch_kind=BatchKindV3(document["batch_kind"]),
    )

# --------------------------------------------------------------------------------------
# Version 4: the closed platform-combination contract
#
# Version 3 stays byte- and semantics-frozen: it is the Linux CUDA/NVML contract and is
# still the version this repository executes on ai-station. Version 4 exists so a second
# platform can be named explicitly instead of being inferred, and it is closed in both
# directions: exactly two combinations are admitted, and nothing outside them parses.
#
#   Linux   : accelerator cuda + requested_device cuda + proc_fd_unix   + mujoco_gl egl
#   macOS   : accelerator mps  + requested_device mps  + darwin_private_path_unix + cgl
#
# The Linux combination is retained in this contract (and covered by offline unit tests)
# because removing it would silently narrow the product to one platform. It is not
# executed in this task: there is no Linux environment, so it is DEFERRED_ENVIRONMENT.
# --------------------------------------------------------------------------------------


class AcceleratorKind(StrEnum):
    """The accelerator family a v4 document may select."""

    CUDA = "cuda"
    MPS = "mps"


class IpcTransport(StrEnum):
    """The closed set of v4 AF_UNIX address strategies."""

    PROC_FD_UNIX = "proc_fd_unix"
    DARWIN_PRIVATE_PATH_UNIX = "darwin_private_path_unix"


#: value written for ``ipc_transport`` to mean "this platform's closed default".
IPC_TRANSPORT_AUTO = "auto"

#: Exactly the two admitted (accelerator, device, transport, GL) combinations.
V4_PLATFORM_COMBINATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("cuda", "cuda", "proc_fd_unix", "egl"),
    ("mps", "mps", "darwin_private_path_unix", "cgl"),
)

#: Per-platform default transport for ``ipc_transport: auto``. Never TCP.
V4_AUTO_TRANSPORT_BY_PLATFORM: Mapping[str, str] = MappingProxyType({
    "linux": "proc_fd_unix",
    "darwin": "darwin_private_path_unix",
})

#: The only worker count this platform contract supports. W1/W4/W6/W8 are out of scope and
#: the design forbids extrapolating any cross-N qualification from this value.
V4_PLATFORM_WORKER_COUNT = 2

#: v4 keeps the frozen functional timing, frame and model values of v3. It only replaces the
#: platform selection, so the freeze itself is restated here instead of being duplicated.
#:
#: Deliberately absent, because they are platform-selected rather than globally frozen:
#: - `ros_domain_ids` is a per-platform isolation choice (the Darwin combination uses two);
#: - `requested_device` / `allow_cpu_fallback` belong to the platform combination;
#: - `mps_process_memory_fraction` is the Darwin allocator cap and is refused on Linux;
#: - `mujoco_gl` / `ipc_transport` follow from the combination (or from a resolved `auto`).
#: The platform-specific pins live in FROZEN_DARWIN_VALUES_V4 / FROZEN_LINUX_VALUES_V4.
FROZEN_RUNTIME_VALUES_V4: Mapping[str, object] = MappingProxyType({
    **{
        name: value
        for name, value in _FROZEN_RUNTIME_VALUES_V3.items()
        if name not in {"schema_version", "requested_device", "gpu_device", "ros_domain_ids"}
    },
    "schema_version": 4,
    "worker_count": V4_PLATFORM_WORKER_COUNT,
})

#: The values the Darwin combination adds on top of the shared freeze. Validated on the
#: Darwin path only, so a Linux v4 document is free to leave them absent.
FROZEN_DARWIN_VALUES_V4: Mapping[str, object] = MappingProxyType({
    "requested_device": "mps",
    "accelerator_kind": "mps",
    "accelerator_selector": "default",
    "allow_cpu_fallback": False,
    "mps_process_memory_fraction": 0.8,
    "mujoco_gl": "cgl",
    "ipc_transport": "darwin_private_path_unix",
})

#: The values the Linux combination pins. Not executed in this task: DEFERRED_ENVIRONMENT.
FROZEN_LINUX_VALUES_V4: Mapping[str, object] = MappingProxyType({
    "requested_device": "cuda",
    "accelerator_kind": "cuda",
    "allow_cpu_fallback": False,
    "mps_process_memory_fraction": None,
    "mujoco_gl": "egl",
    "ipc_transport": "proc_fd_unix",
})

ACCELERATOR_FIELDS = frozenset({"kind", "selector"})
START_GUARD_V4_FIELDS = frozenset(set(START_GUARD_FIELDS) | {"mps_minimum_headroom_bytes"})

#: Everything the v4 ``execution`` section may carry: the v3 functional fields minus the
#: platform-specific device/GPU selection, which moved to the top-level ``accelerator`` block.
#: ``requested_device`` and ``allow_cpu_fallback`` moved to the top level as well: in v4 they
#: describe the selected platform combination, not a per-run execution knob.
EXECUTION_V4_FIELDS = frozenset(
    set(EXECUTION_V3_FIELDS) - {"requested_device", "allow_cpu_fallback", "gpu_device"}
)

V4_CONFIG_FIELDS = frozenset({
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
class AcceleratorSelectionV4:
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
        if kind is AcceleratorKind.MPS:
            # One Apple GPU: the only valid MPS selector is the explicit default.
            if self.selector != "default":
                raise ContractError("ACCELERATOR_SELECTOR")
        else:
            GpuDeviceSelector(*_split_selector(self.selector))

    @property
    def resolved_selector(self) -> str:
        """The selector as the manifest records it, always explicit."""

        if self.kind is AcceleratorKind.MPS:
            return "default"
        return self.selector


def _split_selector(selector: str) -> tuple[str, str]:
    if not isinstance(selector, str):
        raise ContractError("ACCELERATOR_SELECTOR")
    if selector == "default":
        raise ContractError("ACCELERATOR_SELECTOR")
    if selector.startswith("GPU-"):
        return "UUID", selector
    if ":" in selector:
        kind, _, body = selector.partition(":")
        if kind in _GPU_SELECTOR_KINDS:
            return kind, body
    if selector.isdigit():
        return "INDEX", selector
    raise ContractError("ACCELERATOR_SELECTOR")


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfigV4:
    """The closed version-four document: exact W2 on one of two named platform combinations."""

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
    clock: ClockRulesV3
    start_guard: "StartGuardPolicy"
    accelerator: AcceleratorSelectionV4
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
        if not isinstance(self.accelerator, AcceleratorSelectionV4):
            raise ContractError("ACCELERATOR_SELECTION")
        try:
            transport = IpcTransport(self.ipc_transport)
        except ValueError as error:
            raise ContractError("IPC_TRANSPORT") from error
        object.__setattr__(self, "ipc_transport", transport)

        combination = (
            str(self.accelerator.kind), self.requested_device, str(transport), self.mujoco_gl,
        )
        if combination not in V4_PLATFORM_COMBINATIONS:
            raise ContractError("PLATFORM_COMBINATION_UNSUPPORTED")

        # Exact W2. Any other count is a different platform claim this contract does not make.
        if isinstance(self.worker_count, bool) or self.worker_count != V4_PLATFORM_WORKER_COUNT:
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
        if not isinstance(self.clock, ClockRulesV3):
            raise ContractError("CLOCK_RULES")
        if not isinstance(self.start_guard, StartGuardPolicy):
            raise ContractError("START_GUARD_POLICY")

        if transport is IpcTransport.DARWIN_PRIVATE_PATH_UNIX:
            # The allocator cap is set before any MPS allocation, so it must be a real
            # fraction on the Darwin combination and absent everywhere else.
            object.__setattr__(
                self, "mps_process_memory_fraction",
                _require_fraction("MPS_PROCESS_MEMORY_FRACTION", self.mps_process_memory_fraction),
            )
            headroom = self.start_guard.mps_minimum_headroom_bytes
            if headroom is None:
                raise ContractError("MPS_MINIMUM_HEADROOM_BYTES")
            _require_positive_bytes("MPS_MINIMUM_HEADROOM_BYTES", headroom)
        else:
            if self.mps_process_memory_fraction is not None:
                raise ContractError("MPS_PROCESS_MEMORY_FRACTION")
            if self.start_guard.mps_minimum_headroom_bytes is not None:
                raise ContractError("MPS_MINIMUM_HEADROOM_BYTES")

        platform_pins = (
            FROZEN_DARWIN_VALUES_V4
            if transport is IpcTransport.DARWIN_PRIVATE_PATH_UNIX
            else FROZEN_LINUX_VALUES_V4
        )
        for name, expected in FROZEN_RUNTIME_VALUES_V4.items():
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


def _resolve_v4_transport(
    value: object, accelerator: AcceleratorSelectionV4
) -> dict:
    """Resolve ``auto`` to the current platform's closed default; never to TCP."""

    if value == IPC_TRANSPORT_AUTO:
        if accelerator.kind is AcceleratorKind.MPS:
            return {"ipc_transport": "darwin_private_path_unix", "mujoco_gl": "cgl"}
        return {"ipc_transport": "proc_fd_unix", "mujoco_gl": "egl"}
    return {}


def parse_parallel_runtime_config_v4(document: object) -> ParallelRuntimeConfigV4:
    """Validate a version-four document against the closed platform-combination schema."""

    top = _closed_mapping_fields("CONFIG", document, set(V4_CONFIG_FIELDS))
    if type(top["schema_version"]) is not int or top["schema_version"] != 4:
        raise ContractError("SCHEMA_VERSION")
    accelerator_fields = _closed_mapping_fields(
        "ACCELERATOR", top["accelerator"], set(ACCELERATOR_FIELDS)
    )
    execution = _closed_mapping_fields(
        "EXECUTION", top["execution"], set(EXECUTION_V4_FIELDS)
    )
    guard = _closed_mapping_fields(
        "START_GUARD", top["start_guard"], set(START_GUARD_V4_FIELDS),
        {"mps_minimum_headroom_bytes"},
    )
    clock = _closed_mapping_fields(
        "CLOCK", execution.pop("clock"), {item.name for item in fields(ClockRulesV3)}
    )
    try:
        accelerator = AcceleratorSelectionV4(
            kind=AcceleratorKind(accelerator_fields["kind"]),
            selector=accelerator_fields["selector"],
        )
    except (ValueError, KeyError) as error:
        raise ContractError(f"ACCELERATOR_INVALID: {error}") from error

    resolved = _resolve_v4_transport(top["ipc_transport"], accelerator)
    try:
        guard_policy = StartGuardPolicy(**guard)
    except ValueError as error:
        raise ContractError(f"START_GUARD_INVALID: {error}") from error
    return ParallelRuntimeConfigV4(
        schema_version=4,
        clock=ClockRulesV3(**clock),
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


def load_parallel_runtime_config_v4(path: Path) -> ParallelRuntimeConfigV4:
    """Load the closed version-four YAML document; any drift or cross-platform key is refused."""

    return parse_parallel_runtime_config_v4(_load_closed_yaml(path))


def require_v4_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for any contract version other than version four."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    if request_version != 4 or config_version != 4:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")


#: Version four keeps the functional batch-kind semantics of versions two and three.
BatchKindV4 = BatchKindV2
