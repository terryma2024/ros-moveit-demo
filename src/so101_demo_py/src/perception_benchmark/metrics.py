"""Instance segmentation metrics and deterministic image bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from so101_demo.perception_benchmark.codec import read_mask
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.matching import (
    MaskMatch,
    _hungarian_minimize,
    mask_iou,
    maximize_mask_iou_assignment,
)


def _nonnegative_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _iou_threshold(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("iou_threshold must be finite and in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("iou_threshold must be finite and in [0, 1]")
    return result


@dataclass(frozen=True, slots=True)
class ImageMetricInput:
    formal_sample_index: int
    truth_count: int
    candidate_count: int
    matches: tuple[MaskMatch, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "formal_sample_index",
            _nonnegative_integer("formal_sample_index", self.formal_sample_index),
        )
        object.__setattr__(
            self, "truth_count", _nonnegative_integer("truth_count", self.truth_count)
        )
        object.__setattr__(
            self,
            "candidate_count",
            _nonnegative_integer("candidate_count", self.candidate_count),
        )
        matches = tuple(self.matches)
        if not all(isinstance(match, MaskMatch) for match in matches):
            raise ValueError("matches must contain MaskMatch values")
        truth_ids = [match.truth_instance_id for match in matches]
        candidate_ids = [match.candidate_id for match in matches]
        if len(truth_ids) != len(set(truth_ids)) or len(candidate_ids) != len(
            set(candidate_ids)
        ):
            raise ValueError("matches must be one-to-one")
        if len(matches) > min(self.truth_count, self.candidate_count):
            raise ValueError("matches exceed truth or candidate count")
        object.__setattr__(self, "matches", matches)


@dataclass(frozen=True, slots=True)
class InstanceMetricSummary:
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    mean_iou: float | None
    mean_dice: float | None


@dataclass(frozen=True, slots=True)
class ApSummary:
    by_iou_threshold: tuple[tuple[float, float | None], ...]
    mask_ap50: float | None
    mask_ap75: float | None
    mask_map: float | None


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    lower: float | None
    upper: float | None

    def __post_init__(self) -> None:
        if self.lower is None or self.upper is None:
            if self.lower is not None or self.upper is not None:
                raise ValueError("confidence interval bounds must both be null or finite")
            return
        lower = float(self.lower)
        upper = float(self.upper)
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise ValueError("confidence interval bounds must be finite")
        if lower > upper:
            raise ValueError("confidence interval lower bound exceeds upper bound")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)


def summarize_image_metrics(
    samples: Sequence[ImageMetricInput], *, iou_threshold: float
) -> InstanceMetricSummary:
    threshold = _iou_threshold(iou_threshold)
    total_truth = 0
    total_candidates = 0
    qualified_ious: list[float] = []
    for sample in samples:
        if not isinstance(sample, ImageMetricInput):
            raise ValueError("samples must contain ImageMetricInput values")
        total_truth += sample.truth_count
        total_candidates += sample.candidate_count
        qualified_ious.extend(
            match.iou for match in sample.matches if match.iou >= threshold
        )
    true_positive = len(qualified_ious)
    false_positive = total_candidates - true_positive
    false_negative = total_truth - true_positive
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = (
        None
        if precision_denominator == 0
        else float(true_positive / precision_denominator)
    )
    recall = (
        None if recall_denominator == 0 else float(true_positive / recall_denominator)
    )
    mean_iou = float(np.mean(qualified_ious)) if qualified_ious else None
    mean_dice = (
        float(np.mean([(2.0 * iou) / (1.0 + iou) for iou in qualified_ious]))
        if qualified_ious
        else None
    )
    return InstanceMetricSummary(
        tp=true_positive,
        fp=false_positive,
        fn=false_negative,
        precision=precision,
        recall=recall,
        mean_iou=mean_iou,
        mean_dice=mean_dice,
    )


def compute_image_metrics(
    truth: Sequence[TruthInstance],
    candidates: Sequence[RawCandidate],
    evidence_root: Path | None = None,
    *,
    iou_threshold: float,
) -> InstanceMetricSummary:
    truth_items = tuple(truth)
    candidate_items = tuple(candidates)
    if (truth_items or candidate_items) and evidence_root is None:
        raise ValueError("evidence_root is required when masks are present")
    matches = (
        maximize_mask_iou_assignment(truth_items, candidate_items, evidence_root)
        if truth_items and candidate_items and evidence_root is not None
        else ()
    )
    return summarize_image_metrics(
        (
            ImageMetricInput(
                formal_sample_index=0,
                truth_count=len(truth_items),
                candidate_count=len(candidate_items),
                matches=matches,
            ),
        ),
        iou_threshold=iou_threshold,
    )


def interpolated_ap(recall: np.ndarray, precision: np.ndarray) -> float | None:
    recall_values = np.asarray(recall, dtype=np.float64)
    precision_values = np.asarray(precision, dtype=np.float64)
    if recall_values.ndim != 1 or precision_values.ndim != 1:
        raise ValueError("recall and precision must be one-dimensional")
    if recall_values.shape != precision_values.shape:
        raise ValueError("recall and precision must have the same shape")
    if precision_values.size == 0:
        return None
    if not np.all(np.isfinite(recall_values)) or not np.all(
        np.isfinite(precision_values)
    ):
        raise ValueError("recall and precision must be finite")
    if np.any((recall_values < 0.0) | (recall_values > 1.0)) or np.any(
        (precision_values < 0.0) | (precision_values > 1.0)
    ):
        raise ValueError("recall and precision must be in [0, 1]")
    levels = np.linspace(0.0, 1.0, 101)
    return float(
        np.mean(
            [
                np.max(precision_values[recall_values >= level], initial=0.0)
                for level in levels
            ]
        )
    )


def _validate_record_truth_pair(record: PredictionRecord, truth: TruthSample) -> None:
    if (
        record.formal_sample_index != truth.formal_sample_index
        or record.split != truth.split
        or record.scenario != truth.scenario
        or record.image_relpath != truth.image_relpath
        or record.image_sha256 != truth.image_sha256
        or record.image_width != truth.image_width
        or record.image_height != truth.image_height
    ):
        raise ValueError("prediction record does not match truth sample")


def _ap_at_threshold(
    ranked_candidates: Sequence[tuple[int, RawCandidate]],
    truths_by_index: dict[int, TruthSample],
    evidence_root: Path,
    threshold: float,
) -> float | None:
    total_truth = sum(len(sample.instances) for sample in truths_by_index.values())
    if total_truth == 0:
        return None
    selected_by_index: dict[int, list[RawCandidate]] = {}
    matched_by_index: dict[int, int] = {}
    precision: list[float] = []
    recall: list[float] = []
    previous_total = 0
    for rank, (sample_index, candidate) in enumerate(ranked_candidates, start=1):
        selected = selected_by_index.setdefault(sample_index, [])
        selected.append(candidate)
        sample = truths_by_index[sample_index]
        matched_by_index[sample_index] = _thresholded_match_count(
            sample.instances, tuple(selected), evidence_root, threshold
        )
        current_total = sum(matched_by_index.values())
        if current_total < previous_total:
            raise ValueError("thresholded Hungarian true positives must be monotonic")
        previous_total = current_total
        precision.append(float(current_total / rank))
        recall.append(float(current_total / total_truth))
    return interpolated_ap(np.asarray(recall), np.asarray(precision))


def _thresholded_match_count(
    truth: Sequence[TruthInstance],
    candidates: Sequence[RawCandidate],
    evidence_root: Path,
    threshold: float,
) -> int:
    ordered_truth = tuple(sorted(truth, key=lambda item: item.instance_id))
    ordered_candidates = tuple(
        sorted(candidates, key=lambda item: (-item.ranking_score, item.candidate_id))
    )
    if not ordered_truth or not ordered_candidates:
        return 0
    truth_masks = tuple(read_mask(item.mask, evidence_root) for item in ordered_truth)
    candidate_masks = tuple(
        read_mask(item.mask, evidence_root) for item in ordered_candidates
    )
    ious = np.asarray(
        [
            [mask_iou(truth_mask, candidate_mask) for candidate_mask in candidate_masks]
            for truth_mask in truth_masks
        ],
        dtype=np.float64,
    )
    eligible = ious >= threshold
    cardinality_weight = float(min(ious.shape) + 1)
    assignment = _hungarian_minimize(-(eligible * cardinality_weight + ious))
    return sum(
        column is not None and bool(eligible[row, column])
        for row, column in enumerate(assignment)
    )


def compute_ap(
    records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    evidence_root: Path,
    iou_thresholds: Sequence[float],
) -> ApSummary:
    truth_items = tuple(truths)
    record_items = tuple(records)
    if not all(isinstance(item, TruthSample) for item in truth_items):
        raise ValueError("truths must contain TruthSample values")
    if not all(isinstance(item, PredictionRecord) for item in record_items):
        raise ValueError("records must contain PredictionRecord values")
    truths_by_index = {item.formal_sample_index: item for item in truth_items}
    records_by_index = {item.formal_sample_index: item for item in record_items}
    if len(truths_by_index) != len(truth_items):
        raise ValueError("truth formal_sample_index values must be unique")
    if len(records_by_index) != len(record_items):
        raise ValueError("record formal_sample_index values must be unique")
    if set(truths_by_index) != set(records_by_index):
        raise ValueError("records and truths must cover the same images")
    for sample_index, truth in truths_by_index.items():
        _validate_record_truth_pair(records_by_index[sample_index], truth)

    thresholds = tuple(sorted({_iou_threshold(item) for item in iou_thresholds}))
    if not thresholds:
        raise ValueError("iou_thresholds must be non-empty")
    ranked_candidates = sorted(
        (
            (record.formal_sample_index, candidate)
            for record in record_items
            if record.record_status is RecordStatus.OK
            for candidate in record.raw_candidates
        ),
        key=lambda item: (
            -item[1].ranking_score,
            item[0],
            item[1].candidate_id,
        ),
    )
    by_threshold = tuple(
        (
            threshold,
            _ap_at_threshold(
                ranked_candidates,
                truths_by_index,
                evidence_root,
                threshold,
            ),
        )
        for threshold in thresholds
    )
    values = [value for _, value in by_threshold if value is not None]
    return ApSummary(
        by_iou_threshold=by_threshold,
        mask_ap50=next(
            (value for threshold, value in by_threshold if threshold == 0.50), None
        ),
        mask_ap75=next(
            (value for threshold, value in by_threshold if threshold == 0.75), None
        ),
        mask_map=float(np.mean(values)) if values else None,
    )


def _bootstrap_parameters(seed: int, repetitions: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if (
        isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or repetitions <= 0
    ):
        raise ValueError("repetitions must be a positive integer")


def _finite_metric(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
        raise ValueError("bootstrap metric must return a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("bootstrap metric must return a finite number")
    return result


def _interval(values: np.ndarray) -> ConfidenceInterval:
    return ConfidenceInterval(
        float(np.quantile(values, 0.025)),
        float(np.quantile(values, 0.975)),
    )


def bootstrap_image_metrics(
    samples: Sequence[ImageMetricInput],
    metric: Callable[[Sequence[ImageMetricInput]], float],
    *,
    seed: int = 20260902,
    repetitions: int = 10_000,
) -> ConfidenceInterval:
    _bootstrap_parameters(seed, repetitions)
    sample_items = tuple(samples)
    if not all(isinstance(sample, ImageMetricInput) for sample in sample_items):
        raise ValueError("samples must contain ImageMetricInput values")
    if not sample_items:
        return ConfidenceInterval(None, None)
    rng = np.random.default_rng(seed)
    values = np.empty(repetitions, dtype=np.float64)
    for repetition in range(repetitions):
        selected = rng.integers(0, len(sample_items), size=len(sample_items))
        values[repetition] = _finite_metric(
            metric(tuple(sample_items[index] for index in selected))
        )
    return _interval(values)


def bootstrap_paired_image_metrics(
    first: Sequence[ImageMetricInput],
    second: Sequence[ImageMetricInput],
    metric: Callable[[Sequence[ImageMetricInput]], float],
    *,
    seed: int = 20260902,
    repetitions: int = 10_000,
) -> ConfidenceInterval:
    _bootstrap_parameters(seed, repetitions)
    first_items = tuple(first)
    second_items = tuple(second)
    if not all(isinstance(sample, ImageMetricInput) for sample in first_items + second_items):
        raise ValueError("paired samples must contain ImageMetricInput values")
    first_by_index = {sample.formal_sample_index: sample for sample in first_items}
    second_by_index = {sample.formal_sample_index: sample for sample in second_items}
    if (
        len(first_by_index) != len(first_items)
        or len(second_by_index) != len(second_items)
        or set(first_by_index) != set(second_by_index)
    ):
        raise ValueError("paired samples must cover the same unique image indices")
    if not first_items:
        return ConfidenceInterval(None, None)
    indices = tuple(sorted(first_by_index))
    aligned_first = tuple(first_by_index[index] for index in indices)
    aligned_second = tuple(second_by_index[index] for index in indices)
    rng = np.random.default_rng(seed)
    values = np.empty(repetitions, dtype=np.float64)
    for repetition in range(repetitions):
        selected = rng.integers(0, len(indices), size=len(indices))
        first_value = _finite_metric(
            metric(tuple(aligned_first[index] for index in selected))
        )
        second_value = _finite_metric(
            metric(tuple(aligned_second[index] for index in selected))
        )
        values[repetition] = first_value - second_value
    return _interval(values)
