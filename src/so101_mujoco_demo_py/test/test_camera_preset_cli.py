from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py import camera_preset_cli
from so101_mujoco_demo_py.camera_presets import FreeCameraPreset
from so101_mujoco_demo_py.viewer_camera_client import (
    FixedViewerCameraState,
    FreeViewerCameraState,
    ViewerCameraServiceError,
    viewer_camera_state_to_yaml_fields,
)


class FakeGateway:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.set_calls: list[object] = []
        self.get_calls = 0
        self.closed = False

    def set_camera(self, preset):
        self.set_calls.append(preset)
        if self.failure:
            raise self.failure
        return FreeViewerCameraState((0.0, 0.1, 0.2), 1.2, 135.0, -25.0, False)

    def get_camera(self):
        self.get_calls += 1
        if self.failure:
            raise self.failure
        return FixedViewerCameraState("inspection_camera")

    def close(self) -> None:
        self.closed = True


def camera_config(tmp_path: Path) -> Path:
    config = tmp_path / "camera_views.yaml"
    config.write_text(
        """schema_version: 1
presets:
  table_corner_nw:
    mode: free
    lookat: [0.0, 0.1, 0.2]
    distance: 1.2
    azimuth_deg: 135.0
    elevation_deg: -25.0
    orthographic: false
  inspection:
    mode: fixed
    fixed_camera_name: inspection_camera
""",
        encoding="utf-8",
    )
    return config


def test_list_preserves_yaml_order_without_constructing_gateway(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    constructed = False

    def forbidden_factory():
        nonlocal constructed
        constructed = True
        raise AssertionError("--list must remain ROS-free")

    result = camera_preset_cli.run(
        ["--list"], gateway_factory=forbidden_factory, config_file=camera_config(tmp_path)
    )

    assert result == 0
    assert capsys.readouterr().out.splitlines() == ["table_corner_nw", "inspection"]
    assert constructed is False


def test_apply_passes_typed_preset_and_prints_applied_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeGateway()

    result = camera_preset_cli.run(
        ["table_corner_nw"], gateway_factory=lambda: gateway, config_file=camera_config(tmp_path)
    )

    assert result == 0
    assert gateway.set_calls == [
        FreeCameraPreset("table_corner_nw", (0.0, 0.1, 0.2), 1.2, 135.0, -25.0, False)
    ]
    assert "mode=free" in capsys.readouterr().out
    assert gateway.closed is True


def test_current_does_not_read_config_and_closes_gateway(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeGateway()

    result = camera_preset_cli.run(
        ["--current"], gateway_factory=lambda: gateway, config_file=tmp_path / "missing.yaml"
    )

    assert result == 0
    assert gateway.get_calls == 1
    assert "fixed_camera_name=inspection_camera" in capsys.readouterr().out
    assert gateway.closed is True


@pytest.mark.parametrize(
    "state, expected",
    [
        (
            FreeViewerCameraState((1.0, 2.0, 3.0), 2.0, -45.0, -30.0, True),
            {
                "mode": "free",
                "lookat": [1.0, 2.0, 3.0],
                "distance": 2.0,
                "azimuth_deg": -45.0,
                "elevation_deg": -30.0,
                "orthographic": True,
            },
        ),
        (
            FixedViewerCameraState("inspection_camera"),
            {"mode": "fixed", "fixed_camera_name": "inspection_camera"},
        ),
    ],
)
def test_viewer_camera_state_to_yaml_fields_emits_mode_specific_mapping(state, expected) -> None:
    assert viewer_camera_state_to_yaml_fields(state) == expected


def test_current_yaml_is_copyable_mapping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeGateway()

    result = camera_preset_cli.run(
        ["--current", "--format", "yaml"],
        gateway_factory=lambda: gateway,
        config_file=tmp_path / "missing.yaml",
    )

    assert result == 0
    assert yaml.safe_load(capsys.readouterr().out) == {
        "mode": "fixed",
        "fixed_camera_name": "inspection_camera",
    }
    assert gateway.closed is True


def test_unknown_preset_and_invalid_config_exit_two_before_gateway(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    constructions = 0

    def factory():
        nonlocal constructions
        constructions += 1
        return FakeGateway()

    config = camera_config(tmp_path)
    assert camera_preset_cli.run(["missing"], gateway_factory=factory, config_file=config) == 2
    assert "unknown preset" in capsys.readouterr().err
    config.write_text("schema_version: 1\npresets: []\n", encoding="utf-8")
    assert camera_preset_cli.run(["--list"], gateway_factory=factory, config_file=config) == 2
    assert "presets must be" in capsys.readouterr().err
    assert constructions == 0


@pytest.mark.parametrize(
    "failure",
    [
        ViewerCameraServiceError("set service unavailable after 3.0 seconds"),
        ViewerCameraServiceError("set service response timed out after 3.0 seconds"),
        ViewerCameraServiceError("viewer unavailable"),
    ],
)
def test_gateway_failures_are_actionable_nonzero_and_always_close(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    gateway = FakeGateway(failure=failure)

    result = camera_preset_cli.run(
        ["table_corner_nw"], gateway_factory=lambda: gateway, config_file=camera_config(tmp_path)
    )

    assert result == 1
    assert str(failure) in capsys.readouterr().err
    assert gateway.closed is True
