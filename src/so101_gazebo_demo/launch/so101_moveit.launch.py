from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    """Start MoveIt and RViz from the self-contained SO-101 demo package."""
    is_sim_arg = DeclareLaunchArgument(name="is_sim", default_value="True")
    base_height_arg = DeclareLaunchArgument(
        name="base_height",
        default_value="0.1899186",
        description="SO-101 base height above world ground in metres",
    )
    package_share = Path(get_package_share_directory("so101_gazebo_demo"))
    object_config_arg = DeclareLaunchArgument(
        name="object_config",
        default_value=str(
            package_share / "config" / "task_objects" / "light_plastic_cup.yaml"
        ),
        description="Task-object YAML supplying calibrated adapter primitives",
    )

    is_sim = LaunchConfiguration("is_sim")
    base_height = LaunchConfiguration("base_height")

    so101_urdf_path = package_share / "urdf" / "so101.urdf.xacro"
    srdf_path = package_share / "config" / "so101.srdf"
    controllers_path = package_share / "config" / "moveit_controllers.yaml"
    rviz_config_path = package_share / "config" / "moveit.rviz"

    moveit_config = (
        MoveItConfigsBuilder("so101", package_name="so101_gazebo_demo")
        .robot_description(
            file_path=str(so101_urdf_path),
            mappings={
                "base_height": base_height,
                "object_config": LaunchConfiguration("object_config"),
            },
        )
        .robot_description_semantic(file_path=str(srdf_path))
        .trajectory_execution(file_path=str(controllers_path))
        .to_moveit_configs()
    )

    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {"use_sim_time": is_sim},
            {"publish_robot_description_semantic": True},
            {
                "trajectory_execution.allowed_execution_duration_scaling": 1.5,
                "trajectory_execution.allowed_goal_duration_margin": 1.0,
            },
        ],
        arguments=["--ros-args", "--log-level", "info"],
    )

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="screen",
        arguments=["-d", str(rviz_config_path)],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.joint_limits,
            {"use_sim_time": is_sim},
        ]
    )

    return LaunchDescription([
        is_sim_arg,
        base_height_arg,
        object_config_arg,
        move_group_node,
        rviz_node,
    ])
