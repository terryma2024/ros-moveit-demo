"""Plan-only MoveGroup adapter for sequential task reachability checks."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Callable

from ..application.task_reachability import SegmentPlanReceipt
from ..control.moveit.deterministic_horizon import (
    MOVE_ABOVE_PLAN_CANDIDATE_COUNT,
    HorizonStep,
    HorizonWaypoint,
    cartesian_candidate_score,
    interpolated_move_above_waypoints,
    solve_horizon,
    validate_cartesian_corridor,
)
from ..control.moveit.planning import JointPlanRequest, make_get_motion_plan_request
from ..control.moveit.underactuated_ik import UnderactuatedPoseIk
from ..control.planning_scene.cup import make_cup_collision_object
from ..core.domain import State
from ..core.dynamic_pick import DynamicPickTemplate, ResolvedMotionTargets
from ..ports.evidence import PoseEvidence
from ..ports.robot_control import JointStateEvidence


def make_move_group_goal(
    *,
    state: State,
    target: PoseEvidence,
    start: JointStateEvidence,
    cup_pose_world: PoseEvidence,
    template: DynamicPickTemplate,
    joint_target: tuple[float, ...],
) -> Any:
    """Build a request-local, plan-only MoveGroup goal.

    ``state`` is intentionally accepted at this boundary even though MoveIt does
    not carry the state-machine label: callers retain an explicit one-goal-per-
    segment mapping while the wire request stays standard.
    """

    from moveit_msgs.action import MoveGroup
    from moveit_msgs.msg import CollisionObject

    arm_positions = tuple(
        start.positions_rad[start.names.index(name)] for name in template.arm_joint_names
    )
    request = JointPlanRequest(
        joint_names=template.arm_joint_names,
        current_positions=arm_positions,
        target_positions=joint_target,
        velocity_scaling=template.velocity_scaling,
        acceleration_scaling=template.acceleration_scaling,
        planning_time_s=template.planning_timeout_s,
        planning_group=template.planning_group,
        tcp_link=template.tcp_link,
        start_state_joint_names=start.names,
        start_state_positions=start.positions_rad,
    )
    wire = make_get_motion_plan_request(request)
    goal = MoveGroup.Goal()
    goal.request = wire.motion_plan_request
    goal.planning_options.plan_only = True
    goal.planning_options.replan = False
    goal.planning_options.planning_scene_diff.is_diff = True
    if state is State.MOVE_ABOVE_OBJECT:
        cup_object = make_cup_collision_object(
            cup_pose_world.position_m,
            cup_pose_world.orientation_xyzw,
        )
    else:
        # Every later TCP segment intentionally contacts, carries, releases, or
        # retreats from the target cup.  Keep that target out of this request-
        # local TCP-only collision scene while retaining all shared obstacles.
        cup_object = CollisionObject()
        cup_object.header.frame_id = template.planning_frame
        cup_object.id = template.object_id
        cup_object.operation = CollisionObject.REMOVE
    goal.planning_options.planning_scene_diff.world.collision_objects = [cup_object]
    return goal


class RosMoveGroupReachabilityPlanner:
    """Submit plan-only MoveGroup goals and expose terminal joint evidence."""

    def __init__(
        self,
        node: Any,
        template: DynamicPickTemplate,
        *,
        action_client: Any | None = None,
        ik: Any | None = None,
        progress: Callable[[], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._node = node
        self._template = template
        self._monotonic = monotonic
        self._progress = progress or self._spin_once
        if ik is None:
            from ament_index_python.packages import get_package_share_directory

            urdf = Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/so101.urdf"
            ik = UnderactuatedPoseIk.from_urdf(
                urdf,
                template.arm_joint_names,
                template.planning_frame,
                template.tcp_link,
            )
        self._ik = ik
        self._prepared_steps: dict[State, tuple[HorizonStep, ...]] = {}
        self._prepared_receipts: tuple[dict[str, object], ...] = ()
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
    def _failure(
        code: str,
        moveit_error_code: int | None = None,
        planning_receipts: tuple[dict[str, object], ...] = (),
    ) -> SegmentPlanReceipt:
        return SegmentPlanReceipt(False, None, moveit_error_code, code, (), planning_receipts)

    def _arm_positions(self, start: JointStateEvidence) -> tuple[float, ...]:
        return tuple(
            start.positions_rad[start.names.index(name)] for name in self._template.arm_joint_names
        )

    @staticmethod
    def _interpolate_pose(
        start: PoseEvidence, target: PoseEvidence, fraction: float
    ) -> PoseEvidence:
        position = tuple(
            a + fraction * (b - a) for a, b in zip(start.position_m, target.position_m, strict=True)
        )
        start_q = start.orientation_xyzw
        target_q = target.orientation_xyzw
        if sum(a * b for a, b in zip(start_q, target_q, strict=True)) < 0.0:
            target_q = tuple(-value for value in target_q)
        quaternion = tuple(a + fraction * (b - a) for a, b in zip(start_q, target_q, strict=True))
        norm = math.sqrt(sum(value * value for value in quaternion))
        return PoseEvidence(position, tuple(value / norm for value in quaternion))

    def prepare_horizon(self, targets: ResolvedMotionTargets, start: JointStateEvidence) -> None:
        """Prove the full pick prefix before the first plan-only request."""

        above = targets.for_state(State.MOVE_ABOVE_OBJECT)
        descend = targets.for_state(State.DESCEND)
        waypoints = list(
            interpolated_move_above_waypoints(
                self._ik,
                self._arm_positions(start),
                above,
            )
        )
        waypoints.extend(
            HorizonWaypoint(
                State.DESCEND,
                index,
                self._interpolate_pose(above, descend, index / 6.0),
            )
            for index in range(1, 7)
        )
        waypoints.extend(
            (
                HorizonWaypoint(State.MICRO_LIFT, 0, targets.for_state(State.MICRO_LIFT)),
                HorizonWaypoint(State.LIFT, 0, targets.for_state(State.LIFT)),
            )
        )
        result = solve_horizon(
            self._ik,
            tuple(waypoints),
            self._arm_positions(start),
            position_tolerance_m=self._template.position_tolerance_m,
            orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
            beam_width=3,
        )
        self._prepared_receipts = tuple(
            receipt.to_document() for receipt in result.candidate_receipts
        )
        self._prepared_steps = {}
        if not result.paths:
            return
        for step in result.paths[0].steps:
            self._prepared_steps.setdefault(step.waypoint.state, ())
            self._prepared_steps[step.waypoint.state] += (step,)

    def _steps_for(
        self, state: State, target: PoseEvidence, start: JointStateEvidence
    ) -> tuple[tuple[HorizonStep, ...], tuple[dict[str, object], ...]]:
        prepared = self._prepared_steps.get(state)
        if prepared:
            return prepared, self._prepared_receipts
        result = solve_horizon(
            self._ik,
            (HorizonWaypoint(state, 0, target),),
            self._arm_positions(start),
            position_tolerance_m=self._template.position_tolerance_m,
            orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
            beam_width=3,
        )
        receipts = tuple(item.to_document() for item in result.candidate_receipts)
        return (() if not result.paths else result.paths[0].steps), receipts

    def plan(
        self,
        state: State,
        target: PoseEvidence,
        start: JointStateEvidence,
        cup_pose_world: PoseEvidence,
        timeout_s: float,
    ) -> SegmentPlanReceipt:
        steps, ik_receipts = self._steps_for(state, target, start)
        if not steps:
            return self._failure("DYNAMIC_IK_HORIZON_FAILED", None, ik_receipts)
        if not self._plan_client.wait_for_server(timeout_sec=timeout_s):
            return self._failure("PLANNER_UNAVAILABLE", None, ik_receipts)
        terminal = start
        receipts = list(ik_receipts)
        error_code = None
        for step in steps:
            candidate_count = (
                MOVE_ABOVE_PLAN_CANDIDATE_COUNT
                if state is State.MOVE_ABOVE_OBJECT
                else 1
            )
            candidates = []
            last_failure = "MOVEIT_PLAN_FAILED"
            for candidate_index in range(candidate_count):
                goal = make_move_group_goal(
                    state=state,
                    target=step.waypoint.target,
                    start=terminal,
                    cup_pose_world=cup_pose_world,
                    template=self._template,
                    joint_target=step.receipt.joint_positions_rad or (),
                )
                deadline = self._monotonic() + timeout_s
                goal_future = self._plan_client.send_goal_async(goal)
                if not self._wait_future(goal_future, deadline):
                    return self._failure("PLAN_TIMEOUT", None, tuple(receipts))
                handle = goal_future.result()
                if handle is None or not handle.accepted:
                    return self._failure("MOVEIT_PLAN_FAILED", None, tuple(receipts))
                result_future = handle.get_result_async()
                if not self._wait_future(result_future, deadline):
                    return self._failure("PLAN_TIMEOUT", None, tuple(receipts))
                envelope = result_future.result()
                result = None if envelope is None else envelope.result
                if result is None:
                    return self._failure("PLANNER_UNAVAILABLE", None, tuple(receipts))
                error_code = int(result.error_code.val)
                trajectory = result.planned_trajectory
                if error_code != 1 or not trajectory.joint_trajectory.points:
                    last_failure = (
                        "MOVEIT_PLAN_FAILED"
                        if error_code != 1
                        else "TERMINAL_STATE_UNAVAILABLE"
                    )
                    receipts.append(
                        {
                            "kind": "moveit_plan_candidate",
                            "state": state.value,
                            "segment_index": step.waypoint.segment_index,
                            "candidate_index": candidate_index,
                            "accepted": False,
                            "failure_code": last_failure,
                            "moveit_error_code": error_code,
                        }
                    )
                    continue
                corridor = validate_cartesian_corridor(
                    self._ik,
                    trajectory,
                    self._template.arm_joint_names,
                    self._arm_positions(terminal),
                    step.waypoint.target,
                    maximum_deviation_m=(
                        0.008
                        if state
                        in {
                            State.DESCEND,
                            State.MICRO_LIFT,
                            State.LIFT,
                            State.DESCEND_TO_PLACE,
                        }
                        else 0.050
                    ),
                    orientation_tolerance_rad=max(
                        self._template.orientation_tolerance_rad
                    ),
                    minimum_clearance_z_m=(
                        0.145
                        if state in {State.DESCEND, State.MICRO_LIFT, State.LIFT}
                        else -math.inf
                    ),
                )
                candidate_document = corridor.to_document()
                candidate_document.update(
                    kind="moveit_plan_candidate",
                    validation_kind="actual_moveit_cartesian_corridor",
                    state=state.value,
                    segment_index=step.waypoint.segment_index,
                    candidate_index=candidate_index,
                    moveit_error_code=error_code,
                )
                receipts.append(candidate_document)
                last_failure = (
                    corridor.failure_code or "CARTESIAN_CORRIDOR_FAILED"
                )
                if corridor.accepted:
                    candidates.append(
                        (
                            cartesian_candidate_score(
                                corridor, candidate_index=candidate_index
                            ),
                            candidate_index,
                            trajectory,
                            error_code,
                        )
                    )
            if not candidates:
                return self._failure(
                    last_failure,
                    error_code,
                    tuple(receipts),
                )
            _, selected_index, trajectory, error_code = min(
                candidates, key=lambda item: item[0]
            )
            if candidate_count > 1:
                receipts.append(
                    {
                        "kind": "moveit_plan_selection",
                        "state": state.value,
                        "segment_index": step.waypoint.segment_index,
                        "candidate_index": selected_index,
                        "candidate_count": candidate_count,
                        "accepted_candidate_count": len(candidates),
                        "selection_reason": (
                            "minimum orientation error, Cartesian deviation, "
                            "sample count, then candidate index"
                        ),
                    }
                )
            planned_positions = {
                name: float(value)
                for name, value in zip(
                    trajectory.joint_trajectory.joint_names,
                    trajectory.joint_trajectory.points[-1].positions,
                    strict=True,
                )
            }
            terminal = JointStateEvidence(
                terminal.names,
                tuple(
                    planned_positions.get(name, position)
                    for name, position in zip(terminal.names, terminal.positions_rad, strict=True)
                ),
                self._monotonic(),
            )
        return SegmentPlanReceipt(True, terminal, error_code, None, (), tuple(receipts))

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
