"""Read-only simulator and Planning Scene cup-pose boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from .evidence import PoseEvidence


@dataclass(frozen=True, slots=True)
class CupSceneObservation:
    simulator_pose_world: PoseEvidence
    simulator_received_monotonic_s: float
    moveit_pose_world: PoseEvidence
    moveit_received_monotonic_s: float
    moveit_attached: bool
    simulation_session_id: str | None = None
    reset_epoch: int | None = None
    paused: bool | None = None

    def __post_init__(self) -> None:
        times = (self.simulator_received_monotonic_s, self.moveit_received_monotonic_s)
        if any(not math.isfinite(value) or value < 0.0 for value in times):
            raise ValueError("scene receipt times must be finite and non-negative")


class CupSceneObservationPort(Protocol):
    def observe(self, timeout_s: float) -> CupSceneObservation: ...
