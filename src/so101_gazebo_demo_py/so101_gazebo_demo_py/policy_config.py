"""Strict, ROS-free loading of the three SO-101 policy documents."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from .domain import State


class ConfigurationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class Pose3D:
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TaskObjectConfig:
    schema_version: int
    object_id: str
    spawn_pose: Pose3D
    place_pose: Pose3D
    reset_parking_pose: Pose3D
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class StateMotionConfig:
    logical_start: tuple[float, ...]
    waypoints: tuple[tuple[float, ...], ...]
    require_waypoint_ladder: bool
    require_axial_path_validation: bool
    gripper_q6: float
    velocity_scaling: float
    acceleration_scaling: float


@dataclass(frozen=True, slots=True)
class MotionPolicyConfig:
    schema_version: int
    policy_id: str
    object_id: str
    arm_joints: tuple[str, ...]
    gripper_joint: str
    approach_outside_clearance_m: float
    grasp_tcp_translation_offset_m: tuple[float, float, float]
    preopen_q6: float
    grasp_close_q6: float
    release_q6: float
    states: Mapping[State, StateMotionConfig]
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class StateValidationConfig:
    endpoint_position: tuple[float, float, float]
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PlanningShadowConfig:
    max_position_divergence_m: float
    max_orientation_divergence_rad: float
    max_pair_age_s: float


@dataclass(frozen=True, slots=True)
class PhysicalOutcomeConfig:
    intended_support_collision: str
    minimum_support_contact_depth_m: float
    final_target_min_xy_m: tuple[float, float]
    final_target_max_xy_m: tuple[float, float]
    support_height_range_m: tuple[float, float]
    max_upright_tilt_rad: float
    max_linear_speed_m_s: float
    max_angular_speed_rad_s: float
    consecutive_samples: int
    minimum_stable_duration_s: float
    sample_interval_s: float
    settle_timeout_s: float
    max_observation_age_s: float
    max_telemetry_samples: int
    catastrophic_workspace_bounds_m: tuple[float, ...]
    max_relative_position_drift_m: float
    max_relative_orientation_drift_rad: float
    planning_shadow: PlanningShadowConfig


@dataclass(frozen=True, slots=True)
class ValidationPolicyConfig:
    schema_version: int
    policy_id: str
    object_id: str
    physical_outcome: PhysicalOutcomeConfig
    states: Mapping[State, StateValidationConfig]
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    object: TaskObjectConfig
    motion: MotionPolicyConfig
    validation: ValidationPolicyConfig
    sha256: str
    normalized_documents: tuple[Mapping[str, Any], ...]


def _load(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError("CONFIGURATION_READ_FAILED", f"cannot load {path}: {error}") from error
    if not isinstance(loaded, dict):
        raise ConfigurationError("CONFIGURATION_INVALID_TYPE", f"{path} must contain a mapping")
    _validate_values(loaded, str(path))
    return loaded


def _validate_values(value: Any, location: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ConfigurationError("CONFIGURATION_NONFINITE", f"nonfinite number at {location}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_values(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ConfigurationError("CONFIGURATION_INVALID_KEY", f"non-string key at {location}")
            _validate_values(item, f"{location}.{key}")
        return
    raise ConfigurationError("CONFIGURATION_INVALID_TYPE", f"unsupported value at {location}")


def _mapping(document: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError("CONFIGURATION_MISSING_KEY", f"{key} must be a mapping")
    return value


def _string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError("CONFIGURATION_MISSING_KEY", f"{key} must be a nonempty string")
    return value


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ConfigurationError("CONFIGURATION_INVALID_NUMBER", f"{location} must be a finite number")
    return float(value)


def _vector(value: Any, length: int, location: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ConfigurationError("CONFIGURATION_INVALID_VECTOR", f"{location} must have length {length}")
    return tuple(_number(item, f"{location}[{index}]") for index, item in enumerate(value))


def _exact_keys(document: Mapping[str, Any], expected: set[str], location: str) -> None:
    unknown = set(document) - expected
    missing = expected - set(document)
    if unknown:
        raise ConfigurationError("CONFIGURATION_UNKNOWN_KEY", f"unknown keys at {location}: {sorted(unknown)}")
    if missing:
        raise ConfigurationError("CONFIGURATION_MISSING_KEY", f"missing keys at {location}: {sorted(missing)}")


def _positive(value: Any, location: str) -> float:
    result = _number(value, location)
    if result <= 0.0:
        raise ConfigurationError("CONFIGURATION_INVALID_RANGE", f"{location} must be positive")
    return result


def _positive_integer(value: Any, location: str) -> int:
    result = _number(value, location)
    if result <= 0.0 or not result.is_integer():
        raise ConfigurationError("CONFIGURATION_INVALID_RANGE", f"{location} must be a positive integer")
    return int(result)


def _state(name: str, location: str) -> State:
    try:
        return State(name)
    except ValueError as error:
        raise ConfigurationError("CONFIGURATION_UNKNOWN_STATE", f"unknown state {name} at {location}") from error


def _task_object(document: dict[str, Any]) -> TaskObjectConfig:
    scene = _mapping(document, "scene")
    model = _mapping(document, "model")
    for key in (
        "mass_kg", "height_m", "outer_radius_m", "wall_thickness_m",
        "bottom_thickness_m", "side_count",
    ):
        _number(model.get(key), f"model.{key}")
    return TaskObjectConfig(
        schema_version=int(_number(document.get("schema_version"), "object.schema_version")),
        object_id=_string(document, "object_id"),
        spawn_pose=Pose3D(_vector(scene.get("spawn_pose_xyz_xyzw"), 7, "scene.spawn_pose_xyz_xyzw")),
        place_pose=Pose3D(_vector(scene.get("place_pose_xyz_xyzw"), 7, "scene.place_pose_xyz_xyzw")),
        reset_parking_pose=Pose3D(_vector(scene.get("reset_parking_pose_xyz_xyzw"), 7, "scene.reset_parking_pose_xyz_xyzw")),
        data=MappingProxyType(document),
    )


def _motion(document: dict[str, Any]) -> MotionPolicyConfig:
    joint_names = document.get("arm_joints")
    if joint_names != ["1", "2", "3", "4", "5"]:
        raise ConfigurationError("CONFIGURATION_ARM_JOINTS", "arm_joints must be exactly 1 through 5")
    actions = _mapping(document, "gripper_actions")
    clearance = _positive(
        document.get("approach_outside_clearance_m"),
        "approach_outside_clearance_m",
    )
    grasp_offset = _vector(
        document.get("grasp_tcp_translation_offset_m"),
        3,
        "grasp_tcp_translation_offset_m",
    )
    if sum(value != 0.0 for value in grasp_offset) > 1:
        raise ConfigurationError(
            "CONFIGURATION_GRASP_TCP_TRANSLATION",
            "grasp TCP translation candidate must change only one axis",
        )
    if any(abs(value) > clearance for value in grasp_offset):
        raise ConfigurationError(
            "CONFIGURATION_GRASP_TCP_TRANSLATION",
            "grasp TCP translation candidate exceeds approach clearance",
        )
    states: dict[State, StateMotionConfig] = {}
    for name, raw in _mapping(document, "states").items():
        state = _state(name, "motion.states")
        if not isinstance(raw, dict):
            raise ConfigurationError("CONFIGURATION_INVALID_STATE", f"motion state {name} must be a mapping")
        waypoints = raw.get("waypoints")
        if not isinstance(waypoints, list) or not waypoints:
            raise ConfigurationError("CONFIGURATION_INVALID_WAYPOINTS", f"{name} needs waypoints")
        states[state] = StateMotionConfig(
            logical_start=_vector(raw.get("logical_start"), 5, f"{name}.logical_start"),
            waypoints=tuple(_vector(point, 5, f"{name}.waypoints") for point in waypoints),
            require_waypoint_ladder=bool(raw.get("require_waypoint_ladder")),
            require_axial_path_validation=bool(raw.get("require_axial_path_validation")),
            gripper_q6=_number(raw.get("gripper_q6"), f"{name}.gripper_q6"),
            velocity_scaling=_number(raw.get("velocity_scaling"), f"{name}.velocity_scaling"),
            acceleration_scaling=_number(raw.get("acceleration_scaling"), f"{name}.acceleration_scaling"),
        )
    return MotionPolicyConfig(
        schema_version=int(_number(document.get("schema_version"), "motion.schema_version")),
        policy_id=_string(document, "policy_id"),
        object_id=_string(document, "object_id"),
        arm_joints=tuple(joint_names),
        gripper_joint="6",
        approach_outside_clearance_m=clearance,
        grasp_tcp_translation_offset_m=grasp_offset,
        preopen_q6=_number(actions.get("preopen_q6"), "gripper_actions.preopen_q6"),
        grasp_close_q6=_number(actions.get("grasp_close_q6"), "gripper_actions.grasp_close_q6"),
        release_q6=_number(actions.get("release_q6"), "gripper_actions.release_q6"),
        states=MappingProxyType(states),
        data=MappingProxyType(document),
    )


def _validation(document: dict[str, Any]) -> ValidationPolicyConfig:
    raw_outcome = _mapping(document, "physical_outcome")
    _exact_keys(raw_outcome, {
        "intended_support_collision", "minimum_support_contact_depth_m", "final_target_region",
        "support_height_range_m", "max_upright_tilt_rad", "max_linear_speed_m_s",
        "max_angular_speed_rad_s", "consecutive_samples", "minimum_stable_duration_s",
        "sample_interval_s", "settle_timeout_s", "max_observation_age_s",
        "max_telemetry_samples", "catastrophic_loss", "planning_shadow",
    }, "physical_outcome")
    region = _mapping(raw_outcome, "final_target_region")
    _exact_keys(region, {"kind", "min_xy_m", "max_xy_m"}, "physical_outcome.final_target_region")
    if region.get("kind") != "axis_aligned_box":
        raise ConfigurationError("CONFIGURATION_INVALID_VALUE", "final target region must be axis_aligned_box")
    minimum_xy = _vector(region.get("min_xy_m"), 2, "physical_outcome.final_target_region.min_xy_m")
    maximum_xy = _vector(region.get("max_xy_m"), 2, "physical_outcome.final_target_region.max_xy_m")
    height = _vector(raw_outcome.get("support_height_range_m"), 2, "physical_outcome.support_height_range_m")
    if any(low >= high for low, high in zip(minimum_xy, maximum_xy)) or height[0] >= height[1]:
        raise ConfigurationError("CONFIGURATION_INVALID_RANGE", "physical outcome ranges must increase")
    catastrophic = _mapping(raw_outcome, "catastrophic_loss")
    _exact_keys(catastrophic, {
        "workspace_bounds_m", "max_relative_position_drift_m",
        "max_relative_orientation_drift_rad",
    }, "physical_outcome.catastrophic_loss")
    shadow = _mapping(raw_outcome, "planning_shadow")
    _exact_keys(shadow, {
        "max_position_divergence_m", "max_orientation_divergence_rad", "max_pair_age_s",
    }, "physical_outcome.planning_shadow")
    interval = _positive(raw_outcome.get("sample_interval_s"), "physical_outcome.sample_interval_s")
    duration = _positive(raw_outcome.get("minimum_stable_duration_s"), "physical_outcome.minimum_stable_duration_s")
    timeout = _positive(raw_outcome.get("settle_timeout_s"), "physical_outcome.settle_timeout_s")
    count = _positive_integer(raw_outcome.get("consecutive_samples"), "physical_outcome.consecutive_samples")
    if timeout < duration or timeout < interval * (count - 1):
        raise ConfigurationError("CONFIGURATION_INVALID_TIMING", "settle timeout cannot satisfy stable window")
    outcome = PhysicalOutcomeConfig(
        intended_support_collision=_string(raw_outcome, "intended_support_collision"),
        minimum_support_contact_depth_m=_number(raw_outcome.get("minimum_support_contact_depth_m"), "physical_outcome.minimum_support_contact_depth_m"),
        final_target_min_xy_m=(minimum_xy[0], minimum_xy[1]),
        final_target_max_xy_m=(maximum_xy[0], maximum_xy[1]),
        support_height_range_m=(height[0], height[1]),
        max_upright_tilt_rad=_positive(raw_outcome.get("max_upright_tilt_rad"), "physical_outcome.max_upright_tilt_rad"),
        max_linear_speed_m_s=_positive(raw_outcome.get("max_linear_speed_m_s"), "physical_outcome.max_linear_speed_m_s"),
        max_angular_speed_rad_s=_positive(raw_outcome.get("max_angular_speed_rad_s"), "physical_outcome.max_angular_speed_rad_s"),
        consecutive_samples=count,
        minimum_stable_duration_s=duration,
        sample_interval_s=interval,
        settle_timeout_s=timeout,
        max_observation_age_s=_positive(raw_outcome.get("max_observation_age_s"), "physical_outcome.max_observation_age_s"),
        max_telemetry_samples=_positive_integer(raw_outcome.get("max_telemetry_samples"), "physical_outcome.max_telemetry_samples"),
        catastrophic_workspace_bounds_m=_vector(catastrophic.get("workspace_bounds_m"), 6, "physical_outcome.catastrophic_loss.workspace_bounds_m"),
        max_relative_position_drift_m=_positive(catastrophic.get("max_relative_position_drift_m"), "physical_outcome.catastrophic_loss.max_relative_position_drift_m"),
        max_relative_orientation_drift_rad=_positive(catastrophic.get("max_relative_orientation_drift_rad"), "physical_outcome.catastrophic_loss.max_relative_orientation_drift_rad"),
        planning_shadow=PlanningShadowConfig(
            _positive(shadow.get("max_position_divergence_m"), "physical_outcome.planning_shadow.max_position_divergence_m"),
            _positive(shadow.get("max_orientation_divergence_rad"), "physical_outcome.planning_shadow.max_orientation_divergence_rad"),
            _positive(shadow.get("max_pair_age_s"), "physical_outcome.planning_shadow.max_pair_age_s"),
        ),
    )
    states: dict[State, StateValidationConfig] = {}
    for name, raw in _mapping(document, "states").items():
        state = _state(name, "validation.states")
        if not isinstance(raw, dict):
            raise ConfigurationError("CONFIGURATION_INVALID_STATE", f"validation state {name} must be a mapping")
        states[state] = StateValidationConfig(
            endpoint_position=_vector(raw.get("endpoint_position"), 3, f"{name}.endpoint_position"),
            data=MappingProxyType(raw),
        )
    return ValidationPolicyConfig(
        schema_version=int(_number(document.get("schema_version"), "validation.schema_version")),
        policy_id=_string(document, "policy_id"),
        object_id=_string(document, "object_id"),
        physical_outcome=outcome,
        states=MappingProxyType(states),
        data=MappingProxyType(document),
    )


def load_policy_bundle(object_path: Path, motion_path: Path, validation_path: Path) -> PolicyBundle:
    documents = (_load(Path(object_path)), _load(Path(motion_path)), _load(Path(validation_path)))
    task_object, motion, validation = _task_object(documents[0]), _motion(documents[1]), _validation(documents[2])
    if task_object.schema_version != 1 or motion.schema_version != 1 or validation.schema_version != 2:
        raise ConfigurationError(
            "CONFIGURATION_SCHEMA_VERSION", "object/motion schema must be 1 and validation schema must be 2",
        )
    if task_object.object_id != motion.object_id or motion.object_id != validation.object_id:
        raise ConfigurationError("CONFIGURATION_OBJECT_ID_MISMATCH", "policy object_id values differ")
    if motion.policy_id != validation.policy_id:
        raise ConfigurationError("CONFIGURATION_POLICY_ID_MISMATCH", "policy_id values differ")
    canonical = json.dumps(documents, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return PolicyBundle(
        object=task_object,
        motion=motion,
        validation=validation,
        sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        normalized_documents=tuple(MappingProxyType(document) for document in documents),
    )
