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


def unified_app_for(service=None, *, static_dir=None, capture_dir=None, task_service=None,
                    instances=None, arbiter=None, safety=None):
    """Build the unified app around a stub port; the migration target for these tests (CP-75)."""
    from so101_teleop.unified.app import create_unified_app
    from so101_teleop.unified.ports import UnifiedServices

    return create_unified_app(
        UnifiedServices(
            teleop=service,
            tasks=task_service,
            validation=None,
            arbiter=arbiter,
            instances=instances,
            safety=safety,
        ),
        static_dir=static_dir,
        capture_dir=capture_dir,
        bind_address="127.0.0.1",
    )


class AuthorityFixture:
    """A real instance binding, so a migrated mutation case can carry instance authority.

    This is the fixture CP-75 specified: a real store, arbiter and registry in a temporary
    directory, an instance registered, a channel connected and a lease claimed.
    """

    def __init__(self, tmp_path) -> None:
        from so101_teleop.unified.arbiter import GlobalMutationArbiter
        from so101_teleop.unified.contracts import Domain, LeaseIdentity
        from so101_teleop.unified.instances import InstanceRegistry
        from so101_teleop.unified.intent_store import IntentStore

        self.store = IntentStore.open(tmp_path / "unified-state")
        self.arbiter = GlobalMutationArbiter(self.store, clock_ns=lambda: 1)
        self.registry = InstanceRegistry(
            self.arbiter, service_epoch="e1", origin="http://testserver", clock_ns=lambda: 1
        )
        proof = self.registry.register(Domain.TELEOP)
        binding = self.registry.connect(proof.instance_id, proof.proof, origin="http://testserver")
        self.authority = self.registry.claim(binding, LeaseIdentity("l1", "s1", 1, 10 ** 15))

    def headers(self) -> dict:
        return {
            "X-SO101-Instance-ID": self.authority.instance_id,
            "X-SO101-Instance-Proof": self.authority.proof,
            "X-SO101-Channel-Revision": str(self.authority.channel_revision),
            "X-SO101-Execution-Generation": str(self.authority.execution_generation),
        }

    def close(self) -> None:
        self.store.close()


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


def test_unreachable_tcp_target_is_a_conflict_not_service_outage(tmp_path):
    authority = AuthorityFixture(tmp_path)
    try:
        client = TestClient(
            unified_app_for(Service(), instances=authority.registry, arbiter=authority.arbiter)
        )
        response = client.post(
            "/plan/tcp", json={"command_id": "tcp-1"}, headers=authority.headers()
        )
    finally:
        authority.close()
    assert response.status_code == 409
    assert response.json()["code"] == "MOVEIT_IK_FAILED_-31"


def test_health_and_snapshot_remain_available_without_web_assets():
    """Missing frontend assets must not hide server health from remote diagnosis."""
    client = TestClient(unified_app_for(Service()))

    # The unified /health aggregates the domains and keeps the Teleop fields as a nested
    # compatibility projection, so the assertion follows that contract instead of the old flat body.
    health = client.get("/health").json()
    assert health["ok"] is True
    assert health["teleop"]["ok"] is True
    assert set(health["domains"]) == {"teleop", "tasks", "validation"}
    assert client.get("/snapshot").json()["simulation_session_id"] == "sim-a"


def test_validation_capabilities_report_the_exact_n_view_without_a_validation_service():
    """Superseded contract, kept as a test rather than deleted.

    The old flat `{"available": False, "reason": "VALIDATION_SERVER_REQUIRED"}` body was the
    standalone-server placeholder. The unified route answers with the read-only per-N qualification
    view instead, and the plan requires every exact N to be visible there, so the assertion follows
    the new contract.
    """
    client = TestClient(unified_app_for(Service()))
    body = client.get("/expert-validation/capabilities").json()
    assert body["available"] is False
    assert body["reason"] == "VALIDATION_SERVER_REQUIRED"
    assert [view["selected_n"] for view in body["worker_qualifications"]] == list(range(2, 9))
    assert all(view["status"] == "UNKNOWN" for view in body["worker_qualifications"])


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
    client = TestClient(unified_app_for(Service(), static_dir=dist))
    assert client.get("/assets/chunk.js").status_code == 200
    assert client.get("/assets/chunk.js").headers["content-type"].startswith("text/javascript")


def test_camera_presets_are_listed_and_apply_uses_command_boundary(tmp_path):
    authority = AuthorityFixture(tmp_path)
    service = Service()
    try:
        client = TestClient(
            unified_app_for(service, instances=authority.registry, arbiter=authority.arbiter)
        )
        assert client.get("/gazebo/camera/presets").json() == {"presets": ["overview", "top"]}
        response = client.post(
            "/gazebo/camera/presets/overview",
            json={"command_id": "camera-1", "lease_id": "lease-a", "session_id": "sim-a"},
            headers=authority.headers(),
        )
    finally:
        authority.close()

    assert response.status_code == 409
    assert service.commands[-1][0] == "camera_preset"
    assert service.commands[-1][1]["preset"] == "overview"


def test_task_routes_are_separate_and_typed(tmp_path):
    authority = AuthorityFixture(tmp_path)
    tasks = TaskApiService()
    try:
        client = TestClient(
            unified_app_for(
                Service(),
                task_service=tasks,
                instances=authority.registry,
                arbiter=authority.arbiter,
            )
        )
        response = client.post("/tasks/runs", json={
            "schema_version": 1,
            "points": [{
                "id": "free-a", "label": "Free A",
                "cup_position_world_m": [0.02, -0.30, 0.165],
            }],
            "session_id": "sim-a", "lease_id": "lease-a",
            "command_id": "start-1",
        }, headers=authority.headers())
    finally:
        authority.close()
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
    client = TestClient(unified_app_for(Service(), task_service=tasks))
    response = client.get("/tasks/artifacts/bad-id")
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_NOT_FOUND"


def test_task_websocket_uses_independent_ordered_event_stream():
    tasks = TaskApiService()
    client = TestClient(unified_app_for(Service(), task_service=tasks))
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


def test_the_stub_service_satisfies_the_unified_read_only_port():
    """First step of CP-75's migration, proving the recipe before rewriting the rest.

    The existing `Service` stub is exercised through the unified factory, which is what the legacy
    tests will move to. Only read-only routes are involved here; the mutation cases need the instance
    authority fixture described in CP-75.
    """
    from so101_teleop.unified.app import create_unified_app
    from so101_teleop.unified.ports import UnifiedServices

    app = create_unified_app(
        UnifiedServices(teleop=Service(), tasks=None, validation=None),
        bind_address="127.0.0.1",
    )
    with TestClient(app) as client:
        assert client.get("/health").json()["teleop"]["ok"] is True
        assert client.get("/snapshot").json()["simulation_session_id"] == "sim-a"
        assert client.get("/gazebo/camera/presets").json() == {"presets": ["overview", "top"]}
        # A mutation still refuses without instance authority on this composed app.
        response = client.post("/gripper/execute", json={"command_id": "c1"})
        assert response.status_code == 409
        assert response.json()["code"] == "CONTROLLER_INSTANCE_REQUIRED"
