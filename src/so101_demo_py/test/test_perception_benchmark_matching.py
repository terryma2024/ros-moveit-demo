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
from so101_demo.perception_benchmark.contracts import MaskRef, RawCandidate, TruthInstance
from so101_demo.perception_benchmark.matching import (
    mask_dice,
    mask_iou,
    maximize_mask_iou_assignment,
)


def _write_mask(root: Path, name: str, pixels: list[list[int]]) -> MaskRef:
    mask = np.asarray(pixels, dtype=bool)
    relative_path = f"masks/{name}.json"
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


def _truth(root: Path, instance_id: str, pixels: list[list[int]]) -> TruthInstance:
    return TruthInstance(
        instance_id=instance_id,
        label="plastic_cup",
        mask=_write_mask(root, f"truth-{instance_id}", pixels),
    )


def _candidate(
    root: Path,
    candidate_id: str,
    score: float,
    pixels: list[list[int]],
) -> RawCandidate:
    mask = _write_mask(root, f"candidate-{candidate_id}", pixels)
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


def test_mask_iou_and_dice_use_hand_counted_binary_geometry() -> None:
    first = np.asarray([[1, 1], [0, 0]], dtype=bool)
    second = np.asarray([[1, 0], [1, 0]], dtype=bool)

    assert mask_iou(first, second) == pytest.approx(1.0 / 3.0)
    assert mask_dice(first, second) == pytest.approx(0.5)


def test_mask_geometry_rejects_non_2d_and_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="two-dimensional"):
        mask_iou(np.zeros(2, dtype=bool), np.zeros(2, dtype=bool))
    with pytest.raises(ValueError, match="same shape"):
        mask_dice(np.zeros((1, 2), dtype=bool), np.zeros((2, 1), dtype=bool))


def test_empty_masks_do_not_synthesize_perfect_overlap() -> None:
    empty = np.zeros((2, 3), dtype=bool)
    nonempty = np.asarray([[1, 0, 0], [0, 0, 0]], dtype=bool)

    assert mask_iou(empty, empty) == 0.0
    assert mask_dice(empty, empty) == 0.0
    assert mask_iou(empty, nonempty) == 0.0
    assert mask_dice(empty, nonempty) == 0.0


def test_rectangular_assignment_maximizes_total_iou(tmp_path: Path) -> None:
    truth = (
        _truth(tmp_path, "t2", [[0, 0, 0, 1]]),
        _truth(tmp_path, "t0", [[1, 1, 0, 0]]),
        _truth(tmp_path, "t1", [[1, 0, 0, 0]]),
    )
    candidates = (
        _candidate(tmp_path, "b", 0.8, [[0, 1, 0, 0]]),
        _candidate(tmp_path, "a", 0.9, [[1, 0, 0, 0]]),
    )

    matches = maximize_mask_iou_assignment(truth, candidates, tmp_path)

    assert [(match.truth_instance_id, match.candidate_id, match.iou) for match in matches] == [
        ("t0", "b", 0.5),
        ("t1", "a", 1.0),
    ]


def test_equal_iou_tie_uses_ranking_score_then_candidate_id(tmp_path: Path) -> None:
    truth = (_truth(tmp_path, "t0", [[1, 0], [0, 0]]),)
    candidates = (
        _candidate(tmp_path, "b", 0.9, [[1, 0], [0, 0]]),
        _candidate(tmp_path, "a", 0.9, [[1, 0], [0, 0]]),
        _candidate(tmp_path, "c", 0.8, [[1, 0], [0, 0]]),
    )

    assert maximize_mask_iou_assignment(truth, candidates, tmp_path)[0].candidate_id == "a"

    higher_score = (
        _candidate(tmp_path, "z", 0.95, [[1, 0], [0, 0]]),
        _candidate(tmp_path, "a2", 0.90, [[1, 0], [0, 0]]),
    )
    assert maximize_mask_iou_assignment(truth, higher_score, tmp_path)[0].candidate_id == "z"


def test_equal_cost_matrix_uses_sorted_truth_and_lower_candidate_column(tmp_path: Path) -> None:
    truth = (
        _truth(tmp_path, "t1", [[1, 0], [0, 0]]),
        _truth(tmp_path, "t0", [[1, 0], [0, 0]]),
    )
    candidates = (
        _candidate(tmp_path, "b", 0.9, [[1, 0], [0, 0]]),
        _candidate(tmp_path, "a", 0.9, [[1, 0], [0, 0]]),
    )

    matches = maximize_mask_iou_assignment(truth, candidates, tmp_path)

    assert [(match.truth_instance_id, match.candidate_id) for match in matches] == [
        ("t0", "a"),
        ("t1", "b"),
    ]


def test_residual_ties_are_refined_after_locking_the_highest_iou_edge(
    tmp_path: Path,
) -> None:
    truth = (
        _truth(tmp_path, "t1", [[0, 0, 0, 0]]),
        _truth(tmp_path, "t2", [[1, 0, 0, 0]]),
        _truth(tmp_path, "t0", [[0, 0, 0, 0]]),
    )
    candidates = (
        _candidate(tmp_path, "c", 0.9, [[0, 0, 0, 0]]),
        _candidate(tmp_path, "a", 0.9, [[1, 1, 1, 1]]),
        _candidate(tmp_path, "b", 0.9, [[0, 0, 0, 0]]),
    )

    matches = maximize_mask_iou_assignment(truth, candidates, tmp_path)

    assert [(match.truth_instance_id, match.candidate_id, match.iou) for match in matches] == [
        ("t0", "b", 0.0),
        ("t1", "c", 0.0),
        ("t2", "a", 0.25),
    ]


def test_equal_iou_and_confidence_prefers_smaller_candidate_id(tmp_path: Path) -> None:
    truth = (_truth(tmp_path, "t0", [[0, 0]]),)
    candidates = (
        _candidate(tmp_path, "b", 0.7, [[0, 0]]),
        _candidate(tmp_path, "a", 0.7, [[0, 0]]),
    )

    match = maximize_mask_iou_assignment(truth, candidates, tmp_path)[0]

    assert (match.truth_instance_id, match.candidate_id, match.iou) == ("t0", "a", 0.0)


def test_assignment_handles_either_empty_side_without_synthetic_matches(tmp_path: Path) -> None:
    truth = (_truth(tmp_path, "t0", [[1]]),)
    candidate = (_candidate(tmp_path, "a", 0.9, [[1]]),)

    assert maximize_mask_iou_assignment((), candidate, tmp_path) == ()
    assert maximize_mask_iou_assignment(truth, (), tmp_path) == ()
    assert maximize_mask_iou_assignment((), (), tmp_path) == ()


@pytest.mark.parametrize("field", ["sha256", "pixel_count", "image_width"])
def test_assignment_reads_masks_through_verified_codec(
    tmp_path: Path, field: str
) -> None:
    truth = _truth(tmp_path, "t0", [[1, 0], [0, 0]])
    candidate = _candidate(tmp_path, "a", 0.9, [[1, 0], [0, 0]])
    invalid_values: dict[str, object] = {
        "sha256": "f" * 64,
        "pixel_count": 2,
        "image_width": 3,
    }
    invalid_mask = replace(candidate.mask, **{field: invalid_values[field]})
    invalid_candidate = replace(
        candidate,
        mask=invalid_mask,
        bbox_xyxy=(0.0, 0.0, float(invalid_mask.image_width), 2.0),
    )

    with pytest.raises(ValueError, match=field.replace("image_width", "dimensions")):
        maximize_mask_iou_assignment((truth,), (invalid_candidate,), tmp_path)
