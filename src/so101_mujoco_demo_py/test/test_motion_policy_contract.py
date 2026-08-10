from pathlib import Path

import yaml

POLICY = Path(__file__).parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"


def test_motion_policy_preserves_public_joint_and_gripper_contract() -> None:
    document = yaml.safe_load(POLICY.read_text())
    assert document["planning_group"] == "arm"
    assert document["tcp_link"] == "so101_tcp"
    assert document["arm_joints"] == ["1", "2", "3", "4", "5"]
    assert document["gripper_joint"] == "6"
    assert document["all_joints"] == ["1", "2", "3", "4", "5", "6"]
    assert document["gripper_actions"]["preopen_q6"] == 0.465038
    assert document["gripper_actions"]["grasp_close_q6"] == -0.047608632840292
    assert document["gripper_actions"]["release_q6"] == 0.75


def test_motion_policy_preserves_approved_pick_place_endpoints() -> None:
    states = yaml.safe_load(POLICY.read_text())["states"]
    seated = [-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465]
    assert states["DESCEND"]["waypoints"][-1] == seated
    assert states["LIFT"]["logical_start"] == seated
    assert states["MOVE_ABOVE_PLACE"]["velocity_scaling"] == 0.10
    assert states["DESCEND_TO_PLACE"]["velocity_scaling"] == 0.05
    assert states["DESCEND_TO_PLACE"]["acceleration_scaling"] == 0.05
