"""Strict schema-v2 loader for perception-driven pick templates."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .dynamic_pick import DynamicPickTemplate
from .task_geometry import Pose7


class DynamicPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedDynamicPolicy:
    template: DynamicPickTemplate
    path: Path
    sha256: str
    qualification_status: str
    backend: str
    execution_allowed: bool


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise DynamicPolicyError(f"DYNAMIC_POLICY_INVALID: {name} must be a mapping")
    return value


def _exact(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise DynamicPolicyError(
            f"DYNAMIC_POLICY_INVALID: {name} fields differ; "
            f"missing={sorted(expected - actual)} unknown={sorted(actual - expected)}"
        )


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DynamicPolicyError(f"DYNAMIC_POLICY_INVALID: {name} must be non-empty")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DynamicPolicyError(f"DYNAMIC_POLICY_INVALID: {name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise DynamicPolicyError(f"DYNAMIC_POLICY_INVALID: {name} must be finite")
    return result


def _numbers(value: object, length: int, name: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise DynamicPolicyError(
            f"DYNAMIC_POLICY_INVALID: {name} must contain {length} numbers"
        )
    return tuple(_number(item, f"{name}[{index}]") for index, item in enumerate(value))


def load_dynamic_pick_template(
    path: Path,
    *,
    expected_backend: str | None = None,
    expected_execution_allowed: bool | None = None,
) -> DynamicPickTemplate:
    document = _mapping(yaml.safe_load(path.read_bytes()), "dynamic policy")
    _exact(
        document,
        {
            "schema_version",
            "policy_id",
            "backend",
            "execution_allowed",
            "planning",
            "object",
            "pick",
            "place",
            "safety",
        },
        "dynamic policy",
    )
    if document["schema_version"] != 2:
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: schema_version must be 2")
    backend = _string(document["backend"], "backend")
    if backend not in {"gazebo", "mujoco"}:
        raise DynamicPolicyError("DYNAMIC_BACKEND_UNSUPPORTED")
    if expected_backend is not None and backend != expected_backend:
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: backend identity mismatch")
    execution_allowed = document["execution_allowed"]
    if not isinstance(execution_allowed, bool):
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: execution_allowed must be boolean")
    if (
        expected_execution_allowed is not None
        and execution_allowed is not expected_execution_allowed
    ):
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: execution identity mismatch")

    planning = _mapping(document["planning"], "planning")
    _exact(
        planning,
        {
            "frame",
            "group",
            "arm_joint_names",
            "tcp_link",
            "planning_timeout_s",
            "position_tolerance_m",
            "orientation_tolerance_rad",
            "velocity_scaling",
            "acceleration_scaling",
        },
        "planning",
    )
    object_config = _mapping(document["object"], "object")
    _exact(object_config, {"object_id", "cup_to_tcp_grasp_xyz_xyzw"}, "object")
    pick = _mapping(document["pick"], "pick")
    _exact(
        pick,
        {
            "pregrasp_world_z_clearance_m",
            "micro_lift_world_z_clearance_m",
            "lift_world_z_clearance_m",
        },
        "pick",
    )
    place = _mapping(document["place"], "place")
    _exact(
        place,
        {
            "tcp_world_xyz_xyzw",
            "approach_world_z_clearance_m",
            "retreat_world_z_clearance_m",
        },
        "place",
    )
    safety = _mapping(document["safety"], "safety")
    _exact(
        safety,
        {
            "workspace_bounds_m",
            "maximum_source_age_s",
            "maximum_future_skew_s",
            "scene_position_tolerance_m",
            "scene_orientation_tolerance_rad",
        },
        "safety",
    )
    return DynamicPickTemplate(
        policy_id=_string(document["policy_id"], "policy_id"),
        planning_frame=_string(planning["frame"], "planning.frame"),
        object_id=_string(object_config["object_id"], "object.object_id"),
        planning_group=_string(planning["group"], "planning.group"),
        arm_joint_names=tuple(
            _string(value, f"planning.arm_joint_names[{index}]")
            for index, value in enumerate(planning["arm_joint_names"])
        )
        if isinstance(planning["arm_joint_names"], list)
        else (),
        tcp_link=_string(planning["tcp_link"], "planning.tcp_link"),
        cup_to_tcp_grasp=Pose7(
            _numbers(object_config["cup_to_tcp_grasp_xyz_xyzw"], 7, "cup_to_tcp_grasp")
        ),
        pregrasp_world_z_clearance_m=_number(
            pick["pregrasp_world_z_clearance_m"], "pick.pregrasp"
        ),
        micro_lift_world_z_clearance_m=_number(
            pick["micro_lift_world_z_clearance_m"], "pick.micro_lift"
        ),
        lift_world_z_clearance_m=_number(pick["lift_world_z_clearance_m"], "pick.lift"),
        place_tcp_world=Pose7(_numbers(place["tcp_world_xyz_xyzw"], 7, "place.tcp")),
        place_approach_world_z_clearance_m=_number(
            place["approach_world_z_clearance_m"], "place.approach"
        ),
        retreat_world_z_clearance_m=_number(
            place["retreat_world_z_clearance_m"], "place.retreat"
        ),
        workspace_bounds_m=_numbers(safety["workspace_bounds_m"], 6, "workspace_bounds"),
        maximum_source_age_s=_number(safety["maximum_source_age_s"], "maximum_source_age_s"),
        maximum_future_skew_s=_number(
            safety["maximum_future_skew_s"], "maximum_future_skew_s"
        ),
        scene_position_tolerance_m=_number(
            safety["scene_position_tolerance_m"], "scene_position_tolerance_m"
        ),
        scene_orientation_tolerance_rad=_number(
            safety["scene_orientation_tolerance_rad"], "scene_orientation_tolerance_rad"
        ),
        position_tolerance_m=_number(
            planning["position_tolerance_m"], "planning.position_tolerance_m"
        ),
        orientation_tolerance_rad=_numbers(
            planning["orientation_tolerance_rad"], 3, "planning.orientation_tolerance_rad"
        ),
        planning_timeout_s=_number(planning["planning_timeout_s"], "planning.timeout"),
        velocity_scaling=_number(planning["velocity_scaling"], "planning.velocity_scaling"),
        acceleration_scaling=_number(
            planning["acceleration_scaling"], "planning.acceleration_scaling"
        ),
    )


def load_dynamic_policy_variant(
    share_dir: Path,
    *,
    backend: str = "gazebo",
    policy_id: str = "dynamic_cup_pick",
    version: str = "v1",
) -> LoadedDynamicPolicy:
    if backend not in {"gazebo", "mujoco"}:
        raise DynamicPolicyError("DYNAMIC_BACKEND_UNSUPPORTED")
    root = Path(share_dir) / "config" / "policies" / policy_id / version
    manifest = _mapping(yaml.safe_load((root / "manifest.yaml").read_bytes()), "manifest")
    _exact(
        manifest,
        {
            "schema_version",
            "policy_id",
            "version",
            "supported_backends",
            "execution_allowed_backends",
            "variants",
        },
        "manifest",
    )
    if (
        manifest["schema_version"] != 2
        or manifest["policy_id"] != policy_id
        or manifest["version"] != version
        or manifest["supported_backends"] != ["gazebo", "mujoco"]
        or manifest["execution_allowed_backends"] != ["mujoco"]
    ):
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: manifest identity mismatch")
    variants = _mapping(manifest["variants"], "variants")
    _exact(variants, {"gazebo", "mujoco"}, "variants")
    entry = _mapping(variants[backend], f"{backend} variant")
    _exact(entry, {"filename", "sha256", "qualification_status"}, f"{backend} variant")
    filename = _string(entry["filename"], "variant filename")
    if Path(filename).name != filename:
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: variant filename escapes root")
    path = root / filename
    raw = path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if entry["sha256"] != actual_sha:
        raise DynamicPolicyError("DYNAMIC_POLICY_INVALID: variant hash mismatch")
    execution_allowed = backend in manifest["execution_allowed_backends"]
    return LoadedDynamicPolicy(
        load_dynamic_pick_template(
            path,
            expected_backend=backend,
            expected_execution_allowed=execution_allowed,
        ),
        path,
        actual_sha,
        _string(entry["qualification_status"], "qualification_status"),
        backend,
        execution_allowed,
    )
