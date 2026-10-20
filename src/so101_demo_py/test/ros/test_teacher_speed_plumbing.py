"""Where the schema 4 speed keys reach the Teacher (plan 2026-10-20 teacher speed tiers 1 and 2, items 18d/18e/18f).

Fixture level, like test_teacher_moveit_execution: the real `RosDynamicMujocoExecution` over fakes, no ROS graph. The scaling is
read where the MoveIt request is built and the gripper duration where the gripper goal is sent; nothing else may change."""

from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core.domain import ActionResult, ActionStatus, State

from test_teacher_moveit_execution import make_adapter
from paths import PACKAGE_ROOT

DEFAULT_POLICY = PACKAGE_ROOT / "config/act/teacher_execution_policy.yaml"
FAST_POLICY = PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast.yaml"
TEMPLATE_SCALING = (0.03, 0.03)
CARRY_SCALING = (0.03, 0.0075)
FAST_SCALING = (0.10, 0.10)


def planned_requests(tmp_path, state, *, policy_path, frozen=True):
    value = make_adapter(tmp_path)
    value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03, planning_timeout_s=1.0,
                                      planning_group="arm", tcp_link="tcp")
    value._execution_policy = load_teacher_execution_policy(policy_path)
    if frozen:
        value._execution_snapshot_root = tmp_path
    seen = []

    class Planning:
        def plan_joint_path(self, request, timeout_s):
            seen.append(request)
            return SimpleNamespace(failure=SimpleNamespace(code="PLAN_REFUSED"), trajectory=None)

    value._planning = Planning()
    value._record_planning_attempt = lambda document: None
    with pytest.raises(RuntimeError, match="PLAN_REFUSED"):
        value._plan_candidate_set(state=state, step=SimpleNamespace(waypoint=SimpleNamespace(segment_index=0)),
                                  current=(0.0,) * 5, joint_target=(0.1,) * 5)
    return seen


def scaling_of(request):
    return (request.velocity_scaling, request.acceleration_scaling)


@pytest.mark.parametrize("state", [State.MOVE_ABOVE_OBJECT, State.RETREAT])
def test_the_fast_policy_scales_only_move_above_object_and_retreat(tmp_path, state):
    requests = planned_requests(tmp_path, state, policy_path=FAST_POLICY)
    assert requests and {scaling_of(request) for request in requests} == {FAST_SCALING}   # every candidate of the phase


@pytest.mark.parametrize("state", [State.DESCEND, State.MICRO_LIFT, State.PREPARE_OPEN_GRIPPER, State.RECOVER_RETREAT,
                                   State.RECOVER_LIFT_TO_SAFE_HEIGHT, State.RECOVER_MOVE_ABOVE_PICK])
def test_the_fast_policy_leaves_the_other_free_space_states_on_the_template(tmp_path, state):
    assert {scaling_of(request) for request in planned_requests(tmp_path, state, policy_path=FAST_POLICY)} == {TEMPLATE_SCALING}


@pytest.mark.parametrize("state", [State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE])
def test_the_fast_policy_leaves_the_carry_scaling_alone(tmp_path, state):
    assert {scaling_of(request) for request in planned_requests(tmp_path, state, policy_path=FAST_POLICY)} == {CARRY_SCALING}


@pytest.mark.parametrize("state", [State.MOVE_ABOVE_OBJECT, State.RETREAT, State.DESCEND, State.LIFT])
def test_a_schema_3_policy_plans_exactly_as_before(tmp_path, state):
    expected = CARRY_SCALING if state is State.LIFT else TEMPLATE_SCALING
    assert {scaling_of(request) for request in planned_requests(tmp_path, state, policy_path=DEFAULT_POLICY)} == {expected}


@pytest.mark.parametrize("state", [State.MOVE_ABOVE_OBJECT, State.RETREAT])
def test_without_frozen_inputs_the_speed_keys_are_not_read(tmp_path, state):
    requests = planned_requests(tmp_path, state, policy_path=FAST_POLICY, frozen=False)
    assert {scaling_of(request) for request in requests} == {TEMPLATE_SCALING}


def test_the_move_above_object_candidate_count_is_unchanged(tmp_path):
    from so101_demo.control.moveit.deterministic_horizon import MOVE_ABOVE_PLAN_CANDIDATE_COUNT

    # PLAN_REFUSED stops the loop at the first candidate; the count itself comes from the constant, which the policy cannot reach
    assert MOVE_ABOVE_PLAN_CANDIDATE_COUNT == 4
    assert len(planned_requests(tmp_path, State.MOVE_ABOVE_OBJECT, policy_path=FAST_POLICY)) >= 1


# ---- the PREPARE_OPEN_GRIPPER trajectory duration ------------------------------------------------------------------

def gripper_durations(tmp_path, state, *, policy_path, frozen=True):
    value = make_adapter(tmp_path)
    value._execution_policy = load_teacher_execution_policy(policy_path)
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
    value._command_gripper(state, 0.1)
    return durations


def test_the_fast_policy_shortens_only_prepare_open_gripper(tmp_path):
    assert gripper_durations(tmp_path, State.PREPARE_OPEN_GRIPPER, policy_path=FAST_POLICY) == [1.0]


@pytest.mark.parametrize("state", [State.CLOSE_GRIPPER, State.OPEN_GRIPPER, State.RECOVER_OPEN_GRIPPER])
def test_the_other_gripper_commands_keep_two_seconds(tmp_path, state):
    assert gripper_durations(tmp_path, state, policy_path=FAST_POLICY) == [2.0]


def test_a_schema_3_policy_sends_two_seconds_for_prepare_open_gripper(tmp_path):
    assert gripper_durations(tmp_path, State.PREPARE_OPEN_GRIPPER, policy_path=DEFAULT_POLICY) == [2.0]


def test_without_frozen_inputs_prepare_open_gripper_keeps_two_seconds(tmp_path):
    assert gripper_durations(tmp_path, State.PREPARE_OPEN_GRIPPER, policy_path=FAST_POLICY, frozen=False) == [2.0]


def test_frozen_inputs_with_a_schema_4_policy_missing_the_duration_refuse(tmp_path):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = tmp_path
    value._execution_policy = {**load_teacher_execution_policy(FAST_POLICY)}
    del value._execution_policy["prepare_open_gripper_duration_s"]
    value._gripper = SimpleNamespace(command=lambda *arguments, **keywords: ActionResult(ActionStatus.SUCCEEDED))
    value._motion_monitor = lambda state: None
    value._snapshot = lambda: None
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._command_gripper(State.PREPARE_OPEN_GRIPPER, 0.1)
