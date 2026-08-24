"""ROS/MoveIt adapter for dynamic single-state Pose planning."""

from __future__ import annotations

import time
from typing import Any

from ..control.moveit.planning import MoveItPlanningClient, PosePlanRequest
from ..control.robot_control import SharedRobotControl
from ..ports.robot_control import (
    ExecutionResult,
    GripperResult,
    JointStateEvidence,
    StopResult,
)


class RosDynamicPlanner:
    def __init__(self, node: Any, arm_joint_names: tuple[str, ...]) -> None:
        from moveit_msgs.srv import GetMotionPlan
        from sensor_msgs.msg import JointState

        self._node = node
        self._arm_joint_names = arm_joint_names
        self._positions: dict[str, float] = {}
        self._joint_subscription = node.create_subscription(
            JointState, "/joint_states", self._on_joint_state, 100
        )
        client = node.create_client(GetMotionPlan, "/plan_kinematic_path")
        self._planning = MoveItPlanningClient(
            client,
            progress=lambda: self._spin_once(0.0),
        )
        self.control = SharedRobotControl(
            state_reader=self._state,
            joint_planner=lambda *_: (_ for _ in ()).throw(
                RuntimeError("joint planning is unavailable in dynamic plan-only")
            ),
            tcp_planner=self._plan_tcp,
            trajectory_executor=lambda _: ExecutionResult(False, "DYNAMIC_EXECUTION_NOT_QUALIFIED"),
            gripper_commander=lambda _: GripperResult(False, error_code="PLAN_ONLY"),
            stopper=lambda reason: StopResult(True, reason),
        )

    def _spin_once(self, timeout_s: float) -> None:
        import rclpy

        rclpy.spin_once(self._node, timeout_sec=timeout_s)

    def _on_joint_state(self, message: Any) -> None:
        if len(message.name) == len(message.position):
            self._positions.update(
                (name, float(position))
                for name, position in zip(message.name, message.position, strict=True)
            )

    def _state(self, timeout_s: float) -> JointStateEvidence:
        deadline = time.monotonic() + timeout_s
        while (
            any(name not in self._positions for name in self._arm_joint_names)
            and time.monotonic() < deadline
        ):
            self._spin_once(min(0.05, deadline - time.monotonic()))
        if any(name not in self._positions for name in self._arm_joint_names):
            raise RuntimeError("JOINT_STATE_TIMEOUT")
        return JointStateEvidence(
            self._arm_joint_names,
            tuple(self._positions[name] for name in self._arm_joint_names),
            time.monotonic(),
        )

    def _plan_tcp(self, request, start: JointStateEvidence):
        outcome = self._planning.plan_pose_path(
            PosePlanRequest(
                joint_names=start.names,
                current_positions=start.positions_rad,
                target_position_m=request.target_pose.position_m,
                target_orientation_xyzw=request.target_pose.orientation_xyzw,
                orientation_tolerance_rad=request.orientation_tolerance_rad,
                position_tolerance_m=request.position_tolerance_m,
                velocity_scaling=request.velocity_scaling,
                acceleration_scaling=request.acceleration_scaling,
                planning_time_s=request.timeout_s,
                planning_group=request.planning_group,
                frame_id=request.planning_frame,
                tcp_link=request.tcp_link,
            ),
            timeout_s=request.timeout_s,
        )
        if outcome.failure is not None or outcome.trajectory is None:
            code = "CUP_POSE_PLAN_FAILED"
            if outcome.failure is not None and outcome.failure.code:
                code = outcome.failure.code
            raise RuntimeError(code)
        joint = outcome.trajectory.joint_trajectory
        final = joint.points[-1]
        terminal = JointStateEvidence(
            tuple(joint.joint_names), tuple(float(value) for value in final.positions), time.monotonic()
        )
        return outcome.trajectory, terminal

    def close(self) -> None:
        self._node.destroy_subscription(self._joint_subscription)
