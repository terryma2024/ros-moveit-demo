"""Deterministic, ROS-free evaluation of a physical grasp window."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from so101_mujoco_demo_py.contact_policy import ApprovedContactPolicy
from so101_mujoco_demo_py.simulation.types import ReceivedSimulationEvidence


@dataclass(frozen=True, slots=True)
class GraspOutcome:
    success: bool
    failure_code: str | None
    sample_count: int
    duration_s: float
    metrics: Mapping[str, float]
    telemetry: tuple[ReceivedSimulationEvidence, ...]


Pose = tuple[float, float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class CarrySample:
    segment: str
    simulation_session_id: str
    reset_epoch: int
    publisher_sequence: int
    simulation_time_s: float
    received_monotonic_s: float
    cup_pose_xyz_xyzw: Pose
    tcp_pose_xyz_xyzw: Pose
    table_contact: bool
    table_clearance_m: float
    left_force_n: float
    right_force_n: float
    maximum_force_n: float
    forbidden_contact: bool

    def __post_init__(self) -> None:
        for name in ("segment", "simulation_session_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("reset_epoch", "publisher_sequence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "simulation_time_s",
            "received_monotonic_s",
            "table_clearance_m",
            "left_force_n",
            "right_force_n",
            "maximum_force_n",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite non-negative number")
            if not math.isfinite(float(value)) or value < 0.0:
                raise ValueError(f"{name} must be a finite non-negative number")
        for name in ("cup_pose_xyz_xyzw", "tcp_pose_xyz_xyzw"):
            pose = getattr(self, name)
            if (
                not isinstance(pose, tuple)
                or len(pose) != 7
                or not all(math.isfinite(float(value)) for value in pose)
            ):
                raise ValueError(f"{name} must contain seven finite numbers")
            if math.sqrt(sum(float(value) ** 2 for value in pose[3:])) <= 0.0:
                raise ValueError(f"{name} quaternion must be non-zero")
        for name in ("table_contact", "forbidden_contact"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if self.maximum_force_n < max(self.left_force_n, self.right_force_n):
            raise ValueError("maximum_force_n must cover both fingertip forces")


@dataclass(frozen=True, slots=True)
class CarryOutcome:
    success: bool
    failure_code: str | None
    sample_count: int
    metrics: Mapping[str, float]
    telemetry: tuple[CarrySample, ...]


@dataclass(frozen=True, slots=True)
class MicroLiftPolicy:
    minimum_cup_lift_m: float
    maximum_cup_lift_m: float
    minimum_tcp_lift_m: float
    maximum_lateral_drift_m: float
    maximum_relative_position_drift_m: float
    minimum_stable_duration_s: float


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    maximum_relative_position_drift_m: float
    maximum_relative_orientation_drift_rad: float
    minimum_table_clearance_m: float


@dataclass(frozen=True, slots=True)
class CarryPolicy:
    micro_lift: MicroLiftPolicy
    transport: TransportPolicy
    max_observation_age_s: float
    catastrophic_workspace_bounds_m: tuple[float, ...]


def _speed(sample: ReceivedSimulationEvidence) -> float:
    return math.sqrt(
        sum(float(value) ** 2 for value in sample.evidence.object_state.linear_velocity_world)
    )


def _side_force(sample: ReceivedSimulationEvidence, side: str) -> float:
    contacts = getattr(sample.evidence, f"{side}_fingertip_contacts")
    return sum(float(item.normal_force_n) for item in contacts)


def _forbidden_contact(
    sample: ReceivedSimulationEvidence,
    allowed_names: frozenset[str],
) -> bool:
    return any(
        contact.body2 not in allowed_names and contact.geom2 not in allowed_names
        for contact in sample.evidence.other_object_contacts
    )


def _evaluate_grasp_window(
    eligible: tuple[ReceivedSimulationEvidence, ...],
    policy: ApprovedContactPolicy,
    expected_session_id: str,
    expected_reset_epoch: int,
    now_monotonic_s: float,
) -> GraspOutcome:
    thresholds = policy.thresholds
    evaluation = policy.evaluation
    duration = (
        eligible[-1].evidence.simulation_time_s - eligible[0].evidence.simulation_time_s
        if eligible
        else 0.0
    )
    left_forces = tuple(_side_force(sample, "left") for sample in eligible)
    right_forces = tuple(_side_force(sample, "right") for sample in eligible)
    maximum_force = max(
        (sample.evidence.maximum_normal_force_n for sample in eligible), default=0.0
    )
    maximum_compression = max(
        (max(0.0, -sample.evidence.minimum_signed_distance_m) for sample in eligible),
        default=0.0,
    )
    maximum_speed = max((_speed(sample) for sample in eligible), default=0.0)
    metrics = MappingProxyType(
        {
            "minimum_left_force_n": min(left_forces, default=0.0),
            "minimum_right_force_n": min(right_forces, default=0.0),
            "maximum_force_n": maximum_force,
            "maximum_compression_distance_m": maximum_compression,
            "maximum_linear_speed_m_s": maximum_speed,
        }
    )

    monotonic = all(
        later.evidence.publisher_sequence > earlier.evidence.publisher_sequence
        and later.evidence.simulation_time_s > earlier.evidence.simulation_time_s
        and later.received_monotonic_s > earlier.received_monotonic_s
        for earlier, later in zip(eligible, eligible[1:])
    )
    latest_age = now_monotonic_s - eligible[-1].received_monotonic_s if eligible else math.inf

    code: str | None = None
    if (
        len(eligible) < evaluation.minimum_consecutive_samples
        or not monotonic
        or not math.isfinite(latest_age)
        or latest_age < 0.0
        or latest_age > evaluation.maximum_observation_age_s
    ):
        code = "GRASP_STALE_EVIDENCE"
    elif any(
        sample.evidence.simulation_session_id != expected_session_id
        or sample.evidence.reset_epoch != expected_reset_epoch
        for sample in eligible
    ):
        code = "GRASP_PROVENANCE_MISMATCH"
    elif any(sample.evidence.truncated for sample in eligible):
        code = "GRASP_TRUNCATED_CONTACTS"
    elif any(
        _forbidden_contact(sample, policy.allowed_other_contact_bodies) for sample in eligible
    ):
        code = "GRASP_FORBIDDEN_CONTACT"
    elif any(not sample.evidence.left_fingertip_contacts for sample in eligible):
        code = "GRASP_LEFT_CONTACT_MISSING"
    elif any(not sample.evidence.right_fingertip_contacts for sample in eligible):
        code = "GRASP_RIGHT_CONTACT_MISSING"
    elif (
        metrics["minimum_left_force_n"] < thresholds.minimum_bilateral_force_n
        or metrics["minimum_right_force_n"] < thresholds.minimum_bilateral_force_n
    ):
        code = "GRASP_FORCE_TOO_LOW"
    elif maximum_force > thresholds.maximum_safe_force_n:
        code = "GRASP_FORCE_TOO_HIGH"
    elif maximum_compression > thresholds.maximum_compression_distance_m:
        code = "GRASP_OVER_COMPRESSED"
    elif maximum_speed > thresholds.maximum_hold_linear_speed_m_s:
        code = "GRASP_SLIPPING"
    elif duration < thresholds.minimum_stable_hold_duration_s:
        code = "GRASP_DWELL_TOO_SHORT"

    return GraspOutcome(
        success=code is None,
        failure_code=code,
        sample_count=len(eligible),
        duration_s=duration,
        metrics=metrics,
        telemetry=eligible,
    )


def evaluate_grasp(
    samples: tuple[ReceivedSimulationEvidence, ...],
    policy: ApprovedContactPolicy,
    expected_session_id: str,
    expected_reset_epoch: int,
    action_boundary_sequence: int,
    now_monotonic_s: float,
) -> GraspOutcome:
    """Evaluate only atomic evidence newer than the grasp action boundary."""

    eligible = tuple(
        item for item in samples if item.evidence.publisher_sequence > action_boundary_sequence
    )
    return _evaluate_grasp_window(
        eligible,
        policy,
        expected_session_id,
        expected_reset_epoch,
        now_monotonic_s,
    )


def _carry_eligible(
    samples: tuple[CarrySample, ...], action_boundary_sequence: int
) -> tuple[CarrySample, ...]:
    return tuple(
        sample for sample in samples if sample.publisher_sequence > action_boundary_sequence
    )


def _carry_common_failure(
    samples: tuple[CarrySample, ...],
    contact_policy: ApprovedContactPolicy,
    carry_policy: CarryPolicy,
    expected_session_id: str,
    expected_reset_epoch: int,
    now_monotonic_s: float,
) -> str | None:
    monotonic = all(
        later.publisher_sequence > earlier.publisher_sequence
        and later.simulation_time_s > earlier.simulation_time_s
        and later.received_monotonic_s > earlier.received_monotonic_s
        for earlier, later in zip(samples, samples[1:])
    )
    latest_age = now_monotonic_s - samples[-1].received_monotonic_s if samples else math.inf
    if (
        not samples
        or not monotonic
        or not math.isfinite(latest_age)
        or latest_age < 0.0
        or latest_age > carry_policy.max_observation_age_s
    ):
        return "CARRY_STALE_EVIDENCE"
    if any(
        sample.simulation_session_id != expected_session_id
        or sample.reset_epoch != expected_reset_epoch
        for sample in samples
    ):
        return "CARRY_PROVENANCE_MISMATCH"
    if any(not _inside_workspace(sample.cup_pose_xyz_xyzw, carry_policy) for sample in samples):
        return "CARRY_WORKSPACE_EXIT"
    if any(sample.forbidden_contact for sample in samples):
        return "CARRY_FORBIDDEN_CONTACT"
    if any(sample.left_force_n <= 0.0 for sample in samples):
        return "CARRY_LEFT_CONTACT_MISSING"
    if any(sample.right_force_n <= 0.0 for sample in samples):
        return "CARRY_RIGHT_CONTACT_MISSING"
    thresholds = contact_policy.thresholds
    if any(
        sample.left_force_n < thresholds.minimum_bilateral_force_n
        or sample.right_force_n < thresholds.minimum_bilateral_force_n
        for sample in samples
    ):
        return "CARRY_FORCE_TOO_LOW"
    if any(sample.maximum_force_n > thresholds.maximum_safe_force_n for sample in samples):
        return "CARRY_FORCE_TOO_HIGH"
    return None


def _inside_workspace(pose: Pose, policy: CarryPolicy) -> bool:
    bounds = policy.catastrophic_workspace_bounds_m
    return all(bounds[index] <= pose[index] <= bounds[index + 3] for index in range(3))


def _relative_position(sample: CarrySample) -> tuple[float, float, float]:
    return tuple(
        sample.cup_pose_xyz_xyzw[index] - sample.tcp_pose_xyz_xyzw[index] for index in range(3)
    )


def _quaternion_normalized(value: tuple[float, float, float, float]) -> tuple[float, ...]:
    magnitude = math.sqrt(sum(item * item for item in value))
    return tuple(item / magnitude for item in value)


def _quaternion_multiply(
    left: tuple[float, ...], right: tuple[float, ...]
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def _relative_orientation(sample: CarrySample) -> tuple[float, float, float, float]:
    cup = _quaternion_normalized(sample.cup_pose_xyz_xyzw[3:])
    tcp = _quaternion_normalized(sample.tcp_pose_xyz_xyzw[3:])
    tcp_inverse = (-tcp[0], -tcp[1], -tcp[2], tcp[3])
    return _quaternion_multiply(tcp_inverse, cup)


def _quaternion_distance(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    dot = abs(sum(left * right for left, right in zip(first, second, strict=True)))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def _relative_position_drift(samples: tuple[CarrySample, ...]) -> float:
    if not samples:
        return 0.0
    initial = _relative_position(samples[0])
    return max(math.dist(initial, _relative_position(sample)) for sample in samples)


def _relative_orientation_drift(samples: tuple[CarrySample, ...]) -> float:
    if not samples:
        return 0.0
    initial = _relative_orientation(samples[0])
    return max(_quaternion_distance(initial, _relative_orientation(sample)) for sample in samples)


def evaluate_micro_lift(
    samples: tuple[CarrySample, ...],
    contact_policy: ApprovedContactPolicy,
    carry_policy: CarryPolicy,
    expected_session_id: str,
    expected_reset_epoch: int,
    action_boundary_sequence: int,
    now_monotonic_s: float,
) -> CarryOutcome:
    """Prove that bounded TCP motion causally lifts the physically held cup."""

    eligible = _carry_eligible(samples, action_boundary_sequence)
    common = _carry_common_failure(
        eligible,
        contact_policy,
        carry_policy,
        expected_session_id,
        expected_reset_epoch,
        now_monotonic_s,
    )
    micro = carry_policy.micro_lift
    enough = len(eligible) >= contact_policy.evaluation.minimum_consecutive_samples
    cup_lift = (
        eligible[-1].cup_pose_xyz_xyzw[2] - eligible[0].cup_pose_xyz_xyzw[2] if enough else 0.0
    )
    maximum_cup_lift = (
        max(sample.cup_pose_xyz_xyzw[2] - eligible[0].cup_pose_xyz_xyzw[2] for sample in eligible)
        if enough
        else 0.0
    )
    tcp_lift = (
        eligible[-1].tcp_pose_xyz_xyzw[2] - eligible[0].tcp_pose_xyz_xyzw[2] if enough else 0.0
    )
    lateral_drift = (
        math.dist(eligible[0].cup_pose_xyz_xyzw[:2], eligible[-1].cup_pose_xyz_xyzw[:2])
        if enough
        else 0.0
    )
    relative_drift = _relative_position_drift(eligible)
    duration = eligible[-1].simulation_time_s - eligible[0].simulation_time_s if enough else 0.0
    metrics = MappingProxyType(
        {
            "cup_lift_m": cup_lift,
            "maximum_cup_lift_m": maximum_cup_lift,
            "tcp_lift_m": tcp_lift,
            "lateral_drift_m": lateral_drift,
            "maximum_relative_position_drift_m": relative_drift,
            "duration_s": duration,
        }
    )

    code = common
    if code is None and not enough:
        code = "CARRY_STALE_EVIDENCE"
    elif code is None and maximum_cup_lift > micro.maximum_cup_lift_m:
        code = "MICRO_LIFT_CUP_TELEPORT"
    elif code is None and cup_lift < micro.minimum_cup_lift_m:
        code = "MICRO_LIFT_CUP_NOT_LIFTED"
    elif code is None and tcp_lift < micro.minimum_tcp_lift_m:
        code = "MICRO_LIFT_TCP_NOT_LIFTED"
    elif code is None and lateral_drift > micro.maximum_lateral_drift_m:
        code = "MICRO_LIFT_LATERAL_DRIFT"
    elif code is None and relative_drift > micro.maximum_relative_position_drift_m:
        code = "MICRO_LIFT_RELATIVE_DRIFT"
    elif code is None and any(sample.table_contact for sample in eligible[1:]):
        code = "MICRO_LIFT_TABLE_SUPPORTED"
    elif (
        code is None
        and eligible[-1].table_clearance_m < carry_policy.transport.minimum_table_clearance_m
    ):
        code = "MICRO_LIFT_TABLE_CLEARANCE"
    elif code is None and duration < micro.minimum_stable_duration_s:
        code = "MICRO_LIFT_DWELL_TOO_SHORT"

    return CarryOutcome(code is None, code, len(eligible), metrics, eligible)


def evaluate_transport(
    samples: tuple[CarrySample, ...],
    contact_policy: ApprovedContactPolicy,
    carry_policy: CarryPolicy,
    expected_session_id: str,
    expected_reset_epoch: int,
    action_boundary_sequence: int,
    now_monotonic_s: float,
) -> CarryOutcome:
    """Prove continuous physical carry across every named transport segment."""

    eligible = _carry_eligible(samples, action_boundary_sequence)
    common = _carry_common_failure(
        eligible,
        contact_policy,
        carry_policy,
        expected_session_id,
        expected_reset_epoch,
        now_monotonic_s,
    )
    position_drift = _relative_position_drift(eligible)
    orientation_drift = _relative_orientation_drift(eligible)
    metrics = MappingProxyType(
        {
            "maximum_relative_position_drift_m": position_drift,
            "maximum_relative_orientation_drift_rad": orientation_drift,
            "minimum_table_clearance_m": min(
                (sample.table_clearance_m for sample in eligible), default=0.0
            ),
        }
    )
    segment_order = ("LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE")
    required_segments = set(segment_order)
    segment_counts = {
        segment: sum(sample.segment == segment for sample in eligible)
        for segment in required_segments
    }

    observed_segment_order = tuple(
        segment
        for index, segment in enumerate(sample.segment for sample in eligible)
        if index == 0 or segment != eligible[index - 1].segment
    )
    code = common
    if code is None and (
        any(sample.segment not in required_segments for sample in eligible)
        or any(count < 2 for count in segment_counts.values())
        or observed_segment_order != segment_order
    ):
        code = "TRANSPORT_MISSING_SEGMENT"
    elif code is None and any(sample.table_contact for sample in eligible):
        code = "TRANSPORT_TABLE_RECONTACT"
    elif code is None and any(
        sample.table_clearance_m < carry_policy.transport.minimum_table_clearance_m
        for sample in eligible
    ):
        code = "TRANSPORT_CLEARANCE"
    elif code is None and position_drift > carry_policy.transport.maximum_relative_position_drift_m:
        code = "TRANSPORT_POSITION_DRIFT"
    elif (
        code is None
        and orientation_drift > carry_policy.transport.maximum_relative_orientation_drift_rad
    ):
        code = "TRANSPORT_ORIENTATION_DRIFT"

    return CarryOutcome(code is None, code, len(eligible), metrics, eligible)
