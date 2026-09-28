"""Batch 2: the reservation boundary accepts only broker-owned bound data."""

import inspect
import json
import uuid

import pytest
from control_msgs.action import FollowJointTrajectory

from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

GOAL_UUID = "12345678-1234-5678-1234-567812345678"
IDENTITY = (1, "inc-1", "boot-1")


def _client():
    return ControllerReservationClient({"arm": "/tmp/endpoint"}, capability=b"c" * 32,
                                       timeout_s=1.0)


def _receipt(**overrides):
    base = {"permit_id": "p-1", "goal_uuid": GOAL_UUID, "role": "arm", "target_digest": "d-1",
            "session_id": "s-1", "broker_incarnation": "b-1", "generation": 1,
            "controller_incarnation": "inc-1", "controller_boot_incarnation": "boot-1",
            "claim_monotonic_ns": 10, "deadline_ns": 100}
    base.update(overrides)
    return base


def _goal():
    return FollowJointTrajectory.Goal()


def test_bound_entry_point_exposes_identity_and_receipt_only():
    parameters = inspect.signature(ControllerReservationClient.reserve_bound).parameters
    assert "identity" in parameters and "receipt" in parameters
    assert "controller_snapshot" not in parameters
    legacy = inspect.signature(ControllerReservationClient.reserve).parameters
    assert "identity" not in legacy and "receipt" not in legacy


def test_missing_or_caller_supplied_identity_is_refused():
    client = _client()
    with pytest.raises(Exception):
        client.reserve_bound(("ticket",), "arm", _goal(), GOAL_UUID, identity=None,
                             receipt=_receipt())
    with pytest.raises(Exception):
        client.reserve_bound(("ticket",), "arm", _goal(), GOAL_UUID,
                             identity=("forged",), receipt=_receipt())


def test_mismatched_missing_or_late_binding_fails_closed_before_send():
    client = _client()
    sent = []
    client._request = lambda *a, **k: sent.append((a, k))
    ticket = (1,)
    for kwargs in ({"receipt": _receipt(generation=99)},                     # identity mismatch
                   {"receipt": {k: v for k, v in _receipt().items() if k != "deadline_ns"}},
                   {"receipt": _receipt(goal_uuid=str(uuid.uuid4()))},       # goal mismatch
                   {"receipt": _receipt(), "now_ns": 101}):                  # late
        with pytest.raises(Exception):
            client.reserve_bound(ticket, "arm", _goal(), GOAL_UUID, identity=IDENTITY, **kwargs)
    assert sent == [], "a refused reservation still reached the wire"


def test_bound_reservation_carries_every_approved_field():
    client = _client()
    captured = {}

    def capture(kind, operation, generation, goal_uuid, payload):
        captured.update(kind=kind, operation=operation, generation=generation,
                        goal_uuid=goal_uuid, payload=payload)
        return True

    client._request = capture
    assert client.reserve_bound((1,), "arm", _goal(), GOAL_UUID, identity=IDENTITY,
                                receipt=_receipt(), now_ns=50) is True
    payload = captured["payload"]
    size = int.from_bytes(payload[:4], "big")
    binding = json.loads(payload[4:4 + size].decode("utf-8"))
    for field, value in _receipt().items():
        assert binding[field] == value, field
    assert binding["generation"] == IDENTITY[0]
    assert binding["controller_incarnation"] == IDENTITY[1]
    assert binding["controller_boot_incarnation"] == IDENTITY[2]
    assert captured["generation"] == 1 and captured["operation"] == 1
    assert len(payload) > 4 + size, "the serialized goal must follow the binding"
