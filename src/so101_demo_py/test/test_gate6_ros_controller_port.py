"""Phase 3b: the production controller-port adapter is role-scoped and I/O-free for identity."""

import inspect
import socket

import pytest

from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient
from so101_demo.adapters.act.ros_controller_port import RosControllerPort


def _client(*roles):
    endpoints = {role: f"/tmp/endpoint-{role}" for role in roles}
    capabilities = {role: bytes([index + 1]) * 32 for index, role in enumerate(sorted(roles))}
    return ControllerReservationClient(endpoints, capability=capabilities, timeout_s=1.0)


def test_adapter_requires_the_real_client():
    with pytest.raises(TypeError):
        RosControllerPort(object())
    assert RosControllerPort(_client("arm")) is not None


def test_identity_snapshot_is_role_scoped_and_never_does_io(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("identity_snapshot performed I/O")

    monkeypatch.setattr(socket, "socket", explode)
    client = _client("arm", "gripper")
    client._cache_confirmed_identity("arm", generation=3, incarnation="inc-a", boot="boot-a")
    port = RosControllerPort(client)
    assert port.identity_snapshot("arm") == (3, "inc-a", "boot-a")
    with pytest.raises(Exception):
        port.identity_snapshot("gripper")            # not confirmed: fails closed
    with pytest.raises(Exception):
        port.identity_snapshot("neck")               # unknown role


def test_adapter_takes_no_caller_identity_values():
    parameters = inspect.signature(RosControllerPort.identity_snapshot).parameters
    assert "role" in parameters
    for forbidden in ("incarnation", "boot", "generation", "identity", "snapshot"):
        assert forbidden not in parameters, forbidden


def test_the_port_has_no_second_dispatch_path():
    # reserve/send must not exist on the production port: dispatch is unique
    for forbidden in ("reserve", "send", "reserve_bound", "send_prepared"):
        assert not hasattr(RosControllerPort, forbidden), forbidden


def test_close_current_generation_really_closes_and_validates_input():
    client = _client("arm")
    port = RosControllerPort(client)
    with pytest.raises(ValueError, match="GENERATION_INVALID"):
        port.close_current_generation(0)
    with pytest.raises(ValueError, match="GENERATION_INVALID"):
        port.close_current_generation("4")
    assert port.close_current_generation(4) is True    # delegates to a real close
