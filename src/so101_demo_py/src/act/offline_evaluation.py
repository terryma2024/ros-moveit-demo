"""Task 12A: read-only evaluation of a frozen bundle on the Offline Test split.

Padded frames are not evidence. A tail padded to complete an action chunk must never contribute to a
joint metric, and a metric must never quietly shrink its denominator to make a bad row disappear — the
mask decides which frames count, and a frame that is malformed is refused rather than skipped.
"""

from __future__ import annotations

import math

_JOINTS = 6


def _row(row, label: str) -> list:
    if not isinstance(row, (list, tuple)) or len(row) != _JOINTS:
        raise ValueError("MASK_SHAPE_INVALID")
    values = []
    for value in row:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label}_INVALID")
        values.append(float(value))
    return values


def masked_joint_mae(predicted: list, target: list, valid: list) -> list:
    """Per-joint mean absolute error over the frames the mask keeps."""

    if len(predicted) != len(target) or len(valid) != len(target):
        raise ValueError("MASK_SHAPE_INVALID")
    for keep in valid:
        if type(keep) is not bool:
            raise ValueError("MASK_SHAPE_INVALID")
    indices = [index for index, keep in enumerate(valid) if keep]
    if not indices:
        raise ValueError("NO_VALID_TARGETS")
    predictions = [_row(predicted[index], "PREDICTED") for index in indices]
    targets = [_row(target[index], "TARGET") for index in indices]
    return [sum(abs(predictions[position][joint] - targets[position][joint])
                for position in range(len(indices))) / len(indices)
            for joint in range(_JOINTS)]


def masked_joint_rmse(predicted: list, target: list, valid: list) -> list:
    """Per-joint root mean squared error over the same frames, with the same refusals."""

    if len(predicted) != len(target) or len(valid) != len(target):
        raise ValueError("MASK_SHAPE_INVALID")
    for keep in valid:
        if type(keep) is not bool:
            raise ValueError("MASK_SHAPE_INVALID")
    indices = [index for index, keep in enumerate(valid) if keep]
    if not indices:
        raise ValueError("NO_VALID_TARGETS")
    predictions = [_row(predicted[index], "PREDICTED") for index in indices]
    targets = [_row(target[index], "TARGET") for index in indices]
    return [math.sqrt(sum((predictions[position][joint] - targets[position][joint]) ** 2
                          for position in range(len(indices))) / len(indices))
            for joint in range(_JOINTS)]
