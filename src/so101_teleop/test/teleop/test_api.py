import json

from fastapi.testclient import TestClient
import pytest

from so101_teleop.api import create_app, validate_bind_address
from so101_teleop.models import CommandResult, ServerMode, TelemetrySnapshot
from so101_teleop.models import CaptureResponse, TaskEvent, TaskRunSummary
from so101_teleop.task_artifacts import ManifestArtifactStore


class Service:
    def __init__(self):
        self.snapshot = TelemetrySnapshot(sequence=1, mode=ServerMode.READY, simulation_session_id="sim-a")
        self.commands = []

    async def health(self): return {"ok": True}
    async def current_snapshot(self): return self.snapshot
    async def execute_plan(self, plan_id, body):
        return CommandResult(command_id=body["command_id"], accepted=True, succeeded=False,
                             code="PLAN_STALE_SCENE", message="scene changed")

    async def command(self, name, body):
        self.commands.append((name, body))
        return CommandResult(command_id=body["command_id"], accepted=True, succeeded=False,
                             code="MOVEIT_IK_FAILED_-31", message="No IK solution")

    async def camera_presets(self):
        return {"presets": ["overview", "top"]}


class TaskApiService:
    def __init__(self):
        self.calls = []

    async def presets(self):
        return {"schema_version": 1, "points": []}

    async def start(self, request):
        self.calls.append(("start", request))
        return TaskRunSummary(
            run_id="run-1", status="RUNNING",
            simulation_session_id=request.session_id, points=[],
        )

    async def list_runs(self): return []
    async def status(self, run_id):
        return TaskRunSummary(
            run_id=run_id, status="RUNNING",
            simulation_session_id="sim-a", points=[],
        )

    async def cancel(self, run_id, request):
        self.calls.append(("cancel", run_id, request))
        return TaskRunSummary(
            run_id=run_id, status="CANCELLED",
            simulation_session_id=request.session_id, points=[],
        )

    async def capture(self, request):
        return CaptureResponse(
            capture_id="c1", status="SUCCEEDED", artifact_ids=[]
        )

    def subscribe(self):
        import asyncio
        queue = asyncio.Queue()
        queue.put_nowait(TaskEvent(
            sequence=1, kind="BATCH_STARTED", run_id="run-1",
            status="RUNNING",
        ))
        return queue

    def unsubscribe(self, queue):
        self.unsubscribed = queue


def test_unsafe_bind_is_rejected():
    """Permitting wildcard/LAN bind would expose simulation control outside Tailscale."""
    with pytest.raises(ValueError, match="BIND_ADDRESS_UNSAFE"):
        validate_bind_address("0.0.0.0")


def test_execute_returns_conflict_for_stale_plan():
    """Returning 2xx for a stale plan would let the browser mistake rejection for execution."""
    client = TestClient(create_app(Service()))

    response = client.post("/plans/p1/execute", json={"command_id": "execute-1"})

    assert response.status_code == 409
    assert response.json()["code"] == "PLAN_STALE_SCENE"


def test_unreachable_tcp_target_is_a_conflict_not_service_outage():
    client = TestClient(create_app(Service()))
    response = client.post("/plan/tcp", json={"command_id": "tcp-1"})
    assert response.status_code == 409
    assert response.json()["code"] == "MOVEIT_IK_FAILED_-31"


def test_health_and_snapshot_remain_available_without_web_assets():
    """Missing frontend assets must not hide server health from remote diagnosis."""
    client = TestClient(create_app(Service()))

    assert client.get("/health").json() == {"ok": True}
    assert client.get("/snapshot").json()["simulation_session_id"] == "sim-a"


def test_missing_web_assets_return_machine_readable_service_unavailable():
    """A missing production bundle must be diagnosable instead of looking like a lost route."""
    client = TestClient(create_app(Service()))

    response = client.get("/")

    assert response.status_code == 503
    assert response.json() == {"code": "WEB_ASSETS_NOT_BUILT"}


def test_vite_assets_referenced_by_index_are_served_from_symlink_install(tmp_path):
    """The production SPA must not become blank when installed chunks are symlinks."""
    dist = tmp_path / "web"; assets = dist / "assets"; assets.mkdir(parents=True)
    source = tmp_path / "chunk.js"; source.write_text("console.log('ok')")
    (assets / "chunk.js").symlink_to(source)
    (dist / "index.html").write_text('<script type="module" src="/assets/chunk.js"></script>')
    client = TestClient(create_app(Service(), dist))
    assert client.get("/assets/chunk.js").status_code == 200
    assert client.get("/assets/chunk.js").headers["content-type"].startswith("text/javascript")


def test_camera_presets_are_listed_and_apply_uses_command_boundary():
    service = Service()
    client = TestClient(create_app(service))

    assert client.get("/gazebo/camera/presets").json() == {"presets": ["overview", "top"]}
    response = client.post(
        "/gazebo/camera/presets/overview",
        json={"command_id": "camera-1", "lease_id": "lease-a", "session_id": "sim-a"},
    )

    assert response.status_code == 409
    assert service.commands[-1][0] == "camera_preset"
    assert service.commands[-1][1]["preset"] == "overview"


def test_task_routes_are_separate_and_typed():
    tasks = TaskApiService()
    client = TestClient(create_app(Service(), task_service=tasks))
    response = client.post("/tasks/runs", json={
        "schema_version": 1,
        "points": [{
            "id": "free-a", "label": "Free A",
            "cup_position_world_m": [0.02, -0.30, 0.165],
        }],
        "session_id": "sim-a", "lease_id": "lease-a",
        "command_id": "start-1",
    })
    assert response.status_code == 200
    assert response.json()["run_id"] == "run-1"
    assert tasks.calls[0][0] == "start"
    assert client.get("/snapshot").json()["simulation_session_id"] == "sim-a"


def test_task_artifact_route_rejects_manifest_escape(tmp_path):
    tasks = TaskApiService()
    tasks.artifacts = ManifestArtifactStore(tmp_path / "evidence")
    tasks.artifacts.manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "artifacts": [{
            "artifact_id": "bad-id",
            "relative_path": "../../etc/passwd",
            "media_type": "text/plain",
            "byte_size": 1,
            "sha256": "0" * 64,
            "capture_id": None,
            "run_id": None,
            "source_artifact_id": None,
            "metadata": {},
        }],
    }))
    client = TestClient(create_app(Service(), task_service=tasks))
    response = client.get("/tasks/artifacts/bad-id")
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"


def test_task_websocket_uses_independent_ordered_event_stream():
    tasks = TaskApiService()
    client = TestClient(create_app(Service(), task_service=tasks))
    with client.websocket_connect("/tasks/events") as websocket:
        event = websocket.receive_json()
    assert event == {
        "sequence": 1,
        "kind": "BATCH_STARTED",
        "run_id": "run-1",
        "point_id": None,
        "status": "RUNNING",
        "failure_code": None,
    }
