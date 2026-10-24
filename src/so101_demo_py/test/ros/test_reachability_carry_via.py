"""R3-a: the reachability filter and the per-run `check_task_reachability` run against the sampled per-episode targets, via-point included.

Without a via-point (schema 3, 4 and 5) the preflight plans what it always planned: one MOVE_ABOVE_PLACE waypoint, the template targets."""

from types import SimpleNamespace

import pytest

from so101_demo.application import task_reachability as application
from so101_demo.control.moveit import deterministic_horizon
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
from so101_demo.core.task_geometry import Pose7
from so101_demo.core.task_points import TaskPoint
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.robot_control import JointStateEvidence
from so101_demo.ros import dynamic_runtime, task_reachability as ros_reachability

from test_pick_horizon_precompute import START, ik, targets, template  # noqa: F401 - fixtures

JOINTS = ("1", "2", "3", "4", "5")
SAMPLE = CupPoseSample("world", 1, 0.0, Pose7((0.051023, -0.339445, 0.165, 0.0, 0.0, 0.0, 1.0)))


def planner(template, ik):
    return ros_reachability.RosMoveGroupReachabilityPlanner(object(), template, action_client=object(), ik=ik, progress=lambda: None)


def solved_waypoints(monkeypatch, run):
    seen = []

    def spy(ik_, waypoints, *arguments, **keywords):
        seen.append(tuple(waypoints))
        return SimpleNamespace(paths=(), candidate_receipts=())

    monkeypatch.setattr(ros_reachability, "solve_horizon", spy)
    run()
    return seen


def test_without_a_via_point_the_move_above_place_preflight_is_the_single_target_waypoint(monkeypatch, ik, template, targets):
    value = planner(template, ik)
    start = JointStateEvidence(JOINTS, START, 0.0)
    target = targets.for_state(State.MOVE_ABOVE_PLACE)
    seen = solved_waypoints(monkeypatch, lambda: value._steps_for(State.MOVE_ABOVE_PLACE, target, start))
    assert seen == [(deterministic_horizon.HorizonWaypoint(State.MOVE_ABOVE_PLACE, 0, target),)]


def test_with_a_via_point_the_preflight_plans_the_via_leg_and_the_target_leg(monkeypatch, ik, template):
    via_targets = resolve_motion_targets(SAMPLE, template, carry_via_offset_m=(0.01, -0.02, 0.03))
    value = planner(template, ik)
    start = JointStateEvidence(JOINTS, START, 0.0)
    value._remember_carry_via(via_targets)
    target = via_targets.for_state(State.MOVE_ABOVE_PLACE)
    seen = solved_waypoints(monkeypatch, lambda: value._steps_for(State.MOVE_ABOVE_PLACE, target, start))
    assert seen == [(deterministic_horizon.HorizonWaypoint(State.MOVE_ABOVE_PLACE, 0, via_targets.carry_via),
                     deterministic_horizon.HorizonWaypoint(State.MOVE_ABOVE_PLACE, 1, target))]
    # the other states are planned as they were
    other = solved_waypoints(monkeypatch, lambda: value._steps_for(State.LIFT, via_targets.for_state(State.LIFT), start))
    assert [len(item) for item in other] == [1]


def test_prepare_horizon_takes_the_via_point_of_the_targets_and_forgets_it_for_targets_without_one(monkeypatch, ik, template, targets):
    value = planner(template, ik)
    start = JointStateEvidence(JOINTS, START, 0.0)
    via_targets = resolve_motion_targets(SAMPLE, template, carry_via_offset_m=(0.0, 0.0, 0.01))
    solved_waypoints(monkeypatch, lambda: value.prepare_horizon(via_targets, start))
    assert value._carry_via == via_targets.carry_via
    solved_waypoints(monkeypatch, lambda: value.prepare_horizon(targets, start))
    assert value._carry_via is None


class SpyPlanner:
    def __init__(self):
        self.prepared, self.planned = [], []

    def prepare_horizon(self, targets, start):
        self.prepared.append(targets)

    def plan(self, state, target, start, cup_pose_world, timeout_s):
        self.planned.append((state, target))
        return application.SegmentPlanReceipt(True, start, 1, None)


def point():
    return TaskPoint(id="perceived_cup", label="Perceived cup", cup_position_world_m=tuple(SAMPLE.pose_world.values[:3]))


def test_check_task_reachability_resolves_the_targets_of_the_episode_with_the_via_offset(template):
    start = JointStateEvidence(JOINTS, START, 0.0)
    plain, spy = SpyPlanner(), SpyPlanner()
    assert application.check_task_reachability(point(), template, start, plain).status is application.ReachabilityStatus.REACHABLE
    assert plain.prepared[0].carry_via is None
    report = application.check_task_reachability(point(), template, start, spy, carry_via_offset_m=(0.01, 0.0, -0.02))
    assert report.status is application.ReachabilityStatus.REACHABLE
    assert spy.prepared[0].carry_via is not None
    # the same seven states are planned either way
    assert [state for state, _ in spy.planned] == [state for state, _ in plain.planned] == list(application.DYNAMIC_REACHABILITY_STATES)


def test_check_task_reachability_reports_a_via_point_outside_the_workspace_as_unreachable(template):
    start = JointStateEvidence(JOINTS, START, 0.0)
    report = application.check_task_reachability(point(), template, start, SpyPlanner(), carry_via_offset_m=(0.0, 0.0, 0.5))
    assert report.status is application.ReachabilityStatus.UNREACHABLE and report.first_failure_code == "TARGET_RESOLUTION_FAILED"


def test_the_real_preflight_passes_the_episode_template_and_the_via_offset_on(monkeypatch):
    seen = {}

    class Planner:
        def __init__(self, node, template, **kwargs):
            seen["template"] = template

        def close(self):
            pass

    class Reader:
        def __init__(self, node, names):
            pass

        def read(self, timeout_s):
            return "start"

        def close(self):
            pass

    def check(point, template, start, planner, **kwargs):
        seen["kwargs"] = kwargs
        return "report"

    monkeypatch.setattr(ros_reachability, "RosMoveGroupReachabilityPlanner", Planner)
    monkeypatch.setattr(ros_reachability, "RosJointStateReader", Reader)
    monkeypatch.setattr(application, "check_task_reachability", check)
    runtime = dynamic_runtime._dynamic_execute_runtime()
    template = SimpleNamespace(arm_joint_names=("a",), planning_timeout_s=1.0)
    sample = SimpleNamespace(pose_world=SimpleNamespace(values=(0.0, 0.0, 0.0)))
    assert runtime.reachability_preflight(object(), sample, template, 3, carry_via_offset_m=(0.0, 0.0, 0.01)) == "report"
    assert seen["kwargs"] == {"scene_revision": 3, "carry_via_offset_m": (0.0, 0.0, 0.01)}
    assert runtime.reachability_preflight(object(), sample, template, 3) == "report"
    assert seen["kwargs"] == {"scene_revision": 3}                # nothing extra for a run without a via-point
