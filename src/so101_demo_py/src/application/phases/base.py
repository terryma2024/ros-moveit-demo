"""Backend-neutral phase context used by the common nine-phase application."""

from __future__ import annotations

from dataclasses import dataclass

from ...ports.lifecycle import LifecyclePort
from ...ports.planning_scene import PlanningScenePort
from ...ports.robot_control import RobotControlPort
from ...ports.world import WorldPort


@dataclass(frozen=True, slots=True)
class PhaseContext:
    robot_control: RobotControlPort
    planning_scene: PlanningScenePort
    world: WorldPort
    lifecycle: LifecyclePort
    phase_evidence: object | None = None


@dataclass(frozen=True, slots=True)
class PhaseResult:
    accepted: bool
    error_code: str | None = None
