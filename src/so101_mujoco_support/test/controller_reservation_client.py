#!/usr/bin/env python3
"""Cross-process wire client for the controller reservation test only."""

import os
from pathlib import Path
import socket
import sys
import time
import uuid

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import deserialize_message
from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.command_broker import CommandBroker
from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient


capability = bytes.fromhex(sys.stdin.readline().strip())
if len(sys.argv) == 3:
    gripper_capability = bytes.fromhex(sys.stdin.readline().strip())
    wire_client = ControllerReservationClient(
        {"arm": sys.argv[1], "gripper": sys.argv[2]},
        capability={"arm": capability, "gripper": gripper_capability}, timeout_s=0.5,
    )
else:
    wire_client = ControllerReservationClient(
        {"arm": sys.argv[1]}, capability=capability, timeout_s=1.0,
    )
broker_state = None
held_other_connections = []


class PreparedDriver:
    def stopped(self):
        return True

    def prepare_goal(self, kind, goal):
        native_uuid = b"\x11" if kind == "arm" else b"\x22"
        return f"{kind}-goal", str(uuid.UUID(bytes=native_uuid * 16))

    def send_prepared(self, goal_id, kind, goal, goal_uuid):
        return goal_id

    def discard_prepared(self, goal_id):
        pass

    def stop_all(self, reason):
        pass


def start_ticks() -> int:
    return int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])


def frame_for(mode: str) -> bytes:
    key = capability
    if mode.startswith("bootstrap_") or mode.startswith("scoped_"):
        generation = 6 if "other_generation" in mode else 5
        if mode.startswith("bootstrap_"):
            body = b"SOPQ\x01\x02" + key + generation.to_bytes(8, "big") + bytes(16)
        else:
            inc, boot = b"startup-inc", b"startup-boot"
            if mode == "scoped_stale_identity":
                inc = b"old-inc"
            if mode == "scoped_wrong_cap":
                key = bytes([key[0] ^ 1]) + key[1:]
            role = 1 if mode == "scoped_bad_role" else 3
            body = (b"SOPC\x01\x01" + key + generation.to_bytes(8, "big") + bytes([role, len(inc)])
                    + inc + bytes([len(boot)]) + boot)
        return len(body).to_bytes(4, "big") + body
    if mode.startswith("prearm_") or mode.startswith("diagnostic_arm"):
        if mode == "prearm_wrong_cap":
            key = bytes([key[0] ^ 1]) + key[1:]
        operation = 5 if mode.startswith("prearm_") else 6
        generation = 6 if mode == "diagnostic_arm_next" else 5
        body = b"SOGR\x01" + bytes([operation]) + key + generation.to_bytes(8, "big") + bytes(16)
        if mode == "prearm_bad_reserved":
            body = body[:-1] + b"\x01"
        return len(body).to_bytes(4, "big") + body
    if mode in ("identity_neck", "identity_wrong_role"):
        role = 3 if mode == "identity_neck" else 1
        body = b"SOIA\x01\x01" + key + bytes([role])
        return len(body).to_bytes(4, "big") + body
    if mode in ("ingress_snapshot", "ingress_wrong_role", "ingress_stale_generation", "ingress_neck"):
        generation = 4 if mode == "ingress_stale_generation" else 5
        role = 3 if mode in ("ingress_wrong_role", "ingress_neck") else 1
        body = (b"SOGR\x01\x04" + key + generation.to_bytes(8, "big")
                + bytes([role]) + bytes(15))
        return len(body).to_bytes(4, "big") + body
    if mode in ("arm_generation", "arm_next"):
        generation = 6 if mode == "arm_next" else 5
        body = b"SOGR\x01\x03" + key + generation.to_bytes(8, "big") + bytes(16)
        return len(body).to_bytes(4, "big") + body
    if mode in ("close_generation", "close_stale", "close_zero", "close_wrong_capability", "close_drop_reply"):
        if mode == "close_wrong_capability":
            key = bytes([key[0] ^ 1]) + key[1:]
        generation = 0 if mode == "close_zero" else 5
        body = b"SOGR\x01\x02" + key + generation.to_bytes(8, "big") + bytes(16)
        return len(body).to_bytes(4, "big") + body
    payload = bytes.fromhex(
        (Path(__file__).parent / "fixtures/follow_joint_trajectory_goal.cdr.hex")
        .read_text()
        .strip()
    )
    if mode == "wrong_capability":
        key = bytes([key[0] ^ 1]) + key[1:]
    generation = 4 if mode == "stale_generation" else 5
    body = (
        b"SOGR\x01\x01"
        + key
        + generation.to_bytes(8, "big")
        + b"\x11" * 16
        + payload
    )
    if mode == "oversized":
        return (1_048_641).to_bytes(4, "big") + body
    if mode == "truncated":
        return len(body).to_bytes(4, "big") + body[:8]
    return len(body).to_bytes(4, "big") + body


def request(mode: str) -> str:
    global broker_state
    report_sent = mode.startswith("sent_")
    if report_sent:
        mode = mode[5:]
    if mode == "hold_other":
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(sys.argv[2])
        conn.sendall(b'\0')
        held_other_connections.append(conn)
        return "PARTIAL"
    if mode == "ingress_snapshot":
        snapshot = wire_client.snapshot_generation(
            (5, 0, "act", "session", "attempt"), "arm")
        return "SNAPSHOT " + " ".join(map(str, (
            snapshot["owner_generation"], 1, snapshot["ingress_sequence"],
            snapshot["last_ingress_monotonic_ns"],
            snapshot["observed_monotonic_ns"],
        )))
    if mode == "broker_transaction":
        payload = bytes.fromhex(
            (Path(__file__).parent / "fixtures/follow_joint_trajectory_goal.cdr.hex")
            .read_text().strip()
        )
        typed_goal = deserialize_message(payload, FollowJointTrajectory.Goal)
        ownership = Ownership()
        broker = CommandBroker(
            PreparedDriver(), ownership=ownership, simulation_session_id="session",
            reservation_port=wire_client,
        )
        scope = dict(protocol_version=1, request_id="r", owner="act",
                     session_id="session", attempt_id="attempt", lease_token="")
        response = broker.handle(dict(scope, operation="acquire"), "test-client")
        if not response["accepted"]:
            return "REJECT"
        token = response["lease_token"]
        ticket = ownership.ticket(token, "act", "session", "attempt")
        broker.dispatch(ticket, "arm", typed_goal)
        broker.dispatch(ticket, "gripper", typed_goal)
        broker_state = broker, dict(scope, lease_token=token)
        return "ACK"
    if mode == "broker_release":
        if broker_state is None:
            return "REJECT"
        broker, scope = broker_state
        response = broker.handle(dict(scope, operation="release"), "test-client")
        return "ACK" if response["accepted"] else "REJECT"
    if mode in ("valid", "valid_second"):
        payload = bytes.fromhex(
            (Path(__file__).parent / "fixtures/follow_joint_trajectory_goal.cdr.hex")
            .read_text()
            .strip()
        )
        goal = deserialize_message(payload, FollowJointTrajectory.Goal)
        if mode == "valid_second":
            goal.trajectory.points[0].positions[0] = 0.25
        native_uuid = str(uuid.UUID(bytes=(b"\x22" if mode == "valid_second" else b"\x11") * 16))
        accepted = wire_client.reserve((5, 0, "act", "session", "attempt"),
                                       "arm", goal, native_uuid)
        return "ACK" if accepted else "REJECT"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(2.0)
        conn.connect(sys.argv[1])
        frame = frame_for(mode)
        if mode in ("slow_prefix", "hold_prefix"):
            conn.sendall(frame[:1])
            if mode == "hold_prefix":
                print(f"PARTIAL {time.monotonic_ns()}", flush=True)
            time.sleep(0.3)
            try:
                conn.sendall(frame[1:])
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            conn.sendall(frame)
        if report_sent:
            print("REQUEST_SENT", flush=True)
        if mode == "close_drop_reply":
            conn.shutdown(socket.SHUT_RDWR)
            return "CLOSE_SENT_WITHOUT_ACK"
        if mode.startswith(("bootstrap_", "scoped_", "prearm_", "diagnostic_arm")):
            if mode == "prearm_drop_reply" or "drop_reply" in mode:
                conn.shutdown(socket.SHUT_RDWR)
                return "DROPPED"
            def exact(size):
                reply = bytearray()
                while len(reply) < size:
                    chunk = conn.recv(size - len(reply))
                    if not chunk:
                        return None
                    reply.extend(chunk)
                return bytes(reply)
            if mode.startswith(("bootstrap_", "scoped_", "prearm_")):
                prefix = exact(4)
                if prefix is None:
                    return "EOF"
                size = int.from_bytes(prefix, "big")
                if size > 236:
                    return "EOF"
            else:
                size = 104
            reply = exact(size)
            return "WIRE " + reply.hex() if reply is not None else "EOF"
        if mode.startswith("identity_"):
            prefix = conn.recv(4)
            if len(prefix) != 4:
                return "EOF"
            size = int.from_bytes(prefix, "big")
            reply = bytearray()
            while len(reply) < size:
                chunk = conn.recv(size - len(reply))
                if not chunk:
                    return "EOF"
                reply.extend(chunk)
            if reply[:7] == b"SOID\x01\x01\x03":
                return f"IDENTITY {int.from_bytes(reply[7:15], 'big')}"
            return "REJECT"
        if mode == "truncated":
            conn.shutdown(socket.SHUT_WR)
        try:
            expected = 40 if mode.startswith("ingress_") else 16
            reply = bytearray()
            while len(reply) < expected:
                chunk = conn.recv(expected - len(reply))
                if not chunk:
                    break
                reply.extend(chunk)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            return "EOF"
        if mode.startswith("ingress_"):
            if len(reply) != 40 or reply[:5] != b"SOGI\x01" or reply[7] != 0:
                return "EOF"
            if reply[5] == 1:
                return "REJECT"
            if reply[5] != 0:
                return "EOF"
            fields = [int.from_bytes(reply[start:start + 8], "big")
                      for start in (8, 16, 24, 32)]
            return "SNAPSHOT " + " ".join(map(str, (fields[0], reply[6], *fields[1:])))
        if len(reply) == 16 and reply[:6] == b"SOGA\x01\x00":
            return "ACK"
        if len(reply) == 16 and reply[:6] == b"SOGA\x01\x01":
            return "REJECT"
        return "EOF"


print(f"READY {os.getpid()} {start_ticks()}", flush=True)
for line in sys.stdin:
    mode = line.strip()
    if mode == "QUIT":
        break
    try:
        print(request(mode), flush=True)
    except (OSError, ValueError, RuntimeError):
        print("EOF", flush=True)
