from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import threading
import time
from types import SimpleNamespace

import pytest


def request(**changes):
    value = {
        "schema_version": 1,
        "kind": "coordinator_call",
        "coordinator_epoch": 7,
        "worker_id": "worker-01",
        "worker_generation": 2,
        "lease": {
            "batch_id": "batch-1",
            "coordinator_epoch": 7,
            "worker_id": "worker-01",
            "worker_generation": 2,
            "point_id": "task_start",
            "attempt_id": "attempt-1",
            "lease_generation": 1,
        },
        "request_id": "request-1",
        "idempotency_key": "same-operation-1",
        "token": "ab" * 32,
        "payload": {"operation": "heartbeat"},
    }
    value.update(changes)
    return value


def test_codec_rejects_noncanonical_duplicate_unknown_and_bad_frames():
    from so101_demo.runtime.parallel_ipc import IpcError, decode_frame, encode_frame

    canonical = json.dumps(request(), sort_keys=True, separators=(",", ":")).encode()
    assert decode_frame(struct.pack(">I", len(canonical)) + canonical) == request()
    cases = [
        b"\0\0\0\0",
        struct.pack(">I", 999) + b"{}",
        struct.pack(">I", 2) + b"{}x",
        struct.pack(">I", 5) + b"{}",
        struct.pack(">I", 2) + b"\xff\xff",
        struct.pack(">I", 13) + b'{"a":1,"a":2}',
        struct.pack(">I", len(b'{"z":1, "a":2}')) + b'{"z":1, "a":2}',
    ]
    for frame in cases:
        with pytest.raises(IpcError):
            decode_frame(frame, max_frame_bytes=128)
    with pytest.raises(IpcError):
        encode_frame({"blob": "x" * 200}, max_frame_bytes=64)


@pytest.mark.parametrize(
    "change,error",
    [
        ({"token": "cd" * 32}, "TOKEN"),
        ({"coordinator_epoch": 6}, "EPOCH"),
        ({"worker_generation": 1}, "GENERATION"),
        ({"lease": None}, "LEASE"),
        ({"extra": True}, "FIELDS"),
    ],
)
def test_authority_rejects_wrong_token_fields_and_stale_identity(tmp_path, change, error):
    from so101_demo.runtime.parallel_ipc import IpcError, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    with pytest.raises(IpcError, match=error):
        authority.authenticate(request(**change))


def test_authority_rejects_missing_wrong_types_and_bool_as_int(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    for value in (
        {key: item for key, item in request().items() if key != "request_id"},
        request(request_id=1),
        request(worker_generation=True),
        request(kind="unknown"),
    ):
        with pytest.raises(IpcError):
            authority.authenticate(value)


def test_authority_accepts_explicit_private_external_ipc_root(tmp_path):
    from so101_demo.runtime.parallel_ipc import WorkerTokenAuthority

    evidence_root = tmp_path / "durable"
    evidence_root.mkdir()
    ipc_root = tmp_path / "runtime-ipc"
    ipc_root.mkdir(mode=0o700)

    authority = WorkerTokenAuthority(
        evidence_root, coordinator_epoch=7, ipc_root=ipc_root
    )

    assert authority.ipc_root == ipc_root
    assert authority.issue("worker-01", 1).is_relative_to(ipc_root)


def test_generation_advance_retires_old_lease_instead_of_rewriting_it(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    authority.advance_generation("worker-01", 2, 3)
    rewritten = request(
        worker_generation=3,
        lease={**request()["lease"], "worker_generation": 3},
    )
    with pytest.raises(IpcError, match="LEASE"):
        authority.authenticate(rewritten)


def test_dropped_generation_register_ack_retries_with_retired_old_authority(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    message = request(
        worker_generation=2,
        lease=None,
        request_id="register-generation-3",
        idempotency_key="register-generation-3",
        payload={"operation": "register_worker", "generation": 3},
    )
    calls = []
    def register(_message):
        calls.append("mutated")
        authority.advance_generation("worker-01", 2, 3)
        return {"generation": 3, "state": "RECOVERING"}
    expected = authority.dispatch(message, register)
    assert authority.dispatch(message, lambda _message: calls.append("double")) == expected
    assert calls == ["mutated"]
    changed = {**message, "request_id": "old-generation-new-request", "idempotency_key": "new"}
    with pytest.raises(IpcError, match="GENERATION"):
        authority.dispatch(changed, lambda _message: None)


def test_idempotency_replay_ack_loss_and_conflict(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    calls = []
    first = authority.dispatch(request(), lambda value: calls.append(value) or {"ok": 1})
    first["ok"] = 999
    retry = authority.dispatch(request(), lambda _value: calls.append("duplicate"))
    assert retry == {"ok": 1}
    assert len(calls) == 1
    changed = request(payload={"operation": "heartbeat", "changed": True})
    with pytest.raises(IpcError, match="IDEMPOTENCY"):
        authority.dispatch(changed, lambda _value: None)


def test_private_token_and_real_authenticated_socket_round_trip(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        UnixRpcClient,
        WorkerTokenAuthority,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    token_path = authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    server = AuthenticatedUnixServer(
        tmp_path / "ipc/coordinator.sock",
        authority,
        lambda value: {"seen": value["payload"]["operation"]},
        deadline_s=1.0,
    )
    thread = threading.Thread(target=server.serve_once)
    thread.start()
    response = UnixRpcClient(server.path, deadline_s=1.0).call(request())
    thread.join(timeout=2)
    server.close()
    assert response["payload"] == {"seen": "heartbeat"}
    assert stat_mode(tmp_path / "ipc") == 0o700
    assert stat_mode(token_path) == 0o600
    assert server.bound_mode == 0o600


def test_server_contains_reply_disconnect_to_the_single_client(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        WorkerTokenAuthority,
        encode_frame,
        transport_address,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    handler_entered = threading.Event()
    release_handler = threading.Event()

    def handler(_value):
        handler_entered.set()
        assert release_handler.wait(1.0)
        return {"ok": True}

    server = AuthenticatedUnixServer(
        tmp_path / "ipc/coordinator.sock",
        authority,
        handler,
        deadline_s=1.0,
    )
    errors = []

    def serve():
        try:
            server.serve_once()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve)
    thread.start()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        parent_fd = os.open(
            server.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            connection.connect(transport_address(server.path, parent_fd))
        finally:
            os.close(parent_fd)
        connection.sendall(encode_frame(request()))
        connection.shutdown(socket.SHUT_WR)
        assert handler_entered.wait(1.0)
        connection.setsockopt(
            socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
        )
    release_handler.set()
    thread.join(timeout=2.0)
    server.close()
    assert not thread.is_alive()
    assert errors == []


def test_broker_transport_validates_locally_before_real_socket_mutation(
    tmp_path,
):
    from so101_demo.parallel_batch.broker import BrokerResponse, BrokerSubmission
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        InferenceRequest,
        ModelOutcome,
        NormalizedInferenceResponseIdentity,
    )
    from so101_demo.runtime.parallel_ipc import (
        BrokerTransport, IpcError, UnixRpcClient,
    )
    from so101_demo.runtime.parallel_perception_runtime import Snapshot

    (tmp_path / "ipc").mkdir(mode=0o700)
    transport = BrokerTransport(
        ipc_root=tmp_path / "ipc",
        config=SimpleNamespace(broker_max_frame_bytes=8 * 1024 * 1024),
        generation=1,
        deadline_s=1.0,
        runtime_identity={
            "connection_handler_count": 8,
            "yolo_executor_count": 2,
            "grounded_sam_executor_count": 1,
            "queue_capacity_per_model": 8,
        },
    )
    inference = InferenceRequest(
        request_id="attempt-1-yolo",
        model_id="plastic-cup-yolo11n-seg-v1",
        execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-1",
        coordinator_epoch=7,
        worker_id="worker-01",
        worker_generation=2,
        point_id="task_start",
        lease_generation=1,
        reset_epoch="reset-1",
        image_timestamp_s=12.0,
        input_relative_path=(
            "worker-01/attempts/task_start/attempt-1/working/"
            "perception/input/rgb.npy"
        ),
        input_sha256="ef" * 32,
        deadline_s=5.0,
        attempt_id="attempt-1",
    )
    snapshot = Snapshot(
        (4, 5, 3),
        12_000_000_000,
        "task_camera_frame",
        "attempt-start-attempt-1",
        "ATTEMPT_STARTED",
        NormalizedInferenceResponseIdentity.from_request(inference),
    )
    response = BrokerResponse(
        inference,
        1,
        ModelOutcome.QUALIFIED,
        {"candidate": "real-service-result"},
        None,
        1.0,
        2.0,
        1.1,
        2.1,
        1.2,
    )

    class Service:
        def __init__(self):
            self.mutations = []
            self.broker = SimpleNamespace(
                cancel_generation=lambda *_args: self.mutations.append("cancel")
            )

        def submit(self, actual_request, actual_snapshot):
            self.mutations.append((actual_request, actual_snapshot))
            return BrokerSubmission(True)

        def run_next(self):
            raise AssertionError("transport must not run inference inline")

        def wait_response(self, actual_request, timeout_s):
            assert actual_request == inference
            assert timeout_s == 1.0
            return response

        def poll_response(self, _request):
            return response

    service = Service()
    socket_path = tmp_path / "ipc/perception.sock"
    server = transport.server(service, endpoint=socket_path)
    assert server.max_concurrent_connections == 8
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    message = request(
        kind="broker_call",
        request_id="broker-request-1",
        idempotency_key="broker-request-1",
        payload={
            "operation": "infer",
            "request": {
                **asdict(inference),
                "execution_kind": inference.execution_kind.value,
            },
            "snapshot": {
                "shape": list(snapshot.shape),
                "source_stamp_ns": snapshot.source_stamp_ns,
                "source_frame_id": snapshot.source_frame_id,
                "start_event_id": snapshot.start_event_id,
                "start_event_type": snapshot.start_event_type,
                "start_identity": {
                    **asdict(snapshot.start_identity),
                    "execution_kind": snapshot.start_identity.execution_kind.value,
                },
                "query_class_id": snapshot.query_class_id,
            },
        },
    )
    reply = UnixRpcClient(socket_path, deadline_s=1.0).call(message)
    replay = UnixRpcClient(socket_path, deadline_s=1.0).call(message)
    server.close()
    assert server.wait_handlers(timeout_s=1.0) is True
    thread.join(timeout=2.0)

    assert reply["payload"]["outcome"] == "QUALIFIED"
    assert reply["payload"]["candidate"] == {"candidate": "real-service-result"}
    assert replay == reply
    assert service.mutations == [(inference, snapshot), (inference, snapshot)]
    metrics = transport.metrics_snapshot()
    assert metrics["logical_inference_count"] == 1
    assert "replay_count" not in metrics
    assert metrics["transport_errors"].get("TRUNCATED_FRAME", 0) == 0
    assert {
        "accepted", "received", "validated", "serialized", "sent"
    }.issubset({event["event"] for event in metrics["events"]})
    assert "authority_call_count" not in metrics
    assert "journal_replay_hot_path_count" not in metrics
    summary_path = transport.persist_metrics_summary()
    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert persisted == {
        "schema_version": 1,
        "kind": "broker_concurrency_summary",
        **metrics,
    }
    assert summary_path.stat().st_mode & 0o777 == 0o600

    assert transport.report_health_down({
        "outcome": "INFERENCE_TIMEOUT",
        "request_id": inference.request_id,
        "reason": "deadline exceeded",
    }) is True
    with pytest.raises(IpcError, match="BROKER_HEALTH_DOWN_OUTCOME"):
        transport.report_health_down({
            "outcome": "MODEL_ERROR",
            "request_id": inference.request_id,
            "reason": "deterministic model result",
        })

    ready = {
        "schema_version": 1,
        "kind": "so101_parallel_broker_ready",
        "batch_id": "batch-1",
        "coordinator_epoch": 7,
        "broker_generation": 1,
        "image_id": "sha256:" + "b" * 64,
        "models": {"model": {"ready": True, "sha256": "c" * 64}},
    }
    ready_sha = transport.bind_ready_identity(ready)
    health_server = transport.server(service, endpoint=socket_path)
    health_thread = threading.Thread(target=health_server.serve_once)
    health_thread.start()
    health = request(
        kind="broker_call",
        lease=None,
        request_id="broker-health-1",
        idempotency_key="broker-health-1",
        payload={"operation": "health", "ready_sha256": ready_sha},
    )
    health_reply = UnixRpcClient(socket_path, deadline_s=1.0).call(health)
    health_thread.join(timeout=2.0)
    health_server.close()
    assert health_reply["payload"] == {
        "ready": ready,
        "ready_sha256": ready_sha,
    }
    assert service.mutations == [(inference, snapshot), (inference, snapshot)]


def test_broker_summary_survives_runtime_start_failure(tmp_path):
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config
    from so101_demo.runtime.parallel_ipc import BrokerTransport
    from so101_demo.runtime.parallel_perception_runtime import GROUNDED_ID, YOLO_ID

    ipc_root = tmp_path / "ipc"
    ipc_root.mkdir(mode=0o700)
    config = load_parallel_runtime_config(
        Path(__file__).parents[1] / "config/mujoco/parallel_batch_v1.yaml"
    )
    transport = BrokerTransport(
        ipc_root=ipc_root,
        config=config,
        generation=1,
        deadline_s=1.0,
    )

    class FailedRuntime:
        executor_counts = {YOLO_ID: 1, GROUNDED_ID: 1}
        health_changed = lambda _healthy: None

        def start(self):
            raise RuntimeError("controlled startup failure")

        def _unhealthy(self):
            self.health_changed(False)

    with pytest.raises(RuntimeError, match="controlled startup failure"):
        transport.serve(FailedRuntime(), endpoint=ipc_root / "perception.sock")

    summary = json.loads(
        (ipc_root / "broker-concurrency-summary.json").read_text(encoding="utf-8")
    )
    assert summary["kind"] == "broker_concurrency_summary"
    assert summary["events"] == []


def test_server_bounds_handler_and_response_send_to_one_absolute_deadline(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        IpcError,
        UnixRpcClient,
        WorkerTokenAuthority,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    server = AuthenticatedUnixServer(
        tmp_path / "ipc/coordinator.sock",
        authority,
        lambda _value: time.sleep(0.2),
        deadline_s=0.05,
    )
    thread = threading.Thread(target=server.serve_once)
    started = time.monotonic()
    thread.start()
    with pytest.raises((IpcError, ConnectionError, BrokenPipeError)):
        UnixRpcClient(server.path, deadline_s=0.2).call(request())
    thread.join(timeout=0.3)
    server.close()
    assert not thread.is_alive()
    assert time.monotonic() - started < 0.3


def test_server_accept_idle_does_not_consume_request_deadline(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        UnixRpcClient,
        WorkerTokenAuthority,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    server = AuthenticatedUnixServer(
        tmp_path / "ipc/coordinator.sock",
        authority,
        lambda _message: time.sleep(0.05) or {"ok": True},
        deadline_s=0.20,
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        time.sleep(0.18)
        assert UnixRpcClient(server.path, deadline_s=0.5).call(request())[
            "payload"
        ] == {"ok": True}
    finally:
        server.close()
        thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_server_handler_timeout_returns_structured_error(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        IpcError,
        UnixRpcClient,
        WorkerTokenAuthority,
        _BrokerMetrics,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    metrics = _BrokerMetrics()
    server = AuthenticatedUnixServer(
        tmp_path / "ipc/coordinator.sock",
        authority,
        lambda _message: time.sleep(0.20),
        deadline_s=0.05,
        metrics=metrics,
    )
    thread = threading.Thread(target=server.serve_once)
    thread.start()
    try:
        with pytest.raises(IpcError, match="HANDLER_DEADLINE_EXCEEDED"):
            UnixRpcClient(server.path, deadline_s=0.5).call(request())
    finally:
        thread.join(timeout=1.0)
        server.close()
    assert not thread.is_alive()
    timeout = next(
        event for event in metrics.snapshot()["events"]
        if event["event"] == "handler_timeout"
    )
    assert timeout["timeout_phase"] == "received"
    assert type(timeout["phase_started_monotonic_s"]) is float


def test_server_eight_distinct_requests_enter_handlers_concurrently(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        UnixRpcClient,
        _BrokerMetrics,
        _StatelessBrokerDispatcher,
    )

    root = tmp_path
    metrics = _BrokerMetrics()
    ipc_root = root / "ipc"
    ipc_root.mkdir(mode=0o700)
    authority = _StatelessBrokerDispatcher(ipc_root, metrics)
    all_entered = threading.Barrier(8)
    active = 0
    maximum_active = 0
    active_lock = threading.Lock()

    def handler(message):
        nonlocal active, maximum_active
        with active_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            all_entered.wait(timeout=1.0)
            return {"request_id": message["request_id"]}
        finally:
            with active_lock:
                active -= 1

    server = AuthenticatedUnixServer(
        root / "ipc/broker.sock",
        authority,
        handler,
        deadline_s=2.0,
        max_concurrent_connections=8,
        metrics=metrics,
    )
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    replies = []
    errors = []

    def call(index):
        message = request(
            kind="broker_call",
            request_id=f"request-{index}",
            idempotency_key=f"operation-{index}",
            payload={"operation": "infer"},
        )
        try:
            replies.append(
                UnixRpcClient(server.path, deadline_s=3.0).call(message)["payload"]
            )
        except BaseException as error:
            errors.append(error)

    clients = [threading.Thread(target=call, args=(index,)) for index in range(8)]
    for client in clients:
        client.start()
    for client in clients:
        client.join(timeout=4.0)
    server.close()
    assert server.wait_handlers(timeout_s=2.0) is True
    server_thread.join(timeout=2.0)

    assert not server_thread.is_alive()
    assert all(not client.is_alive() for client in clients)
    assert errors == []
    assert maximum_active == 8
    assert sorted(reply["request_id"] for reply in replies) == [
        f"request-{index}" for index in range(8)
    ]
    summary = metrics.snapshot()
    assert summary["pending_rpc_peak"] == 8
    assert summary["logical_inference_count"] == 8
    assert "replay_count" not in summary
    assert summary["transport_errors"].get("TRUNCATED_FRAME", 0) == 0


def test_pending_mutation_same_key_executes_once_and_replays_terminal_result(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        UnixRpcClient,
        WorkerTokenAuthority,
    )

    root = tmp_path
    worker_authority = WorkerTokenAuthority(root, coordinator_epoch=7)
    worker_authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    worker_authority.bind_lease("worker-01", 2, request()["lease"])
    authority = worker_authority
    mutation_entered = threading.Event()
    release_mutation = threading.Event()
    mutation_calls = []

    def handler(_message):
        mutation_calls.append("called")
        mutation_entered.set()
        assert release_mutation.wait(timeout=1.0)
        return {"value": [1, 2, 3]}

    server = AuthenticatedUnixServer(
        root / "ipc/broker.sock",
        authority,
        handler,
        deadline_s=2.0,
        max_concurrent_connections=2,
    )
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    replies = []
    errors = []

    def call():
        try:
            replies.append(
                UnixRpcClient(server.path, deadline_s=3.0).call(request())["payload"]
            )
        except BaseException as error:
            errors.append(error)

    clients = [threading.Thread(target=call) for _ in range(2)]
    for client in clients:
        client.start()
    assert mutation_entered.wait(timeout=1.0)
    time.sleep(0.05)
    assert mutation_calls == ["called"]
    release_mutation.set()
    for client in clients:
        client.join(timeout=3.0)
    server.close()
    assert server.wait_handlers(timeout_s=2.0) is True
    server_thread.join(timeout=2.0)

    assert errors == []
    assert mutation_calls == ["called"]
    assert replies == [{"value": [1, 2, 3]}, {"value": [1, 2, 3]}]
    replies[0]["value"].append(4)
    assert replies[1] == {"value": [1, 2, 3]}


def test_pending_mutation_failure_is_published_before_waiters_wake(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        IpcError,
        WorkerTokenAuthority,
    )

    root = tmp_path
    worker_authority = WorkerTokenAuthority(root, coordinator_epoch=7)
    worker_authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    worker_authority.bind_lease("worker-01", 2, request()["lease"])
    authority = worker_authority
    mutation_entered = threading.Event()
    release_mutation = threading.Event()
    calls = []
    errors = []

    def mutation(_message):
        calls.append("called")
        mutation_entered.set()
        assert release_mutation.wait(timeout=1.0)
        raise IpcError("EXPECTED_FAILURE")

    def dispatch():
        try:
            authority.dispatch(request(), mutation)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=dispatch) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert mutation_entered.wait(timeout=1.0)
    time.sleep(0.05)
    assert calls == ["called"]
    release_mutation.set()
    for thread in threads:
        thread.join(timeout=2.0)

    assert all(not thread.is_alive() for thread in threads)
    assert calls == ["called"]
    assert len(errors) == 2
    assert all(isinstance(error, IpcError) for error in errors)
    assert [str(error) for error in errors] == ["EXPECTED_FAILURE"] * 2
    with pytest.raises(IpcError, match="EXPECTED_FAILURE"):
        authority.dispatch(request(), lambda _message: calls.append("double"))
    assert calls == ["called"]


def test_default_server_remains_serial(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        UnixRpcClient,
        WorkerTokenAuthority,
    )

    root = tmp_path
    authority = WorkerTokenAuthority(root, coordinator_epoch=7)
    authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    authority.bind_lease("worker-01", 2, request()["lease"])
    first_entered = threading.Event()
    release_first = threading.Event()
    entered = []

    def handler(message):
        entered.append(message["request_id"])
        if message["request_id"] == "request-1":
            first_entered.set()
            assert release_first.wait(timeout=1.0)
        return {"request_id": message["request_id"]}

    server = AuthenticatedUnixServer(
        root / "ipc/coordinator.sock",
        authority,
        handler,
        deadline_s=2.0,
    )
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    errors = []

    def call(message):
        try:
            UnixRpcClient(server.path, deadline_s=3.0).call(message)
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=call, args=(request(),))
    second = threading.Thread(
        target=call,
        args=(
            request(request_id="request-2", idempotency_key="operation-2"),
        ),
    )
    first.start()
    assert first_entered.wait(timeout=1.0)
    second.start()
    time.sleep(0.05)
    assert entered == ["request-1"]
    release_first.set()
    first.join(timeout=3.0)
    second.join(timeout=3.0)
    server.close()
    assert server.wait_handlers(timeout_s=1.0) is True
    server_thread.join(timeout=2.0)

    assert errors == []
    assert entered == ["request-1", "request-2"]


def test_client_rejects_wrong_response_schema_and_union(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        IpcError,
        UnixRpcClient,
        encode_frame,
        receive_frame,
    )

    root = tmp_path
    path = root / "s"
    replies = [
        {"schema_version": 2, "kind": "response", "request_id": "request-1", "idempotency_key": "same-operation-1", "ok": True, "payload": {}, "error": None},
        {"schema_version": 1, "kind": "wrong", "request_id": "request-1", "idempotency_key": "same-operation-1", "ok": True, "payload": {}, "error": None},
        {"schema_version": 1, "kind": "response", "request_id": "request-1", "idempotency_key": "same-operation-1", "ok": True, "payload": {}, "error": "also-error"},
    ]
    for reply in replies:
        from so101_demo.runtime.parallel_ipc import transport_address
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            listener.bind(transport_address(path, parent_fd))
        finally:
            os.close(parent_fd)
        listener.listen(1)
        def serve():
            connection, _ = listener.accept()
            with connection:
                receive_frame(connection, deadline_s=1.0)
                connection.sendall(encode_frame(reply))
            listener.close()
        thread = threading.Thread(target=serve)
        thread.start()
        with pytest.raises(IpcError):
            UnixRpcClient(path).call(request())
        thread.join()
        path.unlink()


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_supervisor_fails_on_early_exit_and_preserves_unowned_processes():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
        SupervisorError,
    )

    owned = OwnedProcess("batch-1", "worker", 101, 101, ("worker",), 50)
    identities = {101: owned}
    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        signal_group=lambda pgid, sig: signals.append((pgid, sig)),
    )
    supervisor._record_started(owned, poll=lambda: 9)
    with pytest.raises(SupervisorError, match="EARLY_EXIT"):
        supervisor.assert_healthy()
    assert signals == []
    with pytest.raises(SupervisorError, match="UNOWNED"):
        OwnedProcess("batch-1", "database", 202, 202, ("db",), 1)


def test_supervisor_cleanup_order_pid_reuse_and_failure_are_visible():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
    )

    owned = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 50)
    identities = {101: owned}
    order = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        signal_group=lambda pgid, sig: order.append(("signal", pgid, sig)),
    )
    supervisor._record_started(owned, poll=lambda: None)
    result = supervisor.shutdown(
        stop_leases=lambda: order.append("stop-leases") or True,
        cancel_goal=lambda: order.append("cancel-goal") or True,
        confirm_goal_cancelled=lambda: order.append("confirm-goal") or True,
        request_recovery=lambda: order.append("recovery") or True,
        wait_group=lambda _process, _timeout: True,
    )
    assert result is True
    assert order[:4] == ["stop-leases", "cancel-goal", "confirm-goal", "recovery"]
    assert order[4] == ("signal", 101, signal.SIGTERM)

    reused = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        signal_group=lambda pgid, sig: order.append(("signal", pgid, sig)),
    )
    reused._record_started(owned, poll=lambda: None)
    identities[101] = OwnedProcess("batch-1", "broker", 101, 101, ("other",), 51)
    assert reused.shutdown(wait_group=lambda _process, _timeout: True) is False
    assert ("signal", 101, signal.SIGTERM) not in order[5:]

    identities[101] = owned
    failing = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        signal_group=lambda pgid, sig: order.append(("signal", pgid, sig)),
    )
    failing._record_started(owned, poll=lambda: None)
    assert failing.shutdown(
        stop_leases=lambda: False,
        wait_group=lambda _process, _timeout: False,
    ) is False
    assert ("signal", 101, signal.SIGKILL) in order


def test_child_identity_failure_never_signals_an_unverified_or_reused_group(monkeypatch):
    from so101_demo.runtime.parallel_processes import ProcessSupervisor, SupervisorError
    import so101_demo.runtime.parallel_processes as processes

    class Child:
        pid = 701
        returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            events.append("terminate-child")
            self.returncode = -15
        def wait(self, timeout):
            events.append(("reap-child", timeout))
            return self.returncode

    reads = iter(((0, (), 0),) + ((900, ("unrelated",), 99),) * 99)
    monkeypatch.setattr(processes, "_proc_values", lambda _pid: next(reads))
    signals = []
    events = []
    supervisor = ProcessSupervisor(
        "batch-1", popen=lambda *_args, **_kwargs: Child(),
        signal_group=lambda pgid, value: signals.append((pgid, value)),
    )
    with pytest.raises(SupervisorError, match="CHILD_IDENTITY"):
        supervisor.start("worker", ("worker",))
    assert signals == []
    assert events == ["terminate-child", ("reap-child", 1.0)]


def test_supervisor_boundedly_waits_for_child_to_establish_its_own_session(monkeypatch):
    from so101_demo.runtime.parallel_processes import ProcessSupervisor
    import so101_demo.runtime.parallel_processes as processes

    class Child:
        pid = 701

        def poll(self):
            return None

    reads = iter((
        (600, ("worker",), 50),
        (600, ("worker",), 50),
        (701, ("worker",), 50),
    ))
    monkeypatch.setattr(processes, "_proc_values", lambda _pid: next(reads))
    yields = []
    monkeypatch.setattr(processes.time, "sleep", lambda delay: yields.append(delay))
    supervisor = ProcessSupervisor(
        "batch-1", popen=lambda *_args, **_kwargs: Child(),
    )

    owned = supervisor.start("worker", ("worker",))

    assert owned.pid == owned.pgid == 701
    assert owned.cmdline == ("worker",)
    assert owned.start_time == 50
    assert yields == [0.001, 0.001]


def test_worker_shutdown_uses_bounded_interrupt_before_termination():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    owned = OwnedProcess("batch-1", "worker", 701, 701, ("worker",), 12)
    signals = []
    waits = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: owned,
        signal_group=lambda pgid, value: signals.append((pgid, value)),
    )
    supervisor._record_started(owned, poll=lambda: None)
    assert supervisor.shutdown(
        wait_group=lambda _process, timeout: waits.append(timeout) or len(waits) == 2,
        interrupt_timeout_s=1.0,
        term_timeout_s=2.0,
    ) is True
    assert signals == [(701, signal.SIGINT), (701, signal.SIGTERM)]
    assert waits == [1.0, 2.0]


def test_broker_cancel_generation_is_lease_optional_and_strict(tmp_path):
    from so101_demo.runtime.parallel_ipc import WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    token = bytes.fromhex("ab" * 32)
    authority.install_token("worker-01", 1, token)
    message = request(
        worker_generation=1,
        lease=None,
        payload={
            "operation": "cancel_generation",
            "worker_id": "worker-01",
            "worker_generation": 1,
        },
    )
    assert authority.authenticate(message)["payload"]["operation"] == "cancel_generation"


@pytest.mark.parametrize("operation", ["readiness", "release_start"])
def test_adaptive_start_control_operations_are_lease_optional(tmp_path, operation):
    from so101_demo.runtime.parallel_ipc import WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 1, bytes.fromhex("ab" * 32))
    message = request(
        worker_generation=1,
        lease=None,
        payload={"operation": operation},
    )

    assert authority.authenticate(message)["payload"]["operation"] == operation


def test_unlisted_worker_control_operation_still_requires_a_lease(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 1, bytes.fromhex("ab" * 32))

    with pytest.raises(IpcError, match="LEASE_REQUIRED"):
        authority.authenticate(
            request(
                worker_generation=1,
                lease=None,
                payload={"operation": "run_point"},
            )
        )


def test_authenticated_readiness_control_round_trip_without_a_lease(tmp_path):
    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        UnixRpcClient,
        WorkerTokenAuthority,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    authority.install_token("worker-01", 1, bytes.fromhex("ab" * 32))
    message = request(
        worker_generation=1,
        lease=None,
        payload={"operation": "readiness"},
    )
    server = AuthenticatedUnixServer(
        tmp_path / "ipc/readiness.sock",
        authority,
        lambda authenticated: {
            "seen": authenticated["payload"]["operation"]
        },
        deadline_s=1.0,
    )
    thread = threading.Thread(target=server.serve_once)
    thread.start()

    response = UnixRpcClient(server.path, deadline_s=1.0).call(message)

    thread.join(timeout=2.0)
    server.close()
    assert response["payload"] == {"seen": "readiness"}


def test_authenticated_server_accepts_sixteen_handlers_and_rejects_seventeen(tmp_path):
    """The connection server supports the worker ceiling and rejects one above it."""

    from so101_demo.runtime.parallel_ipc import (
        AuthenticatedUnixServer,
        IpcError,
        WorkerTokenAuthority,
    )

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    server = AuthenticatedUnixServer(
        tmp_path / "ipc/w16.sock",
        authority,
        lambda _message: {},
        max_concurrent_connections=16,
    )
    try:
        assert server.max_concurrent_connections == 16
    finally:
        server.close()

    with pytest.raises(IpcError, match="MAX_CONCURRENT_CONNECTIONS_LIMIT"):
        AuthenticatedUnixServer(
            tmp_path / "ipc/w17.sock",
            authority,
            lambda _message: {},
            max_concurrent_connections=17,
        )


def test_broker_runtime_decoder_accepts_the_exact_producer_identity_fields(tmp_path, monkeypatch):
    from so101_demo.runtime import parallel_ipc

    ipc_root = tmp_path / "ipc"
    ipc_root.mkdir()
    config = ipc_root / "runtime-config.yaml"
    config.write_bytes(
        (Path(__file__).parents[1] / "config/mujoco/parallel_batch_v1.yaml").read_bytes()
    )
    document = {
        "schema_version": 1,
        "kind": "so101_parallel_broker_runtime",
        "batch_id": "batch-1",
        "coordinator_epoch": 3,
        "broker_generation": 1,
        "run_mode": "plan_only",
        "image_id": "sha256:" + "b" * 64,
        "yolo_weights_sha256": "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781",
        "grounded_manifest_sha256": "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05",
        "config_path": str(config),
        "request_deadline_s": 5.0,
        "max_frame_bytes": 8388608,
    }
    spec = tmp_path / "broker-spec.json"
    spec.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    transport = parallel_ipc.build_broker_transport(spec)
    assert transport.generation == 1
    assert transport.runtime_identity == document
    adaptive_document = {
        **document,
        "queue_capacity_per_model": 16,
        "connection_handler_count": 16,
        "yolo_executor_count": 2,
        "grounded_sam_executor_count": 1,
        "request_deadline_s": 75.0,
    }
    spec.write_text(
        json.dumps(adaptive_document, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    adaptive_transport = parallel_ipc.build_broker_transport(spec)
    assert adaptive_transport.runtime_identity == adaptive_document

    service_calls = []
    from so101_demo.runtime import parallel_perception_runtime

    class Service:
        def __init__(self, _runtime, _config, **kwargs):
            service_calls.append(kwargs)

        def start(self):
            return True

        def close(self, timeout_s):
            assert timeout_s == 75.0
            return True

    class Server:
        def serve_forever(self):
            return True

        def stop_accept(self):
            return True

        def wait_handlers(self, timeout_s):
            assert timeout_s == 75.0
            return True

        def close(self):
            return True

    monkeypatch.setattr(parallel_perception_runtime, "PerceptionService", Service)
    monkeypatch.setattr(
        adaptive_transport,
        "server",
        lambda _service, *, endpoint: Server(),
    )
    adaptive_transport.serve(object(), endpoint=ipc_root / "perception.sock")
    assert service_calls[0]["queue_capacity_per_model"] == 16

    from so101_demo.runtime.parallel_ipc import IpcError
    invalid_documents = [
        {**document, "extra": True},
        {key: value for key, value in document.items() if key != "image_id"},
        {**document, "broker_generation": "1"},
        {**document, "run_mode": "dry_run"},
        {**document, "image_id": "sha256:" + "z" * 64},
        {**document, "queue_capacity_per_model": True},
        {**document, "queue_capacity_per_model": 17},
        {**adaptive_document, "connection_handler_count": True},
        {**adaptive_document, "connection_handler_count": 0},
        {**adaptive_document, "connection_handler_count": 17},
        {**adaptive_document, "yolo_executor_count": True},
        {**adaptive_document, "yolo_executor_count": 3},
        {**adaptive_document, "grounded_sam_executor_count": 2},
    ]
    for invalid in invalid_documents:
        spec.write_text(
            json.dumps(invalid, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        with pytest.raises(IpcError):
            parallel_ipc.build_broker_transport(spec)


def test_supervisor_rejects_absent_incomplete_and_batch_mismatched_manifest():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
        SupervisorError,
    )

    supervisor = ProcessSupervisor("batch-1", identity_reader=lambda _pid: None)
    with pytest.raises(SupervisorError, match="MANIFEST"):
        supervisor.load_manifest(None)
    with pytest.raises(SupervisorError, match="MANIFEST"):
        supervisor.load_manifest({"batch_id": "batch-1", "processes": [{}]})
    wrong = OwnedProcess("batch-2", "worker", 1, 1, ("worker",), 1)
    with pytest.raises(SupervisorError, match="BATCH"):
        supervisor._record_started(wrong)


def test_loaded_manifest_never_grants_signal_authority():
    from so101_demo.runtime.parallel_processes import ProcessSupervisor

    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: None,
        signal_group=lambda pgid, sig: signals.append((pgid, sig)),
    )
    supervisor.load_manifest({
        "schema_version": 1,
        "batch_id": "batch-1",
        "processes": [{
            "batch_id": "batch-1",
            "role": "worker",
            "pid": 999,
            "pgid": 999,
            "cmdline": ["unrelated"],
            "start_time": 1,
        }],
    })
    assert supervisor.processes == ()
    assert supervisor.shutdown() is True
    assert signals == []


def test_supervisor_waits_for_workers_but_keeps_broker_owned_and_healthy():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    broker = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 1)
    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 2)
    identities = {101: broker, 102: worker}
    polls = {101: None, 102: None}
    supervisor = ProcessSupervisor(
        "batch-1", identity_reader=lambda pid: identities.get(pid)
    )
    supervisor._record_started(broker, poll=lambda: polls[101])

    def worker_poll():
        polls[102] = 0
        identities.pop(102, None)
        return 0

    supervisor._record_started(worker, poll=worker_poll)
    assert supervisor.wait_for_children(deadline_monotonic_s=time.monotonic() + 1) == (0,)
    assert supervisor.processes == (broker,)


def test_supervisor_refuses_to_release_exited_leader_while_exact_pgid_members_survive():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
        SupervisorError,
    )

    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 2)
    members = {102: (103,)}
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: None,
        group_members_reader=lambda pgid: members.get(pgid, ()),
    )
    supervisor._record_started(worker, poll=lambda: 0)
    with pytest.raises(SupervisorError, match="GROUP_SURVIVORS"):
        supervisor.wait_for_children(deadline_monotonic_s=time.monotonic() + 1)
    assert supervisor.processes == (worker,)
    members[102] = ()
    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1
    ) == (0,)

    members[102] = (103,)
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: worker,
        signal_group=lambda *_args: None,
        group_members_reader=lambda pgid: members.get(pgid, ()),
    )
    supervisor._record_started(worker, poll=lambda: None)
    assert supervisor.shutdown(wait_group=lambda *_args: True) is False
    assert supervisor.processes == (worker,)


def test_shutdown_signals_exact_owned_group_after_leader_is_reaped():
    import signal
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 2)
    members = {102: (103,)}
    signals = []

    def send(pgid, value):
        signals.append((pgid, value))
        members[pgid] = ()

    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: None,
        signal_group=send,
        group_members_reader=lambda pgid: members.get(pgid, ()),
    )
    supervisor._record_started(worker, poll=lambda: 0)

    assert supervisor.shutdown(interrupt_timeout_s=0.01) is True
    assert signals == [(102, signal.SIGINT)]
    assert supervisor.processes == ()


def test_shutdown_repolls_worker_that_exits_before_identity_confirmation():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 2)
    polls = iter((None, 0))
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: None,
        group_members_reader=lambda _pgid: (),
    )
    supervisor._record_started(worker, poll=lambda: next(polls, 0))

    assert supervisor.shutdown(interrupt_timeout_s=0.01) is True
    assert supervisor.processes == ()


def test_supervisor_default_shutdown_requires_poll_and_proc_absence(tmp_path):
    from so101_demo.runtime.parallel_processes import ProcessSupervisor

    supervisor = ProcessSupervisor(
        "batch-1", manifest_path=tmp_path / "owned.json"
    )
    owned = supervisor.start(
        "worker", (sys.executable, "-c", "import time; time.sleep(30)")
    )
    assert supervisor.shutdown(term_timeout_s=1.0, kill_timeout_s=1.0) is True
    from so101_demo.parallel_batch.start_guard_probe import read_process_identity

    assert read_process_identity(owned.pid) is None
    assert supervisor.processes == ()
