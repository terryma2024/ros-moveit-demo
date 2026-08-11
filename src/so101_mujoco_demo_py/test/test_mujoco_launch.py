from __future__ import annotations

import importlib.util
from pathlib import Path

from launch.actions import DeclareLaunchArgument, OpaqueFunction

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_FILE = PACKAGE_ROOT / "launch/so101_mujoco.launch.py"


def load_launch_module():
    spec = importlib.util.spec_from_file_location("so101_mujoco_launch", LAUNCH_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launch_has_safe_defaults_unique_session_and_deferred_runtime() -> None:
    module = load_launch_module()
    description = module.generate_launch_description()
    declarations = {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }
    assert declarations["start_simulation"].default_value[0].text == "false"
    assert declarations["run_mode"].default_value[0].text == "dry_run"
    assert declarations["headless"].default_value[0].text == "true"
    assert declarations["readiness_timeout_s"].default_value[0].text == "30.0"
    first_session = declarations["simulation_session_id"].default_value[0].text
    second = module.generate_launch_description()
    second_declarations = {
        action.name: action
        for action in second.entities
        if isinstance(action, DeclareLaunchArgument)
    }
    assert first_session
    assert first_session != second_declarations["simulation_session_id"].default_value[0].text
    assert sum(isinstance(action, OpaqueFunction) for action in description.entities) == 1


def test_launch_builds_independent_description_and_expected_nodes() -> None:
    module = load_launch_module()
    source_urdf = (PACKAGE_ROOT / "urdf/so101.urdf").read_text(encoding="utf-8")
    rendered = module.render_robot_description(PACKAGE_ROOT)
    assert "@SO101_MUJOCO_SCENE@" in source_urdf
    assert "@SO101_MUJOCO_SCENE@" not in rendered
    assert str(PACKAGE_ROOT / "mjcf/scene.xml") in rendered
    assert '<param name="headless">true</param>' in rendered
    assert '<param name="headless">false</param>' in module.render_robot_description(
        PACKAGE_ROOT, headless="false"
    )
    assert module.RUNTIME_NODE_CONTRACT == {
        "mujoco_ros2_control/ros2_control_node",
        "robot_state_publisher/robot_state_publisher",
        "controller_manager/spawner:joint_state_broadcaster",
        "controller_manager/spawner:arm_controller",
        "controller_manager/spawner:gripper_controller",
    }
