"""Narrow Allowed Collision Matrix helpers for release separation."""

from __future__ import annotations

from moveit_msgs.msg import AllowedCollisionEntry, AllowedCollisionMatrix


def _validate_pair(first: str, second: str) -> None:
    if not first or not second:
        raise ValueError("collision names must be non-empty")
    if first == second:
        raise ValueError("collision pair must contain two distinct names")


def _normalize_square(matrix: AllowedCollisionMatrix) -> None:
    size = len(matrix.entry_names)
    if len(set(matrix.entry_names)) != size:
        raise ValueError("allowed collision matrix contains duplicate names")
    while len(matrix.entry_values) < size:
        matrix.entry_values.append(AllowedCollisionEntry())
    if len(matrix.entry_values) > size:
        del matrix.entry_values[size:]
    for row in matrix.entry_values:
        if len(row.enabled) < size:
            row.enabled.extend([False] * (size - len(row.enabled)))
        elif len(row.enabled) > size:
            del row.enabled[size:]


def _ensure_name(matrix: AllowedCollisionMatrix, name: str) -> int:
    _normalize_square(matrix)
    if name in matrix.entry_names:
        return matrix.entry_names.index(name)

    old_size = len(matrix.entry_names)
    matrix.entry_names.append(name)
    for row in matrix.entry_values:
        row.enabled.append(False)
    matrix.entry_values.append(AllowedCollisionEntry(enabled=[False] * (old_size + 1)))
    return old_size


def set_collision_allowed(
    matrix: AllowedCollisionMatrix,
    first: str,
    second: str,
    allowed: bool,
) -> None:
    """Set exactly one symmetric ACM pair while preserving all other entries."""

    _validate_pair(first, second)
    first_index = _ensure_name(matrix, first)
    second_index = _ensure_name(matrix, second)
    matrix.entry_values[first_index].enabled[second_index] = bool(allowed)
    matrix.entry_values[second_index].enabled[first_index] = bool(allowed)


def collision_is_allowed(
    matrix: AllowedCollisionMatrix,
    first: str,
    second: str,
) -> bool:
    """Read an explicit symmetric pair, failing closed for missing/malformed entries."""

    if not first or not second:
        raise ValueError("collision names must be non-empty")
    if first not in matrix.entry_names or second not in matrix.entry_names:
        return False
    first_index = matrix.entry_names.index(first)
    second_index = matrix.entry_names.index(second)
    if first_index >= len(matrix.entry_values) or second_index >= len(matrix.entry_values):
        return False
    first_row = matrix.entry_values[first_index].enabled
    second_row = matrix.entry_values[second_index].enabled
    if second_index >= len(first_row) or first_index >= len(second_row):
        return False
    return bool(first_row[second_index] and second_row[first_index])
