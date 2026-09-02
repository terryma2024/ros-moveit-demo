from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Mapping

import numpy as np
import pytest

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    MaskRef,
    PhaseTimings,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RuntimeProvenance,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.decisions import (
    aggregate_decisions,
    aggregate_scenarios,
    non_cup_leakage_ratio,
    replay_decision,
)
from so101_demo.perception_benchmark.matching import MaskMatch
from so101_demo.perception_benchmark.metrics import ImageMetricInput


class ScoreThresholds:
    """A real minimal filter used to exercise the replay protocol."""

    def __init__(self, minimum_score: float) -> None:
        self.minimum_score = minimum_score

    def filter_candidates(
        self, candidates: tuple[RawCandidate, ...]
    ) -> tuple[RawCandidate, ...]:
        return tuple(
            candidate
            for candidate in candidates
            if candidate.ranking_score >= self.minimum_score
        )


class FailIfCalledThresholds:
    """A real filter stub whose only valid use is not being called."""

    def __init__(self) -> None:
        self.call_count = 0

    def filter_candidates(
        self, candidates: tuple[RawCandidate, ...]
    ) -> tuple[RawCandidate, ...]:
        self.call_count += 1
        raise AssertionError("ERROR replay must not filter candidates")


class DuplicateCompositeMatches(
    Mapping[tuple[int, str], ImageMetricInput]
):
    """Expose a duplicate key through the Mapping iteration contract."""

    def __init__(
        self, key: tuple[int, str], value: ImageMetricInput
    ) -> None:
        self._key = key
        self._value = value

    def __getitem__(self, key: tuple[int, str]) -> ImageMetricInput:
        if key != self._key:
            raise KeyError(key)
        return self._value

    def __iter__(self):
        yield self._key
        yield self._key

    def __len__(self) -> int:
        return 2


def _write_mask(
    root: Path,
    sample_index: int,
    name: str,
    pixels: list[list[int]],
    *,
    directory: str = "masks",
) -> MaskRef:
    mask = np.asarray(pixels, dtype=bool)
    relative_path = f"{directory}/{sample_index}-{name}.json"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(encode_mask_rle(mask)))
    return MaskRef(
        relative_path=relative_path,
        sha256=sha256_bytes(mask.astype(np.uint8).tobytes(order="C")),
        pixel_count=int(mask.sum()),
        image_width=mask.shape[1],
        image_height=mask.shape[0],
    )


def _truth(
    root: Path,
    sample_index: int,
    scenario: str,
    masks: tuple[list[list[int]], ...] = (),
    *,
    image_sha256: str | None = None,
    shape: tuple[int, int] = (3, 3),
    mask_directory: str = "masks",
) -> TruthSample:
    height, width = shape
    instances = tuple(
        TruthInstance(
            instance_id=f"truth-{position}",
            label="plastic_cup",
            mask=_write_mask(
                root,
                sample_index,
                f"truth-{position}",
                pixels,
                directory=mask_directory,
            ),
        )
        for position, pixels in enumerate(masks)
    )
    return TruthSample(
        formal_sample_index=sample_index,
        split="val",
        scenario=scenario,
        image_relpath=f"images/{sample_index}.png",
        image_sha256=image_sha256 or f"{sample_index + 1:064x}",
        image_width=width,
        image_height=height,
        instances=instances,
    )


def _candidate(
    root: Path,
    sample_index: int,
    candidate_id: str,
    score: float,
    pixels: list[list[int]],
) -> RawCandidate:
    mask = _write_mask(root, sample_index, candidate_id, pixels)
    return RawCandidate(
        candidate_id=candidate_id,
        label="plastic_cup",
        bbox_xyxy=(0.0, 0.0, float(mask.image_width), float(mask.image_height)),
        mask=mask,
        ranking_score=score,
        ranking_score_source="class_confidence",
        class_confidence=score,
        grounding_box_score=None,
        grounding_text_score=None,
        sam_quality=None,
    )


def _record(
    truth: TruthSample,
    candidates: tuple[RawCandidate, ...] = (),
    *,
    decision: DecisionOutput = DecisionOutput.NOT_FOUND,
    status: RecordStatus = RecordStatus.OK,
) -> PredictionRecord:
    is_error = status is RecordStatus.ERROR
    selected_id = candidates[0].candidate_id if decision is DecisionOutput.UNIQUE else None
    rejection_reason = {
        DecisionOutput.NOT_FOUND: "TARGET_NOT_FOUND",
        DecisionOutput.AMBIGUOUS: "TARGET_AMBIGUOUS",
    }.get(decision)
    return PredictionRecord(
        run_id="run-task4-synthetic",
        schema_version="so101-perception-benchmark/v1",
        run_kind=RunKind.VAL_RAW,
        record_status=status,
        formal_sample_index=truth.formal_sample_index,
        split=truth.split,
        scenario=truth.scenario,
        image_relpath=truth.image_relpath,
        image_sha256=truth.image_sha256,
        image_width=truth.image_width,
        image_height=truth.image_height,
        model_id="yolo-seg-task4-synthetic",
        runtime_provenance=RuntimeProvenance(
            runtime_device="mps",
            runtime_name="synthetic-yolo",
            runtime_version="1.0",
            weights_sha256="a" * 64,
        ),
        config_sha256="b" * 64,
        threshold_lock_sha256=None,
        raw_candidates=candidates,
        phase_timings=PhaseTimings(),
        raw_count=len(candidates),
        decision=decision,
        selected_candidate_id=selected_id,
        rejection_reason=None if is_error else rejection_reason,
        error_type="INFERENCE_FAILED" if is_error else None,
        error_summary=None,
        timed_out=is_error,
        oom=False,
        fallback_used=False,
    )


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def _record_sha(record: PredictionRecord) -> str:
    return sha256_bytes(canonical_json_bytes(_canonical_value(record)))


def _zero_mask() -> list[list[int]]:
    return [[0, 0, 0], [0, 0, 0], [0, 0, 0]]


def _one_pixel_mask(column: int = 0) -> list[list[int]]:
    pixels = _zero_mask()
    pixels[0][column] = 1
    return pixels


def _record_for_output(
    root: Path,
    truth: TruthSample,
    output: DecisionOutput,
) -> PredictionRecord:
    if output is DecisionOutput.ERROR:
        return _record(truth, decision=DecisionOutput.ERROR, status=RecordStatus.ERROR)
    if output is DecisionOutput.NOT_FOUND:
        return _record(truth, decision=output)
    count = 1 if output is DecisionOutput.UNIQUE else 2
    candidates = tuple(
        _candidate(root, truth.formal_sample_index, f"candidate-{position}", 0.9, _one_pixel_mask(position))
        for position in range(count)
    )
    return _record(truth, candidates, decision=output)


def _metric_input(
    record: PredictionRecord,
    truth: TruthSample,
    matches: tuple[MaskMatch, ...] = (),
) -> ImageMetricInput:
    return ImageMetricInput(
        formal_sample_index=record.formal_sample_index,
        truth_count=len(truth.instances),
        candidate_count=len(record.raw_candidates),
        matches=matches,
    )


def _keyed_matches(
    records: tuple[PredictionRecord, ...],
    inputs: tuple[ImageMetricInput, ...],
) -> dict[tuple[int, str], ImageMetricInput]:
    return {
        (record.formal_sample_index, record.image_sha256): image_input
        for record, image_input in zip(records, inputs, strict=True)
    }


def test_replay_maps_zero_one_and_two_accepted_candidates_without_mutating_record(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "synthetic")
    candidates = (
        _candidate(tmp_path, 0, "low", 0.2, _one_pixel_mask(0)),
        _candidate(tmp_path, 0, "middle", 0.6, _one_pixel_mask(1)),
        _candidate(tmp_path, 0, "high", 0.9, _one_pixel_mask(2)),
    )
    record = _record(truth, candidates)
    before_sha = _record_sha(record)

    not_found = replay_decision(record, ScoreThresholds(0.95))
    unique = replay_decision(record, ScoreThresholds(0.75))
    ambiguous = replay_decision(record, ScoreThresholds(0.50))

    assert (not_found.decision, not_found.selected_candidate_id, not_found.rejection_reason) == (
        DecisionOutput.NOT_FOUND,
        None,
        "TARGET_NOT_FOUND",
    )
    assert (unique.decision, unique.selected_candidate_id, unique.rejection_reason) == (
        DecisionOutput.UNIQUE,
        "high",
        None,
    )
    assert (ambiguous.decision, ambiguous.selected_candidate_id, ambiguous.rejection_reason) == (
        DecisionOutput.AMBIGUOUS,
        None,
        "TARGET_AMBIGUOUS",
    )
    assert _record_sha(record) == before_sha
    assert tuple(candidate.candidate_id for candidate in record.raw_candidates) == (
        "low",
        "middle",
        "high",
    )
    assert tuple(candidate.class_confidence for candidate in record.raw_candidates) == (
        0.2,
        0.6,
        0.9,
    )


def test_replay_preserves_error_without_filtering_or_mutating_record(tmp_path: Path) -> None:
    truth = _truth(tmp_path, 0, "synthetic")
    record = _record(
        truth,
        decision=DecisionOutput.ERROR,
        status=RecordStatus.ERROR,
    )
    before_sha = _record_sha(record)
    thresholds = FailIfCalledThresholds()

    replay = replay_decision(record, thresholds)

    assert (replay.decision, replay.selected_candidate_id, replay.rejection_reason) == (
        DecisionOutput.ERROR,
        None,
        "INFERENCE_FAILED",
    )
    assert thresholds.call_count == 0
    assert _record_sha(record) == before_sha


def test_full_three_by_four_confusion_and_macro_f1_keep_error_column(
    tmp_path: Path,
) -> None:
    records: list[PredictionRecord] = []
    truths: list[TruthSample] = []
    truth_masks = {
        "0": (),
        "1": (_one_pixel_mask(0),),
        "2+": (_one_pixel_mask(0), _one_pixel_mask(1)),
    }
    outputs = tuple(DecisionOutput)
    for truth_position, (truth_class, masks) in enumerate(truth_masks.items()):
        for output_position, output in enumerate(outputs):
            sample_index = truth_position * len(outputs) + output_position
            truth = _truth(tmp_path, sample_index, "confusion", masks)
            truths.append(truth)
            records.append(_record_for_output(tmp_path, truth, output))

    metrics = aggregate_decisions(tuple(reversed(records)), tuple(truths))

    assert metrics.confusion == {
        "0": {"NOT_FOUND": 1, "UNIQUE": 1, "AMBIGUOUS": 1, "ERROR": 1},
        "1": {"NOT_FOUND": 1, "UNIQUE": 1, "AMBIGUOUS": 1, "ERROR": 1},
        "2+": {"NOT_FOUND": 1, "UNIQUE": 1, "AMBIGUOUS": 1, "ERROR": 1},
    }
    assert metrics.sample_count == 12
    assert metrics.error_count == 3
    assert metrics.macro_f1 == pytest.approx(2.0 / 7.0)


def test_unsafe_unique_and_unique_success_use_eligible_truth_denominators(
    tmp_path: Path,
) -> None:
    truth_zero = _truth(tmp_path, 0, "no_cup")
    truth_two = _truth(tmp_path, 1, "two_cups", (_one_pixel_mask(0), _one_pixel_mask(1)))
    truth_one_ok = _truth(tmp_path, 2, "one_cup", (_one_pixel_mask(0),))
    truth_one_error = _truth(tmp_path, 3, "one_cup", (_one_pixel_mask(0),))
    records = (
        _record_for_output(tmp_path, truth_zero, DecisionOutput.UNIQUE),
        _record_for_output(tmp_path, truth_two, DecisionOutput.UNIQUE),
        _record_for_output(tmp_path, truth_one_ok, DecisionOutput.UNIQUE),
        _record_for_output(tmp_path, truth_one_error, DecisionOutput.ERROR),
    )

    metrics = aggregate_decisions(
        records, (truth_zero, truth_two, truth_one_ok, truth_one_error)
    )

    assert metrics.unsafe_unique_count == 2
    assert metrics.unsafe_unique_denominator == 2
    assert metrics.unsafe_unique_rate == 1.0
    assert metrics.unique_success_count == 1
    assert metrics.unique_success_denominator == 2
    assert metrics.unique_success_rate == 0.5


def test_empty_decision_aggregate_uses_null_rate_semantics() -> None:
    metrics = aggregate_decisions((), ())

    assert metrics.sample_count == 0
    assert metrics.macro_f1 is None
    assert metrics.unsafe_unique_rate is None
    assert metrics.unique_success_rate is None
    assert metrics.confusion == {
        "0": {"NOT_FOUND": 0, "UNIQUE": 0, "AMBIGUOUS": 0, "ERROR": 0},
        "1": {"NOT_FOUND": 0, "UNIQUE": 0, "AMBIGUOUS": 0, "ERROR": 0},
        "2+": {"NOT_FOUND": 0, "UNIQUE": 0, "AMBIGUOUS": 0, "ERROR": 0},
    }


def test_decision_aggregate_rejects_missing_duplicate_and_sha_mismatched_images(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "synthetic")
    record = _record(truth)
    mismatched_sha_truth = _truth(
        tmp_path, 0, "synthetic", image_sha256="f" * 64
    )

    with pytest.raises(ValueError, match="same images"):
        aggregate_decisions((record,), ())
    with pytest.raises(ValueError, match="unique"):
        aggregate_decisions((record, record), (truth,))
    with pytest.raises(ValueError, match="does not match"):
        aggregate_decisions((record,), (mismatched_sha_truth,))


def test_no_cup_fpr_counts_ok_raw_candidate_rejected_by_selector(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "no_cup")
    candidate = _candidate(tmp_path, 0, "low-raw", 0.01, _one_pixel_mask())
    record = _record(
        truth,
        (candidate,),
        decision=DecisionOutput.NOT_FOUND,
    )

    metrics = aggregate_scenarios(
        (record,),
        (truth,),
        _keyed_matches((record,), (_metric_input(record, truth),)),
        evidence_root=tmp_path,
    )["no_cup"]

    assert metrics.no_cup_sample_count == 1
    assert metrics.no_cup_false_positive_count == 1
    assert metrics.no_cup_false_positive_rate == 1.0


def test_no_cup_fpr_does_not_count_ok_record_without_raw_candidates(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "no_cup")
    record = _record(truth, decision=DecisionOutput.NOT_FOUND)

    metrics = aggregate_scenarios(
        (record,),
        (truth,),
        _keyed_matches((record,), (_metric_input(record, truth),)),
        evidence_root=tmp_path,
    )["no_cup"]

    assert metrics.no_cup_sample_count == 1
    assert metrics.no_cup_false_positive_count == 0
    assert metrics.no_cup_false_positive_rate == 0.0


def test_no_cup_fpr_ignores_retained_raw_candidates_on_error_record(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "no_cup")
    partial_candidate = _candidate(
        tmp_path,
        0,
        "partial-raw",
        0.9,
        _one_pixel_mask(),
    )
    record = _record(
        truth,
        (partial_candidate,),
        decision=DecisionOutput.ERROR,
        status=RecordStatus.ERROR,
    )

    metrics = aggregate_scenarios(
        (record,),
        (truth,),
        _keyed_matches((record,), (_metric_input(record, truth),)),
        evidence_root=tmp_path,
    )["no_cup"]

    assert metrics.error_count == 1
    assert metrics.no_cup_sample_count == 1
    assert metrics.no_cup_false_positive_count == 0
    assert metrics.no_cup_false_positive_rate == 0.0
    assert metrics.predicted_union_pixel_count == 0


def test_no_cup_fpr_counts_multiple_raw_candidates_as_one_image(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "no_cup")
    candidates = (
        _candidate(tmp_path, 0, "raw-0", 0.02, _one_pixel_mask(0)),
        _candidate(tmp_path, 0, "raw-1", 0.01, _one_pixel_mask(1)),
    )
    record = _record(
        truth,
        candidates,
        decision=DecisionOutput.NOT_FOUND,
    )

    metrics = aggregate_scenarios(
        (record,),
        (truth,),
        _keyed_matches((record,), (_metric_input(record, truth),)),
        evidence_root=tmp_path,
    )["no_cup"]

    assert metrics.no_cup_sample_count == 1
    assert metrics.no_cup_false_positive_count == 1
    assert metrics.no_cup_false_positive_rate == 1.0


def test_two_cup_recall_requires_two_distinct_matches_at_iou_point_five(
    tmp_path: Path,
) -> None:
    truths = tuple(
        _truth(
            tmp_path,
            index,
            "two_cups",
            (_one_pixel_mask(0), _one_pixel_mask(1)),
        )
        for index in range(3)
    )
    records = (
        _record_for_output(tmp_path, truths[0], DecisionOutput.AMBIGUOUS),
        _record_for_output(tmp_path, truths[1], DecisionOutput.AMBIGUOUS),
        _record_for_output(tmp_path, truths[2], DecisionOutput.ERROR),
    )
    inputs = (
        _metric_input(
            records[0],
            truths[0],
            (
                MaskMatch("truth-0", "candidate-0", 0.50),
                MaskMatch("truth-1", "candidate-1", 0.90),
            ),
        ),
        _metric_input(
            records[1],
            truths[1],
            (
                MaskMatch("truth-0", "candidate-0", 0.90),
                MaskMatch("truth-1", "candidate-1", 0.49),
            ),
        ),
        _metric_input(records[2], truths[2]),
    )

    metrics = aggregate_scenarios(
        records,
        truths,
        _keyed_matches(records, inputs),
        evidence_root=tmp_path,
    )["two_cups"]

    assert metrics.sample_count == 3
    assert metrics.error_count == 1
    assert metrics.two_cup_sample_count == 3
    assert metrics.two_cup_both_matched_count == 1
    assert metrics.two_cup_both_matched_recall == pytest.approx(1.0 / 3.0)


def test_cup_near_bottle_leakage_reads_validated_masks_outside_truth_cup_union(
    tmp_path: Path,
) -> None:
    truth = _truth(
        tmp_path,
        0,
        "cup_near_bottle",
        ([[1, 1, 0], [1, 1, 0], [0, 0, 0]],),
    )
    prediction = _candidate(
        tmp_path,
        0,
        "prediction",
        0.9,
        [[1, 1, 1], [1, 1, 1], [0, 0, 1]],
    )
    empty_truth = _truth(
        tmp_path,
        1,
        "cup_near_bottle",
        ([[1, 0, 0], [0, 0, 0], [0, 0, 0]],),
    )
    records = (
        _record(truth, (prediction,), decision=DecisionOutput.UNIQUE),
        _record(empty_truth, decision=DecisionOutput.NOT_FOUND),
    )
    inputs = (
        _metric_input(records[0], truth, (MaskMatch("truth-0", "prediction", 4.0 / 7.0),)),
        _metric_input(records[1], empty_truth),
    )

    metrics = aggregate_scenarios(
        records,
        (truth, empty_truth),
        _keyed_matches(records, inputs),
        evidence_root=tmp_path,
    )["cup_near_bottle"]

    assert metrics.predicted_union_pixel_count == 7
    assert metrics.non_cup_leakage_pixel_count == 3
    assert metrics.non_cup_leakage_ratio == pytest.approx(3.0 / 7.0)


def test_scenario_leakage_supports_separate_truth_and_candidate_roots(
    tmp_path: Path,
) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    truth = _truth(
        truth_root,
        0,
        "cup_near_bottle",
        ([[1, 1, 0], [1, 1, 0], [0, 0, 0]],),
        mask_directory="truth_masks",
    )
    prediction = _candidate(
        candidate_root,
        0,
        "prediction",
        0.9,
        [[1, 1, 1], [1, 1, 1], [0, 0, 1]],
    )
    record = _record(truth, (prediction,), decision=DecisionOutput.UNIQUE)
    image_input = _metric_input(
        record,
        truth,
        (MaskMatch("truth-0", "prediction", 4.0 / 7.0),),
    )

    metrics = aggregate_scenarios(
        (record,),
        (truth,),
        _keyed_matches((record,), (image_input,)),
        truth_root,
        candidate_evidence_root=candidate_root,
    )["cup_near_bottle"]

    assert metrics.predicted_union_pixel_count == 7
    assert metrics.non_cup_leakage_pixel_count == 3
    assert metrics.non_cup_leakage_ratio == pytest.approx(3.0 / 7.0)


@pytest.mark.parametrize("invalid_side", ["truth", "candidate"])
def test_scenario_leakage_verifies_sha_on_each_separate_root(
    tmp_path: Path,
    invalid_side: str,
) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    truth = _truth(
        truth_root,
        0,
        "synthetic",
        (_one_pixel_mask(),),
        mask_directory="truth_masks",
    )
    candidate = _candidate(
        candidate_root,
        0,
        "candidate",
        0.9,
        _one_pixel_mask(),
    )
    if invalid_side == "truth":
        invalid_instance = replace(
            truth.instances[0],
            mask=replace(truth.instances[0].mask, sha256="f" * 64),
        )
        truth = replace(truth, instances=(invalid_instance,))
    else:
        candidate = replace(
            candidate,
            mask=replace(candidate.mask, sha256="f" * 64),
        )
    record = _record(truth, (candidate,), decision=DecisionOutput.UNIQUE)
    image_input = _metric_input(
        record,
        truth,
        (MaskMatch("truth-0", "candidate", 1.0),),
    )

    with pytest.raises(ValueError, match="sha256"):
        aggregate_scenarios(
            (record,),
            (truth,),
            _keyed_matches((record,), (image_input,)),
            truth_root,
            candidate_evidence_root=candidate_root,
        )


def test_non_cup_leakage_ratio_handles_zero_union_and_rejects_shape_mismatch() -> None:
    empty = np.zeros((2, 2), dtype=bool)
    cup = np.asarray([[True, False], [False, False]])

    assert non_cup_leakage_ratio(empty, cup) == 0.0
    assert non_cup_leakage_ratio(empty, empty) == 0.0
    with pytest.raises(ValueError, match="same shape"):
        non_cup_leakage_ratio(empty, np.zeros((1, 2), dtype=bool))


def test_scenario_aggregate_rejects_missing_duplicate_foreign_and_count_mismatch(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "synthetic", (_one_pixel_mask(),))
    candidate = _candidate(tmp_path, 0, "candidate", 0.9, _one_pixel_mask())
    record = _record(truth, (candidate,), decision=DecisionOutput.UNIQUE)
    valid = _metric_input(
        record, truth, (MaskMatch("truth-0", "candidate", 1.0),)
    )

    identity = (record.formal_sample_index, record.image_sha256)
    with pytest.raises(ValueError, match="composite image identities"):
        aggregate_scenarios((record,), (truth,), {}, evidence_root=tmp_path)
    with pytest.raises(ValueError, match="unique"):
        aggregate_scenarios(
            (record,),
            (truth,),
            DuplicateCompositeMatches(identity, valid),
            evidence_root=tmp_path,
        )
    foreign = ImageMetricInput(9, 0, 0, ())
    with pytest.raises(ValueError, match="composite image identities"):
        aggregate_scenarios(
            (record,),
            (truth,),
            {(9, "f" * 64): foreign},
            evidence_root=tmp_path,
        )
    wrong_count = ImageMetricInput(0, 0, 1, ())
    with pytest.raises(ValueError, match="truth_count"):
        aggregate_scenarios(
            (record,),
            (truth,),
            {identity: wrong_count},
            evidence_root=tmp_path,
        )


def test_scenario_aggregate_rejects_match_ids_outside_the_aligned_image(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "synthetic", (_one_pixel_mask(),))
    candidate = _candidate(tmp_path, 0, "candidate", 0.9, _one_pixel_mask())
    record = _record(truth, (candidate,), decision=DecisionOutput.UNIQUE)

    foreign_truth = _metric_input(
        record, truth, (MaskMatch("foreign-truth", "candidate", 1.0),)
    )
    foreign_candidate = _metric_input(
        record, truth, (MaskMatch("truth-0", "foreign-candidate", 1.0),)
    )

    with pytest.raises(ValueError, match="truth_instance_id"):
        aggregate_scenarios(
            (record,),
            (truth,),
            {
                (record.formal_sample_index, record.image_sha256): foreign_truth
            },
            evidence_root=tmp_path,
        )
    with pytest.raises(ValueError, match="candidate_id"):
        aggregate_scenarios(
            (record,),
            (truth,),
            {
                (
                    record.formal_sample_index,
                    record.image_sha256,
                ): foreign_candidate
            },
            evidence_root=tmp_path,
        )


def test_scenario_aggregate_requires_explicit_valid_evidence_root(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "synthetic", (_one_pixel_mask(),))
    candidate = _candidate(tmp_path, 0, "candidate", 0.9, _one_pixel_mask())
    record = _record(truth, (candidate,), decision=DecisionOutput.UNIQUE)
    image_input = _metric_input(
        record, truth, (MaskMatch("truth-0", "candidate", 1.0),)
    )

    with pytest.raises(ValueError, match="evidence_root"):
        aggregate_scenarios(
            (record,),
            (truth,),
            {
                (record.formal_sample_index, record.image_sha256): image_input
            },
            evidence_root=tmp_path / "missing",
        )


def test_empty_scenario_aggregate_does_not_resolve_unused_candidate_root(
    tmp_path: Path,
) -> None:
    metrics = aggregate_scenarios(
        (),
        (),
        {},
        evidence_root=tmp_path,
        candidate_evidence_root=tmp_path / "missing-candidate-root",
    )

    assert metrics == {}


def test_no_cup_without_candidates_does_not_resolve_unused_candidate_root(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "no_cup")
    record = _record(truth, decision=DecisionOutput.NOT_FOUND)
    image_input = _metric_input(record, truth)

    metrics = aggregate_scenarios(
        (record,),
        (truth,),
        _keyed_matches((record,), (image_input,)),
        evidence_root=tmp_path,
        candidate_evidence_root=tmp_path / "missing-candidate-root",
    )["no_cup"]

    assert metrics.sample_count == 1
    assert metrics.error_count == 0
    assert metrics.no_cup_sample_count == 1
    assert metrics.no_cup_false_positive_count == 0
    assert metrics.no_cup_false_positive_rate == 0.0
    assert metrics.two_cup_sample_count == 0
    assert metrics.two_cup_both_matched_count == 0
    assert metrics.two_cup_both_matched_recall is None
    assert metrics.predicted_union_pixel_count == 0
    assert metrics.non_cup_leakage_pixel_count == 0
    assert metrics.non_cup_leakage_ratio == 0.0


def test_candidate_mask_read_rejects_missing_candidate_root(tmp_path: Path) -> None:
    truth = _truth(tmp_path, 0, "no_cup")
    candidate = _candidate(
        tmp_path,
        0,
        "candidate",
        0.9,
        _one_pixel_mask(),
    )
    record = _record(truth, (candidate,), decision=DecisionOutput.UNIQUE)
    image_input = _metric_input(record, truth)

    with pytest.raises(ValueError, match="candidate_evidence_root"):
        aggregate_scenarios(
            (record,),
            (truth,),
            _keyed_matches((record,), (image_input,)),
            evidence_root=tmp_path,
            candidate_evidence_root=tmp_path / "missing-candidate-root",
        )


def test_scenario_aggregate_rejects_distinct_indices_with_duplicate_image_sha(
    tmp_path: Path,
) -> None:
    duplicate_sha = "d" * 64
    truths = (
        _truth(tmp_path, 0, "synthetic", image_sha256=duplicate_sha),
        _truth(tmp_path, 1, "synthetic", image_sha256=duplicate_sha),
    )
    records = tuple(_record(truth) for truth in truths)
    inputs = tuple(
        _metric_input(record, truth)
        for record, truth in zip(records, truths, strict=True)
    )

    with pytest.raises(ValueError, match="image_sha256 values must be unique"):
        aggregate_scenarios(
            records,
            truths,
            _keyed_matches(records, inputs),
            evidence_root=tmp_path,
        )


def test_scenario_aggregate_rejects_foreign_sha_before_scoring_local_ids(
    tmp_path: Path,
) -> None:
    truth = _truth(tmp_path, 0, "synthetic", (_one_pixel_mask(),))
    candidate = _candidate(tmp_path, 0, "candidate", 0.9, _one_pixel_mask())
    record = _record(truth, (candidate,), decision=DecisionOutput.UNIQUE)
    image_input = _metric_input(
        record, truth, (MaskMatch("truth-0", "candidate", 1.0),)
    )

    with pytest.raises(ValueError, match="composite image identities"):
        aggregate_scenarios(
            (record,),
            (truth,),
            {(record.formal_sample_index, "f" * 64): image_input},
            evidence_root=tmp_path,
        )
