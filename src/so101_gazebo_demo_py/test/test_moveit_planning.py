from dataclasses import dataclass

from so101_gazebo_demo.domain import ActionStatus, FailureCategory
from so101_gazebo_demo.moveit.planning import JointPlanRequest, MoveItPlanningClient
from so101_gazebo_demo.motion.executor import MoveItExecutionClient


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
        self.available, self.response, self.done = available, response, done

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


REQUEST = JointPlanRequest(("1", "2"), (0.0, 0.0), (0.1, 0.2))


def test_plan_service_unavailable_timeout_and_moveit_error_are_stable() -> None:
    unavailable = MoveItPlanningClient(FakeService(False)).plan_joint_path(REQUEST, 0.001)
    assert unavailable.failure.category is FailureCategory.PLANNING
    assert unavailable.failure.code == "MOVEIT_PLAN_SERVICE_UNAVAILABLE"
    timeout = MoveItPlanningClient(FakeService(done=False)).plan_joint_path(REQUEST, 0.001)
    assert timeout.failure.code == "MOVEIT_PLAN_TIMEOUT"
    rejected = MoveItPlanningClient(
        FakeService(response=Response(MotionResponse(ErrorCode(-1)))),
    ).plan_joint_path(REQUEST, 0.001)
    assert rejected.failure.code == "MOVEIT_PLAN_FAILED"
    assert rejected.failure.metrics["moveit_error_code"] == -1.0


class FakeCancelFuture(FakeFuture):
    pass


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
        return FakeCancelFuture()


class FakeAction:
    def __init__(self, goal):
        self.goal = goal

    def wait_for_server(self, timeout_sec):
        return True

    def send_goal_async(self, goal):
        return FakeFuture(self.goal)


def test_execute_rejected_goal_is_execution_failure() -> None:
    result = MoveItExecutionClient(FakeAction(FakeGoal(False))).execute(object(), 0.01)
    assert result.status is ActionStatus.FAILED
    assert result.failure.code == "MOVEIT_EXECUTION_REJECTED"


def test_result_timeout_cancels_only_request_owned_goal() -> None:
    owned = FakeGoal(result_done=False)
    unrelated = FakeGoal(result_done=False)
    result = MoveItExecutionClient(FakeAction(owned)).execute(object(), 0.001)
    assert result.status is ActionStatus.TIMED_OUT
    assert result.failure.code == "MOVEIT_EXECUTION_TIMEOUT"
    assert owned.cancel_count == 1
    assert unrelated.cancel_count == 0


def test_moveit_execution_error_code_is_failure() -> None:
    wrapped = type("Wrapped", (), {"result": type("Result", (), {"error_code": ErrorCode(-4)})()})()
    result = MoveItExecutionClient(FakeAction(FakeGoal(result=wrapped))).execute(object(), 0.01)
    assert result.status is ActionStatus.FAILED
    assert result.failure.metrics["moveit_error_code"] == -4.0
