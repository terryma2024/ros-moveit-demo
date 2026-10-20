"""Plan execution, the arm motion and the gripper command."""

from __future__ import annotations

import math

from so101_demo.act.teacher_endpoint import (
    DEFAULT_GRIPPER_DURATION_S,
    EXECUTION_SCHEMA_DESCEND,
    OPEN_DURATION_FIELD,
    SPEED_DURATION_FIELD,
    speed_policy_value,
)
from so101_demo.control.moveit.deterministic_horizon import descend_waypoints
from so101_demo.core.domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.dynamic_execution.common import INJECTED_EXECUTION_FAILURE, _ExecutionFailed


class MotionExecution:
    def _execute_planned(self, trajectory, state: State, monitor) -> ActionResult:
        """One `ExecuteTrajectory` goal through `MoveItExecutionClient`.

        Returns on SUCCEEDED. Otherwise raises: `TeacherStop` for a monitor stop (its own code) or a cancel that did
        not settle, `_ExecutionFailed` for a controller-originated failure (reject, abort result, timeout whose
        cancel settled), which keeps the original RECOVER_* route.
        """
        self._check_stop()
        self._refuse_plan_start_drift(trajectory)
        self._last_arm_result = None
        self._emit_phase_begin("arm")
        executed = self._trajectory.execute(
            trajectory, getattr(self, "_execute_timeout_s", 45.0), monitor=monitor)
        if (executed.status is ActionStatus.SUCCEEDED and self._teacher_run() and getattr(self, "inject_failure_at", None) is state
                and not getattr(self, "_injected_failure_fired", False)):
            # Diagnostic only: the execute really succeeded (the arm moved, the cup is held); report it as the failed result a
            # failed execute returns, once, so everything after this line is the real Teacher failure path
            self._injected_failure_fired = True
            executed = ActionResult(ActionStatus.FAILED, Failure(
                FailureCategory.EXECUTION, INJECTED_EXECUTION_FAILURE,
                f"diagnostic injection at {state.value}: the execution result was replaced by a failure"))
        if executed.status is ActionStatus.SUCCEEDED:
            self._last_arm_result = "SUCCEEDED"
            return executed
        failure = executed.failure
        code = failure.code if failure is not None else "DYNAMIC_EXECUTION_FAILED"
        message = "" if failure is None else failure.message
        settled = None if failure is None else failure.metrics.get("cancel_settled")
        if code == "MOVEIT_EXECUTION_MONITOR_ABORTED":
            self._last_arm_result = "MONITOR_ABORTED"
            reason = message.split(":", 1)[0] or code
            if settled == 0.0:
                raise self._unsettled_cancel(reason, "arm", state)
            raise RuntimeError(message or code)  # the monitor's own coded reason, e.g. DYNAMIC_CUP_FORCE_EXCEEDED
        if code == "MOVEIT_EXECUTION_TIMEOUT" and settled == 0.0:
            self._last_arm_result = "TIMED_OUT"
            raise self._unsettled_cancel(code, "arm", state)
        self._last_arm_result = ("CONTROLLER_FAILED" if code in (
            "MOVEIT_EXECUTION_FAILED", "MOVEIT_EXECUTION_REJECTED", "MOVEIT_EXECUTION_UNAVAILABLE",
            INJECTED_EXECUTION_FAILURE) else "TIMED_OUT")
        raise _ExecutionFailed(f"{code}: {message}", executed)

    def _motion(self, state: State, target: PoseEvidence) -> None:
        before = self._snapshot()
        current = self._motion_planning_start()
        motion_targets = [target]
        if state is State.DESCEND:
            self._descend_grasp_target = target
        if state in {State.DESCEND, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE}:
            start_pose = self._ik.forward(current)
            motion_targets = [
                self._interpolate_pose(start_pose, target, step / 6.0) for step in range(1, 7)
            ]
            final_distance_m = self._descend_final_distance_m() if state is State.DESCEND else None
            if final_distance_m is not None:  # schema 5: the approach stage, then the final stage
                motion_targets = [
                    waypoint.target
                    for waypoint in descend_waypoints(self._interpolate_pose, start_pose, target, final_distance_m)
                ]

        monitor = self._motion_monitor(state)

        trajectory_points = 0
        segment_joint_targets: list[list[float]] = []
        execution_reconciliations: list[dict[str, float]] = []
        cartesian_corridor_receipts: list[dict[str, object]] = []
        joint_target = current
        resolved_pose = self._ik.forward(current)
        horizon_steps = self._motion_horizon(state, motion_targets, current)
        for segment_index, step in enumerate(horizon_steps):
            self._check_stop()  # no new goal is planned or sent after a stop
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
            try:
                self._execute_planned(planned.trajectory, state, monitor)
            except _ExecutionFailed as failed:
                # The trajectory client has already cancelled and settled the goal. Persist the
                # triggering atomic sample before recovery can replace it with a later snapshot.
                if "monitor_violation" in self._document:
                    self._write()
                if self._is_reconcilable_control_failure(failed.result):
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
                raise
            except RuntimeError:
                if "monitor_violation" in self._document:
                    self._write()
                raise
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
        if state is State.MICRO_LIFT:
            self._before_micro_lift = before
            lift = after.object_state.position_world[2] - before.object_state.position_world[2]
            bilateral = self._bilateral(after)
            table_contact = self._table_contact(after)
            if not 0.001 <= lift <= 0.010 or not bilateral or table_contact:
                # Audit-only (D3): micro-lift verification is process quality; the endpoint decides the task result.
                self._record_process_diagnostic(
                    "DYNAMIC_MICRO_LIFT_NOT_PROVED", state, sample=after,
                    facts={"physical_cup_lift_m": lift, "bilateral_contact": bilateral,
                           "table_contact": table_contact})
            details.update(
                physical_cup_lift_m=lift,
                physical_bilateral_contact=bilateral,
                physical_table_contact=table_contact,
                validation_failure=None,
            )
        self._record(state, before, after, **details)

    def _gripper_duration_s(self, state: State) -> float:
        """The gripper trajectory duration: 2.0 s for every command, except with frozen inputs PREPARE_OPEN_GRIPPER, which takes the
        schema 4 Teacher policy value, and OPEN_GRIPPER, which takes the schema 5 value (an older policy has none: 2.0 s).
        CLOSE_GRIPPER and RECOVER_OPEN_GRIPPER always keep 2.0 s."""

        if getattr(self, "_execution_snapshot_root", None) is None:
            return DEFAULT_GRIPPER_DURATION_S
        policy = getattr(self, "_execution_policy", None)
        if state is State.PREPARE_OPEN_GRIPPER:
            return speed_policy_value(policy, SPEED_DURATION_FIELD, DEFAULT_GRIPPER_DURATION_S)
        if state is State.OPEN_GRIPPER:
            return speed_policy_value(policy, OPEN_DURATION_FIELD, DEFAULT_GRIPPER_DURATION_S, since_schema=EXECUTION_SCHEMA_DESCEND)
        return DEFAULT_GRIPPER_DURATION_S

    def _command_gripper(self, state: State, target: float, *, before=None) -> None:
        self._check_stop()  # no new goal after a stop
        if before is None:
            before = self._snapshot()
        timeout_s = getattr(self, "_gripper_timeout_s", 15.0)
        duration_s = self._gripper_duration_s(state)
        # The gripper goal has the arm goal's stop path: the same monitor, a raise cancels the goal.
        monitor = self._motion_monitor(state)
        if state in (State.OPEN_GRIPPER, State.RECOVER_OPEN_GRIPPER) and not self._teacher_run():
            def before_dispatch():
                self._check_selected_release_freshness(before)
                self._emit_phase_begin("gripper")

            result = self._gripper.command(target, duration_s, timeout_s, before_dispatch=before_dispatch, monitor=monitor)
        else:
            result = self._gripper.command(
                target, duration_s, timeout_s, before_dispatch=lambda: self._emit_phase_begin("gripper"), monitor=monitor)
        if result.status is not ActionStatus.SUCCEEDED:
            failure = result.failure
            code = failure.code if failure is not None else "GRIPPER_COMMAND_FAILED"
            settled = None if failure is None else failure.metrics.get("cancel_settled")
            if code == "GRIPPER_MONITOR_ABORTED":
                reason = failure.message.split(":", 1)[0] or code
                if settled == 0.0:
                    raise self._unsettled_cancel(reason, "gripper", state)
                raise RuntimeError(failure.message or code)  # the monitor's own coded reason
            if code == "GRIPPER_RESULT_TIMEOUT" and settled == 0.0:
                raise self._unsettled_cancel(code, "gripper", state)
            raise RuntimeError(code)
        after = self._snapshot()
        self._record(state, before, after, target_q6_rad=target)

    def _release_bounds(self):
        """(state age bound, support distance bound) for the release preflight.

        The age is the Teacher execution policy's `state_max_age_s`, not the ACT RGB-synchronisation age: the
        support-before-open check is execution protection and keeps no dependence on the 100 ms data contract.
        """
        from so101_demo.act.contracts import finite

        try:
            age = finite(self._execution_policy["state_max_age_s"])
            distance = finite(self._release_runtime_policy["safety_release"]["support_distance_max_m"])
            if age <= 0 or distance <= 0:
                raise ValueError("release bounds")
            return age, distance
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("DYNAMIC_RELEASE_POLICY_INVALID") from error

    def _release_scope(self):
        """(session, reset epoch, attempt): the scope of one release. There is no lease token."""
        attempt = getattr(self, "_attempt_id", None)
        if (not isinstance(self._session_id, str) or not self._session_id
                or type(self._expected_reset_epoch) is not int
                or not isinstance(attempt, str) or not attempt):
            raise RuntimeError("DYNAMIC_RELEASE_SCOPE_REQUIRED")
        return (self._session_id, self._expected_reset_epoch, attempt)

    def _close_target_q6(self) -> float:
        """The CLOSE_GRIPPER target: the frozen Teacher policy value with frozen inputs, else the original constant."""

        if getattr(self, "_execution_snapshot_root", None) is None:
            return self._CLOSE_Q6
        policy = getattr(self, "_execution_policy", None)
        if policy is None or "gripper_close_target_rad" not in policy:
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: gripper_close_target_rad")
        return float(policy["gripper_close_target_rad"])
