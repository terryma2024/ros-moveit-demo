"""Batch 2 correction: only an opaque handle resolved by the sealed broker binds."""

import inspect
import json
import uuid

import pytest
from control_msgs.action import FollowJointTrajectory

from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

GOAL_UUID = "12345678-1234-5678-1234-567812345678"


class _Handle:
    def __init__(self, permit_id):
        self.permit_id = permit_id


class _Registry:
    """Sealed broker-owned resolver over real IN_FLIGHT records."""

    def __init__(self, binding=None, state="IN_FLIGHT"):
        self._binding, self._state = binding, state

    def reservation_binding(self, handle):
        from so101_demo.adapters.act.authority_transaction import AuthorityRefused

        if getattr(handle, "permit_id", None) not in ("p-1",):
            raise AuthorityRefused("AUTHORITY_PERMIT_UNKNOWN")
        if self._state != "IN_FLIGHT":
            raise AuthorityRefused(f"AUTHORITY_PERMIT_NOT_IN_FLIGHT:{self._state}")
        return self._binding


def _binding(**overrides):
    base = {"permit_id": "p-1", "goal_uuid": GOAL_UUID, "role": "arm", "target_digest": "d-1",
            "session_id": "s-1", "broker_incarnation": "b-1", "generation": 1,
            "controller_incarnation": "inc-1", "controller_boot_incarnation": "boot-1",
            "claim_monotonic_ns": 10, "deadline_ns": 100}
    base.update(overrides)
    return base


def _client():
    return ControllerReservationClient({"arm": "/tmp/endpoint"}, capability=b"c" * 32, timeout_s=1.0)


def test_entry_point_accepts_no_raw_authority_values():
    parameters = inspect.signature(ControllerReservationClient.reserve_bound).parameters
    for forbidden in ("identity", "receipt", "snapshot", "claim_monotonic_ns", "deadline_ns"):
        assert forbidden not in parameters, forbidden
    assert "handle" in parameters and "resolver" in parameters


def test_fabricated_handle_and_foreign_registry_fail_before_wire():
    client = _client()
    sent = []
    client._request = lambda *a, **k: sent.append((a, k))
    with pytest.raises(Exception):
        client.reserve_bound((1,), "arm", FollowJointTrajectory.Goal(), GOAL_UUID,
                             handle=_Handle("forged"), resolver=_Registry(_binding()))
    with pytest.raises(Exception):
        client.reserve_bound((1,), "arm", FollowJointTrajectory.Goal(), GOAL_UUID,
                             handle=None, resolver=_Registry(_binding()))
    assert sent == []


@pytest.mark.parametrize("state", ["READY", "UNKNOWN", "REJECTED"])
def test_not_in_flight_states_fail_before_wire(state):
    client = _client()
    sent = []
    client._request = lambda *a, **k: sent.append((a, k))
    with pytest.raises(Exception):
        client.reserve_bound((1,), "arm", FollowJointTrajectory.Goal(), GOAL_UUID,
                             handle=_Handle("p-1"), resolver=_Registry(_binding(), state=state))
    assert sent == []


def test_wrong_goal_role_and_late_binding_fail_before_wire():
    client = _client()
    sent = []
    client._request = lambda *a, **k: sent.append((a, k))
    goal = FollowJointTrajectory.Goal()
    cases = [{"goal_uuid": str(uuid.uuid4())}, {"role": "gripper"}]
    for overrides in cases:
        with pytest.raises(Exception):
            client.reserve_bound((1,), "arm", goal, GOAL_UUID, handle=_Handle("p-1"),
                                 resolver=_Registry(_binding(**overrides)))
    with pytest.raises(Exception):
        client.reserve_bound((1,), "arm", goal, GOAL_UUID, handle=_Handle("p-1"),
                             resolver=_Registry(_binding()), now_ns=101)
    assert sent == []


def test_resolved_binding_is_carried_byte_for_byte_on_the_wire():
    client = _client()
    captured = {}

    def capture(kind, operation, generation, goal_uuid, payload):
        captured.update(kind=kind, operation=operation, generation=generation,
                        goal_uuid=goal_uuid, payload=payload)
        return True

    client._request = capture
    binding = _binding()
    assert client.reserve_bound((1,), "arm", FollowJointTrajectory.Goal(), GOAL_UUID,
                                handle=_Handle("p-1"), resolver=_Registry(binding),
                                now_ns=50) is True
    payload = captured["payload"]
    size = int.from_bytes(payload[:4], "big")
    on_wire = json.loads(payload[4:4 + size].decode("utf-8"))
    assert on_wire == binding, "the on-wire binding differs from the registry's record"
    assert len(payload) > 4 + size


def test_owner_health_revocation_prevents_the_production_call():
    """A revoked owner is not IN_FLIGHT, so the broker-owned resolve refuses."""
    client = _client()
    sent = []
    client._request = lambda *a, **k: sent.append((a, k))
    with pytest.raises(Exception):
        client.reserve_bound((1,), "arm", FollowJointTrajectory.Goal(), GOAL_UUID,
                             handle=_Handle("p-1"), resolver=_Registry(_binding(), state="REVOKED"))
    assert sent == []
