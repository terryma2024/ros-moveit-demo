"""Val-only joint-platform threshold calibration and immutable lock files."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Literal

from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    read_mask,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.dataset import TestSeal
from so101_demo.perception_benchmark.decisions import (
    DecisionMetrics,
    aggregate_decisions,
    aggregate_scenarios,
)
from so101_demo.perception_benchmark.matching import maximize_mask_iou_assignment
from so101_demo.perception_benchmark.metrics import ImageMetricInput, compute_ap


ModelName = Literal["yolo_seg", "grounded_sam"]
CalibrationOutcome = Literal[
    "SAFE_CALIBRATED", "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"
]
ThresholdConfig = "YoloThresholds | GroundedSamBenchmarkThresholds"

LOCK_SCHEMA_VERSION = "so101-threshold-lock/v1"
OBJECTIVE_VERSION = "joint-platform-val/v1"
TIE_BREAK_VERSION = "joint-platform-seven-level/v1"
_GRID_VERSIONS: dict[str, str] = {
    "yolo_seg": "yolo-seg-grid/v1",
    "grounded_sam": "grounded-sam-grid/v1",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_TWO_DECIMAL = Decimal("0.01")
_AP_THRESHOLDS = tuple(value / 100 for value in range(50, 96, 5))


class CalibrationError(ValueError):
    """Stable fail-closed calibration or threshold-lock error."""


def _decimal_probability(name: str, value: object) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal with two decimal places")
    normalized = value.quantize(_TWO_DECIMAL)
    if normalized != value:
        raise ValueError(f"{name} must have at most two decimal places")
    if not Decimal("0.00") <= normalized <= Decimal("1.00"):
        raise ValueError(f"{name} must be in [0.00, 1.00]")
    return normalized


def _decimal_document(value: Decimal) -> str:
    return format(value, ".2f")


def _normalized_json(document: Mapping[str, object]) -> str:
    return canonical_json_bytes(dict(document)).decode("utf-8").removesuffix("\n")


def _box_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return float(intersection / (first_area + second_area - intersection))


def _deduplicate_boxes(
    candidates: Sequence[RawCandidate], threshold: Decimal
) -> tuple[RawCandidate, ...]:
    ordered = tuple(
        sorted(candidates, key=lambda item: (-item.ranking_score, item.candidate_id))
    )
    kept: list[RawCandidate] = []
    limit = float(threshold)
    for candidate in ordered:
        if all(
            _box_iou(candidate.bbox_xyxy, previous.bbox_xyxy) < limit
            for previous in kept
        ):
            kept.append(candidate)
    return tuple(kept)


@dataclass(frozen=True, slots=True)
class YoloThresholds:
    conf: Decimal
    nms_iou: Decimal
    target_confidence_threshold: Decimal
    imgsz: int = 640

    def __post_init__(self) -> None:
        for name in ("conf", "nms_iou", "target_confidence_threshold"):
            object.__setattr__(
                self, name, _decimal_probability(name, getattr(self, name))
            )
        if isinstance(self.imgsz, bool) or self.imgsz != 640:
            raise ValueError("imgsz must be the fixed integer 640")

    def to_document(self) -> dict[str, object]:
        return {
            "conf": _decimal_document(self.conf),
            "nms_iou": _decimal_document(self.nms_iou),
            "target_confidence_threshold": _decimal_document(
                self.target_confidence_threshold
            ),
            "imgsz": self.imgsz,
        }

    @property
    def normalized_json(self) -> str:
        return _normalized_json(self.to_document())

    @property
    def safety_preference_key(self) -> tuple[Decimal, ...]:
        return (-self.conf, -self.target_confidence_threshold, self.nms_iou)

    def filter_candidates(
        self, candidates: tuple[RawCandidate, ...]
    ) -> tuple[RawCandidate, ...]:
        class_filtered = tuple(
            candidate
            for candidate in candidates
            if candidate.class_confidence is not None
            and candidate.class_confidence >= float(self.conf)
        )
        deduplicated = _deduplicate_boxes(class_filtered, self.nms_iou)
        return tuple(
            candidate
            for candidate in deduplicated
            if candidate.ranking_score >= float(self.target_confidence_threshold)
        )


@dataclass(frozen=True, slots=True)
class GroundedSamBenchmarkThresholds:
    box_threshold: Decimal
    text_threshold: Decimal
    sam_quality: Decimal
    target_confidence_threshold: Decimal
    duplicate_iou: Decimal = Decimal("0.85")
    min_mask_pixels: int = 64
    max_mask_area_ratio: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        for name in (
            "box_threshold",
            "text_threshold",
            "sam_quality",
            "target_confidence_threshold",
            "duplicate_iou",
            "max_mask_area_ratio",
        ):
            object.__setattr__(
                self, name, _decimal_probability(name, getattr(self, name))
            )
        if self.duplicate_iou != Decimal("0.85"):
            raise ValueError("duplicate_iou must be fixed at 0.85")
        if isinstance(self.min_mask_pixels, bool) or self.min_mask_pixels != 64:
            raise ValueError("min_mask_pixels must be fixed at 64")
        if self.max_mask_area_ratio != Decimal("0.50"):
            raise ValueError("max_mask_area_ratio must be fixed at 0.50")

    def to_document(self) -> dict[str, object]:
        return {
            "box_threshold": _decimal_document(self.box_threshold),
            "text_threshold": _decimal_document(self.text_threshold),
            "sam_quality": _decimal_document(self.sam_quality),
            "target_confidence_threshold": _decimal_document(
                self.target_confidence_threshold
            ),
            "duplicate_iou": _decimal_document(self.duplicate_iou),
            "min_mask_pixels": self.min_mask_pixels,
            "max_mask_area_ratio": _decimal_document(self.max_mask_area_ratio),
        }

    @property
    def normalized_json(self) -> str:
        return _normalized_json(self.to_document())

    @property
    def safety_preference_key(self) -> tuple[Decimal, ...]:
        return (
            -self.box_threshold,
            -self.text_threshold,
            -self.sam_quality,
            -self.target_confidence_threshold,
        )

    def filter_candidates(
        self, candidates: tuple[RawCandidate, ...]
    ) -> tuple[RawCandidate, ...]:
        grounding_filtered = tuple(
            candidate
            for candidate in candidates
            if candidate.grounding_box_score is not None
            and candidate.grounding_text_score is not None
            and candidate.grounding_box_score >= float(self.box_threshold)
            and candidate.grounding_text_score >= float(self.text_threshold)
        )
        deduplicated = _deduplicate_boxes(grounding_filtered, self.duplicate_iou)
        return tuple(
            candidate
            for candidate in deduplicated
            if candidate.sam_quality is not None
            and candidate.sam_quality >= float(self.sam_quality)
            and candidate.mask.pixel_count >= self.min_mask_pixels
            and (
                candidate.mask.pixel_count
                / (candidate.mask.image_width * candidate.mask.image_height)
            )
            <= float(self.max_mask_area_ratio)
            and candidate.ranking_score
            >= float(self.target_confidence_threshold)
        )


def decimal_range(start: str, stop: str, step: str) -> tuple[Decimal, ...]:
    current = Decimal(start)
    end = Decimal(stop)
    increment = Decimal(step)
    if increment <= 0:
        raise ValueError("step must be positive")
    values: list[Decimal] = []
    while current <= end:
        values.append(current.quantize(_TWO_DECIMAL))
        current += increment
    return tuple(values)


def enumerate_yolo_grid() -> Iterator[YoloThresholds]:
    for conf, nms_iou, selector in product(
        decimal_range("0.05", "0.95", "0.05"),
        decimal_range("0.30", "0.90", "0.10"),
        decimal_range("0.05", "0.95", "0.05"),
    ):
        yield YoloThresholds(conf, nms_iou, selector, 640)


def enumerate_grounded_sam_grid() -> Iterator[GroundedSamBenchmarkThresholds]:
    for box, text, sam, selector in product(
        decimal_range("0.10", "0.95", "0.05"),
        decimal_range("0.05", "0.50", "0.05"),
        decimal_range("0.50", "0.95", "0.05"),
        decimal_range("0.10", "0.95", "0.05"),
    ):
        yield GroundedSamBenchmarkThresholds(
            box,
            text,
            sam,
            selector,
            Decimal("0.85"),
            64,
            Decimal("0.50"),
        )


def _optional_probability(name: str, value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be null or a finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be null or a finite probability")
    return result


def _required_probability(name: str, value: object) -> float:
    result = _optional_probability(name, value)
    if result is None:
        raise ValueError(f"{name} must be a finite probability")
    return result


@dataclass(frozen=True, slots=True)
class PlatformCalibrationMetrics:
    sample_count: int
    error_count: int
    macro_f1: float
    mask_ap50_95: float | None
    unsafe_unique_count: int
    unsafe_unique_denominator: int
    unsafe_unique_rate: float | None
    two_cup_both_matched_recall: float | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count <= 0
        ):
            raise ValueError("sample_count must be a positive integer")
        for name in (
            "error_count",
            "unsafe_unique_count",
            "unsafe_unique_denominator",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.error_count > self.sample_count:
            raise ValueError("error_count must not exceed sample_count")
        if self.unsafe_unique_count > self.unsafe_unique_denominator:
            raise ValueError(
                "unsafe_unique_count must not exceed unsafe_unique_denominator"
            )
        object.__setattr__(
            self, "macro_f1", _required_probability("macro_f1", self.macro_f1)
        )
        for name in (
            "mask_ap50_95",
            "unsafe_unique_rate",
            "two_cup_both_matched_recall",
        ):
            object.__setattr__(
                self, name, _optional_probability(name, getattr(self, name))
            )
        expected_rate = (
            None
            if self.unsafe_unique_denominator == 0
            else self.unsafe_unique_count / self.unsafe_unique_denominator
        )
        if self.unsafe_unique_rate != expected_rate:
            raise ValueError("unsafe_unique_rate does not match its counts")

    def to_document(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "error_count": self.error_count,
            "macro_f1": self.macro_f1,
            "mask_ap50_95": self.mask_ap50_95,
            "unsafe_unique_count": self.unsafe_unique_count,
            "unsafe_unique_denominator": self.unsafe_unique_denominator,
            "unsafe_unique_rate": self.unsafe_unique_rate,
            "two_cup_both_matched_recall": self.two_cup_both_matched_recall,
        }


def _platform_is_safe(metrics: PlatformCalibrationMetrics) -> bool:
    return (
        metrics.error_count == 0
        and metrics.unsafe_unique_denominator > 0
        and metrics.unsafe_unique_count == 0
        and metrics.unsafe_unique_rate == 0.0
    )


def _score(value: float | None) -> float:
    return -1.0 if value is None else value


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    selected: YoloThresholds | GroundedSamBenchmarkThresholds
    platform_metrics: Mapping[str, PlatformCalibrationMetrics]
    merged_macro_f1: float
    merged_mask_ap50_95: float | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.selected, (YoloThresholds, GroundedSamBenchmarkThresholds)
        ):
            raise ValueError("selected must be a supported threshold config")
        metrics = dict(self.platform_metrics)
        if set(metrics) != {"macos", "linux"} or not all(
            isinstance(value, PlatformCalibrationMetrics)
            for value in metrics.values()
        ):
            raise ValueError("platform_metrics must contain macos and linux")
        object.__setattr__(self, "platform_metrics", MappingProxyType(metrics))
        object.__setattr__(
            self,
            "merged_macro_f1",
            _required_probability("merged_macro_f1", self.merged_macro_f1),
        )
        object.__setattr__(
            self,
            "merged_mask_ap50_95",
            _optional_probability(
                "merged_mask_ap50_95", self.merged_mask_ap50_95
            ),
        )

    @property
    def deployable(self) -> bool:
        return all(
            _platform_is_safe(metrics)
            for metrics in self.platform_metrics.values()
        )

    @property
    def outcome(self) -> CalibrationOutcome:
        return (
            "SAFE_CALIBRATED"
            if self.deployable
            else "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"
        )


def calibration_key(point: CalibrationResult) -> tuple[object, ...]:
    if not isinstance(point, CalibrationResult):
        raise ValueError("point must be a CalibrationResult")
    mac = point.platform_metrics["macos"]
    linux = point.platform_metrics["linux"]
    return (
        not point.deployable,
        -min(mac.macro_f1, linux.macro_f1),
        -point.merged_macro_f1,
        -_score(point.merged_mask_ap50_95),
        -min(
            _score(mac.two_cup_both_matched_recall),
            _score(linux.two_cup_both_matched_recall),
        ),
        point.selected.safety_preference_key,
        point.selected.normalized_json,
    )


def select_calibration_result(
    points: Sequence[CalibrationResult],
) -> CalibrationResult:
    values = tuple(points)
    if not values or not all(isinstance(value, CalibrationResult) for value in values):
        raise ValueError("points must contain CalibrationResult values")
    return min(values, key=calibration_key)


@dataclass(frozen=True, slots=True)
class ObjectiveCalibrationMetrics:
    min_platform_macro_f1: float
    merged_macro_f1: float
    merged_mask_ap50_95: float | None
    min_platform_two_cup_recall: float | None

    def __post_init__(self) -> None:
        for name in ("min_platform_macro_f1", "merged_macro_f1"):
            object.__setattr__(
                self, name, _required_probability(name, getattr(self, name))
            )
        for name in ("merged_mask_ap50_95", "min_platform_two_cup_recall"):
            object.__setattr__(
                self, name, _optional_probability(name, getattr(self, name))
            )

    def to_document(self) -> dict[str, object]:
        return {
            "min_platform_macro_f1": self.min_platform_macro_f1,
            "merged_macro_f1": self.merged_macro_f1,
            "merged_mask_ap50_95": self.merged_mask_ap50_95,
            "min_platform_two_cup_recall": self.min_platform_two_cup_recall,
        }


def _objective_metrics(result: CalibrationResult) -> ObjectiveCalibrationMetrics:
    mac = result.platform_metrics["macos"]
    linux = result.platform_metrics["linux"]
    mac_two = mac.two_cup_both_matched_recall
    linux_two = linux.two_cup_both_matched_recall
    minimum_two = (
        None
        if mac_two is None or linux_two is None
        else min(mac_two, linux_two)
    )
    return ObjectiveCalibrationMetrics(
        min(mac.macro_f1, linux.macro_f1),
        result.merged_macro_f1,
        result.merged_mask_ap50_95,
        minimum_two,
    )


@dataclass(frozen=True, slots=True)
class ThresholdLock:
    schema_version: str
    model: ModelName
    grid_version: str
    objective_version: str
    tie_break_version: str
    val_inventory_sha256: str
    mac_prediction_inventory_sha256: str
    linux_prediction_inventory_sha256: str
    selected: YoloThresholds | GroundedSamBenchmarkThresholds
    outcome: CalibrationOutcome
    deployable: bool
    source_commit: str
    objective_metrics: ObjectiveCalibrationMetrics
    platform_metrics: Mapping[str, PlatformCalibrationMetrics]
    lock_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != LOCK_SCHEMA_VERSION:
            raise ValueError("schema_version is invalid")
        if self.model not in _GRID_VERSIONS:
            raise ValueError("model is invalid")
        if self.grid_version != _GRID_VERSIONS[self.model]:
            raise ValueError("grid_version is invalid")
        if self.objective_version != OBJECTIVE_VERSION:
            raise ValueError("objective_version is invalid")
        if self.tie_break_version != TIE_BREAK_VERSION:
            raise ValueError("tie_break_version is invalid")
        for name in (
            "val_inventory_sha256",
            "mac_prediction_inventory_sha256",
            "linux_prediction_inventory_sha256",
            "lock_sha256",
        ):
            if not isinstance(getattr(self, name), str) or _SHA256.fullmatch(
                getattr(self, name)
            ) is None:
                raise ValueError(f"{name} is invalid")
        if not isinstance(self.source_commit, str) or _SOURCE_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise ValueError("source_commit is invalid")
        if self.model == "yolo_seg" and not isinstance(self.selected, YoloThresholds):
            raise ValueError("selected config does not match model")
        if self.model == "grounded_sam" and not isinstance(
            self.selected, GroundedSamBenchmarkThresholds
        ):
            raise ValueError("selected config does not match model")
        if not isinstance(self.objective_metrics, ObjectiveCalibrationMetrics):
            raise ValueError("objective_metrics is invalid")
        metrics = dict(self.platform_metrics)
        if set(metrics) != {"macos", "linux"} or not all(
            isinstance(value, PlatformCalibrationMetrics)
            for value in metrics.values()
        ):
            raise ValueError("platform_metrics is invalid")
        object.__setattr__(self, "platform_metrics", MappingProxyType(metrics))
        mac = metrics["macos"]
        linux = metrics["linux"]
        minimum_two = (
            None
            if mac.two_cup_both_matched_recall is None
            or linux.two_cup_both_matched_recall is None
            else min(
                mac.two_cup_both_matched_recall,
                linux.two_cup_both_matched_recall,
            )
        )
        if (
            self.objective_metrics.min_platform_macro_f1
            != min(mac.macro_f1, linux.macro_f1)
            or self.objective_metrics.min_platform_two_cup_recall != minimum_two
        ):
            raise ValueError("objective_metrics do not match platform_metrics")
        safe = all(_platform_is_safe(value) for value in metrics.values())
        if (
            self.outcome == "SAFE_CALIBRATED"
            and self.deployable is True
            and safe
        ):
            return
        if (
            self.outcome == "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"
            and self.deployable is False
            and not safe
        ):
            return
        raise ValueError("outcome and deployable do not match frozen safety metrics")

    def with_recomputed_sha256(self) -> "ThresholdLock":
        digest = hashlib.sha256(
            canonical_json_bytes(_threshold_lock_document(self, include_sha=False))
        ).hexdigest()
        return replace(self, lock_sha256=digest)


def _platform_document(
    values: Mapping[str, PlatformCalibrationMetrics]
) -> dict[str, object]:
    return {
        platform: values[platform].to_document()
        for platform in ("macos", "linux")
    }


def _threshold_lock_document(
    lock: ThresholdLock, *, include_sha: bool
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": lock.schema_version,
        "model": lock.model,
        "grid_version": lock.grid_version,
        "objective_version": lock.objective_version,
        "tie_break_version": lock.tie_break_version,
        "val_inventory_sha256": lock.val_inventory_sha256,
        "mac_prediction_inventory_sha256": lock.mac_prediction_inventory_sha256,
        "linux_prediction_inventory_sha256": lock.linux_prediction_inventory_sha256,
        "selected": lock.selected.to_document(),
        "outcome": lock.outcome,
        "deployable": lock.deployable,
        "source_commit": lock.source_commit,
        "objective_metrics": lock.objective_metrics.to_document(),
        "platform_metrics": _platform_document(lock.platform_metrics),
    }
    if include_sha:
        document["lock_sha256"] = lock.lock_sha256
    return document


def _validated_sha(value: object, code: str = "THRESHOLD_LOCK_FIELD_INVALID") -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CalibrationError(code)
    return value


def _validated_source_commit(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_COMMIT.fullmatch(value) is None:
        raise CalibrationError("THRESHOLD_LOCK_FIELD_INVALID")
    return value


def _candidate_model_matches(record: PredictionRecord, model: ModelName) -> bool:
    normalized = record.model_id.lower().replace("_", "-")
    return (
        "yolo" in normalized
        if model == "yolo_seg"
        else "grounded-sam" in normalized
    )


def _validate_record(record: object) -> PredictionRecord:
    if not isinstance(record, PredictionRecord):
        raise CalibrationError("TASK1_RECORD_CONTRACT_INVALID")
    try:
        candidates = tuple(
            replace(candidate, mask=replace(candidate.mask))
            for candidate in record.raw_candidates
        )
        return replace(
            record,
            runtime_provenance=replace(record.runtime_provenance),
            phase_timings=replace(record.phase_timings),
            raw_candidates=candidates,
        )
    except (TypeError, ValueError) as error:
        raise CalibrationError("TASK1_RECORD_CONTRACT_INVALID") from error


def _validate_truth(truth: object) -> TruthSample:
    if not isinstance(truth, TruthSample):
        raise CalibrationError("TASK1_TRUTH_CONTRACT_INVALID")
    try:
        instances = tuple(
            replace(instance, mask=replace(instance.mask))
            for instance in truth.instances
        )
        return replace(truth, instances=instances)
    except (TypeError, ValueError) as error:
        raise CalibrationError("TASK1_TRUTH_CONTRACT_INVALID") from error


def _identity(item: PredictionRecord | TruthSample) -> tuple[int, str]:
    return item.formal_sample_index, item.image_sha256


def _validate_inputs(
    model: object,
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    inventory_sha: object,
    evidence_root: Path,
    mac_prediction_inventory_sha256: object,
    linux_prediction_inventory_sha256: object,
    source_commit: object,
    fixture_mode: object,
) -> tuple[
    ModelName,
    tuple[PredictionRecord, ...],
    tuple[PredictionRecord, ...],
    tuple[TruthSample, ...],
    Path,
    str,
    str,
    str,
    str,
]:
    if model not in ("yolo_seg", "grounded_sam"):
        raise CalibrationError("CALIBRATION_MODEL_INVALID")
    normalized_model: ModelName = model
    val_inventory_sha = _validated_sha(inventory_sha)
    mac_inventory_sha = _validated_sha(mac_prediction_inventory_sha256)
    linux_inventory_sha = _validated_sha(linux_prediction_inventory_sha256)
    commit = _validated_source_commit(source_commit)
    if not isinstance(fixture_mode, bool):
        raise CalibrationError("CALIBRATION_FIXTURE_MODE_INVALID")
    try:
        root = Path(evidence_root).resolve(strict=True)
    except (OSError, TypeError, RuntimeError) as error:
        raise CalibrationError("CALIBRATION_EVIDENCE_ROOT_INVALID") from error
    if not root.is_dir():
        raise CalibrationError("CALIBRATION_EVIDENCE_ROOT_INVALID")

    mac = tuple(_validate_record(record) for record in mac_records)
    linux = tuple(_validate_record(record) for record in linux_records)
    truth_items = tuple(_validate_truth(truth) for truth in truths)
    if not mac or not linux or not truth_items:
        raise CalibrationError("CALIBRATION_INVENTORY_EMPTY")
    if any(
        item.split != "val"
        for item in (*mac, *linux, *truth_items)
    ):
        raise CalibrationError("CALIBRATION_VAL_ONLY")
    if any(
        record.run_kind is not RunKind.VAL_RAW
        or record.threshold_lock_sha256 is not None
        for record in (*mac, *linux)
    ):
        raise CalibrationError("CALIBRATION_VAL_ONLY")
    if any(record.record_status is RecordStatus.ERROR for record in (*mac, *linux)):
        raise CalibrationError("CALIBRATION_ERROR_RECORD_FORBIDDEN")
    if any(
        not _candidate_model_matches(record, normalized_model)
        for record in (*mac, *linux)
    ):
        raise CalibrationError("CALIBRATION_MODEL_MISMATCH")

    mac_identities = tuple(_identity(record) for record in mac)
    linux_identities = tuple(_identity(record) for record in linux)
    truth_identities = tuple(_identity(truth) for truth in truth_items)
    for identities in (mac_identities, linux_identities, truth_identities):
        if len(identities) != len(set(identities)):
            raise CalibrationError("CALIBRATION_INVENTORY_IDENTITY_DUPLICATE")
        if len({identity[1] for identity in identities}) != len(identities):
            raise CalibrationError("CALIBRATION_INVENTORY_IDENTITY_DUPLICATE")
    if set(mac_identities) != set(linux_identities):
        raise CalibrationError("PLATFORM_INVENTORY_IDENTITY_MISMATCH")
    if set(mac_identities) != set(truth_identities):
        raise CalibrationError("CALIBRATION_TRUTH_IDENTITY_MISMATCH")
    if not fixture_mode and (
        len(mac_identities) != 200
        or len(linux_identities) != 200
        or len(truth_identities) != 200
    ):
        raise CalibrationError("FORMAL_VAL_INVENTORY_INVALID")

    mac_by_identity = {_identity(record): record for record in mac}
    linux_by_identity = {_identity(record): record for record in linux}
    truths_by_identity = {_identity(truth): truth for truth in truth_items}
    ordered_identities = tuple(sorted(truths_by_identity))
    ordered_mac = tuple(mac_by_identity[identity] for identity in ordered_identities)
    ordered_linux = tuple(
        linux_by_identity[identity] for identity in ordered_identities
    )
    ordered_truths = tuple(
        truths_by_identity[identity] for identity in ordered_identities
    )
    for platform_records in (ordered_mac, ordered_linux):
        for record, truth in zip(platform_records, ordered_truths, strict=True):
            if (
                record.formal_sample_index != truth.formal_sample_index
                or record.split != truth.split
                or record.scenario != truth.scenario
                or record.image_relpath != truth.image_relpath
                or record.image_sha256 != truth.image_sha256
                or record.image_width != truth.image_width
                or record.image_height != truth.image_height
            ):
                raise CalibrationError("CALIBRATION_RECORD_TRUTH_MISMATCH")

    verified_refs: set[tuple[object, ...]] = set()
    try:
        for truth in ordered_truths:
            for instance in truth.instances:
                key = (
                    instance.mask.relative_path,
                    instance.mask.sha256,
                    instance.mask.pixel_count,
                    instance.mask.image_width,
                    instance.mask.image_height,
                )
                if key not in verified_refs:
                    read_mask(instance.mask, root)
                    verified_refs.add(key)
        for record in (*ordered_mac, *ordered_linux):
            for candidate in record.raw_candidates:
                key = (
                    candidate.mask.relative_path,
                    candidate.mask.sha256,
                    candidate.mask.pixel_count,
                    candidate.mask.image_width,
                    candidate.mask.image_height,
                )
                if key not in verified_refs:
                    read_mask(candidate.mask, root)
                    verified_refs.add(key)
    except (OSError, ValueError) as error:
        raise CalibrationError("MASK_EVIDENCE_INVALID") from error

    return (
        normalized_model,
        ordered_mac,
        ordered_linux,
        ordered_truths,
        root,
        val_inventory_sha,
        mac_inventory_sha,
        linux_inventory_sha,
        commit,
    )


def _record_with_candidates(
    record: PredictionRecord,
    candidates: tuple[RawCandidate, ...],
) -> PredictionRecord:
    if not candidates:
        decision = DecisionOutput.NOT_FOUND
        selected = None
        rejection = "TARGET_NOT_FOUND"
    elif len(candidates) == 1:
        decision = DecisionOutput.UNIQUE
        selected = candidates[0].candidate_id
        rejection = None
    else:
        decision = DecisionOutput.AMBIGUOUS
        selected = None
        rejection = "TARGET_AMBIGUOUS"
    return replace(
        record,
        raw_candidates=candidates,
        raw_count=len(candidates),
        decision=decision,
        selected_candidate_id=selected,
        rejection_reason=rejection,
        error_type=None,
        error_summary=None,
        timed_out=False,
        oom=False,
    )


def _selection_signature(
    records: Sequence[PredictionRecord],
    candidate_sets: Sequence[tuple[RawCandidate, ...]],
) -> tuple[tuple[int, str, tuple[str, ...]], ...]:
    return tuple(
        (
            record.formal_sample_index,
            record.image_sha256,
            tuple(candidate.candidate_id for candidate in candidates),
        )
        for record, candidates in zip(records, candidate_sets, strict=True)
    )


@dataclass(frozen=True, slots=True)
class _PlatformEvaluation:
    records: tuple[PredictionRecord, ...]
    decision_metrics: DecisionMetrics
    frozen_metrics: PlatformCalibrationMetrics


def _evaluate_platform(
    filtered_records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    evidence_root: Path,
) -> _PlatformEvaluation:
    decisions = aggregate_decisions(filtered_records, truths)
    ap = compute_ap(filtered_records, truths, evidence_root, _AP_THRESHOLDS)
    matches: dict[tuple[int, str], ImageMetricInput] = {}
    for record, truth in zip(filtered_records, truths, strict=True):
        assigned = (
            maximize_mask_iou_assignment(
                truth.instances, record.raw_candidates, evidence_root
            )
            if truth.instances and record.raw_candidates
            else ()
        )
        identity = (record.formal_sample_index, record.image_sha256)
        matches[identity] = ImageMetricInput(
            formal_sample_index=record.formal_sample_index,
            truth_count=len(truth.instances),
            candidate_count=len(record.raw_candidates),
            matches=assigned,
        )
    scenarios = aggregate_scenarios(
        filtered_records, truths, matches, evidence_root
    )
    two_cup = scenarios.get("two_cups")
    if decisions.macro_f1 is None:
        raise CalibrationError("CALIBRATION_FULL_DENOMINATOR_REQUIRED")
    metrics = PlatformCalibrationMetrics(
        sample_count=decisions.sample_count,
        error_count=decisions.error_count,
        macro_f1=decisions.macro_f1,
        mask_ap50_95=ap.mask_map,
        unsafe_unique_count=decisions.unsafe_unique_count,
        unsafe_unique_denominator=decisions.unsafe_unique_denominator,
        unsafe_unique_rate=decisions.unsafe_unique_rate,
        two_cup_both_matched_recall=(
            None if two_cup is None else two_cup.two_cup_both_matched_recall
        ),
    )
    return _PlatformEvaluation(filtered_records, decisions, metrics)


def _combined_macro_f1(
    first: DecisionMetrics, second: DecisionMetrics
) -> float:
    truth_classes = ("0", "1", "2+")
    expected = {
        "0": DecisionOutput.NOT_FOUND.value,
        "1": DecisionOutput.UNIQUE.value,
        "2+": DecisionOutput.AMBIGUOUS.value,
    }
    scores: list[float] = []
    for truth_class in truth_classes:
        output = expected[truth_class]
        true_positive = (
            first.confusion[truth_class][output]
            + second.confusion[truth_class][output]
        )
        false_positive = sum(
            first.confusion[other][output] + second.confusion[other][output]
            for other in truth_classes
            if other != truth_class
        )
        false_negative = sum(
            first.confusion[truth_class][actual]
            + second.confusion[truth_class][actual]
            for actual in ("NOT_FOUND", "UNIQUE", "AMBIGUOUS", "ERROR")
            if actual != output
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(
            0.0 if denominator == 0 else (2.0 * true_positive) / denominator
        )
    return float(sum(scores) / len(scores))


def _remap_for_merged(
    records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    parity: int,
) -> tuple[tuple[PredictionRecord, ...], tuple[TruthSample, ...]]:
    remapped_records = tuple(
        replace(record, formal_sample_index=record.formal_sample_index * 2 + parity)
        for record in records
    )
    remapped_truths = tuple(
        replace(truth, formal_sample_index=truth.formal_sample_index * 2 + parity)
        for truth in truths
    )
    return remapped_records, remapped_truths


def _merged_ap(
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    evidence_root: Path,
) -> float | None:
    mac_remapped, mac_truths = _remap_for_merged(mac_records, truths, 0)
    linux_remapped, linux_truths = _remap_for_merged(linux_records, truths, 1)
    return compute_ap(
        mac_remapped + linux_remapped,
        mac_truths + linux_truths,
        evidence_root,
        _AP_THRESHOLDS,
    ).mask_map


def calibrate_joint_platform_val(
    model: str,
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    inventory_sha: str,
    *,
    evidence_root: Path,
    mac_prediction_inventory_sha256: str,
    linux_prediction_inventory_sha256: str,
    source_commit: str,
    fixture_mode: bool = False,
) -> ThresholdLock:
    """Calibrate one exact grid over aligned macOS and Linux val records."""

    (
        normalized_model,
        mac,
        linux,
        truth_items,
        root,
        val_inventory_sha,
        mac_inventory_sha,
        linux_inventory_sha,
        commit,
    ) = _validate_inputs(
        model,
        mac_records,
        linux_records,
        truths,
        inventory_sha,
        evidence_root,
        mac_prediction_inventory_sha256,
        linux_prediction_inventory_sha256,
        source_commit,
        fixture_mode,
    )
    grid: Iterator[YoloThresholds | GroundedSamBenchmarkThresholds]
    grid = (
        enumerate_yolo_grid()
        if normalized_model == "yolo_seg"
        else enumerate_grounded_sam_grid()
    )
    platform_cache: dict[
        tuple[str, tuple[tuple[int, str, tuple[str, ...]], ...]],
        _PlatformEvaluation,
    ] = {}
    merged_cache: dict[
        tuple[
            tuple[tuple[int, str, tuple[str, ...]], ...],
            tuple[tuple[int, str, tuple[str, ...]], ...],
        ],
        tuple[float, float | None],
    ] = {}
    points: list[CalibrationResult] = []
    for config in grid:
        mac_candidates = tuple(
            config.filter_candidates(record.raw_candidates) for record in mac
        )
        linux_candidates = tuple(
            config.filter_candidates(record.raw_candidates) for record in linux
        )
        mac_signature = _selection_signature(mac, mac_candidates)
        linux_signature = _selection_signature(linux, linux_candidates)
        mac_key = ("macos", mac_signature)
        linux_key = ("linux", linux_signature)
        if mac_key not in platform_cache:
            mac_filtered = tuple(
                _record_with_candidates(record, candidates)
                for record, candidates in zip(mac, mac_candidates, strict=True)
            )
            platform_cache[mac_key] = _evaluate_platform(
                mac_filtered, truth_items, root
            )
        if linux_key not in platform_cache:
            linux_filtered = tuple(
                _record_with_candidates(record, candidates)
                for record, candidates in zip(
                    linux, linux_candidates, strict=True
                )
            )
            platform_cache[linux_key] = _evaluate_platform(
                linux_filtered, truth_items, root
            )
        mac_evaluation = platform_cache[mac_key]
        linux_evaluation = platform_cache[linux_key]
        merged_key = (mac_signature, linux_signature)
        if merged_key not in merged_cache:
            merged_cache[merged_key] = (
                _combined_macro_f1(
                    mac_evaluation.decision_metrics,
                    linux_evaluation.decision_metrics,
                ),
                _merged_ap(
                    mac_evaluation.records,
                    linux_evaluation.records,
                    truth_items,
                    root,
                ),
            )
        merged_macro, merged_mask_ap = merged_cache[merged_key]
        points.append(
            CalibrationResult(
                selected=config,
                platform_metrics={
                    "macos": mac_evaluation.frozen_metrics,
                    "linux": linux_evaluation.frozen_metrics,
                },
                merged_macro_f1=merged_macro,
                merged_mask_ap50_95=merged_mask_ap,
            )
        )
    result = select_calibration_result(points)
    lock = ThresholdLock(
        schema_version=LOCK_SCHEMA_VERSION,
        model=normalized_model,
        grid_version=_GRID_VERSIONS[normalized_model],
        objective_version=OBJECTIVE_VERSION,
        tie_break_version=TIE_BREAK_VERSION,
        val_inventory_sha256=val_inventory_sha,
        mac_prediction_inventory_sha256=mac_inventory_sha,
        linux_prediction_inventory_sha256=linux_inventory_sha,
        selected=result.selected,
        outcome=result.outcome,
        deployable=result.deployable,
        source_commit=commit,
        objective_metrics=_objective_metrics(result),
        platform_metrics=result.platform_metrics,
        lock_sha256="0" * 64,
    )
    return lock.with_recomputed_sha256()


def write_threshold_lock(path: Path, lock: ThresholdLock) -> Path:
    if not isinstance(lock, ThresholdLock):
        raise CalibrationError("THRESHOLD_LOCK_INVALID")
    if lock.with_recomputed_sha256().lock_sha256 != lock.lock_sha256:
        raise CalibrationError("THRESHOLD_LOCK_HASH_MISMATCH")
    target = Path(path)
    atomic_write_json(target, _threshold_lock_document(lock, include_sha=True))
    return target


def _exact_keys(document: object, expected: set[str], code: str) -> Mapping[str, object]:
    if not isinstance(document, Mapping) or set(document) != expected:
        raise CalibrationError(code)
    return document


def _parse_decimal_field(document: Mapping[str, object], name: str) -> Decimal:
    value = document[name]
    if not isinstance(value, str) or re.fullmatch(r"[01]\.\d{2}", value) is None:
        raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID")
    try:
        return Decimal(value)
    except ValueError as error:
        raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID") from error


def _parse_selected(
    model: ModelName, document: object
) -> YoloThresholds | GroundedSamBenchmarkThresholds:
    try:
        if model == "yolo_seg":
            values = _exact_keys(
                document,
                {"conf", "nms_iou", "target_confidence_threshold", "imgsz"},
                "THRESHOLD_LOCK_SELECTED_MODEL_MISMATCH",
            )
            config: YoloThresholds | GroundedSamBenchmarkThresholds = YoloThresholds(
                _parse_decimal_field(values, "conf"),
                _parse_decimal_field(values, "nms_iou"),
                _parse_decimal_field(values, "target_confidence_threshold"),
                values["imgsz"],
            )
            if (
                config.conf not in decimal_range("0.05", "0.95", "0.05")
                or config.nms_iou not in decimal_range("0.30", "0.90", "0.10")
                or config.target_confidence_threshold
                not in decimal_range("0.05", "0.95", "0.05")
            ):
                raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID")
            return config
        values = _exact_keys(
            document,
            {
                "box_threshold",
                "text_threshold",
                "sam_quality",
                "target_confidence_threshold",
                "duplicate_iou",
                "min_mask_pixels",
                "max_mask_area_ratio",
            },
            "THRESHOLD_LOCK_SELECTED_MODEL_MISMATCH",
        )
        config = GroundedSamBenchmarkThresholds(
            _parse_decimal_field(values, "box_threshold"),
            _parse_decimal_field(values, "text_threshold"),
            _parse_decimal_field(values, "sam_quality"),
            _parse_decimal_field(values, "target_confidence_threshold"),
            _parse_decimal_field(values, "duplicate_iou"),
            values["min_mask_pixels"],
            _parse_decimal_field(values, "max_mask_area_ratio"),
        )
        if (
            config.box_threshold not in decimal_range("0.10", "0.95", "0.05")
            or config.text_threshold not in decimal_range("0.05", "0.50", "0.05")
            or config.sam_quality not in decimal_range("0.50", "0.95", "0.05")
            or config.target_confidence_threshold
            not in decimal_range("0.10", "0.95", "0.05")
        ):
            raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID")
        return config
    except CalibrationError:
        raise
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID") from error


def _parse_platform_metrics(document: object) -> Mapping[str, PlatformCalibrationMetrics]:
    platforms = _exact_keys(
        document, {"macos", "linux"}, "THRESHOLD_LOCK_METRICS_INVALID"
    )
    expected = {
        "sample_count",
        "error_count",
        "macro_f1",
        "mask_ap50_95",
        "unsafe_unique_count",
        "unsafe_unique_denominator",
        "unsafe_unique_rate",
        "two_cup_both_matched_recall",
    }
    result: dict[str, PlatformCalibrationMetrics] = {}
    try:
        for platform in ("macos", "linux"):
            values = _exact_keys(
                platforms[platform], expected, "THRESHOLD_LOCK_METRICS_INVALID"
            )
            result[platform] = PlatformCalibrationMetrics(**values)  # type: ignore[arg-type]
    except CalibrationError:
        raise
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_METRICS_INVALID") from error
    return MappingProxyType(result)


def _parse_objective_metrics(document: object) -> ObjectiveCalibrationMetrics:
    values = _exact_keys(
        document,
        {
            "min_platform_macro_f1",
            "merged_macro_f1",
            "merged_mask_ap50_95",
            "min_platform_two_cup_recall",
        },
        "THRESHOLD_LOCK_METRICS_INVALID",
    )
    try:
        return ObjectiveCalibrationMetrics(**values)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_METRICS_INVALID") from error


def verify_threshold_lock(path: Path) -> ThresholdLock:
    target = Path(path)
    if target.is_symlink():
        raise CalibrationError("THRESHOLD_LOCK_UNREADABLE")
    try:
        payload = target.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CalibrationError("THRESHOLD_LOCK_UNREADABLE") from error
    if not isinstance(document, Mapping):
        raise CalibrationError("THRESHOLD_LOCK_DOCUMENT_INVALID")
    if payload != canonical_json_bytes(document):
        raise CalibrationError("THRESHOLD_LOCK_NOT_CANONICAL")
    expected_keys = {
        "schema_version",
        "model",
        "grid_version",
        "objective_version",
        "tie_break_version",
        "val_inventory_sha256",
        "mac_prediction_inventory_sha256",
        "linux_prediction_inventory_sha256",
        "selected",
        "outcome",
        "deployable",
        "source_commit",
        "objective_metrics",
        "platform_metrics",
        "lock_sha256",
    }
    values = _exact_keys(
        document, expected_keys, "THRESHOLD_LOCK_DOCUMENT_INVALID"
    )
    stored_sha = _validated_sha(values["lock_sha256"])
    unhashed = dict(values)
    unhashed.pop("lock_sha256")
    computed_sha = hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest()
    if stored_sha != computed_sha:
        raise CalibrationError("THRESHOLD_LOCK_HASH_MISMATCH")
    if values["schema_version"] != LOCK_SCHEMA_VERSION:
        raise CalibrationError("THRESHOLD_LOCK_SCHEMA_INVALID")
    if values["model"] not in _GRID_VERSIONS:
        raise CalibrationError("THRESHOLD_LOCK_MODEL_INVALID")
    model: ModelName = values["model"]
    if (
        values["grid_version"] != _GRID_VERSIONS[model]
        or values["objective_version"] != OBJECTIVE_VERSION
        or values["tie_break_version"] != TIE_BREAK_VERSION
    ):
        raise CalibrationError("THRESHOLD_LOCK_VERSION_INVALID")
    val_inventory_sha = _validated_sha(values["val_inventory_sha256"])
    mac_inventory_sha = _validated_sha(values["mac_prediction_inventory_sha256"])
    linux_inventory_sha = _validated_sha(
        values["linux_prediction_inventory_sha256"]
    )
    commit = _validated_source_commit(values["source_commit"])
    selected = _parse_selected(model, values["selected"])
    platform_metrics = _parse_platform_metrics(values["platform_metrics"])
    objective_metrics = _parse_objective_metrics(values["objective_metrics"])
    expected_objective = _objective_metrics(
        CalibrationResult(
            selected=selected,
            platform_metrics=platform_metrics,
            merged_macro_f1=objective_metrics.merged_macro_f1,
            merged_mask_ap50_95=objective_metrics.merged_mask_ap50_95,
        )
    )
    if objective_metrics != expected_objective:
        raise CalibrationError("THRESHOLD_LOCK_METRICS_INVALID")
    if not isinstance(values["deployable"], bool) or values["outcome"] not in (
        "SAFE_CALIBRATED",
        "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT",
    ):
        raise CalibrationError("THRESHOLD_LOCK_OUTCOME_INVALID")
    try:
        lock = ThresholdLock(
            schema_version=LOCK_SCHEMA_VERSION,
            model=model,
            grid_version=values["grid_version"],
            objective_version=values["objective_version"],
            tie_break_version=values["tie_break_version"],
            val_inventory_sha256=val_inventory_sha,
            mac_prediction_inventory_sha256=mac_inventory_sha,
            linux_prediction_inventory_sha256=linux_inventory_sha,
            selected=selected,
            outcome=values["outcome"],
            deployable=values["deployable"],
            source_commit=commit,
            objective_metrics=objective_metrics,
            platform_metrics=platform_metrics,
            lock_sha256=stored_sha,
        )
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_OUTCOME_INVALID") from error
    if _threshold_lock_document(lock, include_sha=True) != dict(values):
        raise CalibrationError("THRESHOLD_LOCK_DOCUMENT_INVALID")
    return lock


def unlock_test_seal(
    seal: TestSeal,
    yolo_lock_path: Path,
    grounded_sam_lock_path: Path,
) -> TestSeal:
    """Verify both distinct model locks before TestSeal appends its access event."""

    if not isinstance(seal, TestSeal):
        raise CalibrationError("TEST_SEAL_INVALID")
    yolo_path = Path(yolo_lock_path)
    grounded_path = Path(grounded_sam_lock_path)
    yolo_lock = verify_threshold_lock(yolo_path)
    grounded_lock = verify_threshold_lock(grounded_path)
    if yolo_lock.model != "yolo_seg" or grounded_lock.model != "grounded_sam":
        raise CalibrationError("TEST_SEAL_LOCK_MODEL_MISMATCH")
    if yolo_lock.val_inventory_sha256 != grounded_lock.val_inventory_sha256:
        raise CalibrationError("TEST_SEAL_LOCK_INVENTORY_MISMATCH")
    if yolo_lock.source_commit != grounded_lock.source_commit:
        raise CalibrationError("TEST_SEAL_LOCK_SOURCE_MISMATCH")
    if yolo_lock.lock_sha256 == grounded_lock.lock_sha256:
        raise CalibrationError("TEST_SEAL_LOCKS_NOT_DISTINCT")
    verified = {
        yolo_path: yolo_lock.lock_sha256,
        grounded_path: grounded_lock.lock_sha256,
    }
    return seal.unlock(
        yolo_path,
        grounded_path,
        verify_lock=lambda path: verified[Path(path)],
    )


__all__ = (
    "CalibrationError",
    "CalibrationResult",
    "GroundedSamBenchmarkThresholds",
    "ObjectiveCalibrationMetrics",
    "PlatformCalibrationMetrics",
    "ThresholdLock",
    "YoloThresholds",
    "calibration_key",
    "calibrate_joint_platform_val",
    "decimal_range",
    "enumerate_grounded_sam_grid",
    "enumerate_yolo_grid",
    "select_calibration_result",
    "unlock_test_seal",
    "verify_threshold_lock",
    "write_threshold_lock",
)
