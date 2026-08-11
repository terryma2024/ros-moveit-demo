import asyncio
from pathlib import Path

from so101_teleop.backends.protocol import BackendEnvelope
from so101_teleop.backends.registry import load_backend_profile
from so101_teleop.models import PlanSummary, ServerMode, TelemetrySnapshot
from so101_teleop.server import StoredTrajectory, TeleopService


PACKAGE = Path(__file__).resolve().parents[2]


class Worker:
    def __init__(self):
        self._plans = {}
        self.cancel_calls = 0
        self._snapshot = TelemetrySnapshot(
            mode=ServerMode.READY,
            simulation_session_id="sim-a",
            revision=7,
        )

    def snapshot(self):
        return self._snapshot

    def invalidate_session(self):
        self._plans.clear()
        self._snapshot.simulation_session_id = "sim-reset"
        return "sim-reset"

    def cancel(self):
        self.cancel_calls += 1


class FakeAdapter:
    def __init__(self, backend):
        self.profile = load_backend_profile(backend, PACKAGE)
        self.calls = []

    def capabilities(self):
        return self.profile.capabilities

    def run_workflow(self, request):
        self.calls.append(("workflow", request))
        return self._success("workflow_run", request.session_id, {"trace": "IDLE -> DONE"})

    def reset_world(self, request):
        self.calls.append(("reset_world", request))
        return self._success("reset_world", request.session_id, {"status": "SUCCEEDED"})

    def scene_operation(self, request):
        self.calls.append(("scene", request))
        return self._success(f"scene_{request.operation}", request.session_id, {"status": "SUCCEEDED"})

    def _success(self, operation, session_id, result):
        spec = self.profile.probe
        return BackendEnvelope(
            ok=True,
            backend=self.profile.backend,
            operation=operation,
            session_id=session_id,
            owner_package=spec.package,
            owner_executable=spec.executable,
            exit_code=0,
            result=result,
        )


async def lease(service):
    result = await service.command("lease", {"command_id": "lease"})
    return result.layers["lease_id"]


def test_capabilities_include_frozen_owner_provenance():
    service = TeleopService(Worker(), backend=FakeAdapter("gazebo_py"))

    payload = asyncio.run(service.capabilities())

    assert payload["backend"] == "gazebo_py"
    assert payload["owner_package"] == "so101_gazebo_demo_py"
    assert payload["capabilities"]["workflow_run"] is True
    assert payload["capabilities"]["scene_operations"] is False


def test_unsupported_workflow_fails_before_run_or_checkpoint():
    adapter = FakeAdapter("mujoco_py")
    service = TeleopService(Worker(), backend=adapter)
    lease_id = asyncio.run(lease(service))

    result = asyncio.run(service.command("workflow_run", {
        "command_id": "run",
        "lease_id": lease_id,
        "session_id": "sim-a",
    }))

    assert result.succeeded is False
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert service._workflow == {}
    assert adapter.calls == []


def test_workflow_stop_fails_closed_without_an_explicit_backend_capability():
    adapter = FakeAdapter("gazebo_cpp")
    service = TeleopService(Worker(), backend=adapter)
    lease_id = asyncio.run(lease(service))
    started = asyncio.run(service.command("workflow_start", {
        "command_id": "start",
        "lease_id": lease_id,
        "session_id": "sim-a",
    }))
    workflow_before = dict(service._workflow)

    result = asyncio.run(service.command("workflow_stop", {
        "command_id": "stop",
        "lease_id": lease_id,
        "session_id": "sim-a",
        "run_id": started.data["workflow"]["run_id"],
    }))

    assert result.succeeded is False
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert result.layers["capability"] == "workflow_stop"
    assert service._workflow == workflow_before
    assert len(adapter.calls) == 1


def test_probe_only_backend_rejects_cancel_before_touching_the_worker():
    adapter = FakeAdapter("mujoco_py")
    worker = Worker()
    service = TeleopService(worker, backend=adapter)
    lease_id = asyncio.run(lease(service))

    result = asyncio.run(service.command("cancel", {
        "command_id": "cancel",
        "lease_id": lease_id,
        "session_id": "sim-a",
    }))

    assert result.succeeded is False
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert worker.cancel_calls == 0


def test_unsupported_reset_preserves_control_plane_state():
    adapter = FakeAdapter("mujoco_py")
    worker = Worker()
    service = TeleopService(worker, backend=adapter)
    lease_id = asyncio.run(lease(service))
    checkpoint = Path("/tmp/existing-checkpoint.json")
    service._workflow["existing"] = (checkpoint, "sim-a")
    summary = PlanSummary(
        plan_id="existing-plan",
        start_fingerprint="start",
        target_fingerprint="target",
        scene_revision=0,
        expires_at_monotonic=9999999999.0,
    )
    service._plans.put(summary)
    worker._plans[summary.plan_id] = StoredTrajectory(summary, object(), "sim-a", 7)

    result = asyncio.run(service.command("simulation_reset", {
        "command_id": "reset",
        "lease_id": lease_id,
        "session_id": "sim-a",
        "confirmation": "CONFIRM SIMULATION_RESET",
    }))

    assert result.succeeded is False
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert service._lease == (lease_id, service._lease[1])
    assert service._workflow == {"existing": (checkpoint, "sim-a")}
    assert service._plans._latest.plan_id == "existing-plan"
    assert "existing-plan" in worker._plans
    assert adapter.calls == []


def test_unsupported_scene_repair_does_not_clear_plans():
    adapter = FakeAdapter("gazebo_py")
    worker = Worker()
    service = TeleopService(worker, backend=adapter)
    lease_id = asyncio.run(lease(service))
    summary = PlanSummary(
        plan_id="existing-plan",
        start_fingerprint="start",
        target_fingerprint="target",
        scene_revision=0,
        expires_at_monotonic=9999999999.0,
    )
    service._plans.put(summary)
    worker._plans[summary.plan_id] = StoredTrajectory(summary, object(), "sim-a", 7)

    result = asyncio.run(service.command("scene_repair", {
        "command_id": "repair",
        "lease_id": lease_id,
        "session_id": "sim-a",
        "confirmation": "CONFIRM SCENE_REPAIR",
    }))

    assert result.succeeded is False
    assert result.code == "BACKEND_CAPABILITY_UNAVAILABLE"
    assert service._plans._latest.plan_id == "existing-plan"
    assert "existing-plan" in worker._plans
    assert adapter.calls == []
