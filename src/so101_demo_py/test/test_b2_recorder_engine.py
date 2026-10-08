"""B2: the offline engine turns a missing, foreign, V1 or gapped Teacher event into an INVALID verdict."""
import json
from types import SimpleNamespace

import pytest

import time

from so101_demo.act.offline.engine import OfflineEngine
from so101_demo.act.teacher_event_stream import StreamIdentity

V2 = "SO101_TEACHER_EVENT_V2"
IDENTITY = StreamIdentity("s", 1, "a")


class Sources:
    def __init__(self):
        self.seen = []

    def on_teacher_event(self, engine, event):
        self.seen.append(event["type"])


def make_engine(tmp_path):
    episode = SimpleNamespace(capture=SimpleNamespace(started=True))
    policy = {"event_inbox_capacity": 64, "poll_s": 0.001, "finish_budget_s": 1.0}
    engine = OfflineEngine(episode=episode, sources=Sources(), policy=policy, identity=IDENTITY,
                           result_file=tmp_path / "result.json", clock=time.monotonic, sleep=time.sleep)
    engine.ready = True
    return engine


def text(seq, type_, payload=None, *, schema=V2, attempt="a"):
    return json.dumps({"schema": schema, "seq": seq, "type": type_, "session_id": "s", "reset_epoch": 1,
                       "attempt_id": attempt, "sim_time_ns": seq * 1000, "monotonic_ns": seq * 1000,
                       "payload": payload or {}})


GOAL_BEGIN = {"state": "PREPARE_OPEN_GRIPPER", "sim_time_ns": 1, "monotonic_ns": 1, "goal_sent": True, "goal_kind": "gripper"}
PLAIN_BEGIN = {"state": "WAIT_GRASP_STABLE", "sim_time_ns": 1, "monotonic_ns": 1, "goal_sent": False, "goal_kind": None}


def feed(engine, *texts):
    for item in texts:
        engine._handle_text(item)


def reasons(engine):
    return [item["reason"] for item in engine.invalid]


def complete(engine):
    feed(engine, text(1, "reset_complete", {"simulation_step": 1}), text(2, "phase_begin", GOAL_BEGIN),
         text(3, "normal_stop", {"proof": {"stop_confirmed_wall_s": 1.0}}), text(4, "terminal", {"status": "DONE"}))


def test_a_complete_v2_run_has_no_missing_event(tmp_path):
    engine = make_engine(tmp_path)
    complete(engine)
    engine.require_teacher_events()
    assert reasons(engine) == []


@pytest.mark.parametrize("missing,reason", [("reset_complete", "RECORDER_EVENT_MISSING: reset_complete"),
                                            ("phase_begin", "RECORDER_EVENT_MISSING: phase_begin"),
                                            ("normal_stop", "RECORDER_EVENT_MISSING: normal_stop")])
def test_a_missing_required_event_is_invalid(tmp_path, missing, reason):
    engine = make_engine(tmp_path)
    events = [("reset_complete", {"simulation_step": 1}), ("phase_begin", GOAL_BEGIN),
              ("normal_stop", {"proof": {"stop_confirmed_wall_s": 1.0}}), ("terminal", {"status": "DONE"})]
    feed(engine, *[text(index + 1, kind, payload) for index, (kind, payload) in
                   enumerate([item for item in events if item[0] != missing])])
    engine.require_teacher_events()
    assert reason in reasons(engine)


def test_a_phase_begin_that_sent_no_goal_is_not_the_first_command(tmp_path):
    engine = make_engine(tmp_path)
    feed(engine, text(1, "reset_complete"), text(2, "phase_begin", PLAIN_BEGIN),
         text(3, "normal_stop", {"proof": {}}), text(4, "terminal", {}))
    engine.require_teacher_events()
    assert "RECORDER_EVENT_MISSING: phase_begin" in reasons(engine)


def test_a_v1_event_is_rejected_and_breaks_the_stream(tmp_path):
    engine = make_engine(tmp_path)
    feed(engine, text(1, "reset_complete", schema="SO101_TEACHER_EVENT_V1"))
    assert "TEACHER_EVENT_SCHEMA_UNKNOWN" in reasons(engine) and engine._stream_broken
    assert engine.sources.seen == []


def test_a_removed_v1_event_type_is_rejected(tmp_path):
    engine = make_engine(tmp_path)
    feed(engine, text(1, "native_dispatch", {"goal_id": "g"}))
    assert "TEACHER_EVENT_TYPE_UNKNOWN" in reasons(engine)


def test_an_event_sequence_gap_is_invalid(tmp_path):
    engine = make_engine(tmp_path)
    feed(engine, text(1, "reset_complete"), text(3, "phase_begin", GOAL_BEGIN))
    assert "TEACHER_EVENT_SEQUENCE_GAP" in reasons(engine)


def test_every_retained_type_reaches_the_sources_in_order(tmp_path):
    engine = make_engine(tmp_path)
    complete(engine)
    assert engine.sources.seen == ["reset_complete", "phase_begin", "normal_stop", "terminal"]


def test_the_engine_counts_every_accepted_event_for_the_sealed_summary(tmp_path):
    engine = make_engine(tmp_path)
    complete(engine)
    feed(engine)
    summary = engine.event_summary()
    assert summary == {"schema": V2, "accepted": 4, "last_seq": 4,
                       "types": {"reset_complete": 1, "phase_begin": 1, "normal_stop": 1, "terminal": 1}}
