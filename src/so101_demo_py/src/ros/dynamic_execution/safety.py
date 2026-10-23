"""Safety monitoring and enforcement during a motion."""

from __future__ import annotations

import math
import time

from so101_demo.application.staged_approach import maximum_joint_error
from so101_demo.control.trajectory.executor import (
    SustainedConditionGuard,
)
from so101_demo.core.domain import ActionResult, ActionStatus, State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.dynamic_execution.common import (
    _DEFAULT_STATE_MAX_AGE_S,
    _DEFAULT_STATE_UNAVAILABLE_STOP_S,
    _PLAN_START_DRIFT_MAX_RAD,
    _evidence_is_finite,
)
from so101_demo.ros.teacher_safety import evaluate_cup_contacts
from so101_demo.ros.teacher_stop import TeacherStop


class MotionSafety:
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
            self._enforce_safety(getattr(self, "_safety_state", None), value)
            healthy = bool(predicate(value)) and value.maximum_normal_force_n <= self._MAX_FORCE_N
            now = time.monotonic()
            started = started if healthy and started is not None else (now if healthy else None)
            latest = value
            if started is not None and now - started >= duration_s:
                return latest
        raise RuntimeError("DYNAMIC_STABLE_STATE_TIMEOUT")

    def _monitor_sample(self):
        """The latest world sample for the monitor, read without blocking, or None while the state is unavailable.

        Unlike `_snapshot` this never waits and never spins: `executor.execute` has just called `progress()`. The
        safety checks that need the sample count as unavailable when the newest evidence or joint state is older than
        `state_max_age_s`. (A truncated sample never reaches this point in the general runtime, where the observer rejects it, and in a Teacher run it is accepted:
        its cup state is valid and the contact lists are only telemetry.) Unavailability longer than `state_unavailable_stop_s` is a
        stop. The identity checks of `_snapshot` (session, pause, reset epoch) apply to the latest sample.
        """
        from so101_demo.backends.mujoco.observer import EvidenceStale

        policy = getattr(self, "_execution_policy", None) or {}
        max_age = policy.get("state_max_age_s", _DEFAULT_STATE_MAX_AGE_S)
        stop_after = policy.get("state_unavailable_stop_s", _DEFAULT_STATE_UNAVAILABLE_STOP_S)
        now = self._monotonic()
        try:
            value = self.observer.snapshot_with_receipt().evidence
        except EvidenceStale:
            value = None
        joint_received = getattr(self, "_joint_state_received_monotonic_s", None)
        joint_fresh = joint_received is not None and 0.0 <= now - joint_received <= max_age
        if value is None or not joint_fresh:
            since = getattr(self, "_unavailable_since", None)
            if since is None:
                since = self._unavailable_since = now
            if now - since > stop_after:
                # a Teacher run splits the one code: a silent joint state cannot be commanded blind, a silent world stream is a broken simulator
                code = "DYNAMIC_STATE_UNAVAILABLE_STOP"
                if self._teacher_run():
                    code = "TEACHER_JOINT_STATE_UNAVAILABLE" if not joint_fresh else "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE"
                raise TeacherStop(code, f"necessary state unavailable for {now - since:.3f}s (limit {stop_after}s)")
            return None
        self._unavailable_since = None
        teacher_run = self._teacher_run()
        if value.simulation_session_id != self._session_id:
            raise TeacherStop("SIM_INTEGRITY_SESSION_MISMATCH" if teacher_run else "DYNAMIC_SESSION_MISMATCH")
        mismatch = "SIM_INTEGRITY_RESET_EPOCH_MISMATCH" if teacher_run else "DYNAMIC_RESET_EPOCH_MISMATCH"
        if value.reset_epoch != self._expected_reset_epoch:
            raise TeacherStop(mismatch, self._identity_detail(value))
        if value.paused:
            # the parent's inference hold is an owned, short pause of the expected epoch: the sample is unavailable while it lasts
            since = getattr(self, "_paused_since", None)
            if since is None:
                since = self._paused_since = now
            if now - since > stop_after:
                raise TeacherStop(mismatch, self._identity_detail(value))
            return None
        self._paused_since = None
        if teacher_run and not _evidence_is_finite(value):
            raise TeacherStop("SIM_INTEGRITY_NON_FINITE_STATE")
        return value

    def _enforce_safety(self, state, value) -> None:
        """The execution protections that stop the robot, on one fresh sample: raises `TeacherStop`.

        1. the original maximum single-contact force (11.60 N);
        2. with the frozen contact policy: summed cup force and fingertip compression (same limits as the broker);
        3. with the robot contact watch: a collision pair outside the cup process pairs.
        Everything else the broker checked about the process (hold, stability, contact timing) stays audit-only.

        Teacher run (design section 3): none of these stops the Teacher. Force, compression and collisions are process telemetry
        (`teacher_process_summary`); the identity and availability checks stay in `_monitor_sample` and `_snapshot`.
        """
        if self._teacher_run():
            return
        if value.maximum_normal_force_n > self._MAX_FORCE_N:
            self._record_monitor_violation(state or State.IDLE, "DYNAMIC_FORCE_LIMIT_EXCEEDED", value)
            raise TeacherStop("DYNAMIC_FORCE_LIMIT_EXCEEDED")
        limits = getattr(self, "_safety_limits", None)
        plugin = getattr(self, "_physics_hazard_watch", None)
        if plugin is not None and plugin.limit_code is not None:
            self._enforce_step_limit(state, plugin)
        if limits is not None:
            verdict = evaluate_cup_contacts(value, limits)
            if verdict.code is not None:
                self._record_monitor_violation(state or State.IDLE, verdict.code, value)
                raise TeacherStop(
                    verdict.code,
                    f"summed force {verdict.summed_force_n:.6f} N (limit {limits.maximum_safe_force_n:.6f}), "
                    f"compression {verdict.compression_m:.9f} m (limit {limits.maximum_compression_distance_m:.9f})")
        watch = getattr(self, "_collision_watch", None)
        if watch is not None and watch.hazard is not None:
            raise TeacherStop(watch.hazard, watch.detail)
        if plugin is not None and plugin.hazard is not None:
            raise TeacherStop(plugin.hazard, plugin.detail)

    def _enforce_step_limit(self, state, plugin) -> None:
        """The same frozen rule evaluated on every 500 Hz physics step of the chunk stream (C3a)."""
        self._record_per_step_violation(state or State.IDLE, plugin)
        raise TeacherStop(plugin.limit_code, plugin.limit_detail)

    def _step_evidence_available(self, plugin, baseline_gaps: int) -> None:
        """P4/P9 for the per-step stream: a gap since the goal began, or silence beyond the bound, is a stop."""

        if plugin is None or plugin.limits is None or self._teacher_run():
            return
        if plugin.gaps > baseline_gaps:
            raise TeacherStop("DYNAMIC_STATE_UNAVAILABLE_STOP", "per-step physics evidence gap: " + plugin.gap_detail)
        policy = getattr(self, "_execution_policy", None) or {}
        now = self._monotonic()
        last = plugin.last_chunk_monotonic_s
        if last is None:
            last = plugin.armed_monotonic_s
        silent = 0.0 if last is None else now - last
        if silent > policy.get("state_unavailable_stop_s", _DEFAULT_STATE_UNAVAILABLE_STOP_S):
            raise TeacherStop(
                "DYNAMIC_STATE_UNAVAILABLE_STOP", f"per-step physics evidence silent for {silent:.3f}s")

    def _motion_monitor(self, state: State):
        """Per-trajectory monitor, also the gripper's. It raises (and the client cancels the goal) for: a stop flag,
        state unavailable too long and an identity change. The general runtime also stops on the force limits and a collision
        (`_enforce_safety`); in a Teacher run those are telemetry and the monitor never stops for them. Every process check is audit-only (D3)."""

        carried = state in {
            State.MICRO_LIFT,
            State.LIFT,
            State.MOVE_ABOVE_PLACE,
            State.DESCEND_TO_PLACE,
            State.RECOVER_LIFT_TO_SAFE_HEIGHT,
            State.RECOVER_MOVE_ABOVE_PICK,
            State.RECOVER_DESCEND_TO_PICK,
        }
        guard = SustainedConditionGuard(0.08, clock=getattr(self, "_monotonic", time.monotonic))
        step_watch = getattr(self, "_physics_hazard_watch", None)
        goal_gaps = []   # the gap count when the goal's first monitor call runs (after its first spin drained any backlog)

        def monitor() -> None:
            self._check_stop()
            if step_watch is not None:
                if not goal_gaps:
                    goal_gaps.append(step_watch.gaps)
                if not self._teacher_run():   # Teacher run: the per-step stream is telemetry (gaps and silence mark the summary incomplete)
                    if step_watch.limit_code is not None:
                        self._enforce_step_limit(state, step_watch)
                    self._step_evidence_available(step_watch, goal_gaps[0])
            value = self._monitor_sample()
            if value is None:
                return
            self._enforce_safety(state, value)
            if carried:
                try:
                    guard.require(self._bilateral(value), "dynamic carry lost bilateral contact")
                except RuntimeError as lost:
                    self._record_process_diagnostic(
                        "DYNAMIC_CARRY_BILATERAL_LOST", state, sample=value, message=str(lost))
                if self._reject_carried_table_contact(state, self._table_contact(value)):
                    self._record_process_diagnostic("DYNAMIC_EARLY_TABLE_CONTACT", state, sample=value)
            elif state in {State.MOVE_ABOVE_OBJECT, State.DESCEND} and self._initial is not None:
                displacement = math.dist(
                    value.object_state.position_world,
                    self._initial.object_state.position_world,
                )
                if displacement > 0.005:
                    self._record_process_diagnostic(
                        "DYNAMIC_PRECLOSE_CUP_MOVED", state, sample=value, displacement_m=displacement)

        return monitor

    def _unsettled_cancel(self, reason: str, goal: str, state) -> TeacherStop:
        """A cancel that did not settle within its bound ends the run; the worker then confirms and cancels every
        goal (`cancel_and_confirm_parallel_goals`)."""
        self._document["cancel_unsettled"] = {
            "reason": reason, "goal": goal, "state": None if state is None else state.value}
        try:
            self._write()
        except Exception:
            pass
        return TeacherStop("TEACHER_CANCEL_UNSETTLED", reason)

    def _refuse_plan_start_drift(self, trajectory) -> None:
        """Refuse a plan whose first point is more than 0.01 rad from the measured arm joints (no goal is sent)."""
        try:
            names = list(trajectory.joint_trajectory.joint_names)
            first = dict(zip(names, trajectory.joint_trajectory.points[0].positions, strict=True))
            start = tuple(float(first[name]) for name in self._ARM_JOINTS)
            handoff = tuple(float(self._positions[name]) for name in self._ARM_JOINTS)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("DYNAMIC_PLAN_START_DRIFT: start state unavailable") from error
        drift = maximum_joint_error(handoff, start)
        if drift > _PLAN_START_DRIFT_MAX_RAD:
            raise RuntimeError(
                f"DYNAMIC_PLAN_START_DRIFT: {drift:.6f} rad exceeds {_PLAN_START_DRIFT_MAX_RAD} rad")
