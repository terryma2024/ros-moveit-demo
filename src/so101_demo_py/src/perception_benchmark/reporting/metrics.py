"""Detection metrics: F1, bootstrap, average precision traces and metric details."""

from __future__ import annotations

import math
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.codec import (
    read_mask,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    TruthSample,
)
from so101_demo.perception_benchmark.metrics import (
    ConfidenceInterval,
    ImageMetricInput,
    InstanceMetricSummary,
    _thresholded_match_count,
    interpolated_ap,
    summarize_image_metrics,
)
from so101_demo.perception_benchmark.reporting.records import _IOU_THRESHOLDS, MetricDetails


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else float(numerator / denominator)


def _f1(summary: InstanceMetricSummary) -> float | None:
    if summary.precision is None or summary.recall is None:
        return None
    denominator = summary.precision + summary.recall
    return 0.0 if denominator == 0.0 else float(
        2.0 * summary.precision * summary.recall / denominator
    )


def _metric_f1(samples: Sequence[ImageMetricInput]) -> float | None:
    return _f1(summarize_image_metrics(samples, iou_threshold=0.50))


def _null_interval() -> ConfidenceInterval:
    return ConfidenceInterval(None, None)


def _bootstrap_rows(
    rows: Sequence[object],
    metric: Callable[[tuple[object, ...]], float | None],
    *,
    seed: int,
    repetitions: int,
) -> ConfidenceInterval:
    items = tuple(rows)
    point = metric(items)
    if not items or point is None:
        return _null_interval()
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(repetitions):
        selected = rng.integers(0, len(items), size=len(items))
        result = metric(tuple(items[index] for index in selected))
        if result is None:
            continue
        numeric = float(result)
        if not math.isfinite(numeric):
            raise ValueError("bootstrap metric returned a nonfinite value")
        values.append(numeric)
    if not values:
        return _null_interval()
    return ConfidenceInterval(
        float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
    )


def _ap_prefix_traces(
    records: tuple[PredictionRecord, ...],
) -> tuple[tuple[RawCandidate, ...], ...]:
    return tuple(
        tuple(
            sorted(
                record.raw_candidates,
                key=lambda candidate: (-candidate.ranking_score, candidate.candidate_id),
            )
        )
        if record.record_status is RecordStatus.OK
        else ()
        for record in records
    )


def _ap_match_traces(
    ordered_candidates: tuple[tuple[RawCandidate, ...], ...],
    truths: tuple[TruthSample, ...],
    truth_root: Path,
    candidate_root: Path,
) -> Mapping[tuple[int, float], tuple[int, ...]]:
    traces: dict[tuple[int, float], tuple[int, ...]] = {}
    for image_position, (candidates, truth) in enumerate(
        zip(ordered_candidates, truths, strict=True)
    ):
        for threshold in _IOU_THRESHOLDS:
            traces[(image_position, threshold)] = tuple(
                _thresholded_match_count(
                    truth.instances,
                    candidates[:prefix_length],
                    truth_root,
                    threshold,
                    candidate_evidence_root=candidate_root,
                )
                for prefix_length in range(1, len(candidates) + 1)
            )
    return MappingProxyType(traces)


def _bootstrap_ap_value(
    selected: tuple[object, ...],
    *,
    ordered_candidates: tuple[tuple[RawCandidate, ...], ...],
    truths: tuple[TruthSample, ...],
    match_traces: Mapping[tuple[int, float], tuple[int, ...]],
    mean_over_thresholds: bool,
) -> float | None:
    selected_positions = tuple(int(position) for position in selected)
    total_truth = sum(len(truths[position].instances) for position in selected_positions)
    if total_truth == 0:
        return None
    events = sorted(
        (
            -candidate.ranking_score,
            copy_position,
            candidate.candidate_id,
            source_position,
            prefix_position,
        )
        for copy_position, source_position in enumerate(selected_positions)
        for prefix_position, candidate in enumerate(
            ordered_candidates[source_position]
        )
    )
    values: list[float] = []
    thresholds = _IOU_THRESHOLDS if mean_over_thresholds else (0.50,)
    for threshold in thresholds:
        matched_by_copy: dict[int, int] = {}
        current_total = 0
        precision: list[float] = []
        recall: list[float] = []
        for rank, (_, copy_position, _, source_position, prefix_position) in enumerate(
            events, start=1
        ):
            matched = match_traces[(source_position, threshold)][prefix_position]
            current_total += matched - matched_by_copy.get(copy_position, 0)
            matched_by_copy[copy_position] = matched
            precision.append(float(current_total / rank))
            recall.append(float(current_total / total_truth))
        ap = interpolated_ap(np.asarray(recall), np.asarray(precision))
        if ap is not None:
            values.append(ap)
    return None if not values else float(np.mean(values))


def _ap_intervals(
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    truth_root: Path,
    candidate_root: Path,
    *,
    seed: int,
    repetitions: int,
) -> Mapping[str, ConfidenceInterval]:
    ordered_candidates = _ap_prefix_traces(records)
    match_traces = _ap_match_traces(
        ordered_candidates, truths, truth_root, candidate_root
    )
    rows = tuple(range(len(records)))

    def metric(
        selected: tuple[object, ...], *, mean_over_thresholds: bool
    ) -> float | None:
        return _bootstrap_ap_value(
            selected,
            ordered_candidates=ordered_candidates,
            truths=truths,
            match_traces=match_traces,
            mean_over_thresholds=mean_over_thresholds,
        )

    return MappingProxyType(
        {
            "mask_ap50": _bootstrap_rows(
                rows,
                lambda selected: metric(selected, mean_over_thresholds=False),
                seed=seed,
                repetitions=repetitions,
            ),
            "mask_ap50_95": _bootstrap_rows(
                rows,
                lambda selected: metric(selected, mean_over_thresholds=True),
                seed=seed,
                repetitions=repetitions,
            ),
        }
    )


def _metric_details(
    inputs: tuple[ImageMetricInput, ...],
    records: tuple[PredictionRecord, ...],
    *,
    seed: int,
    repetitions: int,
) -> tuple[InstanceMetricSummary, MetricDetails]:
    summary = summarize_image_metrics(inputs, iou_threshold=0.50)
    qualified = [
        match.iou
        for sample in inputs
        for match in sample.matches
        if match.iou >= 0.50
    ]
    dice = [(2.0 * iou) / (1.0 + iou) for iou in qualified]
    exact = sum(
        record.record_status is RecordStatus.OK
        and sample.truth_count == sample.candidate_count
        for record, sample in zip(records, inputs, strict=True)
    )
    count = len(inputs)
    f1_value = _f1(summary)
    f1_interval = (
        _null_interval()
        if f1_value is None
        else _bootstrap_rows(
            inputs,
            _metric_f1,
            seed=seed,
            repetitions=repetitions,
        )
    )
    def qualified_values(selected: Sequence[ImageMetricInput]) -> tuple[float, ...]:
        return tuple(
            match.iou
            for sample in selected
            for match in sample.matches
            if match.iou >= 0.50
        )

    def bootstrap_instance_metric(
        point: float | None,
        metric: Callable[[Sequence[ImageMetricInput]], float | None],
    ) -> ConfidenceInterval:
        if point is None:
            return _null_interval()

        return _bootstrap_rows(
            inputs,
            lambda selected: metric(selected),
            seed=seed,
            repetitions=repetitions,
        )

    median_iou = float(np.median(qualified)) if qualified else None
    median_dice = float(np.median(dice)) if dice else None
    precision_interval = bootstrap_instance_metric(
        summary.precision,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).precision,
    )
    recall_interval = bootstrap_instance_metric(
        summary.recall,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).recall,
    )
    mean_iou_interval = bootstrap_instance_metric(
        summary.mean_iou,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).mean_iou,
    )
    mean_dice_interval = bootstrap_instance_metric(
        summary.mean_dice,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).mean_dice,
    )
    median_iou_interval = bootstrap_instance_metric(
        median_iou,
        lambda selected: (
            float(np.median(qualified_values(selected)))
            if qualified_values(selected)
            else None
        ),
    )
    median_dice_interval = bootstrap_instance_metric(
        median_dice,
        lambda selected: (
            float(
                np.median(
                    [
                        (2.0 * iou) / (1.0 + iou)
                        for iou in qualified_values(selected)
                    ]
                )
            )
            if qualified_values(selected)
            else None
        ),
    )
    rows = tuple(zip(records, inputs, strict=True))

    def exact_metric(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        correct = 0
        for row in selected:
            record, sample = row  # type: ignore[misc]
            correct += bool(
                record.record_status is RecordStatus.OK
                and sample.truth_count == sample.candidate_count
            )
        return float(correct / len(selected))

    def fp_metric(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        samples = tuple(row[1] for row in selected)  # type: ignore[index]
        return float(
            summarize_image_metrics(samples, iou_threshold=0.50).fp
            / len(samples)
        )

    def fn_metric(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        samples = tuple(row[1] for row in selected)  # type: ignore[index]
        return float(
            summarize_image_metrics(samples, iou_threshold=0.50).fn
            / len(samples)
        )

    intervals = MappingProxyType(
        {
            "precision_at_50": precision_interval,
            "recall_at_50": recall_interval,
            "f1_at_50": f1_interval,
            "mean_iou": mean_iou_interval,
            "median_iou": median_iou_interval,
            "mean_dice": mean_dice_interval,
            "median_dice": median_dice_interval,
            "exact_count_accuracy": _bootstrap_rows(
                rows, exact_metric, seed=seed, repetitions=repetitions
            ),
            "fp_per_image": _bootstrap_rows(
                rows, fp_metric, seed=seed, repetitions=repetitions
            ),
            "fn_per_image": _bootstrap_rows(
                rows, fn_metric, seed=seed, repetitions=repetitions
            ),
        }
    )
    return summary, MetricDetails(
        f1=f1_value,
        median_iou=median_iou,
        median_dice=median_dice,
        exact_count_accuracy=_rate(exact, count),
        fp_per_image=None if count == 0 else float(summary.fp / count),
        fn_per_image=None if count == 0 else float(summary.fn / count),
        confidence_intervals=intervals,
    )


def _per_image_leakage_counts(
    record: PredictionRecord,
    truth: TruthSample,
    truth_root: Path,
    candidate_root: Path,
) -> tuple[int, int]:
    if record.record_status is RecordStatus.ERROR or not record.raw_candidates:
        return (0, 0)
    predicted = np.zeros((truth.image_height, truth.image_width), dtype=bool)
    truth_union = np.zeros_like(predicted)
    for candidate in record.raw_candidates:
        predicted |= read_mask(candidate.mask, candidate_root)
    for instance in truth.instances:
        truth_union |= read_mask(instance.mask, truth_root)
    predicted_pixels = int(predicted.sum())
    return (
        int(np.count_nonzero(predicted & ~truth_union)),
        predicted_pixels,
    )
