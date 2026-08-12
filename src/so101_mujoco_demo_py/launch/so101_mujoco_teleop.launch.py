#!/usr/bin/env python3
"""Own the MuJoCo/MoveIt stack and standalone Teleop on one session ID."""

from __future__ import annotations

import uuid
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch import LaunchDescription


def generate_launch_description() -> LaunchDescription:
    mujoco_share = Path(get_package_share_directory("so101_mujoco_demo_py"))
    teleop_share = Path(get_package_share_directory("so101_teleop"))
    session_id = LaunchConfiguration("simulation_session_id")
    runtime = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(mujoco_share / "launch/so101_pick_place.launch.py")),
        launch_arguments={
            "run_mode": "dry_run",
            "execute": "false",
            "launch_workflow": "false",
            "start_simulation": "true",
            "headless": LaunchConfiguration("headless"),
            "simulation_session_id": session_id,
            "readiness_timeout_s": LaunchConfiguration("readiness_timeout_s"),
        }.items(),
    )
    teleop = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(teleop_share / "launch/so101_teleop.launch.py")),
        launch_arguments={
            "backend": "mujoco_py",
            "bind_address": LaunchConfiguration("bind_address"),
            "port": LaunchConfiguration("port"),
            "simulation_session_id": session_id,
            "build_web_if_needed": LaunchConfiguration("build_web_if_needed"),
        }.items(),
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("headless", default_value="false"),
            DeclareLaunchArgument("readiness_timeout_s", default_value="30.0"),
            DeclareLaunchArgument("simulation_session_id", default_value=uuid.uuid4().hex),
            DeclareLaunchArgument("bind_address", default_value="127.0.0.1"),
            DeclareLaunchArgument("port", default_value="8000"),
            DeclareLaunchArgument("build_web_if_needed", default_value="false"),
            runtime,
            teleop,
        ]
    )
