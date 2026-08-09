"""ROS-free deterministic evaluation of a post-release physical outcome."""

from dataclasses import asdict, dataclass
import math
from types import MappingProxyType
from typing import Mapping

from .policy_config import PhysicalOutcomeConfig


Pose = tuple[float, float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class FinalPlacementSample:
    release_epoch_id: str
    receipt_sequence: int
    source_timestamp_s: float
    observed_monotonic_s: float
    pose_xyz_xyzw: Pose
    support_contact: bool
    gripper_contact: bool
    gazebo_detached: bool
    moveit_detached: bool
    controller_healthy: bool
    safety_healthy: bool
    shadow_divergence_healthy: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FinalPlacementResult:
    success: bool
    failure_code: str | None
    sample_count: int
    duration_s: float
    max_linear_speed_m_s: float | None
    max_angular_speed_rad_s: float | None
    metrics: Mapping[str, float]
    telemetry: tuple[FinalPlacementSample, ...]


def _finite_sample(sample: FinalPlacementSample, maximum_age_s: float) -> bool:
    numeric = (
        sample.source_timestamp_s, sample.observed_monotonic_s,
        *sample.pose_xyz_xyzw,
    )
    return (
        bool(sample.release_epoch_id)
        and sample.receipt_sequence >= 0
        and all(math.isfinite(value) for value in numeric)
        and 0.0 <= sample.observed_monotonic_s - sample.source_timestamp_s <= maximum_age_s
    )


def _quaternion_angle(first: Pose, second: Pose) -> float:
    dot = abs(sum(a * b for a, b in zip(first[3:], second[3:])))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def _upright_tilt(pose: Pose) -> float:
    x, y, _, w = pose[3:]
    rotated_z_z = 1.0 - 2.0 * (x * x + y * y)
    return math.acos(max(-1.0, min(1.0, rotated_z_z)))


def evaluate_final_placement(
    samples: tuple[FinalPlacementSample, ...],
    policy: PhysicalOutcomeConfig,
    release_epoch_id: str,
    release_marker_sequence: int,
) -> FinalPlacementResult:
    """Evaluate only fresh samples strictly newer than the active release marker."""
    eligible = tuple(
        sample for sample in samples
        if sample.release_epoch_id == release_epoch_id
        and sample.receipt_sequence > release_marker_sequence
    )
    telemetry = eligible[-policy.max_telemetry_samples:]
    finite = all(_finite_sample(sample, policy.max_observation_age_s) for sample in eligible)
    monotonic = all(
        later.source_timestamp_s > earlier.source_timestamp_s
        and later.receipt_sequence > earlier.receipt_sequence
        for earlier, later in zip(eligible, eligible[1:])
    )
    duration = round(
        eligible[-1].source_timestamp_s - eligible[0].source_timestamp_s, 12,
    ) if eligible else 0.0

    linear_speeds: list[float] = []
    angular_speeds: list[float] = []
    if finite and monotonic:
        for earlier, later in zip(eligible, eligible[1:]):
            elapsed = later.source_timestamp_s - earlier.source_timestamp_s
            linear_speeds.append(
                math.dist(earlier.pose_xyz_xyzw[:3], later.pose_xyz_xyzw[:3]) / elapsed
            )
            angular_speeds.append(_quaternion_angle(earlier.pose_xyz_xyzw, later.pose_xyz_xyzw) / elapsed)
    maximum_linear = max(linear_speeds, default=None)
    maximum_angular = max(angular_speeds, default=None)
    latest = eligible[-1] if eligible else None
    metrics = {} if latest is None else {
        "final_x_m": latest.pose_xyz_xyzw[0],
        "final_y_m": latest.pose_xyz_xyzw[1],
        "final_z_m": latest.pose_xyz_xyzw[2],
        "final_upright_tilt_rad": _upright_tilt(latest.pose_xyz_xyzw),
        "maximum_linear_speed_m_s": maximum_linear or 0.0,
        "maximum_angular_speed_rad_s": maximum_angular or 0.0,
    }

    code: str | None = None
    if (
        len(eligible) < policy.consecutive_samples
        or not finite or not monotonic
        or duration < policy.minimum_stable_duration_s
    ):
        code = "FINAL_STALE_EVIDENCE"
    elif any(not sample.safety_healthy or not sample.controller_healthy for sample in eligible):
        code = "FINAL_SAFETY_FAILURE"
    elif any(not sample.shadow_divergence_healthy for sample in eligible):
        code = "FINAL_PLANNING_SHADOW_DIVERGENCE"
    elif any(not sample.gazebo_detached or not sample.moveit_detached for sample in eligible):
        code = "FINAL_SAFETY_FAILURE"
    elif any(sample.gripper_contact for sample in eligible):
        code = "FINAL_GRIPPER_CONTACT"
    elif any(not sample.support_contact for sample in eligible):
        code = "FINAL_UNSUPPORTED"
    elif not (
        policy.final_target_min_xy_m[0] <= latest.pose_xyz_xyzw[0] <= policy.final_target_max_xy_m[0]
        and policy.final_target_min_xy_m[1] <= latest.pose_xyz_xyzw[1] <= policy.final_target_max_xy_m[1]
    ):
        code = "FINAL_OUT_OF_REGION"
    elif not policy.support_height_range_m[0] <= latest.pose_xyz_xyzw[2] <= policy.support_height_range_m[1]:
        code = "FINAL_UNSUPPORTED"
    elif metrics["final_upright_tilt_rad"] > policy.max_upright_tilt_rad:
        code = "FINAL_TIPPED"
    elif (
        maximum_linear is None or maximum_angular is None
        or maximum_linear > policy.max_linear_speed_m_s
        or maximum_angular > policy.max_angular_speed_rad_s
    ):
        code = "FINAL_STILL_MOVING"

    return FinalPlacementResult(
        success=code is None,
        failure_code=code,
        sample_count=len(eligible),
        duration_s=duration,
        max_linear_speed_m_s=maximum_linear,
        max_angular_speed_rad_s=maximum_angular,
        metrics=MappingProxyType(metrics),
        telemetry=telemetry,
    )
