"""Phase 3b: authenticated per-role identity and the real SOGB reserve path."""

import json
import os
import socket
import struct
import threading
import uuid
from pathlib import Path

import pytest
from control_msgs.action import FollowJointTrajectory

FIXTURES = (Path(__file__).resolve().parent.parent / ".." / "so101_mujoco_support"
            / "test" / "fixtures")
MANIFEST = json.loads((FIXTURES / "bound_frame_v2.json").read_text())
ROLE_CODES = {"arm": 1, "gripper": 2, "neck": 3}


def _bounded(value: str) -> bytes:
    raw = value.encode("ascii")
    assert 0 < len(raw) <= 64
    return bytes((len(raw),)) + raw


def _identity_body(role: int, generation: int, incarnation: str, boot: str) -> bytes:
    return (b"SOID" + bytes((1, 1)) + bytes((role,)) + struct.pack(">Q", generation)
            + _bounded(incarnation) + _bounded(boot))


def _reservation_reply(status: int, generation: int) -> bytes:
    """Exactly 16 bytes: SOGA + version/status + two reserved zero bytes + u64."""

    return b"SOGA" + bytes((1, status)) + b"\x00\x00" + struct.pack(">Q", generation)


class _FakeService:
    """One-shot controller service double with a configurable reservation reply."""

    def __init__(self, *, reply=None, identity=("i", "boot-1", 1)):
        self.short_dir = Path(f"/tmp/so101-debug-act-b3-p3b1-{uuid.uuid4().hex[:8]}")
        self.short_dir.mkdir(mode=0o700, exist_ok=True)
        (self.short_dir / "README-retained.txt").write_text(
            "retained task-owned IPC evidence; deletion candidate\n")
        self.path = self.short_dir / "arm.sock"
        assert len(os.fsencode(str(self.path))) <= 107
        self.received = []
        self.identity = identity
        self.reply = reply
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.socket.listen(2)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        for _ in range(2):
            try:
                connection, _ = self.socket.accept()
            except OSError:
                return
            with connection:
                header = connection.recv(4)
                if len(header) != 4:
                    continue
                size = struct.unpack(">I", header)[0]
                body = b""
                while len(body) < size:
                    chunk = connection.recv(size - len(body))
                    if not chunk:
                        break
                    body += chunk
                self.received.append((header, body))
                if body[:4] == b"SOIA":
                    incarnation, boot, generation = self.identity
                    payload = _identity_body(ROLE_CODES["arm"], generation, incarnation, boot)
                    connection.sendall(struct.pack(">I", len(payload)) + payload)
                else:
                    connection.sendall(self.reply or _reservation_reply(0, 1))

    def close(self):
        self.socket.close()
        self.thread.join(5.0)
        # the /tmp IPC directory is retained task evidence and is never deleted here


@pytest.fixture()
def service():
    server = _FakeService()
    yield server
    server.close()


def _client(path, capability=b"c" * 32):
    from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

    return ControllerReservationClient({"arm": str(path)}, capability=capability, timeout_s=1.0)


def _composition_fixture():
    from test_act_composition_lifecycle import TICKET, _composition, _sample
    from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, comp = _composition(now)
    comp.adopt_sample(ticket=TICKET, sample=_sample())
    return comp, registry, TICKET


def test_query_frame_is_exact_and_only_its_own_role_is_cached(service):
    client = _client(service.path)
    assert client.query_identity("arm") == (1, "i", "boot-1")
    header, body = service.received[0]
    assert struct.unpack(">I", header)[0] == len(body)          # exactly one prefix
    assert len(body) == 39                                      # magic+ver/op+cap+role
    assert body[:4] == b"SOIA" and body[4:6] == bytes((1, 1))
    assert body[6:38] == b"c" * 32 and body[38] == ROLE_CODES["arm"]
    with pytest.raises(Exception):
        client.identity_snapshot("gripper")


def test_authenticated_tuple_change_invalidates_the_cached_identity():
    server = _FakeService(identity=("i", "boot-1", 5))
    try:
        client = _client(server.path)
        client._cache_confirmed_identity("arm", generation=1, incarnation="i", boot="boot-1")
        with pytest.raises(RuntimeError):
            client.query_identity("arm")            # generation changed in the ACK
        with pytest.raises(Exception):
            client.identity_snapshot("arm")         # invalidated, not silently replaced
    finally:
        server.close()


def test_reserve_bound_sends_the_production_frame_and_accepts_the_ack(service):
    from test_act_composition_lifecycle import GOAL_ARM

    comp, registry, _ = _composition_fixture()
    goal = FollowJointTrajectory.Goal()
    handle = comp.claim_prepared_goal(ticket=_composition_fixture()[2], role="arm",
                                      goal_uuid=GOAL_ARM, goal=goal)
    client = _client(service.path)
    client.install_authority(comp)
    client.query_identity("arm")
    assert client.reserve_bound((1,), "arm", goal, GOAL_ARM, handle=handle) is True
    header, body = service.received[-1]
    golden = (FIXTURES / "bound_frame_v2.bin").read_bytes()
    assert struct.unpack(">I", header)[0] == len(body)          # a single prefix
    assert body[:4] == b"SOGB" and body[4] == 2 and body[5] == 1
    # same frozen schema/version/op as the golden artifact (values differ because
    # this reservation is for its own goal/permit); the golden file is unchanged
    assert body[:6] == golden[4:10]
    binding = registry.reservation_binding(handle)
    assert binding["goal_uuid"] == GOAL_ARM


def test_wrong_generation_ack_and_trailing_bytes_are_rejected():
    server = _FakeService(reply=_reservation_reply(0, 99))
    try:
        from so101_demo.adapters.act.controller_reservation_client import (
            _encode_bound_frame,
        )

        client = _client(server.path)
        golden = (FIXTURES / "bound_frame_v2.bin").read_bytes()
        with pytest.raises(RuntimeError, match="GENERATION_MISMATCH"):
            client._send_prebuilt("arm", golden, expected_generation=1)
    finally:
        server.close()
    trailing = _FakeService(reply=_reservation_reply(0, 1) + b"\x00")
    try:
        client = _client(trailing.path)
        golden = (FIXTURES / "bound_frame_v2.bin").read_bytes()
        with pytest.raises(RuntimeError, match="TRAILING|INVALID"):
            client._send_prebuilt("arm", golden, expected_generation=1)
    finally:
        trailing.close()
