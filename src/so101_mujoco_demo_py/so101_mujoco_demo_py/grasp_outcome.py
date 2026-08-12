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
