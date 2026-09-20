"""Acquiring a lease binds the domain controller to the instance's live channel.

Design section 5.1: registration grants no control; when the user explicitly acquires, the
existing domain lease endpoint validates the instance's live channel and binds that domain's
single controller in the same transaction. Before this, the acquire path required a controller
that only acquiring could create, so no mutation was reachable.

The channel is made live with ``registry.connect`` - the same state the channel websocket
handler establishes - to keep this test independent of the websocket client.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from so101_teleop.unified.app import create_unified_app
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import Domain
from so101_teleop.unified.instances import InstanceRegistry
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.ports import UnifiedServices

ORIGIN = "http://127.0.0.1:8000"


class StubLeaseService:
    """Only what the acquire route calls; the lease it returns is a real LeaseIdentity shape."""

    def __init__(self) -> None:
        self.calls = 0

    async def command(self, name: str, body: dict) -> dict:
        assert name == "lease", name
        self.calls += 1
        return {
            "succeeded": True,
            "lease_id": "L1",
            "service_session_id": body.get("service_session_id", "s1"),
            "generation": 1,
            "expires_monotonic_ns": 10**15,
        }


@pytest.fixture()
def composed(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    registry = InstanceRegistry(arbiter, service_epoch="e1", origin=ORIGIN, clock_ns=lambda: 1)
    service = StubLeaseService()
    services = UnifiedServices(
        teleop=service, tasks=None, validation=None, arbiter=arbiter, instances=registry
    )
    app = create_unified_app(services, bind_address="127.0.0.1")
    return app, registry, service


def _register(client) -> dict:
    response = client.post("/control/instances", json={"domain": "teleop"})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(body: dict, revision: int) -> dict[str, str]:
    return {
        "X-SO101-Instance-ID": body["instance_id"],
        "X-SO101-Instance-Proof": body["proof"],
        "X-SO101-Channel-Revision": str(revision),
        "X-SO101-Execution-Generation": "1",
    }


def test_acquire_binds_the_controller_for_a_live_channel(composed):
    app, registry, service = composed
    client = TestClient(app)
    body = _register(client)
    binding = registry.connect(body["instance_id"], body["proof"], origin=ORIGIN)

    lease = client.post(
        "/control/lease", json={"service_session_id": "s1"}, headers=_headers(body, binding.revision)
    )
    assert lease.status_code == 200, lease.text
    assert service.calls == 1
    assert registry.current_lease(Domain.TELEOP).lease_id == "L1"


def test_second_instance_still_cannot_take_a_bound_controller(composed):
    app, registry, service = composed
    client = TestClient(app)
    first = _register(client)
    binding = registry.connect(first["instance_id"], first["proof"], origin=ORIGIN)
    assert client.post(
        "/control/lease", json={"service_session_id": "s1"}, headers=_headers(first, binding.revision)
    ).status_code == 200

    second = _register(client)
    other = registry.connect(second["instance_id"], second["proof"], origin=ORIGIN)
    refused = client.post(
        "/control/lease", json={"service_session_id": "s2"}, headers=_headers(second, other.revision)
    )
    assert refused.status_code == 409, refused.text
    assert "CONTROLLER_ALREADY_BOUND" in refused.text
    assert registry.current_lease(Domain.TELEOP).lease_id == "L1"


def test_acquire_without_a_live_channel_is_refused(composed):
    app, registry, _service = composed
    client = TestClient(app)
    body = _register(client)
    refused = client.post(
        "/control/lease", json={"service_session_id": "s1"}, headers=_headers(body, 1)
    )
    assert refused.status_code == 409, refused.text
    assert "CHANNEL_NOT_LIVE" in refused.text
