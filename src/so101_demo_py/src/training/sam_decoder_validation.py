"""Fixed-threshold proposal coverage and saved-decoder validation contracts."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np
from so101_demo.adapters.perception.grounded_sam_postprocess import (
    GroundedSamThresholds,
    GroundingProposal,
    convert_grounding_results,
    convert_sam_results,
)
from so101_demo.core.detection import DetectionFrame, DetectionQuery

from .grounded_sam_val_calibration import ValDataset, _greedy_matches

REPLAY_THRESHOLDS = GroundedSamThresholds(
    box_threshold=.25, text_threshold=.25, duplicate_iou=.85,
    max_candidates=16, sam_quality=.50, min_mask_pixels=64, max_mask_area_ratio=.50,
)


def prepare_replay_proposals(candidates: Sequence[Any], frame: DetectionFrame) -> tuple[Any, ...]:
    """Replay retained DINO inputs, not unrecorded full live token outputs."""
    if not certify_retained_dino_coverage(candidates)["certified"]:
        raise ValueError("PROPOSAL_COVERAGE_UNCERTIFIED")
    if any(c.label != "cup" or c.grounding_text_score is None for c in candidates):
        raise ValueError("PROPOSAL_IDENTITY_INVALID")
    eligible = tuple(c for c in candidates if c.grounding_box_score > .25)
    proposals = convert_grounding_results(
        np.asarray([c.bbox_xyxy for c in eligible], dtype=float).reshape(-1, 4),
        np.asarray([c.grounding_box_score for c in eligible], dtype=float),
        ["cup" if c.grounding_text_score > .25 else "" for c in eligible],
        frame, DetectionQuery("cup"), REPLAY_THRESHOLDS, {"cup": "cup."},
    )
    output = []
    for proposal in proposals:
        matches = [c for c in eligible if (
            c.bbox_xyxy == proposal.bbox_xyxy and c.grounding_box_score == proposal.confidence
        )]
        if len(matches) != 1:
            raise ValueError("PROPOSAL_IDENTITY_AMBIGUOUS")
        output.append(matches[0])
    return tuple(output)


def filter_replay_sam(
    candidates: Sequence[Any], masks: np.ndarray, qualities: np.ndarray, frame: DetectionFrame,
) -> tuple[tuple[Any, Any], ...]:
    """Use real production SAM filtering while retaining original proposal IDs."""
    proposals = tuple(GroundingProposal(c.bbox_xyxy, c.grounding_box_score) for c in candidates)
    detections = convert_sam_results(proposals, masks, qualities, frame, REPLAY_THRESHOLDS, "cup")
    output = []
    for detection in detections:
        matches = [c for c in candidates if (
            c.bbox_xyxy == detection.bbox_xyxy and c.grounding_box_score == detection.confidence
        )]
        if len(matches) != 1:
            raise ValueError("PROPOSAL_IDENTITY_AMBIGUOUS")
        output.append((matches[0], detection))
    return tuple(output)


def certify_retained_dino_coverage(candidates: Sequence[Any]) -> dict[str, Any]:
    """Certify coverage at 0.25 using the original descending proposal indices."""
    scores = {}
    for candidate in candidates:
        match = re.fullmatch(r"grounded-sam-(\d{3,})", candidate.candidate_id)
        score = candidate.grounding_box_score
        if match is None or score is None or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("PROPOSAL_ORDER_INVALID")
        index = int(match[1])
        if index in scores:
            raise ValueError("PROPOSAL_ORDER_INVALID")
        scores[index] = score
    ordered = sorted(scores)
    if any(scores[a] < scores[b] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("PROPOSAL_ORDER_INVALID")
    uncertain = []
    missing = []
    preceding_score = 1.0
    for index in range(ordered[-1] + 1 if ordered else 0):
        if index in scores:
            preceding_score = scores[index]
        else:
            missing.append(index)
            if preceding_score >= 0.25:
                uncertain.append(index)
    tail_uncertain = not ordered or scores[ordered[-1]] >= 0.25
    return {
        "box_threshold": 0.25,
        "certified": not uncertain and not tail_uncertain,
        "missing_internal_ids": missing,
        "uncertain_internal_ids": uncertain,
        "tail_uncertain": tail_uncertain,
    }


def score_production_masks(
    dataset: ValDataset,
    rows: Sequence[Sequence[tuple[Any, np.ndarray]]],
) -> dict[str, Any]:
    """Score already production-filtered masks; scenario labels are offline only."""
    if len(rows) != len(dataset.samples) or not rows:
        raise ValueError("VALIDATION_DENOMINATOR_INVALID")
    counters = {"all_scenario": Counter(), "primary_near_workspace": Counter()}
    decisions = {name: Counter() for name in counters}
    for sample, row in zip(dataset.samples, rows, strict=True):
        for candidate, mask in row:
            if (
                not isinstance(mask, np.ndarray)
                or mask.dtype != np.bool_
                or mask.shape != (candidate.mask.image_height, candidate.mask.image_width)
                or int(mask.sum()) != candidate.mask.pixel_count
            ):
                raise ValueError("VALIDATION_MASK_INVALID")
        candidates = tuple(candidate for candidate, _ in row)
        matches = _greedy_matches(candidates, sample.truths)
        passed = 0
        for candidate_index, truth_index in matches:
            predicted = row[candidate_index][1]
            truth = sample.truths[truth_index]["mask"]
            if not isinstance(truth, np.ndarray) or truth.shape != predicted.shape or truth.dtype != np.bool_:
                raise ValueError("VALIDATION_MASK_INVALID")
            union = int((predicted | truth).sum())
            overlap = int((predicted & truth).sum()) / union if union else 0.0
            passed += overlap >= 0.80
        values = {
            "image_count": 1, "truth_count": len(sample.truths),
            "candidate_count": len(candidates), "tp": passed,
            "fp": len(candidates) - passed, "fn": len(sample.truths) - passed,
            "bbox_match_count": len(matches), "mask_pass_count": passed,
            "mask_fail_count": len(matches) - passed,
            "no_cup_unique_count": int(not sample.truths and len(candidates) == 1),
        }
        decision = "NOT_FOUND" if not candidates else "UNIQUE" if len(candidates) == 1 else "AMBIGUOUS"
        for name in counters:
            if name == "primary_near_workspace" and sample.scenario == "small_far_cup":
                continue
            counters[name].update(values)
            decisions[name][decision] += 1
    output = {}
    for name, counts in counters.items():
        tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
        result = {key: value for key, value in counts.items() if key not in {"tp", "fp", "fn"}}
        result.update({
            "totals": {"tp": tp, "fp": fp, "fn": fn},
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
            "decision_counts": dict(sorted(decisions[name].items())),
            "mask_iou_gate": 0.80,
        })
        output[name] = result
    return output


def select_decoder_epoch(reports: Sequence[Mapping[str, Any]]) -> int:
    """Select among exactly five completed epochs without threshold search."""
    if len(reports) != 5 or {row.get("epoch") for row in reports} != {1, 2, 3, 4, 5}:
        raise ValueError("EPOCH_COMPARISON_INCOMPLETE")
    for row in reports:
        metrics = row.get("primary_near_workspace", {})
        if type(row.get("epoch")) is not int or any(
            type(metrics.get(key)) not in {int, float}
            or not math.isfinite(metrics[key]) or not 0 <= metrics[key] <= 1
            for key in ("f1", "recall")
        ):
            raise ValueError("EPOCH_COMPARISON_INVALID")
    selected = max(reports, key=lambda row: (
        row["primary_near_workspace"]["f1"],
        row["primary_near_workspace"]["recall"], -row["epoch"],
    ))
    return int(selected["epoch"])
