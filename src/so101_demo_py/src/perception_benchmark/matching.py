"""Deterministic binary-mask geometry and assignment."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Sequence

import numpy as np

from so101_demo.perception_benchmark.codec import read_mask
from so101_demo.perception_benchmark.contracts import RawCandidate, TruthInstance


@dataclass(frozen=True, slots=True)
class MaskMatch:
    truth_instance_id: str
    candidate_id: str
    iou: float

    def __post_init__(self) -> None:
        if not isinstance(self.truth_instance_id, str) or not self.truth_instance_id:
            raise ValueError("truth_instance_id must be non-empty")
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise ValueError("candidate_id must be non-empty")
        value = float(self.iou)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("iou must be finite and in [0, 1]")
        object.__setattr__(self, "iou", value)


def _binary_pair(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    first_mask = np.asarray(first, dtype=bool)
    second_mask = np.asarray(second, dtype=bool)
    if first_mask.ndim != 2 or second_mask.ndim != 2:
        raise ValueError("masks must be two-dimensional")
    if first_mask.shape != second_mask.shape:
        raise ValueError("masks must have the same shape")
    return first_mask, second_mask


def mask_iou(first: np.ndarray, second: np.ndarray) -> float:
    """Return binary-mask IoU, using zero for an empty union."""

    first_mask, second_mask = _binary_pair(first, second)
    intersection = int(np.count_nonzero(first_mask & second_mask))
    union = int(np.count_nonzero(first_mask | second_mask))
    if union == 0:
        return 0.0
    return float(intersection / union)


def mask_dice(first: np.ndarray, second: np.ndarray) -> float:
    """Return binary-mask Dice, using zero when both masks are empty."""

    first_mask, second_mask = _binary_pair(first, second)
    intersection = int(np.count_nonzero(first_mask & second_mask))
    denominator = int(np.count_nonzero(first_mask)) + int(np.count_nonzero(second_mask))
    if denominator == 0:
        return 0.0
    return float((2 * intersection) / denominator)


def _hungarian_minimize(cost: np.ndarray) -> tuple[int | None, ...]:
    """Return a minimum-cost rectangular assignment in O(n^3)."""

    matrix = np.asarray(cost, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("cost must be two-dimensional")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("cost must contain only finite values")
    row_count, original_column_count = matrix.shape
    if row_count == 0:
        return ()
    if original_column_count == 0:
        return (None,) * row_count

    if row_count > original_column_count:
        spread = float(np.max(matrix) - np.min(matrix))
        dummy_cost = float(np.max(matrix)) + max(1.0, spread + 1.0)
        matrix = np.pad(
            matrix,
            ((0, 0), (0, row_count - original_column_count)),
            mode="constant",
            constant_values=dummy_cost,
        )

    column_count = matrix.shape[1]
    row_potential = np.zeros(row_count + 1, dtype=np.float64)
    column_potential = np.zeros(column_count + 1, dtype=np.float64)
    column_to_row = np.zeros(column_count + 1, dtype=np.int64)
    predecessor = np.zeros(column_count + 1, dtype=np.int64)

    for row in range(1, row_count + 1):
        column_to_row[0] = row
        minimum = np.full(column_count + 1, np.inf, dtype=np.float64)
        used = np.zeros(column_count + 1, dtype=bool)
        current_column = 0
        while True:
            used[current_column] = True
            current_row = int(column_to_row[current_column])
            delta = math.inf
            next_column = 0
            for column in range(1, column_count + 1):
                if used[column]:
                    continue
                reduced_cost = (
                    matrix[current_row - 1, column - 1]
                    - row_potential[current_row]
                    - column_potential[column]
                )
                if reduced_cost < minimum[column]:
                    minimum[column] = reduced_cost
                    predecessor[column] = current_column
                if minimum[column] < delta:
                    delta = float(minimum[column])
                    next_column = column
            for column in range(column_count + 1):
                if used[column]:
                    row_potential[column_to_row[column]] += delta
                    column_potential[column] -= delta
                else:
                    minimum[column] -= delta
            current_column = next_column
            if column_to_row[current_column] == 0:
                break
        while current_column != 0:
            previous_column = int(predecessor[current_column])
            column_to_row[current_column] = column_to_row[previous_column]
            current_column = previous_column

    assignment: list[int | None] = [None] * row_count
    for column in range(1, column_count + 1):
        assigned_row = int(column_to_row[column])
        if assigned_row != 0 and column <= original_column_count:
            assignment[assigned_row - 1] = column - 1
    return tuple(assignment)


def maximize_mask_iou_assignment(
    truth: Sequence[TruthInstance],
    candidates: Sequence[RawCandidate],
    evidence_root: Path,
) -> tuple[MaskMatch, ...]:
    """Maximize total mask IoU with stable truth and candidate ordering."""

    ordered_truth = tuple(sorted(truth, key=lambda item: item.instance_id))
    ordered_candidates = tuple(
        sorted(candidates, key=lambda item: (-item.ranking_score, item.candidate_id))
    )
    if not ordered_truth or not ordered_candidates:
        return ()
    truth_masks = tuple(read_mask(item.mask, evidence_root) for item in ordered_truth)
    candidate_masks = tuple(
        read_mask(item.mask, evidence_root) for item in ordered_candidates
    )
    ious = np.asarray(
        [
            [mask_iou(truth_mask, candidate_mask) for candidate_mask in candidate_masks]
            for truth_mask in truth_masks
        ],
        dtype=np.float64,
    )
    row_to_column = _hungarian_minimize(1.0 - ious)
    return tuple(
        MaskMatch(
            ordered_truth[row].instance_id,
            ordered_candidates[column].candidate_id,
            float(ious[row, column]),
        )
        for row, column in enumerate(row_to_column)
        if column is not None
    )
