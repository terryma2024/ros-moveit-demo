from pathlib import Path

from so101_gazebo_demo_py.policy_config import load_policy_bundle
from so101_gazebo_demo_py.profile import SO101Profile


CONFIG = Path(__file__).parents[1] / "config"


def test_profile_binds_public_names_and_configured_gripper_values() -> None:
    bundle = load_policy_bundle(
        CONFIG / "task_objects/light_plastic_cup.yaml",
        CONFIG / "motion_policies/light_cup_wall_pick.yaml",
        CONFIG / "validation_policies/light_cup_wall_pick.yaml",
    )
    profile = SO101Profile.from_bundle(bundle)
    assert profile.world_name == "so101_pick_place"
    assert profile.planning_group == "arm"
    assert profile.tcp_link == "so101_tcp"
    assert profile.arm_joints == ("1", "2", "3", "4", "5")
    assert profile.gripper_joint == "6"
    assert profile.object_model == "plastic_cup"
    assert profile.object_link == "body"
    assert profile.attach_topic != profile.detach_topic
    assert profile.preopen_q6 == 0.465038
    assert profile.grasp_close_q6 == -0.047608632840292
    assert profile.release_q6 == 0.465038
