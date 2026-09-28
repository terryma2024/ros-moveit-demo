"""Phase 3b RED: per-role authenticated controller identity (Python surface)."""

import inspect
import socket

import pytest

from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient


def _client(*roles):
    endpoints = {role: f"/tmp/endpoint-{role}" for role in roles}
    capabilities = {role: bytes([index + 1]) * 32 for index, role in enumerate(sorted(roles))}
    return ControllerReservationClient(endpoints, capability=capabilities, timeout_s=1.0)


def test_identity_snapshot_is_role_scoped_and_takes_no_caller_values():
    parameters = inspect.signature(ControllerReservationClient.identity_snapshot).parameters
    assert "role" in parameters
    for forbidden in ("incarnation", "boot", "identity", "snapshot", "now_ns"):
        assert forbidden not in parameters, forbidden


def test_snapshot_returns_the_full_frozen_tuple_and_is_socket_free(monkeypatch):
    def explode(*args, **kwargs):            # any I/O would fail the test
        raise AssertionError("identity_snapshot performed I/O")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    monkeypatch.setattr(socket, "socketpair", explode)
    client = _client("arm")
    client._cache_confirmed_identity("arm", generation=7, incarnation="inc-1", boot="boot-1")
    assert client.identity_snapshot("arm") == (7, "inc-1", "boot-1")


def test_unavailable_unknown_and_malformed_identities_fail_closed():
    client = _client("arm")
    with pytest.raises(Exception):
        client.identity_snapshot("arm")                       # nothing confirmed yet
    with pytest.raises(Exception):
        client.identity_snapshot("neck")                      # not configured
    for bad in ({"generation": 0, "incarnation": "i", "boot": "b"},
                {"generation": 1, "incarnation": "", "boot": "b"},
                {"generation": 1, "incarnation": "i", "boot": ""},
                {"generation": 1, "incarnation": "i" * 65, "boot": "b"},
                {"generation": 1, "incarnation": "i\x00", "boot": "b"}):
        with pytest.raises(Exception):
            client._cache_confirmed_identity("arm", **bad)


def test_transport_close_keeps_confirmed_identity_and_invalidation_clears_one_role():
    client = _client("arm", "gripper")
    client._cache_confirmed_identity("arm", generation=1, incarnation="inc-a", boot="boot-a")
    client._cache_confirmed_identity("gripper", generation=1, incarnation="inc-g", boot="boot-g")
    client._drop_transport()
    assert client.identity_snapshot("arm") == (1, "inc-a", "boot-a")
    assert client.identity_snapshot("gripper") == (1, "inc-g", "boot-g")
    client._invalidate_identity("arm", reason="identity_change")
    with pytest.raises(Exception):
        client.identity_snapshot("arm")
    assert client.identity_snapshot("gripper") == (1, "inc-g", "boot-g")


def test_missing_role_never_borrows_another_roles_identity():
    client = _client("arm", "gripper")
    client._cache_confirmed_identity("gripper", generation=1, incarnation="inc-g", boot="boot-g")
    with pytest.raises(Exception):
        client.identity_snapshot("arm")


def test_reserve_bound_has_no_caller_authority_surface():
    parameters = inspect.signature(ControllerReservationClient.reserve_bound).parameters
    for forbidden in ("now_ns", "resolver", "identity", "receipt", "controller_snapshot"):
        assert forbidden not in parameters, forbidden
    assert "handle" in parameters
    from so101_demo.adapters.act import controller_reservation_client as module

    assert hasattr(module, "_encode_bound_frame")
    assert not hasattr(module, "encode_bound_frame")
    assert not hasattr(ControllerReservationClient, "_resolved_payload")
    client = _client("arm")
    with pytest.raises(Exception):
        client.reserve_bound(("t",), "arm", object(), "uuid", handle="h", now_ns=1)
