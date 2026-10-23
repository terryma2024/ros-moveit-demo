"""Diagnostic-only RECORDER_DELIVERY_SLOW log lines for the raw recorder process (stderr, no files, no per-message output).

rosbag2's recorder is a C++ node in the `bag_record_entry` child process: its subscription callbacks, cache and mcap writes
cannot be timed from Python. What this process owns, and what is timed here: the probe node's subscriptions on the same topics
(a gap across ALL topics seen by the probe, a burst after it) and the sidecar writer's write and fsync.
"""
from __future__ import annotations

import json
import sys
import time

from so101_demo.act.rig_profile import DEFAULT_RIG

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


STALL_GAP_NS = 100_000_000
STALL_CLUSTER_NS = 350_000_000
STALL_MAX_LINES = 10
STALL_MAX_MESSAGES = 50_000
STALL_MAX_SECONDS = 10.0
STALL_MAX_TRACE_BYTES = 64 * 1024 * 1024
STALL_TOPICS = DEFAULT_RIG.camera_topics     # the cameras of the default rig; a rig names its own via `rig.camera_topics`


def recorder_only_stalls(bag_dir, trace_path, *, stream=None, topics=STALL_TOPICS, read_messages=None, header_stamp_ns=None,
                         gap_ns: int = STALL_GAP_NS, max_lines: int = STALL_MAX_LINES, max_messages: int = STALL_MAX_MESSAGES,
                         max_seconds: float = STALL_MAX_SECONDS, monotonic=time.monotonic) -> dict:
    """Post-hoc, at task seal: messages the bag recorder received more than `gap_ns` after the probe received the same one.

    The recorder is a C++ process, so its receipt is the bag's per-message timestamp (CLOCK_REALTIME at receipt); the probe's is
    `real_ns` in `<bag>-probe-trace.jsonl`; messages are matched on (topic, header stamp). Late messages whose stamps lie within
    STALL_CLUSTER_NS of each other form one event, logged as `RECORDER_ONLY_STALL {json}` (at most `max_lines`). Diagnostic only:
    bounded in messages, time and trace size, never raises, no verdict. Returns a small summary."""
    summary = {"events": 0, "late_messages": 0, "matched": 0, "logged": 0, "truncated": False, "error": None}
    try:
        if read_messages is None:
            from .bag_io import read_messages
        if header_stamp_ns is None:
            from .probe_trace import header_stamp_ns
        probe, size = {}, 0
        with open(trace_path, encoding="utf-8") as trace:
            for line in trace:
                size += len(line)
                if size > STALL_MAX_TRACE_BYTES:
                    summary["truncated"] = True
                    break
                row = json.loads(line)
                if isinstance(row, list) and len(row) == 4 and row[0] in topics and row[3] is not None:
                    probe.setdefault((row[0], row[3]), row[1])
        deadline, late, seen = monotonic() + max_seconds, [], 0
        for topic, _type, bag_ns, data in read_messages(bag_dir, topics=list(topics)):
            seen += 1
            if seen > max_messages or monotonic() > deadline:
                summary["truncated"] = True
                break
            stamp = header_stamp_ns(data)
            real = probe.get((topic, stamp))
            if real is None:
                continue
            summary["matched"] += 1
            if bag_ns - real > gap_ns:
                late.append((stamp, topic, bag_ns - real))
        late.sort()
        events = []
        for item in late:
            if events and item[0] - events[-1][-1][0] <= STALL_CLUSTER_NS:
                events[-1].append(item)
            else:
                events.append([item])
        summary["late_messages"], summary["events"] = len(late), len(events)
        out = stream if stream is not None else sys.stderr
        for event in events[:max_lines]:
            record = {"topic_count": len({topic for _, topic, _ in event}), "topics": sorted({topic for _, topic, _ in event}),
                      "message_count": len(event), "gap_ms": round(max(gap for _, _, gap in event) / 1e6, 3),
                      "first_stamp": event[0][0], "last_stamp": event[-1][0]}
            print("RECORDER_ONLY_STALL " + json.dumps(record, sort_keys=True), file=out, flush=True)
            summary["logged"] += 1
    except BaseException as error:   # noqa: BLE001 - diagnostics never fail the recorder
        summary["error"] = repr(error)[:200]
    return summary
