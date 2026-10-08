"""The controller_state topics in their own process (data side only, no authority).

arm, gripper and neck publish at 500 Hz each: 1500 messages per second, ~215 us of GIL each in the Recorder (CP-3405
measurement), the largest single load of its main process. A spooler process now subscribes to the three topics with the same
QoS, validates and gap-counts every frame with the unchanged `ControllerReferenceObserver`, stamps its receipt on arrival and
appends the accepted frame to a spool file. The Recorder's `ControllerSpoolView` keeps the frames of the 2 s window, answers
the exact-instant lookup with the observer's own semantics, and takes the continuity report and any hazard from the spooler's
status file. Nothing about the rule changes: every frame is validated, every gap is counted, and the reference at an instant is
the one frame within 1 us of it inside the window of the sim clock.
"""

from __future__ import annotations

import bisect
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

KINDS = ("arm", "gripper", "neck")
MAGIC = b"CST1"
_HEADER = struct.Struct("<4sBQQI")
SPOOL_FILE, OVERFLOW_FILE, READY_FILE, STATUS_FILE = "controller.spool", "OVERFLOW", "ready", "status.json"
_TOPIC = "/{kind}_controller/controller_state"
_STATUS_PERIOD_S = 0.25


class SpoolFrameWriter:
    def __init__(self, directory, *, max_bytes: int) -> None:
        self.directory, self.max_bytes, self.size, self.full = Path(directory), int(max_bytes), 0, False
        self._stream = open(self.directory / SPOOL_FILE, "ab", buffering=0)

    def write(self, kind: str, stamp_ns: int, receipt_ns: int, payload: bytes) -> bool:
        if self.full:
            return False
        frame = _HEADER.pack(MAGIC, KINDS.index(kind), int(stamp_ns), int(receipt_ns), len(payload)) + bytes(payload)
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
    """A writer thread behind a queue: a callback only stamps and enqueues, so a stalled disk can never delay a receipt."""

    def __init__(self, writer) -> None:
        self.writer, self._queue = writer, queue.SimpleQueue()
        self.max_write_ns, self.max_depth, self.written = 0, 0, 0
        self._thread = threading.Thread(target=self._loop, name="so101-controller-spool-writer", daemon=True)
        self._thread.start()

    def put(self, kind, stamp_ns, receipt_ns, payload) -> None:
        self._queue.put((kind, stamp_ns, receipt_ns, payload))
        self.max_depth = max(self.max_depth, self._queue.qsize())

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            began = time.perf_counter_ns()
            self.writer.write(*item)
            self.max_write_ns = max(self.max_write_ns, time.perf_counter_ns() - began)
            self.written += 1

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


class SpoolFrameReader:
    def __init__(self, directory) -> None:
        self.directory, self._offset, self._buffer = Path(directory), 0, bytearray()

    def read(self) -> list:
        try:
            with open(self.directory / SPOOL_FILE, "rb") as stream:
                stream.seek(self._offset)
                data = stream.read()
        except FileNotFoundError:
            return []
        self._offset += len(data)
        self._buffer += data
        frames, position, buffer = [], 0, self._buffer
        while len(buffer) - position >= _HEADER.size:
            magic, kind, stamp, receipt, length = _HEADER.unpack_from(buffer, position)
            if magic != MAGIC or kind >= len(KINDS):
                raise ValueError("CONTROLLER_SPOOL_CORRUPT")
            end = position + _HEADER.size + length
            if len(buffer) < end:
                break
            frames.append((KINDS[kind], stamp, receipt, bytes(buffer[position + _HEADER.size:end])))
            position = end
        del buffer[:position]
        return frames

    def overflowed(self) -> bool:
        return (self.directory / OVERFLOW_FILE).exists()


class ControllerSpoolView:
    """The Recorder's bounded window of the frames the spooler accepted, answering like `ControllerReferenceObserver`."""

    def __init__(self, directory, *, identity, capacity: int = 2048) -> None:
        self._reader, self.identity, self._capacity = SpoolFrameReader(directory), tuple(identity), int(capacity)
        self._lock = threading.RLock()
        self._stamps = {kind: [] for kind in KINDS}
        self._frames = {kind: {} for kind in KINDS}

    def pull(self) -> int:
        frames = self._reader.read()
        with self._lock:
            for kind, stamp, receipt, payload in frames:
                stamps = self._stamps[kind]
                if stamps and stamp <= stamps[-1]:
                    continue
                stamps.append(stamp)
                self._frames[kind][stamp] = (receipt, payload)
                if len(stamps) > self._capacity:
                    drop = len(stamps) - self._capacity
                    for old in stamps[:drop]:
                        self._frames[kind].pop(old, None)
                    del stamps[:drop]
        return len(frames)

    def overflowed(self) -> bool:
        return self._reader.overflowed()

    def latest_stamp_ns(self, kind):
        with self._lock:
            stamps = self._stamps.get(kind)
            return stamps[-1] if stamps else None

    def matching_by_stamp(self, kind, *, now_sim_ns, window_ns, target_ns, tolerance_ns):
        with self._lock:
            try:
                if kind not in self._stamps:
                    raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID")
                stamps = self._stamps[kind]
                low = bisect.bisect_left(stamps, now_sim_ns - window_ns)
                high = bisect.bisect_right(stamps, now_sim_ns)
                if stamps and low >= high:
                    raise ValueError("CONTROLLER_REFERENCE_HISTORY_STALE")
                first = max(low, bisect.bisect_left(stamps, target_ns - tolerance_ns))
                last = min(high, bisect.bisect_right(stamps, target_ns + tolerance_ns))
                found = []
                for stamp in stamps[first:last]:
                    receipt, payload = self._frames[kind][stamp]
                    frame = json.loads(payload)
                    frame["sim_stamp_ns"], frame["received_monotonic_ns"] = stamp, receipt
                    found.append(frame)
                return self.identity, tuple(found)
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID") from error


class ControllerSpoolProcess:
    def __init__(self, directory, *, session_id: str, reset_epoch: int, floor_ns: int, max_bytes: int = 2 << 30) -> None:
        self.directory, self.session_id, self.reset_epoch = Path(directory), session_id, int(reset_epoch)
        self.floor_ns, self.max_bytes, self.child = int(floor_ns), int(max_bytes), None

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.child = subprocess.Popen(
            [sys.executable, "-m", "so101_demo.act.controller_spool", "--dir", str(self.directory), "--session",
             self.session_id, "--epoch", str(self.reset_epoch), "--floor-ns", str(self.floor_ns), "--max-bytes",
             str(self.max_bytes), "--parent-pid", str(os.getpid())], stdin=subprocess.DEVNULL, close_fds=True)
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

    def view(self, *, identity=None, capacity: int = 2048) -> ControllerSpoolView:
        return ControllerSpoolView(self.directory, identity=identity or (self.session_id, self.reset_epoch),
                                   capacity=capacity)

    def status_nowait(self) -> dict:
        try:
            return json.loads((self.directory / STATUS_FILE).read_text())
        except (OSError, ValueError):
            return {}

    def report(self, timeout_s: float = 2.0) -> dict:
        """The spooler's status after it has processed everything it received (asks for a fresh write)."""
        before = self.status_nowait().get("seq", 0)
        if self.child is not None and self.child.poll() is None:
            try:
                self.child.send_signal(signal.SIGUSR1)
            except OSError:
                pass
            end = time.monotonic() + timeout_s
            while time.monotonic() < end and self.status_nowait().get("seq", 0) <= before:
                time.sleep(0.01)
        return {"status": self.status_nowait()}

    def failure(self):
        if self.child is not None and self.child.poll() is not None:
            return "CONTROLLER_SPOOL_PROCESS_EXITED"
        if (self.directory / OVERFLOW_FILE).exists():
            return "CONTROLLER_SPOOL_OVERFLOW"
        return self.status_nowait().get("hazard")

    def close(self) -> dict:
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
        return self.status_nowait()


def run_spooler(directory: Path, session_id: str, reset_epoch: int, floor_ns: int, max_bytes: int,
                parent_pid: int | None = None) -> int:
    import rclpy
    from control_msgs.msg import JointTrajectoryControllerState
    from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

    from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver

    if parent_pid is not None:
        from .spool_lifecycle import die_with_parent
        die_with_parent(parent_pid)
    directory = Path(directory)
    writer = AsyncSpoolWriter(SpoolFrameWriter(directory, max_bytes=max_bytes))
    observer = ControllerReferenceObserver(max_frames=64)
    observer.reset(session_id, reset_epoch, source_floor_ns=floor_ns)
    counters = {"frames": 0, "max_gap_ns": 0, "seq": 0, "last": {}, "off_grid": {kind: 0 for kind in KINDS}}
    flags = {"stop": False, "dump": False}

    def on_frame(kind, message) -> None:
        receipt_s = time.monotonic()                      # first statement: the delivery boundary
        receipt_ns = int(receipt_s * 1e9)
        previous = counters["last"].get(kind)
        if previous is not None:
            counters["max_gap_ns"] = max(counters["max_gap_ns"], receipt_ns - previous)
        counters["last"][kind] = receipt_ns
        if not observer.accept(kind, message, received_monotonic_s=receipt_s):
            return
        record = observer._frames[kind][-1]
        if record["sim_stamp_ns"] % 2_000_000:           # the controller period is 2 ms: a stamp off that grid is evidence
            counters["off_grid"][kind] += 1
        body = {key: (list(value) if isinstance(value, tuple) else value) for key, value in record.items()
                if key not in ("sim_stamp_ns", "received_monotonic_ns")}
        writer.put(kind, record["sim_stamp_ns"], record["received_monotonic_ns"], json.dumps(body).encode())
        counters["frames"] += 1

    def status() -> dict:
        counters["seq"] += 1
        return {"seq": counters["seq"], "frames": counters["frames"], "gap_report": observer.gap_report(),
                "hazard": observer._hazard, "max_callback_gap_ms": counters["max_gap_ns"] / 1e6,
                "bytes": writer.size, "overflow": writer.full, "max_write_ms": writer.max_write_ns / 1e6,
                "max_queue_depth": writer.max_depth, "written": writer.written,
                "off_grid_frames": dict(counters["off_grid"])}

    def publish_status() -> None:
        tmp = directory / (STATUS_FILE + ".tmp")
        tmp.write_text(json.dumps(status()))
        tmp.replace(directory / STATUS_FILE)

    rclpy.init()
    node = rclpy.create_node(f"so101_controller_spool_{os.getpid()}")
    qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=1000, reliability=QoSReliabilityPolicy.RELIABLE)
    for kind in KINDS:
        node.create_subscription(JointTrajectoryControllerState, _TOPIC.format(kind=kind),
                                 lambda message, kind=kind: on_frame(kind, message), qos)
    signal.signal(signal.SIGTERM, lambda *_: flags.__setitem__("stop", True))
    signal.signal(signal.SIGINT, lambda *_: flags.__setitem__("stop", True))
    signal.signal(signal.SIGUSR1, lambda *_: flags.__setitem__("dump", True))
    publish_status()
    (directory / READY_FILE).write_bytes(b"1")
    next_status = time.monotonic() + _STATUS_PERIOD_S
    try:
        while not flags["stop"] and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)
            if flags["dump"] or time.monotonic() >= next_status:
                flags["dump"] = False
                publish_status()
                next_status = time.monotonic() + _STATUS_PERIOD_S
    except BaseException:
        pass
    finally:
        writer.close()                       # drains the queue before the last status is written
        try:
            publish_status()
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

    parser = argparse.ArgumentParser(prog="controller_spool")
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--epoch", required=True, type=int)
    parser.add_argument("--floor-ns", required=True, type=int)
    parser.add_argument("--max-bytes", type=int, default=2 << 30)
    parser.add_argument("--parent-pid", type=int, default=None)
    options = parser.parse_args(argv)
    return run_spooler(options.dir, options.session, options.epoch, options.floor_ns, options.max_bytes,
                       options.parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
