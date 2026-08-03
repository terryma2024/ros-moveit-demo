from pathlib import Path

import pytest

from so101_teleop.camera import CameraController, CameraPreset, load_camera_presets


def test_load_camera_presets_rejects_unknown_fields(tmp_path: Path):
    config = tmp_path / "camera.yaml"
    config.write_text("camera_views:\n  overview:\n    position: [1, 2, 3]\n    rpy: [0, 0, 0]\n    fov: 1.2\n")

    with pytest.raises(ValueError, match="CAMERA_PRESET_INVALID"):
        load_camera_presets(config)


def test_controller_calls_existing_gui_service_with_same_process_environment():
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "data: true\n", "stderr": ""})()

    controller = CameraController(
        {"overview": CameraPreset(position=(0.8, 1.8, 1.2), rpy=(-0.3, 0.0, -1.8))},
        runner=run,
    )

    controller.apply("overview")

    command, kwargs = calls[0]
    assert command[:4] == ["gz", "service", "-s", "/gui/move_to/pose"]
    assert "gz.msgs.GUICamera" in command
    assert "position" in command[-1]
    assert kwargs["env"] is not None


def test_controller_reports_missing_gui_service_without_false_success():
    def run(*_args, **_kwargs):
        return type("Result", (), {"returncode": 0, "stdout": "data: false\n", "stderr": ""})()

    controller = CameraController(
        {"overview": CameraPreset(position=(0.8, 1.8, 1.2), rpy=(-0.3, 0.0, -1.8))},
        runner=run,
    )

    with pytest.raises(RuntimeError, match="GAZEBO_CAMERA_SERVICE_UNAVAILABLE"):
        controller.apply("overview")
