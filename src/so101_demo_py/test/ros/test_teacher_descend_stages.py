"""Round-2 plan S2: DESCEND in two stages and the OPEN_GRIPPER duration under a schema 5 Teacher policy.

Fixture level, with the real repository URDF and the real mujoco policy template, like test_pick_horizon_precompute. Schema 3 and
4 policies keep today's six interpolated DESCEND segments at the template scaling and the 2.0 s OPEN_GRIPPER."""

import math
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core.domain import ActionResult, ActionStatus, State

from test_pick_horizon_precompute import (  # noqa: F401 - fixtures
    START, ik, targets, teacher, template)
from test_teacher_moveit_execution import make_adapter
from paths import PACKAGE_ROOT

CONFIG = PACKAGE_ROOT / "config/act"
DESCEND010 = CONFIG / "teacher_execution_policy_side_wrist_fast_r2_descend010.yaml"
DESCEND020 = CONFIG / "teacher_execution_policy_side_wrist_fast_r2_descend020.yaml"
CARRY015 = CONFIG / "teacher_execution_policy_side_wrist_fast_carry015.yaml"
TEMPLATE_SCALING = (0.03, 0.03)


def distance(a, b):
    return math.dist(a.position_m, b.position_m)


# ---- the DESCEND horizon ----------------------------------------------------------------------------------------------------

def test_schema_5_descend_is_an_approach_to_the_final_distance_and_the_grasp(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    steps = value._motion_horizon(State.DESCEND, [], START)
    above, grasp = targets.for_state(State.MOVE_ABOVE_OBJECT), targets.for_state(State.DESCEND)
    assert [step.waypoint.state for step in steps] == [State.DESCEND] * 2
    assert [step.waypoint.segment_index for step in steps] == [1, 2]
    approach, final = (step.waypoint.target for step in steps)
    assert distance(approach, grasp) == pytest.approx(0.02, abs=1e-12)
    assert final == grasp
    # on the descend line: the approach point is collinear with the pregrasp and the grasp pose, between them
    length = distance(above, grasp)
    assert distance(above, approach) == pytest.approx(length - 0.02, abs=1e-12)
    # the other pick-prefix states are untouched
    assert len(value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)) == 6
    assert len(value._pick_horizon_steps[State.MICRO_LIFT]) == 1 and len(value._pick_horizon_steps[State.LIFT]) == 1


def test_the_final_distance_follows_the_policy_value(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    value._execution_policy["descend_final_distance_m"] = 0.035
    steps = value._motion_horizon(State.DESCEND, [], START)
    grasp = targets.for_state(State.DESCEND)
    assert distance(steps[0].waypoint.target, grasp) == pytest.approx(0.035, abs=1e-12) and len(steps) == 2


def test_when_the_start_is_within_the_final_distance_only_the_final_motion_runs(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    grasp = targets.for_state(State.DESCEND)
    value._execution_policy["descend_final_distance_m"] = distance(targets.for_state(State.MOVE_ABOVE_OBJECT), grasp) + 0.001
    steps = value._motion_horizon(State.DESCEND, [], START)
    assert [step.waypoint.target for step in steps] == [grasp] and steps[0].waypoint.segment_index == 1


@pytest.mark.parametrize("policy_path", [CARRY015, CONFIG / "teacher_execution_policy.yaml"])
def test_a_schema_3_or_4_policy_keeps_the_six_interpolated_descend_segments(tmp_path, ik, template, targets, policy_path):
    value = teacher(tmp_path, ik, template, targets, policy_path=policy_path)
    steps = value._motion_horizon(State.DESCEND, [], START)
    above, grasp = targets.for_state(State.MOVE_ABOVE_OBJECT), targets.for_state(State.DESCEND)
    assert [step.waypoint.segment_index for step in steps] == [1, 2, 3, 4, 5, 6]
    assert distance(steps[-1].waypoint.target, grasp) < 1e-12
    assert distance(steps[0].waypoint.target, above) == pytest.approx(distance(above, grasp) / 6, abs=1e-12)


def test_the_schema_5_precompute_computes_the_two_stage_horizon(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    value._start_pick_horizon_precompute()
    value._pick_horizon_precompute.thread.join()
    solved = value._ik.solves
    steps = value._motion_horizon(State.DESCEND, [], START)
    assert value._ik.solves == solved and value._document["pick_prefix_precompute"]["status"] == "USED"
    assert len(steps) == 2


# ---- the scaling of each stage ----------------------------------------------------------------------------------------------

def stage_scalings(value, state, waypoint_targets, *, grasp=None):
    seen = []

    class Planning:
        def plan_joint_path(self, request, timeout_s):
            seen.append((request.velocity_scaling, request.acceleration_scaling))
            return SimpleNamespace(failure=SimpleNamespace(code="PLAN_REFUSED"), trajectory=None)

    value._planning = Planning()
    value._record_planning_attempt = lambda document: None
    value._descend_grasp_target = grasp
    for waypoint_target in waypoint_targets:
        step = SimpleNamespace(waypoint=SimpleNamespace(segment_index=0, target=waypoint_target))
        with pytest.raises(RuntimeError, match="PLAN_REFUSED"):
            value._plan_candidate_set(state=state, step=step, current=(0.0,) * 5, joint_target=(0.1,) * 5)
    return seen


@pytest.mark.parametrize("policy_path,approach", [(DESCEND010, (0.10, 0.10)), (DESCEND020, (0.20, 0.20))])
def test_the_approach_stage_uses_the_approach_scaling_and_the_final_stage_keeps_today_s(tmp_path, ik, template, targets, policy_path, approach):
    value = teacher(tmp_path, ik, template, targets, policy_path=policy_path)
    steps = value._motion_horizon(State.DESCEND, [], START)
    grasp = targets.for_state(State.DESCEND)
    seen = stage_scalings(value, State.DESCEND, [step.waypoint.target for step in steps], grasp=grasp)
    assert seen == [approach, TEMPLATE_SCALING]


def test_the_final_only_stage_uses_today_s_scaling(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    grasp = targets.for_state(State.DESCEND)
    assert stage_scalings(value, State.DESCEND, [grasp], grasp=grasp) == [TEMPLATE_SCALING]


@pytest.mark.parametrize("policy_path", [CARRY015, CONFIG / "teacher_execution_policy.yaml"])
def test_a_schema_3_or_4_policy_plans_every_descend_segment_at_the_template(tmp_path, ik, template, targets, policy_path):
    value = teacher(tmp_path, ik, template, targets, policy_path=policy_path)
    above = targets.for_state(State.MOVE_ABOVE_OBJECT)
    # schema 3 and 4 steps carry no stage; nothing may read the target of the step
    seen = stage_scalings(value, State.DESCEND, [above, targets.for_state(State.DESCEND)], grasp=None)
    assert seen == [TEMPLATE_SCALING] * 2


def test_without_frozen_inputs_the_descend_keys_are_not_read(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010, frozen=False)
    above = targets.for_state(State.MOVE_ABOVE_OBJECT)
    assert stage_scalings(value, State.DESCEND, [above], grasp=targets.for_state(State.DESCEND)) == [TEMPLATE_SCALING]


@pytest.mark.parametrize("state", [State.MOVE_ABOVE_OBJECT, State.MICRO_LIFT, State.RETREAT, State.RECOVER_DESCEND_TO_PICK])
def test_the_descend_keys_scale_no_other_state(tmp_path, ik, template, targets, state):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    seen = stage_scalings(value, state, [targets.for_state(State.MOVE_ABOVE_OBJECT)], grasp=targets.for_state(State.DESCEND))
    expected = (0.10, 0.10) if state in (State.MOVE_ABOVE_OBJECT, State.RETREAT) else TEMPLATE_SCALING
    assert set(seen) == {expected}


def test_a_schema_5_policy_without_the_approach_scaling_refuses(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets, policy_path=DESCEND010)
    del value._execution_policy["descend_approach_velocity_scaling"]
    value._descend_grasp_target = targets.for_state(State.DESCEND)
    step = SimpleNamespace(waypoint=SimpleNamespace(segment_index=0, target=targets.for_state(State.MOVE_ABOVE_OBJECT)))
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._planning_scaling(State.DESCEND, step)


# ---- _motion issues one request per stage ---------------------------------------------------------------------------------

def run_descend(tmp_path, ik, template, targets, policy_path, **policy_changes):
    value = teacher(tmp_path, ik, template, targets, policy_path=policy_path)
    value._execution_policy.update(policy_changes)
    issued = []

    def plan(*, state, step, current, joint_target):
        issued.append(SimpleNamespace(scaling=value._planning_scaling(state, step), target=step.waypoint.target))
        trajectory = SimpleNamespace(joint_trajectory=SimpleNamespace(points=[]))
        return SimpleNamespace(trajectory=trajectory), []

    value._plan_candidate_set = plan
    value._execute_planned = lambda trajectory, state, monitor: ActionResult(ActionStatus.SUCCEEDED)
    value._check_stop = lambda: None
    value._snapshot = lambda: None
    value._record = lambda *arguments, **keywords: None
    value._record_planning_attempt = lambda document: None
    value._motion_monitor = lambda state: None
    value._joint_state_source_stamp_ns = 0
    value._motion(State.DESCEND, targets.for_state(State.DESCEND))
    return issued


def test_a_schema_5_descend_issues_two_motion_requests(tmp_path, ik, template, targets):
    issued = run_descend(tmp_path, ik, template, targets, DESCEND010)
    grasp = targets.for_state(State.DESCEND)
    assert [item.scaling for item in issued] == [(0.10, 0.10), TEMPLATE_SCALING]
    assert distance(issued[0].target, grasp) == pytest.approx(0.02, abs=1e-12) and issued[1].target == grasp


def test_a_schema_5_descend_within_the_final_distance_issues_one_motion_request(tmp_path, ik, template, targets):
    grasp = targets.for_state(State.DESCEND)
    near = distance(targets.for_state(State.MOVE_ABOVE_OBJECT), grasp) + 0.001
    issued = run_descend(tmp_path, ik, template, targets, DESCEND010, descend_final_distance_m=near)
    assert [(item.scaling, item.target) for item in issued] == [(TEMPLATE_SCALING, grasp)]


def test_a_schema_4_descend_issues_the_six_motion_requests_it_always_did(tmp_path, ik, template, targets):
    issued = run_descend(tmp_path, ik, template, targets, CARRY015)
    assert [item.scaling for item in issued] == [TEMPLATE_SCALING] * 6


# ---- the OPEN_GRIPPER duration ----------------------------------------------------------------------------------------------

def gripper_duration(tmp_path, state, *, policy_path, frozen=True, **policy_changes):
    value = make_adapter(tmp_path)
    value._execution_policy = {**load_teacher_execution_policy(policy_path), **policy_changes}
    if frozen:
        value._execution_snapshot_root = tmp_path
    durations = []

    def command(target, duration_s, timeout_s, **keywords):
        durations.append(duration_s)
        return ActionResult(ActionStatus.SUCCEEDED)

    value._gripper = SimpleNamespace(command=command)
    value._snapshot = lambda: None
    value._record = lambda *arguments, **keywords: None
    value._motion_monitor = lambda state: None
    value._check_selected_release_freshness = lambda before: None
    value._command_gripper(state, 0.1)
    return durations


def test_open_gripper_uses_the_schema_5_duration(tmp_path):
    assert gripper_duration(tmp_path, State.OPEN_GRIPPER, policy_path=DESCEND010) == [1.0]
    assert gripper_duration(tmp_path, State.OPEN_GRIPPER, policy_path=DESCEND010, open_gripper_duration_s=1.5) == [1.5]


@pytest.mark.parametrize("policy_path", [CARRY015, CONFIG / "teacher_execution_policy.yaml"])
def test_open_gripper_keeps_two_seconds_under_schema_3_and_4(tmp_path, policy_path):
    assert gripper_duration(tmp_path, State.OPEN_GRIPPER, policy_path=policy_path) == [2.0]


def test_open_gripper_keeps_two_seconds_without_frozen_inputs(tmp_path):
    assert gripper_duration(tmp_path, State.OPEN_GRIPPER, policy_path=DESCEND010, frozen=False) == [2.0]


@pytest.mark.parametrize("state", [State.CLOSE_GRIPPER, State.RECOVER_OPEN_GRIPPER])
def test_close_gripper_and_the_recovery_open_keep_two_seconds(tmp_path, state):
    assert gripper_duration(tmp_path, state, policy_path=DESCEND010) == [2.0]


def test_prepare_open_gripper_still_uses_its_own_duration(tmp_path):
    assert gripper_duration(tmp_path, State.PREPARE_OPEN_GRIPPER, policy_path=DESCEND010, prepare_open_gripper_duration_s=0.7) == [0.7]


def test_a_schema_5_policy_missing_the_open_duration_refuses(tmp_path):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = tmp_path
    value._execution_policy = {**load_teacher_execution_policy(DESCEND010)}
    del value._execution_policy["open_gripper_duration_s"]
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._gripper_duration_s(State.OPEN_GRIPPER)
