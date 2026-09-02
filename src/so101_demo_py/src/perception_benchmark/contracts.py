"""Validated immutable records for the perception benchmark."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Mapping

from so101_demo.core.detection import RuntimeDevice

SCHEMA_VERSION = "so101-perception-benchmark/v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RunStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    VALID = "VALID"
    INVALID = "INVALID"


class RecordStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"


class RunKind(str, Enum):
    NON_FORMAL_DRY_RUN = "NON_FORMAL_DRY_RUN"
    VAL_RAW = "VAL_RAW"
    TEST_RAW_FROZEN = "TEST_RAW_FROZEN"
    TEST_PRODUCTION = "TEST_PRODUCTION"
    TEST_CALIBRATED = "TEST_CALIBRATED"
    TEST_CHARACTERIZATION = "TEST_CHARACTERIZATION"
    ORACLE_DIAGNOSTIC = "ORACLE_DIAGNOSTIC"


class DecisionOutput(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    ERROR = "ERROR"


def _require_sha256(name: str, value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA256 digest")
    return value


def _require_nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be non-empty")
    return value


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_probability(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return result


def _require_nonnegative_finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and nonnegative")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _require_optional_nonnegative_finite(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _require_nonnegative_finite(name, value)


def _require_relative_path(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{name} must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{name} must be a safe relative path")
    return value


def _require_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


@dataclass(frozen=True, slots=True)
class MaskRef:
    relative_path: str
    sha256: str
    pixel_count: int
    image_width: int
    image_height: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_path", _require_relative_path("relative_path", self.relative_path))
        object.__setattr__(self, "sha256", _require_sha256("sha256", self.sha256))
        if isinstance(self.pixel_count, bool) or not isinstance(self.pixel_count, int) or self.pixel_count < 0:
            raise ValueError("pixel_count must be a nonnegative integer")
        object.__setattr__(self, "image_width", _require_positive_int("image dimensions", self.image_width))
        object.__setattr__(self, "image_height", _require_positive_int("image dimensions", self.image_height))
        if self.pixel_count > self.image_width * self.image_height:
            raise ValueError("pixel_count must not exceed image area")


@dataclass(frozen=True, slots=True)
class TruthInstance:
    instance_id: str
    label: str
    mask: MaskRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _require_nonempty("instance_id", self.instance_id))
        if self.label != "plastic_cup":
            raise ValueError("truth label must be plastic_cup")
        if not isinstance(self.mask, MaskRef):
            raise ValueError("mask must be a MaskRef")


@dataclass(frozen=True, slots=True)
class TruthSample:
    formal_sample_index: int
    split: str
    scenario: str
    image_relpath: str
    image_sha256: str
    image_width: int
    image_height: int
    instances: tuple[TruthInstance, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.formal_sample_index, bool)
            or not isinstance(self.formal_sample_index, int)
            or self.formal_sample_index < 0
        ):
            raise ValueError("formal_sample_index must be a nonnegative integer")
        object.__setattr__(self, "split", _require_nonempty("split", self.split))
        object.__setattr__(self, "scenario", _require_nonempty("scenario", self.scenario))
        object.__setattr__(self, "image_relpath", _require_relative_path("image_relpath", self.image_relpath))
        object.__setattr__(self, "image_sha256", _require_sha256("image_sha256", self.image_sha256))
        object.__setattr__(self, "image_width", _require_positive_int("image dimensions", self.image_width))
        object.__setattr__(self, "image_height", _require_positive_int("image dimensions", self.image_height))
        instances = tuple(self.instances)
        if not all(isinstance(instance, TruthInstance) for instance in instances):
            raise ValueError("instances must contain TruthInstance values")
        ids = [instance.instance_id for instance in instances]
        if len(ids) != len(set(ids)):
            raise ValueError("truth instance_id values must be unique")
        if any(
            (instance.mask.image_width, instance.mask.image_height)
            != (self.image_width, self.image_height)
            for instance in instances
        ):
            raise ValueError("truth mask dimensions must match image dimensions")
        object.__setattr__(self, "instances", instances)


@dataclass(frozen=True, slots=True)
class RawCandidate:
    candidate_id: str
    label: str
    bbox_xyxy: tuple[float, float, float, float]
    mask: MaskRef
    ranking_score: float
    ranking_score_source: str
    class_confidence: float | None
    grounding_box_score: float | None
    grounding_text_score: float | None
    sam_quality: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ranking_score", _require_probability("ranking_score", self.ranking_score))
        if not self.candidate_id or self.label != "plastic_cup":
            raise ValueError("candidate identity is invalid")
        if not isinstance(self.mask, MaskRef):
            raise ValueError("mask must be a MaskRef")
        bbox = tuple(self.bbox_xyxy)
        if len(bbox) != 4:
            raise ValueError("bbox_xyxy must contain four finite values")
        normalized_bbox = tuple(
            _require_nonnegative_finite("bbox_xyxy", value) for value in bbox
        )
        x_min, y_min, x_max, y_max = normalized_bbox
        if not (
            x_min < x_max <= float(self.mask.image_width)
            and y_min < y_max <= float(self.mask.image_height)
        ):
            raise ValueError("bbox_xyxy must have positive area inside the mask image")
        object.__setattr__(self, "bbox_xyxy", normalized_bbox)
        object.__setattr__(self, "ranking_score_source", _require_nonempty("ranking_score_source", self.ranking_score_source))
        for name in (
            "class_confidence",
            "grounding_box_score",
            "grounding_text_score",
            "sam_quality",
        ):
            value = _require_optional_nonnegative_finite(name, getattr(self, name))
            if value is not None and value > 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class PhaseTimings:
    grounding_ms: float | None = None
    sam_ms: float | None = None
    selector_ms: float | None = None

    def __post_init__(self) -> None:
        for name in ("grounding_ms", "sam_ms", "selector_ms"):
            object.__setattr__(
                self, name, _require_optional_nonnegative_finite(name, getattr(self, name))
            )


@dataclass(frozen=True, slots=True)
class RuntimeProvenance:
    runtime_device: RuntimeDevice
    runtime_name: str
    runtime_version: str
    weights_sha256: str
    environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.runtime_device not in {"cuda", "mps"}:
            raise ValueError("runtime_device must be cuda or mps; cpu is not permitted")
        object.__setattr__(self, "runtime_name", _require_nonempty("runtime_name", self.runtime_name))
        object.__setattr__(self, "runtime_version", _require_nonempty("runtime_version", self.runtime_version))
        object.__setattr__(self, "weights_sha256", _require_sha256("weights_sha256", self.weights_sha256))
        environment = dict(self.environment)
        if not all(isinstance(key, str) and key and isinstance(value, str) and value for key, value in environment.items()):
            raise ValueError("environment must map non-empty strings to non-empty strings")
        object.__setattr__(self, "environment", MappingProxyType(environment))


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    run_id: str
    schema_version: str
    run_kind: RunKind
    record_status: RecordStatus
    formal_sample_index: int
    split: str
    scenario: str
    image_relpath: str
    image_sha256: str
    image_width: int
    image_height: int
    model_id: str
    runtime_provenance: RuntimeProvenance
    config_sha256: str
    threshold_lock_sha256: str | None
    raw_candidates: tuple[RawCandidate, ...]
    phase_timings: PhaseTimings
    raw_count: int
    decision: DecisionOutput
    selected_candidate_id: str | None
    rejection_reason: str | None
    error_type: str | None
    error_summary: str | None
    timed_out: bool
    oom: bool
    fallback_used: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_nonempty("run_id", self.run_id))
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("schema_version is unknown")
        try:
            object.__setattr__(self, "run_kind", RunKind(self.run_kind))
            object.__setattr__(self, "record_status", RecordStatus(self.record_status))
            object.__setattr__(self, "decision", DecisionOutput(self.decision))
        except ValueError as error:
            raise ValueError("run_kind, record_status, and decision must be known values") from error
        if (
            isinstance(self.formal_sample_index, bool)
            or not isinstance(self.formal_sample_index, int)
            or self.formal_sample_index < 0
        ):
            raise ValueError("formal_sample_index must be a nonnegative integer")
        object.__setattr__(self, "split", _require_nonempty("split", self.split))
        object.__setattr__(self, "scenario", _require_nonempty("scenario", self.scenario))
        object.__setattr__(self, "image_relpath", _require_relative_path("image_relpath", self.image_relpath))
        object.__setattr__(self, "image_sha256", _require_sha256("image_sha256", self.image_sha256))
        object.__setattr__(self, "image_width", _require_positive_int("image dimensions", self.image_width))
        object.__setattr__(self, "image_height", _require_positive_int("image dimensions", self.image_height))
        object.__setattr__(self, "model_id", _require_nonempty("model_id", self.model_id))
        if not isinstance(self.runtime_provenance, RuntimeProvenance):
            raise ValueError("runtime_provenance is required")
        object.__setattr__(self, "config_sha256", _require_sha256("config_sha256", self.config_sha256))
        object.__setattr__(
            self,
            "threshold_lock_sha256",
            _require_sha256("threshold_lock_sha256", self.threshold_lock_sha256, optional=True),
        )
        if self.run_kind.name.startswith("TEST_") or self.run_kind is RunKind.ORACLE_DIAGNOSTIC:
            if self.threshold_lock_sha256 is None:
                raise ValueError("threshold_lock_sha256 is required for locked run kinds")
        candidates = tuple(self.raw_candidates)
        if not all(isinstance(candidate, RawCandidate) for candidate in candidates):
            raise ValueError("raw_candidates must contain RawCandidate values")
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id values must be unique")
        if any(
            (candidate.mask.image_width, candidate.mask.image_height)
            != (self.image_width, self.image_height)
            for candidate in candidates
        ):
            raise ValueError("candidate mask dimensions must match prediction image dimensions")
        object.__setattr__(self, "raw_candidates", candidates)
        if isinstance(self.raw_count, bool) or not isinstance(self.raw_count, int) or self.raw_count != len(candidates):
            raise ValueError("raw_count must equal the number of raw_candidates")
        if not isinstance(self.phase_timings, PhaseTimings):
            raise ValueError("phase_timings is required")
        for name in ("timed_out", "oom", "fallback_used"):
            object.__setattr__(self, name, _require_bool(name, getattr(self, name)))
        if self.fallback_used:
            raise ValueError("fallback_used must be false for benchmark records")
        self._validate_model_candidate_fields(candidates)
        self._validate_decision(candidate_ids)

    def _validate_model_candidate_fields(
        self, candidates: tuple[RawCandidate, ...]
    ) -> None:
        normalized_model_id = self.model_id.lower().replace("_", "-")
        if "yolo" in normalized_model_id:
            for candidate in candidates:
                if candidate.class_confidence is None:
                    raise ValueError("YOLO candidates require class_confidence")
                if any(
                    value is not None
                    for value in (
                        candidate.grounding_box_score,
                        candidate.grounding_text_score,
                        candidate.sam_quality,
                    )
                ):
                    raise ValueError("YOLO candidates forbid Grounded-SAM score fields")
                if candidate.ranking_score_source != "class_confidence":
                    raise ValueError("YOLO ranking_score_source must be class_confidence")
                if candidate.ranking_score != candidate.class_confidence:
                    raise ValueError("YOLO ranking_score must match class_confidence")
            return
        if "grounded-sam" in normalized_model_id:
            for candidate in candidates:
                if candidate.class_confidence is not None:
                    raise ValueError("Grounded-SAM candidates forbid class_confidence")
                if any(
                    value is None
                    for value in (
                        candidate.grounding_box_score,
                        candidate.grounding_text_score,
                        candidate.sam_quality,
                    )
                ):
                    raise ValueError("Grounded-SAM candidates require grounding and SAM scores")
                if candidate.ranking_score_source != "grounding_box_score":
                    raise ValueError(
                        "Grounded-SAM ranking_score_source must be grounding_box_score"
                    )
                if candidate.ranking_score != candidate.grounding_box_score:
                    raise ValueError(
                        "Grounded-SAM ranking_score must match grounding_box_score"
                    )
            return
        if candidates:
            raise ValueError("model_id must identify YOLO or Grounded-SAM candidates")

    def _validate_decision(self, candidate_ids: list[str]) -> None:
        if self.record_status is RecordStatus.ERROR:
            if self.decision is not DecisionOutput.ERROR:
                raise ValueError("ERROR record_status requires DecisionOutput.ERROR")
            if not self.error_type:
                raise ValueError("ERROR record_status requires error_type")
            if self.selected_candidate_id is not None:
                raise ValueError("ERROR records have no selected_candidate_id")
            if self.rejection_reason is not None:
                raise ValueError("ERROR records have no rejection_reason")
            if self.error_summary is not None:
                object.__setattr__(self, "error_summary", _require_nonempty("error_summary", self.error_summary))
            object.__setattr__(self, "error_type", _require_nonempty("error_type", self.error_type))
            return
        if self.error_type is not None or self.error_summary is not None:
            raise ValueError("OK record_status forbids error fields")
        if self.decision is DecisionOutput.ERROR:
            raise ValueError("OK record_status forbids DecisionOutput.ERROR")
        if self.decision is DecisionOutput.UNIQUE:
            if self.selected_candidate_id not in candidate_ids:
                raise ValueError("selected_candidate_id must name a raw candidate")
            if self.rejection_reason is not None:
                raise ValueError("UNIQUE decision forbids rejection_reason")
            return
        if self.decision is DecisionOutput.NOT_FOUND:
            if self.selected_candidate_id is not None:
                raise ValueError("NOT_FOUND decision has no selected_candidate_id")
            if self.rejection_reason != "TARGET_NOT_FOUND":
                raise ValueError("NOT_FOUND decision requires TARGET_NOT_FOUND")
            return
        if self.decision is DecisionOutput.AMBIGUOUS:
            if self.selected_candidate_id is not None:
                raise ValueError("AMBIGUOUS decision has no selected_candidate_id")
            if self.rejection_reason != "TARGET_AMBIGUOUS":
                raise ValueError("AMBIGUOUS decision requires TARGET_AMBIGUOUS")
            return
        raise ValueError("OK record_status requires a known non-error decision")
