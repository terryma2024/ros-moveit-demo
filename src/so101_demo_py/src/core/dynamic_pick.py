"""ROS-free dynamic cup-pick target resolution."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..ports.evidence import PoseEvidence
from .domain import State
from .task_geometry import Pose7


class DynamicPickError(ValueError):
    """A dynamic pose or template cannot produce safe motion targets."""


DYNAMIC_REACHABILITY_STATES = (
    State.MOVE_ABOVE_OBJECT,
    State.DESCEND,
    State.MICRO_LIFT,
    State.LIFT,
    State.MOVE_ABOVE_PLACE,
    State.DESCEND_TO_PLACE,
    State.RETREAT,
)


DYNAMIC_MOTION_STATES = frozenset(
    {
        *DYNAMIC_REACHABILITY_STATES,
        State.RECOVER_LIFT_TO_SAFE_HEIGHT,
        State.RECOVER_MOVE_ABOVE_PICK,
        State.RECOVER_DESCEND_TO_PICK,
        State.RECOVER_RETREAT,
    }
)


def _finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value):
        raise DynamicPickError(f"DYNAMIC_PICK_INVALID: {name} must be finite")


def _positive(name: str, value: float) -> None:
    _finite(name, value)
    if value <= 0.0:
        raise DynamicPickError(f"DYNAMIC_PICK_INVALID: {name} must be positive")


def _normalize_quaternion(value: tuple[float, float, float, float]) -> tuple[float, ...]:
    if any(not math.isfinite(component) for component in value):
        raise DynamicPickError("DYNAMIC_PICK_INVALID: quaternion must be finite")
    norm = math.sqrt(sum(component * component for component in value))
    if norm <= 1e-12:
        raise DynamicPickError("DYNAMIC_PICK_INVALID: quaternion must be non-zero")
    return tuple(component / norm for component in value)


def _multiply_quaternion(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def _rotate_vector(
    vector: tuple[float, float, float], quaternion: tuple[float, float, float, float]
) -> tuple[float, float, float]:
    qx, qy, qz, qw = quaternion
    vx, vy, vz = vector
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    return (
        vx + qw * tx + qy * tz - qz * ty,
        vy + qw * ty + qz * tx - qx * tz,
        vz + qw * tz + qx * ty - qy * tx,
    )


def normalized_pose(value: Pose7) -> Pose7:
    values = value.values
    if any(not math.isfinite(component) for component in values):
        raise DynamicPickError("DYNAMIC_PICK_INVALID: pose must be finite")
    quaternion = _normalize_quaternion(values[3:])
    return Pose7((*values[:3], *quaternion))  # type: ignore[arg-type]


def compose_pose(parent: Pose7, child: Pose7) -> Pose7:
    """Return ``T_world_parent * T_parent_child`` with normalized rotation."""

    parent = normalized_pose(parent)
    child = normalized_pose(child)
    rotated = _rotate_vector(child.values[:3], parent.values[3:])
    position = tuple(parent.values[index] + rotated[index] for index in range(3))
    orientation = _normalize_quaternion(
        _multiply_quaternion(parent.values[3:], child.values[3:])
    )
    return Pose7((*position, *orientation))  # type: ignore[arg-type]


def inverse_pose(value: Pose7) -> Pose7:
    """Return the rigid-transform inverse of a normalized pose."""

    value = normalized_pose(value)
    x, y, z, w = value.values[3:]
    inverse_orientation = (-x, -y, -z, w)
    inverse_translation = _rotate_vector(
        tuple(-component for component in value.values[:3]),
        inverse_orientation,
    )
    return Pose7((*inverse_translation, *inverse_orientation))  # type: ignore[arg-type]


def _offset_world_z(value: Pose7, clearance_m: float) -> Pose7:
    values = value.values
    return Pose7((values[0], values[1], values[2] + clearance_m, *values[3:]))


@dataclass(frozen=True, slots=True)
class CupPoseSample:
    frame_id: str
    source_stamp_ns: int
    received_monotonic_s: float
    pose_world: Pose7

    def __post_init__(self) -> None:
        if self.frame_id != "world":
            raise DynamicPickError("CUP_POSE_TF_UNAVAILABLE: frame_id must be world")
        if isinstance(self.source_stamp_ns, bool) or self.source_stamp_ns <= 0:
            raise DynamicPickError("CUP_POSE_STALE: source stamp must be positive")
        _finite("received_monotonic_s", self.received_monotonic_s)
        if self.received_monotonic_s < 0.0:
            raise DynamicPickError(
                "DYNAMIC_PICK_INVALID: received_monotonic_s must be non-negative"
            )
        object.__setattr__(self, "pose_world", normalized_pose(self.pose_world))


@dataclass(frozen=True, slots=True)
class DynamicPickTemplate:
    policy_id: str
    planning_frame: str
    object_id: str
    planning_group: str
    arm_joint_names: tuple[str, ...]
    tcp_link: str
    cup_to_tcp_grasp: Pose7
    pregrasp_world_z_clearance_m: float
    micro_lift_world_z_clearance_m: float
    lift_world_z_clearance_m: float
    place_tcp_world: Pose7
    place_approach_world_z_clearance_m: float
    retreat_world_z_clearance_m: float
    workspace_bounds_m: tuple[float, float, float, float, float, float]
    maximum_source_age_s: float
    maximum_future_skew_s: float
    scene_position_tolerance_m: float
    scene_orientation_tolerance_rad: float
    position_tolerance_m: float
    orientation_tolerance_rad: tuple[float, float, float]
    planning_timeout_s: float
    velocity_scaling: float
    acceleration_scaling: float

    def __post_init__(self) -> None:
        for name in ("policy_id", "planning_frame", "object_id", "planning_group", "tcp_link"):
            if not getattr(self, name):
                raise DynamicPickError(f"DYNAMIC_PICK_INVALID: {name} must be non-empty")
        if self.planning_frame != "world" or self.object_id != "plastic_cup":
            raise DynamicPickError(
                "DYNAMIC_PICK_INVALID: V2.1 requires world and canonical plastic_cup"
            )
        if not self.arm_joint_names or any(not name for name in self.arm_joint_names):
            raise DynamicPickError("DYNAMIC_PICK_INVALID: arm_joint_names must be complete")
        if len(set(self.arm_joint_names)) != len(self.arm_joint_names):
            raise DynamicPickError("DYNAMIC_PICK_INVALID: arm_joint_names must be unique")
        positive = (
            "pregrasp_world_z_clearance_m",
            "micro_lift_world_z_clearance_m",
            "lift_world_z_clearance_m",
            "place_approach_world_z_clearance_m",
            "retreat_world_z_clearance_m",
            "maximum_source_age_s",
            "maximum_future_skew_s",
            "scene_position_tolerance_m",
            "scene_orientation_tolerance_rad",
            "position_tolerance_m",
            "planning_timeout_s",
            "velocity_scaling",
            "acceleration_scaling",
        )
        for name in positive:
            _positive(name, getattr(self, name))
        if self.velocity_scaling > 1.0 or self.acceleration_scaling > 1.0:
            raise DynamicPickError("DYNAMIC_PICK_INVALID: scaling must not exceed 1.0")
        if len(self.orientation_tolerance_rad) != 3:
            raise DynamicPickError(
                "DYNAMIC_PICK_INVALID: orientation_tolerance_rad must have three values"
            )
        for value in self.orientation_tolerance_rad:
            _positive("orientation_tolerance_rad", value)
        if len(self.workspace_bounds_m) != 6 or any(
            lower >= upper
            for lower, upper in zip(
                self.workspace_bounds_m[:3], self.workspace_bounds_m[3:], strict=True
            )
        ):
            raise DynamicPickError("DYNAMIC_PICK_INVALID: workspace bounds must be ordered")
        object.__setattr__(self, "cup_to_tcp_grasp", normalized_pose(self.cup_to_tcp_grasp))
        object.__setattr__(self, "place_tcp_world", normalized_pose(self.place_tcp_world))


@dataclass(frozen=True, slots=True)
class ResolvedMotionTargets:
    input_pose: CupPoseSample
    template: DynamicPickTemplate
    targets: Mapping[State, PoseEvidence]

    def __post_init__(self) -> None:
        if set(self.targets) != DYNAMIC_MOTION_STATES:
            raise DynamicPickError("DYNAMIC_PICK_INVALID: motion target coverage is incomplete")
        object.__setattr__(self, "targets", MappingProxyType(dict(self.targets)))

    def for_state(self, state: State) -> PoseEvidence:
        try:
            return self.targets[state]
        except KeyError as error:
            raise DynamicPickError(f"PLAN_ONLY_STATE_UNSUPPORTED: {state.value}") from error

    def target_for(self, state: State) -> PoseEvidence:
        return self.for_state(state)


def _evidence(value: Pose7) -> PoseEvidence:
    value = normalized_pose(value)
    return PoseEvidence(value.values[:3], value.values[3:])


def _check_workspace(value: Pose7, bounds: tuple[float, ...]) -> None:
    if any(
        coordinate < lower or coordinate > upper
        for coordinate, lower, upper in zip(value.values[:3], bounds[:3], bounds[3:], strict=True)
    ):
        raise DynamicPickError("CUP_POSE_OUT_OF_WORKSPACE: resolved TCP target is outside bounds")


def resolve_motion_targets(
    sample: CupPoseSample, template: DynamicPickTemplate
) -> ResolvedMotionTargets:
    grasp = compose_pose(sample.pose_world, template.cup_to_tcp_grasp)
    pregrasp = _offset_world_z(grasp, template.pregrasp_world_z_clearance_m)
    micro_lift = _offset_world_z(grasp, template.micro_lift_world_z_clearance_m)
    lift = _offset_world_z(grasp, template.lift_world_z_clearance_m)
    place = template.place_tcp_world
    above_place = _offset_world_z(place, template.place_approach_world_z_clearance_m)
    retreat = _offset_world_z(place, template.retreat_world_z_clearance_m)
    for value in (grasp, pregrasp, micro_lift, lift, place, above_place, retreat):
        _check_workspace(value, template.workspace_bounds_m)
    targets = {
        State.MOVE_ABOVE_OBJECT: _evidence(pregrasp),
        State.DESCEND: _evidence(grasp),
        State.MICRO_LIFT: _evidence(micro_lift),
        State.LIFT: _evidence(lift),
        State.MOVE_ABOVE_PLACE: _evidence(above_place),
        State.DESCEND_TO_PLACE: _evidence(place),
        State.RETREAT: _evidence(retreat),
        State.RECOVER_LIFT_TO_SAFE_HEIGHT: _evidence(lift),
        State.RECOVER_MOVE_ABOVE_PICK: _evidence(pregrasp),
        State.RECOVER_DESCEND_TO_PICK: _evidence(grasp),
        State.RECOVER_RETREAT: _evidence(retreat),
    }
    return ResolvedMotionTargets(sample, template, targets)
