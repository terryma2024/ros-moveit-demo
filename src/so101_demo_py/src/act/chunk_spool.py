"""The Recorder's physics-chunk receipt in its own process (data side only, no authority).

A spooler process subscribes to the physics chunk topic with a RAW subscription: the callback only stamps
`time.monotonic_ns()` and queues the serialized bytes; a writer thread converts each chunk to its record (JSON) when it can and
appends it to an append-only spool file, so the Recorder's main process neither pays for the conversion nor can a stall of it
(a long json.loads, a GC pass, an import) change a receipt. The receipt stamp is the true delivery boundary and is RECORDED
(telemetry: how long each leg of sample -> publish -> receipt took); since CP-3410 it is no longer judged per chunk. The writer
never blocks the callback: a spool that would exceed `max_bytes` writes an OVERFLOW marker and stops; the reader turns that, a
dead spooler and a backlog beyond the frozen policy into failures of the data. The spooler dies with its parent
(PR_SET_PDEATHSIG and a parent-pid watchdog, `spool_lifecycle`).
"""

from __future__ import annotations

import json
import os
import queue
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

MAGIC = b"SPL1"
MAGIC_RECORD = b"SPL2"      # the payload is the converted record (JSON), not the CDR bytes
_HEADER = struct.Struct("<4sQQ")
SPOOL_FILE, OVERFLOW_FILE, READY_FILE, STATS_FILE = "chunks.spool", "OVERFLOW", "ready", "stats.json"
CHUNK_TOPIC = "/so101/simulation/physics_step_chunks"


class SpoolWriter:
    def __init__(self, directory, *, max_bytes: int) -> None:
        self.directory, self.max_bytes, self.size, self.full = Path(directory), int(max_bytes), 0, False
        self._stream = open(self.directory / SPOOL_FILE, "ab", buffering=0)

    def write(self, receipt_ns: int, data: bytes, *, record: bool = False) -> bool:
        if self.full:
            return False
        frame = _HEADER.pack(MAGIC_RECORD if record else MAGIC, int(receipt_ns), len(data)) + bytes(data)
        if self.size + len(frame) > self.max_bytes:
            self.full = True
            (self.directory / OVERFLOW_FILE).write_bytes(b"1")
            return False
        self._stream.write(frame)
        self.size += len(frame)
        return True

    def close(self) -> None:
        self._stream.close()


class AsyncSpoolWriter:
    """A writer thread behind a queue: the callback only stamps and enqueues, a stalled disk cannot delay a receipt."""

    def __init__(self, writer, *, transform=None) -> None:
        self.writer, self._queue, self.transform = writer, queue.SimpleQueue(), transform
        self.max_write_ns, self.max_depth, self.converted, self.passed_through = 0, 0, 0, 0
        self._thread = threading.Thread(target=self._loop, name="so101-chunk-spool-writer", daemon=True)
        self._thread.start()

    def write(self, receipt_ns: int, data: bytes) -> None:
        self._queue.put((receipt_ns, data))
        self.max_depth = max(self.max_depth, self._queue.qsize())

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            began = time.perf_counter_ns()
            record = False
            if self.transform is not None:
                # In this writer thread, not in the callback (which only stamps): the conversion costs the spooler's GIL,
                # not the Recorder's. A chunk that cannot be converted travels as its original bytes and the Recorder
                # judges it exactly as before.
                record, data = self.transform(*item)
                item = (item[0], data)
                self.converted, self.passed_through = self.converted + bool(record), self.passed_through + (not record)
            self.writer.write(*item, record=record)
            self.max_write_ns = max(self.max_write_ns, time.perf_counter_ns() - began)

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(5.0)
        self.writer.close()

    @property
    def full(self) -> bool:
        return self.writer.full

    @property
    def size(self) -> int:
        return self.writer.size


class SpoolReader:
    def __init__(self, directory, child=None) -> None:
        self.directory, self.child = Path(directory), child
        self._offset, self._buffer = 0, b""

    def read_frames(self) -> list[tuple[bool, int, bytes]]:
        """(is_record, receipt_ns, payload) for every complete frame; a partial tail waits for its end."""
        path = self.directory / SPOOL_FILE
        try:
            with open(path, "rb") as stream:
                stream.seek(self._offset)
                data = stream.read()
        except FileNotFoundError:
            return []
        self._offset += len(data)
        self._buffer += data
        frames = []
        while len(self._buffer) >= _HEADER.size:
            magic, receipt, length = _HEADER.unpack_from(self._buffer)
            if magic not in (MAGIC, MAGIC_RECORD):
                raise ValueError("PHYSICS_RAW_SPOOL_CORRUPT")
            if len(self._buffer) < _HEADER.size + length:
                break
            frames.append((magic == MAGIC_RECORD, receipt, self._buffer[_HEADER.size:_HEADER.size + length]))
            self._buffer = self._buffer[_HEADER.size + length:]
        return frames

    def read(self) -> list[tuple[int, bytes]]:
        return [(receipt, data) for _, receipt, data in self.read_frames()]

    def overflowed(self) -> bool:
        return (self.directory / OVERFLOW_FILE).exists()

    def failure(self) -> str | None:
        """The hazard the spool itself implies: overflow, corruption is raised by read(), a dead spooler."""
        if self.overflowed():
            return "PHYSICS_RAW_SPOOL_OVERFLOW"
        if self.child is not None and self.child.poll() is not None:
            return "PHYSICS_RAW_RECEIVER_FAILED"
        return None

    def stats(self) -> dict:
        try:
            return json.loads((self.directory / STATS_FILE).read_text())
        except (OSError, ValueError):
            return {}

    def close(self) -> None:
        child = self.child
        if child is not None and child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=5.0)
            except Exception:
                try:
                    child.kill()
                except Exception:
                    pass


class SpoolProcess:
    """Starts and owns the spooler subprocess of one Recorder."""

    def __init__(self, directory, *, topic: str = CHUNK_TOPIC, max_bytes: int = 4 << 30, convert=None) -> None:
        #: `(max_samples, max_contacts)` (each may be None): the spooler converts every chunk to its record in its own process
        self.directory, self.topic, self.max_bytes, self.child = Path(directory), topic, max_bytes, None
        self.convert = convert

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.child = subprocess.Popen(
            [sys.executable, "-m", "so101_demo.act.chunk_spool", "--dir", str(self.directory), "--topic", self.topic,
             "--max-bytes", str(self.max_bytes), "--parent-pid", str(os.getpid()),
             *(() if self.convert is None else ("--convert", str(-1 if self.convert[0] is None else self.convert[0]),
                                                  str(-1 if self.convert[1] is None else self.convert[1])))],
            stdin=subprocess.DEVNULL, close_fds=True)
        self._register_exit_close()

    def _register_exit_close(self) -> None:
        from .spool_lifecycle import register_exit_close
        register_exit_close(self)

    def wait_ready(self, timeout_s: float) -> bool:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            if (self.directory / READY_FILE).exists():
                return True
            if self.child is not None and self.child.poll() is not None:
                return False
            time.sleep(0.01)
        return (self.directory / READY_FILE).exists()

    def reader(self) -> SpoolReader:
        return SpoolReader(self.directory, child=self.child)

    def close(self) -> None:
        self.reader().close()


def make_record_transform(max_samples=None, max_contacts=None):
    """`(receipt_ns, cdr_bytes) -> (is_record, payload)`: the converted record as JSON, or the original bytes when it cannot be."""
    from rclpy.serialization import deserialize_message
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk

    from .raw_physics_chunks import raw_chunk_from_ros

    def transform(receipt, data):
        try:
            message = deserialize_message(data, PhysicsStepEvidenceChunk)
            record = raw_chunk_from_ros(message, received_monotonic_ns=receipt, max_samples=max_samples,
                                        max_contacts=max_contacts)
            return True, json.dumps(record, separators=(",", ":"), allow_nan=False).encode()
        except Exception:
            return False, data
    return transform


def run_spooler(directory: Path, topic: str, max_bytes: int, parent_pid: int | None = None, convert=None) -> int:
    """The spooler process body: stamp, append, nothing else."""

    import rclpy
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk

    if parent_pid is not None:
        from .spool_lifecycle import die_with_parent
        die_with_parent(parent_pid)
    transform = None
    if convert is not None:
        import sys as _sys
        transform = make_record_transform(*(None if value < 0 else value for value in convert))
        _sys.setswitchinterval(0.001)            # the callback (a stamp) must not wait behind the conversion thread
    writer = AsyncSpoolWriter(SpoolWriter(directory, max_bytes=max_bytes), transform=transform)
    state = {"count": 0, "last": None, "max_gap_ns": 0}

    def on_chunk(data) -> None:
        stamp = time.monotonic_ns()               # first statement: the delivery boundary
        if state["last"] is not None:
            state["max_gap_ns"] = max(state["max_gap_ns"], stamp - state["last"])
        state["last"] = stamp
        state["count"] += 1
        writer.write(stamp, data)

    rclpy.init()
    node = rclpy.create_node(f"so101_chunk_spool_{os.getpid()}")
    qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
    node.create_subscription(PhysicsStepEvidenceChunk, topic, on_chunk, qos, raw=True)
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("now", True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("now", True))
    (Path(directory) / READY_FILE).write_bytes(b"1")
    try:
        while not stop["now"] and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
    except BaseException:
        pass
    finally:
        writer.close()                       # drains the queue: the stats below count what reached the file
        try:
            (Path(directory) / STATS_FILE).write_text(json.dumps(
                {"chunks": state["count"], "max_callback_gap_ms": state["max_gap_ns"] / 1e6,
                 "bytes": writer.size, "overflow": writer.full, "max_write_ms": writer.max_write_ns / 1e6,
                 "max_queue_depth": writer.max_depth, "converted": writer.converted,
                 "passed_through": writer.passed_through}))
        except OSError:
            pass
        try:
            node.destroy_node()
            rclpy.try_shutdown()
        except Exception:
            pass
    return 0


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="chunk_spool")
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--topic", default=CHUNK_TOPIC)
    parser.add_argument("--max-bytes", type=int, default=4 << 30)
    parser.add_argument("--parent-pid", type=int, default=None)
    parser.add_argument("--convert", nargs=2, type=int, default=None, metavar=("MAX_SAMPLES", "MAX_CONTACTS"))
    options = parser.parse_args(argv)
    return run_spooler(options.dir, options.topic, options.max_bytes, options.parent_pid,
                       None if options.convert is None else tuple(options.convert))


if __name__ == "__main__":
    raise SystemExit(main())
