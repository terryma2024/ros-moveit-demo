"""Teacher-only result contract (Phase A1b): endpoint verdict, manifest v2 and audit-only process checks."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_event_stream import StreamEventSink
from so101_demo.act.general_runtime_policy import load_general_runtime_policy
from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy
from so101_demo.core.domain import ActionStatus, Failure, FailureCategory, State
from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
START = (0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)
SCHEMA_GENERAL = "so101-dynamic-execute"
ARM_AND_GRIPPER = (*RosDynamicMujocoExecution._ARM_JOINTS, "6")


def _template():
    return load_dynamic_pick_template(
        PACKAGE / "config/policies/dynamic_cup_pick/mujoco.yaml",
        expected_backend="mujoco", expected_execution_allowed=True)


def _end_pose():
    """Frozen place target: today's VALIDATE_FINAL_PLACEMENT expected cup pose, resting on the start height."""

    expected = compose_pose(_template().place_tcp_world, inverse_pose(_template().cup_to_tcp_grasp))
    return (expected.values[0], expected.values[1], START[2], *expected.values[3:7])


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _sample(position, quaternion=(0.0, 0.0, 0.0, 1.0), *, time_s, sequence=1, force=0.5,
            left=True, right=True, table=True):
    return SimpleNamespace(
        simulation_time_s=time_s, frame_id="world", simulation_session_id="s", reset_epoch=3,
        publisher_sequence=sequence, simulation_step=sequence * 5, paused=False,
        object_state=SimpleNamespace(
            body="plastic_cup", position_world=tuple(position), orientation_xyzw=tuple(quaternion),
            linear_velocity_world=(0.0, 0.0, 0.0), angular_velocity_world=(0.0, 0.0, 0.0)),
        left_fingertip_contacts=(object(),) if left else (),
        right_fingertip_contacts=(object(),) if right else (),
        maximum_normal_force_n=force,
        other_object_contacts=(SimpleNamespace(
            geom1="bottom_collision", geom2="table_collision", position_world=(0.0, 0.0, 0.1),
            signed_distance_m=-0.0003, normal_force_n=1.0),) if table else ())


def _adapter(*, start=START, joint_speed=0.0):
    adapter = object.__new__(RosDynamicMujocoExecution)
    clock = Clock()
    adapter._clock = clock
    adapter._monotonic = clock
    adapter._document = {"state_events": [], "planning_attempts": [], "final_samples": []}
    adapter._state_events = adapter._document["state_events"]
    adapter._planning_attempts = adapter._document["planning_attempts"]
    adapter._final_samples = adapter._document["final_samples"]
    adapter._write = lambda: None
    adapter._release_marker_sequence = None
    adapter._scene_readback = None
    adapter._session_id, adapter._expected_reset_epoch = "s", 3
    adapter._template = _template()
    adapter._targets = SimpleNamespace(
        input_pose=SimpleNamespace(pose_world=SimpleNamespace(values=start)), reset_epoch=3)
    adapter._teacher_endpoint_policy = load_teacher_endpoint_policy(
        PACKAGE / "config/act/teacher_endpoint.yaml")
    adapter._execution_policy = load_general_runtime_policy(PACKAGE / "config/act/general_runtime_policy.yaml")
    adapter._teacher_policy_files = {"endpoint": {"path": "e", "file_sha256": "1" * 64},
                                     "execution": {"path": "x", "file_sha256": "2" * 64}}
    adapter._teacher_config_error = None
    adapter._initial = None
    adapter._event_sink = StreamEventSink(None)
    adapter._positions = {}
    adapter._joint_state_generation = 1
    adapter._joint_velocities = {name: joint_speed for name in ARM_AND_GRIPPER}
    adapter._joint_state_received_monotonic_s = clock.now

    def progress():
        clock.now += 0.01
        adapter._joint_state_received_monotonic_s = clock.now

    adapter._progress = progress
    adapter._scene_membership = lambda: ([], {"plastic_cup": 13})
    return adapter


def _begin(adapter, start_sample=None):
    """Drive the first workflow state so the Teacher reads its own start pose."""

    start_sample = start_sample or _sample(START[:3], START[3:], time_s=1.0)
    order = []
    adapter._snapshot = lambda: order.append("snapshot") or start_sample
    adapter._command_gripper = lambda state, target, before=None: order.append("gripper")
    result = adapter.perform(State.PREPARE_OPEN_GRIPPER, None)
    return result, order


def _done_result():
    return SimpleNamespace(
        status=SimpleNamespace(value="DONE"), current_state=State.DONE, transition_count=19,
        state_trace=(State.IDLE, State.DONE), failure=None)


def _end_sampler(adapter, position, quaternion=(0.0, 0.0, 0.0, 1.0)):
    state = {"time": 5.0, "sequence": 1000}

    def snapshot():
        state["time"] += 0.1
        state["sequence"] += 1
        return _sample(position, quaternion, time_s=state["time"], sequence=state["sequence"],
                       left=False, right=False)

    adapter._snapshot = snapshot
    return state


def _finished(adapter, position, quaternion=(0.0, 0.0, 0.0, 1.0)):
    _end_sampler(adapter, position, quaternion)
    adapter.finish(_done_result())
    return adapter._document


def _yaw(angle):
    return (0.0, 0.0, math.sin(angle / 2.0), math.cos(angle / 2.0))


def _tilt(angle):
    return (math.sin(angle / 2.0), 0.0, 0.0, math.cos(angle / 2.0))


def test_teacher_only_start_observation_is_read_before_the_first_motion_without_a_recorder():
    adapter = _adapter()

    result, order = _begin(adapter)

    assert result.status is ActionStatus.SUCCEEDED
    assert order == ["snapshot", "gripper"]
    start = adapter._document["teacher_start_observation"]
    assert start["position"] == list(START[:3])
    assert start["object_id"] == "plastic_cup" and start["session_id"] == "s"
    assert start["reset_epoch"] == 3 and start["frame_id"] == "world" and start["simulation_time_s"] == 1.0
    targets = adapter._document["teacher_targets"]
    assert targets["start_target"]["position"] == list(START[:3])
    assert targets["end_target"]["position"] == pytest.approx(list(_end_pose()[:3]))


def test_teacher_only_done_run_with_endpoint_pass_gives_general_pass_and_disabled_data():
    adapter = _adapter()
    _begin(adapter)

    document = _finished(adapter, _end_pose()[:3], _end_pose()[3:])

    assert document["schema"] == SCHEMA_GENERAL and document["schema_version"] == 1
    assert document["status"] == "DONE"
    assert document["teacher_execution_status"] == "COMPLETED"
    task = document["teacher_task_result"]
    assert task["result"] == "PASS" and task["reasons"] == []
    assert task["rule_version"] == "teacher_endpoint"
    assert task["policy_sha256"] == adapter._teacher_endpoint_policy["policy_sha256"]
    assert task["start_observation"] == document["teacher_start_observation"]
    assert task["end_observation"] == document["teacher_end_observation"]
    assert document["act_data_status"] == "DISABLED"
    assert document["process_diagnostics"] == []
    assert document["teacher_policies"]["endpoint"]["file_sha256"] == "1" * 64
    start, end = document["teacher_start_observation"], document["teacher_end_observation"]
    assert end["simulation_time_s"] - start["simulation_time_s"] > 0.5


def test_the_teacher_manifest_never_carries_a_data_verdict_of_its_own():
    """The data verdict is the independent Recorder's (A4c): the Teacher manifest holds only the constant DISABLED."""
    adapter = _adapter()
    _begin(adapter)

    document = _finished(adapter, _end_pose()[:3], _end_pose()[3:])

    assert document["act_data_status"] == "DISABLED"
    assert document["teacher_task_result"]["result"] == "PASS"
    assert not hasattr(adapter, "episode_recorder") and "act_data_invalid" not in document


def test_end_offset_beyond_the_xy_tolerance_is_a_task_fail():
    adapter = _adapter()
    _begin(adapter)
    end = _end_pose()

    document = _finished(adapter, (end[0] + 0.03, end[1], end[2]), end[3:])

    assert document["teacher_execution_status"] == "COMPLETED"
    assert document["teacher_task_result"]["result"] == "FAIL"
    assert document["teacher_task_result"]["reasons"] == ["FINAL_XY_OUT_OF_TOLERANCE"]


def test_a_tipped_cup_at_the_right_place_is_a_task_fail():
    adapter = _adapter()
    _begin(adapter)
    end = _end_pose()

    document = _finished(adapter, end[:3], _tilt(0.5))

    assert document["teacher_task_result"]["result"] == "FAIL"
    assert "FINAL_AXIS_OUT_OF_TOLERANCE" in document["teacher_task_result"]["reasons"]


def test_a_yaw_rotated_upright_cup_still_passes():
    adapter = _adapter()
    _begin(adapter)
    end = _end_pose()

    document = _finished(adapter, end[:3], _yaw(2.0))

    assert document["teacher_task_result"]["result"] == "PASS"


def test_unavailable_end_state_is_unconfirmed_and_never_a_pass():
    adapter = _adapter()
    _begin(adapter)

    def unavailable():
        raise RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT")

    adapter._snapshot = unavailable
    adapter.finish(_done_result())
    document = adapter._document

    assert document["status"] == "DONE"
    assert document["teacher_end_observation"] is None
    assert document["teacher_task_result"]["result"] == "UNCONFIRMED"
    assert any("END_OBSERVATION" in reason for reason in document["teacher_task_result"]["reasons"])


def test_controllers_that_never_stop_leave_the_end_observation_unconfirmed():
    adapter = _adapter(joint_speed=0.5)
    _begin(adapter)
    calls = []
    _end_sampler(adapter, _end_pose()[:3], _end_pose()[3:])
    original = adapter._snapshot
    adapter._snapshot = lambda: calls.append(1) or original()

    adapter.finish(_done_result())

    assert calls == []  # the single snapshot is never taken before the stop is confirmed
    result = adapter._document["teacher_task_result"]
    assert result["result"] == "UNCONFIRMED"
    assert any("CONTROLLER_STOP" in reason for reason in result["reasons"])


def test_the_end_snapshot_waits_the_configured_settle_in_simulation_time():
    adapter = _adapter()
    _begin(adapter)
    state = _end_sampler(adapter, _end_pose()[:3], _end_pose()[3:])

    adapter.finish(_done_result())

    end = adapter._document["teacher_end_observation"]
    assert end["simulation_time_s"] >= 5.1 + 0.5 - 1e-9
    assert state["time"] == pytest.approx(end["simulation_time_s"])


def test_coincident_targets_refuse_before_any_motion_and_record_the_config_code():
    adapter = _adapter(start=(*_end_pose()[:3], 0.0, 0.0, 0.0, 1.0))

    result, order = _begin(adapter)

    assert result.status is ActionStatus.FAILED
    assert result.failure.code == "TEACHER_ENDPOINT_TARGETS_COINCIDENT"
    assert "gripper" not in order
    adapter.finish(SimpleNamespace(
        status=SimpleNamespace(value="ERROR"), current_state=State.ERROR, transition_count=1,
        state_trace=(State.IDLE, State.ERROR), failure=result.failure))
    document = adapter._document
    assert document["teacher_execution_status"] == "FAILED"
    assert document["teacher_task_result"]["result"] == "UNCONFIRMED"
    assert any("TEACHER_ENDPOINT_TARGETS_COINCIDENT" in reason
               for reason in document["teacher_task_result"]["reasons"])


def test_missing_policy_files_refuse_before_any_motion():
    adapter = _adapter()
    adapter._teacher_config_error = "TEACHER_ENDPOINT_POLICY_INVALID: cannot read the document"

    result, order = _begin(adapter)

    assert result.status is ActionStatus.FAILED
    assert result.failure.code == "TEACHER_ENDPOINT_POLICY_INVALID"
    assert "gripper" not in order


def test_a_failed_execution_is_never_a_pass_even_with_a_perfect_cup():
    adapter = _adapter()
    _begin(adapter)
    _end_sampler(adapter, _end_pose()[:3], _end_pose()[3:])

    adapter.finish(SimpleNamespace(
        status=SimpleNamespace(value="ERROR"), current_state=State.ERROR, transition_count=3,
        state_trace=(State.IDLE, State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT, State.ERROR),
        failure=Failure(FailureCategory.EXECUTION, "DYNAMIC_FORCE_LIMIT_EXCEEDED", "force")))

    document = adapter._document
    assert document["teacher_execution_status"] == "STOPPED_SAFETY"
    assert document["teacher_task_result"]["result"] == "UNCONFIRMED"
    assert document["teacher_end_observation"] is None


@pytest.mark.parametrize(("code", "expected"), [
    ("DYNAMIC_FORCE_LIMIT_EXCEEDED", "STOPPED_SAFETY"),
    ("DYNAMIC_RELEASE_SUPPORT_NOT_PROVED", "STOPPED_SAFETY"),
    ("MOVEIT_PLAN_TIMEOUT", "FAILED"),
    ("GRIPPER_RESULT_TIMEOUT", "INDETERMINATE"),
])
def test_error_codes_map_to_the_execution_status(code, expected):
    adapter = _adapter()
    _begin(adapter)
    adapter._snapshot = lambda: _sample(START[:3], START[3:], time_s=9.0)

    adapter.finish(SimpleNamespace(
        status=SimpleNamespace(value="ERROR"), current_state=State.ERROR, transition_count=3,
        state_trace=(State.IDLE, State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT, State.ERROR),
        failure=Failure(FailureCategory.EXECUTION, code, "x")))

    assert adapter._document["teacher_execution_status"] == expected


# ---- D3: process items are audit-only ----------------------------------------------------------------------

def _codes(adapter):
    return [item["code"] for item in adapter._document.get("process_diagnostics", [])]


def test_early_table_contact_while_carrying_is_a_diagnostic_and_never_cancels():
    adapter = _adapter()
    adapter._monitor_sample = lambda: _sample((0.0, 0.0, 0.2), time_s=2.0, table=True)

    adapter._motion_monitor(State.MOVE_ABOVE_PLACE)()

    entry, = adapter._document["process_diagnostics"]
    assert entry["code"] == "DYNAMIC_EARLY_TABLE_CONTACT" and entry["state"] == "MOVE_ABOVE_PLACE"
    assert entry["audit_only"] is True
    assert entry["contacts"]["other"][0]["geom2"] == "table_collision"
    assert "monitor_violation" not in adapter._document


def test_sustained_carry_bilateral_loss_is_a_diagnostic_and_never_cancels():
    adapter = _adapter()
    adapter._monitor_sample = lambda: _sample((0.0, 0.0, 0.2), time_s=2.0, left=False, right=False, table=False)
    monitor = adapter._motion_monitor(State.LIFT)

    monitor()
    adapter._clock.now += 0.2
    monitor()
    monitor()

    assert _codes(adapter) == ["DYNAMIC_CARRY_BILATERAL_LOST"]
    assert adapter._document["process_diagnostics"][0]["count"] >= 1
    assert "monitor_violation" not in adapter._document


def test_preclose_cup_displacement_is_a_diagnostic_and_never_cancels():
    adapter = _adapter()
    adapter._initial = _sample((0.0, 0.0, 0.165), time_s=1.0, table=False)
    adapter._monitor_sample = lambda: _sample((0.02, 0.0, 0.165), time_s=2.0, table=False, left=False, right=False)

    adapter._motion_monitor(State.DESCEND)()

    entry, = adapter._document["process_diagnostics"]
    assert entry["code"] == "DYNAMIC_PRECLOSE_CUP_MOVED"
    assert entry["displacement_m"] == pytest.approx(0.02)


def test_the_force_limit_still_cancels_and_is_a_monitor_violation_not_a_diagnostic():
    adapter = _adapter()
    adapter._positions = {name: 0.0 for name in ARM_AND_GRIPPER}
    adapter._monitor_sample = lambda: _sample((0.0, 0.0, 0.2), time_s=2.0, force=12.0)

    with pytest.raises(RuntimeError, match="DYNAMIC_FORCE_LIMIT_EXCEEDED"):
        adapter._motion_monitor(State.LIFT)()

    assert adapter._document["monitor_violation"]["reason"] == "DYNAMIC_FORCE_LIMIT_EXCEEDED"
    assert _codes(adapter) == []


def test_wait_grasp_stable_timeout_is_a_diagnostic_and_the_state_succeeds():
    adapter = _adapter()
    adapter._initial = object()
    sample = _sample((0.0, 0.0, 0.165), time_s=2.0, left=False, right=False)
    adapter._snapshot = lambda: sample

    def timeout(*_args, **_kwargs):
        raise RuntimeError("DYNAMIC_STABLE_STATE_TIMEOUT")

    adapter._wait_stable = timeout
    adapter._record = lambda *args, **kwargs: None

    result = adapter.perform(State.WAIT_GRASP_STABLE, None)

    assert result.status is ActionStatus.SUCCEEDED
    assert _codes(adapter) == ["DYNAMIC_STABLE_STATE_TIMEOUT"]


def test_failed_physical_grasp_verification_is_a_diagnostic_and_the_transition_proceeds():
    adapter = _adapter()
    adapter._initial = object()
    adapter._before_micro_lift = None
    adapter._snapshot = lambda: _sample((0.0, 0.0, 0.165), time_s=2.0, left=False, right=False)
    adapter._record = lambda *args, **kwargs: None

    result = adapter.perform(State.VERIFY_PHYSICAL_GRASP, None)

    assert result.status is ActionStatus.SUCCEEDED
    assert _codes(adapter) == ["DYNAMIC_PHYSICAL_GRASP_NOT_PROVED"]
    from so101_demo.core.workflow import SO101_WORKFLOW
    assert SO101_WORKFLOW.transitions[State.VERIFY_PHYSICAL_GRASP][0] is State.ATTACH_MOVEIT


def test_release_settle_window_failure_is_a_diagnostic_observation_and_the_state_succeeds():
    adapter = _adapter()
    adapter._initial = object()
    sample = _sample((0.0, 0.0, 0.165), time_s=2.0, left=True)
    adapter._snapshot = lambda: sample

    def timeout(*_args, **_kwargs):
        raise RuntimeError("DYNAMIC_STABLE_STATE_TIMEOUT")

    adapter._wait_stable = timeout
    adapter._record = lambda *args, **kwargs: None

    result = adapter.perform(State.WAIT_RELEASE_SETTLE, None)

    assert result.status is ActionStatus.SUCCEEDED
    assert _codes(adapter) == ["DYNAMIC_SETTLE_WINDOW_NOT_MET"]
    assert len(adapter._final_samples) == 1


def test_final_placement_mismatch_is_a_diagnostic_and_the_state_succeeds():
    adapter = _adapter()
    adapter._initial = object()
    adapter._snapshot = lambda: _sample((0.3, 0.3, 0.3), time_s=2.0, table=False)
    adapter._record = lambda *args, **kwargs: None

    result = adapter.perform(State.VALIDATE_FINAL_PLACEMENT, None)

    assert result.status is ActionStatus.SUCCEEDED
    entry, = adapter._document["process_diagnostics"]
    assert entry["code"] == "DYNAMIC_FINAL_PLACEMENT_NOT_PROVED"
    assert entry["facts"]["table_contact"] is False


def test_release_support_before_open_still_refuses_an_unsupported_held_cup():
    adapter = _adapter()
    adapter._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    unsupported = _sample((0.0, 0.0, 0.2), time_s=2.0, left=False, right=True, table=False)

    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SUPPORT_NOT_PROVED"):
        adapter._require_supported_bilateral(unsupported)


def test_release_open_without_a_fresh_preflight_authorization_still_refuses():
    adapter = _adapter()
    adapter._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    adapter._session_id, adapter._expected_reset_epoch, adapter._attempt_id = "s", 1, "a"
    adapter._release_authorization = None
    adapter._command_gripper = lambda *args, **kwargs: pytest.fail("the gripper must not open")

    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_PREFLIGHT_REQUIRED"):
        adapter._open_supported_gripper(State.OPEN_GRIPPER)


# ---- policy loading from the share config dir the runtime already uses ---------------------------------------

def test_teacher_policies_load_from_the_share_config_dir_and_record_path_and_sha256():
    import hashlib

    adapter = object.__new__(RosDynamicMujocoExecution)

    adapter._load_teacher_policies(PACKAGE / "assets/mujoco/so101.urdf")

    assert adapter._teacher_config_error is None
    endpoint = adapter._teacher_policy_files["endpoint"]
    execution = adapter._teacher_policy_files["execution"]
    assert endpoint["path"] == str(PACKAGE / "config/act/teacher_endpoint.yaml")
    assert endpoint["file_sha256"] == hashlib.sha256(
        (PACKAGE / "config/act/teacher_endpoint.yaml").read_bytes()).hexdigest()
    assert execution["path"] == str(PACKAGE / "config/act/general_runtime_policy.yaml")
    assert endpoint["policy_sha256"] == adapter._teacher_endpoint_policy["policy_sha256"]
    assert execution["policy_sha256"] == adapter._execution_policy["policy_sha256"]


def test_missing_or_invalid_policy_files_become_a_config_error_not_a_crash(tmp_path):
    adapter = object.__new__(RosDynamicMujocoExecution)
    adapter._load_teacher_policies(tmp_path / "assets/mujoco/so101.urdf")
    assert adapter._teacher_config_error.startswith("TEACHER_POLICY_UNAVAILABLE")
    assert adapter._teacher_endpoint_policy is None

    config = tmp_path / "config/act"
    config.mkdir(parents=True)
    (config / "teacher_endpoint.yaml").write_text("kind: nope\n")
    (config / "general_runtime_policy.yaml").write_bytes(
        (PACKAGE / "config/act/general_runtime_policy.yaml").read_bytes())
    adapter._load_teacher_policies(tmp_path / "assets/mujoco/so101.urdf")
    assert adapter._teacher_config_error.startswith("TEACHER_ENDPOINT_POLICY_INVALID")
