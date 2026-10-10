"""B2 (plan R3 + R9.9 + R9.10): boundaries, the audit and native QC on TEACHER_EVENT_SCHEMA Teacher events instead of dispatch receipts.

First command = the first goal-sending `phase_begin`; verified reset = `reset_complete`; normal end = `normal_stop`
followed by `terminal`. A missing one, a V1 receipt, an event sequence gap, a reference gap or a cross-reset frame is
INVALID.
"""
import copy

import pytest

from teacher_collection_fixtures import TEACHER_EVENT_SCHEMA, envelope, event_row, collection_materials, summary_row
from test_act_scene_association import frozen_scene  # noqa: F401  (fixture)


def verify(events, identity, window, frozen_scene):
    from so101_demo.act.episode_qc import verify_native_collection_events
    return verify_native_collection_events(events, identity=identity, window=window, inputs=frozen_scene[1])


def teacher_rows(events):
    return [row for row in events if row["kind"] == "teacher_event"]


def test_the_collection_reads_back_complete_with_no_dispatch_receipt(frozen_scene):
    events, identity, window, _boundaries, sources, _samples, _teacher = collection_materials(frozen_scene)
    answer = verify(events, identity, window, frozen_scene)
    assert answer["initial_source"] == sources[1] and answer["final_source"] == sources[3]
    assert answer["normal_stop_step"] == 3 and answer["goal_phase_begins"] == 1
    assert not any(row["kind"] == "native_dispatch_v1" for row in events)


@pytest.mark.parametrize("fault,match", [
    ("missing_phase_begin", "NATIVE_QC_FIRST_COMMAND_EVENT_REQUIRED"),
    ("only_non_goal_phase_begin", "NATIVE_QC_FIRST_COMMAND_EVENT_REQUIRED"),
    ("missing_reset_complete", "NATIVE_QC_RESET_COMPLETE_REQUIRED"),
    ("missing_normal_stop_event", "NATIVE_QC_NORMAL_STOP_EVENT_REQUIRED"),
    ("missing_terminal", "NATIVE_QC_TERMINAL_EVENT_REQUIRED"),
    ("terminal_before_stop", "NATIVE_QC_TERMINAL_ORDER_INVALID"),
    ("summary_missing", "NATIVE_QC_EVENT_SUMMARY_REQUIRED"),
    ("sequence_gap", "NATIVE_QC_EVENT_SEQUENCE_GAP"),
    ("summary_gap", "NATIVE_QC_EVENT_SEQUENCE_GAP"),
    ("repeated_seq", "NATIVE_QC_EVENT_SEQUENCE_GAP"),
    ("v1_schema", "NATIVE_QC_EVENT_SCHEMA_INVALID"),
    ("v1_dispatch_row", "NATIVE_QC_V1_EVENT_REJECTED"),
    ("foreign_attempt", "NATIVE_QC_EVENT_IDENTITY_INVALID"),
    ("reset_mismatch", "NATIVE_QC_RESET_EVENT_MISMATCH"),
    ("first_command_window", "NATIVE_DISPATCH_WINDOW_INVALID"),
    ("normal_end_window", "NATIVE_NORMAL_END_WINDOW_INVALID"),
    ("stop_result_not_success", "NATIVE_QC_STOP_RESULT_INVALID"),
    ("stop_moving", "NATIVE_QC_STOP_MEASURED_MOVING"),
    ("continuity_missing", "REFERENCE_CONTINUITY_MISSING"),
    ("continuity_gap", "REFERENCE_GAP_IN_LABEL_WINDOW"),
    ("continuity_epoch", "REFERENCE_EPOCH_MISMATCH"),
])
def test_collection_faults_are_invalid(frozen_scene, fault, match):
    events, identity, window, _b, _s, _samples, teacher = collection_materials(frozen_scene)
    rows = teacher_rows(events)
    if fault == "missing_phase_begin":
        events.remove(rows[1])
    if fault == "only_non_goal_phase_begin":
        rows[1]["payload"]["teacher_event"]["payload"].update(goal_sent=False, goal_kind=None)
    if fault == "missing_reset_complete":
        events.remove(rows[0])
    if fault == "missing_normal_stop_event":
        events.remove(rows[3])
    if fault == "missing_terminal":
        events.remove(rows[4])
    if fault == "terminal_before_stop":
        rows[4]["payload"]["teacher_event"]["monotonic_ns"] = rows[3]["payload"]["teacher_event"]["monotonic_ns"] - 5
    if fault == "summary_missing":
        events[:] = [row for row in events if row["kind"] != "teacher_event_summary"]
    if fault == "sequence_gap":
        for row in rows[2:]:
            row["payload"]["teacher_event"]["seq"] += 1
    if fault == "summary_gap":
        next(row for row in events if row["kind"] == "teacher_event_summary")["payload"]["event_summary"]["accepted"] = 4
    if fault == "repeated_seq":
        rows[2]["payload"]["teacher_event"]["seq"] = 2
    if fault == "v1_schema":
        rows[0]["payload"]["teacher_event"]["schema"] = "SO101_TEACHER_EVENT_V1"
    if fault == "v1_dispatch_row":
        events.append(dict(kind="native_dispatch_v1", sim_time_s=.005, monotonic_ns=1, payload=dict(native_dispatch={})))
    if fault == "foreign_attempt":
        rows[2]["payload"]["teacher_event"]["attempt_id"] = "foreign"
    if fault == "reset_mismatch":
        rows[0]["payload"]["teacher_event"]["payload"]["publisher_sequence"] = 1   # the Teacher claims evidence EARLIER than the Recorder's own first evidence
    if fault == "first_command_window":
        window["first_command_s"] = .0051
    if fault == "normal_end_window":
        window["physics_end_s"] = .008
    if fault == "stop_result_not_success":
        boundary = next(row for row in events if row.get("payload", {}).get("collection_boundary", {}).get("stage") == "normal_stop")
        boundary["payload"]["collection_boundary"]["value"]["trajectory_result"] = "CONTROLLER_FAILED"
    if fault == "stop_moving":
        boundary = next(row for row in events if row.get("payload", {}).get("collection_boundary", {}).get("stage") == "normal_stop")
        boundary["payload"]["collection_boundary"]["value"]["joint_velocities"]["1"] = .00201
    if fault == "continuity_missing":
        events[:] = [row for row in events if row["kind"] != "controller_reference"]
    if fault == "continuity_gap":
        row = next(row for row in events if row["kind"] == "controller_reference")
        row["payload"]["reference_continuity"]["kinds"]["arm"].update(gaps=1, steps=[[100_000_000, 104_000_000]])   # the label instant 0.102 s has no frame (CP-3439)
    if fault == "continuity_epoch":
        next(row for row in events if row["kind"] == "controller_reference")["payload"]["reference_continuity"]["reset_epoch"] = 2
    with pytest.raises(ValueError, match=match):
        verify(events, identity, window, frozen_scene)


def test_a_step_finished_before_the_stop_receipt_but_ahead_of_its_sim_stamp_is_not_the_stops_step():
    """CP-3449 (bag 429dbf50): the Teacher's stop stamp is a received /clock value, so physics may already be one step ahead of
    it when the stamp is taken: step 55981 (116.548 s) ended 46 us before the stop receipt that read 116.546 s. The stop's native
    step is the last step finished before the receipt AND not later than the stamp (55980); a step ahead of the stamp is neither
    stale evidence nor the stop's state."""
    from so101_demo.act.episode_qc import stop_native_step

    stop = dict(sim_time_ns=116_546_000_000, begin_monotonic_ns=914_957_319_669_645, end_monotonic_ns=914_957_319_669_645)

    def step(number, sim_s, before_stop_ns):
        return dict(physics_step=number, simulation_time_s=sim_s, clock_interval_end_monotonic_ns=stop["begin_monotonic_ns"] + before_stop_ns)

    steps = [step(55979, 116.54399999990979, -4_384_834), step(55980, 116.54599999990978, -2_216_294),
             step(55981, 116.54799999990978, -45_997), step(55982, 116.54999999990977, 2_123_718)]
    assert stop_native_step(steps, stop)["physics_step"] == 55980
    with pytest.raises(ValueError, match="NATIVE_QC_STOP_NATIVE_REQUIRED"):
        stop_native_step(steps[2:], stop)                         # nothing at or before the stamp finished before the receipt
    stale = [step(1, 116.30, -2_000_000)]
    with pytest.raises(ValueError, match="NATIVE_QC_STOP_NATIVE_STALE"):
        stop_native_step(stale, stop)                             # 246 ms before the stamp: still stale


def test_the_first_command_clock_comes_from_the_first_goal_sending_phase_begin(frozen_scene):
    events, identity, window, boundaries, _s, _samples, teacher = collection_materials(frozen_scene)
    # a later goal phase_begin does not move the first command
    extra = copy.deepcopy(teacher_rows(events)[1])
    extra["payload"]["teacher_event"]["seq"] = 3
    answer = verify(events, identity, window, frozen_scene)
    assert answer["first_command_s"] == window["first_command_s"] == .005


# ---- boundary documents ----------------------------------------------------------------------------------------

def test_the_reset_boundary_is_closed_and_bound_to_its_scope(frozen_scene):
    from so101_demo.act.collection_boundaries import validate_verified_reset
    _e, identity, _w, boundaries, _s, _x, _t = collection_materials(frozen_scene)
    reset = boundaries["verified_reset"]
    assert validate_verified_reset(reset, identity=identity) == reset
    for change in ({"generation": 1}, {"controller_readback_sha256": "a" * 64}, {"schema_version": 1},
                   {"reset_epoch": 2}, {"attempt_id": "foreign"}):
        bad = {**copy.deepcopy(reset), **change}
        with pytest.raises(ValueError):
            validate_verified_reset(bad, identity=identity)


def test_a_retired_verified_reset_boundary_is_rejected():
    from so101_demo.act.collection_boundaries import validate_verified_reset
    identity = dict(session_id="s", attempt_id="a", reset_epoch=1)
    clock = dict(sim_time_ns=0, begin_monotonic_ns=10_000_000_000, end_monotonic_ns=10_000_000_001)
    v1 = dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=1, generation=1, source_clock=clock,
              controller_readback_base64="e30=", controller_readback_sha256="a" * 64,
              physical_source=dict(session_id="s", reset_epoch=1, simulation_step=0, publisher_sequence=1,
                                   simulation_time_s=0., received_wall_s=9.99, paused=True, scalar_received_wall_s=9.99,
                                   scalar_positions=[0.] * 7, scalar_velocities=[0.] * 7, verification_clock=[]),
              **identity)
    with pytest.raises(ValueError):
        validate_verified_reset(v1, identity=identity)


def test_the_normal_stop_boundary_needs_a_successful_result_and_a_stopped_arm(frozen_scene):
    from so101_demo.act.native_endpoints import validate_normal_stop_boundary
    _e, identity, _w, boundaries, _s, _x, _t = collection_materials(frozen_scene)
    stop = boundaries["normal_stop"]
    assert validate_normal_stop_boundary(stop, identity=identity).publisher_sequence == 9
    for path, value in (("trajectory_result", "TIMED_OUT"), ("confirmed_monotonic_ns", 1), ("schema_version", 1)):
        bad = {**copy.deepcopy(stop), path: value}
        with pytest.raises(ValueError):
            validate_normal_stop_boundary(bad, identity=identity)
    moving = copy.deepcopy(stop)
    moving["joint_velocities"]["3"] = .01
    with pytest.raises(ValueError):
        validate_normal_stop_boundary(moving, identity=identity)


def test_reset_complete_event_must_be_consistent_with_the_recorders_own_verified_reset():
    from so101_demo.act.teacher_collection import validate_reset_complete_matches
    identity = dict(session_id="s", attempt_id="a", reset_epoch=2)
    document = envelope(1, "reset_complete", 2_000_000, 9_000_000_000,
                        dict(session_id="s", reset_epoch=2, simulation_time_s=.002, simulation_step=1,
                             publisher_sequence=7, received_monotonic_ns=9_000_000_000), identity=identity)
    boundary = dict(kind="ACT_VERIFIED_RESET_BOUNDARY", schema_version=3, session_id="s", attempt_id="a", reset_epoch=2,
                    source_clock=dict(sim_time_ns=1_000_000, begin_monotonic_ns=8_000_000_000, end_monotonic_ns=8_000_000_100),
                    physical_source=dict(session_id="s", reset_epoch=2, simulation_step=0, publisher_sequence=3,
                                         simulation_time_s=.001, received_wall_s=8.0001))
    validate_reset_complete_matches(document, boundary)                  # the Recorder's evidence is earlier: consistent
    for change in (dict(publisher_sequence=8), dict(simulation_time_s=.003), dict(session_id="t"), dict(reset_epoch=3)):
        later = copy.deepcopy(boundary)
        later["physical_source"].update({key: value for key, value in change.items() if key in ("publisher_sequence",)})
        if "simulation_time_s" in change:
            later["physical_source"]["simulation_time_s"] = change["simulation_time_s"]
        if "session_id" in change:
            later["session_id"] = "t"
        if "reset_epoch" in change:
            later["reset_epoch"] = 3
        with pytest.raises(ValueError):
            validate_reset_complete_matches(document, later)             # later evidence, or another scope: inconsistent
    boundary["schema_version"] = 2
    with pytest.raises(ValueError):
        validate_reset_complete_matches(document, boundary)              # the Teacher-receipt version is never accepted


def test_the_goal_sending_phase_begin_becomes_the_first_command_clock():
    from so101_demo.act.teacher_collection import first_command_clock
    identity = dict(session_id="s", attempt_id="a", reset_epoch=2)
    goal = envelope(2, "phase_begin", 5_000_000, 9_000_100_000, dict(state="X", sim_time_ns=5_000_000,
        monotonic_ns=9_000_100_000, goal_sent=True, goal_kind="arm"), identity=identity)
    plain = envelope(1, "phase_begin", 4_000_000, 9_000_000_000, dict(state="Y", sim_time_ns=4_000_000,
        monotonic_ns=9_000_000_000, goal_sent=False, goal_kind=None), identity=identity)
    assert first_command_clock(plain) is None
    assert first_command_clock(goal) == dict(sim_time_ns=5_000_000, begin_monotonic_ns=9_000_100_000,
                                             end_monotonic_ns=9_000_100_000)


# ---- audit writer ----------------------------------------------------------------------------------------------

def test_the_audit_refuses_a_retired_dispatch_row_a_retired_event_and_a_repeated_event(tmp_path):
    from test_act_episode_audit import complete_audit
    writer, _window = complete_audit(tmp_path)
    identity = dict(writer.identity)
    assert not hasattr(writer, "append_native_dispatch")
    ok = envelope(1, "phase_finish", 1, 10, dict(state="X", status="SUCCEEDED", code=None), identity=identity)
    writer.append_teacher_event(ok)
    with pytest.raises(ValueError):
        writer.append_teacher_event(copy.deepcopy(ok))  # repeated seq
    with pytest.raises(ValueError):
        writer.append_teacher_event({**envelope(2, "phase_finish", 1, 10, {}, identity=identity),
                                     "schema": "SO101_TEACHER_EVENT_V1"})
    # scene operations take sequence numbers without being retained, so a skip is allowed; the sealed summary proves
    # that nothing else was lost (QC: retained + scene operations == last_seq == accepted)
    writer.append_teacher_event(envelope(4, "phase_finish", 1, 10, dict(state="Y", status="SUCCEEDED", code=None),
                                         identity=identity))
    with pytest.raises(ValueError):
        writer.append_source("events", dict(kind="native_dispatch_v1", identity=identity, sim_time_s=0.,
                                            monotonic_ns=1, payload={"native_dispatch": {}}))


def test_reset_complete_payload_is_closed_and_coherent():
    from so101_demo.act.teacher_collection import validate_reset_complete_payload
    identity = dict(session_id="s", attempt_id="a", reset_epoch=2)
    good = dict(session_id="s", reset_epoch=2, simulation_time_s=.002, simulation_step=1,
                publisher_sequence=7, received_monotonic_ns=9_000_000_000)
    for change in (dict(extra=1), dict(simulation_time_s=.003), dict(session_id="t"), dict(reset_epoch=3),
                   dict(received_monotonic_ns=9_000_000_001)):
        with pytest.raises(ValueError):
            validate_reset_complete_payload(envelope(1, "reset_complete", 2_000_000, 9_000_000_000,
                                                     dict(good, **change), identity=identity))
