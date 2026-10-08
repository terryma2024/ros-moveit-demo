"""B2: the Recorder data side consumes V2 Teacher events (no dispatch receipt, no sequence_complete, no stop RPC)."""
import copy
import time
from types import SimpleNamespace

import pytest

from b2_collection_fixtures import V2, envelope
from so101_demo.ros.recorder_data_side import RecorderDataSide

IDENTITY = dict(session_id="s", attempt_id="a", reset_epoch=4, release_epoch=0,
                lease=dict(lease_deadline_monotonic_s=time.monotonic() + 600.))


def consumer(*, started=True):
    from so101_demo.act.episode_assembly import PointEpisode
    from test_act_continuous_capture import build
    retained = []
    capture, _ = build(clock=time.monotonic)
    capture.audit = SimpleNamespace(
        identity=IDENTITY,
        append_collection_boundary=lambda stage, value: retained.append(("boundary", stage, copy.deepcopy(value))),
        append_teacher_event=lambda event: retained.append(("event", event["type"], event["seq"])))
    episode = PointEpisode.__new__(PointEpisode)
    episode.identity, episode.capture = IDENTITY, capture
    if started:
        capture.start("s", "a", 4, 1.)
    side = RecorderDataSide(node=None, session_id="s", reset_epoch=4, episode=episode, binding=None,
                            world_observer=None, execution_root=None, progress=lambda: None,
                            normal_stop_proof=lambda: {}, invalid_latched=lambda: False, drain_collection=lambda: 0)
    if started:
        side.retain_epoch_boundary(episode, epoch_boundary())     # retained at the capture start, before any Teacher event
    return side, episode, retained


def epoch_boundary(**changes):
    """The V3 verified reset: the Recorder's own first evidence of the epoch, on the producer's clock (CP-3425)."""
    end = time.monotonic_ns() - 50_000_000
    value = dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=3, session_id="s", attempt_id="a", reset_epoch=4,
                 source_clock=dict(sim_time_ns=1_000_000_000, begin_monotonic_ns=end - 1_000_000, end_monotonic_ns=end),
                 physical_source=dict(session_id="s", reset_epoch=4, simulation_step=500, publisher_sequence=400,
                                      simulation_time_s=1.0, received_wall_s=end / 1e9 + 0.001))
    value.update(changes)
    return value


def event(seq, type_, payload, *, sim=2_000_000_000, mono=None):
    return envelope(seq, type_, sim, time.monotonic_ns() - 1_000_000 if mono is None else mono, payload, identity=IDENTITY)


def reset_payload(**changes):
    mono = time.monotonic_ns() - 2_000_000
    value = dict(session_id="s", reset_epoch=4, simulation_time_s=2.0, simulation_step=1000, publisher_sequence=500,
                 received_monotonic_ns=mono)
    value.update(changes)
    return value


def goal_begin(seq, *, mono=None, sim=2_100_000_000, goal=True, kind="gripper"):
    mono = time.monotonic_ns() - 500_000 if mono is None else mono
    return event(seq, "phase_begin", dict(state="X", sim_time_ns=sim, monotonic_ns=mono, goal_sent=goal,
                                          goal_kind=kind if goal else None), sim=sim, mono=mono)


def test_the_verified_reset_is_the_recorders_own_first_evidence_retained_once_and_the_teachers_event_is_consistent():
    side, episode, retained = consumer()
    boundaries = [item for item in retained if item[0] == "boundary"]
    assert len(boundaries) == 1 and boundaries[0][1] == "verified_reset" and boundaries[0][2]["schema_version"] == 3
    assert boundaries[0][2]["physical_source"]["publisher_sequence"] == 400
    side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload()))
    assert ("event", "reset_complete", 1) in retained
    assert len([item for item in retained if item[0] == "boundary"]) == 1, "the event retains no second boundary"
    with pytest.raises(PermissionError, match="EPISODE_RESET_BOUNDARY_REPEATED"):
        side.retain_epoch_boundary(episode, epoch_boundary())


def test_a_reset_complete_before_the_recorders_own_evidence_exists_is_a_data_failure():
    side, episode, _retained = consumer(started=False)
    with pytest.raises(PermissionError, match="TEACHER_RESET_BEFORE_RECORDER_EVIDENCE"):
        side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload()))


@pytest.mark.parametrize("fault", ["foreign_session", "foreign_epoch", "after_now", "sim_mismatch", "earlier_than_boundary"])
def test_reset_complete_faults_raise_to_the_data_caller_only(fault):
    side, episode, retained = consumer()
    payload = reset_payload()
    if fault == "foreign_session":
        payload["session_id"] = "other"
    if fault == "foreign_epoch":
        payload["reset_epoch"] = 5
    if fault == "after_now":
        payload["received_monotonic_ns"] = time.monotonic_ns() + 10 ** 12
    if fault == "sim_mismatch":
        payload["simulation_time_s"] = 2.5       # the boundary cannot be later than the event that announces it
    if fault == "earlier_than_boundary":
        payload["publisher_sequence"] = 100      # the Teacher claims evidence EARLIER than the Recorder's own first evidence
    first = event(1, "reset_complete", payload)
    with pytest.raises((RuntimeError, PermissionError, ValueError)):
        side._consume_teacher_event(episode, first)


def test_the_first_goal_phase_begin_starts_the_capture_deadline_and_the_first_command_clock():
    side, episode, _retained = consumer()
    side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload()))
    begin = goal_begin(2)
    side._consume_teacher_event(episode, begin)
    assert episode.capture._first_command_s == begin["sim_time_ns"] / 1e9
    assert side._data_first_dispatch_begin_ns == begin["monotonic_ns"]
    side._consume_teacher_event(episode, goal_begin(3, sim=2_200_000_000))
    assert episode.capture._first_command_s == begin["sim_time_ns"] / 1e9  # never moved


def test_a_phase_begin_without_a_goal_is_not_the_first_command():
    side, episode, _retained = consumer()
    side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload()))
    side._consume_teacher_event(episode, goal_begin(2, goal=False))
    assert episode.capture._first_command_s is None


def test_the_initial_boundary_cannot_follow_the_first_command():
    side, episode, _retained = consumer()
    side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload()))
    side._consume_teacher_event(episode, goal_begin(2))
    with pytest.raises(RuntimeError, match="DYNAMIC_INITIAL_BOUNDARY_AFTER_FIRST_COMMAND"):
        side._step_data_initial_boundary()


def test_normal_stop_event_is_kept_as_the_v2_stop_boundary_and_needs_no_rpc():
    side, episode, retained = consumer()
    mono = time.monotonic_ns() - 1_000_000
    clock = dict(sim_time_ns=3_000_000_000, begin_monotonic_ns=mono, end_monotonic_ns=mono)
    proof = dict(kind="TEACHER_NORMAL_STOP", trajectory_result="SUCCEEDED", stop_confirmed_wall_s=(mono - 10) / 1e9,
                 source_clock=clock, simulation_step=1500, publisher_sequence=900, sim_stamp_s=3.0,
                 received_wall_s=mono / 1e9, joint_positions={n: 0.0 for n in "123456"},
                 joint_velocities={n: 0.0 for n in "123456"})
    side._consume_teacher_event(episode, event(1, "normal_stop", dict(proof=proof), sim=3_000_000_000, mono=mono))
    stop = side._data_normal_stop
    assert stop["schema_version"] == 2 and stop["epoch"]["publisher_sequence"] == 900
    assert stop["source_clock"] == clock and stop["confirmed_monotonic_ns"] == mono


def test_a_v1_event_and_a_repeated_sequence_are_data_failures():
    """Contiguity across all events (scene operations included) is the engine's `EventStreamMonitor`; the data side
    only needs retained events strictly ordered (scene operations take numbers it never sees)."""
    side, episode, _retained = consumer()
    v1 = {**event(1, "reset_complete", reset_payload()), "schema": "SO101_TEACHER_EVENT_V1"}
    with pytest.raises(RuntimeError, match="TEACHER_EVENT_SCHEMA"):
        side._consume_teacher_event(episode, v1)
    side, episode, _retained = consumer()
    side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload()))
    side._consume_teacher_event(episode, goal_begin(3))  # a skipped number is a scene operation: allowed here
    with pytest.raises(RuntimeError, match="TEACHER_EVENT_SEQUENCE"):
        side._consume_teacher_event(episode, goal_begin(3))


def test_the_data_side_has_no_dispatch_or_expert_sequence_retention():
    for removed in ("_data_retain_dispatch", "_data_retain_sequence_complete"):
        assert not hasattr(RecorderDataSide, removed), removed


@pytest.mark.parametrize("change", [dict(extra_key=1), dict(operator="x"), dict(simulation_step=-1),
                                    dict(simulation_time_s=float("nan")), dict(publisher_sequence="7"),
                                    dict(received_monotonic_ns=True)])
def test_the_reset_complete_payload_is_a_closed_object(change):
    side, episode, retained = consumer()
    with pytest.raises((RuntimeError, PermissionError, ValueError)):
        side._consume_teacher_event(episode, event(1, "reset_complete", reset_payload(**change)))
    assert len([item for item in retained if item[0] == "boundary"]) == 1      # only the capture-start boundary


@pytest.mark.parametrize("missing", ["session_id", "reset_epoch", "simulation_time_s", "simulation_step",
                                     "publisher_sequence", "received_monotonic_ns"])
def test_a_reset_complete_payload_missing_a_key_is_a_data_failure_not_a_key_error(missing):
    side, episode, retained = consumer()
    payload = reset_payload()
    del payload[missing]
    with pytest.raises(ValueError):
        side._consume_teacher_event(episode, event(1, "reset_complete", payload))
