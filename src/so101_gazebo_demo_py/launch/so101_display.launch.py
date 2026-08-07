from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = Path(get_package_share_directory("so101_gazebo_demo_py"))
    model = DeclareLaunchArgument("model", default_value=str(share / "urdf/so101.urdf.xacro"))
    description = ParameterValue(Command(["xacro ", LaunchConfiguration("model")]), value_type=str)
    return LaunchDescription([
        model,
        Node(package="joint_state_publisher_gui", executable="joint_state_publisher_gui"),
        Node(package="robot_state_publisher", executable="robot_state_publisher", parameters=[{"robot_description": description}]),
        Node(package="rviz2", executable="rviz2", name="rviz2", arguments=["-d", str(share / "rviz/display.rviz")]),
    ])
