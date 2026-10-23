"""Stall diagnostics (T0b-diag): GC callbacks, inference spans, heartbeat, the per-pair join and the episode wiring; no behaviour change."""

import gc
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.stall_diagnostics import StallMonitor
from so101_demo.adapters.act.rollout_ros import ThreadInferenceTransport

from test_act_rollout_episode import Ports, Session, Sink, _run


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now


def test_gc_collections_are_recorded_with_generation_times_and_counts():
    monitor = StallMonitor()
    monitor.start()
    try:
        cycle = []
        cycle.append(cycle)
        del cycle
        before = len(monitor.collections)
        gc.collect(2)
        gc.collect(0)
    finally:
        monitor.stop()
    rows = list(monitor.collections)[before:]
    assert [row[0] for row in rows][:2] == [2, 0]
    for generation, start, end, collected, uncollectable in rows:
        assert end >= start and collected >= 0 and uncollectable >= 0
    assert rows[0][3] >= 1                                   # the cycle was collected
    assert monitor._on_gc not in gc.callbacks                # stop removes the callback


def test_the_gc_callback_is_removed_and_start_stop_are_idempotent():
    monitor = StallMonitor()
    monitor.start(); monitor.start()
    assert gc.callbacks.count(monitor._on_gc) == 1
    monitor.stop(); monitor.stop()
    assert monitor._on_gc not in gc.callbacks


def test_a_late_wakeup_is_a_stall_and_a_prompt_one_is_not():
    clock = FakeClock()
    monitor = StallMonitor(monotonic=clock.monotonic, sleep=lambda s: setattr(clock, "now", clock.now + monitor_delay[0]))
    monitor_delay = [0.0011]
    now = monitor.beat(clock.now)
    assert not monitor.stalls and monitor.wakeups == 1
    monitor_delay[0] = 0.030
    start = now
    now = monitor.beat(now)
    assert list(monitor.stalls) == [(start, now)] and monitor.max_gap_s == pytest.approx(0.030)


def test_the_heartbeat_thread_runs_and_stops():
    monitor = StallMonitor()
    monitor.start()
    time.sleep(0.05)
    monitor.stop()
    assert monitor.wakeups > 5 and not any(t.name == "act-stall-heartbeat" and t.is_alive() for t in threading.enumerate())


def test_the_transport_reports_the_span_of_each_model_call_and_a_failing_sink_changes_nothing():
    spans = []
    transport = ThreadInferenceTransport(lambda observation: ((1.0,),), span_sink=lambda *a: spans.append(a))
    transport.send({"sequence": 1, "observation": {}})
    deadline = time.monotonic() + 5
    reply = None
    while reply is None and time.monotonic() < deadline:
        reply = transport.receive(); time.sleep(0.001)
    assert reply["actions"] == ((1.0,),) and len(spans) == 1 and spans[0][0] == "call" and spans[0][2] >= spans[0][1]
    transport.close()

    def broken(*_):
        raise RuntimeError("sink")

    transport = ThreadInferenceTransport(lambda observation: ((2.0,),), span_sink=broken)
    transport.send({"sequence": 1, "observation": {}})
    reply = None
    while reply is None:
        reply = transport.receive(); time.sleep(0.001)
    assert reply["actions"] == ((2.0,),)
    transport.close()


def test_the_policy_reports_pre_forward_and_post_spans(monkeypatch):
    import numpy as np

    from so101_demo.adapters.act import lerobot

    monkeypatch.setattr(lerobot, "_as_batch", lambda *a, **k: {})
    policy = SimpleNamespace(predict_action_chunk=lambda batch: np.zeros((1, 3, 6)))
    wrapped = lerobot.LerobotPolicy(policy, device="cpu")
    spans = []
    wrapped.span_sink = lambda *a: spans.append(a)
    actions = wrapped.infer({})
    assert len(actions) == 3 and [span[0] for span in spans] == ["pre", "forward", "post"]
    assert all(span[2] >= span[1] for span in spans) and spans[0][2] <= spans[1][1] and spans[1][2] <= spans[2][1]
    wrapped.span_sink = None
    assert wrapped.infer({}) == actions


def _pair(sequence, send, accept=None, check=None, sent_done=None, outcome="timeout", latency=None):
    return {"sequence": sequence, "outcome": outcome, "late_controller": "both" if outcome == "timeout" else None,
            "send_wall_s": {"arm": send, "gripper": send}, "accept_wall_s": {"arm": accept, "gripper": accept},
            "accept_latency_s": {"arm": latency, "gripper": latency}, "check_wall_s": check,
            "sent_done_wall_s": sent_done if sent_done is not None else send}


def test_the_summary_joins_each_failed_pair_with_gc_inference_and_stalls():
    monitor = StallMonitor()
    monitor.collections.extend([(2, 10.005, 10.040, 100, 0), (0, 12.000, 12.0002, 5, 0), (1, 20.000, 20.001, 1, 0)])
    monitor.spans.extend([("call", 10.000, 10.050), ("forward", 10.010, 10.045), ("call", 11.000, 11.020), ("forward", 11.005, 11.015)])
    monitor.stalls.extend([(10.006, 10.039), (30.0, 30.01)])
    pairs = [_pair(1, send=10.0, accept=10.045, check=10.020, sent_done=10.0, latency=0.045),
             _pair(2, send=11.0, accept=11.002, outcome="accepted", latency=0.002),
             _pair(3, send=15.0, accept=15.026, check=15.020, latency=0.026)]
    summary = monitor.summary(since_s=9.0, until_s=40.0, pairs=pairs)
    assert [row["sequence"] for row in summary["pairs"]] == [1, 3]
    first, third = summary["pairs"]
    assert [g["generation"] for g in first["gc"]] == [2] and {i["kind"] for i in first["inference"]} == {"call", "forward"}
    assert len(first["heartbeat_stalls"]) == 1
    assert third["gc"] == [] and third["inference"] == [] and third["heartbeat_stalls"] == []
    assert summary["gc"]["count"] == {"0": 1, "1": 1, "2": 1}
    assert [row["generation"] for row in summary["gc"]["long"]] == [2]       # only the 35 ms collection is longer than 5 ms
    assert summary["gc"]["duration_s"]["2"]["max"] == pytest.approx(0.035)
    assert summary["inference"]["count"] == 2 and summary["inference"]["duration_s"]["forward"]["n"] == 2
    assert summary["heartbeat"]["stalls"] == 2
    assert summary["coincidence"]["stalls"] == 2 and summary["coincidence"]["with_gc_generation_2"] == 1
    assert summary["coincidence"]["with_inference_call"] == 1 and summary["coincidence"]["with_none"] == 1


def test_an_accepted_pair_that_arrived_late_is_attributed_too():
    monitor = StallMonitor()
    monitor.stalls.append((10.01, 10.03))
    late = _pair(7, send=10.0, accept=10.028, outcome="accepted", latency=0.028)
    summary = monitor.summary(since_s=0.0, until_s=20.0, pairs=[late])
    assert len(summary["pairs"]) == 1 and len(summary["pairs"][0]["heartbeat_stalls"]) == 1


def test_an_after_common_start_pair_is_windowed_by_its_check_wall_time():
    monitor = StallMonitor()
    monitor.stalls.append((10.02, 10.06))
    pair = _pair(3, send=10.0, check=10.07, outcome="after_common_start", latency=None)
    summary = monitor.summary(since_s=0.0, until_s=20.0, pairs=[pair])
    assert summary["pairs"][0]["window"][1] == pytest.approx(10.07) and len(summary["pairs"][0]["heartbeat_stalls"]) == 1


def test_the_window_of_one_episode_excludes_earlier_records():
    monitor = StallMonitor()
    monitor.collections.extend([(2, 1.0, 1.1, 0, 0), (2, 50.0, 50.1, 0, 0)])
    monitor.stalls.extend([(2.0, 2.1), (51.0, 51.1)])
    summary = monitor.summary(since_s=40.0, until_s=60.0, pairs=[])
    assert summary["gc"]["count"] == {"2": 1} and summary["heartbeat"]["stalls"] == 1


class MonitoredPorts(Ports):
    def __init__(self, monitor, **kwargs):
        super().__init__(**kwargs)
        self.stall_monitor = monitor


def test_the_episode_carries_the_attribution_only_when_a_monitor_is_attached(monkeypatch):
    from test_act_goal_pair_telemetry import TelemetrySession, _open_with

    monkeypatch.setattr(MonitoredPorts, "open_session", _open_with(TelemetrySession))
    TelemetrySession.goal_pairs = lambda self: []
    try:
        monitor = StallMonitor()
        result = _run(MonitoredPorts(monitor), Sink())
        assert set(result["stall_attribution"]) >= {"gc", "inference", "heartbeat", "coincidence", "pairs"}
        assert result["stall_attribution"]["window"]["until_s"] >= result["stall_attribution"]["window"]["since_s"]
        plain = _run(Ports(), Sink())
        assert "stall_attribution" not in plain
    finally:
        del TelemetrySession.goal_pairs


def test_the_verdict_is_the_same_with_the_monitor(monkeypatch):
    plain = _run(Ports(), Sink())
    monitored = _run(MonitoredPorts(StallMonitor()), Sink())
    for key in ("verdict", "reason", "done", "status", "counts", "phases", "stop"):
        assert monitored[key] == plain[key]
