"""Round-2 plan S3, measurement only: phase marks around the place-side planning and IK between Teacher phases.

The marks are observation only (`dynamic_runtime._mark_active_phase`): these tests check that they are emitted, in order, for the place
side states only, and that the motion they surround is unchanged. Fixture level, no ROS graph."""

import json
from types import SimpleNamespace

import pytest

from so101_demo.core.domain import ActionResult, ActionStatus, State
from so101_demo.ros import dynamic_runtime
from so101_demo.ros.dynamic_execution import planning as planning_module

from test_teacher_moveit_execution import make_adapter

PLACE_SIDE = (State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE)


class Marks(list):
    """The place-side marks; `main` collects what reaches the timer's main phase marks (it must stay empty)."""

    def __init__(self):
        super().__init__()
        self.main = []


@pytest.fixture()
def marks(monkeypatch):
    seen = Marks()
    monkeypatch.setattr(dynamic_runtime, "_ACTIVE_PHASE_TIMER", SimpleNamespace(mark=seen.main.append, mark_place_side=seen.append))
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
    assert marks.main == []                                                          # none of them reaches the main phase marks


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


# ---- the separate line ------------------------------------------------------------------------------------------------------

def timer_lines(capsys, place_side_count, *, phases=(("a", 1), ("b", 2))):
    timer = dynamic_runtime._PhaseTimer()
    timer.phases = [list(item) for item in phases]
    for index in range(place_side_count):
        timer.mark_place_side(f"place_side.LIFT.segment{index}.plan.begin")
    timer.emit("ok")
    return [line for line in capsys.readouterr().err.splitlines() if line.startswith("DYNAMIC_EXECUTE_")]


def test_the_main_phase_timing_line_is_byte_identical_with_or_without_place_side_marks(capsys):
    without = timer_lines(capsys, 0)
    with_marks = timer_lines(capsys, 40)
    assert len(without) == 1 and len(with_marks) == 2
    assert with_marks[0] == without[0]                    # no node: the clock and census are null, so the whole line is deterministic
    assert "place_side" not in with_marks[0] and "truncated" not in with_marks[0]


def test_place_side_marks_never_use_the_main_phase_capacity():
    timer = dynamic_runtime._PhaseTimer()
    for index in range(5000):
        timer.mark_place_side(f"m{index}")
    for index in range(256):
        timer.mark(f"p{index}")
    assert len(timer.phases) == 256 and timer.phases[0][0] == "p0" and timer.phases[-1][0] == "p255"


def test_the_place_side_line_is_truncated_on_its_own_with_an_explicit_count(capsys):
    baseline = timer_lines(capsys, 0)[0]
    main, place = timer_lines(capsys, 5000)
    assert main == baseline
    assert place.startswith(dynamic_runtime._PLACE_SIDE_TIMING_PREFIX)
    document = json.loads(place[len(dynamic_runtime._PLACE_SIDE_TIMING_PREFIX):])
    assert len(place) <= len(dynamic_runtime._PLACE_SIDE_TIMING_PREFIX) + dynamic_runtime._PLACE_SIDE_TIMING_MAX_BYTES
    assert document["truncated"] > 0 and document["truncated"] + len(document["marks"]) == 5000
    assert all(isinstance(item[0], str) and isinstance(item[1], int) for item in document["marks"])


def test_a_small_place_side_line_is_complete_and_in_order(capsys):
    _, place = timer_lines(capsys, 3)
    document = json.loads(place[len(dynamic_runtime._PLACE_SIDE_TIMING_PREFIX):])
    assert document["truncated"] == 0
    assert [item[0] for item in document["marks"]] == [f"place_side.LIFT.segment{index}.plan.begin" for index in range(3)]
    assert [item[1] for item in document["marks"]] == sorted(item[1] for item in document["marks"])


def test_place_side_marks_do_not_count_as_progress_for_the_stall_sampler():
    timer = dynamic_runtime._PhaseTimer()
    before = timer.last_progress_ns
    timer.mark_place_side("place_side.LIFT.motion.begin")
    assert timer.last_progress_ns == before
