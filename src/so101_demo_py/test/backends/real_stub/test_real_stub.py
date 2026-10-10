"""The v1 real-arm extension boundary must be fail-closed and zero-I/O."""

from __future__ import annotations

import builtins
import socket
import subprocess

import pytest
from so101_demo.core.domain import ExecutionRunStatus


@pytest.fixture
def io_spies(monkeypatch):
    calls: list[str] = []

    def reject(name):
        def _rejected(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"real stub attempted I/O through {name}")

        return _rejected

    monkeypatch.setattr(builtins, "open", reject("open"))
    monkeypatch.setattr(socket, "socket", reject("socket"))
    monkeypatch.setattr(subprocess, "Popen", reject("subprocess"))
    return calls


@pytest.mark.parametrize(
    "operation",
    [
        "readiness",
        "plan_joint_waypoints",
        "plan_tcp_motion",
        "execute",
        "command_gripper",
        "reset",
        "stop",
        "recover",
    ],
)
def test_every_real_operation_rejects_without_io(operation, io_spies):
    from so101_demo.backends.real_stub.backend import RealStubBackend

    backend = RealStubBackend()
    result = getattr(backend, operation)(None)
    assert result.error_code == "REAL_HARDWARE_NOT_CONFIGURED"
    assert result.run_status is ExecutionRunStatus.REJECTED
    assert result.accepted is False
    assert io_spies == []


def test_safety_configuration_is_parsed_without_device_access():
    from so101_demo.backends.real_stub.safety import parse_safety_configuration

    safety = parse_safety_configuration(
        {
            "execution_allowed": False,
            "readiness_error_code": "REAL_HARDWARE_NOT_CONFIGURED",
            "safety": {
                "device_access_allowed": False,
                "ros_control_io_allowed": False,
            },
        }
    )
    assert safety.device_access_allowed is False
    assert safety.ros_control_io_allowed is False


def test_real_stub_declares_no_runtime_capabilities():
    from so101_demo.runtime.composition import backend_capabilities

    capabilities = backend_capabilities("real_stub")
    assert not any(
        getattr(capabilities, field)
        for field in (
            "atomic_snapshot",
            "snapshot_with_receipt",
            "reset_epoch",
            "pause",
            "viewer_camera",
            "physical_contact_force",
            "lossless_physics_step_trace",
        )
    )
