"""Teacher execution policy v3 (design 2026-10-10, section 10.1): the real `RosDynamicMujocoExecution` over fakes.

Removed gates no longer raise, kept gates still raise, the release sequence of 5a, the place fallback per enum reason, the status
mapping, the process summary, the final normal_stop. v1/v2 behaviour is covered by the untouched tests of the same module."""
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.application.e2e_acceptance import SCHEMA_TEACHER
from so101_demo.core import place_height as ph
from so101_demo.core.domain import ActionStatus, State
from so101_demo.core.process_summary import ProcessSummary
from so101_demo.ros.dynamic_mujoco_execution import (
    RosDynamicMujocoExecution, _JointStateStale)
from so101_demo.ros.teacher_safety import CupSafetyLimits
from so101_demo.ros.teacher_stop import TeacherStop

from test_b1_teacher_execution import ARM, make_adapter, release_adapter
from test_b1_teacher_stop_core import COMPRESSION_LIMIT_M, FORCE_LIMIT_N, evidence
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
TEACHER_POLICY = load_teacher_execution_policy(PACKAGE / "config/act/teacher_execution_policy.yaml")
HOVER_Z = 0.2176344


def teacher_adapter(tmp_path, **kwargs):
    value = make_adapter(tmp_path, **kwargs)
    value._execution_policy = TEACHER_POLICY
    value._document = {"schema": SCHEMA_TEACHER}
    value._write = lambda: None
    value._process_summary = ProcessSummary(limits=CupSafetyLimits(FORCE_LIMIT_N, COMPRESSION_LIMIT_M))
    value._release_marker_sequence, value._scene_readback, value._final_samples = None, None, []
    return value


def run_monitor(value, state=State.MOVE_ABOVE_PLACE):
    value._snapshot = lambda: pytest.fail("the monitor must not use the blocking _snapshot()")
    return value._motion_monitor(state)()


# ---- removed gates no longer raise ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("sample", [
    evidence(left=(12.0,)),                                          # the original 11.60 N single-contact limit
    evidence(left=(FORCE_LIMIT_N,), right=(FORCE_LIMIT_N,)),         # summed cup force above the activated limit
    evidence(distance=-(COMPRESSION_LIMIT_M * 4)),                   # fingertip compression above the activated limit
], ids=["single-contact", "summed-force", "compression"])
def test_force_and_compression_no_longer_stop_the_teacher_monitor_but_stop_a_general_run(tmp_path, sample):
    value = teacher_adapter(tmp_path)
    value.observer.put(sample)
    run_monitor(value)
    old = make_adapter(tmp_path)
    old.observer.put(sample)
    with pytest.raises(TeacherStop):
        run_monitor(old)


def test_a_collision_or_hazard_latch_no_longer_stops_the_teacher(tmp_path):
    value = teacher_adapter(tmp_path)
    value._collision_watch = SimpleNamespace(hazard="DYNAMIC_COLLISION_STOP", detail="pair")
    value._physics_hazard_watch = SimpleNamespace(
        hazard="DYNAMIC_PHYSICS_HAZARD", detail="x", limit_code="DYNAMIC_CUP_FORCE_EXCEEDED", gaps=5, limits=None,
        last_chunk_monotonic_s=None, armed_monotonic_s=None)
    value._enforce_safety(State.LIFT, evidence(left=(50.0,)))
    run_monitor(value)


# ---- kept gates still raise -----------------------------------------------------------------------------------------------

def test_session_epoch_and_non_finite_state_are_simulation_integrity_stops(tmp_path):
    for change, code in ((dict(simulation_session_id="other"), "SIM_INTEGRITY_SESSION_MISMATCH"),
                         (dict(reset_epoch=2), "SIM_INTEGRITY_RESET_EPOCH_MISMATCH"), (dict(paused=True), "SIM_INTEGRITY_RESET_EPOCH_MISMATCH")):
        value = teacher_adapter(tmp_path)
        value.observer.put(replace(evidence(), **change))
        with pytest.raises(TeacherStop) as stop:
            run_monitor(value)
        assert stop.value.code == code
    value = teacher_adapter(tmp_path)
    good = evidence()
    object.__setattr__(good.object_state, "position_world", (math.nan, 0.0, 0.0))     # the dataclass refuses it at construction
    value.observer.put(good)
    with pytest.raises(TeacherStop) as stop:
        run_monitor(value)
    assert stop.value.code == "SIM_INTEGRITY_NON_FINITE_STATE"


def test_a_silent_joint_state_or_world_stream_is_a_stop_after_one_second_with_its_own_code(tmp_path):
    joint = teacher_adapter(tmp_path)
    joint._joint_state_received_monotonic_s = 90.0
    run_monitor(joint)
    joint._now[0] += 1.1
    with pytest.raises(TeacherStop) as stop:
        run_monitor(joint)
    assert stop.value.code == "TEACHER_JOINT_STATE_UNAVAILABLE"
    world = teacher_adapter(tmp_path)
    world.observer.put(evidence(), received=50.0)                    # stale evidence, fresh joint states
    run_monitor(world)
    world._now[0] += 1.1
    world._joint_state_received_monotonic_s = world._now[0]
    with pytest.raises(TeacherStop) as stop:
        run_monitor(world)
    assert stop.value.code == "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE"


def test_the_helper_codes_become_the_teacher_codes_only_in_a_teacher_run(tmp_path):
    v3, old = teacher_adapter(tmp_path), make_adapter(tmp_path)
    for raw, mapped in (("DYNAMIC_SESSION_MISMATCH", "SIM_INTEGRITY_SESSION_MISMATCH"),
                        ("DYNAMIC_RESET_EPOCH_MISMATCH", "SIM_INTEGRITY_RESET_EPOCH_MISMATCH"),
                        ("DYNAMIC_EVIDENCE_TIMEOUT", "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE"),
                        ("JOINT_STATE_TIMEOUT", "TEACHER_JOINT_STATE_UNAVAILABLE")):
        assert v3._failure_code(RuntimeError(raw + ": detail")) == (mapped, mapped + ": detail")
        assert old._failure_code(RuntimeError(raw)) == (raw, raw)
    assert v3._failure_code(RuntimeError("MOVEIT_EXECUTION_FAILED: x")) == ("MOVEIT_EXECUTION_FAILED", "MOVEIT_EXECUTION_FAILED: x")


def test_perform_state_reports_the_mapped_code(tmp_path):
    value = teacher_adapter(tmp_path)
    value._initial = evidence()
    value._phase_finish = lambda *args: None

    def broken(state):
        raise RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT")
    value._perform_teacher_state = broken
    result = value._perform_state(State.WAIT_GRASP_STABLE, None)
    assert result.status is ActionStatus.FAILED and result.failure.code == "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE"


# ---- status mapping -------------------------------------------------------------------------------------------------------

def test_the_teacher_status_mapping(tmp_path):
    def status(code):
        return RosDynamicMujocoExecution._teacher_execution_status(
            SimpleNamespace(status=SimpleNamespace(value="ERROR"), failure=SimpleNamespace(code=code)),
            {"physical_action_proven_absent": False})
    assert status("TEACHER_JOINT_STATE_UNAVAILABLE") == "STOPPED_SAFETY"
    for code in ("SIM_INTEGRITY_SESSION_MISMATCH", "SIM_INTEGRITY_RESET_EPOCH_MISMATCH", "SIM_INTEGRITY_NON_FINITE_STATE",
                 "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE", "TEACHER_ARM_NOT_STOPPED", "TEACHER_DWELL_TIMEOUT", "MOVEIT_EXECUTION_FAILED",
                 "DYNAMIC_DETACH_SYNC_FAILED"):
        assert status(code) == "FAILED", code
    assert status("TEACHER_CANCEL_UNSETTLED") == "INDETERMINATE"
    # unchanged from v2: the operator and watchdog codes keep their statuses
    assert status("TEACHER_USER_STOP") == "STOPPED_USER" and status("TEACHER_DEADLINE") == "DEADLINE"


def test_the_manifest_fields_name_the_teacher_schema_the_failure_class_and_the_summary(tmp_path):
    value = teacher_adapter(tmp_path)
    value._document["teacher_process_summary"] = {"schema": "teacher_process_summary_v1"}
    failed = SimpleNamespace(status=SimpleNamespace(value="ERROR"), failure=SimpleNamespace(code="SIM_INTEGRITY_NON_FINITE_STATE"))
    fields = value._teacher_manifest_fields(failed, {"physical_action_proven_absent": False}, None, None)
    assert fields["schema"] == SCHEMA_TEACHER and fields["teacher_execution_status"] == "FAILED"
    assert fields["failure_class"] == "sim_integrity" and fields["teacher_process_summary"]["schema"] == "teacher_process_summary_v1"
    other = SimpleNamespace(status=SimpleNamespace(value="ERROR"), failure=SimpleNamespace(code="MOVEIT_EXECUTION_FAILED"))
    assert value._teacher_manifest_fields(other, {"physical_action_proven_absent": False}, None, None)["failure_class"] is None


# ---- failure boundary without recovery ------------------------------------------------------------------------------------

def test_the_failure_boundary_of_a_trace_is_the_state_before_error():
    from so101_demo.core.workflow import TEACHER_WORKFLOW
    trace = (State.IDLE, State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT, State.ERROR)
    failure = SimpleNamespace(code="MOVEIT_EXECUTION_FAILED")
    assert RosDynamicMujocoExecution._failure_boundary(trace, failure, TEACHER_WORKFLOW) is State.MOVE_ABOVE_OBJECT
    # the v1/v2 route of the same non-terminal failure is a RECOVER_* state, so the same trace has no boundary there
    assert RosDynamicMujocoExecution._failure_boundary(trace, failure) is None


# ---- release sequence (5a) ------------------------------------------------------------------------------------------------

def test_the_arm_stop_wait_passes_on_a_stopped_arm_and_times_out_with_its_own_code(tmp_path):
    value = teacher_adapter(tmp_path)
    value._wait_progress = lambda: value._now.__setitem__(0, value._now[0] + 0.05)
    value._wait_arm_stopped()
    value._joint_velocities = {name: 0.0021 for name in (*ARM, "6")}     # just above 0.002 rad/s
    with pytest.raises(RuntimeError, match="TEACHER_ARM_NOT_STOPPED"):
        value._wait_arm_stopped()
    value._joint_velocities = {name: 0.002 for name in (*ARM, "6")}      # exactly at the bound passes
    value._joint_state_received_monotonic_s = value._now[0]
    value._wait_arm_stopped()
    value._joint_state_received_monotonic_s = value._now[0] - 0.6        # not fresh
    with pytest.raises(RuntimeError, match="TEACHER_ARM_NOT_STOPPED"):
        value._wait_arm_stopped()


def test_open_gripper_records_the_release_marker_from_a_fresh_snapshot_without_any_release_proof(tmp_path):
    value = teacher_adapter(tmp_path)
    value.observer.put(evidence(other=(), step=4321))                    # nothing supports the cup: v2 would refuse
    value._ik = SimpleNamespace(forward=lambda joints: SimpleNamespace(position_m=(0.0, 0.0, 0.2), orientation_xyzw=(0.0, 0.0, 0.0, 1.0)))
    commands = []
    value._command_gripper = lambda *args, **kwargs: commands.append((args, kwargs))
    value._supported_release_preflight = lambda: pytest.fail("v3 has no release preflight")
    value._normal_stop_proof = lambda: pytest.fail("v3 has no release stop proof")
    value._perform_teacher_state(State.OPEN_GRIPPER)
    assert value._release_marker_sequence == 4321 and len(commands) == 1
    assert commands[0][1]["before"].publisher_sequence == 4321
    assert value._process_summary._poses["release_start"]["left_contacts"] == 1


def test_detach_uses_a_fresh_snapshot_not_the_release_preflight(tmp_path):
    value = teacher_adapter(tmp_path)
    value._task_geometry = None                                            # ends the method right after the source check
    value._supported_release_preflight = lambda: pytest.fail("v3 has no release preflight")
    with pytest.raises(RuntimeError, match="DYNAMIC_DETACH_SYNC_SOURCE_INVALID"):
        value._detach_or_sync(State.DETACH_MOVEIT)


def test_the_fixed_dwells_wait_simulation_time_not_a_predicate(tmp_path):
    value = teacher_adapter(tmp_path)
    clock = [1000]
    states = []

    def snapshot():
        clock[0] += 125                                                    # 0.25 s per call at 0.002 s a step
        sample = evidence(step=clock[0], left=(), right=())                # no bilateral contact: a predicate would never hold
        states.append(sample)
        return sample
    value._snapshot = snapshot
    value._ik = SimpleNamespace(forward=lambda joints: SimpleNamespace(position_m=(0.0, 0.0, 0.2), orientation_xyzw=(0.0, 0.0, 0.0, 1.0)))
    value._perform_teacher_state(State.WAIT_GRASP_STABLE)
    assert len(states) == 2 and value._state_events[-1]["dwell_s"] == 0.25
    assert "grasp_stable" in value._process_summary._poses
    value._perform_teacher_state(State.WAIT_RELEASE_SETTLE)
    assert value._state_events[-1]["dwell_s"] == 0.5 and len(value._final_samples) == 1


def test_a_dwell_that_never_advances_ends_the_attempt(tmp_path):
    value = teacher_adapter(tmp_path)
    value._snapshot = lambda: evidence()
    import so101_demo.ros.dynamic_mujoco_execution as module
    ticks = iter(range(0, 1000, 3))
    module_time = SimpleNamespace(monotonic=lambda: next(ticks), monotonic_ns=lambda: 0)
    original = module.time
    module.time = module_time
    try:
        with pytest.raises(RuntimeError, match="TEACHER_DWELL_TIMEOUT"):
            value._fixed_dwell(0.25)
    finally:
        module.time = original


# ---- the final normal_stop (D5) -------------------------------------------------------------------------------------------

def test_the_final_normal_stop_age_comes_from_the_execution_policy_in_a_teacher_run(tmp_path):
    value, _ = release_adapter(tmp_path)
    value._execution_policy = TEACHER_POLICY
    value._release_runtime_policy = None                                   # the release policy is not part of v3
    events = []
    value._publish_teacher_event = lambda kind, payload: events.append((kind, payload))
    value.final_stop_proof_enabled = True
    value._publish_final_normal_stop()
    assert [kind for kind, _ in events] == ["normal_stop"] and "teacher_final_stop_error" not in value._document
    proof = events[0][1]["proof"]
    assert set(proof) >= {"source_clock", "publisher_sequence", "sim_stamp_s"}


# ---- place strategy with fallback (section 4) -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def geometry():
    return ph.cup_geometry_from_scene(PACKAGE / "assets/mujoco/act/scene.xml")


def place_adapter(tmp_path, geometry, measurement):
    value = teacher_adapter(tmp_path)
    value._execution_snapshot_root = PACKAGE
    value._place_geometry = lambda: geometry

    def measure():
        if isinstance(measurement, BaseException):
            raise measurement
        return measurement
    value._measure_place_height = measure
    return value


def place(value):
    from so101_demo.ports.evidence import PoseEvidence
    return value._place_target(State.DESCEND_TO_PLACE, PoseEvidence((0.1, -0.2, HOVER_Z), (0.0, 0.0, 0.0, 1.0)))


NOMINAL = (math.radians(4.04), 0.037454)


def test_a_nominal_measurement_gives_the_tilt_compensated_target_and_a_valid_record(tmp_path, geometry):
    value = place_adapter(tmp_path, geometry, NOMINAL)
    target = place(value)
    record = value._document["place_height"]
    assert record["mode"] == "tilt_compensated" and record["fallback_reason"] is None
    assert target.position_m == (0.1, -0.2, record["target_tcp_z_m"])
    ph.validate_document(record, ph.PlaceHeightPolicy.from_document(TEACHER_POLICY))


@pytest.mark.parametrize("measurement,reason", [
    (ph.PlaceHeightRefused(ph.TILT_UNSTABLE, "no window"), "TILT_UNSTABLE"),
    ((math.radians(7.0), 0.037454), "TILT_OUT_OF_RANGE"),
    ((math.radians(4.04), 0.0385), "K_OUT_OF_BAND"),
    (_JointStateStale(ph.MEASUREMENT_FAILED, "the joint state is not fresh"), "JOINT_STATE_STALE"),
    (RuntimeError("scene parse error"), "MEASUREMENT_FAILED"),
    (ph.PlaceHeightRefused(ph.MEASUREMENT_FAILED, "geometry"), "MEASUREMENT_FAILED"),
])
def test_every_fallback_reason_uses_the_constant_offset_target_and_never_refuses(tmp_path, geometry, measurement, reason):
    value = place_adapter(tmp_path, geometry, measurement)
    target = place(value)
    record = value._document["place_height"]
    assert record["mode"] == "fallback_reference" and record["fallback_reason"] == reason
    assert target.position_m[2] == pytest.approx(HOVER_Z - 0.01325, abs=1e-12) == record["constant_offset_target_tcp_z_m"]
    ph.validate_document(record, ph.PlaceHeightPolicy.from_document(TEACHER_POLICY))


def test_the_target_deviation_and_scene_hash_reasons(tmp_path, geometry):
    # a 3 mm deviation: the measurement implies a target 3 mm from the v1 one when the geometry cup is taller by that much
    taller = replace(geometry, half_height_m=geometry.half_height_m + 0.003)
    value = place_adapter(tmp_path, taller, NOMINAL)
    place(value)
    assert value._document["place_height"]["fallback_reason"] in ("TARGET_DEVIATION", "SCENE_HASH_MISMATCH")
    other = replace(geometry, scene_sha256="0" * 64)
    value = place_adapter(tmp_path, other, NOMINAL)
    place(value)
    record = value._document["place_height"]
    assert record["fallback_reason"] == "SCENE_HASH_MISMATCH"
    ph.validate_document(record, ph.PlaceHeightPolicy.from_document(TEACHER_POLICY))


@pytest.mark.parametrize("failure,code", [
    (TeacherStop("TEACHER_USER_STOP"), "TEACHER_USER_STOP"),
    (RuntimeError("JOINT_STATE_TIMEOUT"), "TEACHER_JOINT_STATE_UNAVAILABLE"),
    (RuntimeError("DYNAMIC_SESSION_MISMATCH"), "SIM_INTEGRITY_SESSION_MISMATCH"),
    (RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT"), "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE")])
def test_a_stop_during_the_measurement_keeps_its_code_and_is_not_a_fallback(tmp_path, geometry, failure, code):
    value = place_adapter(tmp_path, geometry, failure)
    with pytest.raises(Exception) as raised:
        place(value)
    assert value._failure_code(raised.value)[0] == code and "place_height" not in value._document


# ---- process summary ------------------------------------------------------------------------------------------------------

def finish_adapter(tmp_path, *, done=True):
    value = teacher_adapter(tmp_path)
    value._stop_suspended = False
    value._stream_emit = lambda *args, **kwargs: None
    value._stream_manifest_block = lambda: None
    value._capture_failure_evidence = lambda result: {"physical_action_proven_absent": False}
    value._take_teacher_end_observation = lambda: ({"position": [0.0, 0.0, 0.0], "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}, None)
    value._teacher_manifest_fields = lambda *args: {"teacher_execution_status": "COMPLETED", "teacher_task_result": {"result": "PASS"}}
    return value


def result(done=True):
    return SimpleNamespace(status=SimpleNamespace(value="DONE" if done else "ERROR"), current_state=State.DONE,
                           transition_count=1, state_trace=[State.IDLE, State.DONE], failure=None)


def test_finish_builds_the_summary_off_thread_and_stores_it_in_the_manifest(tmp_path):
    value = finish_adapter(tmp_path)
    summary = value._process_summary
    summary.phase_begin("LIFT", 1.0)
    summary.offer_step(500, 1.1, 0.5, 1e-5)
    summary.offer_step(501, 1.102, FORCE_LIMIT_N + 0.5, 1e-5)
    summary.offer_collision(501, 1.102, "table_collision", "upper_arm_collision", -1e-4, 0.4)
    summary.phase_finish("LIFT", 2.0, "SUCCEEDED")
    value._perception_error = {"xy_mm": 1.5, "z_mm": 0.2, "tilt_deg": 0.1}
    value._document["place_height"] = {"mode": "fallback_reference", "fallback_reason": "K_OUT_OF_BAND"}
    value.finish(result())
    document = value._document["teacher_process_summary"]
    assert document["schema"] == "teacher_process_summary_v1" and document["complete"] is True
    assert document["flags"]["ORACLE_CUP_OVERLOAD"] == ["LIFT"] and document["flags"]["ORACLE_COLLISION"] == ["LIFT"]
    assert document["perception_error"]["xy_mm"] == 1.5 and document["place_fallback_reason"] == "K_OUT_OF_BAND"
    assert document["policy"]["cup_pose_source"] == "broker_rgbd" and document["policy"]["verdict_source"] == "sim_truth"


def test_a_summary_that_cannot_be_built_is_an_incomplete_document_not_an_error(tmp_path):
    value = finish_adapter(tmp_path)
    value._process_summary.build = lambda **kwargs: 1 / 0
    value.finish(result())
    document = value._document["teacher_process_summary"]
    assert document["complete"] is False and document["schema"] == "teacher_process_summary_v1"
    assert value._document["status"] == "DONE"


def test_missing_thresholds_and_truncated_world_messages_mark_the_summary_incomplete(tmp_path):
    value = finish_adapter(tmp_path)
    value._process_summary.limits = None
    value._safety_limits = None
    value._safety_limits_error = "TEACHER_SAFETY_LIMITS_INVALID"
    value.observer.truncated_count = 2
    value.finish(result())
    document = value._document["teacher_process_summary"]
    assert document["complete"] is False
    assert {"TEACHER_SAFETY_LIMITS_INVALID", "WORLD_TRUNCATED"} <= set(document["incomplete_reasons"])


def test_a_failed_attempt_still_carries_a_summary(tmp_path):
    value = finish_adapter(tmp_path)
    failed = result(done=False)
    failed.failure = SimpleNamespace(code="MOVEIT_EXECUTION_FAILED")
    value.finish(failed)
    assert value._document["status"] == "ERROR" and value._document["teacher_process_summary"]["schema"] == "teacher_process_summary_v1"


def test_the_activation_taps_the_observer_and_makes_a_sequence_gap_telemetry(tmp_path):
    value = make_adapter(tmp_path)
    value._document = {}
    taps = []
    value.observer.add_tap = taps.append
    value.observer._on_sequence_gap = None
    value._activate_teacher_run()
    assert value._document["schema"] == SCHEMA_TEACHER and len(taps) == 1
    taps[0](evidence(), 1.0)
    assert len(value._process_summary._worlds) == 1
    value.observer._on_sequence_gap(1, 3)
    assert value._process_summary.build()["incomplete_reasons"] == ["WORLD_SEQUENCE_GAP"]


# ---- sustained truncated evidence never ages the control evidence out (review change 1) --------------------------------------------

def real_observer_adapter(tmp_path, monkeypatch):
    """The v3 adapter over the REAL world observer (so the truncated-sample rule is the observer's), a fake monotonic clock."""
    from so101_demo.backends.mujoco import observer as world_module
    monkeypatch.setattr(world_module, "convert_message", lambda message: message)
    value = make_adapter(tmp_path)
    value._execution_policy = TEACHER_POLICY
    value._document = {}
    value._write = lambda: None
    value.observer = world_module.MujocoWorldObserver(SimpleNamespace(create_subscription=lambda *a: object()), "s", max_age_s=0.5,
                                                      subscription_depth=256, monotonic=lambda: value._now[0])
    value._activate_teacher_run()
    value._process_summary.limits = CupSafetyLimits(FORCE_LIMIT_N, COMPRESSION_LIMIT_M)
    return value, world_module


def test_truncated_evidence_lasting_more_than_a_second_does_not_abort_the_teacher_and_marks_the_summary_incomplete(tmp_path, monkeypatch):
    value, _ = real_observer_adapter(tmp_path, monkeypatch)
    value._snapshot = lambda: pytest.fail("the monitor must not block")
    monitor = value._motion_monitor(State.LIFT)
    for index in range(1, 31):                                   # 3.0 s of truncated samples every 0.1 s
        value._now[0] += 0.1
        value._joint_state_received_monotonic_s = value._now[0]
        value.observer.accept(evidence(step=1000 + index, truncated=True), received_at_s=value._now[0])
        monitor()                                                # never raises SIM_INTEGRITY_EVIDENCE_UNAVAILABLE
    document = value._process_summary.build()
    assert document["complete"] is False and "WORLD_TRUNCATED" in document["incomplete_reasons"]
    assert value.observer.truncated_count == 30
    # the same stream is an abort in v1/v2: the observer rejects it, the latest goes stale and 1 s later the run stops
    from so101_demo.backends.mujoco import observer as world_module
    old = make_adapter(tmp_path)
    old.observer = world_module.MujocoWorldObserver(SimpleNamespace(create_subscription=lambda *a: object()), "s", max_age_s=0.5,
                                                    subscription_depth=256, monotonic=lambda: old._now[0])
    old._snapshot = lambda: pytest.fail("the monitor must not block")
    old_monitor = old._motion_monitor(State.LIFT)
    with pytest.raises(TeacherStop):
        for index in range(1, 31):
            old._now[0] += 0.1
            old._joint_state_received_monotonic_s = old._now[0]
            with pytest.raises(world_module.EvidenceRejected):
                old.observer.accept(evidence(step=1000 + index, truncated=True), received_at_s=old._now[0])
            old_monitor()


def test_a_truncated_snapshot_is_usable_for_the_detach_source_check(tmp_path, monkeypatch):
    value, _ = real_observer_adapter(tmp_path, monkeypatch)
    value._now[0] += 0.1
    value.observer.accept(evidence(step=2000, truncated=True), received_at_s=value._now[0])
    sample = value.observer.snapshot()
    assert sample.truncated is True
    value._snapshot = lambda: sample
    value._task_geometry = None                                  # ends right after the source check, which must not name truncation
    with pytest.raises(RuntimeError, match="DYNAMIC_DETACH_SYNC_SOURCE_INVALID"):
        value._detach_or_sync(State.DETACH_MOVEIT)


# ---- fail closed on silent streams (review change 2) -----------------------------------------------------------------------------

def test_a_summary_is_incomplete_when_the_physics_or_contact_stream_never_delivered(tmp_path):
    value = finish_adapter(tmp_path)
    value._process_summary.silence_limit_s = 1.0
    value._physics_hazard_watch = SimpleNamespace(chunks_seen=0)
    value._collision_watch = SimpleNamespace(frames_seen=0)
    value.finish(result())
    reasons = set(value._document["teacher_process_summary"]["incomplete_reasons"])
    assert {"PHYSICS_CHUNKS_NEVER_RECEIVED", "COLLISION_FRAMES_NEVER_RECEIVED", "PHYSICS_STREAM_NEVER_RECEIVED",
            "COLLISION_STREAM_NEVER_RECEIVED"} <= reasons
    assert value._document["teacher_process_summary"]["complete"] is False


def test_a_summary_stays_complete_when_both_streams_delivered(tmp_path):
    value = finish_adapter(tmp_path)
    value._process_summary.silence_limit_s = 1.0
    value._process_summary.note_receipt("physics", value._now[0])
    value._process_summary.note_receipt("collision", value._now[0])
    value._physics_hazard_watch = SimpleNamespace(chunks_seen=3)
    value._collision_watch = SimpleNamespace(frames_seen=3)
    value.finish(result())
    assert value._document["teacher_process_summary"]["complete"] is True


def test_the_activation_sets_the_silence_limit_from_the_execution_policy(tmp_path):
    value = make_adapter(tmp_path)
    value._document = {}
    value._execution_policy = TEACHER_POLICY
    value._activate_teacher_run()
    assert value._process_summary.silence_limit_s == TEACHER_POLICY["state_unavailable_stop_s"] == 1.0
