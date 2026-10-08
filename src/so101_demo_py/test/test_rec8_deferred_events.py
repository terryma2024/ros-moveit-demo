"""Recorder round 8 (CP-3414): a Teacher event received before the capture started is bound after the start.

L2 on cOVHs9qE: the Teacher PASSED, the Recorder's only reason was RECORDER_NOT_READY_BEFORE_TEACHER_EVENT (`reset_complete`
received with the capture not yet started). The contract needs a verified reset boundary that the recording covers, not a
capture that is already running when the event is received (`episode_qc` boundary order verified_reset <= capture_start <= ...
on both clocks). So a non-scene event received early is held (bounded), the sequence is still checked on receipt, and the held
events are retained in order right after the start, bound by their own simulation stamps against the retained history.
The Teacher is never held or delayed: nothing here is on its path.
"""
import json
import subprocess
import sys
import time

import pytest

from so101_demo.act import episode_recorder_process as process
from so101_demo.act.episode_recorder_process import RC_INVALID, RC_VALID
from test_act_episode_recorder import STAMPS, assert_invalid_retained, build, readback, result_of, teacher_script
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)
from test_rec2_stall_replay import FRESH_READBACK, RealTimeSources, run_replay


def preload(engine, script, ticks=(-1,)):
    for tick in ticks:
        for text in script.pop(tick, ()):
            engine.on_event_text(text)


def start_after_passes(sources, engine, passes):
    """The capture becomes startable only after `passes` engine passes: the events arrive first."""
    counter = [0]
    original = sources.try_start

    def try_start(engine_):
        counter[0] += 1
        return original(engine_) if counter[0] > passes else None

    sources.try_start = try_start


# ---- the engine: held, bound, retained in order ----------------------------------------------------------------------------

def test_a_reset_complete_received_before_the_capture_started_is_valid_when_the_capture_covers_it(tmp_path):
    script = teacher_script(reset_sim_s=1.0, reset_tick=-1)
    engine, sources, working = build(tmp_path, script=script)
    preload(engine, script)
    start_after_passes(sources, engine, 3)
    assert engine.run() == RC_VALID, result_of(working)["reasons"]
    result = result_of(working)
    assert result["status"] == "VALID" and result["reasons"] == []
    assert result["event_stream"]["deferred_replayed"] == 1 and result["event_stream"]["deferred_first"][0] == "reset_complete"
    assert sources.events_seen[0] == "reset_complete", "retained first, in the order the Teacher sent it"
    seal, manifest, references = readback(working)
    assert seal["status"] == "PASSED" and references["status"] == "PASS"


def test_events_held_for_the_start_are_retained_in_the_order_received_before_later_ones(tmp_path):
    script = teacher_script(reset_sim_s=1.0, reset_tick=-1)
    early = script.pop(-1)
    engine, sources, working = build(tmp_path, script=script)
    for text in early:
        engine.on_event_text(text)
    start_after_passes(sources, engine, 2)
    assert engine.run() == RC_VALID
    assert sources.events_seen == ["reset_complete", "teacher_start_observation", "phase_begin", "phase_finish",
                                   "normal_stop", "teacher_end_observation", "terminal"]


def test_a_reset_complete_stamped_before_any_retained_data_is_invalid(tmp_path):
    script = teacher_script(reset_sim_s=0.05, reset_tick=-1)
    engine, sources, working = build(tmp_path, script=script)
    preload(engine, script)
    sources.retained_history_start_s = lambda engine_: 0.902   # a chunk of 50 steps ending at 1.0 s starts the history
    start_after_passes(sources, engine, 3)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="RECORDER_EVENT_BEFORE_RETAINED_HISTORY")


def test_a_sequence_gap_among_the_held_events_is_still_invalid(tmp_path):
    script = teacher_script(drop=(2,), reset_sim_s=1.0, reset_tick=-1)   # the start observation (seq 2) is lost
    engine, sources, working = build(tmp_path, script=script)
    preload(engine, script)
    start_after_passes(sources, engine, 3)
    assert engine.run() == RC_INVALID
    assert_invalid_retained(working, code="TEACHER_EVENT_SEQUENCE_GAP")


def test_the_held_events_are_bounded_and_an_overflow_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(process, "_DEFERRED_EVENTS_MAX", 1)
    script = teacher_script(reset_sim_s=1.0, reset_tick=-1)
    early = script.pop(-1)
    early += script.pop(0, [])[:1]   # the start observation too: two held events
    engine, sources, working = build(tmp_path, script=script)
    for text in early:
        engine.on_event_text(text)
    start_after_passes(sources, engine, 3)
    engine.run()
    assert_invalid_retained(working, code="RECORDER_DEFERRED_EVENT_OVERFLOW")


def test_a_capture_that_never_starts_keeps_the_not_ready_reason_and_the_held_count(tmp_path):
    script = teacher_script(reset_sim_s=1.0, reset_tick=-1)
    engine, sources, working = build(tmp_path, script=script)
    preload(engine, script, ticks=(-1, 0, 1, 2, 3, 4, 5))
    sources.try_start = lambda engine_: None
    ticks = iter(range(0, 10_000))
    engine.clock = lambda: next(ticks) * 1.0
    assert engine.run() == RC_INVALID
    result = assert_invalid_retained(working, code="RECORDER_NOT_READY_BEFORE_TEACHER_EVENT", sealed=False)
    entry = [item for item in result["reasons"] if "NOT_READY" in item["reason"]][0]
    assert entry["event_type"] == "reset_complete" and int(entry["held_events"]) >= 1


def test_the_start_gate_names_the_source_that_is_not_causal(frozen_scene):
    from test_act_live_physical_audit import provider
    source, values, at_s = provider(frozen_scene)
    assert source.ready(at_s) is True and source.unready_cause(at_s) == "association_or_window"
    source.controller_source = lambda at: None
    assert source.ready(at_s) is False and source.unready_cause(at_s) == "controller_state"
    source.physics_source = lambda at: None
    assert source.unready_cause(at_s) == "physics"


# ---- a real-rate replay with a late capture start --------------------------------------------------------------------------

class LateStartSources(RealTimeSources):
    """The reset boundary reaches the Recorder when the replay is 0.5 s of simulation old; the capture starts at 1.0."""

    def __init__(self, box, script, early, **kwargs):
        super().__init__(box, script, **kwargs)
        self.early, self.early_sent = list(early), 0.0

    def try_start(self, engine):
        if self.early and self.sim_now() >= 0.5:
            for text in self.early:
                engine.on_event_text(text)
            self.early_sent, self.early = time.monotonic(), []
        return super().try_start(engine)


def late_start_replay(tmp_path, *, reset_sim_s):
    script = teacher_script(reset_sim_s=reset_sim_s, reset_tick=-1)
    early = script.pop(-1)
    return run_replay(tmp_path, served_by_receiver=True, script=script, sources_cls=LateStartSources, early=early)


def test_a_real_rate_replay_with_a_late_capture_start_is_valid_and_reads_back_in_a_fresh_process(tmp_path):
    engine, sources, working = late_start_replay(tmp_path, reset_sim_s=0.5)
    code = engine.run()
    result = result_of(working)
    assert sources.early_sent and not sources.early, "the reset boundary was received before the capture started"
    assert code == RC_VALID and result["status"] == "VALID", result["reasons"]
    assert result["event_stream"]["deferred_replayed"] == 1
    seal, manifest, references = readback(working)
    assert seal["status"] == "PASSED" and references["status"] == "PASS"
    events = [json.loads(line) for line in (working / "episode/audit/events.jsonl").read_text().splitlines()]
    done = subprocess.run([sys.executable, "-c", FRESH_READBACK, str(working)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    report = json.loads(done.stdout.strip().splitlines()[-1])
    assert report["status"] == "PASSED" and report["records"] >= 2
    assert manifest["window"]["collection_start_s"] >= 0.5, "the capture started after the reset boundary it covers"


def test_the_same_late_replay_with_a_reset_older_than_the_retained_history_is_invalid(tmp_path):
    engine, sources, working = late_start_replay(tmp_path, reset_sim_s=0.05)
    assert engine.run() == RC_INVALID
    assert any("RECORDER_EVENT_BEFORE_RETAINED_HISTORY" in item["reason"] for item in result_of(working)["reasons"])
