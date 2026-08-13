import os
import subprocess

import pytest


def _preset():
    from so101_demo.core.camera import PoseCameraPreset

    return PoseCameraPreset(
        name="overview",
        position=(0.6, -0.2, 0.3),
        orientation_xyzw=(0.0, 0.0, 1.0, 0.0),
    )


def test_gazebo_camera_calls_gui_pose_service_and_validates_ack(monkeypatch) -> None:
    from so101_demo.backends.gazebo.camera import GazeboCameraGateway

    monkeypatch.setenv("GZ_PARTITION", "camera-contract")
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "data: true\n", "")

    receipt = GazeboCameraGateway(runner=run).apply(_preset())

    assert receipt.success
    assert receipt.phase == "ACKNOWLEDGE"
    assert receipt.evidence["acknowledged"] is True
    argv, kwargs = calls[0]
    assert argv[:4] == ["gz", "service", "-s", "/gui/move_to/pose"]
    assert "gz.msgs.GUICamera" in argv
    assert "gz.msgs.Boolean" in argv
    assert "position" in argv[-1] and "orientation" in argv[-1]
    assert kwargs["shell"] is False
    assert kwargs["env"]["GZ_PARTITION"] == "camera-contract"


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (subprocess.CompletedProcess([], 1, "", "transport failed"), "CAMERA_TRANSPORT_FAILED"),
        (subprocess.CompletedProcess([], 0, "data: false\n", ""), "CAMERA_ACK_REJECTED"),
        (subprocess.CompletedProcess([], 0, "not boolean\n", ""), "CAMERA_ACK_INVALID"),
    ],
)
def test_gazebo_camera_maps_transport_and_ack_failures(result, code: str) -> None:
    from so101_demo.backends.gazebo.camera import CameraAdapterError, GazeboCameraGateway

    gateway = GazeboCameraGateway(runner=lambda *_args, **_kwargs: result)
    with pytest.raises(CameraAdapterError) as raised:
        gateway.apply(_preset())
    assert raised.value.code == code


def test_gazebo_camera_maps_timeout_and_missing_executable() -> None:
    from so101_demo.backends.gazebo.camera import CameraAdapterError, GazeboCameraGateway

    failures = (
        (subprocess.TimeoutExpired("gz", 5.0), "CAMERA_SERVICE_TIMEOUT"),
        (FileNotFoundError("gz"), "CAMERA_SERVICE_UNAVAILABLE"),
    )
    for failure, code in failures:
        def run(*_args, _failure=failure, **_kwargs):
            raise _failure

        with pytest.raises(CameraAdapterError) as raised:
            GazeboCameraGateway(runner=run).apply(_preset())
        assert raised.value.code == code


def test_gazebo_camera_runner_receives_an_environment_copy() -> None:
    from so101_demo.backends.gazebo.camera import GazeboCameraGateway

    environments = []

    def run(argv, **kwargs):
        environments.append(kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, "data: true\n", "")

    GazeboCameraGateway(runner=run).apply(_preset())

    assert environments[0] == os.environ
    assert environments[0] is not os.environ
