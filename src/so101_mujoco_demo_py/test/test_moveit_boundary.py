from dataclasses import dataclass

from so101_mujoco_demo_py.domain import ActionStatus, FailureCategory
from so101_mujoco_demo_py.motion.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
)
from so101_mujoco_demo_py.moveit.planning import (
    JointPlanRequest,
    MoveItPlanningClient,
    make_get_motion_plan_request,
)


@dataclass
class FakeFuture:
    value: object = None
    done_value: bool = True

    def done(self):
        return self.done_value

    def result(self):
        return self.value


class FakeService:
    def __init__(self, available=True, response=None, done=True):
        self.available = available
        self.response = response
        self.done = done

    def wait_for_service(self, timeout_sec):
        return self.available

    def call_async(self, request):
        return FakeFuture(self.response, self.done)


@dataclass
class ErrorCode:
    val: int


@dataclass
class MotionResponse:
    error_code: ErrorCode
    trajectory: object = None


@dataclass
class Response:
    motion_plan_response: MotionResponse


REQUEST = JointPlanRequest(
    ("1", "2", "3", "4", "5"),
    (0.0, 0.0, 0.0, 0.0, 0.0),
    (0.1, 0.2, 0.3, 0.4, 0.5),
)


def test_request_preserves_public_moveit_names() -> None:
    assert REQUEST.planning_group == "arm"
    assert REQUEST.tcp_link == "so101_tcp"
    assert REQUEST.joint_names + ("6",) == ("1", "2", "3", "4", "5", "6")


def test_joint_request_can_include_preopened_q6_in_start_state_without_goal_constraint() -> None:
    request = JointPlanRequest(
        ("1", "2", "3", "4", "5"),
        (0.0, 0.0, 0.0, 0.0, 0.0),
        (0.1, 0.2, 0.3, 0.4, 0.5),
        start_state_joint_names=("1", "2", "3", "4", "5", "6"),
        start_state_positions=(0.0, 0.0, 0.0, 0.0, 0.0, 0.465038),
    )

    wire = make_get_motion_plan_request(request).motion_plan_request

    assert wire.start_state.joint_state.name == ["1", "2", "3", "4", "5", "6"]
    assert wire.start_state.joint_state.position[-1] == 0.465038
    assert [item.joint_name for item in wire.goal_constraints[0].joint_constraints] == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


def test_pose_request_is_world_tcp_constrained() -> None:
    from so101_mujoco_demo_py.moveit.planning import PosePlanRequest

    request = PosePlanRequest(
        joint_names=("1", "2", "3", "4", "5", "6"),
        current_positions=(0.0, 0.1, 0.1, 0.2, 0.0, 0.465038),
        target_position_m=(0.02, -0.263, 0.24),
        target_orientation_xyzw=(-0.01, -0.01, -0.707, 0.707),
        orientation_tolerance_rad=(0.01, 0.01, 0.01),
    )

    assert request.frame_id == "world"
    assert request.tcp_link == "so101_tcp"
    assert request.planning_group == "arm"
    assert request.joint_names[-1] == "6"
    assert request.position_tolerance_m == 0.0005
    assert request.orientation_tolerance_rad == (0.01, 0.01, 0.01)


def test_pose_planner_rejects_empty_trajectory() -> None:
    from so101_mujoco_demo_py.moveit.planning import PosePlanRequest

    request = PosePlanRequest(
        joint_names=("1", "2", "3", "4", "5", "6"),
        current_positions=(0.0, 0.1, 0.1, 0.2, 0.0, 0.465038),
        target_position_m=(0.02, -0.263, 0.24),
        target_orientation_xyzw=(-0.01, -0.01, -0.707, 0.707),
        orientation_tolerance_rad=(0.01, 0.01, 0.01),
    )
    response = Response(
        MotionResponse(
            ErrorCode(1),
            trajectory=type("T", (), {"joint_trajectory": type("J", (), {"points": []})()})(),
        )
    )

    outcome = MoveItPlanningClient(FakeService(response=response)).plan_pose_path(request)

    assert outcome.failure.code == "EMPTY_TRAJECTORY"


def test_pregrasp_goal_orientation_does_not_invalidate_unaligned_start() -> None:
    from so101_mujoco_demo_py.moveit.planning import (
        PosePlanRequest,
        make_get_motion_plan_pose_request,
    )

    request = PosePlanRequest(
        joint_names=("1", "2", "3", "4", "5", "6"),
        current_positions=(0.0, 0.0, 0.0, 0.0, 0.0, 0.465038),
        target_position_m=(0.02, -0.263, 0.24),
        target_orientation_xyzw=(-0.0102659913, -0.0102629866, -0.7067526865, 0.7073117563),
        orientation_tolerance_rad=(0.01, 0.01, 0.01),
        enforce_orientation_path=False,
    )

    wire = make_get_motion_plan_pose_request(request)

    assert len(wire.motion_plan_request.goal_constraints[0].orientation_constraints) == 1
    assert wire.motion_plan_request.path_constraints.orientation_constraints == []


def test_plan_service_failures_are_stable() -> None:
    unavailable = MoveItPlanningClient(FakeService(False)).plan_joint_path(REQUEST, 0.001)
    assert unavailable.failure.category is FailureCategory.PLANNING
    assert unavailable.failure.code == "MOVEIT_PLAN_SERVICE_UNAVAILABLE"
    timeout = MoveItPlanningClient(FakeService(done=False)).plan_joint_path(REQUEST, 0.001)
    assert timeout.failure.code == "MOVEIT_PLAN_TIMEOUT"
    rejected = MoveItPlanningClient(
        FakeService(response=Response(MotionResponse(ErrorCode(-1))))
    ).plan_joint_path(REQUEST, 0.001)
    assert rejected.failure.code == "MOVEIT_PLAN_FAILED"
    assert rejected.failure.metrics["moveit_error_code"] == -1.0


class FakeGoal:
    def __init__(self, accepted=True, result_done=True, result=None):
        self.accepted = accepted
        self.result_done = result_done
        self.result = result
        self.cancel_count = 0

    def get_result_async(self):
        return FakeFuture(self.result, self.result_done)

    def cancel_goal_async(self):
        self.cancel_count += 1
        return FakeFuture()


class FakeAction:
    def __init__(self, goal):
        self.goal = goal

    def wait_for_server(self, timeout_sec):
        return True

    def send_goal_async(self, goal):
        return FakeFuture(self.goal)


def test_execute_rejection_timeout_and_moveit_error_are_stable() -> None:
    rejected = MoveItExecutionClient(FakeAction(FakeGoal(False))).execute(object(), 0.01)
    assert rejected.status is ActionStatus.FAILED
    assert rejected.failure.code == "MOVEIT_EXECUTION_REJECTED"

    owned = FakeGoal(result_done=False)
    result = MoveItExecutionClient(FakeAction(owned)).execute(object(), 0.001)
    assert result.status is ActionStatus.TIMED_OUT
    assert result.failure.code == "MOVEIT_EXECUTION_TIMEOUT"
    assert owned.cancel_count == 1

    wrapped = type(
        "Wrapped",
        (),
        {"result": type("Result", (), {"error_code": ErrorCode(-4)})()},
    )()
    failed = MoveItExecutionClient(FakeAction(FakeGoal(result=wrapped))).execute(object(), 0.01)
    assert failed.status is ActionStatus.FAILED
    assert failed.failure.metrics["moveit_error_code"] == -4.0


def test_execute_monitor_abort_cancels_the_owned_goal() -> None:
    owned = FakeGoal(result_done=False)
    result = MoveItExecutionClient(FakeAction(owned)).execute(
        object(),
        0.1,
        monitor=lambda: (_ for _ in ()).throw(RuntimeError("early contact")),
    )

    assert result.status is ActionStatus.FAILED
    assert result.failure.code == "MOVEIT_EXECUTION_MONITOR_ABORTED"
    assert "early contact" in result.failure.message
    assert owned.cancel_count == 1


def test_sustained_condition_guard_ignores_short_contact_handoff() -> None:
    now = [10.0]
    guard = SustainedConditionGuard(0.05, clock=lambda: now[0])

    guard.require(False, "bilateral contact lost")
    now[0] += 0.049
    guard.require(False, "bilateral contact lost")
    guard.require(True, "bilateral contact lost")

    assert guard.failure_started_s is None


def test_sustained_condition_guard_aborts_at_bounded_grace() -> None:
    now = [20.0]
    guard = SustainedConditionGuard(0.05, clock=lambda: now[0])

    guard.require(False, "bilateral contact lost")
    now[0] += 0.05

    try:
        guard.require(False, "bilateral contact lost")
    except RuntimeError as error:
        assert "bilateral contact lost for 0.050000s" in str(error)
    else:
        raise AssertionError("sustained loss did not abort")


def test_sustained_condition_guard_rejects_invalid_grace() -> None:
    try:
        SustainedConditionGuard(-0.001)
    except ValueError as error:
        assert "failure_grace_s" in str(error)
    else:
        raise AssertionError("negative grace was accepted")
