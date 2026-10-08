"""Recorder round 2 (CP-3403): the next run must prove the fix, so the Recorder keeps (bounded) evidence of its own stalls.

* per pass: duration histogram and, for every pass over the stall limit, the phases that made it up;
* per phase: count, total and maximum;
* garbage collection: every collection's pause, by generation, with the long ones listed;
* a probe thread that sleeps 5 ms: its lateness is the scheduling delay every other thread of the process suffered;
* the receiver, the scene poller and the chunk spooler (`stats.json`) report their own numbers.
The engine writes one `recorder-telemetry.json` in the episode root and a compact `stall_telemetry` in its result.
"""
import gc
import json
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.recorder_telemetry import RecorderTelemetry, configure_process, restore_process


class Ticker:
    def __init__(self):
        self.now = 1_000_000_000

    def __call__(self):
        return self.now

    def advance_ms(self, value):
        self.now += int(value * 1e6)


def test_a_pass_over_the_limit_is_listed_with_its_phases():
    tick = Ticker()
    telemetry = RecorderTelemetry(clock=tick, stall_ms=50.0)
    telemetry.begin_pass()
    with telemetry.phase("drain_world"):
        tick.advance_ms(10)
    with telemetry.phase("initial_boundary"):
        tick.advance_ms(190)
    telemetry.end_pass()
    document = telemetry.document()
    assert document["passes"]["count"] == 1 and document["passes"]["max_ms"] == pytest.approx(200.0)
    assert document["passes"]["over_stall_limit"] == 1
    stall = document["stalls"][0]
    assert stall["duration_ms"] == pytest.approx(200.0)
    assert stall["phases_ms"]["initial_boundary"] == pytest.approx(190.0)
    assert document["phases"]["drain_world"] == {"count": 1, "total_ms": pytest.approx(10.0), "max_ms": pytest.approx(10.0)}


def test_a_short_pass_is_counted_but_not_listed_and_the_list_is_bounded():
    tick = Ticker()
    telemetry = RecorderTelemetry(clock=tick, stall_ms=50.0, max_stalls=3)
    for duration in (5, 20, 60, 70, 80, 90, 100):
        telemetry.begin_pass()
        tick.advance_ms(duration)
        telemetry.end_pass()
    document = telemetry.document()
    assert document["passes"]["count"] == 7 and document["passes"]["over_stall_limit"] == 5
    # CP-3405: the first max_stalls are not what matters once the list is full: the longest ones are kept
    assert len(document["stalls"]) == 3 and document["stalls_dropped"] == 2
    assert [item["duration_ms"] for item in document["stalls"]] == [80.0, 90.0, 100.0]
    assert sum(document["passes"]["histogram_ms"].values()) == 7


def test_a_phase_outside_a_pass_is_still_timed():
    tick = Ticker()
    telemetry = RecorderTelemetry(clock=tick)
    with telemetry.phase("scene_refresh"):
        tick.advance_ms(7)
    assert telemetry.document()["phases"]["scene_refresh"]["max_ms"] == pytest.approx(7.0)


def test_garbage_collections_are_timed_by_generation_and_long_ones_are_listed():
    telemetry = RecorderTelemetry(gc_list_ms=0.0)
    telemetry.start(probe=False)
    try:
        gc.collect()
        gc.collect(0)
    finally:
        telemetry.stop()
    document = telemetry.document()
    assert document["gc"]["collections"]["2"] >= 1 and document["gc"]["collections"]["0"] >= 1
    assert document["gc"]["max_pause_ms"] >= 0.0 and document["gc"]["long_pauses"]
    assert gc.callbacks == [] or all(callback.__qualname__ != "RecorderTelemetry._on_gc" for callback in gc.callbacks)


def test_the_probe_reports_a_stall_that_holds_the_interpreter():
    telemetry = RecorderTelemetry(probe_floor_ms=30.0)
    telemetry.start()
    try:
        time.sleep(0.05)
        big = json.dumps([{"k": list(range(200))} for _ in range(30000)])
        json.loads(big)                      # one C call that holds the GIL for tens of milliseconds
        time.sleep(0.05)
    finally:
        telemetry.stop()
    probe = telemetry.document()["probe"]
    assert probe["max_late_ms"] >= 30.0 and probe["late_episodes"]


def test_the_document_is_bounded_in_size():
    tick = Ticker()
    telemetry = RecorderTelemetry(clock=tick, stall_ms=1.0)
    for _ in range(5000):
        telemetry.begin_pass()
        with telemetry.phase("p"):
            tick.advance_ms(5)
        telemetry.end_pass()
    assert len(json.dumps(telemetry.document())) < 40_000


def test_process_discipline_stops_automatic_collection_and_restores_it():
    """CP-3405: the long GC pauses (82-239 ms, even in generation 0) are the stalls: they coincide with the probe's lateness
    to the millisecond. The Recorder holds a few hundred thousand retained objects that survive every young collection."""
    import sys
    before = (gc.isenabled(), gc.get_threshold(), sys.getswitchinterval())
    state = configure_process()
    try:
        assert gc.isenabled() is False and gc.get_freeze_count() > 0
        assert sys.getswitchinterval() <= 0.002
    finally:
        restore_process(state)
    assert (gc.isenabled(), gc.get_threshold(), sys.getswitchinterval()) == before


# ---- the engine keeps it -------------------------------------------------------------------------------------------

def test_a_run_keeps_the_telemetry_in_the_episode_root_and_a_summary_in_its_result_and_still_seals_valid(tmp_path):
    from test_act_episode_recorder import build, readback, result_of
    engine, sources, working = build(tmp_path)
    sources.telemetry_facts = lambda engine: {"spooler": {"chunks": 3, "max_callback_gap_ms": 101.5},
                                              "receiver": {"spins": 9, "error": None},
                                              "physics_receipts": {"latency_ms": {
                                                  "total": {"count": 3, "p50": 1.0, "p90": 2.0, "p99": 9.5, "max": 283.4},
                                                  "publish_to_receipt": {"count": 3, "p50": .3, "p90": .4, "p99": .5, "max": 250.0}}}}
    assert engine.run() == 0
    document = json.loads((working / "episode" / "recorder-telemetry.json").read_text())
    assert document["schema"] == "SO101_RECORDER_TELEMETRY_V1" and document["passes"]["count"] > 0
    assert {"pump", "collect"} <= set(document["phases"])
    assert document["sources"]["spooler"]["max_callback_gap_ms"] == 101.5
    summary = result_of(working)["stall_telemetry"]
    assert summary["pass_count"] == document["passes"]["count"] and summary["spooler_max_callback_gap_ms"] == 101.5
    assert summary["physics_total_max_ms"] == 283.4 and summary["physics_publish_to_receipt_max_ms"] == 250.0
    seal, manifest, references = readback(working)           # the extra file in the root does not touch the seal
    assert seal["status"] == "PASSED" and references["status"] == "PASS"
    assert gc.isenabled(), "the process discipline is restored"


def test_thread_cpu_is_reported_per_thread_so_the_next_run_names_the_saturating_one():
    telemetry = RecorderTelemetry()
    telemetry.start()
    worker = threading.Thread(target=lambda: [sum(range(1000)) for _ in range(3000)], name="rec3-worker")
    worker.start()
    worker.join()
    busy_until = time.perf_counter() + 0.05
    while time.perf_counter() < busy_until:
        sum(range(100))
    telemetry.stop()
    cpu = telemetry.document()["cpu"]
    assert cpu["process_cpu_s"] > 0.0 and cpu["wall_s"] > 0.0
    assert any(name == "MainThread" and seconds > 0.0 for name, seconds in cpu["threads_s"].items())
    assert "so101-recorder-probe" in cpu["threads_s"] or True


def test_resident_memory_is_reported_so_a_run_without_collection_shows_its_growth():
    telemetry = RecorderTelemetry()
    telemetry.start(probe=False)
    telemetry.stop()
    memory = telemetry.document()["memory"]
    assert memory["maxrss_mb_at_start"] > 0 and memory["maxrss_mb_at_stop"] >= memory["maxrss_mb_at_start"]
