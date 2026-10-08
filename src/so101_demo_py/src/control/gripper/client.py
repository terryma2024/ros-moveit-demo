"""FollowJointTrajectory adapter for the single SO-101 joint 6."""

import time
from typing import Any, Callable

from ...core.domain import ActionResult, ActionStatus, Failure, FailureCategory

# Same bound as the arm's `MoveItExecutionClient`: how long a cancelled gripper goal may take to settle.
CANCELLATION_TIMEOUT_S = 5.0


class GripperClient:
    def __init__(
        self,
        client: Any,
        goal_factory: Callable[[float, float], Any] | None = None,
        progress: Callable[[], None] = lambda: None,
        cancellation_timeout_s: float = CANCELLATION_TIMEOUT_S,
    ) -> None:
        if cancellation_timeout_s < 0.0:
            raise ValueError("cancellation_timeout_s must be non-negative")
        self._client = client
        self._goal_factory = goal_factory
        self._progress = progress
        self._cancellation_timeout_s = cancellation_timeout_s

    def _cancel_and_settle(self, handle: Any, result_future: Any) -> bool:
        """Cancel the goal and wait, boundedly, for the cancel and the result to settle."""
        deadline = time.monotonic() + self._cancellation_timeout_s
        cancel_future = handle.cancel_goal_async()
        while not cancel_future.done() and time.monotonic() < deadline:
            self._progress()
            time.sleep(0.001)
        acknowledged = cancel_future.done()
        while not result_future.done() and time.monotonic() < deadline:
            self._progress()
            time.sleep(0.001)
        return bool(acknowledged and result_future.done())

    def command(self, q6: float, duration_s: float, timeout_s: float, *,
                before_dispatch: Callable[[], None] | None = None,
                monitor: Callable[[], None] | None = None) -> ActionResult:
        """Send one gripper goal.

        `monitor` has the arm path's contract: it is called on every wait iteration once the goal is accepted and
        raises `RuntimeError` to stop. A raise cancels the goal and the result is a `GRIPPER_MONITOR_ABORTED` failure
        whose message is the monitor's, with `cancel_settled` in its metrics. A raise while the goal response is still
        pending is held until the response arrives (bounded by the command deadline) and then cancels the goal.
        """

        def fail(status: ActionStatus, code: str, message: str | None = None, **metrics: float) -> ActionResult:
            return ActionResult(
                status,
                Failure(FailureCategory.GRIPPER, code, code if message is None else message, metrics),
            )

        if not self._client.wait_for_server(timeout_sec=timeout_s):
            return fail(ActionStatus.FAILED, "GRIPPER_ACTION_UNAVAILABLE")
        goal = (
            self._goal_factory(q6, duration_s)
            if self._goal_factory
            else make_gripper_goal(q6, duration_s)
        )
        deadline = time.monotonic() + timeout_s
        if before_dispatch is not None:
            before_dispatch()
        future = self._client.send_goal_async(goal)
        pending_abort: RuntimeError | None = None
        while not future.done() and time.monotonic() < deadline:
            self._progress()
            if monitor is not None and pending_abort is None:
                try:
                    monitor()
                except RuntimeError as error:
                    pending_abort = error
            time.sleep(0.001)
        if not future.done():
            return fail(ActionStatus.TIMED_OUT, "GRIPPER_GOAL_TIMEOUT")
        handle = future.result()
        if handle is None or not handle.accepted:
            return fail(ActionStatus.FAILED, "GRIPPER_GOAL_REJECTED")
        result_future = handle.get_result_async()

        def aborted(error: RuntimeError) -> ActionResult:
            settled = self._cancel_and_settle(handle, result_future)
            return fail(ActionStatus.FAILED, "GRIPPER_MONITOR_ABORTED", str(error), cancel_settled=float(settled))

        if pending_abort is not None:
            return aborted(pending_abort)
        while not result_future.done() and time.monotonic() < deadline:
            self._progress()
            if monitor is not None:
                try:
                    monitor()
                except RuntimeError as error:
                    return aborted(error)
            time.sleep(0.001)
        if not result_future.done():
            settled = self._cancel_and_settle(handle, result_future)
            return fail(ActionStatus.TIMED_OUT, "GRIPPER_RESULT_TIMEOUT", cancel_settled=float(settled))
        wrapped = result_future.result()
        result = getattr(wrapped, "result", wrapped)
        code = int(getattr(result, "error_code", 0))
        if code != 0:
            return fail(ActionStatus.FAILED, "GRIPPER_CONTROLLER_ERROR")
        return ActionResult(ActionStatus.SUCCEEDED)


def make_gripper_goal(q6: float, duration_s: float) -> Any:
    from builtin_interfaces.msg import Duration
    from control_msgs.action import FollowJointTrajectory
    from trajectory_msgs.msg import JointTrajectoryPoint

    goal = FollowJointTrajectory.Goal()
    goal.trajectory.joint_names = ["6"]
    seconds = int(duration_s)
    nanoseconds = int((duration_s - seconds) * 1e9)
    goal.trajectory.points = [
        JointTrajectoryPoint(
            positions=[q6],
            time_from_start=Duration(sec=seconds, nanosec=nanoseconds),
        )
    ]
    return goal
