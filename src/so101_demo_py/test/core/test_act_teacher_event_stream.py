"""The Teacher event stream on /so101/teacher/events (Phase A4a): schema, non-blocking publication, Teacher isolation.

The Teacher thread only offers events to a bounded queue. A publisher thread drains it and may be absent, raising or
stuck without changing one Teacher action or result.
"""

import copy
import json
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_event_stream import (
    EVENT_TYPES, STREAM_SCHEMA, STREAM_TOPIC, EventStreamMonitor, StreamEventSink, StreamIdentity,
    TeacherEventError, TeacherEventStream, decode_event)
from so101_demo.core.domain import ActionStatus, State
from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
from test_act_teacher_data_decoupling import (CONTEXT, FORBIDDEN, PLACE_POSE, _connection, _teacher_view, _workflow_states)
from test_dynamic_teacher_result import START, _adapter, _end_pose, _end_sampler, _sample

IDENTITY = StreamIdentity("s", 3, "a")


def _stream(published, **kwargs):
    return TeacherEventStream(IDENTITY, clock_ns=lambda: 2_000_000_000, publish=published.append, start=False, **kwargs)


# ---- schema ---------------------------------------------------------------------------------------------------

def test_the_stream_names_the_topic_schema_and_every_event_type_the_design_lists():
    assert STREAM_TOPIC == "/so101/teacher/events"
    assert STREAM_SCHEMA == "SO101_TEACHER_EVENT"
    assert set(EVENT_TYPES) == {
        "reset_complete", "teacher_start_observation", "phase_begin", "phase_finish", "normal_stop",
        "teacher_end_observation", "terminal", "scene_operation"}


def test_every_event_round_trips_through_json_with_a_monotonic_seq_and_the_attempt_identity():
    published = []
    stream = _stream(published)
    for index, kind in enumerate(EVENT_TYPES):
        assert stream.offer(kind, {"n": index, "nested": {"values": [1.5, 2]}}) is True
    assert stream.pump() == len(EVENT_TYPES)
    events = [decode_event(text) for text in published]
    assert [event["seq"] for event in events] == list(range(1, len(EVENT_TYPES) + 1))
    assert [event["type"] for event in events] == list(EVENT_TYPES)
    for index, event in enumerate(events):
        assert set(event) == {"schema", "seq", "session_id", "reset_epoch", "attempt_id", "type", "sim_time_ns",
                              "monotonic_ns", "payload"}
        assert (event["session_id"], event["reset_epoch"], event["attempt_id"]) == ("s", 3, "a")
        assert event["schema"] == STREAM_SCHEMA and event["sim_time_ns"] == 2_000_000_000
        assert event["payload"] == {"n": index, "nested": {"values": [1.5, 2]}}
    monotonic = [event["monotonic_ns"] for event in events]
    assert monotonic == sorted(monotonic)
    # the text itself is deterministic canonical JSON and parses back to the same document
    assert all(json.loads(text) == decode_event(text) for text in published)


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.update(schema="SO101_TEACHER_EVENT_V0"), "TEACHER_EVENT_SCHEMA_UNKNOWN"),
    (lambda d: d.update(type="unknown_event"), "TEACHER_EVENT_TYPE_UNKNOWN"),
    (lambda d: d.update(extra=1), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.pop("payload"), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.update(seq=0), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.update(seq=True), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.update(sim_time_ns=None), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.update(attempt_id=""), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.update(reset_epoch=-1), "TEACHER_EVENT_MALFORMED"),
    (lambda d: d.update(payload=[1]), "TEACHER_EVENT_MALFORMED"),
])
def test_the_consumer_refuses_a_document_that_is_not_the_closed_schema(mutate, code):
    published = []
    stream = _stream(published)
    stream.offer("phase_begin", {"phase": "X"})
    stream.pump()
    document = json.loads(published[0])
    mutate(document)
    with pytest.raises(TeacherEventError, match=code):
        decode_event(json.dumps(document))


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"seq": NaN}', "null"])
def test_the_consumer_refuses_text_that_is_not_a_json_object(text):
    with pytest.raises(TeacherEventError, match="TEACHER_EVENT_MALFORMED"):
        decode_event(text)


def test_a_payload_json_cannot_represent_is_a_counted_publish_failure_never_an_exception():
    published = []
    stream = _stream(published)
    assert stream.offer("phase_begin", {"value": float("nan")}) is True   # offering never inspects the payload
    assert stream.offer("phase_finish", {"ok": 1}) is True
    stream.pump()
    snapshot = stream.snapshot()
    assert snapshot["publish_failures"] == 1 and snapshot["published"] == 1
    assert decode_event(published[0])["seq"] == 2, "the failed event consumed seq 1, which the consumer sees as a gap"


# ---- the Teacher thread never waits ----------------------------------------------------------------------------

def test_offering_without_any_subscriber_or_publisher_thread_never_blocks_and_never_raises():
    stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 1, publish=lambda text: None, start=False)
    began = time.monotonic()
    results = [stream.offer("phase_begin", {"n": index}) for index in range(500)]
    assert time.monotonic() - began < 0.5
    assert results.count(True) == 64 and results.count(False) == 436, "the bounded queue drops, it does not grow"
    assert stream.snapshot()["dropped"] == 436 and stream.snapshot()["queue_depth"] == 64


def test_a_publisher_that_blocks_forever_cannot_stall_the_offering_thread():
    release = threading.Event()
    entered = threading.Event()

    def stuck(text):
        entered.set()
        release.wait(30)

    stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 1, publish=stuck, poll_s=0.001)
    try:
        stream.offer("phase_begin", {"n": 0})
        assert entered.wait(5.0)
        began = time.monotonic()
        offered = [stream.offer("phase_begin", {"n": index}) for index in range(300)]
        assert time.monotonic() - began < 0.5
        assert offered.count(False) > 0, "events beyond the bounded depth are dropped and counted"
        assert stream.snapshot()["dropped"] == offered.count(False)
        close_began = time.monotonic()
        stream.close(flush_timeout_s=0.2)
        assert time.monotonic() - close_began < 2.0, "closing abandons a stuck publisher instead of waiting for it"
    finally:
        release.set()


def test_a_publisher_that_raises_is_counted_and_never_propagates_and_the_last_published_seq_stays_honest():
    published = []

    def flaky(text):
        if decode_event(text)["seq"] == 2:
            raise RuntimeError("DDS_WRITE_REFUSED")
        published.append(text)

    stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 1, publish=flaky, start=False)
    for index in range(4):
        stream.offer("phase_begin", {"n": index})
    assert stream.pump() == 4
    snapshot = stream.snapshot()
    assert snapshot == {**snapshot, "published": 3, "publish_failures": 1, "dropped": 0, "last_published_seq": 4,
                        "offered": 4}
    assert "DDS_WRITE_REFUSED" in snapshot["last_error"]
    assert [decode_event(text)["seq"] for text in published] == [1, 3, 4]


def test_the_threaded_publisher_delivers_in_order_and_flushes_on_close():
    published = []
    stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 1, publish=published.append, poll_s=0.001)
    for index in range(20):
        stream.offer("phase_begin", {"n": index})
    stream.close(flush_timeout_s=2.0)
    assert [decode_event(text)["seq"] for text in published] == list(range(1, 21))
    assert stream.snapshot()["last_published_seq"] == 20


def test_a_clock_that_fails_never_raises_into_the_offering_thread():
    def broken():
        raise RuntimeError("NO_CLOCK")

    stream = TeacherEventStream(IDENTITY, clock_ns=broken, publish=lambda text: None, start=False)
    assert stream.offer("phase_begin", {}) is True
    stream.pump()
    assert stream.snapshot()["publish_failures"] == 1


# ---- the sink in front of the stream (the Teacher keeps no event copy of its own) --------------------------------

def test_the_sink_forwards_the_three_in_process_kinds_and_keeps_no_copy():
    published = []
    stream = _stream(published)
    sink = StreamEventSink(stream)
    kinds = ["phase_begin", "phase_finish", "normal_stop"]
    for index, kind in enumerate(kinds):
        assert sink.publish(kind, {"n": index}) is True
    assert not hasattr(sink, "drain") and not hasattr(sink, "attach")
    stream.pump()
    assert [decode_event(text)["type"] for text in published] == kinds
    assert sink.publish("terminal", {}) is False  # not one of the three: the execution emits it through the stream itself


def test_the_sink_survives_a_stream_that_raises_and_without_a_stream_accepts_nothing():
    class Broken:
        def offer(self, *args):
            raise RuntimeError("STREAM_BROKEN")

    assert StreamEventSink(Broken()).publish("phase_begin", {"n": 1}) is False
    assert StreamEventSink(None).publish("phase_begin", {"n": 1}) is False


# ---- the consumer's sequence monitor ----------------------------------------------------------------------------

def _texts(count, *, identity=IDENTITY):
    published = []
    stream = TeacherEventStream(identity, clock_ns=lambda: 5, publish=published.append, start=False)
    for index in range(count):
        stream.offer("phase_begin", {"n": index})
    stream.pump()
    return published


def test_the_monitor_accepts_a_gapless_stream_and_ignores_another_attempts_events():
    monitor = EventStreamMonitor(IDENTITY)
    other = _texts(2, identity=StreamIdentity("s", 3, "other-attempt"))
    own = _texts(3)
    accepted = [monitor.accept(own[0]), monitor.accept(other[0]), monitor.accept(own[1]), monitor.accept(own[2])]
    assert [None if event is None else event["seq"] for event in accepted] == [1, None, 2, 3]
    assert monitor.foreign == 1 and monitor.accepted == 3


@pytest.mark.parametrize("order,code", [
    ([0, 2], "TEACHER_EVENT_SEQUENCE_GAP"),
    ([1], "TEACHER_EVENT_SEQUENCE_GAP"),
    ([0, 0], "TEACHER_EVENT_SEQUENCE_REPEATED"),
])
def test_the_monitor_names_a_gap_or_a_repeat_in_seq(order, code):
    monitor = EventStreamMonitor(IDENTITY)
    texts = _texts(4)
    with pytest.raises(TeacherEventError, match=code):
        for index in order:
            monitor.accept(texts[index])


def test_the_monitor_refuses_a_same_attempt_event_from_another_session_or_epoch():
    for identity in (StreamIdentity("other-session", 3, "a"), StreamIdentity("s", 4, "a")):
        monitor = EventStreamMonitor(IDENTITY)
        with pytest.raises(TeacherEventError, match="TEACHER_EVENT_IDENTITY_MISMATCH"):
            monitor.accept(_texts(1, identity=identity)[0])


def test_the_monitor_refuses_clocks_that_run_backwards():
    published = []
    ticks = iter([10, 9])
    stream = TeacherEventStream(IDENTITY, clock_ns=lambda: next(ticks), publish=published.append, start=False)
    stream.offer("phase_begin", {})
    stream.offer("phase_finish", {})
    stream.pump()
    monitor = EventStreamMonitor(IDENTITY)
    monitor.accept(published[0])
    with pytest.raises(TeacherEventError, match="TEACHER_EVENT_CLOCK_REGRESSED"):
        monitor.accept(published[1])


# ---- the real Teacher run: identical with and without any stream ------------------------------------------------

def _run_teacher(monkeypatch, *, stream=None):
    """The whole DONE workflow through the real perform/finish, as test_act_teacher_data_decoupling does, with an
    optional event stream attached the way the execution constructor attaches it."""

    import rclpy
    operations = []
    monkeypatch.setattr(rclpy, "spin_once", lambda *args, **kwargs: None)
    adapter = _adapter()
    adapter._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=2_000_000_000)))
    adapter._event_stream = stream
    adapter._event_sink = StreamEventSink(stream)
    adapter._scene_source_binding = None
    adapter._scene_source_observer = None
    adapter._targets.for_state = lambda state: PLACE_POSE
    adapter._before_micro_lift, adapter._attached = None, False
    clock_progress = adapter._progress

    def progress():
        clock_progress()
        RosDynamicMujocoExecution._progress(adapter)
    adapter._progress = progress
    start = _sample(START[:3], START[3:], time_s=1.0)

    def snapshot():
        adapter._progress()
        return start
    adapter._snapshot = snapshot
    for name in ("_motion", "_attach", "_detach_or_sync", "_open_supported_gripper", "_wait_release",
                 "_validate_final", "_set_touch_collision"):
        setattr(adapter, name, lambda *args, **kwargs: None)
    adapter._command_gripper = lambda state, target, before=None: adapter._record(state, start, start)
    adapter._wait_stable = lambda predicate, duration, timeout: start
    results = []
    for state in _workflow_states():
        target = PLACE_POSE if state in DYNAMIC_MOTION_STATES else None
        results.append(adapter.perform(state, target))
    _end_sampler(adapter, _end_pose()[:3], _end_pose()[3:])
    adapter.finish(SimpleNamespace(status=SimpleNamespace(value="DONE"), current_state=State.DONE,
                                   transition_count=len(results), state_trace=(State.IDLE, State.DONE),
                                   failure=None))
    return adapter, results, operations


def _events(published):
    return [decode_event(text) for text in published]


def test_the_teacher_offers_every_run_event_in_order_with_the_manifests_own_identifiers(monkeypatch):
    published = []
    stream = _stream(published)
    adapter, results, _ = _run_teacher(monkeypatch, stream=stream)
    assert all(result.status is ActionStatus.SUCCEEDED for result in results)
    stream.pump()
    events = _events(published)
    types = [event["type"] for event in events]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert types[:2] == ["reset_complete", "teacher_start_observation"]
    assert types[-2:] == ["teacher_end_observation", "terminal"] and "sequence_complete" not in types
    phases = [event for event in events if event["type"] in ("phase_begin", "phase_finish")]
    assert len(phases) == 2 * len(results)
    assert [event["payload"]["state"] for event in phases[::2]] == [state.value for state in _workflow_states()]
    assert all(type(event["payload"]["sim_time_ns"]) is int for event in phases)
    document = adapter._document
    start = next(event for event in events if event["type"] == "teacher_start_observation")
    end = next(event for event in events if event["type"] == "teacher_end_observation")
    assert start["payload"]["observation"] == document["teacher_start_observation"]
    assert end["payload"]["observation"] == document["teacher_end_observation"]
    reset = events[0]["payload"]
    assert (reset["session_id"], reset["reset_epoch"]) == ("s", 3)
    assert reset["simulation_step"] == document["teacher_start_observation"]["simulation_step"]
    terminal = events[-1]["payload"]
    assert terminal["teacher_execution_status"] == "COMPLETED" and terminal["teacher_task_result"] == "PASS"
    assert terminal["status"] == "DONE" and terminal["failure"] is None
    assert all(event["sim_time_ns"] == 2_000_000_000 and event["attempt_id"] == "a" for event in events)


def test_the_manifest_carries_the_drop_counter_and_the_last_published_seq(monkeypatch):
    published = []
    stream = _stream(published)
    adapter, _, _ = _run_teacher(monkeypatch, stream=stream)
    stream.pump()
    adapter._document["teacher_event_stream"] = stream.snapshot()
    block = adapter._document["teacher_event_stream"]
    assert block["dropped"] == 0 and block["publish_failures"] == 0
    assert block["last_published_seq"] == len(published) == block["published"]
    assert block["topic"] == STREAM_TOPIC and block["schema"] == STREAM_SCHEMA


def test_finish_writes_the_stream_block_into_the_manifest_without_any_publisher_help(monkeypatch):
    adapter, _, _ = _run_teacher(monkeypatch, stream=_stream([]))
    block = adapter._document["teacher_event_stream"]
    assert block["offered"] >= 2 * len(_workflow_states()) and block["dropped"] == 0
    assert block["published"] == 0, "nothing drained it yet: the Teacher result never waited for a publisher"


def test_a_run_without_any_stream_has_no_stream_block_and_no_error(monkeypatch):
    adapter, results, _ = _run_teacher(monkeypatch)
    assert all(result.status is ActionStatus.SUCCEEDED for result in results)
    assert "teacher_event_stream" not in adapter._document


@pytest.mark.parametrize("mode", ["no_subscriber", "publisher_raises", "publisher_blocks", "queue_full"])
def test_teacher_actions_and_results_are_identical_whatever_the_publisher_does(monkeypatch, mode):
    baseline, base_results, base_operations = _run_teacher(monkeypatch)
    release = threading.Event()
    if mode == "no_subscriber":
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 2_000_000_000, publish=lambda text: None, poll_s=0.001)
    elif mode == "publisher_raises":
        def refuse(text):
            raise RuntimeError("DDS_DOWN")
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 2_000_000_000, publish=refuse, poll_s=0.001)
    elif mode == "publisher_blocks":
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 2_000_000_000,
                                    publish=lambda text: release.wait(30), poll_s=0.001)
    else:
        stream = TeacherEventStream(IDENTITY, clock_ns=lambda: 2_000_000_000, publish=lambda text: None,
                                    depth=2, start=False)
    try:
        began = time.monotonic()
        adapter, results, operations = _run_teacher(monkeypatch, stream=stream)
        assert time.monotonic() - began < 30.0
    finally:
        release.set()
    assert [result.status for result in results] == [result.status for result in base_results]
    assert operations == base_operations
    assert not [operation for operation in operations if operation in FORBIDDEN]
    assert _teacher_view(adapter) == _teacher_view(baseline)
    assert adapter._document["teacher_task_result"]["result"] == "PASS"
    assert adapter._document["act_data_status"] == baseline._document["act_data_status"]
    if mode == "queue_full":
        assert adapter._document["teacher_event_stream"]["dropped"] > 0
    stream.close(flush_timeout_s=0.2)


def test_a_failed_teacher_still_ends_the_stream_with_a_terminal_event_naming_the_failure(monkeypatch):
    published = []
    stream = _stream(published)
    adapter = _adapter()
    adapter._node = SimpleNamespace(get_clock=lambda: SimpleNamespace(
        now=lambda: SimpleNamespace(nanoseconds=7)))
    adapter._event_stream = stream
    adapter._event_sink = StreamEventSink(stream)
    from so101_demo.core.domain import Failure, FailureCategory
    failed = SimpleNamespace(status=SimpleNamespace(value="ERROR"), current_state=State.ERROR, transition_count=0,
                             state_trace=(State.IDLE, State.ERROR),
                             failure=Failure(FailureCategory.EXECUTION, "DYNAMIC_EVIDENCE_TIMEOUT", "x"))
    adapter.finish(failed)
    stream.pump()
    events = _events(published)
    assert events[-1]["type"] == "terminal"
    assert events[-1]["payload"]["status"] == "ERROR"
    assert events[-1]["payload"]["failure"] == "DYNAMIC_EVIDENCE_TIMEOUT"
    assert events[-1]["payload"]["teacher_task_result"] == "UNCONFIRMED"
    end = [event for event in events if event["type"] == "teacher_end_observation"]
    assert end and end[0]["payload"]["observation"] is None


def test_normal_stop_events_reach_the_stream_through_the_executions_own_publisher(monkeypatch):
    published = []
    stream = _stream(published)
    adapter = _adapter()
    adapter._event_sink = StreamEventSink(stream)
    adapter._publish_teacher_event("normal_stop", {"proof": {"stop_confirmed_wall_s": 1.0}})
    stream.pump()
    event = decode_event(published[0])
    assert event["type"] == "normal_stop" and event["payload"] == {"proof": {"stop_confirmed_wall_s": 1.0}}


# REPLACED_BY test_teacher_events.py: the phase port's start and dispatch receipts are gone with the
# broker; the V2 phase events (with the sim stamp of the goal send) are tested there.


# ---- construction and the final stop ----------------------------------------------------------------------------

def _fake_node(publishes, *, refuse=False):
    class Publisher:
        def publish(self, message):
            publishes.append(message.data)

    def create_publisher(message_type, topic, qos):
        if refuse:
            raise RuntimeError("NO_PUBLISHERS_ON_THIS_NODE")
        publishes.append(("created", topic, qos.depth, qos.reliability.name, qos.durability.name, qos.history.name))
        return Publisher()

    return SimpleNamespace(create_publisher=create_publisher, destroy_publisher=lambda publisher: None,
                           get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=9)))


def test_the_execution_starts_the_stream_with_the_lease_attempt_identity_and_the_documented_qos():
    publishes = []
    adapter = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    adapter._event_sink = StreamEventSink(None)
    adapter._event_stream = adapter._event_stream_error = None
    adapter._start_event_stream(_fake_node(publishes), "s", 3, {"attempt_id": "attempt-9"}, "request-1")
    stream = adapter._event_stream
    assert stream is not None and adapter._event_stream_error is None
    assert stream.identity.document() == {"session_id": "s", "reset_epoch": 3, "attempt_id": "attempt-9"}
    assert publishes[0] == ("created", "/so101/teacher/events", 256, "RELIABLE", "VOLATILE", "KEEP_LAST")
    adapter._event_sink.publish("phase_begin", {"phase": "PREPARE_OPEN_GRIPPER"})
    adapter._close_event_stream()
    assert decode_event(publishes[1])["attempt_id"] == "attempt-9" and decode_event(publishes[1])["sim_time_ns"] == 9


def test_a_node_that_cannot_create_the_publisher_leaves_the_teacher_without_a_stream_not_without_a_run():
    adapter = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    adapter._event_sink = StreamEventSink(None)
    adapter._event_stream = adapter._event_stream_error = None
    adapter._start_event_stream(_fake_node([], refuse=True), "s", 3, None, None)
    assert adapter._event_stream is None and "NO_PUBLISHERS_ON_THIS_NODE" in adapter._event_stream_error
    assert adapter._event_sink.publish("phase_begin", {}) is False  # no stream: nothing to forward to
    adapter._stream_emit("terminal", {})  # no stream: a no-op, never an exception
    adapter._close_event_stream()


def _final_stop_adapter(monkeypatch, *, stop):
    published = []
    stream = _stream(published)
    adapter, results, operations = _run_teacher_with_final_stop(monkeypatch, stream, stop)
    stream.pump()
    return adapter, results, [decode_event(text) for text in published]


def _run_teacher_with_final_stop(monkeypatch, stream, stop):
    original = RosDynamicMujocoExecution.final_stop_proof_enabled
    monkeypatch.setattr(RosDynamicMujocoExecution, "final_stop_proof_enabled", True)
    monkeypatch.setattr(RosDynamicMujocoExecution, "_normal_stop_proof", stop)
    try:
        return _run_teacher(monkeypatch, stream=stream)
    finally:
        assert original is False, "the Teacher issues no extra stop request unless collection is on"


def test_with_collection_on_the_teacher_publishes_the_final_normal_stop_before_its_end_pose_and_terminal(
        monkeypatch):
    def stop(self):
        return {"stop_confirmed_wall_s": 1.5}

    adapter, results, events = _final_stop_adapter(monkeypatch, stop=stop)
    types = [event["type"] for event in events]
    assert types[-3:] == ["normal_stop", "teacher_end_observation", "terminal"]
    assert adapter._document["teacher_task_result"]["result"] == "PASS"


def test_a_failing_final_stop_is_recorded_and_never_changes_the_teacher_result(monkeypatch):
    def stop(self):
        raise RuntimeError("DYNAMIC_NORMAL_STOP_UNCONFIRMED")

    adapter, results, events = _final_stop_adapter(monkeypatch, stop=stop)
    assert adapter._document["teacher_final_stop_error"] == "DYNAMIC_NORMAL_STOP_UNCONFIRMED"
    assert adapter._document["teacher_execution_status"] == "COMPLETED"
    assert adapter._document["teacher_task_result"]["result"] == "PASS"
    assert "normal_stop" not in [event["type"] for event in events]


def test_without_collection_the_teacher_makes_no_final_stop_request(monkeypatch):
    def stop(self):
        raise AssertionError("a Teacher without a Recorder asked the owner for an extra stop")

    monkeypatch.setattr(RosDynamicMujocoExecution, "_normal_stop_proof", stop)
    adapter, results, _ = _run_teacher(monkeypatch, stream=_stream([]))
    assert "teacher_final_stop_error" not in adapter._document
