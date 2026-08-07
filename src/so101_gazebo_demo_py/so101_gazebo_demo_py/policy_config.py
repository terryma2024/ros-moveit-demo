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
class ValidationPolicyConfig:
    schema_version: int
    policy_id: str
    object_id: str
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
        preopen_q6=_number(actions.get("preopen_q6"), "gripper_actions.preopen_q6"),
        grasp_close_q6=_number(actions.get("grasp_close_q6"), "gripper_actions.grasp_close_q6"),
        release_q6=_number(actions.get("release_q6"), "gripper_actions.release_q6"),
        states=MappingProxyType(states),
        data=MappingProxyType(document),
    )


def _validation(document: dict[str, Any]) -> ValidationPolicyConfig:
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
        states=MappingProxyType(states),
        data=MappingProxyType(document),
    )


def load_policy_bundle(object_path: Path, motion_path: Path, validation_path: Path) -> PolicyBundle:
    documents = (_load(Path(object_path)), _load(Path(motion_path)), _load(Path(validation_path)))
    task_object, motion, validation = _task_object(documents[0]), _motion(documents[1]), _validation(documents[2])
    if not (task_object.schema_version == motion.schema_version == validation.schema_version == 1):
        raise ConfigurationError("CONFIGURATION_SCHEMA_VERSION", "all policy schema versions must be 1")
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
