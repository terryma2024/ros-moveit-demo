"""Greedy matching, threshold points and the SAM quality threshold selection."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.calibration.thresholds import GroundedSamBenchmarkThresholds
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    read_mask,
)
from so101_demo.perception_benchmark.contracts import RawCandidate
from so101_demo.training.grounded_sam_val_calibration.datasets import (
    _COMMIT,
    _FROZEN_GRID,
    _LOW_QUALITY_GRID,
    _SHA256,
    ValCalibrationError,
    ValDataset,
)
from so101_demo.training.grounded_sam_val_calibration.evidence import _create_output_root
from so101_demo.training.grounding_dino_finetune import box_iou


def _greedy_matches(
    candidates: Sequence[RawCandidate], truths: Sequence[Mapping[str, Any]]
) -> tuple[tuple[int, int], ...]:
    unmatched = set(range(len(truths)))
    matches: list[tuple[int, int]] = []
    for candidate_index in sorted(
        range(len(candidates)),
        key=lambda index: (-candidates[index].ranking_score, candidates[index].candidate_id),
    ):
        eligible = [
            (
                box_iou(
                    candidates[candidate_index].bbox_xyxy,
                    tuple(truths[truth_index]["absolute_xyxy"]),
                ),
                truth_index,
            )
            for truth_index in unmatched
        ]
        if eligible:
            overlap, truth_index = max(eligible, key=lambda item: (item[0], -item[1]))
            if overlap >= 0.5:
                unmatched.remove(truth_index)
                matches.append((candidate_index, truth_index))
    return tuple(matches)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if denominator == 0 else float(numerator / denominator)


def _threshold_point(
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    quality: Decimal,
) -> dict[str, Any]:
    thresholds = GroundedSamBenchmarkThresholds(
        Decimal("0.25"),
        Decimal("0.25"),
        quality,
        Decimal("0.25"),
        Decimal("0.85"),
        64,
        Decimal("0.50"),
    )
    totals: Counter[str] = Counter()
    scenarios: dict[str, Counter[str]] = {
        name: Counter() for name in dataset.scenario_counts
    }
    decisions: Counter[str] = Counter()
    no_cup_unique_count = 0
    for sample, raw in zip(dataset.samples, raw_candidates_by_sample, strict=True):
        candidates = thresholds.filter_candidates(raw)[:16]
        matches = _greedy_matches(candidates, sample.truths)
        tp = len(matches)
        fp = len(candidates) - tp
        fn = len(sample.truths) - tp
        totals.update(tp=tp, fp=fp, fn=fn)
        scenarios[sample.scenario].update(tp=tp, fp=fp, fn=fn, images=1)
        decision = "NOT_FOUND" if not candidates else "UNIQUE" if len(candidates) == 1 else "AMBIGUOUS"
        decisions[decision] += 1
        if sample.scenario == "no_cup" and decision == "UNIQUE":
            no_cup_unique_count += 1
    precision = _ratio(totals["tp"], totals["tp"] + totals["fp"])
    recall = _ratio(totals["tp"], totals["tp"] + totals["fn"])
    f1 = _ratio(2.0 * precision * recall, precision + recall)
    scenario_metrics = {
        name: dict(sorted(values.items())) for name, values in sorted(scenarios.items())
    }

    def scenario_recall(name: str) -> float:
        values = scenarios.get(name, Counter())
        return _ratio(values["tp"], values["tp"] + values["fn"])

    return {
        "sam_quality": format(quality, ".2f"),
        "totals": {"fn": totals["fn"], "fp": totals["fp"], "tp": totals["tp"]},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "small_far_recall": scenario_recall("small_far_cup"),
        "multi_cup_recall": scenario_recall("two_cups"),
        "decision_counts": dict(sorted(decisions.items())),
        "scenario_metrics": scenario_metrics,
        "safety_gates": {"no_cup_unique_count": no_cup_unique_count},
    }


def select_sam_quality_threshold(
    *,
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    quality_grid: Sequence[str] = tuple(format(value, ".2f") for value in _FROZEN_GRID),
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    """Evaluate and select the preregistered val-only SAM threshold grid."""

    if len(raw_candidates_by_sample) != len(dataset.samples):
        raise ValCalibrationError("RAW_DENOMINATOR_INVALID")
    try:
        normalized = tuple(Decimal(value) for value in quality_grid)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID") from error
    if normalized != _FROZEN_GRID and normalized not in {
        (Decimal("0.70"), Decimal("0.75"), Decimal("0.80")),
    }:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID")
    points = tuple(
        MappingProxyType(_threshold_point(dataset, raw_candidates_by_sample, quality))
        for quality in normalized
    )

    def selection_key(point: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            -float(point["f1"]),
            -float(point["recall"]),
            -float(point["small_far_recall"]),
            -float(point["multi_cup_recall"]),
            int(point["safety_gates"]["no_cup_unique_count"]),
            -Decimal(str(point["sam_quality"])),
            int(point["totals"]["fp"]),
        )

    selected = min(points, key=selection_key)
    return selected, points


def _mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    left_mask = np.asarray(left, dtype=bool)
    right_mask = np.asarray(right, dtype=bool)
    if left_mask.shape != right_mask.shape or left_mask.ndim != 2:
        raise ValCalibrationError("MASK_TRUTH_SHAPE_INVALID")
    union = int(np.logical_or(left_mask, right_mask).sum())
    return 0.0 if union == 0 else float(np.logical_and(left_mask, right_mask).sum() / union)


def _mask_aware_threshold_point(
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    raw_evidence_root: Path,
    quality: Decimal,
) -> dict[str, Any]:
    thresholds = GroundedSamBenchmarkThresholds(
        Decimal("0.25"),
        Decimal("0.25"),
        quality,
        Decimal("0.25"),
        Decimal("0.85"),
        64,
        Decimal("0.50"),
    )
    totals: Counter[str] = Counter()
    scenarios: dict[str, Counter[str]] = {
        name: Counter() for name in dataset.scenario_counts
    }
    decisions: Counter[str] = Counter()
    mask_ious: list[float] = []
    no_cup_unique_count = 0
    for sample, raw in zip(dataset.samples, raw_candidates_by_sample, strict=True):
        candidates = thresholds.filter_candidates(raw)[:16]
        matches = _greedy_matches(candidates, sample.truths)
        passing = 0
        for candidate_index, truth_index in matches:
            truth_mask = sample.truths[truth_index].get("mask")
            if not isinstance(truth_mask, np.ndarray):
                raise ValCalibrationError("VAL_TRUTH_MASK_INVALID", str(sample.seed))
            overlap = _mask_iou(
                read_mask(candidates[candidate_index].mask, raw_evidence_root),
                truth_mask,
            )
            mask_ious.append(overlap)
            if overlap >= 0.80:
                passing += 1
        tp = passing
        fp = len(candidates) - passing
        fn = len(sample.truths) - passing
        totals.update(
            tp=tp,
            fp=fp,
            fn=fn,
            bbox_matches=len(matches),
            mask_pass=passing,
            mask_fail=len(matches) - passing,
        )
        scenarios[sample.scenario].update(tp=tp, fp=fp, fn=fn, images=1)
        decision = "NOT_FOUND" if not candidates else "UNIQUE" if len(candidates) == 1 else "AMBIGUOUS"
        decisions[decision] += 1
        if sample.scenario == "no_cup" and decision == "UNIQUE":
            no_cup_unique_count += 1
    precision = _ratio(totals["tp"], totals["tp"] + totals["fp"])
    recall = _ratio(totals["tp"], totals["tp"] + totals["fn"])
    f1 = _ratio(2.0 * precision * recall, precision + recall)

    def scenario_recall(name: str) -> float:
        values = scenarios.get(name, Counter())
        return _ratio(values["tp"], values["tp"] + values["fn"])

    return {
        "sam_quality": format(quality, ".2f"),
        "totals": {"fn": totals["fn"], "fp": totals["fp"], "tp": totals["tp"]},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "small_far_recall": scenario_recall("small_far_cup"),
        "multi_cup_recall": scenario_recall("two_cups"),
        "decision_counts": dict(sorted(decisions.items())),
        "scenario_metrics": {
            name: dict(sorted(values.items())) for name, values in sorted(scenarios.items())
        },
        "safety_gates": {"no_cup_unique_count": no_cup_unique_count},
        "mask_metrics": {
            "bbox_match_count": totals["bbox_matches"],
            "pass_count": totals["mask_pass"],
            "fail_count": totals["mask_fail"],
            "truth_iou_threshold": 0.80,
            "minimum_iou": min(mask_ious) if mask_ious else None,
            "median_iou": float(np.median(mask_ious)) if mask_ious else None,
            "maximum_iou": max(mask_ious) if mask_ious else None,
        },
    }


def select_mask_aware_sam_quality_threshold(
    *,
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    raw_evidence_root: Path,
    quality_grid: Sequence[str] = tuple(format(value, ".2f") for value in _LOW_QUALITY_GRID),
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    """Select the preregistered low SAM-quality grid with truth-mask safety."""

    root = Path(raw_evidence_root)
    if (
        len(raw_candidates_by_sample) != len(dataset.samples)
        or not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
    ):
        raise ValCalibrationError("MASK_AWARE_INPUT_INVALID")
    try:
        normalized = tuple(Decimal(value) for value in quality_grid)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID") from error
    if normalized not in {
        _LOW_QUALITY_GRID,
        (Decimal("0.00"), Decimal("0.10"), Decimal("0.20")),
    }:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID")
    points = tuple(
        MappingProxyType(
            _mask_aware_threshold_point(dataset, raw_candidates_by_sample, root, quality)
        )
        for quality in normalized
    )

    def selection_key(point: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            -float(point["f1"]),
            -float(point["recall"]),
            -float(point["small_far_recall"]),
            -float(point["multi_cup_recall"]),
            int(point["safety_gates"]["no_cup_unique_count"]),
            -Decimal(str(point["sam_quality"])),
            int(point["totals"]["fp"]),
        )

    return min(points, key=selection_key), points


def write_mask_aware_calibration_evidence(
    *,
    output_root: Path,
    dataset: ValDataset,
    raw_run_root: Path,
    raw_manifest_sha256: str,
    source_commit: str,
    selected: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Persist an exclusive mask-aware low-grid calibration result."""

    if (
        _SHA256.fullmatch(raw_manifest_sha256) is None
        or _COMMIT.fullmatch(source_commit) is None
        or not Path(raw_run_root).is_absolute()
        or len(points) != len(_LOW_QUALITY_GRID)
    ):
        raise ValCalibrationError("CALIBRATION_PROVENANCE_INVALID")
    root = _create_output_root(output_root)
    report = {
        "schema_version": "so101-grounded-sam-val-mask-aware-calibration-report/v1",
        "source_commit": source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "raw_run_root": str(Path(raw_run_root)),
        "raw_manifest_sha256": raw_manifest_sha256,
        "frozen_thresholds": {
            "box": "0.25",
            "text": "0.25",
            "truth_box_iou": "0.50",
            "truth_mask_iou": "0.80",
            "sam_quality_grid": [format(value, ".2f") for value in _LOW_QUALITY_GRID],
        },
        "selected_sam_quality": selected["sam_quality"],
        "selected": dict(selected),
        "grid_points": [dict(point) for point in points],
        "inference_rerun": False,
        "synthetic_test_access": "none",
        "coco100_access": "none",
    }
    try:
        report_sha = atomic_write_json(root / "report.json", report)
        atomic_write_json(
            root / "manifest.json",
            {
                "schema_version": "so101-grounded-sam-val-mask-aware-calibration-run/v1",
                "status": "VALID",
                "source_commit": source_commit,
                "val_inventory_sha256": dataset.inventory_sha256,
                "raw_manifest_sha256": raw_manifest_sha256,
                "report_sha256": report_sha,
            },
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_WRITE_FAILED") from error
    return MappingProxyType(report)
