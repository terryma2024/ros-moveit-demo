"""Motion horizon and candidate set planning."""

from __future__ import annotations

import math

from so101_demo.act.teacher_endpoint import speed_policy_value
from so101_demo.control.moveit.deterministic_horizon import (
    MOVE_ABOVE_PLAN_CANDIDATE_COUNT,
    HorizonStep,
    HorizonWaypoint,
    cartesian_candidate_score,
    interpolated_move_above_waypoints,
    solve_horizon,
    validate_cartesian_corridor,
)
from so101_demo.control.moveit.planning import JointPlanRequest
from so101_demo.core.domain import State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ros.task_reachability import _compute_while_progressing


class MotionPlanning:
    #: the schema 4 Teacher policy keys (velocity, acceleration) of the free-space states that have their own MoveIt scaling
    _SPEED_SCALING_KEYS = {
        State.MOVE_ABOVE_OBJECT: ("move_above_object_velocity_scaling", "move_above_object_acceleration_scaling"),
        State.RETREAT: ("retreat_velocity_scaling", "retreat_acceleration_scaling"),
    }

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
                _compute_while_progressing(
                    lambda: interpolated_move_above_waypoints(self._ik, current, above),
                    self._progress,
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

        result = _compute_while_progressing(
            lambda: solve_horizon(
                self._ik,
                tuple(waypoints),
                current,
                position_tolerance_m=self._template.position_tolerance_m,
                orientation_tolerance_rad=max(self._template.orientation_tolerance_rad),
                beam_width=3,
            ),
            self._progress,
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
        scaling = self._planning_scaling(state)
        for candidate_index in range(candidate_count):
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

    def _motion_planning_start(self):
        return self._joint_state()

    def _planning_scaling(self, state: State) -> tuple[float, float]:
        """(velocity, acceleration) MoveIt scaling with frozen inputs: the frozen carry values for the carry states, and the
        schema 4 values for MOVE_ABOVE_OBJECT and RETREAT (a schema 3 policy has none: the template's). Every other state and
        every run without frozen inputs plans with the template's."""

        template = (self._template.velocity_scaling, self._template.acceleration_scaling)
        if getattr(self, "_execution_snapshot_root", None) is None:
            return template
        policy = getattr(self, "_execution_policy", None)
        speed_keys = self._SPEED_SCALING_KEYS.get(state)
        if speed_keys is not None:
            return (speed_policy_value(policy, speed_keys[0], template[0]),
                    speed_policy_value(policy, speed_keys[1], template[1]))
        if state not in self._CARRY_STATES:
            return template
        if (policy is None or "carry_max_velocity_scaling" not in policy
                or "carry_max_acceleration_scaling" not in policy):
            raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: carry scaling")
        return float(policy["carry_max_velocity_scaling"]), float(policy["carry_max_acceleration_scaling"])
