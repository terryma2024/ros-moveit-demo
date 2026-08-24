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


def _position_distance(left: PoseEvidence, right: PoseEvidence) -> float:
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(left.position_m, right.position_m, strict=True))
    )


def _orientation_distance(left: PoseEvidence, right: PoseEvidence) -> float:
    left_norm = math.sqrt(sum(value * value for value in left.orientation_xyzw))
    right_norm = math.sqrt(sum(value * value for value in right.orientation_xyzw))
    dot = abs(
        sum(
            a * b
            for a, b in zip(left.orientation_xyzw, right.orientation_xyzw, strict=True)
        )
        / (left_norm * right_norm)
    )
    return 2.0 * math.acos(min(1.0, max(-1.0, dot)))


def validate_cup_scene(
    sample: CupPoseSample,
    observation: CupSceneObservation,
    template: DynamicPickTemplate,
) -> None:
    if observation.moveit_attached:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE", "plastic_cup must be a MoveIt world object"
        )
    topic = PoseEvidence(sample.pose_world.values[:3], sample.pose_world.values[3:])
    pairs = (
        ("topic_vs_simulator", topic, observation.simulator_pose_world),
        ("topic_vs_moveit", topic, observation.moveit_pose_world),
        ("simulator_vs_moveit", observation.simulator_pose_world, observation.moveit_pose_world),
    )
    for name, left, right in pairs:
        if (
            _position_distance(left, right) > template.scene_position_tolerance_m
            or _orientation_distance(left, right) > template.scene_orientation_tolerance_rad
        ):
            raise CupPosePreflightError(
                "CUP_POSE_SCENE_DIVERGENCE", f"{name} exceeds configured tolerance"
            )
