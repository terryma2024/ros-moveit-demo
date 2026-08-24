"""Atomic `so101-dynamic-plan-v1` evidence writer."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..core.dynamic_pick import CupPoseSample, ResolvedMotionTargets
from ..ports.cup_scene_observation import CupSceneObservation
from ..ports.evidence import PoseEvidence
from ..ports.robot_control import JointStateEvidence, PlanResult


def _pose(value: PoseEvidence) -> list[float]:
    return [*value.position_m, *value.orientation_xyzw]


def _joint_state(value: JointStateEvidence | None):
    if value is None:
        return None
    return {
        "names": list(value.names),
        "positions_rad": list(value.positions_rad),
        "observed_monotonic_s": value.observed_monotonic_s,
    }


def _scene(value: CupSceneObservation | None):
    if value is None:
        return None
    return {
        "simulator_pose_world_xyz_xyzw": _pose(value.simulator_pose_world),
        "simulator_received_monotonic_s": value.simulator_received_monotonic_s,
        "moveit_pose_world_xyz_xyzw": _pose(value.moveit_pose_world),
        "moveit_received_monotonic_s": value.moveit_received_monotonic_s,
        "moveit_attached": value.moveit_attached,
    }


def write_dynamic_plan_manifest(
    path: Path,
    *,
    backend: str,
    source_commit: str,
    installed_prefix: str,
    policy_path: Path,
    policy_sha256: str,
    qualification_status: str,
    selected_state: str,
    sample: CupPoseSample,
    targets: ResolvedMotionTargets,
    before_scene: CupSceneObservation,
    after_scene: CupSceneObservation,
    plan: PlanResult,
) -> Path:
    trajectory = getattr(plan.trajectory, "joint_trajectory", None)
    points = getattr(trajectory, "points", ()) if trajectory is not None else ()
    document = {
        "schema": "so101-dynamic-plan-v1",
        "strategy": "dynamic",
        "backend": backend,
        "execution_allowed": False,
        "source_commit": source_commit,
        "installed_prefix": installed_prefix,
        "policy": {
            "path": str(policy_path),
            "sha256": policy_sha256,
            "qualification_status": qualification_status,
        },
        "input": {
            "frame_id": sample.frame_id,
            "source_stamp_ns": sample.source_stamp_ns,
            "received_monotonic_s": sample.received_monotonic_s,
            "pose_world_xyz_xyzw": list(sample.pose_world.values),
        },
        "selected_state": selected_state,
        "targets": {
            state.value: _pose(pose)
            for state, pose in sorted(targets.targets.items(), key=lambda item: item[0].value)
        },
        "scene_before": _scene(before_scene),
        "scene_after": _scene(after_scene),
        "plan": {
            "accepted": plan.accepted,
            "error_code": plan.error_code,
            "start_state": _joint_state(plan.start_state),
            "terminal_state": _joint_state(plan.terminal_state),
            "trajectory_point_count": len(points),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path
