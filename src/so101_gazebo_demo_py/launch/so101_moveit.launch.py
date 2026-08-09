from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    share = Path(get_package_share_directory("so101_gazebo_demo_py"))
    is_sim_arg = DeclareLaunchArgument("is_sim", default_value="True")
    base_height_arg = DeclareLaunchArgument("base_height", default_value="0.1899186")
    object_config_arg = DeclareLaunchArgument("object_config", default_value=str(share / "config/task_objects/light_plastic_cup.yaml"))
    config = (
        MoveItConfigsBuilder("so101", package_name="so101_gazebo_demo_py")
        .robot_description(file_path=str(share / "urdf/so101.urdf.xacro"), mappings={"base_height": LaunchConfiguration("base_height"), "object_config": LaunchConfiguration("object_config")})
        .robot_description_semantic(file_path=str(share / "config/so101.srdf"))
        .trajectory_execution(file_path=str(share / "config/moveit_controllers.yaml"))
        .planning_pipelines(default_planning_pipeline="ompl", pipelines=["ompl"], load_all=False)
        .to_moveit_configs()
    )
    parameters = [config.to_dict(), {"use_sim_time": LaunchConfiguration("is_sim")}, {"publish_robot_description_semantic": True}]
    return LaunchDescription([
        is_sim_arg, base_height_arg, object_config_arg,
        Node(package="moveit_ros_move_group", executable="move_group", output="screen", parameters=parameters),
        Node(package="rviz2", executable="rviz2", name="rviz2", arguments=["-d", str(share / "config/moveit.rviz")], parameters=[config.robot_description, config.robot_description_semantic, config.robot_description_kinematics, config.joint_limits, {"use_sim_time": LaunchConfiguration("is_sim")}]),
    ])
