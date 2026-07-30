from fastapi.testclient import TestClient
import pytest

from so101_teleop.api import create_app, validate_bind_address
from so101_teleop.models import CommandResult, ServerMode, TelemetrySnapshot


class Service:
    def __init__(self):
        self.snapshot = TelemetrySnapshot(sequence=1, mode=ServerMode.READY, simulation_session_id="sim-a")

    async def health(self): return {"ok": True}
    async def current_snapshot(self): return self.snapshot
    async def execute_plan(self, plan_id, body):
        return CommandResult(command_id=body["command_id"], accepted=True, succeeded=False,
                             code="PLAN_STALE_SCENE", message="scene changed")

    async def command(self, name, body):
        return CommandResult(command_id=body["command_id"], accepted=True, succeeded=False,
                             code="MOVEIT_IK_FAILED_-31", message="No IK solution")


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
