"""Diagnostic-only TEACHER_SOURCE_TRACE lines: where the Teacher's /clock stood when a scene apply named its source.

An apply request names a physics sample (its simulation time). The Recorder judges that sample against the simulation clock it
saw, so a Teacher whose own /clock handling lags shows up as a source that is far behind the clock. `ClockReceiptProbe` keeps
the newest /clock message this process received (raw subscription: two clock reads and one struct unpack per message, no
deserialization); `emit_source_trace` writes one line per apply request to stderr. Nothing here changes a request or can raise.
"""
from __future__ import annotations

import json
import sys
import time

from so101_demo.act.offline.probe_trace import header_stamp_ns

PREFIX = "TEACHER_SOURCE_TRACE"


class ClockReceiptProbe:
    def __init__(self, node, *, clock_type=None, qos=None, monotonic_ns=time.monotonic_ns, realtime_ns=time.time_ns) -> None:
        if clock_type is None:
            from rosgraph_msgs.msg import Clock as clock_type
        if qos is None:
            from rclpy.qos import qos_profile_clock as qos
        self._mono, self._real = monotonic_ns, realtime_ns
        self._latest = None
        self._count = 0
        self._subscription = node.create_subscription(clock_type, "/clock", self._on_clock, qos, raw=True)

    def _on_clock(self, data) -> None:
        sim_ns = header_stamp_ns(data)
        if sim_ns is None:
            return
        self._count += 1
        self._latest = (sim_ns, self._real(), self._mono())

    def latest(self):
        latest = self._latest
        if latest is None:
            return None
        return {"sim_ns": latest[0], "real_ns": latest[1], "mono_ns": latest[2], "count": self._count}


def emit_source_trace(node, probe, *, phase, state, source, stream=None, monotonic_ns=time.monotonic_ns,
                      realtime_ns=time.time_ns) -> None:
    """One `TEACHER_SOURCE_TRACE {json}` line for an apply request. Never raises."""
    try:
        now_mono, now_real = monotonic_ns(), realtime_ns()
        source = source or {}
        source_s = source.get("simulation_time_s")
        source_ns = None if source_s is None else round(float(source_s) * 1e9)
        try:
            node_clock_ns = int(node.get_clock().now().nanoseconds)
        except Exception:   # noqa: BLE001
            node_clock_ns = None
        clock = None if probe is None else probe.latest()
        document = {
            "phase": phase, "state": None if state is None else str(getattr(state, "value", state)),
            "request_mono_ns": now_mono, "request_real_ns": now_real,
            "source_sim_ns": source_ns, "source_step": source.get("simulation_step"),
            "source_sequence": source.get("publisher_sequence"), "node_clock_ns": node_clock_ns,
            "probe_clock_sim_ns": None if clock is None else clock["sim_ns"],
            "probe_clock_real_ns": None if clock is None else clock["real_ns"],
            "probe_clock_mono_ns": None if clock is None else clock["mono_ns"],
            "clock_cb_age_ms": None if clock is None else round((now_mono - clock["mono_ns"]) / 1e6, 3),
            "clock_count": None if clock is None else clock["count"],
            "source_behind_clock_ms": (None if clock is None or source_ns is None
                                       else round((clock["sim_ns"] - source_ns) / 1e6, 3)),
        }
        out = stream if stream is not None else sys.stderr
        out.write(PREFIX + " " + json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
        out.flush()
    except Exception:   # noqa: BLE001 - diagnostics never change a request
        pass
