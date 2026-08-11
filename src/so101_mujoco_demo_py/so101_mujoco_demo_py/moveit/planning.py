"""Direct GetMotionPlan client with stable domain failures."""

import math
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
    start_state_joint_names: tuple[str, ...] | None = None
    start_state_positions: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not self.joint_names or len(self.joint_names) != len(self.current_positions):
            raise ValueError("joint request current state is incomplete")
        if len(self.joint_names) != len(self.target_positions):
            raise ValueError("joint request target state is incomplete")
        if (self.start_state_joint_names is None) != (self.start_state_positions is None):
            raise ValueError("extended start-state names and positions must be provided together")
        if self.start_state_joint_names is not None and (
            len(self.start_state_joint_names) != len(self.start_state_positions or ())
            or not set(self.joint_names) <= set(self.start_state_joint_names)
        ):
            raise ValueError("extended start state is incomplete")
        numeric = (
            *self.current_positions,
            *self.target_positions,
            *(self.start_state_positions or ()),
            self.velocity_scaling,
            self.acceleration_scaling,
            self.planning_time_s,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("joint request must contain only finite values")


@dataclass(frozen=True, slots=True)
class PosePlanRequest:
    joint_names: tuple[str, ...]
    current_positions: tuple[float, ...]
    target_position_m: tuple[float, float, float]
    target_orientation_xyzw: tuple[float, float, float, float]
    orientation_tolerance_rad: tuple[float, float, float]
    position_tolerance_m: float = 0.0005
    velocity_scaling: float = 0.05
    acceleration_scaling: float = 0.05
    planning_time_s: float = 5.0
    planning_group: str = "arm"
    frame_id: str = "world"
    tcp_link: str = "so101_tcp"
    enforce_orientation_path: bool = True

    def __post_init__(self) -> None:
        values = (
            *self.current_positions,
            *self.target_position_m,
            *self.target_orientation_xyzw,
            *self.orientation_tolerance_rad,
            self.position_tolerance_m,
            self.velocity_scaling,
            self.acceleration_scaling,
            self.planning_time_s,
        )
        if not self.joint_names or len(self.joint_names) != len(self.current_positions):
            raise ValueError("pose request joint state is incomplete")
        if any(not math.isfinite(value) for value in values):
            raise ValueError("pose request must contain only finite values")
        if self.frame_id != "world" or self.tcp_link != "so101_tcp":
            raise ValueError("calibration pose request must use world and so101_tcp")
        if any(value <= 0.0 for value in self.orientation_tolerance_rad):
            raise ValueError("orientation tolerances must be positive")
        if self.position_tolerance_m <= 0.0:
            raise ValueError("position tolerance must be positive")
        norm = math.sqrt(sum(value * value for value in self.target_orientation_xyzw))
        if not math.isclose(norm, 1.0, abs_tol=1e-3):
            raise ValueError("target orientation must be a unit quaternion")


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
        return self._plan(request, timeout_s)

    def plan_pose_path(self, request: PosePlanRequest, timeout_s: float = 10.0) -> PlanOutcome:
        return self._plan(request, timeout_s)

    def _plan(self, request: JointPlanRequest | PosePlanRequest, timeout_s: float) -> PlanOutcome:
        def failure(code: str, message: str, **metrics: float) -> PlanOutcome:
            return PlanOutcome(failure=Failure(FailureCategory.PLANNING, code, message, metrics))

        if not self._client.wait_for_service(timeout_sec=timeout_s):
            return failure("MOVEIT_PLAN_SERVICE_UNAVAILABLE", "GetMotionPlan unavailable")
        if self._request_factory:
            wire_request = self._request_factory(request)
        elif isinstance(request, PosePlanRequest):
            wire_request = make_get_motion_plan_pose_request(request)
        else:
            wire_request = request
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
    start_names = request.start_state_joint_names or request.joint_names
    start_positions = request.start_state_positions or request.current_positions
    motion.start_state = RobotState(
        joint_state=JointState(
            name=list(start_names),
            position=list(start_positions),
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


def make_get_motion_plan_pose_request(request: PosePlanRequest) -> Any:
    from geometry_msgs.msg import Pose
    from moveit_msgs.msg import (
        BoundingVolume,
        Constraints,
        OrientationConstraint,
        PositionConstraint,
        RobotState,
    )
    from moveit_msgs.srv import GetMotionPlan
    from sensor_msgs.msg import JointState
    from shape_msgs.msg import SolidPrimitive

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

    primitive = SolidPrimitive()
    primitive.type = SolidPrimitive.BOX
    primitive.dimensions = [2.0 * request.position_tolerance_m] * 3
    pose = Pose()
    pose.position.x, pose.position.y, pose.position.z = request.target_position_m
    pose.orientation.w = 1.0
    position = PositionConstraint()
    position.header.frame_id = request.frame_id
    position.link_name = request.tcp_link
    position.weight = 1.0
    position.constraint_region = BoundingVolume(primitives=[primitive], primitive_poses=[pose])

    orientation = OrientationConstraint()
    orientation.header.frame_id = request.frame_id
    orientation.link_name = request.tcp_link
    (
        orientation.orientation.x,
        orientation.orientation.y,
        orientation.orientation.z,
        orientation.orientation.w,
    ) = request.target_orientation_xyzw
    (
        orientation.absolute_x_axis_tolerance,
        orientation.absolute_y_axis_tolerance,
        orientation.absolute_z_axis_tolerance,
    ) = request.orientation_tolerance_rad
    orientation.weight = 1.0
    constraints = Constraints(
        position_constraints=[position], orientation_constraints=[orientation]
    )
    motion.goal_constraints = [constraints]
    if request.enforce_orientation_path:
        motion.path_constraints = Constraints(orientation_constraints=[orientation])
    return wire
