from pathlib import Path

import yaml

from so101_mujoco_demo_py.task_policy import load_task_policy

WORKSPACE_SRC = Path(__file__).resolve().parents[2]
MUJOCO_POLICY = (
    WORKSPACE_SRC
    / "so101_mujoco_demo_py"
    / "config"
    / "motion_policies"
    / "light_cup_wall_pick.yaml"
)
GAZEBO_POLICY = (
    WORKSPACE_SRC
    / "so101_gazebo_demo_py"
    / "config"
    / "validation_policies"
    / "light_cup_wall_pick.yaml"
)


def test_final_physical_outcome_semantics_match_gazebo_reference() -> None:
    mujoco = load_task_policy(MUJOCO_POLICY).physical_outcome
    gazebo = yaml.safe_load(GAZEBO_POLICY.read_text(encoding="utf-8"))["physical_outcome"]
    gazebo_region = gazebo["final_target_region"]

    assert mujoco.final_target_min_xy_m == tuple(gazebo_region["min_xy_m"])
    assert mujoco.final_target_max_xy_m == tuple(gazebo_region["max_xy_m"])
    assert mujoco.support_height_range_m == tuple(gazebo["support_height_range_m"])
    assert mujoco.max_upright_tilt_rad == gazebo["max_upright_tilt_rad"]
    assert mujoco.max_linear_speed_m_s == gazebo["max_linear_speed_m_s"]
    assert mujoco.max_angular_speed_rad_s == gazebo["max_angular_speed_rad_s"]
