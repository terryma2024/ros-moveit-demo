import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from so101_gazebo_demo_py.gazebo.model_asset import materialize_prepared_model


def _gazebo(headless: bool):
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    prefix = " -s" if headless else ""
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch/gz_sim.launch.py")),
        launch_arguments={"gz_args": [prefix, " -v 4 -r --physics-engine gz-physics-bullet-featherstone-plugin ", LaunchConfiguration("world")]}.items(),
        condition=IfCondition(LaunchConfiguration("headless")) if headless else UnlessCondition(LaunchConfiguration("headless")),
    )


def _spawn_prepared_model(_context, share: Path):
    output_root = Path(os.environ.get("ROS_LOG_DIR", "/tmp"))
    runtime_model = output_root / f"so101-prepared-{os.getpid()}.sdf"
    materialize_prepared_model(share / "models/so101_prepared.sdf", share, runtime_model)
    return [Node(
        package="ros_gz_sim", executable="create",
        arguments=["-file", str(runtime_model), "-name", "so101"], output="screen",
    )]


def generate_launch_description():
    share = Path(get_package_share_directory("so101_gazebo_demo_py"))
    model_arg = DeclareLaunchArgument("model", default_value=str(share / "urdf/so101.urdf.xacro"))
    world_arg = DeclareLaunchArgument("world", default_value=str(share / "worlds/so101_pick_place.sdf"))
    headless_arg = DeclareLaunchArgument("headless", default_value="false")
    base_height_arg = DeclareLaunchArgument("base_height", default_value="0.1899186")
    object_config_arg = DeclareLaunchArgument("object_config", default_value=str(share / "config/task_objects/light_plastic_cup.yaml"))
    description = ParameterValue(Command([
        "xacro ", LaunchConfiguration("model"), " base_height:=", LaunchConfiguration("base_height"),
        " use_gazebo:=true gazebo_collision_primitives:=true object_config:=",
        LaunchConfiguration("object_config"),
    ]), value_type=str)
    contact_topics = tuple(
        "/world/so101_pick_place/model/plastic_cup/link/body/sensor/"
        f"task_object_contact_{name}/contact"
        for name in ("wall_near", "wall_01", "wall_02", "wall_03", "wall_04", "wall_05", "wall_opposite", "wall_07", "wall_08", "wall_09", "wall_10", "wall_11", "bottom")
    )
    bridge = Node(
        package="ros_gz_bridge", executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/so101/attach_object@std_msgs/msg/Empty]gz.msgs.Empty",
            "/so101/detach_object@std_msgs/msg/Empty]gz.msgs.Empty",
            "/so101/object_attached_event@std_msgs/msg/String[gz.msgs.StringMsg",
            "/world/so101_pick_place/pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
            "/world/so101_pick_place/stats@ros_gz_interfaces/msg/WorldStatistics[gz.msgs.WorldStatistics",
            *[f"{topic}@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts" for topic in contact_topics],
        ],
        remappings=[
            ("/world/so101_pick_place/pose/info", "/so101/gazebo_pose_info"),
            ("/world/so101_pick_place/stats", "/so101/gazebo_world_stats"),
            *[(topic, "/task_object/contacts") for topic in contact_topics],
        ],
    )
    relay = TimerAction(period=2.0, actions=[
        Node(package="so101_gazebo_demo_py", executable="gazebo_attachment_state_relay", output="screen"),
    ])
    spawn_and_bridge = TimerAction(period=4.0, actions=[
        OpaqueFunction(function=_spawn_prepared_model, args=[share]),
        bridge,
    ])
    controllers = TimerAction(period=10.0, actions=[
        *[
            Node(
                package="controller_manager", executable="spawner",
                arguments=[name, "--controller-manager", "/controller_manager", "--switch-timeout", "30"],
            )
            for name in ("joint_state_broadcaster", "arm_controller", "gripper_controller")
        ],
    ])
    return LaunchDescription([
        model_arg, world_arg, headless_arg, base_height_arg, object_config_arg,
        SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(share.parent)),
        _gazebo(False), _gazebo(True),
        Node(package="robot_state_publisher", executable="robot_state_publisher", parameters=[{"robot_description": description, "use_sim_time": True}]),
        relay, spawn_and_bridge, controllers,
    ])
