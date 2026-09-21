"""Fixed Web control over actual Unix transport and the upstream durable owner."""

import hashlib
import importlib
import json
import os
import socket
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from test_parallel_batch_coordinator import make  # noqa: F401 - real journal fixture


@pytest.fixture
def endpoint(make):
    @contextmanager
    def open_endpoint():
        coordinator, _, _, journal, request = make(workers=2, k=2)
        root = request.evidence_root / "control"
        root.mkdir(mode=0o700)
        token = "9a" * 32
        binding = SimpleNamespace(
            campaign_id="campaign-a", batch_id="batch-a",
            batch_root=request.evidence_root.resolve(),
            control_socket=(root / "control.sock").resolve(),
            coordinator_epoch=journal.coordinator_epoch, control_token=token,
            control_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        )
        # The real test body enters this boundary after durable owner setup.
        module = importlib.import_module("so101_demo.parallel_batch.web_control")
        server = module.FixedCoordinatorControlServer(
            coordinator=coordinator, campaign_id=binding.campaign_id,
            control_token=token, path=binding.control_socket,
        )
        server.start()
        try:
            yield coordinator, journal, binding
        finally:
            server.close()

    return open_endpoint


def _request(binding, **changes):
    unsigned = {
        "schema_version": 1, "command_id": "cancel-1",
        "campaign_id": "campaign-a", "batch_id": "batch-a",
        "coordinator_epoch": binding.coordinator_epoch, "operation": "CANCEL_BATCH",
    }
    unsigned.update(changes)
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return {
        **unsigned, "request_sha256": hashlib.sha256(canonical).hexdigest(),
        "control_token": binding.control_token,
    }


def _exchange(binding, document=None, *, frame=None):
    from so101_demo.parallel_batch.web_control import _bind_target

    if frame is None:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        frame = len(payload).to_bytes(4, "big") + payload
    parent_fd = os.open(
        binding.control_socket.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(_bind_target(binding.control_socket, parent_fd))
            connection.sendall(frame)
            connection.shutdown(socket.SHUT_WR)
            reply = bytearray()
            try:
                while part := connection.recv(65536):
                    reply.extend(part)
            except ConnectionResetError:
                pass
            return bytes(reply)
    finally:
        os.close(parent_fd)


class _WireClient:
    """Independent protocol consumer; upstream tests do not depend on Teleop."""

    def status(self, *, command_id, binding):
        return self._call(binding, command_id, "STATUS")

    def cancel(self, *, command_id, binding):
        return self._call(binding, command_id, "CANCEL_BATCH")

    def _call(self, binding, command_id, operation):
        frame = _exchange(binding, _request(
            binding, command_id=command_id, operation=operation,
        ))
        assert len(frame) >= 4
        assert int.from_bytes(frame[:4], "big") == len(frame) - 4
        document = json.loads(frame[4:])
        assert set(document) == {
            "schema_version", "command_id", "campaign_id", "batch_id",
            "coordinator_epoch", "operation", "request_sha256", "state",
            "batch_terminal", "batch_cleanup_complete", "owned_descendants_gone",
            "assigned_ros_domains_clear", "cleanup_receipt_sha256",
        }
        assert document["command_id"] == command_id
        assert document["operation"] == operation
        return SimpleNamespace(**document)


def test_authenticated_cancel_durably_fences_all_workers_without_cleanup_claim(endpoint):
    with endpoint() as (coordinator, journal, binding):
        client = _WireClient()
        before = client.status(command_id="status-1", binding=binding)
        assert before.state == "RUNNING" and before.batch_cleanup_complete is False
        first = client.cancel(command_id="cancel-1", binding=binding)
        again = client.cancel(command_id="cancel-1", binding=binding)
        assert first == again
        assert first.state == "STOPPING"
        assert first.batch_terminal is False and first.batch_cleanup_complete is False
        assert first.owned_descendants_gone is False
        assert first.assigned_ros_domains_clear is False
        assert first.cleanup_receipt_sha256 is None
        snapshot = coordinator.snapshot()
        assert snapshot.terminal_reason == "WEB_CANCEL_REQUESTED"
        assert all(worker.stop_requested and not worker.action_allowed
                   and not worker.reset_allowed and not worker.inference_allowed
                   for worker in snapshot.workers.values())
        assert coordinator.grant_lease("w1", generation=1) is None
        assert coordinator.grant_lease("w2", generation=1) is None
        stops = [event for event in journal.replay().events if event.type == "BATCH_STOPPING"]
        assert len(stops) == 1
        assert len(snapshot.points) == 2
        assert all(point.attempts == 0 for point in snapshot.points.values())


@pytest.mark.parametrize("changes", [
    {"schema_version": True}, {"schema_version": 1.0}, {"schema_version": 2},
    {"campaign_id": "campaign-b"}, {"batch_id": "batch-b"},
    {"coordinator_epoch": True}, {"coordinator_epoch": 2},
    {"operation": "CANCEL_WORKER"}, {"operation": ["CANCEL_BATCH"]},
    {"operation": {"requested": "CANCEL_BATCH"}},
    {"command_id": ""}, {"extra": "forbidden"},
])
def test_invalid_control_identity_never_mutates_the_upstream_owner(endpoint, changes):
    with endpoint() as (coordinator, journal, binding):
        before = journal.replay().events
        assert _exchange(binding, _request(binding, **changes)) == b""
        assert journal.replay().events == before
        assert coordinator.snapshot().terminal_reason is None
        assert coordinator.grant_lease("w1", generation=1) is not None
        # A rejected connection must not poison the authenticated accept loop.
        assert _WireClient().status(command_id="status-2", binding=binding).state == "RUNNING"


@pytest.mark.parametrize("fault", ["token", "hash", "partial", "oversized"])
def test_invalid_token_hash_or_frame_has_no_cancellation_side_effect(endpoint, fault):
    with endpoint() as (coordinator, journal, binding):
        before = journal.replay().events
        document = _request(binding)
        if fault == "token":
            document["control_token"] = "ff" * 32
        elif fault == "hash":
            document["request_sha256"] = "0" * 64
        frame = None
        if fault == "partial":
            frame = (100).to_bytes(4, "big") + b"{}"
        elif fault == "oversized":
            frame = (65537).to_bytes(4, "big")
        assert _exchange(binding, document, frame=frame) == b""
        assert journal.replay().events == before
        assert coordinator.snapshot().terminal_reason is None


def test_command_identity_collision_is_not_reinterpreted_as_cancel(endpoint):
    with endpoint() as (coordinator, _, binding):
        assert _WireClient().status(command_id="collision-1", binding=binding).state == "RUNNING"
        assert _exchange(binding, _request(binding, command_id="collision-1")) == b""
        assert coordinator.snapshot().terminal_reason is None


def test_endpoint_close_is_idempotent_and_preserves_replaced_paths(make, monkeypatch):
    coordinator, _, _, _, request = make()
    root = request.evidence_root / "control"
    root.mkdir(mode=0o700)
    path = root / "control.sock"
    module = importlib.import_module("so101_demo.parallel_batch.web_control")
    server = module.FixedCoordinatorControlServer(
        coordinator=coordinator, campaign_id="campaign-a",
        control_token="9a" * 32, path=path.resolve(),
    )
    server.start()
    path.rename(root / "retired.sock")
    outside = request.evidence_root.parent / "outside"
    outside.mkdir()
    alias = outside / "control.sock"
    os.link(root / "retired.sock", alias)
    path.write_bytes(b"foreign replacement must survive owned shutdown")
    server.close()
    with monkeypatch.context() as context:
        context.chdir(outside)
        server.close()
    assert alias.exists()
    assert path.read_bytes() == b"foreign replacement must survive owned shutdown"


def test_existing_control_path_is_not_overwritten_or_deleted(make):
    coordinator, _, _, _, request = make()
    root = request.evidence_root / "control"
    root.mkdir(mode=0o700)
    path = root / "control.sock"
    path.write_bytes(b"existing foreign file")
    module = importlib.import_module("so101_demo.parallel_batch.web_control")
    with pytest.raises(OSError):
        module.FixedCoordinatorControlServer(
            coordinator=coordinator, campaign_id="campaign-a",
            control_token="9a" * 32, path=path.resolve(),
        )
    assert path.read_bytes() == b"existing foreign file"


def test_post_bind_permission_failure_releases_only_the_owned_socket(make, monkeypatch):
    coordinator, _, _, _, request = make()
    root = request.evidence_root / "control"
    root.mkdir(mode=0o700)
    path = root / "control.sock"
    module = importlib.import_module("so101_demo.parallel_batch.web_control")

    def denied(*_args, **_kwargs):
        raise PermissionError("injected chmod failure after actual bind")

    with monkeypatch.context() as context:
        context.setattr(module.os, "chmod", denied)
        with pytest.raises(PermissionError):
            module.FixedCoordinatorControlServer(
                coordinator=coordinator, campaign_id="campaign-a",
                control_token="9a" * 32, path=path.resolve(),
            )
    assert not path.exists()


def test_non_private_control_directory_never_gets_a_socket(make):
    coordinator, _, _, _, request = make()
    root = request.evidence_root / "control"
    root.mkdir(mode=0o755)
    path = root / "control.sock"
    module = importlib.import_module("so101_demo.parallel_batch.web_control")
    with pytest.raises(module.WebControlError, match="CONTROL_SOCKET_DIRECTORY_MODE"):
        module.FixedCoordinatorControlServer(
            coordinator=coordinator, campaign_id="campaign-a",
            control_token="9a" * 32, path=path.resolve(),
        )
    assert not path.exists()


def test_adaptive_generation_does_not_accept_a_fixed_web_control_endpoint(make):
    coordinator, _, _, _, request = make(adaptive=True)
    root = request.evidence_root / "control"
    root.mkdir(mode=0o700)
    module = importlib.import_module("so101_demo.parallel_batch.web_control")
    server = None
    try:
        with pytest.raises(module.WebControlError, match="FIXED_COORDINATOR_REQUEST_REQUIRED"):
            server = module.FixedCoordinatorControlServer(
                coordinator=coordinator, campaign_id="campaign-a",
                control_token="9a" * 32, path=(root / "control.sock").resolve(),
            )
    finally:
        if server is not None:
            server.close()
