"""Gazebo GUI camera preset loading and transport-service control."""

from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import yaml


@dataclass(frozen=True)
class CameraPreset:
    position: tuple[float, float, float]
    rpy: tuple[float, float, float]


def _vector(value: object, field: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"CAMERA_PRESET_INVALID: {field} must contain three numbers")
    try:
        parsed = tuple(float(item) for item in value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"CAMERA_PRESET_INVALID: {field} must contain three numbers") from error
    if not all(math.isfinite(item) for item in parsed):
        raise ValueError(f"CAMERA_PRESET_INVALID: {field} must be finite")
    return parsed


def load_camera_presets(path: str | Path) -> dict[str, CameraPreset]:
    source = Path(path)
    payload = yaml.safe_load(source.read_text())
    views = payload.get("camera_views") if isinstance(payload, dict) else None
    if not isinstance(views, dict) or not views:
        raise ValueError("CAMERA_PRESET_INVALID: camera_views must be a non-empty mapping")
    presets: dict[str, CameraPreset] = {}
    for name, value in views.items():
        if not isinstance(name, str) or not name or not isinstance(value, dict):
            raise ValueError("CAMERA_PRESET_INVALID: invalid preset entry")
        if set(value) != {"position", "rpy"}:
            raise ValueError(f"CAMERA_PRESET_INVALID: {name} supports only position and rpy")
        presets[name] = CameraPreset(
            position=_vector(value["position"], f"{name}.position"),
            rpy=_vector(value["rpy"], f"{name}.rpy"),
        )
    return presets


def _quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


class CameraController:
    def __init__(
        self,
        presets: Mapping[str, CameraPreset],
        runner: Callable[..., object] = subprocess.run,
    ) -> None:
        self._presets = dict(presets)
        self._runner = runner

    @property
    def names(self) -> list[str]:
        return list(self._presets)

    def apply(self, name: str) -> None:
        preset = self._presets.get(name)
        if preset is None:
            raise RuntimeError("CAMERA_PRESET_NOT_FOUND")
        x, y, z = preset.position
        qx, qy, qz, qw = _quaternion_from_rpy(*preset.rpy)
        request = (
            "pose: {"
            f" position: {{x: {x}, y: {y}, z: {z}}}"
            f" orientation: {{x: {qx}, y: {qy}, z: {qz}, w: {qw}}}"
            " }"
        )
        try:
            result = self._runner(
                [
                    "gz", "service", "-s", "/gui/move_to/pose",
                    "--reqtype", "gz.msgs.GUICamera",
                    "--reptype", "gz.msgs.Boolean",
                    "--timeout", "3000",
                    "--req", request,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("GAZEBO_CAMERA_SERVICE_UNAVAILABLE") from error
        if result.returncode != 0 or "data: true" not in result.stdout:
            raise RuntimeError("GAZEBO_CAMERA_SERVICE_UNAVAILABLE")
