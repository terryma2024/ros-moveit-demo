"""The broker's private controller registration client speaks the fixed wire format."""

import hashlib
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import uuid

from control_msgs.action import FollowJointTrajectory
import pytest
from rclpy.serialization import deserialize_message
from trajectory_msgs.msg import JointTrajectoryPoint

from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient


def socket_path():
    task_root = Path(os.environ["TMPDIR"]).parents[2]
    ipc_root = task_root / "ipc"
    ipc_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix="res-", dir=ipc_root))
    return parent / f"p{uuid.uuid4().hex[:8]}.sock"


def test_distinct_scratch_runs_never_share_private_socket_directory(
        monkeypatch, tmp_path):
    first = tmp_path / "first" / "run-0928-001" / "tmp"
    second = tmp_path / "second" / "run-0928-001" / "tmp"
    monkeypatch.setenv("TMPDIR", str(first))
    first_parent = socket_path().parent
    monkeypatch.setenv("TMPDIR", str(second))
    second_parent = socket_path().parent
    assert first_parent != second_parent
    assert first_parent.parent == second_parent.parent == tmp_path / "ipc"


def goal():
    message = FollowJointTrajectory.Goal()
    message.trajectory.joint_names = ["1"]
    point = JointTrajectoryPoint()
    point.positions = [0.125]
    message.trajectory.points = [point]
    return message


def serve(path, replies, frames):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(2)
        ready.set()
        for reply in replies:
            with listener.accept()[0] as connection:
                prefix = connection.recv(4)
                body_size = int.from_bytes(prefix, "big")
                body = bytearray()
                while len(body) < body_size:
                    chunk = connection.recv(body_size - len(body))
                    if not chunk:
                        break
                    body.extend(chunk)
                frames.append(prefix + body)
                if reply == "timeout":
                    time.sleep(0.2)
                else:
                    connection.sendall(reply)


def test_reserve_and_generation_close_use_typed_goal_and_same_capability():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    ack = b"SOGA\x01\x00\x00\x00" + (5).to_bytes(8, "big")
    worker = threading.Thread(target=serve, args=(path, [ack, ack], frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    key = bytes([0xA5]) * 32
    client = ControllerReservationClient({"arm": path}, capability=key, timeout_s=0.1)
    message = goal()
    native_uuid = "11111111-1111-1111-1111-111111111111"
    assert client.reserve((5, 0, "act", "session", "attempt"), "arm", message, native_uuid)
    client.close_generation(5)
    worker.join(1)
    assert not worker.is_alive()
    assert len(frames) == 2
    reserve = frames[0]
    assert int.from_bytes(reserve[:4], "big") == len(reserve) - 4
    assert reserve[4:10] == b"SOGR\x01\x01"
    assert reserve[10:42] == key
    assert reserve[42:50] == (5).to_bytes(8, "big")
    assert reserve[50:66] == uuid.UUID(native_uuid).bytes
    assert deserialize_message(reserve[66:], FollowJointTrajectory.Goal) == message
    assert frames[1] == (62).to_bytes(4, "big") + b"SOGR\x01\x02" + key + (5).to_bytes(8, "big") + bytes(16)


def test_each_controller_role_uses_its_own_capability():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    ack = b"SOGA\x01\x00\x00\x00" + (5).to_bytes(8, "big")
    worker = threading.Thread(target=serve, args=(path, [ack, ack], frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    arm_key = bytes([0xA5]) * 32
    gripper_key = bytes([0x5A]) * 32
    client = ControllerReservationClient(
        {"arm": path, "gripper": path},
        capability={"arm": arm_key, "gripper": gripper_key}, timeout_s=0.1,
    )
    ticket = (5, 0, "act", "session", "attempt")
    assert client.reserve(ticket, "arm", goal(), "11111111-1111-1111-1111-111111111111")
    assert client.reserve(ticket, "gripper", goal(), "22222222-2222-2222-2222-222222222222")
    worker.join(1)
    assert not worker.is_alive()
    assert [frame[10:42] for frame in frames] == [arm_key, gripper_key]


def test_read_only_native_ingress_snapshot_binds_all_three_private_roles():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    observed_ns = time.monotonic_ns()
    replies = [
        b"SOGI\x01\x00" + bytes([role, 0]) + (5).to_bytes(8, "big")
        + (7).to_bytes(8, "big") + (observed_ns - 1000).to_bytes(8, "big")
        + observed_ns.to_bytes(8, "big")
        for role in (1, 2, 3)
    ]
    worker = threading.Thread(target=serve, args=(path, replies, frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    keys = {"arm": bytes([0xA5]) * 32, "gripper": bytes([0x5A]) * 32,
            "neck": bytes([0x3C]) * 32}
    client = ControllerReservationClient(
        {role: path for role in keys}, capability=keys, timeout_s=0.1)
    ticket = (5, "token", "act", "session", "attempt")
    snapshots = [client.snapshot_generation(ticket, role) for role in keys]
    worker.join(1)
    assert not worker.is_alive()
    assert [item["role"] for item in snapshots] == list(keys)
    assert all(item["ingress_sequence"] == 7 and item["command_authority"] is False
               for item in snapshots)
    assert [frame[9] for frame in frames] == [4, 4, 4]
    assert [frame[50] for frame in frames] == [1, 2, 3]
    assert all(frame[51:] == bytes(15) for frame in frames)
    assert [frame[10:42] for frame in frames] == list(keys.values())


@pytest.mark.parametrize("corruption", ["role", "generation", "future", "stale"])
def test_native_ingress_snapshot_rejects_wrong_or_stale_reply(corruption):
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    now = time.monotonic_ns()
    role = 3 if corruption == "role" else 1
    generation = 4 if corruption == "generation" else 5
    observed = now + 1_000_000_000 if corruption == "future" else (
        now - 1_000_000_000 if corruption == "stale" else now)
    reply = (b"SOGI\x01\x00" + bytes([role, 0])
             + generation.to_bytes(8, "big") + (7).to_bytes(8, "big")
             + (observed - 1000).to_bytes(8, "big")
             + observed.to_bytes(8, "big"))
    worker = threading.Thread(target=serve, args=(path, [reply], frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    client = ControllerReservationClient(
        {"arm": path}, capability=bytes([0xA5]) * 32, timeout_s=0.1)
    with pytest.raises((ValueError, RuntimeError),
                       match="CONTROLLER_INGRESS_SNAPSHOT_INVALID"):
        client.snapshot_generation((5, "token", "act", "session", "attempt"), "arm")
    worker.join(1)
    assert not worker.is_alive()


def test_stopped_generation_arms_both_roles_before_any_goal_and_closes_both():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    ack = b"SOGA\x01\x00\x00\x00" + (5).to_bytes(8, "big")
    worker = threading.Thread(target=serve, args=(path, [ack] * 4, frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    keys = {"arm": bytes([0xA5]) * 32, "gripper": bytes([0x5A]) * 32}
    client = ControllerReservationClient(
        {"arm": path, "gripper": path}, capability=keys, timeout_s=0.1,
    )
    ticket = (5, "token", "act", "session", "attempt")
    assert client.arm_generation(ticket)
    client.close_generation(5)
    worker.join(1)
    assert not worker.is_alive()
    assert len(frames) == 4
    assert [frame[9] for frame in frames] == [3, 3, 2, 2]
    assert [frame[10:42] for frame in frames] == [keys["arm"], keys["gripper"],
                                                 keys["arm"], keys["gripper"]]
    for frame in frames:
        assert frame[:4] == (62).to_bytes(4, "big")
        assert frame[42:50] == (5).to_bytes(8, "big")
        assert frame[50:] == bytes(16)


def test_stopped_generation_arms_and_closes_all_three_controller_roles():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    ack = b"SOGA\x01\x00\x00\x00" + (5).to_bytes(8, "big")
    worker = threading.Thread(target=serve, args=(path, [ack] * 6, frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    keys = {"arm": bytes([0xA5]) * 32, "gripper": bytes([0x5A]) * 32,
            "neck": bytes([0x3C]) * 32}
    client = ControllerReservationClient(
        {role: path for role in keys}, capability=keys, timeout_s=0.1,
    )
    assert client.arm_generation((5, "token", "act", "session", "attempt"))
    client.close_generation(5)
    worker.join(1)
    assert not worker.is_alive()
    assert [frame[9] for frame in frames] == [3, 3, 3, 2, 2, 2]
    assert [frame[10:42] for frame in frames] == [
        keys[role] for role in ("arm", "gripper", "neck", "arm", "gripper", "neck")]


def test_neck_arm_refusal_still_closes_every_attempted_controller():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    ack = b"SOGA\x01\x00\x00\x00" + (5).to_bytes(8, "big")
    reject = b"SOGA\x01\x01\x00\x00" + (5).to_bytes(8, "big")
    worker = threading.Thread(target=serve, args=(path, [ack, ack, reject, ack, ack, ack], frames),
                              daemon=True)
    worker.start()
    assert ready.wait(1)
    keys = {"arm": bytes([0xA5]) * 32, "gripper": bytes([0x5A]) * 32,
            "neck": bytes([0x3C]) * 32}
    client = ControllerReservationClient(
        {role: path for role in keys}, capability=keys, timeout_s=0.1,
    )
    assert not client.arm_generation((5, "token", "act", "session", "attempt"))
    client.close_generation(5)
    worker.join(1)
    assert not worker.is_alive()
    assert [frame[9] for frame in frames] == [3, 3, 3, 2, 2, 2]


def test_partial_stopped_generation_ack_still_closes_both_attempted_roles():
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    ack = b"SOGA\x01\x00\x00\x00" + (5).to_bytes(8, "big")
    reject = b"SOGA\x01\x01\x00\x00" + (5).to_bytes(8, "big")
    worker = threading.Thread(target=serve, args=(path, [ack, reject, ack, ack], frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    keys = {"arm": bytes([0xA5]) * 32, "gripper": bytes([0x5A]) * 32}
    client = ControllerReservationClient(
        {"arm": path, "gripper": path}, capability=keys, timeout_s=0.1,
    )
    assert not client.arm_generation((5, "token", "act", "session", "attempt"))
    client.close_generation(5)
    worker.join(1)
    assert not worker.is_alive()
    assert [frame[9] for frame in frames] == [3, 3, 2, 2]


def test_role_capabilities_require_every_endpoint_and_independent_keys():
    path = socket_path()
    with pytest.raises(ValueError, match="CONTROLLER_RESERVATION_CAPABILITY_INVALID"):
        ControllerReservationClient({"arm": path, "gripper": path},
                                    capability={"arm": bytes([0xA5]) * 32}, timeout_s=0.1)
    with pytest.raises(ValueError, match="CONTROLLER_RESERVATION_CAPABILITY_INVALID"):
        ControllerReservationClient({"arm": path, "gripper": path},
                                    capability={"arm": bytes([0xA5]) * 32,
                                                "gripper": bytes([0xA5]) * 32}, timeout_s=0.1)


@pytest.mark.parametrize("reply", [b"SOGA\x01\x00\x00\x00" + (4).to_bytes(8, "big"), "timeout"])
def test_stale_ack_or_timeout_never_reports_a_reservation(reply):
    global ready
    ready = threading.Event()
    path = socket_path()
    frames = []
    worker = threading.Thread(target=serve, args=(path, [reply], frames), daemon=True)
    worker.start()
    assert ready.wait(1)
    client = ControllerReservationClient({"arm": path}, capability=bytes([0xA5]) * 32,
                                         timeout_s=0.05)
    with pytest.raises((RuntimeError, TimeoutError, OSError)):
        client.reserve((5, 0, "act", "session", "attempt"), "arm", goal(),
                       "11111111-1111-1111-1111-111111111111")
    worker.join(1)
    assert not worker.is_alive()


def test_client_rejects_symlinked_ancestor_before_connecting():
    # This case nests three levels below the socket base, so under the official gate it
    # uses the repository's short-IPC base (the same SO101_IPC_SOCKET_BASE strategy the
    # production launcher uses); locally it falls back to the scratch-derived base.
    short_base = os.environ.get("SO101_IPC_SOCKET_BASE")
    if short_base:
        parent = Path(tempfile.mkdtemp(prefix="res-", dir=short_base))
    else:
        parent = socket_path().parent
    real = parent / "real"
    nested = real / "nested"
    nested.mkdir(mode=0o700, parents=True)
    alias = parent / "alias"
    alias.symlink_to(real, target_is_directory=True)
    endpoint = nested / "goal.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(endpoint))
        os.chmod(endpoint, 0o600)
        client = ControllerReservationClient({"arm": alias / "nested" / "goal.sock"},
                                             capability=bytes([0xA5]) * 32, timeout_s=0.05)
        with pytest.raises(PermissionError, match="CONTROLLER_RESERVATION_PATH_INVALID"):
            client.reserve((5, 0, "act", "session", "attempt"), "arm", goal(),
                           "11111111-1111-1111-1111-111111111111")


def test_expired_commit_window_stops_before_connecting():
    path = socket_path()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        client = ControllerReservationClient({"arm": path},
                                             capability=bytes([0xA5]) * 32,
                                             timeout_s=0.1,
                                             deadline_port=lambda: time.monotonic() - 0.001)
        with pytest.raises(TimeoutError, match="CONTROLLER_RESERVATION_WINDOW_EXPIRED"):
            client.reserve((5, 0, "act", "session", "attempt"), "arm", goal(),
                           "11111111-1111-1111-1111-111111111111")
