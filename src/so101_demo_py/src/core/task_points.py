"""ROS-free immutable task-point values and strict mapping validation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


_POINT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_DOCUMENT_FIELDS = frozenset({"schema_version", "points"})
_POINT_FIELDS = frozenset({"id", "label", "cup_position_world_m"})


class TaskPointError(ValueError):
    """A task-point document is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class TaskPoint:
    id: str
    label: str
    cup_position_world_m: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TaskPointList:
    schema_version: int
    points: tuple[TaskPoint, ...]


def _workspace_bounds(
    value: Sequence[float],
) -> tuple[float, float, float, float, float, float]:
    if len(value) != 6 or any(
        isinstance(component, bool)
        or not isinstance(component, (int, float))
        or not math.isfinite(component)
        for component in value
    ):
        raise TaskPointError(
            "TASK_POINT_WORKSPACE_INVALID: workspace bounds must contain six finite numbers"
        )
    bounds = tuple(float(component) for component in value)
    if any(
        lower >= upper
        for lower, upper in zip(bounds[:3], bounds[3:], strict=True)
    ):
        raise TaskPointError(
            "TASK_POINT_WORKSPACE_INVALID: workspace lower bounds must precede upper bounds"
        )
    return bounds  # type: ignore[return-value]


def _position(
    value: object,
    bounds: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(
            isinstance(component, bool)
            or not isinstance(component, (int, float))
            or not math.isfinite(component)
            for component in value
        )
    ):
        raise TaskPointError(
            "TASK_POINT_INVALID: cup_position_world_m must contain three finite numbers"
        )
    position = tuple(float(component) for component in value)
    if any(
        coordinate < lower or coordinate > upper
        for coordinate, lower, upper in zip(
            position, bounds[:3], bounds[3:], strict=True
        )
    ):
        raise TaskPointError(
            "TASK_POINT_OUT_OF_WORKSPACE: cup_position_world_m is outside workspace bounds"
        )
    return position  # type: ignore[return-value]


def parse_task_point_list(
    document: Mapping[str, object],
    workspace_bounds_m: tuple[float, float, float, float, float, float],
) -> TaskPointList:
    """Parse a strict schema-version-one point list within ``workspace_bounds_m``."""

    bounds = _workspace_bounds(workspace_bounds_m)
    if not isinstance(document, Mapping) or set(document) != _DOCUMENT_FIELDS:
        raise TaskPointError(
            "TASK_POINT_INVALID: document fields must be exactly schema_version and points"
        )
    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or schema_version != 1:
        raise TaskPointError("TASK_POINT_SCHEMA_UNSUPPORTED: schema_version must be 1")
    point_documents = document["points"]
    if not isinstance(point_documents, list) or not point_documents:
        raise TaskPointError("TASK_POINT_INVALID: points must be a non-empty list")

    points: list[TaskPoint] = []
    point_ids: set[str] = set()
    for index, point_document in enumerate(point_documents):
        if not isinstance(point_document, Mapping) or set(point_document) != _POINT_FIELDS:
            raise TaskPointError(
                f"TASK_POINT_INVALID: point {index} fields must be exactly id, label, and cup_position_world_m"
            )
        point_id = point_document["id"]
        if not isinstance(point_id, str) or _POINT_ID.fullmatch(point_id) is None:
            raise TaskPointError(f"TASK_POINT_INVALID: point {index} has an unsafe id")
        if point_id in point_ids:
            raise TaskPointError(f"TASK_POINT_DUPLICATE: duplicate point id {point_id}")
        label = point_document["label"]
        if not isinstance(label, str) or not label.strip():
            raise TaskPointError(
                f"TASK_POINT_INVALID: point {point_id} label must be non-empty"
            )
        points.append(
            TaskPoint(
                id=point_id,
                label=label,
                cup_position_world_m=_position(
                    point_document["cup_position_world_m"], bounds
                ),
            )
        )
        point_ids.add(point_id)

    return TaskPointList(schema_version=1, points=tuple(points))
