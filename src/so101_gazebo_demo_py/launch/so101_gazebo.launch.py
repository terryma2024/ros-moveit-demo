from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _gazebo(headless: bool):
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    prefix = " -s" if headless else ""
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch/gz_sim.launch.py")),
        launch_arguments={"gz_args": [prefix, " -v 4 -r --physics-engine gz-physics-bullet-featherstone-plugin ", LaunchConfiguration("world")]}.items(),
        condition=IfCondition(LaunchConfiguration("headless")) if headless else UnlessCondition(LaunchConfiguration("headless")),
    )


def generate_launch_description():
    share = Path(get_package_share_directory("so101_gazebo_demo_py"))
    model_arg = DeclareLaunchArgument("model", default_value=str(share / "urdf/so101.urdf.xacro"))
    world_arg = DeclareLaunchArgument("world", default_value=str(share / "worlds/so101_pick_place.sdf"))
    headless_arg = DeclareLaunchArgument("headless", default_value="false")
    base_height_arg = DeclareLaunchArgument("base_height", default_value="0.1899186")
    object_config_arg = DeclareLaunchArgument("object_config", default_value=str(share / "config/task_objects/light_plastic_cup.yaml"))
    description = ParameterValue(Command([
        "xacro ", LaunchConfiguration("model"), " base_height:=", LaunchConfiguration("base_height"),
        " use_gazebo:=true object_config:=", LaunchConfiguration("object_config"),
    ]), value_type=str)
    bridge = Node(
        package="ros_gz_bridge", executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/so101/attach_object@std_msgs/msg/Empty]gz.msgs.Empty",
            "/so101/detach_object@std_msgs/msg/Empty]gz.msgs.Empty",
            "/so101/object_attached_event@std_msgs/msg/String[gz.msgs.StringMsg",
            "/world/so101_pick_place/pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
            "/world/so101_pick_place/stats@ros_gz_interfaces/msg/WorldStatistics[gz.msgs.WorldStatistics",
        ],
        remappings=[
            ("/world/so101_pick_place/pose/info", "/so101/gazebo_pose_info"),
            ("/world/so101_pick_place/stats", "/so101/gazebo_world_stats"),
        ],
    )
    delayed_stack = TimerAction(period=3.0, actions=[
        Node(package="ros_gz_sim", executable="create", arguments=["-topic", "robot_description", "-name", "so101"]),
        bridge,
        Node(package="so101_gazebo_demo_py", executable="gazebo_attachment_state_relay", output="screen"),
        *[
            Node(package="controller_manager", executable="spawner", arguments=[name, "--controller-manager", "/controller_manager"])
            for name in ("joint_state_broadcaster", "arm_controller", "gripper_controller")
        ],
    ])
    return LaunchDescription([
        model_arg, world_arg, headless_arg, base_height_arg, object_config_arg,
        SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(share.parent)),
        _gazebo(False), _gazebo(True),
        Node(package="robot_state_publisher", executable="robot_state_publisher", parameters=[{"robot_description": description, "use_sim_time": True}]),
        delayed_stack,
    ])
