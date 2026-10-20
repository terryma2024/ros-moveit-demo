"""Round-2 plan S3, measurement only: phase marks around the place-side planning and IK between Teacher phases.

The marks are observation only (`dynamic_runtime._mark_active_phase`): these tests check that they are emitted, in order, for the place
side states only, and that the motion they surround is unchanged. Fixture level, no ROS graph."""

from types import SimpleNamespace

import pytest

from so101_demo.core.domain import ActionResult, ActionStatus, State
from so101_demo.ros import dynamic_runtime
from so101_demo.ros.dynamic_execution import planning as planning_module

from test_teacher_moveit_execution import make_adapter

PLACE_SIDE = (State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE)


@pytest.fixture()
def marks(monkeypatch):
    seen = []
    monkeypatch.setattr(dynamic_runtime, "_ACTIVE_PHASE_TIMER", SimpleNamespace(mark=seen.append))
    return seen


class FakeIk:
    def forward(self, positions):
        return SimpleNamespace(position_m=(0.0, 0.0, 0.0), orientation_xyzw=(0.0, 0.0, 0.0, 1.0))

    def orientation_error_rad(self, a, b):
        return 0.0


def motion_adapter(tmp_path, steps=2):
    value = make_adapter(tmp_path)
    value._ik = FakeIk()
    value._template = SimpleNamespace(position_tolerance_m=0.002, orientation_tolerance_rad=(0.1, 0.1, 0.1))
    value._joint_state = lambda *arguments, **keywords: (0.0,) * 5
    value._joint_state_source_stamp_ns = 0
    value._ARM_JOINTS = tuple("12345")
    value._snapshot = lambda: None
    value._record = lambda *arguments, **keywords: None
    value._record_planning_attempt = lambda document: None
    value._motion_monitor = lambda state: None
    value._check_stop = lambda: None
    pose = SimpleNamespace(position_m=(0.0, 0.0, 0.0), orientation_xyzw=(0.0, 0.0, 0.0, 1.0))
    fake_steps = tuple(SimpleNamespace(
        waypoint=SimpleNamespace(target=pose, segment_index=index),
        receipt=SimpleNamespace(joint_positions_rad=(0.0,) * 5, to_document=lambda: {})) for index in range(steps))
    order = []
    value._motion_horizon = lambda state, targets, current: order.append("horizon") or fake_steps
    value._plan_candidate_set = lambda **keywords: (
        order.append("plan") or SimpleNamespace(trajectory=SimpleNamespace(joint_trajectory=SimpleNamespace(points=[]))), [])
    value._execute_planned = lambda trajectory, state, monitor: order.append("execute") or ActionResult(ActionStatus.SUCCEEDED)
    value._order = order
    return value, pose


@pytest.mark.parametrize("state", PLACE_SIDE)
def test_a_place_side_motion_marks_its_horizon_and_each_segment_plan_in_order(tmp_path, marks, state):
    value, pose = motion_adapter(tmp_path)
    value._motion(state, pose)
    prefix = f"place_side.{state.value}."
    assert marks == [prefix + name for name in (
        "motion.begin", "horizon.begin", "horizon.end", "segment0.plan.begin", "segment0.plan.end",
        "segment1.plan.begin", "segment1.plan.end")]
    assert value._order == ["horizon", "plan", "execute", "plan", "execute"]        # the marks change none of the work or its order


@pytest.mark.parametrize("state", [State.MOVE_ABOVE_OBJECT, State.DESCEND, State.RETREAT])
def test_the_pick_side_and_retreat_motions_emit_no_place_side_mark(tmp_path, marks, state):
    value, pose = motion_adapter(tmp_path)
    value._motion(state, pose)
    assert marks == [] and value._order == ["horizon", "plan", "execute", "plan", "execute"]


def test_a_missing_phase_timer_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(dynamic_runtime, "_ACTIVE_PHASE_TIMER", None)
    value, pose = motion_adapter(tmp_path)
    value._motion(State.MOVE_ABOVE_PLACE, pose)
    assert value._order == ["horizon", "plan", "execute", "plan", "execute"]


@pytest.mark.parametrize("state", PLACE_SIDE + (State.MOVE_ABOVE_OBJECT,))
def test_the_candidate_planning_marks_the_moveit_call_and_the_corridor_check_in_order(tmp_path, marks, monkeypatch, state):
    value = make_adapter(tmp_path)
    value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03, planning_timeout_s=1.0,
                                      planning_group="arm", tcp_link="tcp", orientation_tolerance_rad=(0.1, 0.1, 0.1))
    value._ARM_JOINTS = tuple("12345")
    value._ik = FakeIk()
    value._record_planning_attempt = lambda document: None
    trajectory = SimpleNamespace(joint_trajectory=SimpleNamespace(points=[]))
    value._planning = SimpleNamespace(plan_joint_path=lambda request, timeout_s: SimpleNamespace(failure=None, trajectory=trajectory))
    corridor = SimpleNamespace(accepted=True, failure_code=None, to_document=lambda: {})
    monkeypatch.setattr(planning_module, "validate_cartesian_corridor", lambda *arguments, **keywords: corridor)
    monkeypatch.setattr(planning_module, "cartesian_candidate_score", lambda *arguments, **keywords: 0.0)
    step = SimpleNamespace(waypoint=SimpleNamespace(segment_index=0, target=None))
    value._plan_candidate_set(state=state, step=step, current=(0.0,) * 5, joint_target=(0.0,) * 5)
    if state in PLACE_SIDE:
        prefix = f"place_side.{state.value}.candidate0."
        assert marks == [prefix + name for name in ("moveit.begin", "moveit.end", "corridor.begin", "corridor.end")]
    else:
        assert marks == []


def test_the_place_target_computation_is_marked_before_the_motion_of_descend_to_place(tmp_path, marks):
    value, pose = motion_adapter(tmp_path)
    value._place_target = lambda state, target: marks.append("computing") or target
    value._motion = lambda state, target: marks.append("motion")
    value._teacher_run = lambda: False
    value._initial, value._teacher_start_attempted = object(), True
    result = value._perform_state(State.DESCEND_TO_PLACE, pose)
    assert result.status is ActionStatus.SUCCEEDED
    assert marks == ["place_side.DESCEND_TO_PLACE.place_target.begin", "computing", "place_side.DESCEND_TO_PLACE.place_target.end", "motion"]
