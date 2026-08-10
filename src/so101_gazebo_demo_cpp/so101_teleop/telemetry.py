"""Immutable telemetry publication and conservative mutation readiness checks."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from .models import PhysicalOutcomeEvidence, Pose6D, ServerMode, TelemetrySnapshot


_MAX_OUTCOME_METRICS = 64


def physical_outcome_from_checkpoint(checkpoint: Mapping[str, Any]) -> PhysicalOutcomeEvidence:
    """Translate bounded C++ checkpoint evidence without re-evaluating outcome policy."""
    expected = checkpoint.get("expected") or {}
    failure = checkpoint.get("original_failure") or {}
    raw_metrics = failure.get("metrics") or {}
    metrics = {
        str(name): float(value)
        for name, value in list(raw_metrics.items())[:_MAX_OUTCOME_METRICS]
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    }
    pose = expected.get("gazebo_task_object_pose_world")
    final_pose = None
    if isinstance(pose, Mapping):
        qx, qy, qz, qw = (float(pose[name]) for name in ("qx", "qy", "qz", "qw"))
        sinr = 2.0 * (qw * qx + qy * qz)
        cosr = 1.0 - 2.0 * (qx * qx + qy * qy)
        sinp = max(-1.0, min(1.0, 2.0 * (qw * qy - qz * qx)))
        final_pose = Pose6D(
            frame_id="world", tcp_frame="plastic_cup",
            x_m=float(pose["x"]), y_m=float(pose["y"]), z_m=float(pose["z"]),
            roll_rad=math.atan2(sinr, cosr), pitch_rad=math.asin(sinp),
            yaw_rad=math.atan2(2.0 * (qw * qz + qx * qy),
                               1.0 - 2.0 * (qy * qy + qz * qz)),
        )
    epoch_start = metrics.get("release_epoch_start_sequence")
    session_id = checkpoint.get("simulation_session_id")
    release_epoch_id = None
    if session_id and epoch_start is not None:
        release_epoch_id = f"{session_id}:release:{int(epoch_start)}"
    return PhysicalOutcomeEvidence(
        release_epoch_id=release_epoch_id,
        first_sequence=int(metrics["final_first_sequence"])
        if "final_first_sequence" in metrics else None,
        last_sequence=expected.get("gazebo_pose_sequence"),
        sample_count=int(metrics.get("final_sample_count", 0.0)),
        duration_s=metrics.get("final_stable_duration_s", 0.0),
        metrics=metrics,
        final_pose=final_pose,
        intended_support_contact=expected.get("gazebo_task_object_intended_support_contact"),
        gripper_contact=None,
        gazebo_attached=expected.get("gazebo_task_object_attached"),
        moveit_attached=expected.get("moveit_task_object_attached"),
        world_object_synchronized=bool(metrics.get("final_world_object_synchronized", 0.0))
        if "final_world_object_synchronized" in metrics else None,
        primary_failure=failure.get("code"),
    )


@dataclass(frozen=True)
class ReadinessResult:
    mode: ServerMode
    reasons: Tuple[str, ...] = ()


class ReadinessEvaluator:
    def __init__(self, max_age_s: float = 0.5) -> None:
        self._max_age_s = max_age_s

    def evaluate(self, snapshot: TelemetrySnapshot) -> ReadinessResult:
        reasons = []
        for joint in map(str, range(1, 7)):
            if joint not in snapshot.joints:
                reasons.append(f"JOINT_{joint}_MISSING")
        if snapshot.tcp is None:
            reasons.append("TCP_MISSING")
        if snapshot.object_pose is None:
            reasons.append("OBJECT_POSE_MISSING")
        for name in ("arm_controller", "gripper_controller"):
            if snapshot.controllers.get(name) != "active":
                reasons.append(f"{name.upper()}_INACTIVE")
        if snapshot.gazebo_attached is None:
            reasons.append("GAZEBO_ATTACHMENT_UNKNOWN")
        if snapshot.moveit_attached is None:
            reasons.append("MOVEIT_SCENE_UNKNOWN")
        for source in ("joints", "tcp", "object", "scene"):
            age = snapshot.source_ages_s.get(source)
            if age is None or age > self._max_age_s:
                reasons.append(f"{source.upper()}_STALE")
        return ReadinessResult(ServerMode.READY if not reasons else ServerMode.READ_ONLY, tuple(reasons))


class TelemetryCollector:
    """Publishes copied Pydantic snapshots so clients cannot mutate shared state."""

    def __init__(self) -> None:
        self._sequence = 0
        self._latest = TelemetrySnapshot()

    def publish(self, snapshot: TelemetrySnapshot) -> TelemetrySnapshot:
        self._sequence += 1
        published = snapshot.copy(update={
            "sequence": self._sequence,
            "server_timestamp": time.time(),
        }, deep=True)
        self._latest = published
        return published.copy(deep=True)

    def snapshot(self) -> TelemetrySnapshot:
        return self._latest.copy(deep=True)
