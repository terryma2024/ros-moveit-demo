from __future__ import annotations

from dataclasses import replace

import pytest

from so101_demo.application.task_reachability import (
    ReachabilityPlannerPort,
    ReachabilityStatus,
    SegmentPlanReceipt,
    check_task_reachability,
)
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DynamicPickTemplate
from so101_demo.core.task_geometry import Pose7
from so101_demo.core.task_points import TaskPoint
from so101_demo.ports.robot_control import JointStateEvidence


ORDERED_STATES = (
    State.MOVE_ABOVE_OBJECT,
    State.DESCEND,
    State.MICRO_LIFT,
    State.LIFT,
    State.MOVE_ABOVE_PLACE,
    State.DESCEND_TO_PLACE,
    State.RETREAT,
)


def _template() -> DynamicPickTemplate:
    return DynamicPickTemplate(
        policy_id="dynamic_cup_pick",
        planning_frame="world",
        object_id="plastic_cup",
        planning_group="arm",
        arm_joint_names=("1", "2", "3", "4", "5"),
        tcp_link="so101_tcp",
        cup_to_tcp_grasp=Pose7((0.0, 0.0, 0.035, 0.0, 0.0, 0.0, 1.0)),
        pregrasp_world_z_clearance_m=0.08,
        micro_lift_world_z_clearance_m=0.02,
        lift_world_z_clearance_m=0.10,
        place_tcp_world=Pose7((0.19, -0.18, 0.20, 0.0, 0.0, 0.0, 1.0)),
        place_approach_world_z_clearance_m=0.08,
        retreat_world_z_clearance_m=0.10,
        workspace_bounds_m=(-0.30, -0.50, 0.10, 0.35, 0.20, 0.50),
        maximum_source_age_s=0.20,
        maximum_future_skew_s=0.02,
        scene_position_tolerance_m=0.01,
        scene_orientation_tolerance_rad=0.10,
        position_tolerance_m=0.002,
        orientation_tolerance_rad=(0.10, 0.10, 0.10),
        planning_timeout_s=5.0,
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
    )


def _point() -> TaskPoint:
    return TaskPoint("task_start", "Task start", (0.02, -0.28, 0.165))


def _start_state() -> JointStateEvidence:
    return JointStateEvidence(("1", "2", "3", "4", "5"), (0.0,) * 5, 1.0)


class RecordingPlanner:
    def __init__(self, *, fail_state: State | None = None, failure_code: str | None = None):
        self.fail_state = fail_state
        self.failure_code = failure_code
        self.states = []
        self.starts = []
        self.terminals = []
        self.cup_poses = []

    def plan(self, state, target, start, cup_pose_world, timeout_s):
        self.states.append(state)
        self.starts.append(start)
        self.cup_poses.append(cup_pose_world)
        if state is self.fail_state:
            return SegmentPlanReceipt(
                accepted=False,
                terminal_state=None,
                moveit_error_code=-1,
                failure_code=self.failure_code or "MOVEIT_PLAN_FAILED",
                collision_pairs=(("plastic_cup", "table"),),
            )
        terminal = JointStateEvidence(
            start.names,
            tuple(value + 0.01 for value in start.positions_rad),
            start.observed_monotonic_s + 1.0,
        )
        self.terminals.append(terminal)
        return SegmentPlanReceipt(
            accepted=True,
            terminal_state=terminal,
            moveit_error_code=1,
            failure_code=None,
        )


def test_reachability_plans_dynamic_sequence_from_each_terminal_state() -> None:
    planner = RecordingPlanner()

    report = check_task_reachability(
        _point(), _template(), _start_state(), planner, scene_revision=12
    )

    assert report.status is ReachabilityStatus.REACHABLE
    assert tuple(segment.state for segment in report.segments) == ORDERED_STATES
    assert planner.states == list(ORDERED_STATES)
    assert planner.starts[0] == _start_state()
    assert planner.starts[1:] == planner.terminals[:-1]
    assert all(pose.position_m == _point().cup_position_world_m for pose in planner.cup_poses)
    assert report.scene_revision == 12
    assert report.first_failure_code is None


def test_reachability_stops_at_first_failed_segment() -> None:
    planner = RecordingPlanner(fail_state=State.DESCEND)

    report = check_task_reachability(_point(), _template(), _start_state(), planner)

    assert report.status is ReachabilityStatus.UNREACHABLE
    assert report.first_failure_code == "MOVEIT_PLAN_FAILED"
    assert report.segments[-1].state is State.DESCEND
    assert report.segments[-1].moveit_error_code == -1
    assert report.segments[-1].collision_pairs == (("plastic_cup", "table"),)
    assert planner.states == [State.MOVE_ABOVE_OBJECT, State.DESCEND]


@pytest.mark.parametrize(
    "failure_code",
    ["SCENE_STALE", "JOINT_STATE_STALE", "PLANNER_UNAVAILABLE", "PLAN_TIMEOUT"],
)
def test_infrastructure_failures_are_unknown(failure_code: str) -> None:
    planner = RecordingPlanner(
        fail_state=State.MOVE_ABOVE_OBJECT,
        failure_code=failure_code,
    )

    report = check_task_reachability(_point(), _template(), _start_state(), planner)

    assert report.status is ReachabilityStatus.UNKNOWN
    assert report.first_failure_code == failure_code
    assert len(report.segments) == 1


def test_missing_initial_joint_state_is_unknown_without_planning() -> None:
    planner = RecordingPlanner()

    report = check_task_reachability(_point(), _template(), None, planner)

    assert report.status is ReachabilityStatus.UNKNOWN
    assert report.first_failure_code == "JOINT_STATE_UNAVAILABLE"
    assert report.segments == ()
    assert planner.states == []


def test_target_resolution_outside_workspace_is_unreachable() -> None:
    template = replace(
        _template(),
        cup_to_tcp_grasp=Pose7((0.05, 0.0, 0.035, 0.0, 0.0, 0.0, 1.0)),
    )
    point = TaskPoint("edge", "Edge", (0.34, -0.28, 0.165))
    planner = RecordingPlanner()

    report = check_task_reachability(point, template, _start_state(), planner)

    assert report.status is ReachabilityStatus.UNREACHABLE
    assert report.first_failure_code == "TARGET_RESOLUTION_FAILED"
    assert planner.states == []


def test_planner_exception_is_unknown_and_port_has_no_execute_operation() -> None:
    class UnavailablePlanner:
        def plan(self, *_args, **_kwargs):
            raise RuntimeError("MoveGroup unavailable")

    report = check_task_reachability(
        _point(), _template(), _start_state(), UnavailablePlanner()
    )

    assert report.status is ReachabilityStatus.UNKNOWN
    assert report.first_failure_code == "PLANNER_UNAVAILABLE"
    assert "execute" not in ReachabilityPlannerPort.__dict__
