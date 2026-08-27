import asyncio
from pathlib import Path

import pytest

from so101_teleop.backends.registry import load_backend_profile
from so101_teleop.backends.protocol import BackendOperation
from so101_teleop.models import ServerMode, TelemetrySnapshot
from so101_teleop.server import TeleopService


PACKAGE = Path(__file__).resolve().parents[2]


class Worker:
    def __init__(self):
        self._plans = {}
        self.calls = []
        self._snapshot = TelemetrySnapshot(
            mode=ServerMode.READY,
            simulation_session_id="sim-a",
            revision=1,
        )

    def snapshot(self):
        return self._snapshot

    def __getattr__(self, name):
        def unexpected(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            raise AssertionError(f"worker side effect reached: {name}")
        return unexpected


class ProbeOnlyBackend:
    def __init__(self):
        self.profile = load_backend_profile("mujoco_py", PACKAGE)
        self.calls = []

    def capabilities(self):
        return self.profile.capabilities

    def run_workflow(self, request):
        self.calls.append(("workflow", request))
        raise AssertionError("workflow subprocess boundary reached")

    def reset_world(self, request):
        self.calls.append(("reset", request))
        raise AssertionError("reset subprocess boundary reached")

    def scene_operation(self, request):
        self.calls.append(("scene", request))
        raise AssertionError("scene subprocess boundary reached")


async def run_command(name, body):
    worker = Worker()
    backend = ProbeOnlyBackend()
    service = TeleopService(worker, backend=backend)
    lease = await service.command("lease", {"command_id": "lease"})
    result = await service.command(name, {
        "command_id": "forbidden",
        "lease_id": lease.layers["lease_id"],
        "session_id": "sim-a",
        **body,
    })
    return result, worker, backend, service


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("workflow_start", {}),
        ("workflow_resume", {"run_id": "missing"}),
        ("scene_repair", {"confirmation": "CONFIRM SCENE_REPAIR"}),
        ("attachment_attach", {}),
        ("plan_joints", {"target_joints_rad": {"1": 0.0}}),
        ("plan_tcp", {"target": {}}),
        ("execute", {"plan_id": "missing"}),
        ("gripper", {"target_position_rad": 0.0}),
        ("robot_home", {"confirmation": "CONFIRM ROBOT_HOME"}),
        ("screenshot", {}),
    ],
)
def test_probe_only_backend_rejects_every_live_operation_before_side_effects(
        name, body):
    result, worker, backend, service = asyncio.run(run_command(name, body))

    assert result.succeeded is False
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert worker.calls == []
    assert backend.calls == []
    assert service._workflow == {}


def test_mujoco_profile_pins_formal_owner_operations():
    profile = load_backend_profile("mujoco_py", PACKAGE)

    assert profile.owner_package == "so101_demo_py"
    assert profile.probe.package == "so101_demo_py"
    assert profile.probe.executable == "teleop_workflow"
    assert profile.capabilities.workflow_run is True
    assert profile.capabilities.reset_world is True
    assert profile.capabilities.camera_presets is True
    assert profile.capabilities.workflow_start is False
    assert profile.operations[BackendOperation.WORKFLOW].executable == "teleop_workflow"
    assert profile.operations[BackendOperation.RESET_WORLD].executable == "teleop_reset"
    assert profile.operations[BackendOperation.CAMERA_PRESET].executable == "camera_preset"
    assert profile.camera_presets == (
        "table_corner_nw", "table_corner_ne", "table_corner_se",
        "table_corner_sw", "top_down",
    )
