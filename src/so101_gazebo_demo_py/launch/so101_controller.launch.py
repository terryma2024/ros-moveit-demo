from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import UnlessCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = Path(get_package_share_directory("so101_gazebo_demo_py"))
    is_sim_arg = DeclareLaunchArgument("is_sim", default_value="True")
    is_sim = LaunchConfiguration("is_sim")
    description = ParameterValue(Command(["xacro ", str(share / "urdf/so101.urdf.xacro")]), value_type=str)
    spawners = [
        Node(package="controller_manager", executable="spawner", arguments=[name, "--controller-manager", "/controller_manager"])
        for name in ("joint_state_broadcaster", "arm_controller", "gripper_controller")
    ]
    return LaunchDescription([
        is_sim_arg,
        Node(package="robot_state_publisher", executable="robot_state_publisher", condition=UnlessCondition(is_sim), parameters=[{"robot_description": description}]),
        Node(package="controller_manager", executable="ros2_control_node", condition=UnlessCondition(is_sim), parameters=[{"robot_description": description, "use_sim_time": is_sim}, str(share / "config/so101_controllers.yaml")]),
        *spawners,
    ])
