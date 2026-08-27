import asyncio
import json
from pathlib import Path

from so101_teleop.models import (
    CommandResult,
    TaskCaptureRequest,
    TaskMutationRequest,
    TaskPointModel,
    TaskRunRequest,
)
from so101_teleop.task_artifacts import ManifestArtifactStore
from so101_teleop.task_gateway import TaskHandle
from so101_teleop.task_service import TaskService


class Teleop:
    def __init__(self):
        self.bound = None
        self.gate_result = None

    def bind_task_active(self, predicate):
        self.bound = predicate

    def task_mutation_gate(self, body, capability):
        del capability
        return self.gate_result


class Gateway:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.state = "RUNNING"

    async def start_batch(self, request):
        self.calls.append(("start", request))
        return TaskHandle(
            "run-1", 101, 101,
            self.root / "batches/run-1/batch-result.json",
        )

    async def status(self, run_id):
        self.calls.append(("status", run_id))
        return {"run_id": run_id, "status": self.state, "points": []}

    async def cancel(self, run_id):
        self.calls.append(("cancel", run_id))
        self.state = "CANCELLED"
        return {"run_id": run_id, "status": "CANCELLED"}

    async def capture(self, request):
        self.calls.append(("capture", request))
        output = self.root / "captures/capture-1"
        output.mkdir(parents=True)
        (output / "rgb.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
        (output / "full-cloud.ply").write_bytes(b"ply\n")
        (output / "summary.json").write_text(json.dumps({
            "source_stamp_ns": 123456789,
            "source_frame_id": "task_camera_frame",
            "cup_center_xyz": [0.02, -0.28, 0.165],
        }))
        return {
            "status": "SUCCEEDED",
            "capture_id": "capture-1",
            "output_directory": str(output),
        }


def point():
    return TaskPointModel(
        id="free-a", label="Free A",
        cup_position_world_m=(0.02, -0.30, 0.165),
    )


def run_request(command_id="start-1"):
    return TaskRunRequest(
        schema_version=1,
        points=[point()],
        session_id="sim-a",
        lease_id="lease-a",
        command_id=command_id,
    )


def service_for(tmp_path):
    teleop = Teleop()
    store = ManifestArtifactStore(tmp_path / "evidence")
    gateway = Gateway(store.root)
    service = TaskService(teleop, gateway, store, presets=(point(),))
    return service, teleop, gateway, store


def test_start_binds_active_lock_and_is_idempotent(tmp_path):
    async def scenario():
        service, teleop, gateway, _store = service_for(tmp_path)
        first = await service.start(run_request())
        repeated = await service.start(run_request())
        assert first.run_id == repeated.run_id == "run-1"
        assert [name for name, _ in gateway.calls].count("start") == 1
        assert teleop.bound() is True
    asyncio.run(scenario())


def test_reused_command_id_with_different_points_is_rejected(tmp_path):
    async def scenario():
        service, _teleop, gateway, _store = service_for(tmp_path)
        await service.start(run_request())
        changed = run_request()
        changed.points[0].cup_position_world_m = (0.03, -0.30, 0.165)
        result = await service.start(changed)
        assert result.code == "COMMAND_ID_REUSED"
        assert [name for name, _ in gateway.calls].count("start") == 1
    asyncio.run(scenario())


def test_start_rejects_bad_lease_before_gateway(tmp_path):
    async def scenario():
        service, teleop, gateway, _store = service_for(tmp_path)
        teleop.gate_result = CommandResult(
            command_id="start-1", accepted=False, succeeded=False,
            code="LEASE_REQUIRED", message="valid lease required",
        )
        result = await service.start(run_request())
        assert result.code == "LEASE_REQUIRED"
        assert gateway.calls == []
    asyncio.run(scenario())


def test_cancel_requires_gate_and_releases_old_command_lock(tmp_path):
    async def scenario():
        service, teleop, gateway, _store = service_for(tmp_path)
        await service.start(run_request())
        request = TaskMutationRequest(
            session_id="sim-a", lease_id="lease-a", command_id="cancel-1"
        )
        result = await service.cancel("run-1", request)
        assert result.status == "CANCELLED"
        assert teleop.bound() is False
    asyncio.run(scenario())


def test_capture_registers_fresh_rgb_and_ply_artifacts(tmp_path):
    async def scenario():
        service, _teleop, gateway, store = service_for(tmp_path)
        response = await service.capture(TaskCaptureRequest(
            session_id="sim-a", lease_id="lease-a", command_id="capture-1"
        ))
        assert response.capture_id == "capture-1"
        assert len(response.artifact_ids) == 3
        assert all(store.open(item).path.is_file() for item in response.artifact_ids)
        assert response.source_stamp_ns == 123456789
        assert response.summary["cup_center_xyz"] == [0.02, -0.28, 0.165]
        assert {item.name for item in response.artifacts} == {
            "rgb.png", "full-cloud.ply", "summary.json"
        }
        assert all(len(item.sha256) == 64 for item in response.artifacts)
        assert gateway.calls[0][0] == "capture"
    asyncio.run(scenario())


def test_event_order_is_monotonic_and_bounded(tmp_path):
    async def scenario():
        service, _teleop, gateway, _store = service_for(tmp_path)
        queue = service.subscribe(maxsize=2)
        await service.start(run_request())
        gateway.state = "SUCCEEDED"
        await service.status("run-1")
        events = [queue.get_nowait(), queue.get_nowait()]
        assert [event.kind for event in events] == ["BATCH_STARTED", "BATCH_FINISHED"]
        assert events[0].sequence < events[1].sequence
        service.unsubscribe(queue)
    asyncio.run(scenario())


def test_point_summary_exposes_artifact_names_without_paths(tmp_path):
    service, _teleop, _gateway, _store = service_for(tmp_path)
    summary = service._point_summary({
        "id": "first",
        "status": "FAILED",
        "artifacts": [{
            "artifact_id": "a" * 24,
            "relative_path": "batches/run-1/points/01-first/rgb.png",
            "media_type": "image/png",
            "byte_size": 8,
            "sha256": "b" * 64,
        }],
    })
    assert summary.artifacts[0].name == "rgb.png"
    assert "relative_path" not in summary.artifacts[0].model_dump()


def test_recovery_and_shutdown_require_exact_confirmations(tmp_path):
    async def scenario():
        from so101_teleop.models import TaskRecoveryRequest, TaskShutdownRequest

        service, _teleop, _gateway, _store = service_for(tmp_path)
        await service.start(run_request())
        recovery = await service.recovery("run-1", TaskRecoveryRequest(
            session_id="sim-a", lease_id="lease-a", command_id="recover-1",
            action="stop", confirmation="wrong",
        ))
        shutdown = await service.shutdown(TaskShutdownRequest(
            session_id="sim-a", lease_id="lease-a", command_id="shutdown-1",
            confirmation="wrong",
        ))
        assert {recovery.code, shutdown.code} == {"CONFIRMATION_REQUIRED"}
        assert service.is_active() is True
    asyncio.run(scenario())
