"""Deprecated include for the unified MuJoCo stack launcher."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description() -> LaunchDescription:
    share = Path(get_package_share_directory("so101_demo_py"))
    return LaunchDescription(
        [
            LogInfo(msg="so101_mujoco_demo_py is deprecated; use so101_demo_py"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(share / "launch/so101_mujoco.launch.py"))
            ),
        ]
    )
