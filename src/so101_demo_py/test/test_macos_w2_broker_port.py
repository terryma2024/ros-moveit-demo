"""The Worker-side Broker port of the macOS W2 campaign."""

from __future__ import annotations

import pytest

from so101_demo.runtime.macos_w2_broker_port import (
    BrokerAuthority,
    W2BrokerPort,
    W2BrokerPortError,
    authority_from_document,
)


class _Config:
    broker_max_frame_bytes = 4096
    executing_hard_timeout_s = 5.0
    broker_recovery_timeout_s = 1.0


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def call(self, operation, payload=None, **_kwargs):
        self.calls.append((operation, payload))
        return {"operation": operation}


def _factory(record):
    def make(**kwargs):
        client = _Client(**kwargs)
        record.append(client)
        return client
    return make


def test_authority_document_is_reduced_and_refuses_bad_generations() -> None:
    authority = authority_from_document(
        {"healthy": True, "broker_generation": 3, "broker_socket_path": "/private/tmp/x/broker.sock"}
    )
    assert authority == BrokerAuthority(True, 3, "/private/tmp/x/broker.sock")

    for document in (
        {"healthy": True, "broker_generation": 0, "broker_socket_path": "/x"},
        {"healthy": True, "broker_socket_path": "/x"},
        {"healthy": True, "broker_generation": 2, "broker_socket_path": ""},
    ):
        with pytest.raises(W2BrokerPortError):
            authority_from_document(document)


def test_port_refuses_a_non_positive_initial_generation() -> None:
    with pytest.raises(W2BrokerPortError, match="BROKER_GENERATION_AUTHORITY"):
        W2BrokerPort(
            coordinator=lambda: BrokerAuthority(True, 1, "/x"),
            authority=BrokerAuthority(True, 0, "/x"),
            config=_Config(),
            client_factory=_factory([]),
        )


def test_cancel_waits_for_health_then_sends_one_message() -> None:
    answers = [
        BrokerAuthority(False, 1, "/old.sock"),
        BrokerAuthority(False, 1, "/old.sock"),
        BrokerAuthority(True, 1, "/new.sock"),
    ]
    clients: list[_Client] = []
    port = W2BrokerPort(
        coordinator=lambda: answers.pop(0),
        authority=BrokerAuthority(True, 1, "/old.sock"),
        config=_Config(),
        client_factory=_factory(clients),
        sleep=lambda _s: None,
    )

    assert port.cancel_generation("w1", 4) is True

    # The client is rebuilt for the honest authority and the message carries no token or lease.
    assert clients[-1].kwargs["endpoint_path"] == "/new.sock"
    assert clients[-1].kwargs["max_frame_bytes"] == 4096
    assert clients[-1].calls == [
        ("cancel_generation", {"worker_id": "w1", "worker_generation": 4})
    ]


def test_refresh_refuses_a_generation_rollback() -> None:
    port = W2BrokerPort(
        coordinator=lambda: BrokerAuthority(True, 2, "/x"),
        authority=BrokerAuthority(True, 3, "/x"),
        config=_Config(),
        client_factory=_factory([]),
    )
    with pytest.raises(W2BrokerPortError, match="BROKER_GENERATION_ROLLBACK"):
        port.refresh(wait_until_healthy=False)


def test_refresh_times_out_instead_of_waiting_forever() -> None:
    ticks = iter([0.0, 2.0, 4.0, 6.0])
    port = W2BrokerPort(
        coordinator=lambda: BrokerAuthority(False, 1, "/x"),
        authority=BrokerAuthority(True, 1, "/x"),
        config=_Config(),
        client_factory=_factory([]),
        clock=lambda: next(ticks),
        sleep=lambda _s: None,
    )
    with pytest.raises(W2BrokerPortError, match="BROKER_RECOVERY_TIMEOUT"):
        port.refresh(wait_until_healthy=True)


def test_request_model_uses_the_positional_perception_contract() -> None:
    """`parallel_ros_runtime` expects `perception_runner(lease, kind, snapshot, request_one)`."""

    seen = {}

    def runner(*args):
        lease, kind, snapshot, send = args
        seen["args"] = (lease, kind, snapshot)
        seen["sent"] = send("yolo", before_send=None)
        return "admitted"

    port = W2BrokerPort(
        coordinator=lambda: BrokerAuthority(True, 1, "/x"),
        authority=BrokerAuthority(True, 1, "/x"),
        config=_Config(),
        client_factory=_factory([]),
    )

    def request_one(lease, kind, **kwargs):
        seen["request_one"] = (lease, kind, kwargs["model_id"], kwargs["before_send"])
        return {"model_id": kwargs["model_id"]}

    port.request_one = request_one  # the method the driver's chain reaches through `send`

    result = port.request_model(
        "lease", "yolo", snapshot="snap", start_event_id="e1",
        start_event_type="attempt_started", reset_epoch=1, perception_runner=runner,
    )

    assert result == "admitted"
    assert seen["args"] == ("lease", "yolo", "snap")
    assert seen["sent"] == {"model_id": "yolo"}
    assert seen["request_one"] == ("lease", "yolo", "yolo", None)

    with pytest.raises(W2BrokerPortError, match="PERCEPTION_RUNNER_REQUIRED"):
        port.request_model(
            "lease", "yolo", snapshot="snap", start_event_id="e1",
            start_event_type="attempt_started", reset_epoch=1,
        )
