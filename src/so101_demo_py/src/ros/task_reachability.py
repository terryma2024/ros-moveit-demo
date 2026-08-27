"""Plan-only MoveGroup adapter for sequential task reachability checks."""

from __future__ import annotations

import time
from typing import Any, Callable

from ..application.task_reachability import SegmentPlanReceipt
from ..control.moveit.planning import PosePlanRequest, make_get_motion_plan_pose_request
from ..control.planning_scene.cup import make_cup_collision_object
from ..core.domain import State
from ..core.dynamic_pick import DynamicPickTemplate
from ..ports.evidence import PoseEvidence
from ..ports.robot_control import JointStateEvidence


def make_move_group_goal(
    *,
    state: State,
    target: PoseEvidence,
    start: JointStateEvidence,
    cup_pose_world: PoseEvidence,
    template: DynamicPickTemplate,
) -> Any:
    """Build a request-local, plan-only MoveGroup goal.

    ``state`` is intentionally accepted at this boundary even though MoveIt does
    not carry the state-machine label: callers retain an explicit one-goal-per-
    segment mapping while the wire request stays standard.
    """

    del state
    from moveit_msgs.action import MoveGroup

    request = PosePlanRequest(
        joint_names=start.names,
        current_positions=start.positions_rad,
        target_position_m=target.position_m,
        target_orientation_xyzw=target.orientation_xyzw,
        orientation_tolerance_rad=template.orientation_tolerance_rad,
        position_tolerance_m=template.position_tolerance_m,
        velocity_scaling=template.velocity_scaling,
        acceleration_scaling=template.acceleration_scaling,
        planning_time_s=template.planning_timeout_s,
        planning_group=template.planning_group,
        frame_id=template.planning_frame,
        tcp_link=template.tcp_link,
        enforce_orientation_path=False,
    )
    wire = make_get_motion_plan_pose_request(request)
    goal = MoveGroup.Goal()
    goal.request = wire.motion_plan_request
    goal.planning_options.plan_only = True
    goal.planning_options.replan = False
    goal.planning_options.planning_scene_diff.is_diff = True
    goal.planning_options.planning_scene_diff.world.collision_objects = [
        make_cup_collision_object(
            cup_pose_world.position_m,
            cup_pose_world.orientation_xyzw,
        )
    ]
    return goal


class RosMoveGroupReachabilityPlanner:
    """Submit plan-only MoveGroup goals and expose terminal joint evidence."""

    def __init__(
        self,
        node: Any,
        template: DynamicPickTemplate,
        *,
        action_client: Any | None = None,
        progress: Callable[[], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._node = node
        self._template = template
        self._monotonic = monotonic
        self._progress = progress or self._spin_once
        if action_client is None:
            from moveit_msgs.action import MoveGroup
            from rclpy.action import ActionClient

            action_client = ActionClient(node, MoveGroup, "/move_action")
        self._plan_client = action_client

    def _spin_once(self) -> None:
        import rclpy

        rclpy.spin_once(self._node, timeout_sec=0.01)

    def _wait_future(self, future: Any, deadline: float) -> bool:
        while not future.done() and self._monotonic() < deadline:
            self._progress()
            time.sleep(0.001)
        return bool(future.done())

    @staticmethod
    def _failure(code: str, moveit_error_code: int | None = None) -> SegmentPlanReceipt:
        return SegmentPlanReceipt(False, None, moveit_error_code, code)

    def plan(
        self,
        state: State,
        target: PoseEvidence,
        start: JointStateEvidence,
        cup_pose_world: PoseEvidence,
        timeout_s: float,
    ) -> SegmentPlanReceipt:
        if not self._plan_client.wait_for_server(timeout_sec=timeout_s):
            return self._failure("PLANNER_UNAVAILABLE")
        goal = make_move_group_goal(
            state=state,
            target=target,
            start=start,
            cup_pose_world=cup_pose_world,
            template=self._template,
        )
        deadline = self._monotonic() + timeout_s
        goal_future = self._plan_client.send_goal_async(goal)
        if not self._wait_future(goal_future, deadline):
            return self._failure("PLAN_TIMEOUT")
        handle = goal_future.result()
        if handle is None or not handle.accepted:
            return self._failure("MOVEIT_PLAN_FAILED")
        result_future = handle.get_result_async()
        if not self._wait_future(result_future, deadline):
            return self._failure("PLAN_TIMEOUT")
        envelope = result_future.result()
        result = None if envelope is None else envelope.result
        if result is None:
            return self._failure("PLANNER_UNAVAILABLE")
        error_code = int(result.error_code.val)
        if error_code != 1:
            return self._failure("MOVEIT_PLAN_FAILED", error_code)
        trajectory = result.planned_trajectory.joint_trajectory
        if not trajectory.points:
            return self._failure("TERMINAL_STATE_UNAVAILABLE", error_code)
        planned_positions = {
            name: float(value)
            for name, value in zip(
                trajectory.joint_names,
                trajectory.points[-1].positions,
                strict=True,
            )
        }
        terminal = JointStateEvidence(
            start.names,
            tuple(
                planned_positions.get(name, position)
                for name, position in zip(start.names, start.positions_rad, strict=True)
            ),
            self._monotonic(),
        )
        return SegmentPlanReceipt(True, terminal, error_code, None)

    def close(self) -> None:
        destroy = getattr(self._plan_client, "destroy", None)
        if callable(destroy):
            destroy()


class RosJointStateReader:
    """Read a complete, ordered arm joint state without owning robot execution."""

    def __init__(self, node: Any, joint_names: tuple[str, ...]) -> None:
        from sensor_msgs.msg import JointState

        self._node = node
        self._joint_names = joint_names
        self._positions: dict[str, float] = {}
        self._subscription = node.create_subscription(
            JointState, "/joint_states", self._on_joint_state, 100
        )

    def _on_joint_state(self, message: Any) -> None:
        if len(message.name) == len(message.position):
            self._positions.update(
                (name, float(position))
                for name, position in zip(message.name, message.position, strict=True)
            )

    def read(self, timeout_s: float) -> JointStateEvidence | None:
        import rclpy

        deadline = time.monotonic() + timeout_s
        while (
            any(name not in self._positions for name in self._joint_names)
            and time.monotonic() < deadline
        ):
            rclpy.spin_once(
                self._node,
                timeout_sec=min(0.05, max(0.0, deadline - time.monotonic())),
            )
        if any(name not in self._positions for name in self._joint_names):
            return None
        return JointStateEvidence(
            self._joint_names,
            tuple(self._positions[name] for name in self._joint_names),
            time.monotonic(),
        )

    def close(self) -> None:
        self._node.destroy_subscription(self._subscription)
