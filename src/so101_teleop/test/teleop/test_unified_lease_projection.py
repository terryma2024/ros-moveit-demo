"""A renewed lease must move the controller's projection, or authority dies after one duration.

The unified app binds the domain controller when the lease is acquired, recording that lease's
`expires_monotonic_ns`. Every later mutation - the renewal itself included - is checked against that
recorded projection. Nothing recorded the *renewed* projection, so a lease that its client kept
extending still expired for the controller exactly one lease duration after acquisition, and from then
on the renewal was refused `LEASE_EXPIRED` forever: measured live, renewals succeeded at 10 s and 20 s
and were refused at 30 s against a still-`ACTIVE` row with 20 s left on it, which then cancelled the
campaign through the expiry path.
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


class Clock:
    """A clock this test moves, so 'one lease duration later' is a fact rather than a sleep."""

    def __init__(self, now: int = 1) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


class StubValidationLeaseService:
    """The two calls the lease routes make, with a renewal that really extends the lease."""

    def __init__(self) -> None:
        self.acquired: dict = {}
        self.renewals = 0

    async def acquire_lease(self, body: dict) -> dict:
        self.acquired = {
            "lease_id": "V1",
            "service_session_id": body["service_session_id"],
            "generation": 1,
            "expires_monotonic_ns": 100,
        }
        return dict(self.acquired)

    async def renew_lease(self, lease_id: str, body: dict) -> dict:
        assert lease_id == "V1", lease_id
        self.renewals += 1
        return {
            "lease_id": lease_id,
            "service_session_id": body["service_session_id"],
            "generation": body["generation"] + 1,
            "expires_monotonic_ns": 100 + 100 * self.renewals,
        }


@pytest.fixture()
def composed(tmp_path):
    clock = Clock()
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=clock)
    registry = InstanceRegistry(arbiter, service_epoch="e1", origin=ORIGIN, clock_ns=clock)
    service = StubValidationLeaseService()
    services = UnifiedServices(
        teleop=None, tasks=None, validation=service, arbiter=arbiter, instances=registry
    )
    app = create_unified_app(services, bind_address="127.0.0.1")
    return app, registry, service, clock


def _headers(instance: dict, revision: int) -> dict[str, str]:
    return {
        "X-SO101-Instance-ID": instance["instance_id"],
        "X-SO101-Instance-Proof": instance["proof"],
        "X-SO101-Channel-Revision": str(revision),
        "X-SO101-Execution-Generation": "1",
    }


def _acquire(client, registry) -> tuple[dict, dict, int]:
    instance = client.post("/control/instances", json={"domain": "validation"}).json()
    binding = registry.connect(instance["instance_id"], instance["proof"], origin=ORIGIN)
    acquired = client.post(
        "/expert-validation/lease",
        json={"service_session_id": "s1"},
        headers=_headers(instance, binding.revision),
    )
    assert acquired.status_code == 200, acquired.text
    return instance, acquired.json(), binding.revision


def test_a_renewal_moves_the_controller_lease_projection(composed):
    app, registry, service, clock = composed
    client = TestClient(app)
    instance, lease, revision = _acquire(client, registry)
    headers = _headers(instance, revision)
    assert registry.current_lease(Domain.VALIDATION).expires_monotonic_ns == 100

    clock.now = 50
    renewed = client.put(
        f"/expert-validation/lease/{lease['lease_id']}",
        json={"service_session_id": "s1", "generation": lease["generation"]},
        headers=headers,
    )
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["expires_monotonic_ns"] == 200
    assert registry.current_lease(Domain.VALIDATION).expires_monotonic_ns == 200, (
        "the projection still holds the acquisition expiry, so authority dies one duration in"
    )

    # Past the acquisition expiry and inside the renewed one: only the projection decides this.
    clock.now = 150
    again = client.put(
        f"/expert-validation/lease/{lease['lease_id']}",
        json={"service_session_id": "s1", "generation": renewed.json()["generation"]},
        headers=headers,
    )
    assert again.status_code == 200, again.text
    assert registry.current_lease(Domain.VALIDATION).expires_monotonic_ns == 300
    assert service.renewals == 2


def test_a_renewal_that_does_not_extend_the_lease_cannot_move_the_projection(composed):
    """A projection that could go backwards would let a stale lease authorize work again."""
    app, registry, _service, clock = composed
    client = TestClient(app)
    instance, lease, revision = _acquire(client, registry)
    headers = _headers(instance, revision)
    clock.now = 50
    client.put(
        f"/expert-validation/lease/{lease['lease_id']}",
        json={"service_session_id": "s1", "generation": lease["generation"]},
        headers=headers,
    )
    assert registry.current_lease(Domain.VALIDATION).expires_monotonic_ns == 200
