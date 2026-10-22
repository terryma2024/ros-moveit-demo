"""Read-only diagnostics for the controller goal pair: host load, latency statistics and the per-episode summary.

Nothing here is read by the control path. `ActExecutionAdapter` records a `goal_pair` sub-object for every submission and
calls these helpers inside a guard, so a failure in this module can never change what is sent or the verdict.
"""

import os
import time

CONTROLLERS = ("arm", "gripper")


def percentile(sorted_values, q):
    """The q-th percentile (0..100) of an ascending list, by linear interpolation between closest ranks."""

    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * q / 100.0
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def latency_stats(values):
    ordered = sorted(float(value) for value in values)
    return {"n": len(ordered), "p50": percentile(ordered, 50), "p95": percentile(ordered, 95),
            "p99": percentile(ordered, 99), "max": ordered[-1] if ordered else None}


class LoadSampler:
    """Process CPU time and the host load average, refreshed at most once per `interval_s` (a cached sample is returned
    in between, with its age)."""

    def __init__(self, *, clock=time.monotonic, cpu=time.process_time, load=os.getloadavg, interval_s=1.0):
        self._clock, self._cpu, self._load, self.interval_s = clock, cpu, load, interval_s
        self._base_wall, self._base_cpu = clock(), cpu()
        self._taken_wall = None
        self._sample = None

    def sample(self):
        now = self._clock()
        if self._sample is None or now - self._taken_wall >= self.interval_s:
            cpu = self._cpu()
            try:
                loadavg = [float(value) for value in self._load()]
            except (OSError, AttributeError):
                loadavg = None
            self._sample = {"cpu_process_s": cpu, "cpu_delta_s": cpu - self._base_cpu,
                            "cpu_delta_wall_s": now - self._base_wall, "loadavg": loadavg}
            self._base_wall, self._base_cpu, self._taken_wall = now, cpu, now
        return dict(self._sample, sample_age_s=now - self._taken_wall)


def late_controllers(pair):
    late = pair.get("late_controller")
    return list(CONTROLLERS) if late == "both" else ([late] if late in CONTROLLERS else [])


def summarize_goal_pairs(pairs, *, accept_timeout_s):
    """Acceptance latency per controller (callback time minus send time, late arrivals included), the timeout count and
    the latencies at which the accepts of timed-out pairs arrived after all."""

    latencies = {name: [] for name in CONTROLLERS}
    late_arrivals, unresolved = [], 0
    for pair in pairs:
        for name in CONTROLLERS:
            value = (pair.get("accept_latency_s") or {}).get(name)
            if value is not None:
                latencies[name].append(value)
        if pair.get("outcome") == "timeout":
            arrived = pair.get("late_arrival_latency_s") or {}
            for name in late_controllers(pair):
                if arrived.get(name) is None:
                    unresolved += 1
                else:
                    late_arrivals.append({"sequence": pair.get("sequence"), "controller": name,
                                          "latency_s": arrived[name],
                                          "accept_thread": (pair.get("accept_thread") or {}).get(name)})
    return {"pairs": len(pairs), "timeouts": sum(1 for pair in pairs if pair.get("outcome") == "timeout"),
            "rejected": sum(1 for pair in pairs if pair.get("outcome") == "rejected"),
            "accept_timeout_s": accept_timeout_s,
            "accept_latency_s": {name: latency_stats(latencies[name]) for name in CONTROLLERS},
            "late_arrivals": late_arrivals,
            "late_arrival_latencies_s": [row["latency_s"] for row in late_arrivals],
            "late_arrivals_unresolved": unresolved}
