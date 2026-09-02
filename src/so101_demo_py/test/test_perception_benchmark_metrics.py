from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    GROUNDED_SAM_MODEL_ID,
    MaskRef,
    PhaseTimings,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RuntimeProvenance,
    TruthInstance,
    TruthSample,
    YOLO_MODEL_ID,
)
from so101_demo.perception_benchmark.matching import MaskMatch
from so101_demo.perception_benchmark.metrics import (
    ImageMetricInput,
    bootstrap_image_metrics,
    bootstrap_paired_image_metrics,
    compute_ap,
    compute_image_metrics,
    interpolated_ap,
    summarize_image_metrics,
)


def _write_mask(
    root: Path,
    name: str,
    pixels: list[list[int]],
    *,
    directory: str = "masks",
) -> MaskRef:
    mask = np.asarray(pixels, dtype=bool)
    relative_path = f"{directory}/{name}.json"
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


def _truth_sample(
    root: Path,
    sample_index: int,
    masks: tuple[list[list[int]], ...],
    *,
    mask_directory: str = "masks",
) -> TruthSample:
    instances = tuple(
        TruthInstance(
            instance_id=f"t{position}",
            label="plastic_cup",
            mask=_write_mask(
                root,
                f"truth-{sample_index}-{position}",
                pixels,
                directory=mask_directory,
            ),
        )
        for position, pixels in enumerate(masks)
    )
    height = len(masks[0]) if masks else 2
    width = len(masks[0][0]) if masks else 2
    return TruthSample(
        formal_sample_index=sample_index,
        split="val",
        scenario="synthetic",
        image_relpath=f"images/{sample_index}.png",
        image_sha256=f"{sample_index + 1:064x}",
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
    *,
    grounded_sam: bool = False,
    sam_quality: float | None = None,
) -> RawCandidate:
    mask = _write_mask(root, f"candidate-{sample_index}-{candidate_id}", pixels)
    if grounded_sam:
        return RawCandidate(
            candidate_id=candidate_id,
            label="plastic_cup",
            bbox_xyxy=(0.0, 0.0, float(mask.image_width), float(mask.image_height)),
            mask=mask,
            ranking_score=score,
            ranking_score_source="grounding_box_score",
            class_confidence=None,
            grounding_box_score=score,
            grounding_text_score=0.5,
            sam_quality=sam_quality,
        )
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
    sample: TruthSample,
    candidates: tuple[RawCandidate, ...],
    *,
    status: RecordStatus = RecordStatus.OK,
    grounded_sam: bool = False,
) -> PredictionRecord:
    is_error = status is RecordStatus.ERROR
    model_id = GROUNDED_SAM_MODEL_ID if grounded_sam else YOLO_MODEL_ID
    return PredictionRecord(
        run_id="run-001",
        schema_version="so101-perception-benchmark/v1",
        run_kind=RunKind.VAL_RAW,
        record_status=status,
        formal_sample_index=sample.formal_sample_index,
        split=sample.split,
        scenario=sample.scenario,
        image_relpath=sample.image_relpath,
        image_sha256=sample.image_sha256,
        image_width=sample.image_width,
        image_height=sample.image_height,
        model_id=model_id,
        runtime_provenance=RuntimeProvenance(
            runtime_device="mps",
            runtime_name=model_id,
            runtime_version="1.0",
            weights_sha256="a" * 64,
        ),
        config_sha256="b" * 64,
        threshold_lock_sha256=None,
        raw_candidates=() if is_error else candidates,
        phase_timings=PhaseTimings(),
        raw_count=0 if is_error else len(candidates),
        decision=DecisionOutput.ERROR if is_error else DecisionOutput.NOT_FOUND,
        selected_candidate_id=None,
        rejection_reason=None if is_error else "TARGET_NOT_FOUND",
        error_type="INFERENCE_FAILED" if is_error else None,
        error_summary=None,
        timed_out=is_error,
        oom=False,
        fallback_used=False,
    )


def test_empty_truth_empty_prediction_has_no_synthetic_iou(tmp_path: Path) -> None:
    summary = compute_image_metrics((), (), tmp_path, iou_threshold=0.50)

    assert summary.tp == summary.fp == summary.fn == 0
    assert summary.precision is None
    assert summary.recall is None
    assert summary.mean_iou is None
    assert summary.mean_dice is None


def test_one_empty_side_uses_null_zero_denominator_semantics(tmp_path: Path) -> None:
    truth = _truth_sample(tmp_path, 0, ([[1, 0], [0, 0]],)).instances
    candidate = (
        _candidate(tmp_path, 0, "c0", 0.9, [[1, 0], [0, 0]]),
    )

    missing_prediction = compute_image_metrics(truth, (), tmp_path, iou_threshold=0.50)
    missing_truth = compute_image_metrics((), candidate, tmp_path, iou_threshold=0.50)

    assert (missing_prediction.tp, missing_prediction.fp, missing_prediction.fn) == (0, 0, 1)
    assert missing_prediction.precision is None
    assert missing_prediction.recall == 0.0
    assert (missing_truth.tp, missing_truth.fp, missing_truth.fn) == (0, 1, 0)
    assert missing_truth.precision == 0.0
    assert missing_truth.recall is None


def test_image_metrics_supports_separate_truth_and_candidate_roots(
    tmp_path: Path,
) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    truth = _truth_sample(
        truth_root,
        0,
        ([[1, 0], [0, 0]],),
        mask_directory="truth_masks",
    ).instances
    candidates = (
        _candidate(candidate_root, 0, "tp", 0.9, [[1, 0], [0, 0]]),
        _candidate(candidate_root, 0, "fp", 0.8, [[0, 0], [0, 1]]),
    )

    summary = compute_image_metrics(
        truth,
        candidates,
        truth_root,
        iou_threshold=0.50,
        candidate_evidence_root=candidate_root,
    )

    assert (summary.tp, summary.fp, summary.fn) == (1, 1, 0)
    assert summary.precision == 0.5
    assert summary.recall == 1.0


def test_thresholded_summary_uses_only_qualified_matches() -> None:
    samples = (
        ImageMetricInput(
            formal_sample_index=0,
            truth_count=2,
            candidate_count=3,
            matches=(
                MaskMatch("t0", "c0", 0.75),
                MaskMatch("t1", "c1", 0.49),
            ),
        ),
    )

    summary = summarize_image_metrics(samples, iou_threshold=0.50)

    assert (summary.tp, summary.fp, summary.fn) == (1, 2, 1)
    assert summary.precision == pytest.approx(1.0 / 3.0)
    assert summary.recall == pytest.approx(0.5)
    assert summary.mean_iou == pytest.approx(0.75)
    assert summary.mean_dice == pytest.approx(6.0 / 7.0)


def test_interpolated_ap_uses_101_recall_levels() -> None:
    recall = np.asarray([0.5, 0.5, 1.0])
    precision = np.asarray([1.0, 0.5, 2.0 / 3.0])

    assert interpolated_ap(recall, precision) == pytest.approx(0.8349834983498351)
    assert interpolated_ap(np.asarray([]), np.asarray([])) is None


def test_ap_ranks_globally_and_rematches_each_image_prefix(tmp_path: Path) -> None:
    first = _truth_sample(tmp_path, 0, ([[1, 0], [0, 0]],))
    second = _truth_sample(tmp_path, 1, ([[1, 0], [0, 0]],))
    records = (
        _record(first, (_candidate(tmp_path, 0, "tp0", 0.9, [[1, 0], [0, 0]]),)),
        _record(
            second,
            (
                _candidate(tmp_path, 1, "fp", 0.8, [[0, 0], [0, 1]]),
                _candidate(tmp_path, 1, "tp1", 0.7, [[1, 0], [0, 0]]),
            ),
        ),
    )

    summary = compute_ap(records, (first, second), tmp_path, (0.50,))

    assert summary.mask_ap50 == pytest.approx(0.8349834983498351)
    assert summary.mask_ap75 is None
    assert summary.mask_map == pytest.approx(0.8349834983498351)
    assert summary.by_iou_threshold == ((0.5, pytest.approx(0.8349834983498351)),)


def test_ap_supports_separate_truth_and_candidate_roots(tmp_path: Path) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    sample = _truth_sample(
        truth_root,
        0,
        ([[1, 0], [0, 0]],),
        mask_directory="truth_masks",
    )
    record = _record(
        sample,
        (_candidate(candidate_root, 0, "tp", 0.9, [[1, 0], [0, 0]]),),
    )

    summary = compute_ap(
        (record,),
        (sample,),
        truth_root,
        (0.50, 0.75),
        candidate_evidence_root=candidate_root,
    )

    assert summary.mask_ap50 == 1.0
    assert summary.mask_ap75 == 1.0
    assert summary.mask_map == 1.0


def test_ap_threshold_matching_keeps_true_positive_count_monotonic(tmp_path: Path) -> None:
    sample = _truth_sample(
        tmp_path,
        0,
        (
            [[1, 1, 1, 0, 1, 1, 0, 0, 0, 0]],
            [[1, 1, 0, 0, 1, 1, 0, 0, 1, 1]],
        ),
    )
    candidates = (
        _candidate(
            tmp_path, 0, "c0", 0.9, [[1, 1, 1, 0, 1, 0, 0, 0, 1, 0]]
        ),
        _candidate(
            tmp_path, 0, "c1", 0.8, [[0, 1, 1, 1, 1, 0, 0, 0, 0, 0]]
        ),
        _candidate(
            tmp_path, 0, "c2", 0.7, [[0, 1, 0, 0, 0, 0, 1, 0, 1, 1]]
        ),
    )

    summary = compute_ap((_record(sample, candidates),), (sample,), tmp_path, (0.50,))

    assert summary.mask_ap50 == 1.0


def test_ap_uses_frozen_ranking_score_not_sam_quality(tmp_path: Path) -> None:
    first = _truth_sample(tmp_path, 0, ([[1, 0], [0, 0]],))
    second = _truth_sample(tmp_path, 1, ([[1, 0], [0, 0]],))
    records = (
        _record(
            first,
            (
                _candidate(
                    tmp_path,
                    0,
                    "high-rank",
                    0.9,
                    [[1, 0], [0, 0]],
                    grounded_sam=True,
                    sam_quality=0.1,
                ),
            ),
            grounded_sam=True,
        ),
        _record(
            second,
            (
                _candidate(
                    tmp_path,
                    1,
                    "low-rank",
                    0.8,
                    [[0, 0], [0, 1]],
                    grounded_sam=True,
                    sam_quality=0.9,
                ),
            ),
            grounded_sam=True,
        ),
    )

    summary = compute_ap(records, (first, second), tmp_path, (0.50,))

    assert summary.mask_ap50 == 0.504950495049505


def test_error_record_keeps_truth_in_ap_denominator(tmp_path: Path) -> None:
    first = _truth_sample(tmp_path, 0, ([[1, 0], [0, 0]],))
    second = _truth_sample(tmp_path, 1, ([[1, 0], [0, 0]],))
    records = (
        _record(first, (_candidate(tmp_path, 0, "tp", 0.9, [[1, 0], [0, 0]]),)),
        _record(second, (), status=RecordStatus.ERROR),
    )

    summary = compute_ap(records, (first, second), tmp_path, (0.50,))

    assert summary.mask_ap50 == pytest.approx(51.0 / 101.0)


def test_ap_with_no_prediction_has_null_precision_and_ap(tmp_path: Path) -> None:
    sample = _truth_sample(tmp_path, 0, ([[1, 0], [0, 0]],))

    summary = compute_ap((_record(sample, ()),), (sample,), tmp_path, (0.50, 0.75))

    assert summary.mask_ap50 is None
    assert summary.mask_ap75 is None
    assert summary.mask_map is None


def _bootstrap_samples(values: tuple[int, ...]) -> tuple[ImageMetricInput, ...]:
    return tuple(
        ImageMetricInput(
            formal_sample_index=index,
            truth_count=value,
            candidate_count=0,
            matches=(),
        )
        for index, value in enumerate(values)
    )


def _mean_truth_count(samples: tuple[ImageMetricInput, ...]) -> float:
    return float(np.mean([sample.truth_count for sample in samples]))


def test_image_bootstrap_has_frozen_seed_and_deterministic_sha() -> None:
    samples = _bootstrap_samples((0, 1, 4))

    first = bootstrap_image_metrics(
        samples, _mean_truth_count, seed=20260902, repetitions=10
    )
    second = bootstrap_image_metrics(
        samples, _mean_truth_count, seed=20260902, repetitions=10
    )
    first_sha = hashlib.sha256(
        json.dumps(asdict(first), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    second_sha = hashlib.sha256(
        json.dumps(asdict(second), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert first.lower == pytest.approx(2.0 / 3.0)
    assert first.upper == pytest.approx(2.775)
    assert first_sha == second_sha


def test_paired_bootstrap_reuses_each_image_index_vector() -> None:
    first = _bootstrap_samples((0, 10, 40))
    second = _bootstrap_samples((0, 1, 4))

    interval = bootstrap_paired_image_metrics(
        first,
        second,
        _mean_truth_count,
        seed=20260902,
        repetitions=10,
    )

    assert interval.lower == pytest.approx(6.0)
    assert interval.upper == pytest.approx(24.975)


def test_bootstrap_empty_and_nonfinite_behavior_is_explicit() -> None:
    assert bootstrap_image_metrics((), _mean_truth_count).lower is None
    assert bootstrap_image_metrics((), _mean_truth_count).upper is None
    with pytest.raises(ValueError, match="finite"):
        bootstrap_image_metrics(
            _bootstrap_samples((1,)),
            lambda _samples: float("nan"),
            repetitions=1,
        )
    with pytest.raises(ValueError, match="paired"):
        bootstrap_paired_image_metrics(
            _bootstrap_samples((1,)),
            _bootstrap_samples((1, 2)),
            _mean_truth_count,
        )
