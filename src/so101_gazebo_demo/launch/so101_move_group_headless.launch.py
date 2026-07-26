"""Start the SO-101 MoveIt move_group without RViz or any GUI process."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    is_sim_arg = DeclareLaunchArgument(name="is_sim", default_value="True")
    base_height_arg = DeclareLaunchArgument(
        name="base_height", default_value="0.1899186"
    )
    package_share = Path(get_package_share_directory("so101_gazebo_demo"))
    moveit_config = (
        MoveItConfigsBuilder("so101", package_name="so101_gazebo_demo")
        .robot_description(
            file_path=str(package_share / "urdf" / "so101.urdf.xacro"),
            mappings={"base_height": LaunchConfiguration("base_height")},
        )
        .robot_description_semantic(
            file_path=str(package_share / "config" / "so101.srdf")
        )
        .trajectory_execution(
            file_path=str(package_share / "config" / "moveit_controllers.yaml")
        )
        .to_moveit_configs()
    )
    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {"use_sim_time": LaunchConfiguration("is_sim")},
            {"publish_robot_description_semantic": True},
        ],
    )
    return LaunchDescription([is_sim_arg, base_height_arg, move_group])
