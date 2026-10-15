"""Diagnostic-only RECORDER_DELIVERY_SLOW log lines for the raw recorder process (stderr, no files, no per-message output).

rosbag2's recorder is a C++ node in the `bag_record_entry` child process: its subscription callbacks, cache and mcap writes
cannot be timed from Python. What this process owns, and what is timed here: the probe node's subscriptions on the same topics
(a gap across ALL topics seen by the probe, a burst after it) and the sidecar writer's write and fsync.
"""
from __future__ import annotations

import json
import sys
import time

GAP_THRESHOLD_NS = 150_000_000
IO_THRESHOLD_NS = 100_000_000
MAX_LINES_PER_WINDOW = 20
WINDOW_NS = 10_000_000_000


class SlowLineLog:
    """Writes `RECORDER_DELIVERY_SLOW {json}` lines, at most MAX_LINES_PER_WINDOW per WINDOW_NS; the rest are counted."""

    def __init__(self, *, stream=None, monotonic_ns=time.monotonic_ns, realtime_ns=time.time_ns) -> None:
        self._stream, self._mono, self._real = stream, monotonic_ns, realtime_ns
        self._window_start = None
        self._emitted = 0
        self.suppressed = 0

    def emit(self, kind: str, **fields) -> bool:
        now = self._mono()
        if self._window_start is None or now - self._window_start >= WINDOW_NS:
            self._window_start, self._emitted = now, 0
        if self._emitted >= MAX_LINES_PER_WINDOW:
            self.suppressed += 1
            return False
        self._emitted += 1
        record = {"kind": kind, "suppressed_total": self.suppressed, **fields}
        stream = self._stream if self._stream is not None else sys.stderr
        try:
            print("RECORDER_DELIVERY_SLOW " + json.dumps(record, sort_keys=True), file=stream, flush=True)
        except Exception:   # noqa: BLE001 - diagnostics never fail the recorder
            return False
        return True


LOG = SlowLineLog()


class DeliveryGapMonitor:
    """Gap between consecutive message receipts across all topics, reported only while `active` (recording, not stopping).

    `on_message` runs in the probe's executor thread (one thread), costs one clock read per message and logs only on a gap."""

    def __init__(self, *, log: SlowLineLog = LOG, threshold_ns: int = GAP_THRESHOLD_NS,
                 monotonic_ns=time.monotonic_ns, realtime_ns=time.time_ns) -> None:
        self._log, self._threshold, self._mono, self._real = log, threshold_ns, monotonic_ns, realtime_ns
        self.active = False
        self._last_ns = None
        self._last_topic = None
        self.count = 0
        self.gaps = 0

    def on_message(self, topic: str) -> None:
        now = self._mono()
        last, last_topic = self._last_ns, self._last_topic
        self._last_ns, self._last_topic = now, topic
        self.count += 1
        if not self.active or last is None:
            return
        gap = now - last
        if gap >= self._threshold:
            self.gaps += 1
            self._log.emit("receipt_gap", mono_ns=last, real_ns=self._real() - gap, gap_ms=round(gap / 1e6, 3),
                           from_topic=last_topic, to_topic=topic, messages_so_far=self.count)

    def start(self) -> None:
        """Recording begins: the first gap is measured from the next receipt."""
        self._last_ns = None
        self.active = True

    def stop(self) -> None:
        self.active = False


def timed(log: SlowLineLog, kind: str, operation, *, threshold_ns: int = IO_THRESHOLD_NS,
          monotonic_ns=time.monotonic_ns, realtime_ns=time.time_ns, **fields):
    """Run `operation()`; log `kind` when it took `threshold_ns` or longer. Returns the operation's result."""
    began = monotonic_ns()
    try:
        return operation()
    finally:
        took = monotonic_ns() - began
        if took >= threshold_ns:
            log.emit(kind, mono_ns=began, real_ns=realtime_ns() - took, duration_ms=round(took / 1e6, 3), **fields)
