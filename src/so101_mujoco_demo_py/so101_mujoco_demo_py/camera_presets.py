"""Strict, ROS-independent viewer camera preset configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import yaml


class CameraPresetConfigError(ValueError):
    """Raised when a camera preset file violates the schema."""


class _DuplicateSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _DuplicateSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise CameraPresetConfigError("mapping key must be hashable") from error
        if duplicate:
            raise CameraPresetConfigError(f"duplicate key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_DuplicateSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True)
class FreeCameraPreset:
    name: str
    lookat: tuple[float, float, float]
    distance: float
    azimuth_deg: float
    elevation_deg: float
    orthographic: bool


@dataclass(frozen=True)
class FixedCameraPreset:
    name: str
    fixed_camera_name: str


CameraPreset: TypeAlias = FreeCameraPreset | FixedCameraPreset

_ROOT_FIELDS = {"schema_version", "presets"}
_FREE_FIELDS = {
    "mode",
    "lookat",
    "distance",
    "azimuth_deg",
    "elevation_deg",
    "orthographic",
}
_FIXED_FIELDS = {"mode", "fixed_camera_name"}


def normalize_azimuth(degrees: float) -> float:
    """Normalize an angle into the half-open range [-180, 180)."""
    return (degrees + 180.0) % 360.0 - 180.0


def circular_azimuth_distance(left: float, right: float) -> float:
    """Return the shortest unsigned distance between two azimuths."""
    return abs(normalize_azimuth(left - right))


def _require_exact_fields(record: dict[object, object], expected: set[str], context: str) -> None:
    observed = set(record)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(str(field) for field in observed - expected)
        raise CameraPresetConfigError(
            f"{context} fields must be exactly {sorted(expected)}; "
            f"missing={missing}, unknown={unknown}"
        )


def _finite_number(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CameraPresetConfigError(f"{context} must be a number")
    converted = float(value)
    if not math.isfinite(converted):
        raise CameraPresetConfigError(f"{context} must be finite")
    return converted


def _parse_free(name: str, record: dict[object, object]) -> FreeCameraPreset:
    _require_exact_fields(record, _FREE_FIELDS, f"preset {name!r}")
    raw_lookat = record["lookat"]
    if not isinstance(raw_lookat, list) or len(raw_lookat) != 3:
        raise CameraPresetConfigError(f"preset {name!r} lookat must contain three numbers")
    lookat = tuple(
        _finite_number(value, f"preset {name!r} lookat[{index}]")
        for index, value in enumerate(raw_lookat)
    )
    distance = _finite_number(record["distance"], f"preset {name!r} distance")
    if distance <= 0.0:
        raise CameraPresetConfigError(f"preset {name!r} distance must be positive")
    azimuth = _finite_number(record["azimuth_deg"], f"preset {name!r} azimuth_deg")
    elevation = _finite_number(record["elevation_deg"], f"preset {name!r} elevation_deg")
    if not -90.0 < elevation < 90.0:
        raise CameraPresetConfigError(f"preset {name!r} elevation_deg must be in (-90, 90)")
    orthographic = record["orthographic"]
    if not isinstance(orthographic, bool):
        raise CameraPresetConfigError(f"preset {name!r} orthographic must be a boolean")
    return FreeCameraPreset(
        name=name,
        lookat=lookat,
        distance=distance,
        azimuth_deg=normalize_azimuth(azimuth),
        elevation_deg=elevation,
        orthographic=orthographic,
    )


def _parse_fixed(name: str, record: dict[object, object]) -> FixedCameraPreset:
    _require_exact_fields(record, _FIXED_FIELDS, f"preset {name!r}")
    fixed_camera_name = record["fixed_camera_name"]
    if not isinstance(fixed_camera_name, str) or not fixed_camera_name.strip():
        raise CameraPresetConfigError(f"preset {name!r} fixed_camera_name must be non-empty")
    return FixedCameraPreset(name=name, fixed_camera_name=fixed_camera_name)


def load_camera_presets(config_file: Path) -> dict[str, CameraPreset]:
    """Load and validate a camera preset file without accepting schema extensions."""
    try:
        document = yaml.load(config_file.read_text(encoding="utf-8"), Loader=_DuplicateSafeLoader)
    except CameraPresetConfigError:
        raise
    except (OSError, yaml.YAMLError) as error:
        raise CameraPresetConfigError(f"could not load {config_file}: {error}") from error
    if not isinstance(document, dict):
        raise CameraPresetConfigError("camera preset document must be a mapping")
    _require_exact_fields(document, _ROOT_FIELDS, "root")
    if document["schema_version"] != 1 or isinstance(document["schema_version"], bool):
        raise CameraPresetConfigError("schema_version must be 1")
    records = document["presets"]
    if not isinstance(records, dict) or not records:
        raise CameraPresetConfigError("presets must be a non-empty mapping")

    presets: dict[str, CameraPreset] = {}
    for name, raw_record in records.items():
        if not isinstance(name, str) or not name.strip():
            raise CameraPresetConfigError("preset names must be non-empty strings")
        if not isinstance(raw_record, dict):
            raise CameraPresetConfigError(f"preset {name!r} must be a mapping")
        mode = raw_record.get("mode")
        if mode == "free":
            presets[name] = _parse_free(name, raw_record)
        elif mode == "fixed":
            presets[name] = _parse_fixed(name, raw_record)
        else:
            raise CameraPresetConfigError(f"preset {name!r} has unsupported mode: {mode!r}")
    return presets


def preset_to_yaml_fields(preset: CameraPreset) -> dict[str, object]:
    """Convert a typed preset to its mode-specific YAML mapping."""
    if isinstance(preset, FreeCameraPreset):
        return {
            "mode": "free",
            "lookat": list(preset.lookat),
            "distance": preset.distance,
            "azimuth_deg": preset.azimuth_deg,
            "elevation_deg": preset.elevation_deg,
            "orthographic": preset.orthographic,
        }
    return {"mode": "fixed", "fixed_camera_name": preset.fixed_camera_name}
