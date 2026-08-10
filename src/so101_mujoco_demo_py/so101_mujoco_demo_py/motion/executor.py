"""Request-scoped MoveIt trajectory execution."""

import time
from typing import Any, Callable

from ..domain import ActionResult, ActionStatus, Failure, FailureCategory


def _wait(future: Any, deadline: float, progress: Callable[[], None]) -> bool:
    while not future.done() and time.monotonic() < deadline:
        progress()
        time.sleep(0.001)
    return future.done()


class MoveItExecutionClient:
    def __init__(
        self,
        client: Any,
        goal_factory: Callable[[Any], Any] | None = None,
        progress: Callable[[], None] = lambda: None,
    ) -> None:
        self._client = client
        self._goal_factory = goal_factory
        self._progress = progress

    def execute(self, trajectory: Any, timeout_s: float) -> ActionResult:
        def failure(
            status: ActionStatus, code: str, message: str, **metrics: float
        ) -> ActionResult:
            return ActionResult(
                status,
                Failure(FailureCategory.EXECUTION, code, message, metrics),
            )

        if not self._client.wait_for_server(timeout_sec=timeout_s):
            return failure(
                ActionStatus.FAILED,
                "MOVEIT_EXECUTION_UNAVAILABLE",
                "ExecuteTrajectory unavailable",
            )
        goal = self._goal_factory(trajectory) if self._goal_factory else trajectory
        deadline = time.monotonic() + timeout_s
        goal_future = self._client.send_goal_async(goal)
        if not _wait(goal_future, deadline, self._progress):
            return failure(
                ActionStatus.TIMED_OUT,
                "MOVEIT_EXECUTION_GOAL_TIMEOUT",
                "goal response timed out",
            )
        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            return failure(
                ActionStatus.FAILED,
                "MOVEIT_EXECUTION_REJECTED",
                "goal rejected",
            )
        result_future = goal_handle.get_result_async()
        if not _wait(result_future, deadline, self._progress):
            goal_handle.cancel_goal_async()
            return failure(
                ActionStatus.TIMED_OUT,
                "MOVEIT_EXECUTION_TIMEOUT",
                "execution timed out",
            )
        wrapped = result_future.result()
        result = getattr(wrapped, "result", wrapped)
        code = int(getattr(getattr(result, "error_code", None), "val", 1))
        if code != 1:
            return failure(
                ActionStatus.FAILED,
                "MOVEIT_EXECUTION_FAILED",
                f"MoveIt execution error {code}",
                moveit_error_code=float(code),
            )
        return ActionResult(ActionStatus.SUCCEEDED)


def make_execute_goal(trajectory: Any) -> Any:
    from moveit_msgs.action import ExecuteTrajectory

    goal = ExecuteTrajectory.Goal()
    goal.trajectory = trajectory
    return goal
