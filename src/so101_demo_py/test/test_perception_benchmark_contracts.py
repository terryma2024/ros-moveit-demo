from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    MaskRef,
    PhaseTimings,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RuntimeProvenance,
)


def _sha256() -> str:
    return "a" * 64


def _mask_ref(**overrides: object) -> MaskRef:
    values: dict[str, object] = {
        "relative_path": "masks/cup-0.json",
        "sha256": _sha256(),
        "pixel_count": 6,
        "image_width": 6,
        "image_height": 4,
    }
    values.update(overrides)
    return MaskRef(**values)  # type: ignore[arg-type]


def raw_candidate(**overrides: object) -> RawCandidate:
    values: dict[str, object] = {
        "candidate_id": "cup-0",
        "label": "plastic_cup",
        "bbox_xyxy": (2.0, 1.0, 5.0, 3.0),
        "mask": _mask_ref(),
        "ranking_score": 0.9,
        "ranking_score_source": "grounding_box_score",
        "class_confidence": 0.8,
        "grounding_box_score": 0.9,
        "grounding_text_score": 0.7,
        "sam_quality": 0.6,
    }
    values.update(overrides)
    return RawCandidate(**values)  # type: ignore[arg-type]


def _provenance(**overrides: object) -> RuntimeProvenance:
    values: dict[str, object] = {
        "runtime_device": "cuda",
        "runtime_name": "grounded-sam",
        "runtime_version": "1.0.0",
        "weights_sha256": _sha256(),
    }
    values.update(overrides)
    return RuntimeProvenance(**values)  # type: ignore[arg-type]


def prediction_record(**overrides: object) -> PredictionRecord:
    values: dict[str, object] = {
        "run_id": "run-001",
        "schema_version": "so101-perception-benchmark/v1",
        "run_kind": RunKind.VAL_RAW,
        "record_status": RecordStatus.OK,
        "formal_sample_index": 17,
        "split": "val",
        "scenario": "single-cup",
        "image_relpath": "images/sample-017.png",
        "image_sha256": _sha256(),
        "model_id": "grounded-sam-v1",
        "runtime_provenance": _provenance(),
        "config_sha256": _sha256(),
        "threshold_lock_sha256": _sha256(),
        "raw_candidates": (raw_candidate(),),
        "phase_timings": PhaseTimings(sam_ms=1.5, selector_ms=0.0),
        "raw_count": 1,
        "decision": DecisionOutput.SELECTED,
        "selected_candidate_id": "cup-0",
        "rejection_reason": None,
        "error_type": None,
        "error_summary": None,
        "timed_out": False,
        "oom": False,
        "fallback_used": False,
    }
    values.update(overrides)
    return PredictionRecord(**values)  # type: ignore[arg-type]


def test_prediction_record_preserves_null_phase_and_rejects_nonfinite_score() -> None:
    record = prediction_record(
        phase_timings=PhaseTimings(sam_ms=None, selector_ms=0.0)
    )

    assert record.phase_timings.sam_ms is None
    assert record.phase_timings.selector_ms == 0.0
    with pytest.raises(ValueError, match="ranking_score"):
        raw_candidate(ranking_score=float("nan"))


def test_error_record_is_in_denominator_and_has_no_selected_candidate() -> None:
    record = prediction_record(
        record_status=RecordStatus.ERROR,
        decision=DecisionOutput.ERROR,
        error_type="INFERENCE_FAILED",
        selected_candidate_id=None,
        raw_candidates=(),
        raw_count=0,
    )

    assert record.formal_sample_index == 17
    assert record.error_type == "INFERENCE_FAILED"


def test_record_owns_tuple_input_and_rejects_duplicate_candidate_ids() -> None:
    candidates = [raw_candidate()]
    record = prediction_record(raw_candidates=candidates)
    candidates.append(raw_candidate(candidate_id="cup-1"))

    assert record.raw_candidates == (raw_candidate(),)
    with pytest.raises(ValueError, match="candidate_id"):
        prediction_record(
            raw_candidates=(raw_candidate(), raw_candidate()), raw_count=2
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"relative_path": "../escape.json"}, "relative_path"),
        ({"image_width": 0}, "image dimensions"),
        ({"sha256": "A" * 64}, "sha256"),
    ],
)
def test_mask_ref_rejects_unsafe_or_invalid_metadata(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _mask_ref(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"runtime_device": "cpu"}, "runtime_device"),
        ({"runtime_version": ""}, "runtime_version"),
        ({"weights_sha256": "z" * 64}, "weights_sha256"),
    ],
)
def test_runtime_provenance_rejects_cpu_and_incomplete_values(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _provenance(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"fallback_used": True}, "fallback_used"),
        ({"raw_count": 2}, "raw_count"),
        ({"selected_candidate_id": "missing"}, "selected_candidate_id"),
        ({"run_kind": RunKind.TEST_RAW_FROZEN, "threshold_lock_sha256": None}, "threshold_lock_sha256"),
    ],
)
def test_prediction_record_rejects_inconsistent_or_nonformal_values(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        prediction_record(**overrides)


def test_phase_timings_reject_nonfinite_latency() -> None:
    with pytest.raises(ValueError, match="sam_ms"):
        PhaseTimings(sam_ms=float("inf"))


def test_prediction_record_is_frozen() -> None:
    record = prediction_record()

    with pytest.raises(FrozenInstanceError):
        record.model_id = "changed"  # type: ignore[misc]
