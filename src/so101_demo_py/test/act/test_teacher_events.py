"""B2 (plan R3 + R9.9): the Teacher publishes `SO101_TEACHER_EVENT`; a retired schema is refused; control never waits or raises."""
import json
import time

import pytest

import pick_place_driver as driver
from so101_demo.act import teacher_event_stream as stream_module
from so101_demo.core.domain import State

RETIRED_SCHEMA = "SO101_TEACHER_EVENT_V1"
TEACHER_EVENT_SCHEMA = "SO101_TEACHER_EVENT"
MOTION_STATES = ("MOVE_ABOVE_OBJECT", "DESCEND", "MICRO_LIFT", "LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE", "RETREAT")
GOAL_STATES = ("PREPARE_OPEN_GRIPPER", *MOTION_STATES[:1], "DESCEND", "CLOSE_GRIPPER", "MICRO_LIFT", "LIFT",
               "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE", "OPEN_GRIPPER", "RETREAT")


def document(schema=TEACHER_EVENT_SCHEMA, **changes):
    value = {"schema": schema, "seq": 1, "type": "phase_begin", "session_id": "s", "reset_epoch": 1,
             "attempt_id": "a", "sim_time_ns": 10, "monotonic_ns": 20, "payload": {}}
    value.update(changes)
    return json.dumps(value)


def test_the_stream_schema_is_current_and_native_receipt_types_are_gone():
    assert stream_module.STREAM_SCHEMA == TEACHER_EVENT_SCHEMA
    for gone in ("native_start", "native_dispatch", "sequence_complete"):
        assert gone not in stream_module.EVENT_TYPES
    for kept in ("reset_complete", "teacher_start_observation", "phase_begin", "phase_finish", "normal_stop",
                 "teacher_end_observation", "terminal", "scene_operation"):
        assert kept in stream_module.EVENT_TYPES


def test_an_event_decodes_and_a_retired_schema_event_is_rejected():
    assert stream_module.decode_event(document())["schema"] == TEACHER_EVENT_SCHEMA
    with pytest.raises(stream_module.TeacherEventError, match="TEACHER_EVENT_SCHEMA_UNKNOWN"):
        stream_module.decode_event(document(RETIRED_SCHEMA))


def test_the_consumer_monitor_rejects_a_retired_schema_event():
    identity = stream_module.StreamIdentity("s", 1, "a")
    monitor = stream_module.EventStreamMonitor(identity)
    with pytest.raises(stream_module.TeacherEventError, match="TEACHER_EVENT_SCHEMA_UNKNOWN"):
        monitor.accept(document(RETIRED_SCHEMA))
    assert monitor.accept(document()) is not None


def test_a_removed_event_type_is_rejected_in_the_current_envelope():
    for removed in ("native_dispatch", "native_start", "sequence_complete"):
        with pytest.raises(stream_module.TeacherEventError, match="TEACHER_EVENT_TYPE_UNKNOWN"):
            stream_module.decode_event(document(type=removed))


# ---- publisher: bounded, non-blocking, counted ------------------------------------------------------------------

def make_stream(publish, *, depth=None):
    identity = stream_module.StreamIdentity("s", 1, "a")
    kwargs = {} if depth is None else {"depth": depth}
    return stream_module.TeacherEventStream(identity, clock_ns=lambda: 5, publish=publish, start=False, **kwargs)


def test_the_queue_depth_is_64_and_an_overflow_counts_drops_without_blocking_or_raising():
    blocked = []
    stream = make_stream(lambda text: blocked.append(text) or time.sleep(60))  # a publisher that would block forever
    assert stream.snapshot()["queue_depth"] == 64
    began = time.monotonic()
    results = [stream.offer("phase_begin", {"state": "IDLE"}) for _ in range(100)]
    assert time.monotonic() - began < 1.0 and blocked == []  # the Teacher thread never waited for the publisher
    assert results.count(False) == 36
    snapshot = stream.snapshot()
    assert snapshot["offered"] == 100 and snapshot["dropped"] == 36 and snapshot["schema"] == TEACHER_EVENT_SCHEMA


def test_offer_never_raises_even_when_the_clock_or_the_payload_is_broken():
    identity = stream_module.StreamIdentity("s", 1, "a")

    def broken_clock():
        raise RuntimeError("clock")

    stream = stream_module.TeacherEventStream(identity, clock_ns=broken_clock, publish=lambda text: None, start=False)
    assert stream.offer("phase_begin", {"state": object()}) in (True, False)  # no exception either way


def test_a_failing_publish_is_counted_and_the_next_event_still_goes_out():
    sent = []

    def publish(text):
        if not sent:
            sent.append("failed")
            raise OSError("no subscriber")
        sent.append(text)

    stream = make_stream(publish)
    stream.offer("phase_begin", {"state": "IDLE"})
    stream.offer("phase_finish", {"state": "IDLE"})
    stream.pump()
    assert stream.snapshot()["publish_failures"] == 1 and stream.snapshot()["published"] == 1
    assert json.loads(sent[1])["schema"] == TEACHER_EVENT_SCHEMA


# ---- what the Teacher publishes ---------------------------------------------------------------------------------

class Recorder:
    """A stream double that keeps events and the interleaving with goal sends."""

    def __init__(self, world_holder):
        self.events, self.world_holder, self.raise_on = [], world_holder, None

    def offer(self, kind, payload=None):
        if self.raise_on == kind:
            raise RuntimeError("stream broken")
        world = self.world_holder.get("world")
        if world is not None:
            world.timeline.append(("event", kind, (payload or {}).get("state")))
        self.events.append((kind, payload or {}))
        return True

    def snapshot(self):
        return {"events": len(self.events)}

    def close(self, flush_timeout_s=1.0):
        return True


def run(tmp_path, recorder=None):
    holder = {}
    recorder = recorder or Recorder(holder)
    original_world = driver.World

    class World(original_world):
        def __init__(self):
            super().__init__()
            holder["world"] = self

    driver.World = World
    try:
        return driver.run(tmp_path, event_stream=recorder), recorder
    finally:
        driver.World = original_world


def test_every_state_publishes_phase_begin_and_finish_with_a_sim_stamp(tmp_path):
    out, recorder = run(tmp_path)
    assert out.result.status.value == "DONE"
    begins = [(p["state"], p) for kind, p in recorder.events if kind == "phase_begin"]
    finishes = [(p["state"], p) for kind, p in recorder.events if kind == "phase_finish"]
    states = [state.value for state in out.result.state_trace if state not in (State.IDLE, State.DONE)]
    assert [name for name, _ in begins] == states and [name for name, _ in finishes] == states
    for _name, payload in (*begins, *finishes):
        assert type(payload["sim_time_ns"]) is int and payload["sim_time_ns"] > 0
    assert all(payload["status"] == "SUCCEEDED" for _name, payload in finishes)


def test_a_goal_phase_begin_carries_the_sim_stamp_at_which_the_goal_was_sent(tmp_path):
    out, recorder = run(tmp_path)
    timeline = out.world.timeline
    for index, item in enumerate(timeline):
        if item[0] != "goal":
            continue
        previous = timeline[index - 1]
        assert previous[0] == "event" and previous[1] == "phase_begin", (previous, item)
    goal_begins = [p for kind, p in recorder.events if kind == "phase_begin" and p["goal_sent"]]
    assert [p["state"] for p in goal_begins] == list(GOAL_STATES)
    goals = [item for item in timeline if item[0] == "goal"]
    assert len(goals) == len(goal_begins)
    for begin, goal in zip(goal_begins, goals):
        assert 0 <= goal[2] - begin["sim_time_ns"] < 50_000_000  # the stamp is read immediately before the send
    assert [p["goal_kind"] for p in goal_begins[:2]] == ["gripper", "arm"]


def test_a_non_goal_phase_begin_says_no_goal_was_sent(tmp_path):
    _out, recorder = run(tmp_path)
    plain = [p for kind, p in recorder.events if kind == "phase_begin" and p["state"] == "WAIT_GRASP_STABLE"]
    assert plain and plain[0]["goal_sent"] is False and plain[0]["goal_kind"] is None


def test_the_normal_stop_event_carries_the_stop_proof_with_its_clocks(tmp_path, monkeypatch):
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    monkeypatch.setattr(RosDynamicMujocoExecution, "final_stop_proof_enabled", True)
    out, recorder = run(tmp_path)
    stops = [p for kind, p in recorder.events if kind == "normal_stop"]
    assert len(stops) == 1, "only the final boundary stop is published"
    proof = stops[0]["proof"]
    assert proof["trajectory_result"] == "SUCCEEDED"
    assert type(proof["stop_confirmed_wall_s"]) is float
    assert type(proof["publisher_sequence"]) is int and type(proof["simulation_step"]) is int
    clock = proof["source_clock"]
    assert clock["begin_monotonic_ns"] == clock["end_monotonic_ns"] >= round(proof["stop_confirmed_wall_s"] * 1e9)
    assert clock["sim_time_ns"] >= round(proof["sim_stamp_s"] * 1e9)


def test_a_stream_that_raises_never_reaches_control(tmp_path):
    holder = {}
    recorder = Recorder(holder)
    recorder.raise_on = "phase_begin"
    out, _ = run(tmp_path, recorder)
    assert out.result.status.value == "DONE"
