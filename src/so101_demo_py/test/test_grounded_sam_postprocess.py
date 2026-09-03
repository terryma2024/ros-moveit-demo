from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from so101_demo.adapters.perception.grounded_sam_postprocess import (
    GroundedSamResultError,
    GroundedSamThresholds,
    GroundingProposal,
    convert_grounding_results,
    convert_sam_results,
    prompt_for_query,
)
from so101_demo.core.detection import DetectionFrame, DetectionQuery


def _frame(width: int = 160, height: int = 120) -> DetectionFrame:
    return DetectionFrame(
        np.zeros((height, width, 3), dtype=np.uint8),
        source_stamp_ns=7,
        source_frame_id="task_camera_frame",
    )


def _thresholds(**overrides: object) -> GroundedSamThresholds:
    return replace(GroundedSamThresholds.defaults(), **overrides)


def _masks_for_one_object() -> np.ndarray:
    masks = np.zeros((1, 3, 120, 160), dtype=bool)
    masks[0, 0, 10:70, 10:50] = True
    masks[0, 1, 10:70, 10:50] = True
    masks[0, 2, 10:70, 10:50] = True
    return masks


def _error_code(action: object) -> str:
    with pytest.raises(GroundedSamResultError) as caught:
        action()  # type: ignore[operator]
    return caught.value.code


def test_prompt_is_fixed_for_the_whitelisted_query() -> None:
    """Catch routing the one supported query to a prompt other than Grounding DINO's literal."""

    assert prompt_for_query(DetectionQuery("plastic_cup")) == "plastic cup."


def test_prompt_rejects_a_bypassed_unknown_query_before_any_model_boundary() -> None:
    """Catch accepting a query object that bypassed DetectionQuery's constructor whitelist."""

    unknown = object.__new__(DetectionQuery)
    object.__setattr__(unknown, "class_id", "coffee_mug")

    assert _error_code(lambda: prompt_for_query(unknown)) == "UNSUPPORTED_DETECTION_QUERY"


def test_threshold_defaults_are_the_fixed_grounded_sam_profile() -> None:
    """Catch constructing a pipeline whose deployed score or mask gates differ from the profile."""

    assert GroundedSamThresholds.defaults() == GroundedSamThresholds(
        box_threshold=0.35,
        text_threshold=0.25,
        duplicate_iou=0.85,
        max_candidates=16,
        sam_quality=0.75,
        min_mask_pixels=64,
        max_mask_area_ratio=0.50,
    )


def test_grounding_conversion_clips_sorts_and_deduplicates() -> None:
    """Catch retaining an inferior overlapping box or emitting out-of-frame coordinates."""

    proposals = convert_grounding_results(
        boxes=np.array(
            [[-1.0, 10.0, 31.0, 50.0], [0.0, 10.0, 30.0, 50.0], [80.0, 10.0, 120.0, 50.0]]
        ),
        scores=np.array([0.80, 0.90, 0.70]),
        labels=["plastic cup", "plastic cup", "plastic cup"],
        frame=_frame(),
        query=DetectionQuery("plastic_cup"),
        thresholds=_thresholds(duplicate_iou=0.85),
    )

    assert [(proposal.confidence, proposal.bbox_xyxy) for proposal in proposals] == [
        (0.90, (0.0, 10.0, 30.0, 50.0)),
        (0.70, (80.0, 10.0, 120.0, 50.0)),
    ]


def test_grounding_keeps_two_separate_cups_and_breaks_equal_scores_by_box() -> None:
    """Catch IoU suppression that merges distinct instances or input-order-dependent output."""

    proposals = convert_grounding_results(
        boxes=np.array([[90.0, 20.0, 130.0, 80.0], [10.0, 20.0, 50.0, 80.0]]),
        scores=np.array([0.80, 0.80]),
        labels=["plastic cup", "plastic cup"],
        frame=_frame(),
        query=DetectionQuery("plastic_cup"),
        thresholds=_thresholds(),
    )

    assert [proposal.bbox_xyxy for proposal in proposals] == [
        (10.0, 20.0, 50.0, 80.0),
        (90.0, 20.0, 130.0, 80.0),
    ]


def test_grounding_suppresses_a_duplicate_at_the_exact_iou_threshold() -> None:
    """Catch retaining a second box when its 34/40 IoU equals the configured 0.85 limit."""

    proposals = convert_grounding_results(
        boxes=np.array([[0.0, 0.0, 37.0, 1.0], [3.0, 0.0, 40.0, 1.0]]),
        scores=np.array([0.90, 0.80]),
        labels=["plastic cup", "plastic cup"],
        frame=_frame(),
        query=DetectionQuery("plastic_cup"),
        thresholds=_thresholds(duplicate_iou=0.85),
    )

    assert [(proposal.confidence, proposal.bbox_xyxy) for proposal in proposals] == [
        (0.90, (0.0, 0.0, 37.0, 1.0)),
    ]


def test_grounding_keeps_prompt_equivalent_labels_but_rejects_other_phrases() -> None:
    """Catch display punctuation changing the one fixed prompt's semantic identity."""

    proposals = convert_grounding_results(
        boxes=np.array(
            [[10.0, 10.0, 40.0, 50.0], [60.0, 10.0, 90.0, 50.0], [110.0, 10.0, 140.0, 50.0]]
        ),
        scores=np.array([0.91, 0.82, 0.73]),
        labels=["plastic cup", "coffee cup", "plastic cup."],
        frame=_frame(),
        query=DetectionQuery("plastic_cup"),
        thresholds=_thresholds(max_candidates=16),
    )

    assert [(proposal.confidence, proposal.bbox_xyxy) for proposal in proposals] == [
        (0.91, (10.0, 10.0, 40.0, 50.0)),
        (0.73, (110.0, 10.0, 140.0, 50.0)),
    ]


@pytest.mark.parametrize(
    ("boxes", "scores", "labels"),
    [
        (np.array([[np.nan, 1.0, 3.0, 4.0]]), np.array([0.9]), ["plastic cup"]),
        (np.array([[1.0, 1.0, 1.0, 4.0]]), np.array([0.9]), ["plastic cup"]),
        (np.array([[1.0, 1.0, 3.0, 4.0]]), np.array([np.nan]), ["plastic cup"]),
        (np.array([[1.0, 1.0, 3.0, 4.0]]), np.array([0.9]), []),
    ],
)
def test_grounding_rejects_malformed_input_contracts(
    boxes: np.ndarray, scores: np.ndarray, labels: list[str]
) -> None:
    """Catch silently filtering non-finite, degenerate, or count-mismatched detector output."""

    assert _error_code(
        lambda: convert_grounding_results(
            boxes, scores, labels, _frame(), DetectionQuery("plastic_cup"), _thresholds()
        )
    ) == "RESULT_CONTRACT_INVALID"


def test_grounding_limits_original_proposal_count_before_filtering() -> None:
    """Catch applying the size limit only after labels or score thresholds hide model output."""

    count = 17
    assert _error_code(
        lambda: convert_grounding_results(
            np.tile(np.array([[1.0, 1.0, 3.0, 4.0]]), (count, 1)),
            np.full(count, 0.01),
            ["not a cup"] * count,
            _frame(),
            DetectionQuery("plastic_cup"),
            _thresholds(max_candidates=16),
        )
    ) == "CANDIDATE_LIMIT_EXCEEDED"


def test_grounding_filters_scores_below_the_configured_gate() -> None:
    """Catch returning a valid cup label whose Grounding DINO confidence misses the box gate."""

    proposals = convert_grounding_results(
        boxes=np.array([[10.0, 10.0, 50.0, 70.0]]),
        scores=np.array([0.34]),
        labels=["plastic cup"],
        frame=_frame(),
        query=DetectionQuery("plastic_cup"),
        thresholds=_thresholds(box_threshold=0.35),
    )

    assert proposals == ()


def test_grounding_accepts_a_score_at_the_configured_gate() -> None:
    """Catch changing the box gate from inclusive to exclusive comparison."""

    proposals = convert_grounding_results(
        boxes=np.array([[10.0, 10.0, 50.0, 70.0]]),
        scores=np.array([0.35]),
        labels=["plastic cup"],
        frame=_frame(),
        query=DetectionQuery("plastic_cup"),
        thresholds=_thresholds(box_threshold=0.35),
    )

    assert proposals == (GroundingProposal((10.0, 10.0, 50.0, 70.0), 0.35),)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"box_threshold": -0.01},
        {"text_threshold": 1.01},
        {"duplicate_iou": float("nan")},
        {"max_candidates": 0},
        {"sam_quality": 1.01},
        {"min_mask_pixels": 0},
        {"max_mask_area_ratio": 0.0},
    ],
)
def test_thresholds_reject_invalid_construction(kwargs: dict[str, object]) -> None:
    """Catch admitting invalid gates that would make candidate filtering undefined."""

    with pytest.raises(ValueError):
        _thresholds(**kwargs)


def test_sam_conversion_selects_best_mask_and_preserves_grounding_score() -> None:
    """Catch using SAM quality as detector confidence or selecting a non-maximal object mask."""

    candidates = convert_sam_results(
        proposals=(GroundingProposal((10.0, 10.0, 50.0, 70.0), 0.61),),
        masks=_masks_for_one_object(),
        quality_scores=np.array([[0.40, 0.91, 0.75]]),
        frame=_frame(),
        thresholds=_thresholds(sam_quality=0.75),
    )

    assert len(candidates) == 1
    assert candidates[0].instance_id == "grounded-sam-000"
    assert candidates[0].confidence == 0.61
    assert candidates[0].segmentation_quality == 0.91
    assert type(candidates[0].segmentation_quality) is float
    assert candidates[0].mask.shape == (120, 160)


@pytest.mark.parametrize(
    ("mask", "quality", "thresholds"),
    [
        (np.ones((120, 160), dtype=bool), 0.74, _thresholds(sam_quality=0.75)),
        (np.pad(np.ones((7, 9), dtype=bool), ((10, 103), (10, 141))), 0.91, _thresholds()),
        (np.ones((120, 160), dtype=bool), 0.91, _thresholds()),
        (np.pad(np.ones((40, 40), dtype=bool), ((70, 10), (100, 20))), 0.91, _thresholds()),
    ],
)
def test_sam_rejects_masks_failing_quality_or_geometry_gates(
    mask: np.ndarray, quality: float, thresholds: GroundedSamThresholds
) -> None:
    """Catch emitting candidates for low-score, tiny, oversized, or out-of-box masks."""

    masks = np.zeros((1, 1, 120, 160), dtype=bool)
    masks[0, 0] = mask
    candidates = convert_sam_results(
        proposals=(GroundingProposal((10.0, 10.0, 50.0, 70.0), 0.61),),
        masks=masks,
        quality_scores=np.array([[quality]]),
        frame=_frame(),
        thresholds=thresholds,
    )

    assert candidates == ()


def test_sam_rejects_an_oversized_mask_even_when_it_is_inside_its_box() -> None:
    """Catch removing the frame-area gate while a large mask still satisfies the box-ratio gate."""

    candidates = convert_sam_results(
        proposals=(GroundingProposal((0.0, 0.0, 160.0, 120.0), 0.61),),
        masks=np.ones((1, 1, 120, 160), dtype=bool),
        quality_scores=np.array([[0.91]]),
        frame=_frame(),
        thresholds=_thresholds(max_mask_area_ratio=0.50),
    )

    assert candidates == ()


def test_sam_accepts_every_inclusive_quality_and_geometry_boundary() -> None:
    """Catch making quality, pixel, area, or box-overlap rejection comparisons exclusive."""

    mask = np.zeros((1, 1, 8, 20), dtype=bool)
    mask[0, 0, :, :8] = True
    mask[0, 0, :, 8:10] = True
    candidates = convert_sam_results(
        proposals=(GroundingProposal((0.0, 0.0, 8.0, 8.0), 0.61),),
        masks=mask,
        quality_scores=np.array([[0.75]]),
        frame=_frame(width=20, height=8),
        thresholds=_thresholds(
            sam_quality=0.75,
            min_mask_pixels=80,
            max_mask_area_ratio=0.50,
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].segmentation_quality == 0.75
    assert int(candidates[0].mask.sum()) == 80


def test_sam_rejects_structural_array_mismatches() -> None:
    """Catch accepting SAM arrays whose object axes no longer align with proposals."""

    proposal = (GroundingProposal((10.0, 10.0, 50.0, 70.0), 0.61),)
    for masks, quality_scores in (
        (np.zeros((2, 1, 120, 160), dtype=bool), np.zeros((1, 1))),
        (np.zeros((1, 1, 120, 160), dtype=bool), np.zeros((2, 1))),
    ):
        assert _error_code(
            lambda: convert_sam_results(
                proposals=proposal,
                masks=masks,
                quality_scores=quality_scores,
                frame=_frame(),
                thresholds=_thresholds(),
            )
        ) == "RESULT_CONTRACT_INVALID"


def test_sam_assigns_ids_after_rejecting_earlier_objects() -> None:
    """Catch instance IDs reflecting raw SAM indices instead of final candidate order."""

    masks = np.zeros((2, 1, 120, 160), dtype=bool)
    masks[0, 0, 10:70, 10:50] = True
    masks[1, 0, 10:70, 80:120] = True
    candidates = convert_sam_results(
        proposals=(
            GroundingProposal((10.0, 10.0, 50.0, 70.0), 0.91),
            GroundingProposal((80.0, 10.0, 120.0, 70.0), 0.82),
        ),
        masks=masks,
        quality_scores=np.array([[0.74], [0.91]]),
        frame=_frame(),
        thresholds=_thresholds(),
    )

    assert [candidate.instance_id for candidate in candidates] == ["grounded-sam-000"]
    assert [candidate.confidence for candidate in candidates] == [0.82]
