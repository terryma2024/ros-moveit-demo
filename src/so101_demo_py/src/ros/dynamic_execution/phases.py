"""Phase bookkeeping, place targets and the state dispatch."""

from __future__ import annotations

import math
from pathlib import Path
import time

from so101_demo.core.domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.dynamic_execution.common import _WINDOW_TOLERANCE_S, _mark_phase, _mark_place_side


class PhaseSequencing:
    def _sim_time_ns(self):
        try:
            return int(self._node.get_clock().now().nanoseconds)
        except Exception:
            return None

    def _phase_open(self, state: State, target) -> None:
        self._phase_state, self._phase_begun = state, False
        if target is None and state not in self._GOAL_STATES:
            self._emit_phase_begin(None)

    def _summary_phase(self, kind, state, status=None, code=None) -> None:
        """Teacher run: the phase bounds for the process summary (simulation time, the same instant the stream event carries)."""
        summary = getattr(self, "_process_summary", None)
        if summary is None:
            return
        nanoseconds = self._sim_time_ns()
        seconds = None if nanoseconds is None else nanoseconds * 1e-9
        if kind == "begin":
            summary.phase_begin(state.value, seconds)
        else:
            summary.phase_finish(state.value, seconds, status, code)

    def _emit_phase_begin(self, goal_kind) -> None:
        """Publish the pending `phase_begin`, once per state. Never raises."""
        try:
            state = getattr(self, "_phase_state", None)
            if state is None or getattr(self, "_phase_begun", True):
                return
            self._phase_begun = True
            self._stream_emit("phase_begin", {
                "state": state.value, "sim_time_ns": self._sim_time_ns(), "monotonic_ns": time.monotonic_ns(),
                "goal_sent": goal_kind is not None, "goal_kind": goal_kind})
            self._summary_phase("begin", state)
        except Exception:
            pass

    def _phase_finish(self, status: str, code=None) -> None:
        try:
            state = getattr(self, "_phase_state", None)
            if state is None:
                return
            self._emit_phase_begin(None)  # a state that never sent a goal still begins before it finishes
            self._stream_emit("phase_finish", {
                "state": state.value, "sim_time_ns": self._sim_time_ns(), "monotonic_ns": time.monotonic_ns(),
                "status": status, "code": code})
            self._summary_phase("finish", state, status, code)
        except Exception:
            pass
        finally:
            self._phase_state = None

    def perform(self, state: State, target: PoseEvidence | None) -> ActionResult:
        if getattr(self, '_first_state_marked', False):
            return self._perform_state(state, target)
        self._first_state_marked = True
        _mark_phase('runner.first_state.begin')
        try:
            return self._perform_state(state, target)
        finally:
            _mark_phase('runner.first_state.end')

    def _fixed_dwell(self, duration_s: float):
        """(first snapshot, last snapshot) of a dwell of `duration_s` of simulation time. No predicate: the wait is a fixed time."""
        before = after = self._snapshot()
        deadline = time.monotonic() + max(10.0 * duration_s, 5.0)
        while after.simulation_time_s - before.simulation_time_s < duration_s:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"TEACHER_DWELL_TIMEOUT: simulation time advanced "
                                   f"{after.simulation_time_s - before.simulation_time_s:.3f} s of {duration_s} s")
            after = self._snapshot()
        return before, after

    def _note_pose(self, label: str, value, **facts) -> None:
        """Teacher run: the cup (simulator truth) and the TCP (forward kinematics) at a named instant, for slip and release telemetry."""
        summary = getattr(self, "_process_summary", None)
        if summary is None:
            return
        try:
            tcp = self._ik.forward(tuple(self._positions[name] for name in self._ARM_JOINTS))
            state = value.object_state
            summary.note_pose(label, time_s=value.simulation_time_s, cup_position=state.position_world,
                              cup_quaternion=state.orientation_xyzw, tcp_position=tcp.position_m,
                              tcp_quaternion=tcp.orientation_xyzw, **facts)
        except Exception as error:  # noqa: BLE001 - telemetry never fails the Teacher
            summary.note_incomplete(f"POSE_UNAVAILABLE:{label}:{type(error).__name__}")

    def _wait_arm_stopped(self) -> None:
        """Release sequence step 1 (design 5a): at most `arm_stop_wait_s` for every arm joint to be at most `arm_stop_velocity_rad_s`
        on a fresh joint state. An execution precondition, not a safety proof: a timeout ends the attempt (``TEACHER_ARM_NOT_STOPPED``)."""
        policy = self._execution_policy
        limit, wait_s, max_age = (float(policy["arm_stop_velocity_rad_s"]), float(policy["arm_stop_wait_s"]),
                                  float(policy["state_max_age_s"]))
        clock = self._monotonic
        deadline = clock() + wait_s
        while True:
            received = getattr(self, "_joint_state_received_monotonic_s", None)
            velocities = getattr(self, "_joint_velocities", {})
            fresh = received is not None and 0.0 <= clock() - received <= max_age
            if fresh and all(isinstance(velocities.get(name), (int, float)) and math.isfinite(velocities[name])
                             and abs(velocities[name]) <= limit for name in self._ARM_JOINTS):
                return
            if clock() >= deadline:
                raise RuntimeError(f"TEACHER_ARM_NOT_STOPPED: the arm joints did not reach {limit} rad/s within {wait_s} s")
            self._wait_progress()

    def _place_target(self, state: State, target):
        """The DESCEND_TO_PLACE target; every other target is untouched.

        With frozen inputs (the Teacher) the tilt-compensated place height (``core.place_height``) is computed from the cup tilt and
        the grasp offset measured on the evidence now. Without them a general run descends by the general policy's
        ``place_descend_offset_m`` below the policy place pose. A Teacher run without frozen inputs keeps the pose. Called from
        ``_perform_state`` under ``_safety_state = DESCEND_TO_PLACE`` and before ``_phase_open``."""

        if state is not State.DESCEND_TO_PLACE or target is None:
            return target
        if getattr(self, "_execution_snapshot_root", None) is None:
            policy = getattr(self, "_execution_policy", None)
            if self._teacher_run() or policy is None:
                return target
            x, y, z = target.position_m
            return PoseEvidence((x, y, z + float(policy["place_descend_offset_m"])), target.orientation_xyzw)
        policy = getattr(self, "_execution_policy", None)
        if policy is None or not policy.get("place_height_mode"):
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: place_height_mode")
        return self._teacher_place_target(target, policy)

    def _place_geometry(self):
        from so101_demo.core.place_height import cup_geometry_from_scene

        geometry = getattr(self, "_place_geometry_value", None)
        if geometry is None:
            scene = getattr(self, "_execution_scene_path", "assets/mujoco/act/scene.xml")
            geometry = cup_geometry_from_scene(Path(self._execution_snapshot_root) / scene)
            self._place_geometry_value = geometry
        return geometry

    def _measure_place_height(self) -> tuple[float, float]:
        """(tilt rad, grasp offset m) of the held cup, from a stable window of fresh evidence: at least 100 ms of simulation whose tilt
        range stays under 0.05 deg, within 1 s (else TEACHER_PLACE_TILT_UNSTABLE). ``k`` is the actual TCP height (forward
        kinematics of the actual joints, sag included) above the cup origin at the end of the window."""

        from so101_demo.core.place_height import (
            STABILITY_RANGE_RAD,
            STABILITY_TIMEOUT_S,
            STABILITY_WINDOW_S,
            TILT_UNSTABLE,
            PlaceHeightRefused,
        )

        window: list[tuple[float, float, object]] = []
        last_sequence = -1
        seen: list[tuple[float, float]] = []
        widest_span_s = 0.0
        deadline = time.monotonic() + STABILITY_TIMEOUT_S
        while time.monotonic() < deadline:
            value = self._snapshot()
            if value.publisher_sequence == last_sequence:
                continue
            last_sequence = value.publisher_sequence
            self._enforce_safety(getattr(self, "_safety_state", None), value)
            now_s = value.simulation_time_s
            tilt = self._upright_tilt_rad(value.object_state.orientation_xyzw)
            seen.append((now_s, tilt))
            window.append((now_s, tilt, value))
            # The window is the newest samples that cover at least STABILITY_WINDOW_S: drop the oldest while the next one is still
            # old enough to start such a window. The evidence cadence (12 ms live) need not divide 100 ms, so a window that is cut
            # back to at most 100 ms (the first version) never reaches it: live it stalled at 96 ms and every run refused.
            while len(window) >= 2 and now_s - window[1][0] >= STABILITY_WINDOW_S - _WINDOW_TOLERANCE_S:
                window.pop(0)
            span_s = now_s - window[0][0]
            widest_span_s = max(widest_span_s, span_s)
            if span_s >= STABILITY_WINDOW_S - _WINDOW_TOLERANCE_S:
                tilts = [item[1] for item in window]
                if max(tilts) - min(tilts) < STABILITY_RANGE_RAD:
                    cup_z = value.object_state.position_world[2]
                    self._require_fresh_joint_state()
                    tcp_z = self._ik.forward(self._motion_planning_start()).position_m[2]
                    self._require_fresh_joint_state()
                    tilts.sort()
                    return tilts[len(tilts) // 2], tcp_z - cup_z
        tilts_seen = [item[1] for item in seen]
        latest = [item[1] for item in window]
        raise PlaceHeightRefused(
            TILT_UNSTABLE,
            f"no {STABILITY_WINDOW_S * 1000:.0f} ms window with a tilt range under {math.degrees(STABILITY_RANGE_RAD):.2f} deg "
            f"within {STABILITY_TIMEOUT_S:.0f} s; samples {len(seen)}"
            + (f", simulation span {seen[-1][0] - seen[0][0]:.3f} s, tilt range {math.degrees(max(tilts_seen) - min(tilts_seen)):.4f} deg, "
               f"latest window {len(window)} samples over {window[-1][0] - window[0][0]:.3f} s with range "
               f"{math.degrees(max(latest) - min(latest)):.4f} deg, widest window {widest_span_s:.3f} s" if seen else ", none received"))

    def _perform_state(self, state: State, target: PoseEvidence | None) -> ActionResult:
        try:
            self._check_stop()  # the state machine never starts a new state, hence a new goal, after a stop
            self._safety_state = state
            _mark_place_side(state, "place_target.begin")
            target = self._place_target(state, target)
            _mark_place_side(state, "place_target.end")
            if getattr(self, "_initial", None) is None and not getattr(self, "_teacher_start_attempted", False):
                # The Teacher's own start observation: read from its world observer after reset and before the first
                # arm or gripper command, independent of the recorder, the capture and the data side.
                self._teacher_start_attempted = True
                started = self._capture_teacher_start()
                if started is not None:
                    self._initial = started
            self._scene_state_value = state.value
            self._phase_open(state, target)
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
                    if state is State.DESCEND_TO_PLACE and self._teacher_run():
                        self._wait_arm_stopped()
            elif self._teacher_run() and state in (State.WAIT_GRASP_STABLE, State.OPEN_GRIPPER, State.WAIT_RELEASE_SETTLE):
                self._perform_teacher_state(state)
            elif state is State.PREPARE_OPEN_GRIPPER:
                # item 18b (schema 4 only, otherwise a no-op): the pick-prefix IK horizon computes while the gripper opens
                self._start_pick_horizon_precompute()
                self._command_gripper(state, self._PREOPEN_Q6)
            elif state is State.CLOSE_GRIPPER:
                self._command_gripper(state, self._close_target_q6())
            elif state is State.WAIT_GRASP_STABLE:
                before = self._snapshot()
                try:
                    after = self._wait_stable(self._bilateral, 0.25, 6.0)
                except RuntimeError as error:
                    if str(error) != "DYNAMIC_STABLE_STATE_TIMEOUT":
                        raise
                    # Audit-only (D3): an unstable grasp is a diagnostic, the endpoint decides the task result.
                    after = self._snapshot()
                    self._record_process_diagnostic(
                        "DYNAMIC_STABLE_STATE_TIMEOUT", state, sample=after,
                        facts={"window_s": 0.25, "timeout_s": 6.0})
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
                    # Audit-only (D3): the transition proceeds to ATTACH_MOVEIT.
                    lift = (None if self._before_micro_lift is None else
                            before.object_state.position_world[2]
                            - self._before_micro_lift.object_state.position_world[2])
                    self._record_process_diagnostic(
                        "DYNAMIC_PHYSICAL_GRASP_NOT_PROVED", state, sample=before,
                        facts={"physical_cup_lift_m": lift, "bilateral_contact": self._bilateral(before)})
                self._record(state, before, before)
            elif state is State.ATTACH_MOVEIT:
                self._attach(state)
            elif state in {State.DETACH_MOVEIT, State.SYNC_WORLD_OBJECT}:
                self._detach_or_sync(state)
            elif state is State.OPEN_GRIPPER:
                self._open_supported_gripper(state)
            elif state is State.WAIT_RELEASE_SETTLE:
                self._wait_release(state)
            elif state is State.VALIDATE_FINAL_PLACEMENT:
                self._validate_final(state)
            elif state is State.RECOVER_OPEN_GRIPPER:
                self._open_supported_gripper(state)
            elif state in {State.RECOVER_DETACH_MOVEIT, State.RECOVER_SYNC_WORLD_OBJECT}:
                self._detach_or_sync(state)
            elif state is State.RECOVER_DETACH_GAZEBO:
                value = self._snapshot()
                self._record(state, value, value, simulator_constraint_calls=0)
            else:
                value = self._snapshot()
                self._record(state, value, value)
            self._phase_finish("SUCCEEDED")
            return ActionResult(ActionStatus.SUCCEEDED)
        except Exception as error:
            code, message = self._failure_code(error)
            self._document["last_error"] = message
            self._phase_finish("FAILED", code)
            self._write()
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.EXECUTION, code, message),
            )
