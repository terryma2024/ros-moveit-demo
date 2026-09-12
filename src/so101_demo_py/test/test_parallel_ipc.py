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


def test_broker_transport_authenticates_with_coordinator_before_real_socket_mutation(
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
        BrokerTransport,
        UnixRpcClient,
        WorkerTokenAuthority,
    )
    from so101_demo.runtime.parallel_perception_runtime import Snapshot

    worker_authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=7)
    worker_authority.install_token("worker-01", 2, bytes.fromhex("ab" * 32))
    worker_authority.bind_lease("worker-01", 2, request()["lease"])
    authority_calls = []

    def coordinator_authority(operation, payload):
        authority_calls.append((operation, payload))
        if operation == "authenticate_broker_message":
            worker_authority.authenticate(payload["message"])
        return True

    transport = BrokerTransport(
        ipc_root=tmp_path / "ipc",
        config=SimpleNamespace(broker_max_frame_bytes=8 * 1024 * 1024),
        generation=1,
        authority_call=coordinator_authority,
        deadline_s=1.0,
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
            return response

        def poll_response(self, _request):
            return response

    service = Service()
    socket_path = tmp_path / "ipc/perception.sock"
    server = transport.server(service, endpoint=socket_path)
    thread = threading.Thread(target=server.serve_once)
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
    thread.join(timeout=2.0)
    server.close()

    assert reply["payload"]["outcome"] == "QUALIFIED"
    assert reply["payload"]["candidate"] == {"candidate": "real-service-result"}
    assert [call[0] for call in authority_calls] == [
        "authenticate_broker_message",
        "authorize_inference",
    ]
    assert service.mutations == [(inference, snapshot)]


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


def test_client_rejects_wrong_response_schema_and_union(tmp_path):
    from so101_demo.runtime.parallel_ipc import IpcError, UnixRpcClient, encode_frame

    root = Path(os.environ["TMPDIR"]).parent / "ipc-response"
    root.mkdir(mode=0o700)
    path = root / "s"
    replies = [
        {"schema_version": 2, "kind": "response", "request_id": "request-1", "idempotency_key": "same-operation-1", "ok": True, "payload": {}, "error": None},
        {"schema_version": 1, "kind": "wrong", "request_id": "request-1", "idempotency_key": "same-operation-1", "ok": True, "payload": {}, "error": None},
        {"schema_version": 1, "kind": "response", "request_id": "request-1", "idempotency_key": "same-operation-1", "ok": True, "payload": {}, "error": "also-error"},
    ]
    for reply in replies:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(1)
        def serve():
            connection, _ = listener.accept()
            with connection:
                connection.recv(65536)
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


def test_supervisor_default_shutdown_requires_poll_and_proc_absence(tmp_path):
    from so101_demo.runtime.parallel_processes import ProcessSupervisor

    supervisor = ProcessSupervisor(
        "batch-1", manifest_path=tmp_path / "owned.json"
    )
    owned = supervisor.start(
        "worker", (sys.executable, "-c", "import time; time.sleep(30)")
    )
    assert supervisor.shutdown(term_timeout_s=1.0, kill_timeout_s=1.0) is True
    assert not Path(f"/proc/{owned.pid}").exists()
    assert supervisor.processes == ()
