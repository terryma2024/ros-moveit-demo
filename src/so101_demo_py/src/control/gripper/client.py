"""FollowJointTrajectory adapter for the single SO-101 joint 6."""

import time
from typing import Any, Callable

from ...core.domain import ActionResult, ActionStatus, Failure, FailureCategory


class GripperClient:
    def __init__(
        self,
        client: Any,
        goal_factory: Callable[[float, float], Any] | None = None,
        progress: Callable[[], None] = lambda: None,
    ) -> None:
        self._client = client
        self._goal_factory = goal_factory
        self._progress = progress

    def command(self, q6: float, duration_s: float, timeout_s: float) -> ActionResult:
        def fail(status: ActionStatus, code: str) -> ActionResult:
            return ActionResult(
                status,
                Failure(FailureCategory.GRIPPER, code, code),
            )

        if not self._client.wait_for_server(timeout_sec=timeout_s):
            return fail(ActionStatus.FAILED, "GRIPPER_ACTION_UNAVAILABLE")
        goal = (
            self._goal_factory(q6, duration_s)
            if self._goal_factory
            else make_gripper_goal(q6, duration_s)
        )
        deadline = time.monotonic() + timeout_s
        future = self._client.send_goal_async(goal)
        while not future.done() and time.monotonic() < deadline:
            self._progress()
            time.sleep(0.001)
        if not future.done():
            return fail(ActionStatus.TIMED_OUT, "GRIPPER_GOAL_TIMEOUT")
        handle = future.result()
        if handle is None or not handle.accepted:
            return fail(ActionStatus.FAILED, "GRIPPER_GOAL_REJECTED")
        result_future = handle.get_result_async()
        while not result_future.done() and time.monotonic() < deadline:
            self._progress()
            time.sleep(0.001)
        if not result_future.done():
            handle.cancel_goal_async()
            return fail(ActionStatus.TIMED_OUT, "GRIPPER_RESULT_TIMEOUT")
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
