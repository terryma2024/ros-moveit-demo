from __future__ import annotations

import math
from pathlib import Path

import pytest

from so101_mujoco_demo_py.camera_presets import (
    CameraPresetConfigError,
    FixedCameraPreset,
    FreeCameraPreset,
    circular_azimuth_distance,
    load_camera_presets,
    normalize_azimuth,
    preset_to_yaml_fields,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CONFIG = PACKAGE_ROOT / "config/camera_views.yaml"


def write_config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "camera_views.yaml"
    config.write_text(body, encoding="utf-8")
    return config


def valid_free_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "mode": "free",
        "lookat": [0.1, -0.2, 0.3],
        "distance": 1.2,
        "azimuth_deg": 225.0,
        "elevation_deg": -25.0,
        "orthographic": False,
    }
    body.update(overrides)
    return body


def dump_single(tmp_path: Path, body: dict[str, object]) -> Path:
    import yaml

    return write_config(
        tmp_path,
        yaml.safe_dump({"schema_version": 1, "presets": {"view": body}}, sort_keys=False),
    )


def test_loads_free_and_fixed_presets_in_yaml_order(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """schema_version: 1
presets:
  table_corner_nw:
    mode: free
    lookat: [0.1, -0.2, 0.3]
    distance: 1.2
    azimuth_deg: 225.0
    elevation_deg: -25.0
    orthographic: false
  inspection:
    mode: fixed
    fixed_camera_name: inspection_camera
""",
    )

    presets = load_camera_presets(config)

    assert list(presets) == ["table_corner_nw", "inspection"]
    assert presets["table_corner_nw"] == FreeCameraPreset(
        name="table_corner_nw",
        lookat=(0.1, -0.2, 0.3),
        distance=1.2,
        azimuth_deg=-135.0,
        elevation_deg=-25.0,
        orthographic=False,
    )
    assert presets["inspection"] == FixedCameraPreset(
        name="inspection", fixed_camera_name="inspection_camera"
    )


@pytest.mark.parametrize("degrees, expected", [(180.0, -180.0), (-180.0, -180.0), (540.0, -180.0)])
def test_normalize_azimuth_uses_half_open_range(degrees: float, expected: float) -> None:
    assert normalize_azimuth(degrees) == expected


def test_circular_distance_is_shortest_unsigned_angle() -> None:
    assert circular_azimuth_distance(170.0, -170.0) == 20.0
    assert circular_azimuth_distance(-135.0, 135.0) == 90.0


def test_preset_to_yaml_fields_emits_only_mode_specific_fields() -> None:
    free = FreeCameraPreset("free", (1.0, 2.0, 3.0), 2.0, 45.0, -30.0, True)
    fixed = FixedCameraPreset("fixed", "wrist_camera")
    assert preset_to_yaml_fields(free) == {
        "mode": "free",
        "lookat": [1.0, 2.0, 3.0],
        "distance": 2.0,
        "azimuth_deg": 45.0,
        "elevation_deg": -30.0,
        "orthographic": True,
    }
    assert preset_to_yaml_fields(fixed) == {
        "mode": "fixed",
        "fixed_camera_name": "wrist_camera",
    }


@pytest.mark.parametrize(
    "document",
    [
        "schema_version: 1\nschema_version: 1\npresets: {}\n",
        "schema_version: 1\npresets:\n  view: {mode: fixed, fixed_camera_name: one}\n"
        "  view: {mode: fixed, fixed_camera_name: two}\n",
        "schema_version: 1\npresets:\n  view:\n    mode: fixed\n"
        "    fixed_camera_name: one\n    mode: fixed\n",
    ],
)
def test_rejects_duplicate_yaml_keys(tmp_path: Path, document: str) -> None:
    with pytest.raises(CameraPresetConfigError, match="duplicate key"):
        load_camera_presets(write_config(tmp_path, document))


@pytest.mark.parametrize(
    "document",
    [
        "schema_version: 2\npresets: {}\n",
        "schema_version: 1\npresets: {}\nunknown: true\n",
        "schema_version: 1\n",
        "schema_version: 1\npresets: []\n",
        "schema_version: 1\npresets: {}\n",
        "schema_version: 1\npresets:\n  '': {mode: fixed, fixed_camera_name: camera}\n",
    ],
)
def test_rejects_invalid_root_or_preset_mapping(tmp_path: Path, document: str) -> None:
    with pytest.raises(CameraPresetConfigError):
        load_camera_presets(write_config(tmp_path, document))


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "tracking"},
        {"mode": "fixed"},
        {"mode": "fixed", "fixed_camera_name": ""},
        {"mode": "fixed", "fixed_camera_name": "camera", "distance": 1.0},
        {"mode": "free", "lookat": [0.0, 0.0, 0.0]},
        valid_free_body(unknown=True),
        valid_free_body(fixed_camera_name="camera"),
        valid_free_body(lookat=[0.0, 0.0]),
        valid_free_body(lookat=[0.0, 0.0, True]),
        valid_free_body(distance=True),
        valid_free_body(distance=0.0),
        valid_free_body(distance=-1.0),
        valid_free_body(distance=math.inf),
        valid_free_body(azimuth_deg=math.nan),
        valid_free_body(elevation_deg=-90.0),
        valid_free_body(elevation_deg=90.0),
        valid_free_body(orthographic=0),
    ],
)
def test_rejects_invalid_mode_specific_records(tmp_path: Path, body: dict[str, object]) -> None:
    with pytest.raises(CameraPresetConfigError):
        load_camera_presets(dump_single(tmp_path, body))


def test_production_config_has_four_symmetric_table_corner_views() -> None:
    presets = load_camera_presets(PRODUCTION_CONFIG)
    required = [
        "table_corner_nw",
        "table_corner_ne",
        "table_corner_se",
        "table_corner_sw",
    ]
    assert list(presets) == required
    assert all(isinstance(presets[name], FreeCameraPreset) for name in required)
    assert len({presets[name].lookat for name in required}) == 1
    assert len({presets[name].distance for name in required}) == 1
    assert len({presets[name].elevation_deg for name in required}) == 1
    assert len({presets[name].orthographic for name in required}) == 1
    for left, right in zip(required, required[1:] + required[:1], strict=True):
        assert (
            circular_azimuth_distance(
                presets[left].azimuth_deg,
                presets[right].azimuth_deg,
            )
            == 90.0
        )
