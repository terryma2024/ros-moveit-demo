"""The v4 permission-only RPC: what it checks, and what it deliberately does not.

Task 5 of the macOS MPS / private IPC plan. Two facts have to hold at once:

* the server is still bounded and closed (frame cap, schema, operation allowlist, deadline,
  bounded queue), because those protect the process that owns the socket;
* the client performs no endpoint authentication at all, because the approved trust boundary
  for a single-user task-owned simulation host is the filesystem permission, not a token.

Sockets are real AF_UNIX sockets under a short per-test private directory, because Darwin's
`sun_path` cannot hold pytest's own temporary path.
"""

import os
import socket
import stat
import threading
import time
from pathlib import Path

import pytest

from so101_demo.runtime.parallel_ipc_v4 import (
    DEFAULT_QUEUE_CAPACITY,
    EXPIRED,
    FORBIDDEN_FIELDS,
    INTERNAL,
    MALFORMED,
    OK,
    OVERSIZED,
    QUEUE_FULL,
    UNKNOWN_OPERATION,
    V4_OPERATIONS,
    V4PermissionOnlyClient,
    V4PermissionOnlyServer,
    V4Request,
    V4Response,
    V4IpcError,
    V4_REQUEST_FIELDS,
    V4_RESPONSE_FIELDS,
    decode_v4_frame,
    encode_v4_frame,
)
from so101_demo.runtime.unix_address import (
    DIRECTORY_MODE,
    PRIVATE_TMP,
    DarwinPrivatePathUnixAddress,
    require_root_owned_sticky_directory,
)

@pytest.fixture
def private_root():
    """A short private base under the canonical sticky parent, removed on teardown."""

    import secrets

    require_root_owned_sticky_directory(PRIVATE_TMP)
    base = PRIVATE_TMP / f"so101-ipc-v4-{os.getuid()}-{secrets.token_hex(4)}"
    os.mkdir(base, DIRECTORY_MODE)
    os.chmod(base, DIRECTORY_MODE)
    yield base
    import shutil

    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def campaign(private_root):
    """A strategy, a campaign root and its cleanup, all inside the short private base."""

    address = DarwinPrivatePathUnixAddress(base_path=private_root)
    root = address.create_campaign_root()
    yield address, root
    address.cleanup_campaign(root)


def _echo_handler(request: V4Request):
    return {"echo": dict(request.payload), "operation": request.operation}


def _start_server(campaign, handler=_echo_handler, **kwargs):
    address, root = campaign
    server = V4PermissionOnlyServer(
        endpoint_path=address.endpoint_path(root, "broker"), handler=handler, **kwargs)
    endpoint = server.start(address=address, root=root, role="broker",
                            owner_pid=os.getpid(), owner_birth_identity=1)
    return address, root, server, endpoint


def _stop(address, root, server):
    """Stop the server, then run the exact cleanup and return its receipt."""

    server.stop()
    return address.cleanup_campaign(root)


# --------------------------------------------------------------------------------------
# the envelope
# --------------------------------------------------------------------------------------


def test_request_and_response_carry_only_the_four_and_five_closed_fields():
    """The retired authentication fields are gone from both directions of the protocol."""

    assert set(V4_REQUEST_FIELDS) == {"request_id", "operation", "deadline_monotonic_ns",
                                      "payload"}
    assert set(V4_RESPONSE_FIELDS) == {"request_id", "status", "error", "output_descriptor",
                                       "timing"}

    request = V4Request(request_id="r-1", operation="broker.infer",
                        deadline_monotonic_ns=time.monotonic_ns() + 10**9,
                        payload={"input_descriptor": {"relative_path": "frame.npy"}})
    document = request.to_document()
    assert set(document) == set(V4_REQUEST_FIELDS)

    response = V4Response(request_id="r-1", status=OK,
                          output_descriptor={"shape": [1, 3, 640, 640]}, error=None,
                          timing={"started_monotonic_ns": 1, "completed_monotonic_ns": 2})
    assert set(response.to_document()) == set(V4_RESPONSE_FIELDS)


def test_serialized_frames_never_contain_token_generation_or_lease():
    """The forbidden vocabulary is absent from the bytes on the wire, not just from the API."""

    request = V4Request(request_id="r-2", operation="coordinator.consume_result",
                        deadline_monotonic_ns=time.monotonic_ns() + 10**9,
                        payload={"result": {"status": "ok"}})
    frame = encode_v4_frame(request.to_document())
    # Only the JSON body is inspected: the 4-byte big-endian length prefix is arbitrary binary
    # and could contain any byte sequence at all, so scanning it would prove nothing.
    body = frame[4:].decode("utf-8")
    for forbidden in ("token", "generation", "lease", "receipt", "inode"):
        assert forbidden not in body, forbidden

    assert decode_v4_frame(frame) == request.to_document()


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_FIELDS))
def test_a_request_that_carries_a_retired_field_is_refused(forbidden):
    """Smuggling a retired field back into the envelope is a protocol error."""

    document = V4Request(request_id="r-3", operation="broker.infer",
                         deadline_monotonic_ns=time.monotonic_ns() + 10**9).to_document()
    document[forbidden] = "something"
    with pytest.raises(V4IpcError, match="INVALID_REQUEST"):
        V4Request.from_document(document)


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_FIELDS))
def test_a_response_that_carries_a_retired_field_is_refused(forbidden):
    document = V4Response(request_id="r-4", status=OK, output_descriptor={}, error=None,
                          timing={}).to_document()
    document[forbidden] = "something"
    with pytest.raises(V4IpcError, match="INVALID_REQUEST"):
        V4Response.from_document(document)


def test_response_requires_exactly_one_of_descriptor_and_error():
    """A response cannot be both a success and a failure, and cannot be neither."""

    both = {"request_id": "r", "status": OK, "output_descriptor": {}, "error": {"code": "X"},
            "timing": {}}
    with pytest.raises(V4IpcError, match="INVALID_REQUEST"):
        V4Response.from_document(both)
    neither = {"request_id": "r", "status": OK, "output_descriptor": None, "error": None,
               "timing": {}}
    with pytest.raises(V4IpcError, match="INVALID_REQUEST"):
        V4Response.from_document(neither)


# --------------------------------------------------------------------------------------
# server-side bounded validation
# --------------------------------------------------------------------------------------


def test_unknown_operation_is_refused_against_the_allowlist():
    """Only the closed allowlist is dispatchable."""

    document = V4Request(request_id="r-5", operation="broker.infer",
                         deadline_monotonic_ns=time.monotonic_ns() + 10**9).to_document()
    document["operation"] = "broker.do_something_else"
    with pytest.raises(V4IpcError, match=UNKNOWN_OPERATION):
        V4Request.from_document(document)
    assert "broker.infer" in V4_OPERATIONS
    assert "broker.do_something_else" not in V4_OPERATIONS


def test_an_expired_deadline_is_refused():
    """A request whose deadline already passed is refused, not executed late."""

    document = V4Request(request_id="r-6", operation="broker.infer",
                         deadline_monotonic_ns=1).to_document()
    with pytest.raises(V4IpcError, match=EXPIRED):
        V4Request.from_document(document)


def test_oversized_and_truncated_frames_are_refused():
    """The frame cap is enforced on the declared length and on the carried bytes."""

    with pytest.raises(V4IpcError, match=OVERSIZED):
        encode_v4_frame({"payload": "x" * 100}, max_frame_bytes=32)
    with pytest.raises(V4IpcError, match=OVERSIZED):
        decode_v4_frame(b"\x00\x00\x02\x00{}", max_frame_bytes=32)
    with pytest.raises(V4IpcError, match=MALFORMED):
        decode_v4_frame(b"\x00\x00")
    with pytest.raises(V4IpcError, match=MALFORMED):
        decode_v4_frame(b"\x00\x00\x00\x05{}")
    with pytest.raises(V4IpcError, match=MALFORMED):
        decode_v4_frame(b"\x00\x00\x00\x04nope")


# --------------------------------------------------------------------------------------
# the server never touches the filesystem to authenticate the client
# --------------------------------------------------------------------------------------


def test_bind_creates_a_mode_0600_socket_and_registers_it(campaign):
    """The endpoint is a real socket with the private mode, registered for exact cleanup."""

    address, root, server, endpoint = _start_server(campaign)
    try:
        metadata = os.lstat(endpoint.path)
        assert stat.S_ISSOCK(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        assert endpoint.role == "broker"
    finally:
        _stop(address, root, server)


def test_client_connects_without_any_endpoint_authentication(campaign, monkeypatch):
    """No `stat`, inode, receipt or peer-credential call is made on the client hot path."""

    address, root, server, endpoint = _start_server(campaign)
    forbidden_calls: list[str] = []

    import so101_demo.runtime.parallel_ipc_v4 as module

    real_os_stat = os.stat

    def guarded_stat(path, *args, **kwargs):
        if str(path) == str(endpoint.path):
            forbidden_calls.append("stat")
        return real_os_stat(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "stat", guarded_stat)
    monkeypatch.setattr(module.os, "lstat", lambda path, *a, **k: (
        forbidden_calls.append("lstat"), real_os_stat(path, *a, **k))[1])
    try:
        client = V4PermissionOnlyClient(endpoint_path=endpoint.path)
        response = client.call("broker.infer", {"n": 1})
        assert response.ok is True
        assert response.output_descriptor is not None
        assert response.output_descriptor["echo"] == {"n": 1}
        assert forbidden_calls == [], forbidden_calls
    finally:
        _stop(address, root, server)


def test_snapshot_file_access_is_not_part_of_the_endpoint_auth_path(campaign):
    """The payload may name a data file; that is the data plane, not endpoint authentication."""

    address, root, server, endpoint = _start_server(campaign)
    try:
        snapshot = root.campaign_path / "input.npy"
        snapshot.write_bytes(b"\x00" * 32)
        client = V4PermissionOnlyClient(endpoint_path=endpoint.path)
        response = client.call("broker.infer",
                               {"input_descriptor": {"relative_path": "input.npy"}})
        assert response.ok is True
        # The server echoes the descriptor; it did not need to authenticate anything to do so.
        assert response.output_descriptor["echo"]["input_descriptor"]["relative_path"] == \
            "input.npy"
    finally:
        _stop(address, root, server)


# --------------------------------------------------------------------------------------
# round trips
# --------------------------------------------------------------------------------------


def test_two_concurrent_clients_complete_a_round_trip(campaign):
    """Two clients on the same endpoint both get their own answer, with matching ids."""

    address, root, server, endpoint = _start_server(campaign)
    results: dict[str, V4Response] = {}
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            client = V4PermissionOnlyClient(endpoint_path=endpoint.path)
            results[name] = client.call("broker.infer", {"who": name},
                                        request_id=f"req-{name}")
        except BaseException as error:  # noqa: BLE001 - recorded and re-raised below
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("w1", "w2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    try:
        assert not errors, errors
        assert set(results) == {"w1", "w2"}
        assert results["w1"].request_id == "req-w1"
        assert results["w2"].request_id == "req-w2"
        assert results["w1"].output_descriptor["echo"] == {"who": "w1"}
        assert results["w2"].output_descriptor["echo"] == {"who": "w2"}
    finally:
        _stop(address, root, server)


def test_negative_protocol_paths_return_stable_errors(campaign):
    """Malformed, oversized, unknown-op and expired frames each get their own stable code."""

    address, root, server, endpoint = _start_server(campaign)
    client = V4PermissionOnlyClient(endpoint_path=endpoint.path)
    try:
        # Malformed: a valid length prefix over bytes that are not JSON.
        response = client.send_raw(b"\x00\x00\x00\x04nope")
        assert response is not None and response.status == MALFORMED

        # Oversized: the declared size exceeds the server's cap.
        response = client.send_raw(b"\x00\xff\xff\xff" + b"{}")
        assert response is not None and response.status == OVERSIZED

        # Unknown operation: a well-formed request for something not on the allowlist.
        document = V4Request(request_id="r-x", operation="broker.infer",
                             deadline_monotonic_ns=time.monotonic_ns() + 10**9).to_document()
        document["operation"] = "broker.not_allowed"
        response = client.send_raw(encode_v4_frame(document))
        assert response is not None and response.status == UNKNOWN_OPERATION

        # Expired deadline.
        expired = dict(document)
        expired["operation"] = "broker.infer"
        expired["deadline_monotonic_ns"] = 1
        response = client.send_raw(encode_v4_frame(expired))
        assert response is not None and response.status == EXPIRED

        assert set(server.rejections) >= {MALFORMED, OVERSIZED, UNKNOWN_OPERATION, EXPIRED}
    finally:
        _stop(address, root, server)


def test_a_full_bounded_queue_answers_queue_full_instead_of_dropping(campaign, monkeypatch):
    """The QUEUE_FULL branch is exercised deterministically, not raced.

    The accept loop drains queued connections as fast as they arrive, so "the queue happens to be
    full at this instant" is a race window, and a test that fires a burst at it flakes. Instead the
    queue is made genuinely full for the duration of one connection, which is exactly the state
    the branch exists for, and the server must answer QUEUE_FULL rather than drop the client.
    """

    import queue as queue_module

    address, root = campaign
    server = V4PermissionOnlyServer(endpoint_path=address.endpoint_path(root, "broker"),
                                    handler=_echo_handler, queue_capacity=1)
    endpoint = server.start(address=address, root=root, role="broker",
                            owner_pid=os.getpid(), owner_birth_identity=1)
    try:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(10.0)
        connection.connect(str(endpoint.path))
        connection.sendall(encode_v4_frame(
            V4Request(request_id="r-full", operation="broker.infer",
                      deadline_monotonic_ns=time.monotonic_ns() + 10**9).to_document()))

        real_put = server._queue.put_nowait

        def always_full(item):
            raise queue_module.Full

        monkeypatch.setattr(server._queue, "put_nowait", always_full)
        refused_before = server.refused_connects
        # Each extra connection is a fresh stimulus for the accept loop, and the budget is generous:
        # a loaded machine can delay that loop past a fixed five-second wait, which is how this test
        # failed once in a full-suite run while its sibling failed in the other direction. The
        # assertion is unchanged - the accept loop must still refuse a connection it cannot queue.
        deadline = time.monotonic() + 20
        extra: list[socket.socket] = []
        last_poke = 0.0
        try:
            while server.refused_connects == refused_before and time.monotonic() < deadline:
                if time.monotonic() - last_poke > 2:
                    poke = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    poke.settimeout(10.0)
                    try:
                        poke.connect(str(endpoint.path))
                        extra.append(poke)
                    except OSError:
                        poke.close()
                    last_poke = time.monotonic()
                time.sleep(0.05)
        finally:
            monkeypatch.setattr(server._queue, "put_nowait", real_put)

        assert server.refused_connects >= refused_before + 1, (
            "the accept loop must refuse a connection it cannot queue")
        assert QUEUE_FULL in server.rejections
        for sock in [connection, *extra]:
            try:
                sock.close()
            except OSError:
                pass
    finally:
        _stop(address, root, server)



def test_a_raising_handler_becomes_a_stable_internal_error(campaign):
    """A handler bug must not crash the server or leak a malformed frame."""

    def exploding(_request: V4Request):
        raise RuntimeError("handler exploded")

    address, root, server, endpoint = _start_server(campaign, handler=exploding)
    try:
        client = V4PermissionOnlyClient(endpoint_path=endpoint.path)
        response = client.call("broker.infer", {})
        assert response.ok is False
        assert response.status == INTERNAL
        assert response.error is not None and "handler exploded" in response.error["detail"]
    finally:
        _stop(address, root, server)


# --------------------------------------------------------------------------------------
# restart and cleanup
# --------------------------------------------------------------------------------------


def test_restart_uses_a_new_path_and_the_old_path_is_unusable(campaign):
    """Cleanup unlinks exactly the old socket; a restart binds a different path."""

    address, root, server, endpoint = _start_server(campaign)
    old_path = endpoint.path
    client = V4PermissionOnlyClient(endpoint_path=old_path)
    assert client.call("broker.infer", {"n": 1}).ok is True

    receipt = _stop(address, root, server)
    assert receipt.complete is True
    assert not old_path.exists(), "the old endpoint must be gone"
    assert not root.campaign_path.exists()

    # A restart is a new campaign directory and a new socket; the old path cannot be used.
    second_root = address.create_campaign_root()
    assert second_root.campaign_path != root.campaign_path
    server2 = V4PermissionOnlyServer(
        endpoint_path=address.endpoint_path(second_root, "broker"), handler=_echo_handler)
    endpoint2 = server2.start(address=address, root=second_root, role="broker",
                             owner_pid=os.getpid(), owner_birth_identity=1)
    try:
        assert endpoint2.path != old_path
        assert V4PermissionOnlyClient(endpoint_path=endpoint2.path).call(
            "broker.infer", {"n": 2}).ok is True
        with pytest.raises(V4IpcError, match=MALFORMED):
            V4PermissionOnlyClient(endpoint_path=old_path).call("broker.infer", {})
    finally:
        _stop(address, second_root, server2)


def test_cleanup_leaves_no_socket_behind_after_a_round_trip(campaign):
    """The precise-cleanup readback: no socket, no campaign directory, no leftover."""

    address, root, server, endpoint = _start_server(campaign)
    client = V4PermissionOnlyClient(endpoint_path=endpoint.path)
    for index in range(3):
        assert client.call("broker.infer", {"i": index}).ok is True
    receipt = _stop(address, root, server)
    assert receipt.complete is True
    assert [item.outcome for item in receipt.endpoints] == ["CLEANED"]
    assert not endpoint.path.exists()
    assert not root.campaign_path.exists()
    assert address.registry == ()
