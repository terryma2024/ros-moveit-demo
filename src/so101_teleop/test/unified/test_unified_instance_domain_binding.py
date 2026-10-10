"""An instance obtained over HTTP must be able to authorise a mutation in its own domain.

`POST /control/instances` takes the domain from a JSON body, and the registry stores it without
coercion while comparing domains by identity. If the body value stays a plain string, every later
mutation fails with INSTANCE_DOMAIN_MISMATCH - which is what a live API flow hit.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from so101_teleop.unified.app import create_unified_app
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    Domain,
    LeaseIdentity,
    MutationError,
    RequestAuthority,
)
from so101_teleop.unified.instances import InstanceRegistry
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.ports import UnifiedServices

ORIGIN = "http://127.0.0.1:8000"
LEASE = LeaseIdentity("l1", "s1", 1, 10**15)


@pytest.fixture()
def composed(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    registry = InstanceRegistry(arbiter, service_epoch="e1", origin=ORIGIN, clock_ns=lambda: 1)
    services = UnifiedServices(
        teleop=None, tasks=None, validation=None, arbiter=arbiter, instances=registry
    )
    return create_unified_app(services, bind_address="127.0.0.1"), registry


@pytest.mark.parametrize("domain", ["teleop", "validation"])
def test_http_registered_instance_authorises_its_own_domain(composed, domain):
    app, registry = composed
    client = TestClient(app)
    response = client.post("/control/instances", json={"domain": domain})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == domain

    binding = registry.connect(body["instance_id"], body["proof"], origin=ORIGIN)
    registry.claim(binding, LEASE)
    # This is exactly how the HTTP mutation dependency builds its authority: the domain from
    # the request as the Domain member, everything else from the headers.
    authority = RequestAuthority(
        domain=Domain(domain),
        instance_id=body["instance_id"],
        proof=body["proof"],
        channel_revision=1,
        execution_generation=1,
    )
    try:
        registry.require_bound(authority)
    except MutationError as error:
        pytest.fail(
            "an instance registered over HTTP was rejected by its own registry: "
            f"{error} (record domain type: {type(registry._instances[body['instance_id']].domain).__name__})"
        )
