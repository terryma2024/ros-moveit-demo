"""Strict, ROS-free task geometry contract shared by simulator adapters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class GeometryContractError(ValueError):
    """Raised when the canonical task-scene manifest is not safe to consume."""


def _invalid(message: str) -> GeometryContractError:
    return GeometryContractError(f"SCENE_MANIFEST_INVALID: {message}")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise _invalid(f"{label} must be a string-keyed mapping")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise _invalid(
            f"{label} fields differ: missing={sorted(expected - actual)!r} "
            f"unknown={sorted(actual - expected)!r}"
        )


def _numbers(value: Any, length: int, label: str) -> tuple[float, ...]:
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
    ):
        raise _invalid(f"{label} must contain exactly {length} numbers")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise _invalid(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class Pose7:
    values: tuple[float, float, float, float, float, float, float]

    @classmethod
    def parse(cls, value: Any, label: str) -> Pose7:
        values = _numbers(value, 7, label)
        quaternion = values[3:]
        norm = math.sqrt(sum(component * component for component in quaternion))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise _invalid(f"{label} quaternion must be normalized")
        return cls(values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class GeometryPrimitive:
    name: str
    kind: str
    dimensions: tuple[float, ...]
    pose: Pose7


@dataclass(frozen=True, slots=True)
class TaskGeometryObject:
    object_id: str
    pose: Pose7
    color_rgba: tuple[float, float, float, float]
    primitives: tuple[GeometryPrimitive, ...]


@dataclass(frozen=True, slots=True)
class TaskGeometry:
    frame_id: str
    objects: tuple[TaskGeometryObject, ...]

    @property
    def object_ids(self) -> tuple[str, ...]:
        return tuple(value.object_id for value in self.objects)

    @property
    def primitive_counts(self) -> dict[str, int]:
        return {value.object_id: len(value.primitives) for value in self.objects}

    def object(self, object_id: str) -> TaskGeometryObject:
        for value in self.objects:
            if value.object_id == object_id:
                return value
        raise KeyError(object_id)


def _primitive(value: Any, label: str) -> GeometryPrimitive:
    mapping = _mapping(value, label)
    _exact_fields(mapping, {"name", "type", "dimensions", "pose_xyz_xyzw"}, label)
    name = mapping["name"]
    kind = mapping["type"]
    if not isinstance(name, str) or not name:
        raise _invalid(f"{label}.name must be non-empty")
    if kind not in {"box", "cylinder"}:
        raise _invalid(f"{label}.type must be box or cylinder")
    dimension_count = 3 if kind == "box" else 2
    dimensions = _numbers(mapping["dimensions"], dimension_count, f"{label}.dimensions")
    if any(dimension <= 0.0 for dimension in dimensions):
        raise _invalid(f"{label}.dimensions must be positive")
    return GeometryPrimitive(
        name=name,
        kind=kind,
        dimensions=dimensions,
        pose=Pose7.parse(mapping["pose_xyz_xyzw"], f"{label}.pose_xyz_xyzw"),
    )


def _object(object_id: str, value: Any) -> TaskGeometryObject:
    label = f"task_scene.objects.{object_id}"
    mapping = _mapping(value, label)
    _exact_fields(mapping, {"pose_xyz_xyzw", "color_rgba", "primitives"}, label)
    color = _numbers(mapping["color_rgba"], 4, f"{label}.color_rgba")
    if any(component < 0.0 or component > 1.0 for component in color):
        raise _invalid(f"{label}.color_rgba must be within [0, 1]")
    raw_primitives = mapping["primitives"]
    if not isinstance(raw_primitives, list) or not raw_primitives:
        raise _invalid(f"{label}.primitives must be a non-empty list")
    primitives = tuple(
        _primitive(item, f"{label}.primitives[{index}]")
        for index, item in enumerate(raw_primitives)
    )
    names = tuple(item.name for item in primitives)
    if len(names) != len(set(names)):
        raise _invalid(f"{label}.primitive names must be unique")
    return TaskGeometryObject(
        object_id=object_id,
        pose=Pose7.parse(mapping["pose_xyz_xyzw"], f"{label}.pose_xyz_xyzw"),
        color_rgba=color,  # type: ignore[arg-type]
        primitives=primitives,
    )


def load_task_geometry(manifest_path: Path) -> TaskGeometry:
    """Load the exact three-object task scene from the common asset manifest."""

    try:
        document = yaml.safe_load(Path(manifest_path).read_bytes())
    except (OSError, yaml.YAMLError) as error:
        raise _invalid(str(error)) from error
    root = _mapping(document, "manifest")
    scene = _mapping(root.get("task_scene"), "task_scene")
    _exact_fields(scene, {"schema_version", "frame_id", "objects"}, "task_scene")
    if scene["schema_version"] != 1:
        raise _invalid("task_scene.schema_version must equal 1")
    frame_id = scene["frame_id"]
    if not isinstance(frame_id, str) or not frame_id:
        raise _invalid("task_scene.frame_id must be non-empty")
    raw_objects = _mapping(scene["objects"], "task_scene.objects")
    expected_ids = ("table", "pedestal", "plastic_cup")
    if tuple(raw_objects) != expected_ids:
        raise _invalid(f"task_scene.objects must be ordered as {expected_ids!r}")
    objects = tuple(_object(object_id, raw_objects[object_id]) for object_id in expected_ids)
    expected_counts = {"table": 1, "pedestal": 1, "plastic_cup": 13}
    actual_counts = {value.object_id: len(value.primitives) for value in objects}
    if actual_counts != expected_counts:
        raise _invalid(
            f"primitive counts must be {expected_counts!r}, got {actual_counts!r}"
        )
    return TaskGeometry(frame_id=frame_id, objects=objects)
