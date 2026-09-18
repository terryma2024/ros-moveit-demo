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
