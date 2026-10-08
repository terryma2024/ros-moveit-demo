import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DynamicPickTemplate
from so101_demo.core.task_geometry import Pose7
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.robot_control import JointStateEvidence
from so101_demo.ros.task_reachability import (
    RosMoveGroupReachabilityPlanner,
    make_move_group_goal,
)


def test_prepare_horizon_reuses_real_requests_only_within_one_call(monkeypatch) -> None:
    from collections import Counter
    from pathlib import Path

    from so101_demo.control.moveit.underactuated_ik import UnderactuatedPoseIk
    from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
    from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template

    package = Path(__file__).parents[1]
    template = load_dynamic_pick_template(
        package / "config/policies/dynamic_cup_pick/v1/mujoco.yaml", expected_backend="mujoco"
    )
    ik = UnderactuatedPoseIk.from_urdf(
        package / "assets/mujoco/so101.urdf", template.arm_joint_names, "world", "so101_tcp"
    )
    targets = resolve_motion_targets(
        CupPoseSample("world", 1, 0.0, Pose7((0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0))), template
    )
    requests = Counter()
    real_solve = ik.solve

    def counted(target, seed, **kwargs):
        requests[(target, seed, tuple(kwargs.items()))] += 1
        return real_solve(target, seed, **kwargs)

    monkeypatch.setattr(ik, "solve", counted)
    planner = RosMoveGroupReachabilityPlanner(
        object(), template, action_client=object(), ik=ik, progress=lambda: None
    )
    planner.prepare_horizon(targets, _start())
    first = planner._prepared_receipts
    steps = planner._prepared_steps.copy()
    assert sum(map(len, steps.values())) == 14
    assert max(requests.values()) == 1
    assert len(first) > sum(requests.values())
    planner.prepare_horizon(targets, _start())
    assert planner._prepared_receipts == first
    assert planner._prepared_steps == steps
    assert set(requests.values()) == {2}


def _template() -> DynamicPickTemplate:
    return DynamicPickTemplate(
        "dynamic_cup_pick",
        "world",
        "plastic_cup",
        "arm",
        ("1", "2", "3", "4", "5"),
        "so101_tcp",
        Pose7((0.0, 0.0, 0.035, 0.0, 0.0, 0.0, 1.0)),
        0.08,
        0.02,
        0.10,
        Pose7((0.19, -0.18, 0.20, 0.0, 0.0, 0.0, 1.0)),
        0.08,
        0.10,
        (-0.30, -0.50, 0.10, 0.35, 0.20, 0.50),
        0.20,
        0.02,
        0.01,
        0.10,
        0.002,
        (0.10, 0.10, 0.10),
        5.0,
        0.03,
        0.03,
    )


def _start() -> JointStateEvidence:
    return JointStateEvidence(
        ("1", "2", "3", "4", "5", "6"),
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.465038),
        1.0,
    )


def _target() -> PoseEvidence:
    return PoseEvidence((0.02, -0.28, 0.28), (0.0, 0.0, 0.0, 1.0))


def _cup() -> PoseEvidence:
    return PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0))


class _TargetIk:
    def solve(self, target, _seed, **_kwargs):
        return (*target.position_m, 0.4, 0.5)

    def forward(self, joints):
        return PoseEvidence(tuple(joints[:3]), (0.0, 0.0, 0.0, 1.0))

    @staticmethod
    def orientation_error_rad(_actual, _target):
        return 0.0


def test_goal_is_plan_only_and_contains_request_local_cup_scene() -> None:
    goal = make_move_group_goal(
        state=State.MOVE_ABOVE_OBJECT,
        target=_target(),
        start=_start(),
        cup_pose_world=_cup(),
        template=_template(),
        joint_target=(0.02, -0.28, 0.28, 0.4, 0.5),
    )

    assert goal.planning_options.plan_only is True
    assert goal.planning_options.replan is False
    assert goal.planning_options.planning_scene_diff.is_diff is True
    objects = goal.planning_options.planning_scene_diff.world.collision_objects
    assert [item.id for item in objects] == ["plastic_cup"]
    assert goal.request.start_state.joint_state.name == list(_start().names)
    assert list(goal.request.start_state.joint_state.position) == list(_start().positions_rad)
    assert goal.request.group_name == "arm"
    constraints = goal.request.goal_constraints[0]
    assert constraints.position_constraints == []
    assert [item.joint_name for item in constraints.joint_constraints] == ["1", "2", "3", "4", "5"]
    assert [item.position for item in constraints.joint_constraints] == [
        0.02,
        -0.28,
        0.28,
        0.4,
        0.5,
    ]
    assert goal.request.path_constraints.orientation_constraints == []


def test_contact_and_carry_segments_remove_only_the_target_cup_obstacle() -> None:
    from moveit_msgs.msg import CollisionObject

    goal = make_move_group_goal(
        state=State.DESCEND,
        target=_target(),
        start=_start(),
        cup_pose_world=_cup(),
        template=_template(),
        joint_target=(0.02, -0.28, 0.28, 0.4, 0.5),
    )

    objects = goal.planning_options.planning_scene_diff.world.collision_objects
    assert len(objects) == 1
    assert objects[0].id == "plastic_cup"
    assert objects[0].operation == CollisionObject.REMOVE
    assert objects[0].primitives == []


class _Future:
    def __init__(self, value) -> None:
        self.value = value

    def done(self) -> bool:
        return True

    def result(self):
        return self.value


class _GoalHandle:
    def __init__(self, result, *, accepted: bool = True) -> None:
        self.accepted = accepted
        self._result = result

    def get_result_async(self):
        return _Future(SimpleNamespace(result=self._result))


class _ActionClient:
    def __init__(self, result, *, server=True, accepted=True) -> None:
        self.result = result
        self.server = server
        self.accepted = accepted
        self.goals = []

    def wait_for_server(self, *, timeout_sec: float) -> bool:
        return self.server and timeout_sec > 0.0

    def send_goal_async(self, goal):
        self.goals.append(goal)
        result = self.result
        if isinstance(result, list):
            result = result[len(self.goals) - 1]
        return _Future(_GoalHandle(result, accepted=self.accepted))


def _result(*, code: int = 1, with_point: bool = True, points=None):
    if points is None:
        points = (
            [SimpleNamespace(positions=[0.02, -0.28, 0.28, 0.4, 0.5])]
            if with_point
            else []
        )
    return SimpleNamespace(
        error_code=SimpleNamespace(val=code),
        planned_trajectory=SimpleNamespace(
            joint_trajectory=SimpleNamespace(
                joint_names=["1", "2", "3", "4", "5"],
                points=points,
            )
        ),
    )


def test_accepted_action_returns_final_trajectory_point() -> None:
    action = _ActionClient(_result())
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=action, ik=_TargetIk(), monotonic=lambda: 1.0,
        progress=lambda: None,
    )

    receipt = planner.plan(State.MOVE_ABOVE_OBJECT, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is True
    assert receipt.moveit_error_code == 1
    assert receipt.terminal_state.names == _start().names
    assert receipt.terminal_state.positions_rad == (
        0.02,
        -0.28,
        0.28,
        0.4,
        0.5,
        0.465038,
    )
    assert len(action.goals) == 4


def test_reachability_scores_a_bounded_plan_set_and_selects_a_safe_corridor() -> None:
    bad = _result(
        points=[
            SimpleNamespace(positions=[0.30, 0.30, 0.10, 0.4, 0.5]),
            SimpleNamespace(positions=[0.02, -0.28, 0.28, 0.4, 0.5]),
        ]
    )
    direct = _result(
        points=[
            SimpleNamespace(positions=[0.01, -0.14, 0.14, 0.2, 0.25]),
            SimpleNamespace(positions=[0.02, -0.28, 0.28, 0.4, 0.5]),
        ]
    )
    action = _ActionClient([bad, direct, direct, direct])
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=action, ik=_TargetIk(), monotonic=lambda: 1.0,
        progress=lambda: None,
    )

    receipt = planner.plan(State.MOVE_ABOVE_OBJECT, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is True
    assert len(action.goals) == 4
    plan_receipts = [
        item for item in receipt.planning_receipts if item.get("kind") == "moveit_plan_candidate"
    ]
    assert [item["candidate_index"] for item in plan_receipts] == [0, 1, 2, 3]
    assert plan_receipts[0]["accepted"] is False
    assert plan_receipts[1]["accepted"] is True
    assert receipt.planning_receipts[-1]["kind"] == "moveit_plan_selection"
    assert receipt.planning_receipts[-1]["candidate_index"] == 1


def test_rejected_action_preserves_moveit_error_code() -> None:
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result(code=-31)), ik=_TargetIk(),
        progress=lambda: None,
    )

    receipt = planner.plan(State.DESCEND, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is False
    assert receipt.moveit_error_code == -31
    assert receipt.failure_code == "MOVEIT_PLAN_FAILED"


def test_unavailable_action_is_unknown_and_no_execution_client_exists() -> None:
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result(), server=False), ik=_TargetIk(),
        progress=lambda: None,
    )

    receipt = planner.plan(State.DESCEND, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is False
    assert receipt.failure_code == "PLANNER_UNAVAILABLE"
    assert not hasattr(planner, "execute")
    assert not hasattr(planner, "_execute_client")


class _SlowIk(_TargetIk):
    """Pure-Python stand-in whose solve costs real wall time on the caller's thread."""

    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.solve_threads = set()

    def solve(self, target, seed, **kwargs):
        self.solve_threads.add(threading.get_ident())
        time.sleep(self.delay_s)
        return super().solve(target, seed, **kwargs)


class _Targets:
    def __init__(self) -> None:
        self._poses = {
            State.MOVE_ABOVE_OBJECT: PoseEvidence((0.02, -0.28, 0.28), (0.0, 0.0, 0.0, 1.0)),
            State.DESCEND: PoseEvidence((0.02, -0.28, 0.16), (0.0, 0.0, 0.0, 1.0)),
            State.MICRO_LIFT: PoseEvidence((0.02, -0.28, 0.17), (0.0, 0.0, 0.0, 1.0)),
            State.LIFT: PoseEvidence((0.02, -0.28, 0.25), (0.0, 0.0, 0.0, 1.0)),
        }

    def for_state(self, state: State) -> PoseEvidence:
        return self._poses[state]


def test_prepare_horizon_keeps_progressing_while_the_ik_computes() -> None:
    ik = _SlowIk(0.01)
    ticks = []
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result()), ik=ik,
        progress=lambda: ticks.append(threading.get_ident()),
    )
    reference = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result()), ik=_TargetIk(),
        progress=lambda: None,
    )

    started = time.monotonic()
    planner.prepare_horizon(_Targets(), _start())
    elapsed = time.monotonic() - started
    reference.prepare_horizon(_Targets(), _start())

    assert elapsed > 0.1
    assert len(ticks) > 5
    assert set(ticks) == {threading.get_ident()}
    assert ik.solve_threads and threading.get_ident() not in ik.solve_threads
    assert planner._prepared_steps and planner._prepared_steps == reference._prepared_steps
    assert planner._prepared_receipts == reference._prepared_receipts


def test_unprepared_state_horizon_keeps_progressing_while_the_ik_computes() -> None:
    ik = _SlowIk(0.01)
    ticks = []
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result()), ik=ik,
        progress=lambda: ticks.append(1), monotonic=lambda: 1.0,
    )

    receipt = planner.plan(State.MOVE_ABOVE_OBJECT, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is True
    assert len(ticks) > 0
    assert threading.get_ident() not in ik.solve_threads


def test_compute_while_progressing_returns_value_and_reraises_the_same_error() -> None:
    from so101_demo.ros.task_reachability import _compute_while_progressing

    ticks = []
    assert _compute_while_progressing(lambda: (time.sleep(0.05), 7)[1], lambda: ticks.append(1)) == 7
    assert ticks

    error = RuntimeError("ik failed")

    def fail():
        raise error

    with pytest.raises(RuntimeError) as caught:
        _compute_while_progressing(fail, lambda: None)
    assert caught.value is error


def test_compute_while_progressing_joins_the_worker_before_reraising_a_progress_error() -> None:
    from so101_demo.ros.task_reachability import _compute_while_progressing

    finished = threading.Event()
    boom = RuntimeError("progress failed")

    def work():
        time.sleep(0.1)
        finished.set()

    def progress():
        raise boom

    started = time.monotonic()
    with pytest.raises(RuntimeError) as caught:
        _compute_while_progressing(work, progress)
    assert caught.value is boom
    assert finished.is_set()
    assert time.monotonic() - started < 2.0


def test_compute_while_progressing_runs_scheduled_callbacks_during_the_computation() -> None:
    from so101_demo.ros.task_reachability import _compute_while_progressing

    pending = []
    handled_at = []
    done = threading.Event()

    def work():
        pending.append("chunk")
        time.sleep(0.2)
        done.set()

    def progress():
        while pending:
            pending.pop()
            handled_at.append(done.is_set())

    _compute_while_progressing(work, progress)

    assert handled_at == [False]


def test_consumer_motion_horizon_keeps_progressing_while_the_ik_computes() -> None:
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

    ik = _SlowIk(0.01)
    ticks = []
    runtime = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    runtime._ik = ik
    runtime._template = _template()
    runtime._targets = _Targets()
    runtime._pick_horizon_steps = {}
    runtime._document = {}
    runtime._write = lambda: None
    runtime._progress = lambda: ticks.append(threading.get_ident())

    steps = runtime._motion_horizon(State.MOVE_ABOVE_OBJECT, [_target()], _start().positions_rad[:5])

    assert steps
    assert len(ticks) > 5
    assert set(ticks) == {threading.get_ident()}
    assert threading.get_ident() not in ik.solve_threads
