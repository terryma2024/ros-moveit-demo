#!/usr/bin/env python3
"""Cross-process wire client for the controller reservation test only."""

import os
from pathlib import Path
import socket
import sys
import time


def start_ticks() -> int:
    return int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])


def frame_for(mode: str) -> bytes:
    capability = bytes.fromhex(sys.argv[2])
    if mode in ("close_generation", "close_stale"):
        body = b"SOGR\x01\x02" + capability + (5).to_bytes(8, "big") + bytes(16)
        return len(body).to_bytes(4, "big") + body
    payload = bytes.fromhex(
        (Path(__file__).parent / "fixtures/follow_joint_trajectory_goal.cdr.hex")
        .read_text()
        .strip()
    )
    if mode == "wrong_capability":
        capability = bytes([capability[0] ^ 1]) + capability[1:]
    generation = 4 if mode == "stale_generation" else 5
    body = (
        b"SOGR\x01\x01"
        + capability
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
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(2.0)
        conn.connect(sys.argv[1])
        frame = frame_for(mode)
        if mode == "slow_prefix":
            conn.sendall(frame[:1])
            time.sleep(0.3)
            try:
                conn.sendall(frame[1:])
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            conn.sendall(frame)
        if mode == "truncated":
            conn.shutdown(socket.SHUT_WR)
        try:
            reply = conn.recv(16)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            return "EOF"
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
    except (OSError, ValueError):
        print("EOF", flush=True)
