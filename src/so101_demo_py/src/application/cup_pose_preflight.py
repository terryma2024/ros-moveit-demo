"""Pure three-source cup-pose consistency checks."""

from __future__ import annotations

import math

from ..core.dynamic_pick import CupPoseSample, DynamicPickTemplate
from ..ports.cup_scene_observation import CupSceneObservation
from ..ports.evidence import PoseEvidence


class CupPosePreflightError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_mujoco_scene_identity(
    observation: CupSceneObservation,
    *,
    expected_session_id: str,
    expected_reset_epoch: int,
) -> None:
    missing = tuple(
        name
        for name in ("simulation_session_id", "reset_epoch", "paused")
        if getattr(observation, name) is None
    )
    if missing:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_IDENTITY_MISSING",
            f"MuJoCo scene identity fields are missing: {', '.join(missing)}",
        )
    if observation.simulation_session_id != expected_session_id:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_SESSION_MISMATCH",
            "MuJoCo scene session mismatch: "
            f"expected {expected_session_id}, got {observation.simulation_session_id}",
        )
    if observation.reset_epoch != expected_reset_epoch:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_RESET_EPOCH_MISMATCH",
            "MuJoCo scene reset epoch mismatch: "
            f"expected {expected_reset_epoch}, got {observation.reset_epoch}",
        )
    if observation.paused:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_PAUSED",
            "MuJoCo scene evidence reports paused physics",
        )


def _position_distance(left: PoseEvidence, right: PoseEvidence) -> float:
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(left.position_m, right.position_m, strict=True))
    )


def _orientation_distance(left: PoseEvidence, right: PoseEvidence) -> float:
    left_norm = math.sqrt(sum(value * value for value in left.orientation_xyzw))
    right_norm = math.sqrt(sum(value * value for value in right.orientation_xyzw))
    dot = abs(
        sum(a * b for a, b in zip(left.orientation_xyzw, right.orientation_xyzw, strict=True))
        / (left_norm * right_norm)
    )
    return 2.0 * math.acos(min(1.0, max(-1.0, dot)))


def validate_cup_scene(
    sample: CupPoseSample,
    observation: CupSceneObservation,
    template: DynamicPickTemplate,
    *,
    perception_gate: bool = True,
) -> None:
    """The three-source consistency check. ``perception_gate=False`` (Teacher policy v3) drops every comparison that involves
    the perceived pose against simulator truth (S05): only the MoveIt shadow is checked against the pose it was built from, and
    the perception error is recorded as telemetry instead (`perception_error`)."""
    validate_cup_against_simulator(sample, observation, template, perception_gate=perception_gate)
    topic = PoseEvidence(sample.pose_world.values[:3], sample.pose_world.values[3:])
    pairs = (
        ("topic_vs_moveit", topic, observation.moveit_pose_world),
        *((("simulator_vs_moveit", observation.simulator_pose_world, observation.moveit_pose_world),) if perception_gate else ()),
    )
    for name, left, right in pairs:
        if (
            _position_distance(left, right) > template.scene_position_tolerance_m
            or _orientation_distance(left, right) > template.scene_orientation_tolerance_rad
        ):
            raise CupPosePreflightError(
                "CUP_POSE_SCENE_DIVERGENCE", f"{name} exceeds configured tolerance"
            )


def validate_cup_against_simulator(
    sample: CupPoseSample,
    observation: CupSceneObservation,
    template: DynamicPickTemplate,
    *,
    perception_gate: bool = True,
) -> None:
    """Reject perception that cannot be confirmed by simulator truth (``perception_gate=False``: only the MoveIt state is checked)."""

    if observation.moveit_attached:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE", "plastic_cup must be a MoveIt world object"
        )
    if not perception_gate:
        return
    topic = PoseEvidence(sample.pose_world.values[:3], sample.pose_world.values[3:])
    if (
        _position_distance(topic, observation.simulator_pose_world)
        > template.scene_position_tolerance_m
        or _orientation_distance(topic, observation.simulator_pose_world)
        > template.scene_orientation_tolerance_rad
    ):
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE",
            "topic_vs_simulator exceeds configured tolerance",
        )


def _cup_axis(quaternion_xyzw) -> tuple[float, float, float]:
    x, y, z, w = quaternion_xyzw
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return (2.0 * (x * z + w * y), 2.0 * (y * z - w * x), 1.0 - 2.0 * (x * x + y * y))


def perception_error(sample: CupPoseSample, observation: CupSceneObservation) -> dict[str, float]:
    """The perceived cup pose (the broker's `/cup_pose`) against simulator truth at the start of the run: a telemetry record,
    never a refusal (Teacher policy v3, design 2026-10-10 section 7). ``tilt_deg`` is the yaw-free angle between the two cup axes."""
    truth = observation.simulator_pose_world
    px, py, pz = sample.pose_world.values[:3]
    tx, ty, tz = truth.position_m
    axis_a, axis_b = _cup_axis(sample.pose_world.values[3:]), _cup_axis(truth.orientation_xyzw)
    cosine = min(1.0, max(-1.0, sum(a * b for a, b in zip(axis_a, axis_b, strict=True))))
    if not all(math.isfinite(item) for item in (px, py, pz, tx, ty, tz, *axis_a, *axis_b)):
        # NaN would pass the clamp above (a NaN cosine reads as a 180 degree tilt): the runtime records PERCEPTION_ERROR_UNAVAILABLE
        raise ValueError("PERCEPTION_ERROR_NON_FINITE")
    return {
        "xy_mm": math.hypot(px - tx, py - ty) * 1e3,
        "z_mm": (pz - tz) * 1e3,
        "tilt_deg": math.degrees(math.acos(cosine)),
        "perceived_position_m": [px, py, pz],
        "truth_position_m": [tx, ty, tz],
    }
