"""Owner liveness uses child receive time and one generation-owned connection."""

import importlib
from types import SimpleNamespace as NS

import pytest


def case():
    now = NS(ns=100)
    module = importlib.import_module("so101_demo.runtime.container_campaign.heartbeat")
    return now, module.OwnerHeartbeatMonitor(generation=7, timeout_ns=50, monotonic_ns=lambda: now.ns)


def packet(sequence=1, **changes):
    return dict(kind="owner_heartbeat", generation=7, sequence=sequence, sent_monotonic_ns=1) | changes


def test_receiver_time_controls_expiry_and_sender_time_never_extends_it():
    now, monitor = case()
    connection = object()
    now.ns = 120
    monitor.receive(packet(sent_monotonic_ns=10**18), connection=connection)
    now.ns = 169
    assert monitor.expired is False
    now.ns = 170
    assert monitor.expired is True
    with pytest.raises(ValueError, match="OWNER_HEARTBEAT_FENCED"):
        monitor.receive(packet(2), connection=connection)


@pytest.mark.parametrize("bad", [packet(generation=6), packet(sequence=True), packet(lease="secret"),
    packet(kind="service_health"), packet(sent_monotonic_ns=float("nan"))])
def test_wrong_generation_or_open_format_cannot_refresh_deadline(bad):
    now, monitor = case()
    now.ns = 120
    with pytest.raises(ValueError, match="OWNER_HEARTBEAT_INVALID"):
        monitor.receive(bad, connection=object())
    now.ns = 150
    assert monitor.expired is True


def test_sequence_rollback_and_connection_takeover_refused_without_refresh():
    now, monitor = case()
    connection = object()
    monitor.receive(packet(2), connection=connection)
    now.ns = 120
    with pytest.raises(ValueError, match="OWNER_HEARTBEAT_INVALID"):
        monitor.receive(packet(1), connection=connection)
    with pytest.raises(ValueError, match="OWNER_HEARTBEAT_CONNECTION_OWNED"):
        monitor.receive(packet(3), connection=object())
    now.ns = 150
    assert monitor.expired is True


def test_owned_disconnect_fences_immediately_and_unrelated_rpc_disconnect_does_not():
    _now, monitor = case()
    connection = object()
    monitor.receive(packet(), connection=connection)
    monitor.disconnected(object())
    assert not monitor.expired
    monitor.disconnected(connection)
    assert monitor.expired and monitor.reason == "OWNER_CONNECTION_LOST"


def test_bad_clock_is_permanently_fenced_instead_of_later_comparing_invalid_value():
    now, monitor = case()
    now.ns = "invalid"
    assert monitor.expired
    now.ns = 200
    assert monitor.expired and monitor.reason == "OWNER_CLOCK_REGRESSION"
