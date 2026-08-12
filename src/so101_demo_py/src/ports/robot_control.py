"""Typed robot action boundary shared by simulator backends."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .evidence import PoseEvidence


def _finite_tuple(name: str, values: tuple[float, ...]) -> None:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError(f"{name} must contain finite values")


@dataclass(frozen=True, slots=True)
class JointStateEvidence:
    names: tuple[str, ...]
    positions_rad: tuple[float, ...]
    observed_monotonic_s: float

    def __post_init__(self) -> None:
        if not self.names or len(self.names) != len(self.positions_rad):
            raise ValueError("joint state names and positions must be complete")
        if len(set(self.names)) != len(self.names) or any(not name for name in self.names):
            raise ValueError("joint state names must be unique and non-empty")
        _finite_tuple("positions_rad", self.positions_rad)
        if not math.isfinite(self.observed_monotonic_s) or self.observed_monotonic_s < 0.0:
            raise ValueError("joint state receipt time must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class JointWaypointRequest:
    joint_names: tuple[str, ...]
    target_positions_rad: tuple[float, ...]
    timeout_s: float = 10.0

    def __post_init__(self) -> None:
        if not self.joint_names or len(self.joint_names) != len(self.target_positions_rad):
            raise ValueError("joint waypoint request is incomplete")
        _finite_tuple("target_positions_rad", self.target_positions_rad)
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")


@dataclass(frozen=True, slots=True)
class TcpMotionRequest:
    target_pose: PoseEvidence
    timeout_s: float = 10.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")


@dataclass(frozen=True, slots=True)
class PlanResult:
    accepted: bool
    start_state: JointStateEvidence | None = None
    trajectory: object | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    accepted: bool
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class GripperRequest:
    target_position_rad: float
    duration_s: float
    timeout_s: float

    def __post_init__(self) -> None:
        values = (self.target_position_rad, self.duration_s, self.timeout_s)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("gripper request must contain finite values")
        if self.duration_s <= 0.0 or self.timeout_s <= 0.0:
            raise ValueError("gripper durations must be positive")


@dataclass(frozen=True, slots=True)
class GripperResult:
    accepted: bool
    observed_position_rad: float | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class StopResult:
    accepted: bool
    reason: str
    error_code: str | None = None


@runtime_checkable
class RobotControlPort(Protocol):
    def current_joint_state(self, timeout_s: float) -> JointStateEvidence: ...

    def plan_joint_waypoints(self, request: JointWaypointRequest) -> PlanResult: ...

    def plan_tcp_motion(self, request: TcpMotionRequest) -> PlanResult: ...

    def execute(self, plan: PlanResult) -> ExecutionResult: ...

    def command_gripper(self, request: GripperRequest) -> GripperResult: ...

    def stop(self, reason: str) -> StopResult: ...
