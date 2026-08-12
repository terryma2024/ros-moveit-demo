"""Apply an installed MuJoCo viewer camera preset with readback validation."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from ..backends.mujoco.camera_presets import (
    FixedCameraPreset,
    FreeCameraPreset,
    load_camera_presets,
)
from ..backends.mujoco.viewer import (
    FixedViewerCameraState,
    FreeViewerCameraState,
    RosViewerCameraGateway,
    ViewerCameraServiceError,
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


def main(arguments: list[str] | None = None) -> int:
    if arguments is None:
        arguments = sys.argv[1:]
    if len(arguments) != 1:
        print("usage: camera_preset PRESET", file=sys.stderr)
        return 2
    share = Path(get_package_share_directory("so101_demo_py"))
    presets = load_camera_presets(share / "config/mujoco/camera_views.yaml")
    preset = presets.get(arguments[0])
    if preset is None:
        print(f"unknown preset: {arguments[0]}", file=sys.stderr)
        return 2
    gateway = None
    try:
        gateway = RosViewerCameraGateway()
        gateway.set_camera(preset)
        if not _matches(preset, gateway.get_camera()):
            print("viewer camera readback mismatch", file=sys.stderr)
            return 1
    except ViewerCameraServiceError as error:
        print(f"viewer camera error: {error}", file=sys.stderr)
        return 1
    finally:
        if gateway is not None:
            gateway.close()
    return 0
