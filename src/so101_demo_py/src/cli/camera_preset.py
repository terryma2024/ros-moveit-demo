"""Apply a package-owned camera preset through the selected backend."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from ..backends.gazebo.camera import CameraAdapterError, GazeboCameraGateway
from ..backends.mujoco.viewer import (
    FixedViewerCameraState,
    FreeViewerCameraState,
    RosViewerCameraGateway,
    ViewerCameraServiceError,
)
from ..core.camera import (
    CameraCommandReceipt,
    CameraPresetConfigError,
    FixedCameraPreset,
    FreeCameraPreset,
    PoseCameraPreset,
    load_camera_presets,
)


def _matches(preset, state) -> bool:
    if isinstance(preset, FreeCameraPreset) and isinstance(state, FreeViewerCameraState):
        values = (*preset.lookat, preset.distance, preset.azimuth_deg, preset.elevation_deg)
        observed = (*state.lookat, state.distance, state.azimuth_deg, state.elevation_deg)
        return preset.orthographic == state.orthographic and all(
            math.isclose(expected, actual, rel_tol=0.0, abs_tol=1e-9)
            for expected, actual in zip(values, observed, strict=True)
        )
    return (
        isinstance(preset, FixedCameraPreset)
        and isinstance(state, FixedViewerCameraState)
        and preset.fixed_camera_name == state.fixed_camera_name
    )


def _failure(
    backend: str,
    preset: str,
    phase: str,
    code: str,
    evidence: dict[str, object],
) -> CameraCommandReceipt:
    return CameraCommandReceipt(backend, preset, phase, False, code, evidence)


def execute_camera_command(backend: str, preset_name: str) -> CameraCommandReceipt:
    share = Path(get_package_share_directory("so101_demo_py"))
    config = share / f"config/{backend}/camera_views.yaml"
    try:
        presets = load_camera_presets(config)
    except CameraPresetConfigError as error:
        return _failure(
            backend,
            preset_name,
            "LOAD_CONFIG",
            "CAMERA_PRESET_INVALID",
            {"config": str(config), "message": str(error)},
        )
    preset = presets.get(preset_name)
    if preset is None:
        return _failure(
            backend,
            preset_name,
            "SELECT_PRESET",
            "CAMERA_PRESET_UNKNOWN",
            {"available": sorted(presets)},
        )
    if backend == "gazebo":
        if not isinstance(preset, PoseCameraPreset):
            return _failure(
                backend,
                preset_name,
                "LOAD_CONFIG",
                "CAMERA_PRESET_INVALID",
                {"message": "Gazebo requires pose presets"},
            )
        try:
            return GazeboCameraGateway().apply(preset)
        except CameraAdapterError as error:
            return _failure(
                backend,
                preset_name,
                "ACKNOWLEDGE",
                error.code,
                error.evidence,
            )

    if isinstance(preset, PoseCameraPreset):
        return _failure(
            backend,
            preset_name,
            "LOAD_CONFIG",
            "CAMERA_PRESET_INVALID",
            {"message": "MuJoCo requires free or fixed presets"},
        )
    gateway = None
    try:
        gateway = RosViewerCameraGateway()
        gateway.set_camera(preset)
        state = gateway.get_camera()
        if not _matches(preset, state):
            return _failure(
                backend,
                preset_name,
                "READ_BACK",
                "CAMERA_READBACK_MISMATCH",
                {"state_type": type(state).__name__},
            )
        return CameraCommandReceipt(
            backend,
            preset_name,
            "READ_BACK",
            True,
            None,
            {"matched": True},
        )
    except ViewerCameraServiceError as error:
        return _failure(
            backend,
            preset_name,
            "APPLY",
            "CAMERA_SERVICE_FAILED",
            {"message": str(error)},
        )
    finally:
        if gateway is not None:
            gateway.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="camera_preset")
    parser.add_argument("--backend", choices=("mujoco", "gazebo"), default="mujoco")
    parser.add_argument("preset")
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    receipt = execute_camera_command(options.backend, options.preset)
    print(json.dumps(asdict(receipt), sort_keys=True), flush=True)
    if receipt.success:
        return 0
    return 2 if receipt.failure_code == "CAMERA_PRESET_UNKNOWN" else 1
