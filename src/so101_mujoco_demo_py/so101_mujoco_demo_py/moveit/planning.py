"""Direct GetMotionPlan client with stable domain failures."""

import time
from dataclasses import dataclass
from typing import Any, Callable

from ..domain import Failure, FailureCategory


@dataclass(frozen=True, slots=True)
class JointPlanRequest:
    joint_names: tuple[str, ...]
    current_positions: tuple[float, ...]
    target_positions: tuple[float, ...]
    velocity_scaling: float = 0.1
    acceleration_scaling: float = 0.1
    planning_time_s: float = 5.0
    planning_group: str = "arm"
    tcp_link: str = "so101_tcp"


@dataclass(frozen=True, slots=True)
class PlanOutcome:
    trajectory: Any = None
    failure: Failure | None = None


class MoveItPlanningClient:
    def __init__(
        self,
        client: Any,
        request_factory: Callable[[JointPlanRequest], Any] | None = None,
        progress: Callable[[], None] = lambda: None,
    ) -> None:
        self._client = client
        self._request_factory = request_factory
        self._progress = progress

    def plan_joint_path(self, request: JointPlanRequest, timeout_s: float = 10.0) -> PlanOutcome:
        def failure(code: str, message: str, **metrics: float) -> PlanOutcome:
            return PlanOutcome(failure=Failure(FailureCategory.PLANNING, code, message, metrics))

        if not self._client.wait_for_service(timeout_sec=timeout_s):
            return failure("MOVEIT_PLAN_SERVICE_UNAVAILABLE", "GetMotionPlan unavailable")
        wire_request = self._request_factory(request) if self._request_factory else request
        future = self._client.call_async(wire_request)
        deadline = time.monotonic() + timeout_s
        while not future.done() and time.monotonic() < deadline:
            self._progress()
            time.sleep(0.001)
        if not future.done():
            return failure("MOVEIT_PLAN_TIMEOUT", "planning timed out")
        response = future.result()
        if response is None:
            return failure("MOVEIT_PLAN_FAILED", "empty planning response")
        motion = getattr(response, "motion_plan_response", response)
        code = int(getattr(getattr(motion, "error_code", None), "val", 1))
        trajectory = getattr(motion, "trajectory", None)
        points = getattr(getattr(trajectory, "joint_trajectory", None), "points", None)
        if code != 1:
            return failure(
                "MOVEIT_PLAN_FAILED",
                f"MoveIt error {code}",
                moveit_error_code=float(code),
            )
        if trajectory is None or (points is not None and not points):
            return failure("EMPTY_TRAJECTORY", "MoveIt returned an empty trajectory")
        return PlanOutcome(trajectory=trajectory)


def make_get_motion_plan_request(request: JointPlanRequest) -> Any:
    from moveit_msgs.msg import Constraints, JointConstraint, RobotState
    from moveit_msgs.srv import GetMotionPlan
    from sensor_msgs.msg import JointState

    wire = GetMotionPlan.Request()
    motion = wire.motion_plan_request
    motion.group_name = request.planning_group
    motion.num_planning_attempts = 1
    motion.allowed_planning_time = request.planning_time_s
    motion.max_velocity_scaling_factor = request.velocity_scaling
    motion.max_acceleration_scaling_factor = request.acceleration_scaling
    motion.start_state = RobotState(
        joint_state=JointState(
            name=list(request.joint_names),
            position=list(request.current_positions),
        )
    )
    constraints = Constraints()
    constraints.joint_constraints = [
        JointConstraint(
            joint_name=name,
            position=position,
            tolerance_above=1e-4,
            tolerance_below=1e-4,
            weight=1.0,
        )
        for name, position in zip(request.joint_names, request.target_positions)
    ]
    motion.goal_constraints = [constraints]
    return wire
