"""Diagnostic-only receipt trace of the raw recorder's probe: when each camera frame and /clock message reached this process.

One JSON line per message, `[topic, receipt CLOCK_REALTIME ns, receipt CLOCK_MONOTONIC ns, header stamp ns]`, after a header line
that names the fields. The receipt thread only appends a tuple to a bounded buffer; a daemon thread writes it out every
`flush_every_s` and once more on close. The file sits beside the bag (`<bag>-probe-trace.jsonl`), next to `<bag>-record.log`, outside
the episode that is assembled from the bag. Nothing here can fail the recorder: write errors are kept in `failure`.
"""
from __future__ import annotations

import json
import struct
import threading
import time
from collections import deque

TRACE_TOPICS = ("/clock", "/head_camera/color", "/head_camera/camera_info", "/wrist_camera/color", "/wrist_camera/camera_info")
FIELDS = ["topic", "real_ns", "mono_ns", "stamp_ns"]
MAX_BUFFERED = 200_000


def header_stamp_ns(data) -> int | None:
    """The first field of a CDR-serialized Image, CameraInfo or Clock is the stamp (int32 sec, uint32 nanosec)."""
    try:
        if data is None or len(data) < 12:
            return None
        little = data[1] == 1
        sec, nanosec = struct.unpack_from("<iI" if little else ">iI", data, 4)
        return sec * 1_000_000_000 + nanosec
    except Exception:   # noqa: BLE001
        return None


class ProbeTrace:
    def __init__(self, path, *, topics=TRACE_TOPICS, realtime_ns=time.time_ns, monotonic_ns=time.monotonic_ns,
                 flush_every_s: float = 0.5, max_buffered: int = MAX_BUFFERED) -> None:
        self.path, self.topics = path, frozenset(topics)
        self._real, self._mono, self._every, self._max = realtime_ns, monotonic_ns, flush_every_s, max_buffered
        self._buffer = deque()
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self.count = self.dropped = 0
        self.failure = None
        self._stream = None
        try:
            self._stream = open(path, "x", encoding="utf-8")
            self._stream.write(json.dumps({"kind": "PROBE_TRACE", "schema_version": 1, "fields": FIELDS,
                                           "start_real_ns": self._real(), "start_mono_ns": self._mono()}) + "\n")
        except Exception as error:   # noqa: BLE001
            self.failure = repr(error)[:200]
        self._thread = threading.Thread(target=self._run, name="so101-probe-trace", daemon=True)
        self._thread.start()

    def on_message(self, topic: str, data) -> None:
        """Runs on the probe's executor thread: two clock reads and one append for a traced topic, nothing otherwise."""
        if topic not in self.topics or self._closed.is_set():
            return
        real, mono = self._real(), self._mono()
        if len(self._buffer) >= self._max:
            self.dropped += 1
            return
        self._buffer.append((topic, real, mono, header_stamp_ns(data)))
        self.count += 1

    def _drain(self) -> None:
        with self._lock:
            lines = []
            while self._buffer:
                lines.append(json.dumps(list(self._buffer.popleft()), separators=(",", ":")))
            if lines and self._stream is not None and self.failure is None:
                try:
                    self._stream.write("\n".join(lines) + "\n")
                    self._stream.flush()
                except Exception as error:   # noqa: BLE001
                    self.failure = repr(error)[:200]

    def _run(self) -> None:
        while not self._closed.wait(self._every):
            self._drain()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._thread.join(5.0)
        self._drain()
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception as error:   # noqa: BLE001
                    self.failure = self.failure or repr(error)[:200]
                self._stream = None
