from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.comparison import compare_platforms
from so101_demo.perception_benchmark.contracts import (
    SCHEMA_VERSION,
    DecisionOutput,
    MaskRef,
    PhaseTimings,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RuntimeProvenance,
)


_LOCK_SHA = "a" * 64
_CONFIG_SHA = "b" * 64


def _mask(root: Path, name: str, pixels: list[list[int]]) -> MaskRef:
    value = np.asarray(pixels, dtype=bool)
    path = root / "masks" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(encode_mask_rle(value)))
    return MaskRef(
        relative_path=f"masks/{name}.json",
        sha256=sha256_bytes(value.astype(np.uint8).tobytes(order="C")),
        pixel_count=int(value.sum()),
        image_width=value.shape[1],
        image_height=value.shape[0],
    )


def _candidate(
    root: Path,
    candidate_id: str,
    score: float,
    pixels: list[list[int]],
    *,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> RawCandidate:
    return RawCandidate(
        candidate_id=candidate_id,
        label="plastic_cup",
        bbox_xyxy=bbox,
        mask=_mask(root, candidate_id, pixels),
        ranking_score=score,
        ranking_score_source="class_confidence",
        class_confidence=score,
        grounding_box_score=None,
        grounding_text_score=None,
        sam_quality=None,
    )


def _record(
    candidates: tuple[RawCandidate, ...],
    *,
    decision: DecisionOutput,
    platform: str,
    image_sha256: str = "1" * 64,
    model_id: str = "yolo_seg",
) -> PredictionRecord:
    selected = candidates[0].candidate_id if decision is DecisionOutput.UNIQUE else None
    rejection = {
        DecisionOutput.NOT_FOUND: "TARGET_NOT_FOUND",
        DecisionOutput.AMBIGUOUS: "TARGET_AMBIGUOUS",
    }.get(decision)
    return PredictionRecord(
        run_id=f"{platform}-run",
        schema_version=SCHEMA_VERSION,
        run_kind=RunKind.TEST_RAW_FROZEN,
        record_status=RecordStatus.OK,
        formal_sample_index=0,
        split="test",
        scenario="one_cup",
        image_relpath="images/000.png",
        image_sha256=image_sha256,
        image_width=2,
        image_height=2,
        model_id=model_id,
        runtime_provenance=RuntimeProvenance(
            runtime_device="mps" if platform == "macos" else "cuda",
            runtime_name="test-runtime",
            runtime_version="1",
            weights_sha256="c" * 64,
            environment={"platform": platform},
        ),
        config_sha256=_CONFIG_SHA,
        threshold_lock_sha256=_LOCK_SHA,
        raw_candidates=candidates,
        phase_timings=PhaseTimings(),
        raw_count=len(candidates),
        decision=decision,
        selected_candidate_id=selected,
        rejection_reason=rejection,
        error_type=None,
        error_summary=None,
        timed_out=False,
        oom=False,
        fallback_used=False,
    )


def test_cross_platform_report_uses_two_mask_roots_and_lists_every_mismatch(
    tmp_path: Path,
) -> None:
    mac_root = tmp_path / "mac"
    linux_root = tmp_path / "linux"
    mac = _record(
        (
            _candidate(
                mac_root,
                "candidate-b",
                0.800000000001,
                [[1, 1], [0, 0]],
                bbox=(0.0, 0.0, 2.0, 1.0),
            ),
        ),
        decision=DecisionOutput.UNIQUE,
        platform="macos",
    )
    linux = _record(
        (
            _candidate(
                linux_root,
                "candidate-a",
                0.8,
                [[1, 0], [1, 0]],
                bbox=(0.0, 0.0, 1.0, 2.0),
            ),
            _candidate(
                linux_root,
                "candidate-c",
                0.3,
                [[0, 0], [0, 1]],
            ),
        ),
        decision=DecisionOutput.AMBIGUOUS,
        platform="linux",
    )

    result = compare_platforms(
        (mac,),
        (linux,),
        mac_evidence_root=mac_root,
        linux_evidence_root=linux_root,
    )

    assert result.mismatch_image_shas == ("1" * 64,)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.candidate_count_equal is False
    assert item.decision_equal is False
    assert item.error_type_equal is True
    assert item.mac_candidate_ids == ("candidate-b",)
    assert item.linux_candidate_ids == ("candidate-a", "candidate-c")
    assert item.candidate_pairs[0].mask_iou == pytest.approx(1.0 / 3.0)
    assert item.candidate_pairs[0].box_iou == pytest.approx(1.0 / 3.0)
    assert item.candidate_pairs[0].confidence_absolute_delta > 0.0
    assert item.is_mismatch is True


def test_cross_platform_requires_roots_only_when_candidates_are_present() -> None:
    mac = _record((), decision=DecisionOutput.NOT_FOUND, platform="macos")
    linux = _record((), decision=DecisionOutput.NOT_FOUND, platform="linux")

    result = compare_platforms((mac,), (linux,))

    assert result.mismatch_image_shas == ()
    assert result.items[0].candidate_pairs == ()
    assert result.items[0].is_mismatch is False


def test_cross_platform_rejects_missing_mask_root_for_candidate_records(
    tmp_path: Path,
) -> None:
    mac_root = tmp_path / "mac"
    linux_root = tmp_path / "linux"
    candidate = _candidate(mac_root, "candidate", 0.8, [[1, 0], [0, 0]])
    mac = _record((candidate,), decision=DecisionOutput.UNIQUE, platform="macos")
    linux_candidate = _candidate(
        linux_root, "candidate", 0.8, [[1, 0], [0, 0]]
    )
    linux = _record(
        (linux_candidate,), decision=DecisionOutput.UNIQUE, platform="linux"
    )

    with pytest.raises(ValueError, match="mac_evidence_root"):
        compare_platforms(
            (mac,),
            (linux,),
            linux_evidence_root=linux_root,
        )


def test_cross_platform_does_not_suppress_nonzero_float_deltas(
    tmp_path: Path,
) -> None:
    mac_root = tmp_path / "mac"
    linux_root = tmp_path / "linux"
    pixels = [[1, 0], [0, 0]]
    mac = _record(
        (_candidate(mac_root, "candidate", 0.800000000001, pixels),),
        decision=DecisionOutput.UNIQUE,
        platform="macos",
    )
    linux = _record(
        (_candidate(linux_root, "candidate", 0.8, pixels),),
        decision=DecisionOutput.UNIQUE,
        platform="linux",
    )

    result = compare_platforms(
        (mac,),
        (linux,),
        mac_evidence_root=mac_root,
        linux_evidence_root=linux_root,
    )

    assert result.mismatch_image_shas == ("1" * 64,)
    assert result.items[0].candidate_pairs[0].confidence_absolute_delta > 0.0


def test_cross_platform_compares_every_grounded_sam_score(tmp_path: Path) -> None:
    mac_root = tmp_path / "mac"
    linux_root = tmp_path / "linux"
    pixels = [[1, 0], [0, 0]]

    def grounded_candidate(root: Path, text_score: float) -> RawCandidate:
        return RawCandidate(
            candidate_id="candidate",
            label="plastic_cup",
            bbox_xyxy=(0.0, 0.0, 1.0, 1.0),
            mask=_mask(root, "candidate", pixels),
            ranking_score=0.8,
            ranking_score_source="grounding_box_score",
            class_confidence=None,
            grounding_box_score=0.8,
            grounding_text_score=text_score,
            sam_quality=0.9,
        )

    mac = _record(
        (grounded_candidate(mac_root, 0.7),),
        decision=DecisionOutput.UNIQUE,
        platform="macos",
        model_id="grounded-sam-v1",
    )
    linux = _record(
        (grounded_candidate(linux_root, 0.6),),
        decision=DecisionOutput.UNIQUE,
        platform="linux",
        model_id="grounded-sam-v1",
    )

    result = compare_platforms(
        (mac,),
        (linux,),
        mac_evidence_root=mac_root,
        linux_evidence_root=linux_root,
    )

    pair = result.items[0].candidate_pairs[0]
    assert pair.ranking_score_source_equal is True
    assert pair.ranking_score_absolute_delta == 0.0
    assert pair.grounding_text_score_absolute_delta == pytest.approx(0.1)
    assert pair.grounding_text_score_relative_delta == pytest.approx(1 / 6)
    assert pair.class_confidence_presence_equal is True
    assert pair.class_confidence_absolute_delta is None
    assert pair.grounding_box_score_absolute_delta == 0.0
    assert pair.sam_quality_absolute_delta == 0.0
    assert result.mismatch_image_shas == ("1" * 64,)


def test_cross_platform_reports_explicit_runtime_identity_projection() -> None:
    mac = _record((), decision=DecisionOutput.NOT_FOUND, platform="macos")
    linux = _record((), decision=DecisionOutput.NOT_FOUND, platform="linux")

    result = compare_platforms((mac,), (linux,))
    item = result.items[0]

    assert item.runtime_device_pair_expected is True
    assert item.weights_sha256_equal is True
    assert item.runtime_name_equal is True
    assert item.runtime_version_equal is True
    assert item.runtime_environment_equal is False
    assert item.runtime_environment_identity_equal is True
    assert item.mac_runtime_environment == {"platform": "macos"}
    assert item.linux_runtime_environment == {"platform": "linux"}
    assert item.is_mismatch is False


def test_cross_platform_lists_stable_runtime_environment_drift() -> None:
    mac = _record((), decision=DecisionOutput.NOT_FOUND, platform="macos")
    linux = _record((), decision=DecisionOutput.NOT_FOUND, platform="linux")
    mac = replace(
        mac,
        runtime_provenance=replace(
            mac.runtime_provenance,
            environment={"platform": "macos", "dependency_lock": "v1"},
        ),
    )
    linux = replace(
        linux,
        runtime_provenance=replace(
            linux.runtime_provenance,
            environment={"platform": "linux", "dependency_lock": "v2"},
        ),
    )

    result = compare_platforms((mac,), (linux,))
    item = result.items[0]

    assert item.runtime_environment_equal is False
    assert item.runtime_environment_identity_equal is False
    assert item.is_mismatch is True
    assert result.mismatch_image_shas == ("1" * 64,)
