"""Compatibility exports for the shared strict camera preset schema."""

from ...core.camera import (
    CameraPreset,
    CameraPresetConfigError,
    FixedCameraPreset,
    FreeCameraPreset,
    circular_azimuth_distance,
    load_camera_presets,
    normalize_azimuth,
    preset_to_yaml_fields,
)

__all__ = (
    "CameraPreset",
    "CameraPresetConfigError",
    "FixedCameraPreset",
    "FreeCameraPreset",
    "circular_azimuth_distance",
    "load_camera_presets",
    "normalize_azimuth",
    "preset_to_yaml_fields",
)
