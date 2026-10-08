"""Bounded stall telemetry of the Recorder process (observation only; nothing here can fail a recording).

The L2 run showed main-node receipts up to 250 ms late five times in 12 s and nothing retained said why. This module keeps,
in bounded space: per-pass durations (histogram, and for every pass over the stall limit the phases that made it up), the
cost of every phase, every garbage collection (generation and pause), and the lateness of a probe thread that asks the
interpreter for 5 ms of attention (its lateness is the delay every thread of the process suffered, whatever held the GIL).
"""

from __future__ import annotations

import gc
import os
import sys
import threading
import time
from contextlib import contextmanager

_BUCKETS_MS = (5, 10, 20, 50, 100, 200)
_SWITCH_INTERVAL_S = 0.001


def configure_process() -> dict:
    """Recorder-process discipline: imports are frozen, automatic collection is off, threads switch at 1 ms.

    L2 rerun: the stalls (82-239 ms, in generation 0) are garbage collections: every one coincides with the probe thread's
    lateness to the millisecond. The retained rings (raw samples, world records, frames) hold hundreds of thousands of
    container objects that survive every young pass, so a pass over them stops every thread for 100-240 ms and delays every
    receipt. The Recorder lives for one bounded recording and creates no cyclic garbage worth collecting (its memory is reported in
    the telemetry); the interpreter collects once, at the end."""
    previous = {"enabled": gc.isenabled(), "threshold": gc.get_threshold(), "switch": sys.getswitchinterval()}
    gc.collect()
    gc.freeze()
    gc.disable()
    sys.setswitchinterval(_SWITCH_INTERVAL_S)
    return previous


def restore_process(previous: dict) -> None:
    gc.set_threshold(*previous["threshold"])
    gc.unfreeze()
    if previous["enabled"]:
        gc.enable()
    sys.setswitchinterval(previous["switch"])


class RecorderTelemetry:
    def __init__(self, *, clock=time.monotonic_ns, stall_ms: float = 50.0, max_stalls: int = 64,
                 gc_list_ms: float = 5.0, max_gc_listed: int = 32, probe_floor_ms: float = 20.0,
                 max_probe_listed: int = 32, probe_period_s: float = 0.005) -> None:
        self._clock = clock
        self._stall_ns = int(stall_ms * 1e6)
        self._max_stalls, self._gc_list_ms, self._max_gc = max_stalls, gc_list_ms, max_gc_listed
        self._probe_floor_ms, self._max_probe, self._probe_period_s = probe_floor_ms, max_probe_listed, probe_period_s
        self._lock = threading.Lock()
        self._phases: dict = {}
        self._pass_began = None
        self._pass_phases: list = []
        self._passes = {"count": 0, "max_ns": 0, "over": 0, "histogram": {f"<{b}": 0 for b in _BUCKETS_MS}}
        self._passes["histogram"][f">={_BUCKETS_MS[-1]}"] = 0
        self._stalls: list = []
        self._stalls_dropped = 0
        self._gc = {"collections": {"0": 0, "1": 0, "2": 0}, "max_ns": 0, "total_ns": 0, "long": []}
        self._gc_began = None
        self._probe = {"samples": 0, "max_late_ms": 0.0, "episodes": [], "dropped": 0}
        self._probe_stop = threading.Event()
        self._probe_thread = None
        self._gc_installed = False
        self._started_wall = None
        self._cpu = {}
        self._rss = {"maxrss_mb_at_start": 0.0, "maxrss_mb_at_stop": 0.0}

    # ---- passes and phases -------------------------------------------------------------------------------------

    def begin_pass(self) -> None:
        self._pass_began = self._clock()
        self._pass_phases = []

    @contextmanager
    def phase(self, name: str):
        began = self._clock()
        try:
            yield
        finally:
            elapsed = self._clock() - began
            with self._lock:
                block = self._phases.setdefault(name, [0, 0, 0])
                block[0] += 1
                block[1] += elapsed
                block[2] = max(block[2], elapsed)
            if self._pass_began is not None:
                self._pass_phases.append((name, elapsed))

    def end_pass(self) -> None:
        began, self._pass_began = self._pass_began, None
        if began is None:
            return
        now = self._clock()
        elapsed = now - began
        with self._lock:
            passes = self._passes
            passes["count"] += 1
            passes["max_ns"] = max(passes["max_ns"], elapsed)
            ms = elapsed / 1e6
            for bound in _BUCKETS_MS:
                if ms < bound:
                    passes["histogram"][f"<{bound}"] += 1
                    break
            else:
                passes["histogram"][f">={_BUCKETS_MS[-1]}"] += 1
            if elapsed >= self._stall_ns:
                passes["over"] += 1
                phases: dict = {}
                for name, spent in self._pass_phases:
                    phases[name] = round(phases.get(name, 0.0) + spent / 1e6, 3)
                entry = {"monotonic_ns": began, "duration_ms": round(ms, 3), "phases_ms": phases}
                if len(self._stalls) < self._max_stalls:
                    self._stalls.append(entry)
                else:
                    # full: the longest stalls are the evidence, not the first ones
                    shortest = min(range(len(self._stalls)), key=lambda index: self._stalls[index]["duration_ms"])
                    if entry["duration_ms"] > self._stalls[shortest]["duration_ms"]:
                        self._stalls[shortest] = entry
                    self._stalls_dropped += 1

    # ---- garbage collection and the probe --------------------------------------------------------------------------

    def _on_gc(self, phase, info) -> None:
        if phase == "start":
            self._gc_began = time.perf_counter_ns()
            return
        began, self._gc_began = self._gc_began, None
        if began is None:
            return
        elapsed = time.perf_counter_ns() - began
        generation = str(info.get("generation", 2))
        with self._lock:
            self._gc["collections"][generation] = self._gc["collections"].get(generation, 0) + 1
            self._gc["max_ns"] = max(self._gc["max_ns"], elapsed)
            self._gc["total_ns"] += elapsed
            if elapsed / 1e6 >= self._gc_list_ms and len(self._gc["long"]) < self._max_gc:
                self._gc["long"].append({"monotonic_ns": time.monotonic_ns(), "generation": int(generation),
                                         "pause_ms": round(elapsed / 1e6, 3), "collected": info.get("collected")})

    def _probe_loop(self) -> None:
        period = self._probe_period_s
        while not self._probe_stop.is_set():
            began = time.perf_counter()
            time.sleep(period)
            late_ms = (time.perf_counter() - began - period) * 1e3
            with self._lock:
                self._probe["samples"] += 1
                self._probe["max_late_ms"] = max(self._probe["max_late_ms"], late_ms)
                if late_ms >= self._probe_floor_ms:
                    if len(self._probe["episodes"]) < self._max_probe:
                        self._probe["episodes"].append({"monotonic_ns": time.monotonic_ns(),
                                                        "late_ms": round(late_ms, 3)})
                    else:
                        self._probe["dropped"] += 1

    @staticmethod
    def _thread_cpu() -> dict:
        """CPU seconds per thread of this process, from /proc (names from `threading`); {} where /proc is absent."""
        cpu = {}
        try:
            ticks = os.sysconf("SC_CLK_TCK")
            for thread in threading.enumerate():
                native = getattr(thread, "native_id", None)
                if native is None:
                    continue
                with open(f"/proc/self/task/{native}/stat") as stream:
                    fields = stream.read().rsplit(")", 1)[1].split()
                seconds = (int(fields[11]) + int(fields[12])) / ticks
                name = thread.name
                cpu[name] = round(cpu.get(name, 0.0) + seconds, 3)
        except (OSError, ValueError, IndexError):
            return cpu
        return cpu

    @staticmethod
    def _maxrss_mb() -> float:
        try:
            import resource
            return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
        except Exception:
            return 0.0

    def start(self, *, probe: bool = True) -> None:
        self._started_wall = time.monotonic()
        self._rss["maxrss_mb_at_start"] = self._maxrss_mb()
        if not self._gc_installed:
            gc.callbacks.append(self._on_gc)
            self._gc_installed = True
        if probe and self._probe_thread is None:
            self._probe_stop.clear()
            self._probe_thread = threading.Thread(target=self._probe_loop, name="so101-recorder-probe", daemon=True)
            self._probe_thread.start()

    def snapshot_cpu(self) -> None:
        """Per-thread CPU now (call before the sources close: their threads end then)."""
        if self._started_wall is not None:
            self._cpu = {"wall_s": round(time.monotonic() - self._started_wall, 3),
                         "process_cpu_s": round(time.process_time(), 3), "threads_s": self._thread_cpu()}

    def stop(self) -> None:
        self._rss["maxrss_mb_at_stop"] = self._maxrss_mb()
        if not self._cpu:
            self.snapshot_cpu()
        if self._gc_installed:
            try:
                gc.callbacks.remove(self._on_gc)
            except ValueError:
                pass
            self._gc_installed = False
        self._probe_stop.set()
        thread, self._probe_thread = self._probe_thread, None
        if thread is not None:
            thread.join(1.0)

    # ---- the document ------------------------------------------------------------------------------------------------

    def document(self) -> dict:
        with self._lock:
            passes = self._passes
            return {
                "schema": "SO101_RECORDER_TELEMETRY_V1",
                "passes": {"count": passes["count"], "max_ms": round(passes["max_ns"] / 1e6, 3),
                           "over_stall_limit": passes["over"], "stall_limit_ms": self._stall_ns / 1e6,
                           "histogram_ms": dict(passes["histogram"])},
                "stalls": sorted(self._stalls, key=lambda item: item["monotonic_ns"]),
                "stalls_dropped": self._stalls_dropped,
                "phases": {name: {"count": block[0], "total_ms": round(block[1] / 1e6, 3),
                                  "max_ms": round(block[2] / 1e6, 3)} for name, block in sorted(self._phases.items())},
                "gc": {"collections": dict(self._gc["collections"]), "max_pause_ms": round(self._gc["max_ns"] / 1e6, 3),
                       "total_pause_ms": round(self._gc["total_ns"] / 1e6, 3), "long_pauses": list(self._gc["long"]),
                       "threshold": list(gc.get_threshold()), "enabled": gc.isenabled(),
                       "frozen_objects": gc.get_freeze_count()},
                "memory": dict(self._rss),
                "cpu": dict(self._cpu) if self._cpu else {"wall_s": 0.0, "process_cpu_s": 0.0, "threads_s": {}},
                "probe": {"samples": self._probe["samples"], "max_late_ms": round(self._probe["max_late_ms"], 3),
                          "floor_ms": self._probe_floor_ms, "late_episodes": list(self._probe["episodes"]),
                          "late_episodes_dropped": self._probe["dropped"]},
            }

    def summary(self) -> dict:
        document = self.document()
        return {"pass_count": document["passes"]["count"], "pass_max_ms": document["passes"]["max_ms"],
                "passes_over_stall_limit": document["passes"]["over_stall_limit"],
                "gc_max_pause_ms": document["gc"]["max_pause_ms"], "probe_max_late_ms": document["probe"]["max_late_ms"]}
