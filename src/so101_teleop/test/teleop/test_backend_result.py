from types import SimpleNamespace

from so101_teleop.backends.protocol import BackendEnvelope, BackendError
from so101_teleop.server import TeleopService


def test_backend_failure_omits_absent_owner_failure_code() -> None:
    service = object.__new__(TeleopService)
    service._worker = SimpleNamespace(snapshot=lambda: SimpleNamespace(revision=7))
    envelope = BackendEnvelope(
        ok=False,
        backend="mujoco_py",
        operation="reset_world",
        session_id="session",
        owner_package="so101_demo_py",
        owner_executable="teleop_reset",
        exit_code=1,
        error=BackendError("BACKEND_OPERATION_FAILED", "owner exited with 1"),
    )

    result = service._backend_result({"command_id": "reset-4"}, envelope)

    assert result.code == "BACKEND_OPERATION_FAILED"
    assert result.layers == {
        "backend": "mujoco_py",
        "owner_package": "so101_demo_py",
        "owner_executable": "teleop_reset",
    }
