#!/usr/bin/env python3
"""Minimal isolated SO-101 MuJoCo ros2_control launch."""

from __future__ import annotations

import uuid
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile

from launch import LaunchDescription

PACKAGE_NAME = "so101_mujoco_demo_py"
RUNTIME_NODE_CONTRACT = {
    "mujoco_ros2_control/ros2_control_node",
    "robot_state_publisher/robot_state_publisher",
    "controller_manager/spawner:joint_state_broadcaster",
    "controller_manager/spawner:arm_controller",
    "controller_manager/spawner:gripper_controller",
}


def render_robot_description(package_root: Path, *, headless: str = "true") -> str:
    source = (package_root / "urdf/so101.urdf").read_text(encoding="utf-8")
    rendered = source.replace("@SO101_MUJOCO_SCENE@", str(package_root / "mjcf/scene.xml"))
    rendered = rendered.replace("@SO101_MUJOCO_HEADLESS@", headless)
    if "@SO101_" in rendered:
        raise RuntimeError("unresolved SO-101 URDF launch token")
    return rendered


def launch_setup(context):
    if LaunchConfiguration("start_simulation").perform(context).lower() != "true":
        return []
    package_root = Path(get_package_share_directory(PACKAGE_NAME))
    headless = LaunchConfiguration("headless").perform(context)
    robot_description = render_robot_description(package_root, headless=headless)
    controllers = str(package_root / "config/ros2_controllers.yaml")
    plugins = str(package_root / "config/mujoco_plugins.yaml")
    session_id = LaunchConfiguration("simulation_session_id").perform(context)
    timeout = LaunchConfiguration("readiness_timeout_s").perform(context)
    common_parameters = [
        {"use_sim_time": True, "robot_description": robot_description},
        ParameterFile(controllers, allow_substs=False),
        ParameterFile(plugins, allow_substs=False),
        {"simulation_session_id": session_id},
    ]
    nodes = [
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[{"use_sim_time": True, "robot_description": robot_description}],
            output="both",
        ),
        Node(
            package="mujoco_ros2_control",
            executable="ros2_control_node",
            parameters=common_parameters,
            output="both",
            emulate_tty=True,
            on_exit=Shutdown(),
        ),
    ]
    for controller in ("joint_state_broadcaster", "arm_controller", "gripper_controller"):
        nodes.append(
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=[
                    controller,
                    "--controller-manager-timeout",
                    timeout,
                    "--param-file",
                    controllers,
                ],
                output="both",
            )
        )
    return nodes


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument("start_simulation", default_value="false"),
            DeclareLaunchArgument("run_mode", default_value="dry_run"),
            DeclareLaunchArgument("headless", default_value="true"),
            DeclareLaunchArgument("readiness_timeout_s", default_value="30.0"),
            DeclareLaunchArgument("simulation_session_id", default_value=uuid.uuid4().hex),
            OpaqueFunction(function=launch_setup),
        ]
    )
