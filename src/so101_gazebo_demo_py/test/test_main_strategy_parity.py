from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from so101_gazebo_demo_py.live_execute import (
    make_world_z_target,
    make_pose_move_group_goal,
    seating_preload_target,
    select_joint_position,
    verify_physical_micro_lift,
    stabilize_to_target_penetration,
    local_x_world_delta,
)
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import contact_probe_complete
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import gripper_motion_duration_seconds
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import waypoint_step_seconds
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import gripper_result_acceptable


PACKAGE = Path(__file__).parents[1]


def test_final_release_shortens_only_the_explicit_release_command() -> None:
    assert gripper_motion_duration_seconds(-0.053) == 8
    assert gripper_motion_duration_seconds(0.465) == 5
    assert gripper_motion_duration_seconds(0.75) == 5
    assert gripper_motion_duration_seconds(0.75, final_release=True) == 2

    live_execute = (PACKAGE / "so101_gazebo_demo_py/live_execute.py").read_text()
    assert (
        "backend.move_gripper(bundle.motion.release_q6, final_release=True)"
        in live_execute
    )


def test_policy_matches_main_seated_grasp_strategy() -> None:
    motion = yaml.safe_load(
        (PACKAGE / "config/motion_policies/light_cup_wall_pick.yaml").read_text()
    )
    validation = yaml.safe_load(
        (PACKAGE / "config/validation_policies/light_cup_wall_pick.yaml").read_text()
    )
    controllers = yaml.safe_load(
        (PACKAGE / "config/so101_controllers_physical_outcome.yaml").read_text()
    )

    seated = [-0.000206491845, 0.472194274096, 0.214652624195,
              0.854922375695, 0.000576703465]
    assert motion["states"]["DESCEND"]["waypoints"][-1] == seated
    assert "CLOSE_GRIPPER" not in motion["states"]
    assert "CLOSE_GRIPPER" not in validation["states"]
    assert motion["states"]["LIFT"]["logical_start"] == seated
    assert motion["states"]["MOVE_ABOVE_PLACE"]["velocity_scaling"] == 0.10
    assert motion["states"]["DESCEND_TO_PLACE"]["velocity_scaling"] == 0.10
    assert motion["states"]["DESCEND_TO_PLACE"]["acceleration_scaling"] == 0.10
    constraints = controllers["arm_controller"]["ros__parameters"]["constraints"]
    assert {constraints[str(index)]["trajectory"] for index in range(1, 6)} == {0.008}


def test_seating_preload_is_exactly_six_milliradians_with_safe_floor() -> None:
    assert seating_preload_target(0.465038, -0.059600220867817) == 0.459038
    assert seating_preload_target(-0.058, -0.059600220867817) == -0.059600220867817


def test_world_z_target_preserves_xy_and_orientation() -> None:
    current = (0.020, -0.263, 0.2006, 0.1, 0.2, 0.3, 0.9)
    assert make_world_z_target(current, 0.002) == (
        0.020, -0.263, 0.2026, 0.1, 0.2, 0.3, 0.9
    )


def test_preload_uses_observed_contact_joint_position() -> None:
    q6_contact = select_joint_position(("3", "6", "1"), (0.2, -0.047, 0.0), "6")
    assert seating_preload_target(q6_contact, -0.059600220867817) == -0.053


def test_micro_lift_samples_contact_telemetry_after_motion() -> None:
    events = []

    class Backend:
        def sample(self):
            events.append("sample")
            z = 0.0 if events.count("sample") == 1 else 0.002
            return SimpleNamespace(
                object_xyz=(0.0, 0.0, z),
                tcp_xyz=(0.0, 0.0, 0.2 + z),
                tcp_xyzw=(0.0, 0.0, 0.0, 1.0),
            )

        def contacts(self):
            events.append("contacts")
            return ()

    result = verify_physical_micro_lift(
        Backend(), lambda delta: events.append(("move", delta)) or (3, 0.2)
    )

    assert events == ["sample", ("move", 0.002), "contacts", "sample"]
    assert result[0] == 0.002


def test_contact_probe_finishes_on_first_fresh_nonempty_message() -> None:
    assert not contact_probe_complete(())
    assert contact_probe_complete((object(),))


def test_micro_lift_move_group_goal_uses_main_pose_tolerances() -> None:
    goal = make_pose_move_group_goal(
        ("1", "2", "3", "4", "5", "6"),
        (0.0, 0.1, 0.2, 0.3, 0.4, -0.05),
        (0.02, -0.26, 0.202, 0.0, 0.0, 0.0, 1.0),
    )
    constraint = goal.request.goal_constraints[0]
    position = constraint.position_constraints[0]
    orientation = constraint.orientation_constraints[0]
    assert goal.request.group_name == "arm"
    assert goal.request.allowed_planning_time == 5.0
    assert goal.request.max_velocity_scaling_factor == 0.03
    assert goal.planning_options.plan_only
    assert position.link_name == orientation.link_name == "so101_tcp"
    assert list(position.constraint_region.primitives[0].dimensions) == [0.0004] * 3
    assert orientation.absolute_x_axis_tolerance == 0.005
    assert orientation.absolute_y_axis_tolerance == 0.005
    assert orientation.absolute_z_axis_tolerance == 0.005


def test_carrying_waypoint_timing_applies_policy_velocity_scaling() -> None:
    assert waypoint_step_seconds(3, 0.01) == 10
    assert waypoint_step_seconds(5, 0.03) == 3
    assert waypoint_step_seconds(5, 0.02) == 5
    assert waypoint_step_seconds(5, 0.05) == 2
    assert waypoint_step_seconds(5, 0.10) == 1


def test_target_penetration_closes_after_missing_contact(monkeypatch) -> None:
    targets = []
    stable = SimpleNamespace(max_moving_pad_penetration_m=0.0004)
    attempts = iter([RuntimeError("missing"), RuntimeError("missing"), stable])
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute._stable_bilateral",
        lambda _backend: (_ for _ in ()).throw(value)
        if isinstance((value := next(attempts)), Exception) else value,
    )

    contact, target, adjustments = stabilize_to_target_penetration(
        SimpleNamespace(move_gripper=targets.append), -0.053, 0.465, -0.0596
    )

    assert contact is stable
    assert target == -0.055
    assert adjustments == 2
    assert targets == [0.465, -0.054, 0.465, -0.055]


def test_target_penetration_opens_one_milliradian_when_too_deep(monkeypatch) -> None:
    targets = []
    contacts = iter([
        SimpleNamespace(max_moving_pad_penetration_m=0.001064),
        SimpleNamespace(max_moving_pad_penetration_m=0.000620),
    ])
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute._stable_bilateral",
        lambda _backend: next(contacts),
    )

    contact, target, adjustments = stabilize_to_target_penetration(
        SimpleNamespace(move_gripper=targets.append), -0.0536, 0.465, -0.0596
    )

    assert contact.max_moving_pad_penetration_m == 0.000620
    assert target == -0.0526
    assert adjustments == 1
    assert targets == [-0.0526]


def test_target_penetration_never_recovers_through_hard_ceiling(monkeypatch) -> None:
    monkeypatch.setattr(
        "so101_gazebo_demo_py.live_execute._stable_bilateral",
        lambda _backend: (_ for _ in ()).throw(
            RuntimeError("moving-pad penetration ceiling exceeded: 0.00131")
        ),
    )

    with pytest.raises(RuntimeError, match="penetration ceiling exceeded"):
        stabilize_to_target_penetration(
            SimpleNamespace(move_gripper=lambda _target: None),
            -0.053, 0.465, -0.0596,
        )


def test_contact_stopped_gripper_goal_defers_to_cup_outcome() -> None:
    aborted = "error_code: -5\nGoal finished with status: ABORTED"
    assert gripper_result_acceptable(aborted, bilateral=True)
    assert gripper_result_acceptable(aborted, bilateral=False)
    assert gripper_result_acceptable("status: SUCCEEDED", bilateral=False)


def test_reseating_translates_only_along_current_tcp_local_positive_x() -> None:
    assert local_x_world_delta((0.0, 0.0, 0.0, 1.0), 0.0002) == (
        0.0002, 0.0, 0.0
    )
