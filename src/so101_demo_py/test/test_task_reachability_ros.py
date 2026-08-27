from types import SimpleNamespace

from so101_demo.application.task_reachability import ReachabilityStatus
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DynamicPickTemplate
from so101_demo.core.task_geometry import Pose7
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.robot_control import JointStateEvidence
from so101_demo.ros.task_reachability import (
    RosMoveGroupReachabilityPlanner,
    make_move_group_goal,
)


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


def test_goal_is_plan_only_and_contains_request_local_cup_scene() -> None:
    goal = make_move_group_goal(
        state=State.MOVE_ABOVE_OBJECT,
        target=_target(),
        start=_start(),
        cup_pose_world=_cup(),
        template=_template(),
    )

    assert goal.planning_options.plan_only is True
    assert goal.planning_options.replan is False
    assert goal.planning_options.planning_scene_diff.is_diff is True
    objects = goal.planning_options.planning_scene_diff.world.collision_objects
    assert [item.id for item in objects] == ["plastic_cup"]
    assert goal.request.start_state.joint_state.name == list(_start().names)
    assert list(goal.request.start_state.joint_state.position) == list(
        _start().positions_rad
    )
    assert goal.request.group_name == "arm"
    assert goal.request.goal_constraints[0].position_constraints[0].link_name == "so101_tcp"


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
        return _Future(_GoalHandle(self.result, accepted=self.accepted))


def _result(*, code: int = 1, with_point: bool = True):
    points = (
        [SimpleNamespace(positions=[0.1, 0.2, 0.3, 0.4, 0.5])]
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
        object(), _template(), action_client=action, monotonic=lambda: 1.0
    )

    receipt = planner.plan(
        State.MOVE_ABOVE_OBJECT, _target(), _start(), _cup(), 5.0
    )

    assert receipt.accepted is True
    assert receipt.moveit_error_code == 1
    assert receipt.terminal_state.names == _start().names
    assert receipt.terminal_state.positions_rad == (
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.465038,
    )
    assert len(action.goals) == 1


def test_rejected_action_preserves_moveit_error_code() -> None:
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result(code=-31))
    )

    receipt = planner.plan(State.DESCEND, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is False
    assert receipt.moveit_error_code == -31
    assert receipt.failure_code == "MOVEIT_PLAN_FAILED"


def test_unavailable_action_is_unknown_and_no_execution_client_exists() -> None:
    planner = RosMoveGroupReachabilityPlanner(
        object(), _template(), action_client=_ActionClient(_result(), server=False)
    )

    receipt = planner.plan(State.DESCEND, _target(), _start(), _cup(), 5.0)

    assert receipt.accepted is False
    assert receipt.failure_code == "PLANNER_UNAVAILABLE"
    assert not hasattr(planner, "execute")
    assert not hasattr(planner, "_execute_client")
