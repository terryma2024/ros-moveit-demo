"""Request-scoped MoveIt trajectory execution."""

import time
from typing import Any, Callable

from ..domain import ActionResult, ActionStatus, Failure, FailureCategory


def _wait(future: Any, deadline: float, progress: Callable[[], None]) -> bool:
    while not future.done() and time.monotonic() < deadline:
        progress()
        time.sleep(0.001)
    return future.done()


class SustainedConditionGuard:
    """Allow a condition to be false briefly, but fail on sustained loss."""

    def __init__(
        self,
        failure_grace_s: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_grace_s < 0.0:
            raise ValueError("failure_grace_s must be non-negative")
        self._failure_grace_s = failure_grace_s
        self._clock = clock
        self._failure_started_s: float | None = None

    @property
    def failure_started_s(self) -> float | None:
        return self._failure_started_s

    def require(self, condition: bool, message: str) -> None:
        if condition:
            self._failure_started_s = None
            return
        now = self._clock()
        if self._failure_started_s is None:
            self._failure_started_s = now
        elapsed_s = now - self._failure_started_s
        if elapsed_s >= self._failure_grace_s:
            raise RuntimeError(
                f"{message} for {elapsed_s:.6f}s (grace {self._failure_grace_s:.6f}s)"
            )


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

    def execute(
        self,
        trajectory: Any,
        timeout_s: float,
        *,
        monitor: Callable[[], None] | None = None,
    ) -> ActionResult:
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
        while not result_future.done() and time.monotonic() < deadline:
            self._progress()
            if monitor is not None:
                try:
                    monitor()
                except RuntimeError as error:
                    goal_handle.cancel_goal_async()
                    return failure(
                        ActionStatus.FAILED,
                        "MOVEIT_EXECUTION_MONITOR_ABORTED",
                        str(error),
                    )
            time.sleep(0.001)
        if not result_future.done():
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
