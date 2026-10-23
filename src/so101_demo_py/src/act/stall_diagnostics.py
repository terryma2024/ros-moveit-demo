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
import os
import sys
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
CPU_STALL_S = 0.008             # a stall this long gets the per-thread CPU and scheduling account
SAMPLE_PERIOD_S = 0.010         # how often the heartbeat refreshes its CPU baseline
STACK_PERIOD_S = 1.0            # at most one stored stack summary per second
_FRAMES_PER_THREAD = 3
_MAX_DETAILS = 200


class ThreadSampler:
    """Per-thread on-CPU and runnable-waiting time from `/proc/self/task/<tid>/schedstat`, thread names, and stack summaries.

    `schedstat` is `run_ns wait_ns timeslices`: the nanoseconds the thread ran, and the nanoseconds it was runnable but not on a CPU
    (utime+stime of `stat` tick at 10 ms, too coarse for an 8 ms stall). A thread blocked on the GIL is asleep, not runnable, so it adds
    no wait time; a thread that is runnable and waiting for a CPU does."""

    def __init__(self, *, proc_root="/proc/self/task", current_frames=sys._current_frames, threads=threading.enumerate):
        self.proc_root, self._frames, self._threads = proc_root, current_frames, threads

    def cpu(self):
        """{tid: (run_ns, wait_ns)}"""
        out = {}
        try:
            tids = os.listdir(self.proc_root)
        except OSError:
            return out
        for tid in tids:
            try:
                with open(f"{self.proc_root}/{tid}/schedstat") as handle:
                    fields = handle.read().split()
                out[int(tid)] = (int(fields[0]), int(fields[1]))
            except (OSError, ValueError, IndexError):
                continue             # the thread ended between the listing and the read
        return out

    def names(self):
        """{tid: (name, is_python_thread)}; native threads are named by their `comm`."""
        python = {thread.native_id: thread.name for thread in self._threads() if thread.native_id is not None}
        out = {}
        try:
            tids = os.listdir(self.proc_root)
        except OSError:
            return out
        for tid in tids:
            try:
                number = int(tid)
            except ValueError:
                continue
            if number in python:
                out[number] = (python[number], True)
                continue
            try:
                with open(f"{self.proc_root}/{tid}/comm") as handle:
                    out[number] = (handle.read().strip(), False)
            except OSError:
                out[number] = (f"tid{number}", False)
        return out

    def stacks(self, skip_ident=None):
        """{thread name: ["file:line function", ...]}: the top frames of every Python thread but `skip_ident`."""
        by_ident = {thread.ident: thread.name for thread in self._threads()}
        out = {}
        for ident, frame in self._frames().items():
            if ident == skip_ident:
                continue
            rows = []
            while frame is not None and len(rows) < _FRAMES_PER_THREAD:
                code = frame.f_code
                rows.append(f"{os.path.basename(code.co_filename)}:{frame.f_lineno} {code.co_name}")
                frame = frame.f_back
            out[by_ident.get(ident, f"ident{ident}")] = rows
        return out


def classify_stall(*, window_s, deltas, heartbeat_tid, names):
    """Say why the heartbeat woke late from the CPU and scheduling deltas over `window_s` (see `ThreadSampler`).

    `deltas` maps tid -> (run_s, wait_s). Returns (classification, holder): `unscheduled` (the heartbeat was runnable and waiting for a
    CPU), `gil_holder` (a Python thread ran for most of the window), `native_cpu` (a thread without the GIL ran for most of it),
    `nobody_ran` (no thread ran: the process slept through)."""

    window_s = max(window_s, 1e-9)
    if deltas.get(heartbeat_tid, (0.0, 0.0))[1] >= 0.5 * window_s:
        return "unscheduled", None
    others = [(run, tid) for tid, (run, _wait) in deltas.items() if tid != heartbeat_tid]
    python = sorted(((run, tid) for run, tid in others if names.get(tid, ("", False))[1]), reverse=True)
    native = sorted(((run, tid) for run, tid in others if not names.get(tid, ("", False))[1]), reverse=True)
    if python and python[0][0] >= 0.5 * window_s:
        return "gil_holder", names[python[0][1]][0]
    if native and native[0][0] >= 0.5 * window_s:
        return "native_cpu", names[native[0][1]][0]
    return "nobody_ran", None


def _overlaps(start, end, other_start, other_end):
    return other_start <= end and other_end >= start


def _stats(values):
    stats = latency_stats(values)
    return {key: stats[key] for key in ("n", "p50", "p99", "max")}


class StallMonitor:
    def __init__(self, *, monotonic=time.monotonic, sleep=time.sleep, stall_s=STALL_S, heartbeat_sleep_s=HEARTBEAT_SLEEP_S,
                 capacity=2_000_000, sampler=None, cpu_stall_s=CPU_STALL_S, sample_period_s=SAMPLE_PERIOD_S,
                 stack_period_s=STACK_PERIOD_S):
        self.monotonic, self._sleep, self.stall_s, self.heartbeat_sleep_s = monotonic, sleep, stall_s, heartbeat_sleep_s
        self.collections = collections.deque(maxlen=capacity)        # (generation, start, end, collected, uncollectable)
        self.spans = collections.deque(maxlen=capacity)              # (kind, start, end)
        self.stalls = collections.deque(maxlen=capacity)             # (start, end)
        self.wakeups = 0
        self.max_gap_s = 0.0
        self.sampler = sampler if sampler is not None else ThreadSampler()
        self.cpu_stall_s, self.sample_period_s, self.stack_period_s = cpu_stall_s, sample_period_s, stack_period_s
        self.details = {}                                            # stall start -> account of a stall over cpu_stall_s
        self._baseline = None                                        # (time, {tid: (run_ns, wait_ns)}) of the last beat
        self._last_stack_stored = None
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
        try:
            self._account(previous, now, gap)
        except Exception:               # noqa: BLE001 - diagnostics never stop the heartbeat
            pass
        return now

    def _account(self, previous, now, gap):
        """Keep a CPU baseline fresh every `sample_period_s`; on a stall over `cpu_stall_s` say who ran and who was waiting."""
        baseline = self._baseline
        if gap > self.cpu_stall_s and baseline is not None:
            after = self.sampler.cpu()
            window = now - baseline[0]
            names = self.sampler.names()
            deltas = {tid: ((run - baseline[1].get(tid, (run, wait))[0]) / 1e9, (wait - baseline[1].get(tid, (run, wait))[1]) / 1e9)
                      for tid, (run, wait) in after.items()}
            heartbeat_tid = threading.get_native_id()
            classification, holder = classify_stall(window_s=window, deltas=deltas, heartbeat_tid=heartbeat_tid, names=names)
            top = sorted(((run, wait, tid) for tid, (run, wait) in deltas.items() if tid != heartbeat_tid and run > 0.0005),
                         reverse=True)[:5]
            detail = {"start": previous, "end": now, "duration_s": gap, "window_s": window, "classification": classification,
                      "holder": holder,
                      "process_cpu_s": sum(run for tid, (run, _wait) in deltas.items() if tid != heartbeat_tid),
                      "heartbeat_runnable_wait_s": deltas.get(heartbeat_tid, (0.0, 0.0))[1],
                      "threads": [{"name": names.get(tid, (f"tid{tid}", False))[0], "python": names.get(tid, ("", False))[1],
                                   "cpu_s": run, "runnable_wait_s": wait} for run, wait, tid in top]}
            if self._last_stack_stored is None or now - self._last_stack_stored >= self.stack_period_s:
                self._last_stack_stored = now
                detail["stacks_at_wakeup"] = self.sampler.stacks(skip_ident=threading.get_ident())
            if len(self.details) < _MAX_DETAILS * 50:
                self.details[previous] = detail
            self._baseline = (now, after)
        elif baseline is None or now - baseline[0] >= self.sample_period_s:
            self._baseline = (now, self.sampler.cpu())

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
        detailed = [self.details[row[0]] for row in stalls_in if row[0] in self.details]
        heartbeat["classified"] = {"stalls_over_cpu_threshold": len(detailed), "cpu_stall_threshold_s": self.cpu_stall_s,
                                   "classification": dict(collections.Counter(row["classification"] for row in detailed)),
                                   "gil_holders": dict(collections.Counter(row["holder"] for row in detailed if row["holder"]))}
        heartbeat["details"] = detailed[:_MAX_DETAILS]
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
                "heartbeat_stalls": [dict({"start": row[0], "end": row[1], "duration_s": row[1] - row[0]},
                                          **({"account": self.details[row[0]]} if row[0] in self.details else {}))
                                     for row in stalls_in if _overlaps(start, end, row[0], row[1])]})
        return rows
