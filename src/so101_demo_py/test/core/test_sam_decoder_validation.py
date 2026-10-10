"""Coverage, cohort and selection contracts for saved SAM decoder comparisons."""

import importlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.contracts import MaskRef, RawCandidate
from so101_demo.training.grounded_sam_val_calibration import ValDataset, ValSample


def api():
    spec = importlib.util.find_spec("so101_demo.training.sam_decoder_validation")
    assert spec is not None, "SAM decoder comparison contract is not implemented"
    return importlib.import_module("so101_demo.training.sam_decoder_validation")


def candidate(index=0, score=0.8, pixels=4):
    return RawCandidate(
        candidate_id=f"grounded-sam-{index:03d}", label="cup",
        bbox_xyxy=(1.0, 1.0, 3.0, 3.0),
        mask=MaskRef("mask.json", "a" * 64, pixels, 4, 4),
        ranking_score=score, ranking_score_source="grounding_box_score",
        class_confidence=None, grounding_box_score=score, grounding_text_score=score,
        sam_quality=0.9,
    )


@pytest.mark.parametrize("rows,certified", [
    ((candidate(0, 0.8), candidate(1, 0.1), candidate(3, 0.05)), True),
    ((candidate(0, 0.8), candidate(2, 0.1)), False),
    ((candidate(1, 0.1),), False),
    ((candidate(0, 0.8),), False),
    ((), False),
])
def test_fixed_threshold_certificate_bounds_missing_queries(rows, certified):
    assert api().certify_retained_dino_coverage(rows)["certified"] is certified


def test_coverage_rejects_reversed_score_order():
    with pytest.raises(ValueError, match="PROPOSAL_ORDER_INVALID"):
        api().certify_retained_dino_coverage((candidate(0, 0.1), candidate(1, 0.8)))


def dataset():
    mask = np.zeros((4, 4), dtype=bool)
    mask[1:3, 1:3] = True
    truth = {"absolute_xyxy": (1.0, 1.0, 3.0, 3.0), "mask": mask}
    samples = tuple(ValSample(
        formal_sample_index=index, seed=420000000 + index, scenario=scenario,
        configured_cup_count=0 if scenario == "no_cup" else 1,
        image_path=Path(f"/images/{index}.png"), image_sha256="a" * 64,
        truths=() if scenario == "no_cup" else (truth,),
    ) for index, scenario in enumerate(("one_cup_distractors", "small_far_cup", "no_cup")))
    return ValDataset("a" * 64, "b" * 64, samples, {s.scenario: 1 for s in samples}), mask


def test_cohort_metrics_preserve_false_positive_and_exclude_only_small_far():
    data, correct = dataset()
    wrong = ~correct
    rows = (((candidate(), correct),), ((candidate(pixels=12), wrong),), ((candidate(), correct),))
    result = api().score_production_masks(data, rows)
    assert result["all_scenario"]["totals"] == {"tp": 1, "fp": 2, "fn": 1}
    assert result["all_scenario"]["f1"] == pytest.approx(0.4)
    assert result["primary_near_workspace"]["totals"] == {"tp": 1, "fp": 1, "fn": 0}
    assert result["primary_near_workspace"]["f1"] == pytest.approx(2 / 3)
    assert result["primary_near_workspace"]["no_cup_unique_count"] == 1


def test_mask_iou_below_point_eight_is_not_a_true_positive():
    data, mask = dataset()
    partial = mask.copy()
    partial[1, 1] = False
    result = api().score_production_masks(data, (((candidate(pixels=3), partial),), (), ()))
    assert result["all_scenario"]["totals"]["tp"] == 0
    assert result["all_scenario"]["mask_fail_count"] == 1


def test_missing_frame_denominator_rejected():
    data, _ = dataset()
    with pytest.raises(ValueError, match="VALIDATION_DENOMINATOR_INVALID"):
        api().score_production_masks(data, ((), ()))


def test_selection_uses_primary_f1_recall_then_earliest_epoch():
    rows = [{"epoch": epoch, "primary_near_workspace": {"f1": f1, "recall": recall}}
            for epoch, f1, recall in [(1, .1, .8), (2, .9, .4), (3, .9, .5), (4, .9, .5), (5, .6, .9)]]
    assert api().select_decoder_epoch(rows) == 3
    with pytest.raises(ValueError, match="EPOCH_COMPARISON_INCOMPLETE"):
        api().select_decoder_epoch(rows[:-1])


def frame():
    return DetectionFrame(np.zeros((32, 32, 3), dtype=np.uint8), 1, "offline-val")


def retained(index=0, score=.9, **changes):
    return replace(candidate(index, score),
                   bbox_xyxy=(4., 4., 12., 12.),
                   mask=MaskRef("old.json", "a" * 64, 64, 32, 32), **changes)


def test_replay_deduplicates_before_sam_and_preserves_original_identity():
    rows = (retained(0), retained(1, .8), retained(2, .1))
    kept = api().prepare_replay_proposals(rows, frame())
    assert [item.candidate_id for item in kept] == ["grounded-sam-000"]


def test_replay_rejects_uncertified_tail_and_over_limit_instead_of_truncating():
    with pytest.raises(ValueError, match="PROPOSAL_COVERAGE_UNCERTIFIED"):
        api().prepare_replay_proposals((retained(),), frame())
    rows = tuple(retained(i, .9 - i * .01) for i in range(17)) + (retained(17, .1),)
    with pytest.raises(ValueError, match="CANDIDATE_LIMIT_EXCEEDED"):
        api().prepare_replay_proposals(rows, frame())


def test_replay_applies_text_gate_without_using_previous_sam_quality():
    rows = (retained(0, grounding_text_score=.1), retained(1, .8, sam_quality=.1), retained(2, .1))
    kept = api().prepare_replay_proposals(rows, frame())
    assert [item.candidate_id for item in kept] == ["grounded-sam-001"]


def test_replay_sam_selects_quality_argmax_and_preserves_stable_id():
    masks = np.zeros((1, 3, 32, 32), dtype=bool)
    masks[0, 1, 4:12, 4:12] = True
    accepted = api().filter_replay_sam((retained(7),), masks, np.array([[.1, .9, .3]]), frame())
    assert len(accepted) == 1
    original, detection = accepted[0]
    assert original.candidate_id == "grounded-sam-007"
    assert detection.segmentation_quality == .9
    assert detection.mask.sum() == 64


def test_replay_sam_does_not_choose_lower_quality_mask_to_pass_inside_box_gate():
    masks = np.zeros((1, 3, 32, 32), dtype=bool)
    masks[0, 0, 4:12, 4:12] = True
    masks[0, 1, 20:28, 20:28] = True
    assert api().filter_replay_sam((retained(),), masks, np.array([[.8, .9, .1]]), frame()) == ()
    with pytest.raises(ValueError, match="RESULT_CONTRACT_INVALID"):
        api().filter_replay_sam((retained(),), masks, np.array([[.8, 1.01, .1]]), frame())
