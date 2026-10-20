"""Round-2 S2 review fix: the reachability preflight checks the DESCEND geometry that will be executed.

Schema >= 5: the two-stage waypoints of `descend_waypoints()` with the frozen `descend_final_distance_m`; schema 3 and 4 (no
distance): the six interpolated segments, as before. Fixture level, real URDF IK, no ROS graph."""

from types import SimpleNamespace

import pytest

from so101_demo.control.moveit import deterministic_horizon
from so101_demo.core.domain import State
from so101_demo.ports.robot_control import JointStateEvidence
from so101_demo.ros import dynamic_runtime, task_reachability as ros_reachability
from so101_demo.ros.dynamic_execution.safety import MotionSafety

from test_pick_horizon_precompute import START, ik, targets, template  # noqa: F401 - fixtures

JOINTS = ("1", "2", "3", "4", "5")


def descend_waypoints_seen(monkeypatch, run):
    """The DESCEND waypoints that `run` hands to solve_horizon (the module the executed horizon and the preflight both call)."""
    seen = []

    def spy(ik_, waypoints, *arguments, **keywords):
        seen.append(tuple(waypoint for waypoint in waypoints if waypoint.state is State.DESCEND))
        return SimpleNamespace(paths=(), candidate_receipts=())

    monkeypatch.setattr(deterministic_horizon, "solve_horizon", spy)
    monkeypatch.setattr(ros_reachability, "solve_horizon", spy)
    run()
    assert len(seen) == 1
    return seen[0]


def preflight_waypoints(monkeypatch, ik, template, targets, **options):
    planner = ros_reachability.RosMoveGroupReachabilityPlanner(
        object(), template, action_client=object(), ik=ik, progress=lambda: None, **options)
    start = JointStateEvidence(JOINTS, START, 0.0)
    return descend_waypoints_seen(monkeypatch, lambda: planner.prepare_horizon(targets, start))


def executed_waypoints(monkeypatch, ik, template, targets, distance):
    return descend_waypoints_seen(monkeypatch, lambda: deterministic_horizon.solve_pick_prefix_horizon(
        ik, START, targets, MotionSafety._interpolate_pose, position_tolerance_m=template.position_tolerance_m,
        orientation_tolerance_rad=max(template.orientation_tolerance_rad), descend_final_distance_m=distance))


@pytest.mark.parametrize("distance", [0.02, 0.035, 0.07])      # 0.07 > the pregrasp-to-grasp distance: the final motion only
def test_a_schema_5_preflight_evaluates_exactly_the_executed_waypoints(monkeypatch, ik, template, targets, distance):
    planned = preflight_waypoints(monkeypatch, ik, template, targets, descend_final_distance_m=distance)
    executed = executed_waypoints(monkeypatch, ik, template, targets, distance)
    assert planned == executed
    assert len(planned) == (1 if distance == 0.07 else 2)
    assert planned[-1].target == targets.for_state(State.DESCEND)


def test_a_schema_4_preflight_still_evaluates_the_six_interpolated_segments(monkeypatch, ik, template, targets):
    planned = preflight_waypoints(monkeypatch, ik, template, targets)
    above, grasp = targets.for_state(State.MOVE_ABOVE_OBJECT), targets.for_state(State.DESCEND)
    expected = tuple(deterministic_horizon.HorizonWaypoint(
        State.DESCEND, index, ros_reachability.RosMoveGroupReachabilityPlanner._interpolate_pose(above, grasp, index / 6.0))
        for index in range(1, 7))
    assert planned == expected
    assert planned == executed_waypoints(monkeypatch, ik, template, targets, None)


# ---- how the frozen distance reaches the planner ---------------------------------------------------------------------------

def frozen_with(schema, **values):
    return {"teacher_execution_policy": {"values": {"schema_version": schema, **values}}}


def test_the_frozen_distance_is_read_from_the_frozen_policy_values_for_schema_5_only():
    read = dynamic_runtime._frozen_descend_final_distance_m
    assert read(frozen_with(5, descend_final_distance_m=0.02)) == 0.02
    assert read(frozen_with(4)) is None and read(frozen_with(3)) is None
    assert read(frozen_with(4, descend_final_distance_m=0.02)) is None        # not a schema 5 document: never read
    assert read(None) is None and read({}) is None


def test_a_schema_5_freeze_without_the_distance_refuses():
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        dynamic_runtime._frozen_descend_final_distance_m(frozen_with(5))


def test_the_real_preflight_passes_the_distance_to_the_planner_only_when_given(monkeypatch):
    from so101_demo.application import task_reachability as application

    seen = {}

    class Planner:
        def __init__(self, node, template, **kwargs):
            seen["planner_kwargs"] = kwargs

        def close(self):
            pass

    class Reader:
        def __init__(self, node, names):
            pass

        def read(self, timeout_s):
            return "start"

        def close(self):
            pass

    monkeypatch.setattr(ros_reachability, "RosMoveGroupReachabilityPlanner", Planner)
    monkeypatch.setattr(ros_reachability, "RosJointStateReader", Reader)
    monkeypatch.setattr(application, "check_task_reachability", lambda *args, **kwargs: "report")
    runtime = dynamic_runtime._dynamic_execute_runtime()
    template = SimpleNamespace(arm_joint_names=("a",), planning_timeout_s=1.0)
    sample = SimpleNamespace(pose_world=SimpleNamespace(values=(0.0, 0.0, 0.0)))
    assert runtime.reachability_preflight(object(), sample, template, 3, descend_final_distance_m=0.02) == "report"
    assert seen["planner_kwargs"] == {"descend_final_distance_m": 0.02}
    assert runtime.reachability_preflight(object(), sample, template, 3) == "report"
    assert seen["planner_kwargs"] == {}
