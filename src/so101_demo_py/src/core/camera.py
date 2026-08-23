"""Shared strict camera preset schema, receipt, and stable configuration errors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import yaml


class CameraPresetConfigError(ValueError):
    def __init__(self, message: str) -> None:
        if not message.startswith("CAMERA_PRESET_INVALID"):
            message = f"CAMERA_PRESET_INVALID: {message}"
        super().__init__(message)


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


@dataclass(frozen=True, slots=True)
class FreeCameraPreset:
    name: str
    lookat: tuple[float, float, float]
    distance: float
    azimuth_deg: float
    elevation_deg: float
    orthographic: bool


@dataclass(frozen=True, slots=True)
class FixedCameraPreset:
    name: str
    fixed_camera_name: str


@dataclass(frozen=True, slots=True)
class PoseCameraPreset:
    name: str
    position: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]


CameraPreset: TypeAlias = FreeCameraPreset | FixedCameraPreset | PoseCameraPreset


@dataclass(frozen=True, slots=True)
class CameraCommandReceipt:
    backend: str
    preset: str
    phase: str
    success: bool
    failure_code: str | None
    evidence: dict[str, object]

    def __post_init__(self) -> None:
        if not self.backend or not self.preset or not self.phase:
            raise ValueError("camera receipt identity must be non-empty")
        if self.success == (self.failure_code is not None):
            raise ValueError("camera receipt success and failure code disagree")


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
_POSE_FIELDS = {"mode", "position", "orientation_xyzw"}


def normalize_azimuth(degrees: float) -> float:
    return (degrees + 180.0) % 360.0 - 180.0


def circular_azimuth_distance(left: float, right: float) -> float:
    return abs(normalize_azimuth(left - right))


def _require_exact_fields(
    record: dict[object, object], expected: set[str], context: str
) -> None:
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


def _vector(value: object, length: int, context: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise CameraPresetConfigError(f"{context} must contain {length} numbers")
    return tuple(
        _finite_number(item, f"{context}[{index}]")
        for index, item in enumerate(value)
    )


def _parse_free(name: str, record: dict[object, object]) -> FreeCameraPreset:
    _require_exact_fields(record, _FREE_FIELDS, f"preset {name!r}")
    lookat = _vector(record["lookat"], 3, f"preset {name!r} lookat")
    distance = _finite_number(record["distance"], f"preset {name!r} distance")
    if distance <= 0.0:
        raise CameraPresetConfigError(f"preset {name!r} distance must be positive")
    azimuth = _finite_number(record["azimuth_deg"], f"preset {name!r} azimuth_deg")
    elevation = _finite_number(
        record["elevation_deg"], f"preset {name!r} elevation_deg"
    )
    if not -90.0 < elevation < 90.0:
        raise CameraPresetConfigError(
            f"preset {name!r} elevation_deg must be in (-90, 90)"
        )
    orthographic = record["orthographic"]
    if not isinstance(orthographic, bool):
        raise CameraPresetConfigError(
            f"preset {name!r} orthographic must be a boolean"
        )
    return FreeCameraPreset(
        name=name,
        lookat=lookat,  # type: ignore[arg-type]
        distance=distance,
        azimuth_deg=normalize_azimuth(azimuth),
        elevation_deg=elevation,
        orthographic=orthographic,
    )


def _parse_fixed(name: str, record: dict[object, object]) -> FixedCameraPreset:
    _require_exact_fields(record, _FIXED_FIELDS, f"preset {name!r}")
    fixed_camera_name = record["fixed_camera_name"]
    if not isinstance(fixed_camera_name, str) or not fixed_camera_name.strip():
        raise CameraPresetConfigError(
            f"preset {name!r} fixed_camera_name must be non-empty"
        )
    return FixedCameraPreset(name=name, fixed_camera_name=fixed_camera_name)


def _parse_pose(name: str, record: dict[object, object]) -> PoseCameraPreset:
    _require_exact_fields(record, _POSE_FIELDS, f"preset {name!r}")
    position = _vector(record["position"], 3, f"preset {name!r} position")
    orientation = _vector(
        record["orientation_xyzw"], 4, f"preset {name!r} orientation_xyzw"
    )
    norm = math.sqrt(sum(value * value for value in orientation))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise CameraPresetConfigError(
            f"preset {name!r} orientation_xyzw must be normalized"
        )
    return PoseCameraPreset(
        name=name,
        position=position,  # type: ignore[arg-type]
        orientation_xyzw=orientation,  # type: ignore[arg-type]
    )


def load_camera_presets(config_file: Path) -> dict[str, CameraPreset]:
    try:
        document = yaml.load(
            config_file.read_text(encoding="utf-8"), Loader=_DuplicateSafeLoader
        )
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
        elif mode == "pose":
            presets[name] = _parse_pose(name, raw_record)
        else:
            raise CameraPresetConfigError(
                f"preset {name!r} has unsupported mode: {mode!r}"
            )
    return presets


def preset_to_yaml_fields(preset: CameraPreset) -> dict[str, object]:
    if isinstance(preset, FreeCameraPreset):
        return {
            "mode": "free",
            "lookat": list(preset.lookat),
            "distance": preset.distance,
            "azimuth_deg": preset.azimuth_deg,
            "elevation_deg": preset.elevation_deg,
            "orthographic": preset.orthographic,
        }
    if isinstance(preset, FixedCameraPreset):
        return {"mode": "fixed", "fixed_camera_name": preset.fixed_camera_name}
    return {
        "mode": "pose",
        "position": list(preset.position),
        "orientation_xyzw": list(preset.orientation_xyzw),
    }
