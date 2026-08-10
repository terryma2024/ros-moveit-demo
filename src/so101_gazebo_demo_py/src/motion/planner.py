"""ROS-free motion request composition and trajectory validation."""

from dataclasses import dataclass
import math
from typing import Any

from ..domain import Failure, FailureCategory, State
from ..moveit.planning import JointPlanRequest, PlanOutcome
from ..policy_config import MotionPolicyConfig, ValidationPolicyConfig
from ..profile import SO101Profile
from .evidence import RobotStateEvidence


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    positions: tuple[float, ...]
    time_s: float
    tcp_position: tuple[float, float, float] | None = None
    contacts: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Trajectory:
    joint_names: tuple[str, ...]
    points: tuple[TrajectoryPoint, ...]


@dataclass(frozen=True, slots=True)
class ValidationRules:
    endpoint_tolerance: float
    max_jump: float
    min_duration: float
    waypoint_tolerance: float | None = None
    path_direction: tuple[float, float, float] | None = None
    monotonic_tolerance: float = 0.0
    max_lateral_deviation: float | None = None
    allowed_contacts: frozenset[str] = frozenset()


def _failure(code: str, message: str, **metrics: float) -> Failure:
    return Failure(FailureCategory.PLAN_VALIDATION, code, message, metrics)


def _within(actual: tuple[float, ...], expected: tuple[float, ...], tolerance: float) -> bool:
    return len(actual) == len(expected) and all(
        abs(actual_value - expected_value) <= tolerance
        for actual_value, expected_value in zip(actual, expected)
    )


def _validate_tcp_path(points: tuple[TrajectoryPoint, ...], rules: ValidationRules) -> Failure | None:
    if rules.path_direction is None:
        return None
    tcp = tuple(point.tcp_position for point in points)
    if any(position is None for position in tcp):
        return _failure("TRAJECTORY_TCP_EVIDENCE_MISSING", "TCP samples are required")
    direction_norm = math.sqrt(sum(value * value for value in rules.path_direction))
    if direction_norm == 0.0:
        return _failure("TRAJECTORY_PATH_DIRECTION_INVALID", "path direction is zero")
    axis = tuple(value / direction_norm for value in rules.path_direction)
    origin = tcp[0]
    previous_axial = 0.0
    for position in tcp[1:]:
        delta = tuple(position[index] - origin[index] for index in range(3))
        axial = sum(delta[index] * axis[index] for index in range(3))
        if axial + rules.monotonic_tolerance < previous_axial:
            return _failure("TRAJECTORY_AXIAL_NONMONOTONIC", "TCP reverses along path axis")
        previous_axial = axial
        if rules.max_lateral_deviation is not None:
            lateral = math.sqrt(sum((delta[index] - axial * axis[index]) ** 2 for index in range(3)))
            if lateral > rules.max_lateral_deviation:
                return _failure(
                    "TRAJECTORY_LATERAL_DEVIATION", "TCP leaves axial corridor",
                    lateral_deviation_m=lateral,
                )
    return None


def validate_trajectory(
    state: State,
    trajectory: Trajectory,
    evidence: RobotStateEvidence,
    target: tuple[float, ...],
    endpoint_tolerance: float | None = None,
    max_jump: float | None = None,
    min_duration: float | None = None,
    *,
    rules: ValidationRules | None = None,
    required_waypoints: tuple[tuple[float, ...], ...] = (),
) -> Failure | None:
    del state
    if rules is None:
        if endpoint_tolerance is None or max_jump is None or min_duration is None:
            raise TypeError("validation tolerances are required")
        rules = ValidationRules(endpoint_tolerance, max_jump, min_duration)
    if not trajectory.points:
        return _failure("EMPTY_TRAJECTORY", "trajectory has no points")
    if trajectory.joint_names != evidence.joint_names:
        return _failure("TRAJECTORY_JOINTS_MISMATCH", "trajectory joint order differs")
    if not _within(trajectory.points[0].positions, evidence.positions, rules.endpoint_tolerance):
        return _failure("TRAJECTORY_START_MISMATCH", "trajectory start differs from observed state")
    if not _within(trajectory.points[-1].positions, target, rules.endpoint_tolerance):
        return _failure("TRAJECTORY_ENDPOINT_MISMATCH", "trajectory endpoint differs from target")
    for previous, current in zip(trajectory.points, trajectory.points[1:]):
        if any(abs(left - right) > rules.max_jump for left, right in zip(previous.positions, current.positions)):
            return _failure("TRAJECTORY_JOINT_JUMP", "trajectory exceeds maximum joint jump")
        if current.time_s < previous.time_s:
            return _failure("TRAJECTORY_TIME_NONMONOTONIC", "trajectory time decreases")
    if trajectory.points[-1].time_s < rules.min_duration:
        return _failure("TRAJECTORY_DURATION_TOO_SHORT", "trajectory duration is too short")
    waypoint_tolerance = rules.waypoint_tolerance or rules.endpoint_tolerance
    search_start = 0
    for waypoint in required_waypoints:
        match = next((index for index in range(search_start, len(trajectory.points))
                      if _within(trajectory.points[index].positions, waypoint, waypoint_tolerance)), None)
        if match is None:
            return _failure("TRAJECTORY_WAYPOINT_MISSING", "required waypoint ladder is not visited")
        search_start = match + 1
    for point in trajectory.points:
        forbidden = point.contacts - rules.allowed_contacts
        if forbidden:
            return _failure("TRAJECTORY_FORBIDDEN_CONTACT", f"forbidden contacts: {sorted(forbidden)}")
    return _validate_tcp_path(trajectory.points, rules)


class MotionPlanner:
    """Compose a state-specific joint request for the direct MoveIt client."""

    def __init__(self, planning_client: Any, observer: Any) -> None:
        self._planning_client = planning_client
        self._observer = observer

    def plan(self, state: State, profile: SO101Profile, policy: MotionPolicyConfig) -> PlanOutcome:
        state_policy = policy.states[state]
        evidence = self._observer.sample(timeout_s=2.0)
        if isinstance(evidence, Failure):
            return PlanOutcome(failure=evidence)
        request = JointPlanRequest(
            profile.arm_joints,
            evidence.positions,
            state_policy.waypoints[-1],
            state_policy.velocity_scaling,
            state_policy.acceleration_scaling,
        )
        return self._planning_client.plan_joint_path(request)


def rules_from_policy(state: State, policy: ValidationPolicyConfig) -> ValidationRules:
    data = policy.states[state].data
    temporal = data.get("temporal_contact") or {}
    return ValidationRules(
        endpoint_tolerance=float(data["joint_endpoint_tolerance_rad"]),
        max_jump=float(data["max_joint_jump_rad"]),
        min_duration=float(data["min_duration_s"]),
        path_direction=tuple(float(value) for value in data["path_direction"]),
        monotonic_tolerance=float(data["monotonic_tolerance_m"]),
        max_lateral_deviation=float(data["max_lateral_deviation_m"]),
        allowed_contacts=frozenset(data.get("allowed_touch_pairs", ())) | frozenset(temporal.get("allowed_pairs", ())),
    )
