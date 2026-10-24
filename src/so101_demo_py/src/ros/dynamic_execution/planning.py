"""Motion horizon and candidate set planning."""

from __future__ import annotations

import math
import threading
import time
from types import SimpleNamespace

from so101_demo.act.teacher_endpoint import (
    DESCEND_DISTANCE_FIELD,
    DESCEND_SCALING_FIELDS,
    EXECUTION_SCHEMA_DESCEND,
    EXECUTION_KIND,
    EXECUTION_SCHEMA_SPEED,
    speed_policy_value,
)
from so101_demo.control.moveit.deterministic_horizon import (
    MOVE_ABOVE_PLAN_CANDIDATE_COUNT,
    HorizonStep,
    HorizonWaypoint,
    cartesian_candidate_score,
    descend_waypoints,
    solve_horizon,
    solve_pick_prefix_horizon,
    validate_cartesian_corridor,
)
from so101_demo.control.moveit.planning import JointPlanRequest
from so101_demo.core.domain import State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.dynamic_execution.common import _mark_place_side
from so101_demo.ros.task_reachability import _compute_while_progressing


#: The largest joint difference (rad, any arm joint) between the state a pick-prefix horizon precompute started from and the state at
#: the first MOVE_ABOVE_OBJECT goal for which the precomputed horizon is still used. The arm settles slowly after reset: the sealed
#: EXP-625 episodes (109) moved at most 2.8e-6 rad between the begin of PREPARE_OPEN_GRIPPER and the goal, which moved the selected
#: joint targets by at most 4.0e-6 rad with the same selected path. Beyond the tolerance the horizon is computed again from the state
#: at the goal, exactly as it was without a precompute.
PICK_HORIZON_REUSE_MAX_START_DELTA_RAD = 1e-5


class MotionPlanning:
    #: the schema 4 Teacher policy keys (velocity, acceleration) of the free-space states that have their own MoveIt scaling
    _SPEED_SCALING_KEYS = {
        State.MOVE_ABOVE_OBJECT: ("move_above_object_velocity_scaling", "move_above_object_acceleration_scaling"),
        State.RETREAT: ("retreat_velocity_scaling", "retreat_acceleration_scaling"),
    }

    def _pick_horizon_precompute_enabled(self) -> bool:
        """A Teacher run with frozen inputs, a schema 4 Teacher policy and the full pick target set."""

        policy = getattr(self, "_execution_policy", None) or {}
        return bool(
            getattr(self, "_execution_snapshot_root", None) is not None
            and self._teacher_run()
            and hasattr(self, "_targets")
            and type(policy.get("schema_version")) is int
            and policy["schema_version"] >= EXECUTION_SCHEMA_SPEED
        )

    def _descend_final_distance_m(self):
        """Schema 5, frozen inputs: the distance above the grasp pose at which the DESCEND approach stage ends, else None (the six
        interpolated DESCEND segments of schema 3 and 4, and of every run without frozen inputs)."""

        policy = getattr(self, "_execution_policy", None)
        if (getattr(self, "_execution_snapshot_root", None) is None or policy is None
                or policy.get("kind") != EXECUTION_KIND
                or type(policy.get("schema_version")) is not int or policy["schema_version"] < EXECUTION_SCHEMA_DESCEND):
            return None
        return speed_policy_value(policy, DESCEND_DISTANCE_FIELD, 0.0, since_schema=EXECUTION_SCHEMA_DESCEND)

    def _start_pick_horizon_precompute(self) -> None:
        """Item 18b: compute the pick-prefix IK horizon in a worker thread from the joint state of now (PREPARE_OPEN_GRIPPER), so the
        first MOVE_ABOVE_OBJECT goal does not wait for it. Never raises: a precompute that cannot start leaves today's behaviour.

        The worker only calls the pure `solve_pick_prefix_horizon` on the IK solver, which keeps no per-solve state, and the main
        thread does not use the solver until it takes the result."""

        if not self._pick_horizon_precompute_enabled():
            return
        try:
            start = tuple(float(value) for value in self._joint_state())
            ik, targets, interpolate = self._ik, self._targets, self._interpolate_pose
            position_tolerance_m = self._template.position_tolerance_m
            orientation_tolerance_rad = max(self._template.orientation_tolerance_rad)
            descend_final_distance_m = self._descend_final_distance_m()
        except Exception as error:  # noqa: BLE001 - an optimisation, never a Teacher failure
            self._document["pick_prefix_precompute"] = {"status": "NOT_STARTED", "error": f"{type(error).__name__}: {error}"}
            return
        job = SimpleNamespace(start=start, outcome=[], began=time.monotonic(), thread=None)

        def work() -> None:
            try:
                result = solve_pick_prefix_horizon(
                    ik, start, targets, interpolate, position_tolerance_m=position_tolerance_m,
                    orientation_tolerance_rad=orientation_tolerance_rad, beam_width=3,
                    descend_final_distance_m=descend_final_distance_m)
                job.outcome.append((True, result, time.monotonic()))
            except BaseException as error:  # noqa: BLE001 - reported, then the goal computes it itself
                job.outcome.append((False, error, time.monotonic()))

        job.thread = threading.Thread(target=work, daemon=True, name="pick-horizon-precompute")
        self._pick_horizon_precompute = job
        job.thread.start()

    def _take_pick_horizon_precompute(self, current: tuple[float, ...]):
        """The precomputed horizon when its start state is within `PICK_HORIZON_REUSE_MAX_START_DELTA_RAD` of ``current``, else None
        (the caller computes it from ``current``). Waits for a worker that is still running, spinning like any long computation."""

        job = self.__dict__.pop("_pick_horizon_precompute", None)
        if job is None:
            return None
        waiting_from = time.monotonic()
        try:
            while job.thread.is_alive():
                self._progress()
                time.sleep(0.001)
        except BaseException:
            job.thread.join()
            raise
        job.thread.join()
        report = {"started_state_rad": list(job.start), "wait_s": time.monotonic() - waiting_from}
        succeeded, value, finished = job.outcome[0]
        report["compute_s"] = finished - job.began
        self._document["pick_prefix_precompute"] = report
        if not succeeded:
            report.update(status="FAILED", error=f"{type(value).__name__}: {value}")
            return None
        delta = max(abs(a - b) for a, b in zip(job.start, current, strict=True))
        report["start_delta_max_abs_rad"] = delta
        if not delta <= PICK_HORIZON_REUSE_MAX_START_DELTA_RAD:
            report["status"] = "START_STATE_DIFFERS"
            return None
        report["status"] = "USED"
        return value

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
        position_tolerance_m = self._template.position_tolerance_m
        orientation_tolerance_rad = max(self._template.orientation_tolerance_rad)

        def while_progressing(compute):
            return _compute_while_progressing(compute, self._progress)

        if state in pick_prefix and has_full_target_set:
            result = self._take_pick_horizon_precompute(current)
            if result is None:
                result = solve_pick_prefix_horizon(
                    self._ik,
                    current,
                    self._targets,
                    self._interpolate_pose,
                    position_tolerance_m=position_tolerance_m,
                    orientation_tolerance_rad=orientation_tolerance_rad,
                    beam_width=3,
                    run=while_progressing,
                    descend_final_distance_m=self._descend_final_distance_m(),
                )
        else:
            waypoints = [
                HorizonWaypoint(state, index, target) for index, target in enumerate(motion_targets)
            ]
            result = while_progressing(
                lambda: solve_horizon(
                    self._ik,
                    tuple(waypoints),
                    current,
                    position_tolerance_m=position_tolerance_m,
                    orientation_tolerance_rad=orientation_tolerance_rad,
                    beam_width=3,
                )
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
        scaling = self._planning_scaling(state, step)
        attempts = self._ompl_attempts()
        # a run without episode diversity sends the request, and records the attempts, exactly as before
        attempt_fields = {} if attempts is None else {"num_planning_attempts": attempts}
        for candidate_index in range(candidate_count):
            _mark_place_side(state, f"candidate{candidate_index}.moveit.begin")
            planned = self._planning.plan_joint_path(
                JointPlanRequest(
                    joint_names=self._ARM_JOINTS,
                    current_positions=current,
                    target_positions=joint_target,
                    velocity_scaling=scaling[0],
                    acceleration_scaling=scaling[1],
                    planning_time_s=self._template.planning_timeout_s,
                    planning_group=self._template.planning_group,
                    tcp_link=self._template.tcp_link,
                    **attempt_fields,
                ),
                timeout_s=self._template.planning_timeout_s + 5.0,
            )
            _mark_place_side(state, f"candidate{candidate_index}.moveit.end")
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
                        **attempt_fields,
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
                    **({} if attempts is None else {
                        **attempt_fields, "trajectory_sha256": self._trajectory_digest(planned.trajectory)}),
                }
            )
            _mark_place_side(state, f"candidate{candidate_index}.corridor.begin")
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
            _mark_place_side(state, f"candidate{candidate_index}.corridor.end")
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

    def _motion_planning_start(self):
        return self._joint_state()

    def _planning_scaling(self, state: State, step=None) -> tuple[float, float]:
        """(velocity, acceleration) MoveIt scaling with frozen inputs: the frozen carry values for the carry states, and the
        schema 4 values for MOVE_ABOVE_OBJECT and RETREAT (a schema 3 policy has none: the template's). With a schema 5 policy the
        approach stage of DESCEND (``step`` is a waypoint farther than half the final distance from the grasp pose) takes the schema 5
        approach values; the last stage keeps the template's. Every other state and every run without frozen inputs plans with the
        template's."""

        template = (self._template.velocity_scaling, self._template.acceleration_scaling)
        if getattr(self, "_execution_snapshot_root", None) is None:
            return template
        policy = getattr(self, "_execution_policy", None)
        speed_keys = self._SPEED_SCALING_KEYS.get(state)
        if speed_keys is not None:
            return self._speed_scaled(speed_policy_value(policy, speed_keys[0], template[0]),
                                      speed_policy_value(policy, speed_keys[1], template[1]))
        if state is State.DESCEND and self._is_descend_approach_step(step):
            return self._speed_scaled(
                speed_policy_value(policy, DESCEND_SCALING_FIELDS[0], template[0], since_schema=EXECUTION_SCHEMA_DESCEND),
                speed_policy_value(policy, DESCEND_SCALING_FIELDS[1], template[1], since_schema=EXECUTION_SCHEMA_DESCEND))
        if state not in self._CARRY_STATES:
            return template
        if (policy is None or "carry_max_velocity_scaling" not in policy
                or "carry_max_acceleration_scaling" not in policy):
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: carry scaling")
        carry = (float(policy["carry_max_velocity_scaling"]), float(policy["carry_max_acceleration_scaling"]))
        # the place height was calibrated at the policy's carry speed: the touchdown keeps it whatever the episode speed scale
        return carry if state is State.DESCEND_TO_PLACE else self._speed_scaled(*carry)

    def _speed_scaled(self, velocity: float, acceleration: float) -> tuple[float, float]:
        """R3-a: a policy scaling pair times this episode's speed scale, each capped at 1; unchanged without episode diversity.

        Only the scaling keys of the frozen policy are scaled. The template-scaled phases (the last DESCEND stage, MICRO_LIFT,
        DESCEND_TO_PLACE) are contact-sensitive and keep their values."""

        diversity = getattr(self, "_episode_diversity", None)
        if diversity is None:
            return velocity, acceleration
        from so101_demo.act.teacher_diversity import scaled_scaling

        scale = diversity["speed_scale"]
        return scaled_scaling(velocity, scale), scaled_scaling(acceleration, scale)

    def _ompl_attempts(self) -> int | None:
        """R3-a: the OMPL planning attempts of this episode, or None without episode diversity (the request keeps its single attempt)."""

        diversity = getattr(self, "_episode_diversity", None)
        return None if diversity is None else int(diversity["ompl"]["num_planning_attempts"])

    @staticmethod
    def _trajectory_digest(trajectory) -> str | None:
        """sha256 of the planned joint positions and times: MoveIt takes no planner seed, so the planner output is what gets recorded."""

        import hashlib

        try:
            rows = [(tuple(float(value) for value in point.positions), int(point.time_from_start.sec), int(point.time_from_start.nanosec))
                    for point in trajectory.joint_trajectory.points]
            return hashlib.sha256(repr(rows).encode()).hexdigest()
        except (AttributeError, TypeError, ValueError):
            return None

    def _is_descend_approach_step(self, step) -> bool:
        """True for the approach stage of a schema 5 DESCEND: its waypoint is the point ``descend_final_distance_m`` above the grasp
        pose, the last stage's waypoint is the grasp pose itself (``_descend_grasp_target``, set by ``_motion``)."""

        distance_m = self._descend_final_distance_m()
        grasp = getattr(self, "_descend_grasp_target", None)
        if distance_m is None or step is None or grasp is None:
            return False
        return math.dist(step.waypoint.target.position_m, grasp.position_m) > distance_m / 2.0
