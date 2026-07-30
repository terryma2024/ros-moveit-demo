"""Immutable telemetry publication and conservative mutation readiness checks."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Tuple

from .models import ServerMode, TelemetrySnapshot


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
