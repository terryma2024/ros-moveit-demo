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


def _truth(
    root: Path,
    instance_id: str,
    pixels: list[list[int]],
    *,
    directory: str = "masks",
) -> TruthInstance:
    return TruthInstance(
        instance_id=instance_id,
        label="plastic_cup",
        mask=_write_mask(
            root, f"truth-{instance_id}", pixels, directory=directory
        ),
    )


def _candidate(
    root: Path,
    candidate_id: str,
    score: float,
    pixels: list[list[int]],
    *,
    directory: str = "masks",
) -> RawCandidate:
    mask = _write_mask(
        root, f"candidate-{candidate_id}", pixels, directory=directory
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


def test_assignment_supports_separate_roots_without_changing_tie_order(
    tmp_path: Path,
) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    truth = (
        _truth(
            truth_root,
            "t1",
            [[1, 0], [0, 0]],
            directory="truth_masks",
        ),
        _truth(
            truth_root,
            "t0",
            [[1, 0], [0, 0]],
            directory="truth_masks",
        ),
    )
    candidates = (
        _candidate(candidate_root, "b", 0.9, [[1, 0], [0, 0]]),
        _candidate(candidate_root, "z", 0.95, [[1, 0], [0, 0]]),
        _candidate(candidate_root, "a", 0.9, [[1, 0], [0, 0]]),
    )

    matches = maximize_mask_iou_assignment(
        truth,
        candidates,
        truth_root,
        candidate_evidence_root=candidate_root,
    )

    assert [
        (match.truth_instance_id, match.candidate_id, match.iou)
        for match in matches
    ] == [
        ("t0", "z", 1.0),
        ("t1", "a", 1.0),
    ]


@pytest.mark.parametrize("invalid_side", ["truth", "candidate"])
def test_assignment_verifies_sha_on_each_separate_root(
    tmp_path: Path,
    invalid_side: str,
) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    truth = _truth(
        truth_root,
        "t0",
        [[1, 0], [0, 0]],
        directory="truth_masks",
    )
    candidate = _candidate(
        candidate_root,
        "c0",
        0.9,
        [[1, 0], [0, 0]],
    )
    if invalid_side == "truth":
        truth = replace(truth, mask=replace(truth.mask, sha256="f" * 64))
    else:
        candidate = replace(
            candidate,
            mask=replace(candidate.mask, sha256="f" * 64),
        )

    with pytest.raises(ValueError, match="sha256"):
        maximize_mask_iou_assignment(
            (truth,),
            (candidate,),
            truth_root,
            candidate_evidence_root=candidate_root,
        )


@pytest.mark.parametrize("escaped_side", ["truth", "candidate"])
def test_assignment_rejects_symlink_escape_from_each_separate_root(
    tmp_path: Path,
    escaped_side: str,
) -> None:
    truth_root = tmp_path / "truth-root"
    candidate_root = tmp_path / "candidate-root"
    truth_root.mkdir()
    candidate_root.mkdir()
    outside_root = tmp_path / f"outside-{escaped_side}"

    if escaped_side == "truth":
        truth = _truth(
            outside_root,
            "t0",
            [[1, 0], [0, 0]],
            directory="truth_masks",
        )
        (truth_root / "truth_masks").symlink_to(
            outside_root / "truth_masks",
            target_is_directory=True,
        )
        candidate = _candidate(
            candidate_root,
            "c0",
            0.9,
            [[1, 0], [0, 0]],
        )
    else:
        truth = _truth(
            truth_root,
            "t0",
            [[1, 0], [0, 0]],
            directory="truth_masks",
        )
        candidate = _candidate(
            outside_root,
            "c0",
            0.9,
            [[1, 0], [0, 0]],
        )
        (candidate_root / "masks").symlink_to(
            outside_root / "masks",
            target_is_directory=True,
        )

    with pytest.raises(ValueError, match="escapes evidence_root"):
        maximize_mask_iou_assignment(
            (truth,),
            (candidate,),
            truth_root,
            candidate_evidence_root=candidate_root,
        )
