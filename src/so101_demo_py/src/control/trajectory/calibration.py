"""Pose-constrained, fail-closed contact-calibration approach."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from so101_demo.control.moveit.planning import PosePlanRequest


class ApproachSafetyAbort(RuntimeError):
    """Raised when retrying a calibration approach would be unsafe."""


@dataclass(frozen=True, slots=True)
class ApproachObservation:
    joint_names: tuple[str, ...]
    joint_positions_rad: tuple[float, ...]
    joint_velocities_rad_s: tuple[float, ...]
    gripper_position_rad: float
    tcp_position_world_m: tuple[float, float, float]
    cup_position_world_m: tuple[float, float, float]
    fingertip_contacts: frozenset[str]
    forbidden_contacts: frozenset[str]
    maximum_normal_force_n: float
    paused: bool
    simulation_session_id: str
    reset_epoch: int
    publisher_sequence: int
    received_monotonic_s: float


@dataclass(frozen=True, slots=True)
class PoseTrajectoryPoint:
    joint_positions_rad: tuple[float, ...]
    tcp_position_world_m: tuple[float, float, float]
    tcp_orientation_xyzw: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PoseTrajectory:
    joint_names: tuple[str, ...]
    points: tuple[PoseTrajectoryPoint, ...]
    wire_trajectory: Any = None


@dataclass(frozen=True, slots=True)
class CalibrationApproachPolicy:
    arm_joints: tuple[str, ...]
    stable_home_rad: tuple[float, ...]
    pregrasp_offset_m: tuple[float, float, float]
    contact_offset_m: tuple[float, float, float]
    tcp_orientation_xyzw: tuple[float, float, float, float]
    orientation_tolerance_rad: tuple[float, float, float]
    start_tolerance_rad: float
    home_tolerance_rad: float
    max_joint_speed_rad_s: float
    max_lateral_deviation_m: float
    max_cup_displacement_m: float
    max_diagnostic_force_n: float
    max_receipt_age_s: float
    max_replans: int


@dataclass(frozen=True, slots=True)
class ApproachTargets:
    pregrasp_position_m: tuple[float, float, float]
    contact_position_m: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class ApproachResult:
    valid: bool
    reason: str
    replan_count: int
    completed_phases: tuple[str, ...]


def derive_approach_targets(
    cup_position_world_m: tuple[float, float, float], policy: CalibrationApproachPolicy
) -> ApproachTargets:
    def offset(values: tuple[float, float, float]) -> tuple[float, float, float]:
        return tuple(cup_position_world_m[index] + values[index] for index in range(3))

    return ApproachTargets(
        offset(policy.pregrasp_offset_m),
        offset(policy.contact_offset_m),
        policy.tcp_orientation_xyzw,
    )


def _within(actual: tuple[float, ...], expected: tuple[float, ...], tolerance: float) -> bool:
    return len(actual) == len(expected) and all(
        abs(left - right) <= tolerance for left, right in zip(actual, expected, strict=True)
    )


def _orientation_error(
    actual: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
) -> float:
    actual_norm = math.sqrt(sum(value * value for value in actual))
    expected_norm = math.sqrt(sum(value * value for value in expected))
    if actual_norm == 0.0 or expected_norm == 0.0:
        return math.inf
    dot = abs(
        sum(left * right for left, right in zip(actual, expected, strict=True))
        / (actual_norm * expected_norm)
    )
    return 2.0 * math.acos(min(1.0, dot))


class CalibrationApproachRunner:
    """Plan from fresh state, check handoff drift, then execute while monitoring."""

    def __init__(
        self,
        observe: Callable[[], ApproachObservation],
        plan: Callable[[PosePlanRequest], PoseTrajectory | None],
        execute: Callable[[PoseTrajectory, Callable[[], None]], bool],
        policy: CalibrationApproachPolicy,
        *,
        monotonic: Callable[[], float],
    ) -> None:
        self._observe = observe
        self._plan = plan
        self._execute = execute
        self._policy = policy
        self._monotonic = monotonic

    def run(self, *, max_phases: int = 2, descend_only: bool = False) -> ApproachResult:
        initial = self._observe()
        try:
            self._require_initial_home(initial)
            self._require_safe(initial, initial)
        except ApproachSafetyAbort:
            raise
        targets = derive_approach_targets(initial.cup_position_world_m, self._policy)
        phases = (
            (("descent", targets.contact_position_m),)
            if descend_only
            else (
                ("pregrasp", targets.pregrasp_position_m),
                ("descent", targets.contact_position_m),
            )
        )
        completed: list[str] = []
        replan_count = 0
        for phase, target in phases[:max_phases]:
            phase_result, used_replans = self._run_phase(
                phase, target, targets.orientation_xyzw, initial
            )
            replan_count += used_replans
            if phase_result is not None:
                return ApproachResult(False, phase_result, replan_count, tuple(completed))
            completed.append(phase)
        return ApproachResult(True, "", replan_count, tuple(completed))

    def _run_phase(
        self,
        phase: str,
        target: tuple[float, float, float],
        orientation: tuple[float, float, float, float],
        reference: ApproachObservation,
    ) -> tuple[str | None, int]:
        replans = 0
        start = self._observe()
        self._require_safe(start, reference)
        while True:
            request = PosePlanRequest(
                joint_names=(*self._policy.arm_joints, "6"),
                current_positions=(
                    *start.joint_positions_rad,
                    start.gripper_position_rad,
                ),
                target_position_m=target,
                target_orientation_xyzw=orientation,
                orientation_tolerance_rad=self._policy.orientation_tolerance_rad,
                enforce_orientation_path=phase == "descent",
            )
            trajectory = self._plan(request)
            if trajectory is None:
                return "planning failed", replans
            reason = self._validate_trajectory(phase, trajectory, start, target, orientation)
            if reason:
                return reason, replans
            handoff = self._observe()
            self._require_safe(handoff, reference)
            first = trajectory.points[0].joint_positions_rad
            if not _within(handoff.joint_positions_rad, first, self._policy.start_tolerance_rad):
                if replans >= self._policy.max_replans:
                    return "plan-to-execute start drift exhausted replan budget", replans
                replans += 1
                start = handoff
                continue

            def monitor() -> None:
                self._require_safe(self._observe(), reference)

            if not self._execute(trajectory, monitor):
                return "trajectory execution failed", replans
            self._require_safe(self._observe(), reference)
            return None, replans

    def _require_initial_home(self, observation: ApproachObservation) -> None:
        if observation.joint_names != self._policy.arm_joints:
            raise ApproachSafetyAbort("stable home joint names mismatch")
        if not _within(
            observation.joint_positions_rad,
            self._policy.stable_home_rad,
            self._policy.home_tolerance_rad,
        ):
            raise ApproachSafetyAbort("stable home position mismatch")
        if any(
            abs(value) > self._policy.max_joint_speed_rad_s
            for value in observation.joint_velocities_rad_s
        ):
            raise ApproachSafetyAbort("stable home joint speed exceeded")

    def _require_safe(
        self, observation: ApproachObservation, reference: ApproachObservation
    ) -> None:
        age = self._monotonic() - observation.received_monotonic_s
        if not math.isfinite(age) or age < 0.0 or age > self._policy.max_receipt_age_s:
            raise ApproachSafetyAbort("stale approach observation")
        if observation.paused:
            raise ApproachSafetyAbort("MuJoCo physics is paused")
        if observation.simulation_session_id != reference.simulation_session_id:
            raise ApproachSafetyAbort("simulation session changed")
        if observation.reset_epoch != reference.reset_epoch:
            raise ApproachSafetyAbort("reset epoch changed")
        if observation.fingertip_contacts:
            raise ApproachSafetyAbort("early fingertip contact")
        if observation.forbidden_contacts:
            raise ApproachSafetyAbort("forbidden robot/table contact")
        if observation.maximum_normal_force_n > self._policy.max_diagnostic_force_n:
            raise ApproachSafetyAbort("diagnostic force boundary exceeded")
        if (
            math.dist(observation.cup_position_world_m, reference.cup_position_world_m)
            > self._policy.max_cup_displacement_m
        ):
            raise ApproachSafetyAbort("pre-contact cup displacement exceeded")

    def _validate_trajectory(
        self,
        phase: str,
        trajectory: PoseTrajectory,
        start: ApproachObservation,
        target: tuple[float, float, float],
        orientation: tuple[float, float, float, float],
    ) -> str | None:
        if not trajectory.points:
            return "empty trajectory"
        if trajectory.joint_names != start.joint_names:
            return "trajectory joint names mismatch"
        if not _within(
            trajectory.points[0].joint_positions_rad,
            start.joint_positions_rad,
            self._policy.start_tolerance_rad,
        ):
            return "trajectory start mismatch"
        endpoint = trajectory.points[-1]
        if math.dist(endpoint.tcp_position_world_m, target) > 0.0005:
            return "trajectory pose endpoint mismatch"
        if _orientation_error(endpoint.tcp_orientation_xyzw, orientation) > max(
            self._policy.orientation_tolerance_rad
        ):
            return "trajectory orientation mismatch"
        if phase == "descent":
            reason = self._validate_axial_descent(trajectory.points)
            if reason:
                return reason
        return None

    def _validate_axial_descent(self, points: tuple[PoseTrajectoryPoint, ...]) -> str | None:
        origin = points[0].tcp_position_world_m
        endpoint = points[-1].tcp_position_world_m
        direction = tuple(endpoint[index] - origin[index] for index in range(3))
        length = math.sqrt(sum(value * value for value in direction))
        if length == 0.0:
            return "descent axial path has zero length"
        axis = tuple(value / length for value in direction)
        previous = 0.0
        for point in points[1:]:
            delta = tuple(point.tcp_position_world_m[index] - origin[index] for index in range(3))
            axial = sum(delta[index] * axis[index] for index in range(3))
            if axial + 1e-6 < previous:
                return "descent axial path is non-monotonic"
            previous = axial
            lateral = math.sqrt(
                sum((delta[index] - axial * axis[index]) ** 2 for index in range(3))
            )
            if lateral > self._policy.max_lateral_deviation_m:
                return "descent lateral deviation exceeded"
        return None
