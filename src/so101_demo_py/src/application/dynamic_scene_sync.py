"""Perception-confirmed transaction for the MoveIt cup shadow."""

from __future__ import annotations

import json
from dataclasses import replace

from ..core.dynamic_pick import CupPoseSample, DynamicPickTemplate
from ..core.task_geometry import Pose7, TaskGeometry
from ..ports.cup_scene_observation import CupSceneObservation
from ..ports.planning_scene import TaskScenePort
from .cup_pose_preflight import (
    CupPosePreflightError,
    validate_cup_against_simulator,
)


def _scene_failure_message(label: str, receipt) -> str:
    evidence = json.dumps(
        receipt.evidence,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    )
    return (
        f"{label}: failure_code={receipt.failure_code or 'unknown failure'} "
        f"evidence={evidence}"
    )


def geometry_with_cup_pose(geometry: TaskGeometry, pose: Pose7) -> TaskGeometry:
    """Return a new geometry with exactly the canonical cup pose replaced."""

    cup_count = sum(item.object_id == "plastic_cup" for item in geometry.objects)
    if cup_count != 1:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE",
            "task geometry must contain exactly one plastic_cup",
        )
    objects = tuple(
        replace(item, pose=pose) if item.object_id == "plastic_cup" else item
        for item in geometry.objects
    )
    return replace(geometry, objects=objects)


def prepare_dynamic_cup_scene(
    sample: CupPoseSample,
    observation: CupSceneObservation,
    template: DynamicPickTemplate,
    geometry: TaskGeometry,
    scene: TaskScenePort,
) -> TaskGeometry:
    """Confirm simulator truth, update only the cup shadow, and read it back."""

    validate_cup_against_simulator(sample, observation, template)
    updated = geometry_with_cup_pose(geometry, sample.pose_world)
    applied = scene.apply_task_scene(updated)
    if not applied.success:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE",
            _scene_failure_message("scene apply failed", applied),
        )
    observed = scene.observe_task_scene(updated, expected_cup_attachment=None)
    if not observed.success:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE",
            _scene_failure_message("scene readback failed", observed),
        )
    return updated
