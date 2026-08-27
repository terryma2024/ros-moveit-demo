"""YAML boundary for versioned task-point documents."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..core.task_points import (
    TaskPointError,
    TaskPointList,
    parse_task_point_list,
)


def load_task_point_list(
    path: Path,
    workspace_bounds_m: tuple[float, float, float, float, float, float],
) -> TaskPointList:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise TaskPointError(f"TASK_POINT_READ_FAILED: {path}: {error}") from error
    except yaml.YAMLError as error:
        raise TaskPointError(f"TASK_POINT_YAML_INVALID: {path}: {error}") from error
    return parse_task_point_list(document, workspace_bounds_m)


def dump_task_point_list(points: TaskPointList) -> str:
    document = {
        "schema_version": points.schema_version,
        "points": [
            {
                "id": point.id,
                "label": point.label,
                "cup_position_world_m": list(point.cup_position_world_m),
            }
            for point in points.points
        ],
    }
    return yaml.safe_dump(document, sort_keys=False)
