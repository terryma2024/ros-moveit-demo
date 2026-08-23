import json
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1]


def test_shared_schema_loads_mujoco_and_gazebo_backend_presets() -> None:
    from so101_demo.core.camera import (
        FreeCameraPreset,
        PoseCameraPreset,
        load_camera_presets,
    )

    mujoco = load_camera_presets(PACKAGE / "config/mujoco/camera_views.yaml")
    gazebo = load_camera_presets(PACKAGE / "config/gazebo/camera_views.yaml")

    assert isinstance(mujoco["table_corner_nw"], FreeCameraPreset)
    assert isinstance(gazebo["overview"], PoseCameraPreset)
    assert gazebo["overview"].position == (0.6224652, -0.2052773, 0.3231955)
    assert len(gazebo["overview"].orientation_xyzw) == 4


def test_mujoco_compatibility_module_reexports_shared_types() -> None:
    from so101_demo.backends.mujoco import camera_presets as compatibility
    from so101_demo.core import camera

    assert compatibility.FreeCameraPreset is camera.FreeCameraPreset
    assert compatibility.FixedCameraPreset is camera.FixedCameraPreset
    assert compatibility.load_camera_presets is camera.load_camera_presets


def test_shared_schema_rejects_unknown_fields_with_stable_code(tmp_path: Path) -> None:
    from so101_demo.core.camera import CameraPresetConfigError, load_camera_presets

    config = tmp_path / "camera.yaml"
    config.write_text(
        "schema_version: 1\npresets:\n  bad:\n    mode: pose\n"
        "    position: [0, 0, 1]\n    orientation_xyzw: [0, 0, 0, 1]\n"
        "    fov: 1.2\n",
        encoding="utf-8",
    )

    with pytest.raises(CameraPresetConfigError, match="CAMERA_PRESET_INVALID"):
        load_camera_presets(config)


def test_cli_defaults_to_mujoco_and_accepts_explicit_gazebo(monkeypatch, capsys) -> None:
    from so101_demo.cli import camera_preset
    from so101_demo.core.camera import CameraCommandReceipt

    calls = []

    def execute(backend: str, preset: str) -> CameraCommandReceipt:
        calls.append((backend, preset))
        return CameraCommandReceipt(
            backend=backend,
            preset=preset,
            phase="READ_BACK" if backend == "mujoco" else "ACKNOWLEDGE",
            success=True,
            failure_code=None,
            evidence={"acknowledged": True},
        )

    monkeypatch.setattr(camera_preset, "execute_camera_command", execute)

    assert camera_preset.main(["table_corner_nw"]) == 0
    assert json.loads(capsys.readouterr().out)["backend"] == "mujoco"
    assert camera_preset.main(["--backend", "gazebo", "overview"]) == 0
    assert json.loads(capsys.readouterr().out)["backend"] == "gazebo"
    assert calls == [("mujoco", "table_corner_nw"), ("gazebo", "overview")]


def test_cli_unknown_preset_returns_stable_nonzero_receipt(capsys) -> None:
    from so101_demo.cli import camera_preset

    assert camera_preset.main(["--backend", "gazebo", "not-a-preset"]) == 2
    document = json.loads(capsys.readouterr().out)
    assert document["failure_code"] == "CAMERA_PRESET_UNKNOWN"
