"""Tier 1 sequencing (plan 2026-10-20 item 18b): the pick-prefix IK horizon of the Teacher is computed during PREPARE_OPEN_GRIPPER,
so the first MOVE_ABOVE_OBJECT goal does not wait for it (1.84 s of rows in sealed EXP-625).

Fixture level, with the real repository URDF and the real mujoco policy template. The horizon is a pure function of its start joint
state; the precompute starts from the state at PREPARE_OPEN and is reused only when the state at the first goal is within the
declared tolerance, otherwise the horizon is computed again from the state at the goal (today's behaviour). Nothing here reads a
campaign on disk."""

import json
import threading
from types import SimpleNamespace

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.control.moveit.deterministic_horizon import (
    HorizonWaypoint, interpolated_move_above_waypoints, solve_horizon, solve_pick_prefix_horizon)
from so101_demo.control.moveit.underactuated_ik import UnderactuatedPoseIk
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template
from so101_demo.core.task_geometry import Pose7
from so101_demo.ros.dynamic_execution.planning import PICK_HORIZON_REUSE_MAX_START_DELTA_RAD
from so101_demo.ros.dynamic_execution.safety import MotionSafety
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

from test_teacher_moveit_execution import make_adapter
from paths import PACKAGE_ROOT

URDF = PACKAGE_ROOT / "assets/mujoco/so101.urdf"
POLICY = PACKAGE_ROOT / "config/policies/dynamic_cup_pick/mujoco.yaml"
DEFAULT_POLICY = PACKAGE_ROOT / "config/act/teacher_execution_policy.yaml"
FAST_POLICY = PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast.yaml"
JOINTS = ("1", "2", "3", "4", "5")
START = (2.7e-07, 0.00052866, 0.00041416, 0.00013737, 7.1e-11)
PICK_STATES = (State.MOVE_ABOVE_OBJECT, State.DESCEND, State.MICRO_LIFT, State.LIFT)


@pytest.fixture(scope="module")
def template():
    return load_dynamic_pick_template(POLICY, expected_backend="mujoco")


@pytest.fixture(scope="module")
def ik(template):
    return UnderactuatedPoseIk.from_urdf(URDF, JOINTS, template.planning_frame, template.tcp_link)


@pytest.fixture(scope="module")
def targets(template):
    return resolve_motion_targets(CupPoseSample("world", 1, 0.0, Pose7((0.051023, -0.339445, 0.165, 0.0, 0.0, 0.0, 1.0))), template)


def legacy_document(ik, template, targets, current):
    """The pick-prefix computation exactly as `_motion_horizon` had it inline before the precompute existed."""
    above, descend = targets.for_state(State.MOVE_ABOVE_OBJECT), targets.for_state(State.DESCEND)
    waypoints = list(interpolated_move_above_waypoints(ik, current, above))
    waypoints.extend(HorizonWaypoint(State.DESCEND, index, MotionSafety._interpolate_pose(above, descend, index / 6.0))
                     for index in range(1, 7))
    waypoints.extend((HorizonWaypoint(State.MICRO_LIFT, 0, targets.for_state(State.MICRO_LIFT)),
                      HorizonWaypoint(State.LIFT, 0, targets.for_state(State.LIFT))))
    result = solve_horizon(ik, tuple(waypoints), current, position_tolerance_m=template.position_tolerance_m,
                           orientation_tolerance_rad=max(template.orientation_tolerance_rad), beam_width=3)
    document = result.to_document()
    document.update(selection_reason="minimum deterministic cumulative score among complete beam paths",
                    admitted=bool(result.paths))
    return document


def canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


@pytest.fixture(scope="module")
def baseline(ik, template, targets):
    return legacy_document(ik, template, targets, START)


class CountingIk:
    """Delegates to the real solver and counts the solves (and can be told to fail outside the per-candidate rejections)."""

    def __init__(self, real):
        self._real, self.solves, self.fail = real, 0, None

    def solve(self, *arguments, **keywords):
        self.solves += 1
        return self._real.solve(*arguments, **keywords)

    def forward(self, positions):
        if self.fail is not None:
            raise self.fail
        return self._real.forward(positions)

    def __getattr__(self, name):
        return getattr(self._real, name)


def teacher(tmp_path, ik, template, targets, *, policy_path=FAST_POLICY, current=START, frozen=True):
    value = make_adapter(tmp_path)
    value._ik, value._template, value._targets = CountingIk(ik), template, targets
    value._execution_policy = load_teacher_execution_policy(policy_path)
    if frozen:
        value._execution_snapshot_root = tmp_path
    value._pick_horizon_steps = {}
    value._positions = {**{name: float(position) for name, position in zip(JOINTS, current)}, "6": 0.0}
    value._joint_state = lambda *arguments, **keywords: tuple(value._positions[name] for name in JOINTS)
    value._write = lambda: None
    value._ARM_JOINTS = JOINTS
    return value


# ---- the pure function --------------------------------------------------------------------------------------------------

def test_the_pure_horizon_function_equals_the_inline_computation_bit_for_bit(ik, template, targets, baseline):
    result = solve_pick_prefix_horizon(
        ik, START, targets, MotionSafety._interpolate_pose, position_tolerance_m=template.position_tolerance_m,
        orientation_tolerance_rad=max(template.orientation_tolerance_rad))
    document = result.to_document()
    document.update(selection_reason="minimum deterministic cumulative score among complete beam paths", admitted=bool(result.paths))
    assert baseline["admitted"] and len(baseline["selected_paths"][0]["steps"]) == 14
    assert canonical(document) == canonical(baseline)


def test_the_horizon_is_independent_of_the_thread_and_the_time_it_is_computed_in(ik, template, targets, baseline):
    outcome = []
    worker = threading.Thread(target=lambda: outcome.append(solve_pick_prefix_horizon(
        ik, START, targets, MotionSafety._interpolate_pose, position_tolerance_m=template.position_tolerance_m,
        orientation_tolerance_rad=max(template.orientation_tolerance_rad)).to_document()))
    worker.start()
    worker.join()
    assert [item["selected_paths"] for item in outcome] == [baseline["selected_paths"]]
    assert outcome[0]["candidate_receipts"] == baseline["candidate_receipts"]


# ---- the Teacher's _motion_horizon -------------------------------------------------------------------------------------------

def test_without_a_precompute_the_motion_horizon_is_the_inline_computation(tmp_path, ik, template, targets, baseline):
    value = teacher(tmp_path, ik, template, targets, policy_path=DEFAULT_POLICY)
    steps = value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)
    assert canonical(value._document["pick_prefix_horizon"]) == canonical(baseline)
    assert [step.waypoint.state for step in steps] == [State.MOVE_ABOVE_OBJECT] * 6
    assert set(value._pick_horizon_steps) == set(PICK_STATES)
    assert "pick_prefix_precompute" not in value._document


@pytest.mark.parametrize("policy_path,frozen", [(DEFAULT_POLICY, True), (FAST_POLICY, False)])
def test_the_precompute_is_not_started_for_a_schema_3_policy_or_without_frozen_inputs(tmp_path, ik, template, targets, policy_path, frozen):
    value = teacher(tmp_path, ik, template, targets, policy_path=policy_path, frozen=frozen)
    value._start_pick_horizon_precompute()
    assert value._ik.solves == 0 and not hasattr(value, "_pick_horizon_precompute")
    value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)
    assert "pick_prefix_precompute" not in value._document


def test_the_precompute_is_not_started_without_the_pick_targets(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets)
    del value._targets
    value._start_pick_horizon_precompute()
    assert value._ik.solves == 0 and not hasattr(value, "_pick_horizon_precompute")


def test_a_precompute_from_the_same_state_is_used_and_the_goal_solves_nothing(tmp_path, ik, template, targets, baseline):
    value = teacher(tmp_path, ik, template, targets)
    value._start_pick_horizon_precompute()
    value._pick_horizon_precompute.thread.join()
    solved = value._ik.solves
    assert solved > 0
    steps = value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)
    assert value._ik.solves == solved                                       # the goal computed nothing
    assert canonical(value._document["pick_prefix_horizon"]) == canonical(baseline)
    report = value._document["pick_prefix_precompute"]
    assert report["status"] == "USED" and report["start_delta_max_abs_rad"] == 0.0
    assert [step.waypoint.state for step in steps] == [State.MOVE_ABOVE_OBJECT] * 6
    assert set(value._pick_horizon_steps) == set(PICK_STATES) and not hasattr(value, "_pick_horizon_precompute")


def test_a_precompute_waits_for_a_computation_that_is_still_running(tmp_path, ik, template, targets, baseline):
    value = teacher(tmp_path, ik, template, targets)
    ticks = []
    value._progress = lambda: ticks.append(1)
    value._start_pick_horizon_precompute()
    value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)               # no join first: the goal waits for the worker
    assert canonical(value._document["pick_prefix_horizon"]) == canonical(baseline)
    assert value._document["pick_prefix_precompute"]["status"] == "USED"


def test_a_start_state_within_the_tolerance_reuses_the_horizon_of_the_precompute_start(tmp_path, ik, template, targets, baseline):
    drift = PICK_HORIZON_REUSE_MAX_START_DELTA_RAD / 2
    value = teacher(tmp_path, ik, template, targets)
    value._start_pick_horizon_precompute()
    value._pick_horizon_precompute.thread.join()
    later = tuple(position + drift for position in START)
    value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], later)
    assert canonical(value._document["pick_prefix_horizon"]) == canonical(baseline)       # computed from the precompute start
    report = value._document["pick_prefix_precompute"]
    assert report["status"] == "USED" and report["start_delta_max_abs_rad"] == pytest.approx(drift)


def test_a_start_state_beyond_the_tolerance_recomputes_from_the_state_at_the_goal(tmp_path, ik, template, targets):
    moved = tuple(position + 5 * PICK_HORIZON_REUSE_MAX_START_DELTA_RAD for position in START)
    value = teacher(tmp_path, ik, template, targets)
    value._start_pick_horizon_precompute()
    value._pick_horizon_precompute.thread.join()
    before = value._ik.solves
    value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], moved)
    assert value._ik.solves > before
    assert canonical(value._document["pick_prefix_horizon"]) == canonical(legacy_document(ik, template, targets, moved))
    report = value._document["pick_prefix_precompute"]
    assert report["status"] == "START_STATE_DIFFERS" and report["start_delta_max_abs_rad"] > PICK_HORIZON_REUSE_MAX_START_DELTA_RAD


def test_a_failed_precompute_falls_back_to_the_inline_computation(tmp_path, ik, template, targets, baseline):
    value = teacher(tmp_path, ik, template, targets)
    value._ik.fail = RuntimeError("IK_BOOM")
    value._start_pick_horizon_precompute()
    value._pick_horizon_precompute.thread.join()
    value._ik.fail = None
    value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)
    assert canonical(value._document["pick_prefix_horizon"]) == canonical(baseline)
    report = value._document["pick_prefix_precompute"]
    assert report["status"] == "FAILED" and "IK_BOOM" in report["error"]


def test_a_precompute_is_used_once(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets)
    value._start_pick_horizon_precompute()
    value._motion_horizon(State.MOVE_ABOVE_OBJECT, [], START)
    solved = value._ik.solves
    value._motion_horizon(State.DESCEND, [], START)                          # the cached steps of the one horizon
    assert value._ik.solves == solved and not hasattr(value, "_pick_horizon_precompute")


def test_a_joint_state_that_cannot_be_read_starts_no_precompute(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets)

    def unavailable(*arguments, **keywords):
        raise RuntimeError("JOINT_STATE_TIMEOUT")

    value._joint_state = unavailable
    value._start_pick_horizon_precompute()
    assert not hasattr(value, "_pick_horizon_precompute")
    assert value._document["pick_prefix_precompute"]["status"] == "NOT_STARTED"


# ---- where it starts ---------------------------------------------------------------------------------------------------------------

def test_prepare_open_gripper_starts_the_precompute_before_it_commands_the_gripper(tmp_path, ik, template, targets):
    value = teacher(tmp_path, ik, template, targets)
    order = []
    value._start_pick_horizon_precompute = lambda: order.append("precompute")
    value._command_gripper = lambda state, target, before=None: order.append("gripper")
    value._initial, value._teacher_start_attempted = object(), True
    result = value._perform_state(State.PREPARE_OPEN_GRIPPER, None)
    assert result.status.value == "SUCCEEDED" or result.failure is None
    assert order == ["precompute", "gripper"]


@pytest.mark.parametrize("state", [State.CLOSE_GRIPPER, State.WAIT_GRASP_STABLE, State.VALIDATE_FINAL_PLACEMENT])
def test_no_other_state_starts_it(tmp_path, ik, template, targets, state):
    value = teacher(tmp_path, ik, template, targets)
    order = []
    value._start_pick_horizon_precompute = lambda: order.append("precompute")
    value._command_gripper = lambda *arguments, **keywords: order.append("gripper")
    value._wait_stable = lambda *arguments, **keywords: value._snapshot()
    value._initial, value._teacher_start_attempted = object(), True
    value._perform_state(state, None)
    assert "precompute" not in order


def test_the_class_carries_the_methods():
    assert hasattr(RosDynamicMujocoExecution, "_start_pick_horizon_precompute")
