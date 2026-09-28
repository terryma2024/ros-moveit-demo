"""Phase 3b: the ingress-snapshot exchange must not hold the client lock.

A deterministic blocking op-4 server keeps the snapshot exchange in flight; a
concurrent close_generation/query_identity must still be able to acquire the client
lock. A negative control proves the barrier is sensitive to the violation.
"""

import os
import socket
import struct
import threading
import time
import uuid
from pathlib import Path

import pytest

from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

ROLE_CODES = {"arm": 1, "gripper": 2, "neck": 3}


class _BlockingIngressServer:
    """Accepts the op-4 frame, then blocks before replying."""

    def __init__(self):
        self.dir = Path(f"/tmp/so101-debug-act-b3-snap-{uuid.uuid4().hex[:8]}")
        self.dir.mkdir(mode=0o700, exist_ok=True)
        self.path = self.dir / "arm.sock"
        assert len(os.fsencode(str(self.path))) <= 107
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.socket.listen(4)
        self.socket.settimeout(0.05)
        self.received = threading.Event()
        self.release = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.socket.accept()
            except (socket.timeout, TimeoutError):
                continue
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
                if body[:4] == b"SOIA":
                    payload = (b"SOID" + bytes((1, 1)) + bytes((ROLE_CODES["arm"],))
                               + struct.pack(">Q", 1) + bytes((2,)) + b"i" + bytes((6,))
                               + b"boot-1")
                    connection.sendall(struct.pack(">I", len(payload)) + payload)
                elif len(body) > 5 and body[5] == 4:      # op 4: ingress snapshot
                    self.received.set()
                    self.release.wait(10.0)               # hold the exchange open
                    connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                       + struct.pack(">Q", 1))
                elif len(body) > 5 and (body[5] == 2 or body[5] == 3):
                    generation = struct.unpack(">Q", body[38:46])[0]
                    connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                       + struct.pack(">Q", generation))
                else:
                    connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                       + struct.pack(">Q", 1))

    def close(self):
        self.stop.set()
        self.release.set()
        try:
            self.socket.close()
        except OSError:
            pass
        self.thread.join(1.0)


def _client(path):
    return ControllerReservationClient({"arm": str(path)}, capability=b"c" * 32, timeout_s=1.0)


def test_concurrent_close_is_not_blocked_by_the_snapshot_exchange():
    server = _BlockingIngressServer()
    try:
        client = _client(server.path)
        result = {}

        def run_snapshot():
            try:
                result["snapshot"] = client.snapshot_generation((1, "s", "b", "p", 1), "arm")
            except Exception as failure:                  # noqa: BLE001
                result["snapshot_error"] = failure

        snapshot_thread = threading.Thread(target=run_snapshot, daemon=True)
        snapshot_thread.start()
        assert server.received.wait(5.0), "the op-4 exchange was never started"

        lock_free = threading.Event()

        def run_close():
            try:
                client.close_generation(1)
            except Exception:                             # noqa: BLE001
                pass
            lock_free.set()

        close_thread = threading.Thread(target=run_close, daemon=True)
        close_thread.start()
        acquired_while_io = lock_free.wait(1.0)
        server.release.set()
        snapshot_thread.join(10.0)
        close_thread.join(5.0)
        assert acquired_while_io, (
            "close_generation could not run while the ingress-snapshot exchange was in "
            "flight: the client lock is held across connect/send/recv")
    finally:
        server.close()


def test_barrier_is_sensitive_to_the_violation(monkeypatch):
    """Negative control: an explicitly lock-holding snapshot must trip the barrier."""

    import so101_demo.adapters.act.controller_reservation_client as module

    original = module.ControllerReservationClient.snapshot_generation

    def lock_holding_snapshot(self, ticket, kind="arm"):
        with self._lock:
            time.sleep(1.5)                               # stands in for blocked I/O
        return original(self, ticket, kind)

    monkeypatch.setattr(module.ControllerReservationClient, "snapshot_generation",
                        lock_holding_snapshot)
    server = _BlockingIngressServer()
    try:
        client = _client(server.path)
        outcome = {}

        def run_snapshot():
            # capture the thread's outcome explicitly: an unhandled exception here
            # would surface as a pytest thread warning instead of an assertion
            try:
                outcome["result"] = client.snapshot_generation((1, "s", "b", "p", 1), "arm")
            except Exception as failure:                  # noqa: BLE001
                outcome["error"] = failure

        thread = threading.Thread(target=run_snapshot, daemon=True)
        thread.start()
        time.sleep(0.2)
        lock_free = threading.Event()

        def run_close():
            client.close_generation(1)
            lock_free.set()

        close_thread = threading.Thread(target=run_close, daemon=True)
        close_thread.start()
        blocked = not lock_free.wait(0.6)
        server.release.set()
        thread.join(10.0)
        close_thread.join(5.0)
        assert not thread.is_alive(), "the snapshot thread did not finish"
        error = outcome.get("error")
        if error is not None:
            # any failure must be a controlled contract failure, never an escaped one
            assert isinstance(error, (RuntimeError, ValueError, TimeoutError, OSError,
                                      PermissionError)), repr(error)
        assert blocked, "the barrier failed to notice a lock-holding snapshot"
    finally:
        server.close()


def test_the_role_code_table_is_defined_exactly_once():
    """A duplicate role table would silently fork the wire contract."""

    import so101_demo.adapters.act.controller_reservation_client as module
    from pathlib import Path as _Path

    source = _Path(module.__file__).read_text()
    definitions = [line for line in source.splitlines()
                   if line.startswith("_ROLE_CODES = ")]
    assert len(definitions) == 1, definitions
    assert module._ROLE_CODES == {"arm": 1, "gripper": 2, "neck": 3}
