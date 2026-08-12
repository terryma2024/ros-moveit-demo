"""Strict, ROS-free loading of the complete SO-101 task policy."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from so101_mujoco_demo_py.contact_policy import (
    ApprovedContactPolicy,
    ContactPolicyFingerprint,
    load_approved_contact_policy,
)
from so101_mujoco_demo_py.physical_outcome import (
    PhysicalOutcomePolicy,
    PlanningShadowPolicy,
)

_STATE_NAMES = frozenset(
    {
        "MOVE_ABOVE_OBJECT",
        "DESCEND",
        "LIFT",
        "MOVE_ABOVE_PLACE",
        "DESCEND_TO_PLACE",
        "RETREAT",
        "RECOVER_LIFT_TO_SAFE_HEIGHT",
        "RECOVER_MOVE_ABOVE_PICK",
        "RECOVER_DESCEND_TO_PICK",
        "RECOVER_RETREAT",
    }
)

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "object_id",
        "planning_group",
        "tcp_link",
        "gripper_joint",
        "all_joints",
        "arm_joints",
        "safety_limits",
        "approach_outside_clearance_m",
        "grasp_tcp_translation_offset_m",
        "grasp_tcp_world_x_rotation_rad",
        "gripper_actions",
        "place_alignment",
        "release_retreat",
        "contact_calibration_approach",
        "staged_approach_execution",
        "physical_outcome",
        "states",
    }
)

_GRIPPER_KEYS = frozenset({"preopen_q6", "grasp_close_q6", "seating_preload_rad", "release_q6"})
_STATE_KEYS = frozenset(
    {
        "logical_start",
        "waypoints",
        "require_waypoint_ladder",
        "require_axial_path_validation",
        "gripper_q6",
        "velocity_scaling",
        "acceleration_scaling",
    }
)
_OUTCOME_KEYS = frozenset(
    {
        "intended_support_collision",
        "minimum_support_signed_distance_m",
        "final_target_region",
        "support_height_range_m",
        "max_upright_tilt_rad",
        "max_linear_speed_m_s",
        "max_angular_speed_rad_s",
        "consecutive_samples",
        "minimum_stable_duration_s",
        "sample_interval_s",
        "settle_timeout_s",
        "max_observation_age_s",
        "max_telemetry_samples",
        "catastrophic_workspace_bounds_m",
        "max_relative_position_drift_m",
        "max_relative_orientation_drift_rad",
        "planning_shadow",
    }
)


@dataclass(frozen=True, slots=True)
class TaskPolicyFingerprint:
    motion_policy_sha256: str
    contact_policy_sha256: str | None


@dataclass(frozen=True, slots=True)
class GripperActions:
    preopen_q6: float
    grasp_close_q6: float
    seating_preload_rad: float
    release_q6: float


@dataclass(frozen=True, slots=True)
class MotionStatePolicy:
    logical_start: tuple[float, ...]
    waypoints: tuple[tuple[float, ...], ...]
    require_waypoint_ladder: bool
    require_axial_path_validation: bool
    gripper_q6: float
    velocity_scaling: float
    acceleration_scaling: float


@dataclass(frozen=True, slots=True)
class TaskPolicy:
    policy_id: str
    object_id: str
    planning_group: str
    tcp_link: str
    gripper_joint: str
    all_joints: tuple[str, ...]
    arm_joints: tuple[str, ...]
    gripper: GripperActions
    states: Mapping[str, MotionStatePolicy]
    physical_outcome: PhysicalOutcomePolicy
    maximum_diagnostic_force_n: float
    contact: ApprovedContactPolicy | None
    fingerprint: TaskPolicyFingerprint


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} keys must be strings")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    unknown = sorted(set(value) - expected)
    if unknown:
        raise ValueError(f"unknown {name} keys: {', '.join(unknown)}")
    missing = sorted(expected - set(value))
    if missing:
        raise ValueError(f"missing {name} keys: {', '.join(missing)}")


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


def _positive(value: object, name: str) -> float:
    converted = _finite(value, name)
    if converted <= 0.0:
        raise ValueError(f"{name} must be positive")
    return converted


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _scaling(value: object, name: str) -> float:
    converted = _positive(value, name)
    if converted > 1.0:
        raise ValueError(f"{name} must not exceed 1.0")
    return converted


def _numbers(value: object, size: int, name: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        noun = "five arm joints" if size == 5 else f"{size} numbers"
        raise ValueError(f"{name} must contain {noun}")
    return tuple(_finite(item, f"{name}[{index}]") for index, item in enumerate(value))


def _strings(value: object, size: int, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{name} must contain {size} joint names")
    converted = tuple(_string(item, f"{name}[{index}]") for index, item in enumerate(value))
    if len(set(converted)) != len(converted):
        raise ValueError(f"{name} must contain unique joint names")
    return converted


def _gripper(document: Mapping[str, Any]) -> GripperActions:
    source = _mapping(document.get("gripper_actions"), "gripper_actions")
    _exact_keys(source, _GRIPPER_KEYS, "gripper_actions")
    return GripperActions(
        preopen_q6=_finite(source["preopen_q6"], "gripper_actions.preopen_q6"),
        grasp_close_q6=_finite(source["grasp_close_q6"], "gripper_actions.grasp_close_q6"),
        seating_preload_rad=_positive(
            source["seating_preload_rad"], "gripper_actions.seating_preload_rad"
        ),
        release_q6=_finite(source["release_q6"], "gripper_actions.release_q6"),
    )


def _states(document: Mapping[str, Any]) -> Mapping[str, MotionStatePolicy]:
    source = _mapping(document.get("states"), "states")
    names = set(source)
    if names != _STATE_NAMES:
        missing = ", ".join(sorted(_STATE_NAMES - names)) or "NONE"
        unknown = ", ".join(sorted(names - _STATE_NAMES)) or "NONE"
        raise ValueError(f"states mismatch; missing={missing}; unknown={unknown}")
    converted: dict[str, MotionStatePolicy] = {}
    for name in source:
        state = _mapping(source[name], name)
        _exact_keys(state, _STATE_KEYS, name)
        waypoints_value = state["waypoints"]
        if not isinstance(waypoints_value, (list, tuple)) or not waypoints_value:
            raise ValueError(f"{name}.waypoints must be a non-empty sequence")
        waypoints = tuple(
            _numbers(item, 5, f"{name}.waypoints[{index}]")
            for index, item in enumerate(waypoints_value)
        )
        converted[name] = MotionStatePolicy(
            logical_start=_numbers(state["logical_start"], 5, f"{name}.logical_start"),
            waypoints=waypoints,
            require_waypoint_ladder=_boolean(
                state["require_waypoint_ladder"], f"{name}.require_waypoint_ladder"
            ),
            require_axial_path_validation=_boolean(
                state["require_axial_path_validation"],
                f"{name}.require_axial_path_validation",
            ),
            gripper_q6=_finite(state["gripper_q6"], f"{name}.gripper_q6"),
            velocity_scaling=_scaling(state["velocity_scaling"], f"{name}.velocity_scaling"),
            acceleration_scaling=_scaling(
                state["acceleration_scaling"], f"{name}.acceleration_scaling"
            ),
        )
    return MappingProxyType(converted)


def _ordered_pair(value: object, name: str) -> tuple[float, float]:
    converted = _numbers(value, 2, name)
    if converted[0] > converted[1]:
        raise ValueError(f"{name} must be ordered")
    return converted


def _physical_outcome(document: Mapping[str, Any]) -> PhysicalOutcomePolicy:
    source = _mapping(document.get("physical_outcome"), "physical_outcome")
    _exact_keys(source, _OUTCOME_KEYS, "physical_outcome")

    region = _mapping(source["final_target_region"], "final_target_region")
    _exact_keys(
        region,
        frozenset({"kind", "min_xy_m", "max_xy_m"}),
        "final_target_region",
    )
    if region["kind"] != "axis_aligned_box":
        raise ValueError("final_target_region.kind must be axis_aligned_box")
    minimum_xy = _numbers(region["min_xy_m"], 2, "final_target_region.min_xy_m")
    maximum_xy = _numbers(region["max_xy_m"], 2, "final_target_region.max_xy_m")
    if any(lower > upper for lower, upper in zip(minimum_xy, maximum_xy, strict=True)):
        raise ValueError("final_target_region bounds must be ordered")

    shadow = _mapping(source["planning_shadow"], "planning_shadow")
    _exact_keys(
        shadow,
        frozenset(
            {
                "max_position_divergence_m",
                "max_orientation_divergence_rad",
                "max_pair_age_s",
            }
        ),
        "planning_shadow",
    )
    workspace = _numbers(
        source["catastrophic_workspace_bounds_m"],
        6,
        "catastrophic_workspace_bounds_m",
    )
    if any(lower >= upper for lower, upper in zip(workspace[:3], workspace[3:], strict=True)):
        raise ValueError("catastrophic_workspace_bounds_m must be ordered")

    return PhysicalOutcomePolicy(
        intended_support_collision=_string(
            source["intended_support_collision"], "intended_support_collision"
        ),
        minimum_support_signed_distance_m=_finite(
            source["minimum_support_signed_distance_m"],
            "minimum_support_signed_distance_m",
        ),
        final_target_min_xy_m=minimum_xy,
        final_target_max_xy_m=maximum_xy,
        support_height_range_m=_ordered_pair(
            source["support_height_range_m"], "support_height_range_m"
        ),
        max_upright_tilt_rad=_positive(source["max_upright_tilt_rad"], "max_upright_tilt_rad"),
        max_linear_speed_m_s=_positive(source["max_linear_speed_m_s"], "max_linear_speed_m_s"),
        max_angular_speed_rad_s=_positive(
            source["max_angular_speed_rad_s"], "max_angular_speed_rad_s"
        ),
        consecutive_samples=_positive_integer(source["consecutive_samples"], "consecutive_samples"),
        minimum_stable_duration_s=_positive(
            source["minimum_stable_duration_s"], "minimum_stable_duration_s"
        ),
        sample_interval_s=_positive(source["sample_interval_s"], "sample_interval_s"),
        settle_timeout_s=_positive(source["settle_timeout_s"], "settle_timeout_s"),
        max_observation_age_s=_positive(source["max_observation_age_s"], "max_observation_age_s"),
        max_telemetry_samples=_positive_integer(
            source["max_telemetry_samples"], "max_telemetry_samples"
        ),
        catastrophic_workspace_bounds_m=workspace,
        max_relative_position_drift_m=_positive(
            source["max_relative_position_drift_m"],
            "max_relative_position_drift_m",
        ),
        max_relative_orientation_drift_rad=_positive(
            source["max_relative_orientation_drift_rad"],
            "max_relative_orientation_drift_rad",
        ),
        planning_shadow=PlanningShadowPolicy(
            max_position_divergence_m=_positive(
                shadow["max_position_divergence_m"],
                "planning_shadow.max_position_divergence_m",
            ),
            max_orientation_divergence_rad=_positive(
                shadow["max_orientation_divergence_rad"],
                "planning_shadow.max_orientation_divergence_rad",
            ),
            max_pair_age_s=_positive(shadow["max_pair_age_s"], "planning_shadow.max_pair_age_s"),
        ),
    )


def load_task_policy(
    motion_path: Path,
    contact_path: Path | None = None,
    expected_contact_fingerprint: ContactPolicyFingerprint | None = None,
    *,
    require_approved_contact: bool = False,
) -> TaskPolicy:
    """Load a motion policy from exact bytes and reject untyped additions."""

    raw = motion_path.read_bytes()
    motion_hash = hashlib.sha256(raw).hexdigest()
    document = _mapping(yaml.safe_load(raw), "task policy")
    _exact_keys(document, _ROOT_KEYS, "task policy")
    if document["schema_version"] != 1:
        raise ValueError("task policy schema_version must be 1")

    all_joints = _strings(document["all_joints"], 6, "all_joints")
    arm_joints = _strings(document["arm_joints"], 5, "arm_joints")
    gripper_joint = _string(document["gripper_joint"], "gripper_joint")
    if all_joints != (*arm_joints, gripper_joint):
        raise ValueError("all_joints must contain arm_joints followed by gripper_joint")

    safety = _mapping(document["safety_limits"], "safety_limits")
    _exact_keys(
        safety,
        frozenset({"maximum_diagnostic_force_n"}),
        "safety_limits",
    )

    contact: ApprovedContactPolicy | None = None
    contact_hash: str | None = None
    if contact_path is None:
        if require_approved_contact:
            raise ValueError("approved contact policy is required")
    else:
        if expected_contact_fingerprint is None:
            raise ValueError("expected contact policy fingerprint is required")
        if expected_contact_fingerprint.motion_policy_sha256 != motion_hash:
            raise ValueError("motion policy fingerprint mismatch")
        contact = load_approved_contact_policy(contact_path, expected_contact_fingerprint)
        contact_hash = hashlib.sha256(contact_path.read_bytes()).hexdigest()

    return TaskPolicy(
        policy_id=_string(document["policy_id"], "policy_id"),
        object_id=_string(document["object_id"], "object_id"),
        planning_group=_string(document["planning_group"], "planning_group"),
        tcp_link=_string(document["tcp_link"], "tcp_link"),
        gripper_joint=gripper_joint,
        all_joints=all_joints,
        arm_joints=arm_joints,
        gripper=_gripper(document),
        states=_states(document),
        physical_outcome=_physical_outcome(document),
        maximum_diagnostic_force_n=_positive(
            safety["maximum_diagnostic_force_n"],
            "safety_limits.maximum_diagnostic_force_n",
        ),
        contact=contact,
        fingerprint=TaskPolicyFingerprint(
            motion_policy_sha256=motion_hash,
            contact_policy_sha256=contact_hash,
        ),
    )
