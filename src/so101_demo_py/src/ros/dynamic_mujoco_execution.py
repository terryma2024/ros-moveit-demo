"""MuJoCo execution adapter for the perception-driven shared workflow."""

from __future__ import annotations

import copy
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from ..application.e2e_acceptance import (
    FINAL_MAX_ANGULAR_SPEED_RAD_S,
    FINAL_MAX_LINEAR_SPEED_M_S,
    FINAL_MAX_UPRIGHT_TILT_RAD,
    FINAL_SUPPORT_HEIGHT_RANGE_M,
    FINAL_XY_TOLERANCE_M,
)
from ..control.gripper.client import GripperClient
from ..control.moveit.deterministic_horizon import (
    MOVE_ABOVE_PLAN_CANDIDATE_COUNT,
    HorizonStep,
    HorizonWaypoint,
    cartesian_candidate_score,
    interpolated_move_above_waypoints,
    solve_horizon,
    validate_cartesian_corridor,
)
from ..control.moveit.planning import JointPlanRequest, MoveItPlanningClient
from ..control.moveit.underactuated_ik import UnderactuatedPoseIk
from ..control.planning_scene.acm import set_collision_allowed
from ..control.planning_scene.cup import make_cup_collision_object
from ..control.trajectory.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
    make_execute_goal,
)
from ..core.domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from ..core.dynamic_pick import (
    DynamicPickTemplate,
    ResolvedMotionTargets,
    compose_pose,
    inverse_pose,
)
from ..ports.evidence import PoseEvidence


class RosDynamicMujocoExecution:
    """Execute one dynamic run while preserving the repository workflow states."""

    _ARM_JOINTS = ("1", "2", "3", "4", "5")
    _PREOPEN_Q6 = 0.465038
    _CLOSE_Q6 = -0.0485
    _RELEASE_Q6 = 0.75
    _MAX_FORCE_N = 11.60

    @staticmethod
    def _workflow_identity_fields(
        workflow_id: str | None, request_id: str | None
    ) -> dict[str, str]:
        if workflow_id is None and request_id is None:
            return {}
        if (
            type(workflow_id) is not str
            or not workflow_id.strip()
            or type(request_id) is not str
            or not request_id.strip()
        ):
            raise ValueError("dynamic execution provenance is incomplete")
        return {"workflow_id": workflow_id, "request_id": request_id}

    @staticmethod
    def _parallel_identity_fields(identity) -> dict[str, object]:
        if identity is None:
            return {}
        fields = {
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        }
        if type(identity) is not dict or set(identity) != fields:
            raise ValueError("dynamic parallel lease identity is incomplete")
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            if not isinstance(identity[name], str) or not identity[name]:
                raise ValueError("dynamic parallel lease identity is invalid")
        for name in (
            "coordinator_epoch", "worker_generation", "lease_generation"
        ):
            if type(identity[name]) is not int or identity[name] <= 0:
                raise ValueError("dynamic parallel lease identity is invalid")
        return {"parallel_lease_identity": dict(identity)}

    def __init__(
        self,
        node: Any,
        template: DynamicPickTemplate,
        targets: ResolvedMotionTargets,
        *,
        session_id: str,
        expected_reset_epoch: int,
        evidence_file: Path,
        urdf_path: Path,
        policy_path: Path,
        policy_sha256: str,
        workflow_id: str | None = None,
        request_id: str | None = None,
        parallel_lease_identity: dict[str, object] | None = None,
    ) -> None:
        from control_msgs.action import FollowJointTrajectory
        from moveit_msgs.action import ExecuteTrajectory
        from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
        from rclpy.action import ActionClient
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import JointState

        from ..backends.mujoco.observer import MujocoWorldObserver

        workflow_identity = self._workflow_identity_fields(workflow_id, request_id)
        parallel_identity = self._parallel_identity_fields(parallel_lease_identity)
        if not session_id or expected_reset_epoch < 0:
            raise ValueError("dynamic execution provenance is incomplete")
        self._node = node
        self._template = template
        self._targets = targets
        self._session_id = session_id
        self._expected_reset_epoch = expected_reset_epoch
        self._evidence_file = evidence_file
        self._ik = UnderactuatedPoseIk.from_urdf(
            urdf_path,
            template.arm_joint_names,
            template.planning_frame,
            template.tcp_link,
        )
        self._positions: dict[str, float] = {}
        self._joint_state_generation = 0
        self._joint_state_source_stamp_ns: int | None = None
        self._joint_state_received_monotonic_s: float | None = None
        self._state_events: list[dict[str, object]] = []
        self._planning_attempts: list[dict[str, object]] = []
        self._pick_horizon_steps: dict[State, tuple[HorizonStep, ...]] = {}
        self._final_samples: list[dict[str, object]] = []
        self._release_marker_sequence: int | None = None
        self._attached = False
        self._initial = None
        self._before_micro_lift = None
        self._scene_readback: dict[str, object] | None = None
        self._touch_collision_allowed = False
        self._joint_subscription = node.create_subscription(
            JointState,
            "/joint_states",
            self._on_joint_state,
            qos_profile_sensor_data,
        )
        self.observer = MujocoWorldObserver(node, session_id, max_age_s=0.5)
        self._planning = MoveItPlanningClient(
            node.create_client(GetMotionPlan, "/plan_kinematic_path"),
            progress=self._progress,
        )
        self._trajectory = MoveItExecutionClient(
            ActionClient(node, ExecuteTrajectory, "/execute_trajectory"),
            goal_factory=make_execute_goal,
            progress=self._progress,
        )
        self._gripper = GripperClient(
            ActionClient(
                node,
                FollowJointTrajectory,
                "/gripper_controller/follow_joint_trajectory",
            ),
            progress=self._progress,
        )
        self._apply_scene = node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        self._get_scene = node.create_client(GetPlanningScene, "/get_planning_scene")
        self._document: dict[str, object] = {
            "schema": "so101-dynamic-mujoco-execute-v1",
            "status": "RUNNING",
            "simulation_session_id": session_id,
            "expected_reset_epoch": expected_reset_epoch,
            "policy_path": str(policy_path),
            "policy_sha256": policy_sha256,
            "input_cup_pose_world": list(targets.input_pose.pose_world.values),
            "input_frame_id": targets.input_pose.frame_id,
            "input_source_stamp_ns": targets.input_pose.source_stamp_ns,
            "resolved_targets": {
                state.value: [*pose.position_m, *pose.orientation_xyzw]
                for state, pose in sorted(targets.targets.items(), key=lambda item: item[0].value)
            },
            "state_events": self._state_events,
            "planning_attempts": self._planning_attempts,
            "final_samples": self._final_samples,
        }
        self._document.update(workflow_identity)
        self._document.update(parallel_identity)
        self._write()

    @property
    def evidence_file(self) -> Path:
        return self._evidence_file

    def _write(self) -> None:
        self._evidence_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._evidence_file.with_name(f".{self._evidence_file.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(self._document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._evidence_file)

    def finish(self, result) -> None:
        self._document.update(
            {
                "status": "DONE" if result.status.value == "DONE" else "ERROR",
                "current_state": result.current_state.value,
                "transition_count": result.transition_count,
                "state_trace": [state.value for state in result.state_trace],
                "failure": None if result.failure is None else result.failure.code,
                "release_marker_sequence": self._release_marker_sequence,
                "planning_scene_readback": self._scene_readback,
            }
        )
        self._write()

    def _progress(self) -> None:
        import rclpy

        rclpy.spin_once(self._node, timeout_sec=0.01)

    def _on_joint_state(self, message: Any) -> None:
        if len(message.name) == len(message.position):
            positions = dict(
                (name, float(position))
                for name, position in zip(message.name, message.position, strict=True)
            )
            self._positions.update(positions)
            if all(name in positions for name in self._ARM_JOINTS):
                stamp = getattr(getattr(message, "header", None), "stamp", None)
                self._joint_state_source_stamp_ns = (
                    None if stamp is None else int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
                )
                self._joint_state_received_monotonic_s = time.monotonic()
                self._joint_state_generation += 1

    def _joint_state(
        self,
        timeout_s: float = 5.0,
        *,
        after_generation: int | None = None,
    ) -> tuple[float, ...]:
        deadline = time.monotonic() + timeout_s
        while any(name not in self._positions for name in self._ARM_JOINTS) or (
            after_generation is not None and self._joint_state_generation <= after_generation
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError("JOINT_STATE_TIMEOUT")
            self._progress()
        return tuple(self._positions[name] for name in self._ARM_JOINTS)

    def _snapshot(self):
        from ..backends.mujoco.observer import EvidenceStale

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            self._progress()
            try:
                value = self.observer.snapshot()
            except EvidenceStale:
                continue
            if value.simulation_session_id != self._session_id:
                raise RuntimeError("DYNAMIC_SESSION_MISMATCH")
            if value.reset_epoch != self._expected_reset_epoch or value.paused:
                raise RuntimeError("DYNAMIC_RESET_EPOCH_MISMATCH")
            return value
        raise RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT")

    @staticmethod
    def _evidence(value) -> dict[str, object]:
        return {
            "publisher_sequence": value.publisher_sequence,
            "simulation_step": value.simulation_step,
            "reset_epoch": value.reset_epoch,
            "cup_position_world_m": list(value.object_state.position_world),
            "cup_orientation_world_xyzw": list(value.object_state.orientation_xyzw),
            "cup_linear_velocity_world_m_s": list(value.object_state.linear_velocity_world),
            "cup_angular_velocity_world_rad_s": list(value.object_state.angular_velocity_world),
            "left_contact_count": len(value.left_fingertip_contacts),
            "right_contact_count": len(value.right_fingertip_contacts),
            "maximum_normal_force_n": value.maximum_normal_force_n,
            "table_contact": any(
                item.geom2 == "table_collision" for item in value.other_object_contacts
            ),
        }

    def _record(self, state: State, before, after, **details: object) -> None:
        self._state_events.append(
            {
                "state": state.value,
                "before": None if before is None else self._evidence(before),
                "after": None if after is None else self._evidence(after),
                **details,
            }
        )
        self._write()

    @staticmethod
    def _table_contact(value) -> bool:
        return any(item.geom2 == "table_collision" for item in value.other_object_contacts)

    @staticmethod
    def _bilateral(value) -> bool:
        return bool(value.left_fingertip_contacts and value.right_fingertip_contacts)

    @staticmethod
    def _reject_carried_table_contact(state: State, table_contact: bool) -> bool:
        return bool(table_contact and state is not State.MICRO_LIFT)

    @staticmethod
    def _interpolate_pose(
        start: PoseEvidence, target: PoseEvidence, fraction: float
    ) -> PoseEvidence:
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("pose interpolation fraction must be in [0, 1]")
        position = tuple(
            start.position_m[index]
            + fraction * (target.position_m[index] - start.position_m[index])
            for index in range(3)
        )
        start_q = start.orientation_xyzw
        target_q = target.orientation_xyzw
        if sum(a * b for a, b in zip(start_q, target_q, strict=True)) < 0.0:
            target_q = tuple(-value for value in target_q)
        quaternion = tuple(
            start_q[index] + fraction * (target_q[index] - start_q[index]) for index in range(4)
        )
        norm = math.sqrt(sum(value * value for value in quaternion))
        return PoseEvidence(position, tuple(value / norm for value in quaternion))

    @staticmethod
    def _upright_tilt_rad(quaternion_xyzw: tuple[float, float, float, float]) -> float:
        x, y, _z, _w = quaternion_xyzw
        world_z_dot = 1.0 - 2.0 * (x * x + y * y)
        return math.acos(min(1.0, max(-1.0, world_z_dot)))

    @staticmethod
    def _is_reconcilable_control_failure(result: ActionResult) -> bool:
        """Recognize only MoveIt's controller-level false-negative candidate."""

        return bool(
            result.status is not ActionStatus.SUCCEEDED
            and result.failure is not None
            and result.failure.code == "MOVEIT_EXECUTION_FAILED"
            and result.failure.metrics.get("moveit_error_code") == -6.0
        )

    @staticmethod
    def _terminal_pose_reconciliation(
        actual: PoseEvidence,
        target: PoseEvidence,
        *,
        position_tolerance_m: float,
        orientation_tolerance_rad: float,
        orientation_error_rad,
    ) -> dict[str, float] | None:
        """Accept CONTROL_FAILED only when fresh terminal TCP evidence proves arrival."""

        position_error_m = math.dist(actual.position_m, target.position_m)
        orientation_error = orientation_error_rad(actual, target)
        if position_error_m > position_tolerance_m or orientation_error > orientation_tolerance_rad:
            return None
        return {
            "moveit_error_code": -6,
            "terminal_position_error_m": position_error_m,
            "terminal_orientation_error_rad": orientation_error,
        }

    def _wait_stable(self, predicate, duration_s: float, timeout_s: float):
        started: float | None = None
        latest = None
        last_sequence = -1
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            value = self._snapshot()
            if value.publisher_sequence == last_sequence:
                continue
            last_sequence = value.publisher_sequence
            healthy = bool(predicate(value)) and value.maximum_normal_force_n <= self._MAX_FORCE_N
            now = time.monotonic()
            started = started if healthy and started is not None else (now if healthy else None)
            latest = value
            if started is not None and now - started >= duration_s:
                return latest
        raise RuntimeError("DYNAMIC_STABLE_STATE_TIMEOUT")

    def _record_planning_attempt(self, document: dict[str, object]) -> None:
        attempts = getattr(self, "_planning_attempts", None)
        if attempts is None:
            attempts = []
            self._planning_attempts = attempts
            self._document["planning_attempts"] = attempts
        attempts.append(document)
        self._write()

    def _motion_horizon(
        self,
        state: State,
        motion_targets: list[PoseEvidence],
        current: tuple[float, ...],
    ) -> tuple[HorizonStep, ...]:
        pick_prefix = {
            State.MOVE_ABOVE_OBJECT,
            State.DESCEND,
            State.MICRO_LIFT,
            State.LIFT,
        }
        cached = getattr(self, "_pick_horizon_steps", {}).get(state)
        if cached:
            return cached

        has_full_target_set = hasattr(self, "_targets")
        if state in pick_prefix and has_full_target_set:
            above = self._targets.for_state(State.MOVE_ABOVE_OBJECT)
            descend = self._targets.for_state(State.DESCEND)
            waypoints = list(
                interpolated_move_above_waypoints(
                    self._ik,
                    current,
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
                    HorizonWaypoint(
                        State.MICRO_LIFT,
                        0,
                        self._targets.for_state(State.MICRO_LIFT),
                    ),
                    HorizonWaypoint(State.LIFT, 0, self._targets.for_state(State.LIFT)),
                )
            )
        else:
            waypoints = [
                HorizonWaypoint(state, index, target) for index, target in enumerate(motion_targets)
            ]

        result = solve_horizon(
            self._ik,
            tuple(waypoints),
            current,
            position_tolerance_m=self._template.position_tolerance_m,
            orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
            beam_width=3,
        )
        if state in pick_prefix and has_full_target_set:
            horizon_document = result.to_document()
            horizon_document.update(
                selection_reason=(
                    "minimum deterministic cumulative score among complete beam paths"
                ),
                admitted=bool(result.paths),
            )
            self._document["pick_prefix_horizon"] = horizon_document
            self._write()
        if not result.paths:
            raise RuntimeError("DYNAMIC_IK_HORIZON_FAILED")
        selected = result.paths[0].steps
        if state in pick_prefix and has_full_target_set:
            grouped: dict[State, tuple[HorizonStep, ...]] = {}
            for step in selected:
                grouped.setdefault(step.waypoint.state, ())
                grouped[step.waypoint.state] += (step,)
            self._pick_horizon_steps = grouped
            return grouped[state]
        return selected

    def _plan_candidate_set(
        self,
        *,
        state: State,
        step: HorizonStep,
        current: tuple[float, ...],
        joint_target: tuple[float, ...],
    ):
        candidate_count = (
            MOVE_ABOVE_PLAN_CANDIDATE_COUNT
            if state is State.MOVE_ABOVE_OBJECT
            else 1
        )
        candidates = []
        corridor_receipts: list[dict[str, object]] = []
        last_failure = "CUP_POSE_PLAN_FAILED"
        for candidate_index in range(candidate_count):
            planned = self._planning.plan_joint_path(
                JointPlanRequest(
                    joint_names=self._ARM_JOINTS,
                    current_positions=current,
                    target_positions=joint_target,
                    velocity_scaling=self._template.velocity_scaling,
                    acceleration_scaling=self._template.acceleration_scaling,
                    planning_time_s=self._template.planning_timeout_s,
                    planning_group=self._template.planning_group,
                    tcp_link=self._template.tcp_link,
                ),
                timeout_s=self._template.planning_timeout_s + 5.0,
            )
            if planned.failure is not None or planned.trajectory is None:
                last_failure = (
                    "CUP_POSE_PLAN_FAILED"
                    if planned.failure is None
                    else planned.failure.code
                )
                self._record_planning_attempt(
                    {
                        "kind": "moveit_joint_plan",
                        "state": state.value,
                        "segment_index": step.waypoint.segment_index,
                        "candidate_index": candidate_index,
                        "candidate_count": candidate_count,
                        "accepted": False,
                        "failure_code": last_failure,
                        "joint_target_rad": list(joint_target),
                    }
                )
                continue
            self._record_planning_attempt(
                {
                    "kind": "moveit_joint_plan",
                    "state": state.value,
                    "segment_index": step.waypoint.segment_index,
                    "candidate_index": candidate_index,
                    "candidate_count": candidate_count,
                    "accepted": True,
                    "failure_code": None,
                    "joint_target_rad": list(joint_target),
                    "trajectory_sample_count": len(
                        planned.trajectory.joint_trajectory.points
                    ),
                }
            )
            corridor = validate_cartesian_corridor(
                self._ik,
                planned.trajectory,
                self._ARM_JOINTS,
                current,
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
            corridor_document = corridor.to_document()
            corridor_document.update(
                kind=(
                    "moveit_plan_candidate"
                    if candidate_count > 1
                    else "actual_moveit_cartesian_corridor"
                ),
                validation_kind="actual_moveit_cartesian_corridor",
                state=state.value,
                segment_index=step.waypoint.segment_index,
                candidate_index=candidate_index,
                candidate_count=candidate_count,
            )
            corridor_receipts.append(corridor_document)
            self._record_planning_attempt(corridor_document)
            last_failure = corridor.failure_code or "CARTESIAN_CORRIDOR_FAILED"
            if corridor.accepted:
                candidates.append(
                    (
                        cartesian_candidate_score(
                            corridor, candidate_index=candidate_index
                        ),
                        candidate_index,
                        planned,
                    )
                )
        if not candidates:
            raise RuntimeError(last_failure)
        _, selected_index, selected = min(candidates, key=lambda item: item[0])
        if candidate_count > 1:
            self._record_planning_attempt(
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
        return selected, corridor_receipts

    def _motion(self, state: State, target: PoseEvidence) -> None:
        before = self._snapshot()
        current = self._joint_state()
        motion_targets = [target]
        if state in {State.DESCEND, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE}:
            start_pose = self._ik.forward(current)
            motion_targets = [
                self._interpolate_pose(start_pose, target, step / 6.0) for step in range(1, 7)
            ]

        carried = state in {
            State.MICRO_LIFT,
            State.LIFT,
            State.MOVE_ABOVE_PLACE,
            State.DESCEND_TO_PLACE,
            State.RECOVER_LIFT_TO_SAFE_HEIGHT,
            State.RECOVER_MOVE_ABOVE_PICK,
            State.RECOVER_DESCEND_TO_PICK,
        }
        guard = SustainedConditionGuard(0.08)

        def monitor() -> None:
            value = self._snapshot()
            if value.maximum_normal_force_n > self._MAX_FORCE_N:
                raise RuntimeError("DYNAMIC_FORCE_LIMIT_EXCEEDED")
            if carried:
                guard.require(self._bilateral(value), "dynamic carry lost bilateral contact")
                if self._reject_carried_table_contact(state, self._table_contact(value)):
                    raise RuntimeError("DYNAMIC_EARLY_TABLE_CONTACT")
            elif state in {State.MOVE_ABOVE_OBJECT, State.DESCEND} and self._initial is not None:
                displacement = math.dist(
                    value.object_state.position_world,
                    self._initial.object_state.position_world,
                )
                if displacement > 0.005:
                    raise RuntimeError("DYNAMIC_PRECLOSE_CUP_MOVED")

        trajectory_points = 0
        segment_joint_targets: list[list[float]] = []
        execution_reconciliations: list[dict[str, float]] = []
        cartesian_corridor_receipts: list[dict[str, object]] = []
        joint_target = current
        resolved_pose = self._ik.forward(current)
        horizon_steps = self._motion_horizon(state, motion_targets, current)
        for segment_index, step in enumerate(horizon_steps):
            motion_target = step.waypoint.target
            joint_target = step.receipt.joint_positions_rad
            if joint_target is None:
                raise RuntimeError("DYNAMIC_IK_HORIZON_FAILED")
            resolved_pose = self._ik.forward(joint_target)
            selection_document = step.receipt.to_document()
            selection_document.update(
                kind="deterministic_ik_selection",
                selection_reason="selected complete-path minimum cumulative score",
            )
            self._record_planning_attempt(selection_document)
            planned, candidate_corridors = self._plan_candidate_set(
                state=state,
                step=step,
                current=current,
                joint_target=joint_target,
            )
            cartesian_corridor_receipts.extend(candidate_corridors)
            execution_generation = self._joint_state_generation
            executed = self._trajectory.execute(
                planned.trajectory,
                45.0,
                monitor=monitor,
            )
            if executed.status is not ActionStatus.SUCCEEDED:
                if self._is_reconcilable_control_failure(executed):
                    current = self._joint_state(after_generation=execution_generation)
                    reconciliation = self._terminal_pose_reconciliation(
                        self._ik.forward(current),
                        motion_target,
                        position_tolerance_m=self._template.position_tolerance_m,
                        orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
                        orientation_error_rad=self._ik.orientation_error_rad,
                    )
                    if reconciliation is not None:
                        reconciliation["segment_index"] = float(segment_index)
                        execution_reconciliations.append(reconciliation)
                        trajectory_points += len(planned.trajectory.joint_trajectory.points)
                        segment_joint_targets.append(list(joint_target))
                        continue
                code = (
                    executed.failure.code
                    if executed.failure is not None
                    else "DYNAMIC_EXECUTION_FAILED"
                )
                message = "" if executed.failure is None else executed.failure.message
                raise RuntimeError(f"{code}: {message}")
            trajectory_points += len(planned.trajectory.joint_trajectory.points)
            segment_joint_targets.append(list(joint_target))
            current = self._joint_state(after_generation=execution_generation)
        after = self._snapshot()
        snapshot_joint_generation = self._joint_state_generation
        current = self._joint_state(after_generation=snapshot_joint_generation)
        terminal_pose = self._ik.forward(current)
        details: dict[str, object] = {
            "target_pose": [*target.position_m, *target.orientation_xyzw],
            "resolved_joint_target_rad": list(joint_target),
            "segment_joint_targets_rad": segment_joint_targets,
            "resolved_fk_pose": [
                *resolved_pose.position_m,
                *resolved_pose.orientation_xyzw,
            ],
            "resolved_position_error_m": math.dist(resolved_pose.position_m, target.position_m),
            "resolved_orientation_error_rad": self._ik.orientation_error_rad(resolved_pose, target),
            "terminal_joint_positions_rad": list(current),
            "terminal_fk_pose": [
                *terminal_pose.position_m,
                *terminal_pose.orientation_xyzw,
            ],
            "terminal_position_error_m": math.dist(terminal_pose.position_m, target.position_m),
            "terminal_orientation_error_rad": self._ik.orientation_error_rad(terminal_pose, target),
            "terminal_joint_state_generation": self._joint_state_generation,
            "terminal_joint_state_source_stamp_ns": self._joint_state_source_stamp_ns,
            "terminal_joint_state_received_monotonic_s": (self._joint_state_received_monotonic_s),
            "trajectory_points": trajectory_points,
            "execution_reconciliations": execution_reconciliations,
            "cartesian_corridor_receipts": cartesian_corridor_receipts,
        }
        validation_failure = None
        if state is State.MICRO_LIFT:
            self._before_micro_lift = before
            lift = after.object_state.position_world[2] - before.object_state.position_world[2]
            if (
                not 0.001 <= lift <= 0.010
                or not self._bilateral(after)
                or self._table_contact(after)
            ):
                validation_failure = "DYNAMIC_MICRO_LIFT_NOT_PROVED"
            details.update(
                physical_cup_lift_m=lift,
                physical_bilateral_contact=self._bilateral(after),
                physical_table_contact=self._table_contact(after),
                validation_failure=validation_failure,
            )
        self._record(state, before, after, **details)
        if validation_failure is not None:
            raise RuntimeError(validation_failure)

    def _command_gripper(self, state: State, target: float) -> None:
        before = self._snapshot()
        result = self._gripper.command(target, 2.0, 15.0)
        if result.status is not ActionStatus.SUCCEEDED:
            code = result.failure.code if result.failure is not None else "GRIPPER_COMMAND_FAILED"
            raise RuntimeError(code)
        after = self._snapshot()
        self._record(state, before, after, target_q6_rad=target)

    def _call(self, client, request, timeout_s: float, code: str):
        if not client.wait_for_service(timeout_sec=timeout_s):
            raise RuntimeError(f"{code}_UNAVAILABLE")
        future = client.call_async(request)
        deadline = time.monotonic() + timeout_s
        while not future.done() and time.monotonic() < deadline:
            self._progress()
        if not future.done() or future.result() is None:
            raise RuntimeError(f"{code}_TIMEOUT")
        return future.result()

    def _scene_membership(self) -> tuple[list[str], dict[str, int]]:
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene

        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        response = self._call(self._get_scene, request, 5.0, "DYNAMIC_SCENE_READBACK")
        attached = [
            item.object.id for item in response.scene.robot_state.attached_collision_objects
        ]
        world = {item.id: len(item.primitives) for item in response.scene.world.collision_objects}
        return attached, world

    def _set_touch_collision(self, allowed: bool) -> None:
        from moveit_msgs.msg import PlanningScene, PlanningSceneComponents
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

        request = GetPlanningScene.Request()
        request.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
        response = self._call(self._get_scene, request, 5.0, "DYNAMIC_ACM_READBACK")
        matrix = copy.deepcopy(response.scene.allowed_collision_matrix)
        set_collision_allowed(matrix, "jaw", "plastic_cup", allowed)
        set_collision_allowed(matrix, "gripper", "plastic_cup", allowed)
        scene = PlanningScene()
        scene.is_diff = True
        scene.allowed_collision_matrix = matrix
        applied = self._call(
            self._apply_scene,
            ApplyPlanningScene.Request(scene=scene),
            5.0,
            "DYNAMIC_ACM_APPLY",
        )
        if not applied.success:
            raise RuntimeError("DYNAMIC_ACM_APPLY_FAILED")
        self._touch_collision_allowed = allowed

    def _attach(self, state: State) -> None:
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene
        from moveit_msgs.srv import ApplyPlanningScene

        before = self._snapshot()
        attached = AttachedCollisionObject()
        attached.link_name = "gripper"
        attached.object.id = "plastic_cup"
        attached.object.operation = CollisionObject.ADD
        attached.touch_links = ["gripper", "jaw"]
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [attached]
        response = self._call(
            self._apply_scene,
            ApplyPlanningScene.Request(scene=scene),
            5.0,
            "DYNAMIC_ATTACH",
        )
        if not response.success:
            raise RuntimeError("DYNAMIC_ATTACH_FAILED")
        attached_ids, world = self._scene_membership()
        if "plastic_cup" not in attached_ids:
            raise RuntimeError("DYNAMIC_ATTACH_READBACK_MISMATCH")
        self._attached = True
        if self._touch_collision_allowed:
            self._set_touch_collision(False)
        self._record(state, before, self._snapshot(), attached_ids=attached_ids, world=world)

    def _detach_or_sync(self, state: State) -> None:
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene
        from moveit_msgs.srv import ApplyPlanningScene

        before = self._snapshot()
        remove = AttachedCollisionObject()
        remove.object.id = "plastic_cup"
        remove.object.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [remove]
        scene.world.collision_objects = [
            make_cup_collision_object(
                tuple(before.object_state.position_world),
                tuple(before.object_state.orientation_xyzw),
            )
        ]
        response = self._call(
            self._apply_scene,
            ApplyPlanningScene.Request(scene=scene),
            5.0,
            "DYNAMIC_DETACH_SYNC",
        )
        if not response.success:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_FAILED")
        attached_ids, world = self._scene_membership()
        if "plastic_cup" in attached_ids or world.get("plastic_cup") != 13:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_READBACK_MISMATCH")
        self._attached = False
        self._scene_readback = {
            "attached_object_ids": attached_ids,
            "world_primitive_counts": world,
        }
        if self._touch_collision_allowed:
            self._set_touch_collision(False)
        self._record(state, before, self._snapshot(), **self._scene_readback)

    def _wait_release(self, state: State) -> None:
        before = self._snapshot()

        def released(value) -> bool:
            linear = max(abs(item) for item in value.object_state.linear_velocity_world)
            angular = max(abs(item) for item in value.object_state.angular_velocity_world)
            return (
                self._table_contact(value)
                and not value.left_fingertip_contacts
                and not value.right_fingertip_contacts
                and linear <= FINAL_MAX_LINEAR_SPEED_M_S
                and angular <= FINAL_MAX_ANGULAR_SPEED_RAD_S
            )

        after = self._wait_stable(released, 0.20, 4.0)
        self._final_samples.append(self._evidence(after))
        self._record(state, before, after)

    def _validate_final(self, state: State) -> None:
        before = self._snapshot()
        expected = compose_pose(
            self._template.place_tcp_world,
            inverse_pose(self._template.cup_to_tcp_grasp),
        )
        actual = before.object_state
        xy_error = math.dist(actual.position_world[:2], expected.values[:2])
        q = actual.orientation_xyzw
        upright = self._upright_tilt_rad(q)
        if (
            xy_error > FINAL_XY_TOLERANCE_M
            or not (
                FINAL_SUPPORT_HEIGHT_RANGE_M[0]
                <= actual.position_world[2]
                <= FINAL_SUPPORT_HEIGHT_RANGE_M[1]
            )
            or upright > FINAL_MAX_UPRIGHT_TILT_RAD
            or not self._table_contact(before)
            or before.left_fingertip_contacts
            or before.right_fingertip_contacts
        ):
            raise RuntimeError("DYNAMIC_FINAL_PLACEMENT_NOT_PROVED")
        self._record(
            state,
            before,
            before,
            expected_cup_pose_world=list(expected.values),
            final_xy_error_m=xy_error,
            final_upright_tilt_rad=upright,
        )

    def perform(self, state: State, target: PoseEvidence | None) -> ActionResult:
        try:
            if self._initial is None:
                self._initial = self._snapshot()
            if state is State.DESCEND:
                # The final approach intentionally brings the gripper and jaw into
                # contact with the cup. Keep this exception narrow and remove it
                # immediately after MoveIt owns the attached object.
                self._set_touch_collision(True)
            if target is not None:
                if state in {State.RETREAT, State.RECOVER_RETREAT}:
                    # The released cup has already been restored as a world object,
                    # while the gripper begins this motion inside its conservative
                    # collision proxy. Allow only the cup touch pair until the
                    # gripper has physically retreated, then restore normal checks.
                    self._set_touch_collision(True)
                    try:
                        self._motion(state, target)
                    finally:
                        self._set_touch_collision(False)
                else:
                    self._motion(state, target)
            elif state is State.PREPARE_OPEN_GRIPPER:
                self._command_gripper(state, self._PREOPEN_Q6)
            elif state is State.CLOSE_GRIPPER:
                self._command_gripper(state, self._CLOSE_Q6)
            elif state is State.WAIT_GRASP_STABLE:
                before = self._snapshot()
                after = self._wait_stable(self._bilateral, 0.25, 6.0)
                self._record(state, before, after)
            elif state is State.VERIFY_PHYSICAL_GRASP:
                before = self._snapshot()
                if (
                    self._before_micro_lift is None
                    or before.object_state.position_world[2]
                    - self._before_micro_lift.object_state.position_world[2]
                    < 0.001
                    or not self._bilateral(before)
                ):
                    raise RuntimeError("DYNAMIC_PHYSICAL_GRASP_NOT_PROVED")
                self._record(state, before, before)
            elif state is State.ATTACH_MOVEIT:
                self._attach(state)
            elif state in {State.DETACH_MOVEIT, State.SYNC_WORLD_OBJECT}:
                self._detach_or_sync(state)
            elif state is State.OPEN_GRIPPER:
                self._release_marker_sequence = self._snapshot().publisher_sequence
                self._command_gripper(state, self._RELEASE_Q6)
            elif state is State.WAIT_RELEASE_SETTLE:
                self._wait_release(state)
            elif state is State.VALIDATE_FINAL_PLACEMENT:
                self._validate_final(state)
            elif state is State.RECOVER_OPEN_GRIPPER:
                self._command_gripper(state, self._RELEASE_Q6)
            elif state in {State.RECOVER_DETACH_MOVEIT, State.RECOVER_SYNC_WORLD_OBJECT}:
                self._detach_or_sync(state)
            elif state is State.RECOVER_DETACH_GAZEBO:
                value = self._snapshot()
                self._record(state, value, value, simulator_constraint_calls=0)
            else:
                value = self._snapshot()
                self._record(state, value, value)
            return ActionResult(ActionStatus.SUCCEEDED)
        except Exception as error:
            code = str(error).split(":", 1)[0] or "DYNAMIC_EXECUTION_FAILED"
            self._document["last_error"] = str(error)
            self._write()
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.EXECUTION, code, str(error)),
            )

    def close(self) -> None:
        self._node.destroy_subscription(self._joint_subscription)
