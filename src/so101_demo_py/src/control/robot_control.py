"""Shared fail-closed RobotControlPort implementation over injected ROS clients."""

from __future__ import annotations

import math
from collections.abc import Callable

from ..ports.robot_control import (
    ExecutionResult,
    GripperRequest,
    GripperResult,
    JointStateEvidence,
    JointWaypointRequest,
    PlanResult,
    StopResult,
    TcpMotionRequest,
)


class SharedRobotControl:
    def __init__(
        self,
        *,
        state_reader: Callable[[float], JointStateEvidence],
        joint_planner: Callable[[JointWaypointRequest, JointStateEvidence], object],
        tcp_planner: Callable[[TcpMotionRequest, JointStateEvidence], object],
        trajectory_executor: Callable[[object], ExecutionResult],
        gripper_commander: Callable[[GripperRequest], GripperResult],
        stopper: Callable[[str], StopResult],
        start_state_tolerance_rad: float = 0.01,
    ) -> None:
        if not math.isfinite(start_state_tolerance_rad) or start_state_tolerance_rad <= 0.0:
            raise ValueError("start-state tolerance must be finite and positive")
        self._state_reader = state_reader
        self._joint_planner = joint_planner
        self._tcp_planner = tcp_planner
        self._trajectory_executor = trajectory_executor
        self._gripper_commander = gripper_commander
        self._stopper = stopper
        self._start_state_tolerance_rad = start_state_tolerance_rad

    def current_joint_state(self, timeout_s: float) -> JointStateEvidence:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        return self._state_reader(timeout_s)

    def plan_joint_waypoints(self, request: JointWaypointRequest) -> PlanResult:
        start = self.current_joint_state(request.timeout_s)
        try:
            trajectory = self._joint_planner(request, start)
        except Exception:
            return PlanResult(False, start_state=start, error_code="PLANNING_FAILED")
        return PlanResult(True, start, trajectory)

    def plan_tcp_motion(self, request: TcpMotionRequest) -> PlanResult:
        start = request.start_state or self.current_joint_state(request.timeout_s)
        try:
            planned = self._tcp_planner(request, start)
        except Exception:
            return PlanResult(False, start_state=start, error_code="PLANNING_FAILED")
        terminal = None
        trajectory = planned
        if (
            isinstance(planned, tuple)
            and len(planned) == 2
            and isinstance(planned[1], JointStateEvidence)
        ):
            trajectory, terminal = planned
        return PlanResult(
            True,
            start_state=start,
            trajectory=trajectory,
            terminal_state=terminal,
        )

    def execute(self, plan: PlanResult) -> ExecutionResult:
        if not plan.accepted or plan.start_state is None or plan.trajectory is None:
            return ExecutionResult(False, "PLAN_NOT_EXECUTABLE")
        current = self.current_joint_state(2.0)
        expected = dict(zip(plan.start_state.names, plan.start_state.positions_rad, strict=True))
        observed = dict(zip(current.names, current.positions_rad, strict=True))
        if any(
            name not in observed
            or abs(position - observed[name]) > self._start_state_tolerance_rad
            for name, position in expected.items()
        ):
            return ExecutionResult(False, "PLAN_START_STATE_MISMATCH")
        return self._trajectory_executor(plan.trajectory)

    def command_gripper(self, request: GripperRequest) -> GripperResult:
        return self._gripper_commander(request)

    def stop(self, reason: str) -> StopResult:
        if not reason:
            raise ValueError("stop reason must be non-empty")
        return self._stopper(reason)
