"""Platform metrics, calibration results, the objective and the threshold lock record."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
from types import MappingProxyType

from so101_demo.perception_benchmark.calibration.contracts import (
    _GRID_VERSIONS,
    _SHA256,
    _SOURCE_COMMIT,
    LOCK_SCHEMA_VERSION,
    OBJECTIVE_VERSION,
    TIE_BREAK_VERSION,
    CalibrationError,
    CalibrationOutcome,
    ModelName,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    GroundedSamBenchmarkThresholds,
    YoloThresholds,
    _optional_probability,
    _required_probability,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    TruthSample,
    model_id_for_name,
)


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
            raise ValueError("unsafe_unique_count must not exceed unsafe_unique_denominator")
        object.__setattr__(self, "macro_f1", _required_probability("macro_f1", self.macro_f1))
        for name in (
            "mask_ap50_95",
            "unsafe_unique_rate",
            "two_cup_both_matched_recall",
        ):
            object.__setattr__(self, name, _optional_probability(name, getattr(self, name)))
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
        if not isinstance(self.selected, (YoloThresholds, GroundedSamBenchmarkThresholds)):
            raise ValueError("selected must be a supported threshold config")
        metrics = dict(self.platform_metrics)
        if set(metrics) != {"macos", "linux"} or not all(
            isinstance(value, PlatformCalibrationMetrics) for value in metrics.values()
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
            _optional_probability("merged_mask_ap50_95", self.merged_mask_ap50_95),
        )

    def __reduce__(self):
        return (
            type(self),
            (
                self.selected,
                dict(self.platform_metrics),
                self.merged_macro_f1,
                self.merged_mask_ap50_95,
            ),
        )

    @property
    def deployable(self) -> bool:
        return all(_platform_is_safe(metrics) for metrics in self.platform_metrics.values())

    @property
    def outcome(self) -> CalibrationOutcome:
        return "SAFE_CALIBRATED" if self.deployable else "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"


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
            object.__setattr__(self, name, _required_probability(name, getattr(self, name)))
        for name in ("merged_mask_ap50_95", "min_platform_two_cup_recall"):
            object.__setattr__(self, name, _optional_probability(name, getattr(self, name)))

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
    minimum_two = None if mac_two is None or linux_two is None else min(mac_two, linux_two)
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
    formal: bool
    platform_sample_counts: Mapping[str, int]
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
            if (
                not isinstance(getattr(self, name), str)
                or _SHA256.fullmatch(getattr(self, name)) is None
            ):
                raise ValueError(f"{name} is invalid")
        if (
            not isinstance(self.source_commit, str)
            or _SOURCE_COMMIT.fullmatch(self.source_commit) is None
        ):
            raise ValueError("source_commit is invalid")
        if type(self.formal) is not bool:
            raise ValueError("formal must be a bool")
        sample_counts = dict(self.platform_sample_counts)
        if set(sample_counts) != {"macos", "linux"} or any(
            type(value) is not int or value <= 0 for value in sample_counts.values()
        ):
            raise ValueError("platform_sample_counts are invalid")
        object.__setattr__(self, "platform_sample_counts", MappingProxyType(sample_counts))
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
            isinstance(value, PlatformCalibrationMetrics) for value in metrics.values()
        ):
            raise ValueError("platform_metrics is invalid")
        object.__setattr__(self, "platform_metrics", MappingProxyType(metrics))
        if any(
            sample_counts[platform] != metrics[platform].sample_count
            for platform in ("macos", "linux")
        ):
            raise ValueError("platform_sample_counts do not match platform_metrics")
        if self.formal and sample_counts != {"macos": 200, "linux": 200}:
            raise ValueError("formal locks require exactly 200 samples per platform")
        mac = metrics["macos"]
        linux = metrics["linux"]
        minimum_two = (
            None
            if mac.two_cup_both_matched_recall is None or linux.two_cup_both_matched_recall is None
            else min(
                mac.two_cup_both_matched_recall,
                linux.two_cup_both_matched_recall,
            )
        )
        if (
            self.objective_metrics.min_platform_macro_f1 != min(mac.macro_f1, linux.macro_f1)
            or self.objective_metrics.min_platform_two_cup_recall != minimum_two
        ):
            raise ValueError("objective_metrics do not match platform_metrics")
        safe = all(_platform_is_safe(value) for value in metrics.values())
        if self.outcome == "SAFE_CALIBRATED" and self.deployable is True and safe:
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


def _platform_document(values: Mapping[str, PlatformCalibrationMetrics]) -> dict[str, object]:
    return {platform: values[platform].to_document() for platform in ("macos", "linux")}


def _threshold_lock_document(lock: ThresholdLock, *, include_sha: bool) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": lock.schema_version,
        "model": lock.model,
        "grid_version": lock.grid_version,
        "objective_version": lock.objective_version,
        "tie_break_version": lock.tie_break_version,
        "val_inventory_sha256": lock.val_inventory_sha256,
        "mac_prediction_inventory_sha256": lock.mac_prediction_inventory_sha256,
        "linux_prediction_inventory_sha256": lock.linux_prediction_inventory_sha256,
        "formal": lock.formal,
        "platform_sample_counts": {
            platform: lock.platform_sample_counts[platform] for platform in ("macos", "linux")
        },
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
    return record.model_id == model_id_for_name(model)


def _validate_record(record: object) -> PredictionRecord:
    if not isinstance(record, PredictionRecord):
        raise CalibrationError("CALIBRATION_RECORD_CONTRACT_INVALID")
    try:
        candidates = tuple(
            replace(candidate, mask=replace(candidate.mask)) for candidate in record.raw_candidates
        )
        return replace(
            record,
            runtime_provenance=replace(record.runtime_provenance),
            phase_timings=replace(record.phase_timings),
            raw_candidates=candidates,
        )
    except (TypeError, ValueError) as error:
        raise CalibrationError("CALIBRATION_RECORD_CONTRACT_INVALID") from error


def _validate_truth(truth: object) -> TruthSample:
    if not isinstance(truth, TruthSample):
        raise CalibrationError("CALIBRATION_TRUTH_CONTRACT_INVALID")
    try:
        instances = tuple(
            replace(instance, mask=replace(instance.mask)) for instance in truth.instances
        )
        return replace(truth, instances=instances)
    except (TypeError, ValueError) as error:
        raise CalibrationError("CALIBRATION_TRUTH_CONTRACT_INVALID") from error


def _identity(item: PredictionRecord | TruthSample) -> tuple[int, str]:
    return item.formal_sample_index, item.image_sha256
