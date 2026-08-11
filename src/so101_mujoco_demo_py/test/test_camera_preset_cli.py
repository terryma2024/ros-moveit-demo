from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py import camera_preset_cli
from so101_mujoco_demo_py.camera_presets import FixedCameraPreset, FreeCameraPreset
from so101_mujoco_demo_py.viewer_camera_client import (
    FixedViewerCameraState,
    FreeViewerCameraState,
    ViewerCameraServiceError,
    viewer_camera_state_to_yaml_fields,
)


class FakeGateway:
    def __init__(
        self,
        *,
        set_state=None,
        get_state=None,
        set_failure: Exception | None = None,
        get_failure: Exception | None = None,
    ) -> None:
        self.set_state = set_state or FreeViewerCameraState((9.0, 9.0, 9.0), 9.0, 9.0, 9.0, True)
        self.get_state = get_state or FreeViewerCameraState(
            (0.0, 0.1, 0.2), 1.2, 135.0, -25.0, False
        )
        self.set_failure = set_failure
        self.get_failure = get_failure
        self.set_calls: list[object] = []
        self.get_calls = 0
        self.calls: list[str] = []
        self.closed = False

    def set_camera(self, preset):
        self.calls.append("set")
        self.set_calls.append(preset)
        if self.set_failure:
            raise self.set_failure
        return self.set_state

    def get_camera(self):
        self.calls.append("get")
        self.get_calls += 1
        if self.get_failure:
            raise self.get_failure
        return self.get_state

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


def test_apply_sets_once_then_independently_gets_and_prints_readback_state(
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
    assert gateway.calls == ["set", "get"]
    assert gateway.get_calls == 1
    output = capsys.readouterr().out
    assert "lookat=0.0,0.1,0.2" in output
    assert "distance=1.2" in output
    assert gateway.closed is True


def test_current_does_not_read_config_and_closes_gateway(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeGateway(get_state=FixedViewerCameraState("inspection_camera"))

    result = camera_preset_cli.run(
        ["--current"], gateway_factory=lambda: gateway, config_file=tmp_path / "missing.yaml"
    )

    assert result == 0
    assert gateway.get_calls == 1
    assert gateway.calls == ["get"]
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
    gateway = FakeGateway(get_state=FixedViewerCameraState("inspection_camera"))

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
    "failure_stage, failure",
    [
        ("set", ViewerCameraServiceError("set service unavailable after 3.0 seconds")),
        ("set", ViewerCameraServiceError("set service response timed out after 3.0 seconds")),
        ("get", ViewerCameraServiceError("get service unavailable after 3.0 seconds")),
    ],
)
def test_gateway_failures_are_actionable_nonzero_and_always_close(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure_stage: str,
    failure: Exception,
) -> None:
    gateway = FakeGateway(
        set_failure=failure if failure_stage == "set" else None,
        get_failure=failure if failure_stage == "get" else None,
    )

    result = camera_preset_cli.run(
        ["table_corner_nw"], gateway_factory=lambda: gateway, config_file=camera_config(tmp_path)
    )

    assert result == 1
    assert str(failure) in capsys.readouterr().err
    assert gateway.closed is True


@pytest.mark.parametrize(
    "preset_name, readback",
    [
        ("table_corner_nw", FixedViewerCameraState("inspection_camera")),
        ("inspection", FreeViewerCameraState((0.0, 0.1, 0.2), 1.2, 135.0, -25.0, False)),
    ],
)
def test_apply_returns_nonzero_for_free_fixed_readback_type_mismatch_and_closes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    preset_name: str,
    readback,
) -> None:
    gateway = FakeGateway(get_state=readback)

    result = camera_preset_cli.run(
        [preset_name], gateway_factory=lambda: gateway, config_file=camera_config(tmp_path)
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "readback mismatch" in captured.err
    assert (
        f"mode={'fixed' if isinstance(readback, FixedViewerCameraState) else 'free'}"
        in captured.out
    )
    assert gateway.calls == ["set", "get"]
    assert gateway.closed is True


@pytest.mark.parametrize(
    "readback",
    [
        FreeViewerCameraState((0.0, 0.1, 0.201), 1.2, 135.0, -25.0, False),
        FreeViewerCameraState((0.0, 0.1, 0.2), 1.201, 135.0, -25.0, False),
        FreeViewerCameraState((0.0, 0.1, 0.2), 1.2, 135.001, -25.0, False),
        FreeViewerCameraState((0.0, 0.1, 0.2), 1.2, 135.0, -24.999, False),
    ],
)
def test_apply_returns_nonzero_for_out_of_tolerance_float_readback_and_closes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    readback: FreeViewerCameraState,
) -> None:
    gateway = FakeGateway(get_state=readback)

    result = camera_preset_cli.run(
        ["table_corner_nw"], gateway_factory=lambda: gateway, config_file=camera_config(tmp_path)
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "readback mismatch" in captured.err
    assert "mode=free" in captured.out
    assert gateway.calls == ["set", "get"]
    assert gateway.closed is True


@pytest.mark.parametrize(
    "preset_name, readback",
    [
        (
            "table_corner_nw",
            FreeViewerCameraState((0.0, 0.1, 0.2), 1.2, 135.0, -25.0, True),
        ),
        ("inspection", FixedViewerCameraState("different_camera")),
    ],
)
def test_apply_returns_nonzero_for_typed_field_readback_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    preset_name: str,
    readback,
) -> None:
    gateway = FakeGateway(get_state=readback)

    result = camera_preset_cli.run(
        [preset_name], gateway_factory=lambda: gateway, config_file=camera_config(tmp_path)
    )

    assert result == 1
    assert "readback mismatch" in capsys.readouterr().err
    assert gateway.closed is True


def test_apply_accepts_bounded_float_rounding_and_fixed_name_match(
    tmp_path: Path,
) -> None:
    free_gateway = FakeGateway(
        get_state=FreeViewerCameraState(
            (0.0 + 5e-10, 0.1 - 5e-10, 0.2 + 5e-10),
            1.2 - 5e-10,
            135.0 + 5e-10,
            -25.0 - 5e-10,
            False,
        )
    )
    fixed_gateway = FakeGateway(get_state=FixedViewerCameraState("inspection_camera"))

    assert (
        camera_preset_cli.run(
            ["table_corner_nw"],
            gateway_factory=lambda: free_gateway,
            config_file=camera_config(tmp_path),
        )
        == 0
    )
    assert (
        camera_preset_cli.run(
            ["inspection"],
            gateway_factory=lambda: fixed_gateway,
            config_file=camera_config(tmp_path),
        )
        == 0
    )
    assert fixed_gateway.set_calls == [FixedCameraPreset("inspection", "inspection_camera")]
    assert free_gateway.closed is True
    assert fixed_gateway.closed is True
