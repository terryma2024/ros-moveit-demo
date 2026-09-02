"""Immutable decision replay and safety-oriented benchmark metrics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol, Sequence

import numpy as np

from so101_demo.perception_benchmark.codec import read_mask
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    TruthSample,
)
from so101_demo.perception_benchmark.metrics import ImageMetricInput


OUTPUTS = ("NOT_FOUND", "UNIQUE", "AMBIGUOUS", "ERROR")
TRUTHS = ("0", "1", "2+")
_EXPECTED_OUTPUT = {
    "0": DecisionOutput.NOT_FOUND,
    "1": DecisionOutput.UNIQUE,
    "2+": DecisionOutput.AMBIGUOUS,
}


class DecisionThresholds(Protocol):
    """A deterministic candidate filter used for offline decision replay."""

    def filter_candidates(
        self, candidates: tuple[RawCandidate, ...]
    ) -> tuple[RawCandidate, ...]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DecisionReplay:
    """A replayed selector output without changes to the raw record."""

    decision: DecisionOutput
    selected_candidate_id: str | None
    rejection_reason: str | None


@dataclass(frozen=True, slots=True)
class DecisionMetrics:
    """Dataset-level 0/1/2+ decision and safety metrics."""

    sample_count: int
    error_count: int
    confusion: Mapping[str, Mapping[str, int]]
    macro_f1: float | None
    unsafe_unique_count: int
    unsafe_unique_denominator: int
    unsafe_unique_rate: float | None
    unique_success_count: int
    unique_success_denominator: int
    unique_success_rate: float | None


@dataclass(frozen=True, slots=True)
class ScenarioMetrics:
    """Scenario-level safety, recall, and cup-mask leakage metrics."""

    sample_count: int
    error_count: int
    no_cup_sample_count: int
    no_cup_false_positive_count: int
    no_cup_false_positive_rate: float | None
    two_cup_sample_count: int
    two_cup_both_matched_count: int
    two_cup_both_matched_recall: float | None
    predicted_union_pixel_count: int
    non_cup_leakage_pixel_count: int
    non_cup_leakage_ratio: float


def replay_decision(
    record: PredictionRecord, config: DecisionThresholds
) -> DecisionReplay:
    """Replay only the 0/1/2+ selector decision over immutable raw candidates."""

    if not isinstance(record, PredictionRecord):
        raise ValueError("record must be a PredictionRecord")
    if record.record_status is RecordStatus.ERROR:
        return DecisionReplay(DecisionOutput.ERROR, None, record.error_type)

    accepted = tuple(config.filter_candidates(record.raw_candidates))
    if not all(isinstance(candidate, RawCandidate) for candidate in accepted):
        raise ValueError("filter_candidates must return RawCandidate values")
    accepted_ids = [candidate.candidate_id for candidate in accepted]
    if len(accepted_ids) != len(set(accepted_ids)):
        raise ValueError("filter_candidates must not return duplicate candidates")
    raw_by_id = {
        candidate.candidate_id: candidate for candidate in record.raw_candidates
    }
    if any(
        candidate.candidate_id not in raw_by_id
        or candidate != raw_by_id[candidate.candidate_id]
        for candidate in accepted
    ):
        raise ValueError("filter_candidates must return a subset of raw_candidates")

    if not accepted:
        return DecisionReplay(
            DecisionOutput.NOT_FOUND, None, "TARGET_NOT_FOUND"
        )
    if len(accepted) > 1:
        return DecisionReplay(
            DecisionOutput.AMBIGUOUS, None, "TARGET_AMBIGUOUS"
        )
    return DecisionReplay(DecisionOutput.UNIQUE, accepted[0].candidate_id, None)


def decision_confusion(
    pairs: Iterable[tuple[str, DecisionOutput]],
) -> dict[str, dict[str, int]]:
    """Build a complete fixed 3x4 decision confusion matrix."""

    matrix = {
        truth: {output: 0 for output in OUTPUTS}
        for truth in TRUTHS
    }
    for truth, output in pairs:
        if truth not in matrix:
            raise ValueError("truth decision class must be 0, 1, or 2+")
        if not isinstance(output, DecisionOutput):
            raise ValueError("decision output must be a DecisionOutput")
        matrix[truth][output.value] += 1
    return matrix


def _truth_class(truth: TruthSample) -> str:
    count = len(truth.instances)
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    return "2+"


def _validated_pairs(
    records: Sequence[PredictionRecord], truths: Sequence[TruthSample]
) -> tuple[tuple[PredictionRecord, TruthSample], ...]:
    record_items = tuple(records)
    truth_items = tuple(truths)
    if not all(isinstance(record, PredictionRecord) for record in record_items):
        raise ValueError("records must contain PredictionRecord values")
    if not all(isinstance(truth, TruthSample) for truth in truth_items):
        raise ValueError("truths must contain TruthSample values")

    records_by_index = {
        record.formal_sample_index: record for record in record_items
    }
    truths_by_index = {
        truth.formal_sample_index: truth for truth in truth_items
    }
    if len(records_by_index) != len(record_items):
        raise ValueError("record formal_sample_index values must be unique")
    if len(truths_by_index) != len(truth_items):
        raise ValueError("truth formal_sample_index values must be unique")
    if set(records_by_index) != set(truths_by_index):
        raise ValueError("records and truths must cover the same images")

    pairs: list[tuple[PredictionRecord, TruthSample]] = []
    for sample_index in sorted(records_by_index):
        record = records_by_index[sample_index]
        truth = truths_by_index[sample_index]
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
        pairs.append((record, truth))
    return tuple(pairs)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def _macro_f1(matrix: Mapping[str, Mapping[str, int]]) -> float:
    scores: list[float] = []
    for truth_class, expected_output in _EXPECTED_OUTPUT.items():
        output = expected_output.value
        true_positive = matrix[truth_class][output]
        false_positive = sum(
            matrix[other_truth][output]
            for other_truth in TRUTHS
            if other_truth != truth_class
        )
        false_negative = sum(
            count
            for actual_output, count in matrix[truth_class].items()
            if actual_output != output
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(
            0.0 if denominator == 0 else (2.0 * true_positive) / denominator
        )
    return float(sum(scores) / len(scores))


def aggregate_decisions(
    records: Sequence[PredictionRecord], truths: Sequence[TruthSample]
) -> DecisionMetrics:
    """Aggregate decision quality while retaining ERROR in every denominator."""

    pairs = _validated_pairs(records, truths)
    matrix = decision_confusion(
        (_truth_class(truth), record.decision) for record, truth in pairs
    )
    sample_count = len(pairs)
    error_count = sum(
        matrix[truth_class][DecisionOutput.ERROR.value]
        for truth_class in TRUTHS
    )
    unsafe_denominator = sum(
        matrix[truth_class][output]
        for truth_class in ("0", "2+")
        for output in OUTPUTS
    )
    unsafe_count = sum(
        matrix[truth_class][DecisionOutput.UNIQUE.value]
        for truth_class in ("0", "2+")
    )
    unique_denominator = sum(matrix["1"].values())
    unique_count = matrix["1"][DecisionOutput.UNIQUE.value]
    immutable_matrix = MappingProxyType(
        {
            truth_class: MappingProxyType(dict(outputs))
            for truth_class, outputs in matrix.items()
        }
    )
    return DecisionMetrics(
        sample_count=sample_count,
        error_count=error_count,
        confusion=immutable_matrix,
        macro_f1=None if sample_count == 0 else _macro_f1(matrix),
        unsafe_unique_count=unsafe_count,
        unsafe_unique_denominator=unsafe_denominator,
        unsafe_unique_rate=_rate(unsafe_count, unsafe_denominator),
        unique_success_count=unique_count,
        unique_success_denominator=unique_denominator,
        unique_success_rate=_rate(unique_count, unique_denominator),
    )


def non_cup_leakage_ratio(
    predicted_union: np.ndarray, truth_cup_union: np.ndarray
) -> float:
    """Return predicted pixels outside the truth cup union over predicted pixels."""

    predicted = np.asarray(predicted_union, dtype=bool)
    truth = np.asarray(truth_cup_union, dtype=bool)
    if predicted.ndim != 2 or truth.ndim != 2:
        raise ValueError("masks must be two-dimensional")
    if predicted.shape != truth.shape:
        raise ValueError("masks must have the same shape")
    denominator = int(np.count_nonzero(predicted))
    if denominator == 0:
        return 0.0
    numerator = int(np.count_nonzero(predicted & ~truth))
    return float(numerator / denominator)


def _validated_image_inputs(
    image_inputs: Sequence[ImageMetricInput],
    pairs: Sequence[tuple[PredictionRecord, TruthSample]],
) -> Mapping[int, ImageMetricInput]:
    items = tuple(image_inputs)
    if not all(isinstance(item, ImageMetricInput) for item in items):
        raise ValueError("matches must contain ImageMetricInput values")
    by_index = {item.formal_sample_index: item for item in items}
    if len(by_index) != len(items):
        raise ValueError("match formal_sample_index values must be unique")
    expected_indices = {record.formal_sample_index for record, _ in pairs}
    if set(by_index) != expected_indices:
        raise ValueError("records, truths, and matches must cover the same images")

    for record, truth in pairs:
        item = by_index[record.formal_sample_index]
        if item.truth_count != len(truth.instances):
            raise ValueError("match truth_count does not match truth sample")
        if item.candidate_count != len(record.raw_candidates):
            raise ValueError("match candidate_count does not match prediction record")
        truth_ids = {instance.instance_id for instance in truth.instances}
        candidate_ids = {
            candidate.candidate_id for candidate in record.raw_candidates
        }
        if any(match.truth_instance_id not in truth_ids for match in item.matches):
            raise ValueError("match truth_instance_id is outside the aligned image")
        if any(match.candidate_id not in candidate_ids for match in item.matches):
            raise ValueError("match candidate_id is outside the aligned image")
    return MappingProxyType(by_index)


@dataclass(slots=True)
class _ScenarioAccumulator:
    sample_count: int = 0
    error_count: int = 0
    no_cup_sample_count: int = 0
    no_cup_false_positive_count: int = 0
    two_cup_sample_count: int = 0
    two_cup_both_matched_count: int = 0
    predicted_union_pixel_count: int = 0
    non_cup_leakage_pixel_count: int = 0


def aggregate_scenarios(
    records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    matches: Sequence[ImageMetricInput],
    evidence_root: Path,
) -> Mapping[str, ScenarioMetrics]:
    """Aggregate fail-closed per-scenario safety and mask leakage metrics."""

    try:
        root = Path(evidence_root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("evidence_root must be an existing directory") from error
    if not root.is_dir():
        raise ValueError("evidence_root must be an existing directory")

    pairs = _validated_pairs(records, truths)
    inputs_by_index = _validated_image_inputs(matches, pairs)
    accumulators: dict[str, _ScenarioAccumulator] = {}
    for record, truth in pairs:
        image_input = inputs_by_index[record.formal_sample_index]
        accumulator = accumulators.setdefault(
            truth.scenario, _ScenarioAccumulator()
        )
        accumulator.sample_count += 1
        if record.record_status is RecordStatus.ERROR:
            accumulator.error_count += 1

        if not truth.instances:
            accumulator.no_cup_sample_count += 1
            if (
                record.record_status is RecordStatus.OK
                and record.decision
                in (DecisionOutput.UNIQUE, DecisionOutput.AMBIGUOUS)
            ):
                accumulator.no_cup_false_positive_count += 1

        if len(truth.instances) == 2:
            accumulator.two_cup_sample_count += 1
            qualified = tuple(
                match for match in image_input.matches if match.iou >= 0.50
            )
            if len(qualified) == 2:
                accumulator.two_cup_both_matched_count += 1

        shape = (truth.image_height, truth.image_width)
        truth_union = np.zeros(shape, dtype=bool)
        for instance in truth.instances:
            truth_union |= read_mask(instance.mask, root)
        predicted_union = np.zeros(shape, dtype=bool)
        if record.record_status is RecordStatus.OK:
            for candidate in record.raw_candidates:
                predicted_union |= read_mask(candidate.mask, root)
        predicted_pixels = int(np.count_nonzero(predicted_union))
        leakage_pixels = int(np.count_nonzero(predicted_union & ~truth_union))
        accumulator.predicted_union_pixel_count += predicted_pixels
        accumulator.non_cup_leakage_pixel_count += leakage_pixels

    return MappingProxyType(
        {
            scenario: ScenarioMetrics(
                sample_count=value.sample_count,
                error_count=value.error_count,
                no_cup_sample_count=value.no_cup_sample_count,
                no_cup_false_positive_count=value.no_cup_false_positive_count,
                no_cup_false_positive_rate=_rate(
                    value.no_cup_false_positive_count,
                    value.no_cup_sample_count,
                ),
                two_cup_sample_count=value.two_cup_sample_count,
                two_cup_both_matched_count=value.two_cup_both_matched_count,
                two_cup_both_matched_recall=_rate(
                    value.two_cup_both_matched_count,
                    value.two_cup_sample_count,
                ),
                predicted_union_pixel_count=value.predicted_union_pixel_count,
                non_cup_leakage_pixel_count=value.non_cup_leakage_pixel_count,
                non_cup_leakage_ratio=(
                    0.0
                    if value.predicted_union_pixel_count == 0
                    else float(
                        value.non_cup_leakage_pixel_count
                        / value.predicted_union_pixel_count
                    )
                ),
            )
            for scenario, value in accumulators.items()
        }
    )


__all__ = (
    "DecisionMetrics",
    "DecisionReplay",
    "DecisionThresholds",
    "ScenarioMetrics",
    "aggregate_decisions",
    "aggregate_scenarios",
    "decision_confusion",
    "non_cup_leakage_ratio",
    "replay_decision",
)
