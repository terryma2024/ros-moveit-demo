"""Process-wide stall diagnostics (T0b-diag): garbage collections, inference spans and a heartbeat that detects pauses.

Nothing here is read by the control path. A `StallMonitor` records, on the same monotonic clock the goal-pair telemetry uses:

* every cyclic-GC collection (`gc.callbacks`): generation, start, end, collected and uncollectable counts;
* the spans of the policy inference (the worker call, and the pre-processing, forward pass and post-processing inside it);
* the heartbeat: a thread that sleeps 1 ms in a loop; a wake-up later than `stall_s` (5 ms) is a stall of the whole process
  (the GIL held by another thread, or a stop-the-world event), recorded with its start and end.

`summary` reduces the window of one episode and joins it per failed goal pair: which of GC, inference or a heartbeat stall overlaps
the window [send, accept].
"""

import collections
import gc
import threading
import time

from .goal_pair_telemetry import latency_stats

LONG_COLLECTION_S = 0.005
STALL_S = 0.005
HEARTBEAT_SLEEP_S = 0.001
INFERENCE_KINDS = ("call", "pre", "forward", "post")
_MAX_LISTED = 200
_MAX_SPANS_LISTED = 5000
_LATE_ACCEPT_S = 0.020


def _overlaps(start, end, other_start, other_end):
    return other_start <= end and other_end >= start


def _stats(values):
    stats = latency_stats(values)
    return {key: stats[key] for key in ("n", "p50", "p99", "max")}


class StallMonitor:
    def __init__(self, *, monotonic=time.monotonic, sleep=time.sleep, stall_s=STALL_S, heartbeat_sleep_s=HEARTBEAT_SLEEP_S,
                 capacity=2_000_000):
        self.monotonic, self._sleep, self.stall_s, self.heartbeat_sleep_s = monotonic, sleep, stall_s, heartbeat_sleep_s
        self.collections = collections.deque(maxlen=capacity)        # (generation, start, end, collected, uncollectable)
        self.spans = collections.deque(maxlen=capacity)              # (kind, start, end)
        self.stalls = collections.deque(maxlen=capacity)             # (start, end)
        self.wakeups = 0
        self.max_gap_s = 0.0
        self._gc_started = None
        self._stop = threading.Event()
        self._thread = None
        self._installed = False

    # ---- recording ------------------------------------------------------------------------------------------------------

    def _on_gc(self, phase, info):
        if phase == "start":
            self._gc_started = self.monotonic()
        elif phase == "stop" and self._gc_started is not None:
            self.collections.append((info.get("generation"), self._gc_started, self.monotonic(), info.get("collected", 0),
                                     info.get("uncollectable", 0)))
            self._gc_started = None

    def record_span(self, kind, start, end):
        self.spans.append((kind, start, end))

    def beat(self, previous):
        """One heartbeat: sleep, then record the gap since `previous` when it is a stall. Returns the new time."""
        self._sleep(self.heartbeat_sleep_s)
        now = self.monotonic()
        gap = now - previous
        self.wakeups += 1
        if gap > self.max_gap_s:
            self.max_gap_s = gap
        if gap > self.stall_s:
            self.stalls.append((previous, now))
        return now

    def _run(self):
        previous = self.monotonic()
        while not self._stop.is_set():
            previous = self.beat(previous)

    def start(self):
        if self._installed:
            return
        self._installed = True
        gc.callbacks.append(self._on_gc)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="act-stall-heartbeat", daemon=True)
        self._thread.start()

    def stop(self):
        if not self._installed:
            return
        self._installed = False
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            gc.callbacks.remove(self._on_gc)
        except ValueError:
            pass

    # ---- reduction --------------------------------------------------------------------------------------------------------

    def summary(self, *, since_s, until_s, pairs=(), accept_timeout_s=_LATE_ACCEPT_S):
        """The window [since_s, until_s] of the monitor, joined with the goal pairs of the attempt (diagnostics only)."""

        collections_in = [row for row in tuple(self.collections) if row[2] >= since_s and row[1] <= until_s]
        spans_in = [row for row in tuple(self.spans) if row[2] >= since_s and row[1] <= until_s]
        stalls_in = [row for row in tuple(self.stalls) if row[1] >= since_s and row[0] <= until_s]
        generations = sorted({row[0] for row in collections_in})
        gc_summary = {"count": {str(generation): sum(1 for row in collections_in if row[0] == generation)
                                for generation in generations},
                      "duration_s": {str(generation): _stats([row[2] - row[1] for row in collections_in if row[0] == generation])
                                     for generation in generations},
                      "collected": sum(row[3] for row in collections_in),
                      "uncollectable": sum(row[4] for row in collections_in),
                      "long": [self._gc_row(row) for row in collections_in
                               if row[2] - row[1] > LONG_COLLECTION_S][:_MAX_LISTED]}
        by_kind = {kind: [row for row in spans_in if row[0] == kind] for kind in INFERENCE_KINDS}
        inference = {"count": len(by_kind["call"]),
                     "duration_s": {kind: _stats([row[2] - row[1] for row in rows]) for kind, rows in by_kind.items()},
                     "spans": {kind: [[row[1], row[2]] for row in rows] for kind, rows in by_kind.items()}
                     if len(by_kind["call"]) <= _MAX_SPANS_LISTED else "omitted: more than %d inferences" % _MAX_SPANS_LISTED}
        window = max(until_s - since_s, 1e-9)
        calls = by_kind["call"]
        heartbeat = {"stall_threshold_s": self.stall_s, "sleep_s": self.heartbeat_sleep_s, "wakeups_total": self.wakeups,
                     "max_gap_s_total": self.max_gap_s, "stalls": len(stalls_in),
                     "stall_duration_s": _stats([row[1] - row[0] for row in stalls_in]),
                     "listed": [{"start": row[0], "end": row[1], "duration_s": row[1] - row[0]} for row in stalls_in][:_MAX_LISTED]}
        coincidence = self._coincidence(stalls_in, collections_in, calls, by_kind["forward"])
        coincidence["duty"] = {
            "window_s": window,
            "inference_call_fraction": sum(min(row[2], until_s) - max(row[1], since_s) for row in calls) / window,
            "gc_fraction": sum(min(row[2], until_s) - max(row[1], since_s) for row in collections_in) / window}
        return {"window": {"since_s": since_s, "until_s": until_s}, "gc": gc_summary, "inference": inference,
                "heartbeat": heartbeat, "coincidence": coincidence,
                "pairs": self._attribute(pairs, collections_in, spans_in, stalls_in, accept_timeout_s)}

    @staticmethod
    def _gc_row(row):
        return {"generation": row[0], "start": row[1], "end": row[2], "duration_s": row[2] - row[1], "collected": row[3],
                "uncollectable": row[4]}

    @staticmethod
    def _coincidence(stalls, collections_in, calls, forwards):
        def any_overlap(stall, rows, start=1, end=2):
            return any(_overlaps(stall[0], stall[1], row[start], row[end]) for row in rows)

        counts = {"stalls": len(stalls), "with_gc": 0, "with_gc_generation_2": 0, "with_inference_call": 0,
                  "with_forward": 0, "with_none": 0}
        for stall in stalls:
            gc_any = any_overlap(stall, collections_in)
            gc_two = any_overlap(stall, [row for row in collections_in if row[0] == 2])
            call = any_overlap(stall, calls)
            forward = any_overlap(stall, forwards)
            counts["with_gc"] += gc_any
            counts["with_gc_generation_2"] += gc_two
            counts["with_inference_call"] += call
            counts["with_forward"] += forward
            counts["with_none"] += not (gc_any or call)
        return counts

    def _attribute(self, pairs, collections_in, spans_in, stalls_in, accept_timeout_s):
        rows = []
        for pair in pairs:
            latencies = [value for value in (pair.get("accept_latency_s") or {}).values() if value is not None]
            late = bool(latencies) and max(latencies) > accept_timeout_s
            if pair.get("outcome") == "accepted" and not late:
                continue
            sends = [value for value in (pair.get("send_wall_s") or {}).values() if value is not None]
            if not sends:
                continue
            ends = [value for value in (pair.get("accept_wall_s") or {}).values() if value is not None]
            if pair.get("check_wall_s") is not None:
                ends.append(pair["check_wall_s"])
            if pair.get("sent_done_wall_s") is not None:
                ends.append(pair["sent_done_wall_s"] + accept_timeout_s)
            start, end = min(sends), max(ends or [max(sends)])
            rows.append({
                "sequence": pair.get("sequence"), "outcome": pair.get("outcome"), "late_controller": pair.get("late_controller"),
                "window": [start, end], "window_s": end - start,
                "gc": [self._gc_row(row) for row in collections_in if _overlaps(start, end, row[1], row[2])],
                "inference": [{"kind": row[0], "start": row[1], "end": row[2]} for row in spans_in
                              if _overlaps(start, end, row[1], row[2])],
                "heartbeat_stalls": [{"start": row[0], "end": row[1], "duration_s": row[1] - row[0]} for row in stalls_in
                                     if _overlaps(start, end, row[0], row[1])]})
        return rows
