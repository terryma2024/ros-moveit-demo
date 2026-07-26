import os
from pathlib import Path
from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    IncludeLaunchDescription,
    RegisterEventHandler,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import Command, LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


INITIAL_DETACH_TIMEOUT_SECONDS = 8
COKE_CONTACT_GZ_TOPIC = (
    "/world/so101_pick_place/model/coke/link/body/"
    "sensor/coke_contact_sensor/contact"
)


def initial_detach_command():
    """Wait for the Gazebo plugin, publish one detach, and always terminate."""
    wait_and_publish = (
        "while ! gz topic -i -t /so101/detach_coke 2>&1 "
        "| grep -q '^Subscribers \\['; do sleep 0.1; done; "
        "exec gz topic -t /so101/detach_coke "
        "-m gz.msgs.Empty -p 'unused: true'"
    )
    return [
        "/usr/bin/timeout",
        "--signal=TERM",
        "--kill-after=1",
        str(INITIAL_DETACH_TIMEOUT_SECONDS),
        "/bin/bash",
        "-c",
        wait_and_publish,
    ]


def actions_after_success_or_shutdown(event, success_actions, operation):
    """Continue a launch stage only after its prerequisite exits cleanly."""
    if event.returncode == 0:
        return success_actions

    reason = f"{operation} failed with exit code {event.returncode}"
    return [EmitEvent(event=Shutdown(reason=reason))]


def controller_spawner_nodes():
    """Build the controllers exposed only after detach initialization."""
    return [
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=[
                controller,
                "--controller-manager",
                "/controller_manager",
            ],
        )
        for controller in (
            "joint_state_broadcaster",
            "arm_controller",
            "gripper_controller",
        )
    ]


def attachment_bridge_node():
    """Build the public ROS bridge exposed after detach initialization."""
    return Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/so101/attach_coke@std_msgs/msg/Empty]gz.msgs.Empty",
            "/so101/detach_coke@std_msgs/msg/Empty]gz.msgs.Empty",
            (
                "/so101/coke_attached_event"
                "@std_msgs/msg/String[gz.msgs.StringMsg"
            ),
            (
                f"{COKE_CONTACT_GZ_TOPIC}"
                "@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts"
            ),
        ],
        remappings=[
            (COKE_CONTACT_GZ_TOPIC, "/coke/contacts"),
        ],
    )


def generate_launch_description():
    package_share = get_package_share_directory("so101_gazebo_demo")

    model_arg = DeclareLaunchArgument(name="model", default_value=os.path.join(
                                        package_share, "urdf", "so101.urdf.xacro"
                                        ),
                                      description="Absolute path to robot urdf file"
    )
    world_arg = DeclareLaunchArgument(
        name="world",
        default_value=os.path.join(
            package_share, "worlds", "so101_pick_place.sdf"
        ),
        description="Absolute path to Gazebo world file",
    )
    base_height_arg = DeclareLaunchArgument(
        name="base_height",
        default_value="0.1899186",
        description="SO-101 base height above world ground in metres",
    )
    headless_arg = DeclareLaunchArgument(
        name="headless",
        default_value="false",
        description="Run only the Gazebo server for automated smoke tests",
    )

    gazebo_resource_path = SetEnvironmentVariable(
        name="GZ_SIM_RESOURCE_PATH",
        value=[
            str(Path(package_share).parent.resolve())
            ]
        )

    robot_description = ParameterValue(Command([
            "xacro ",
            LaunchConfiguration("model"),
            " base_height:=",
            LaunchConfiguration("base_height"),
            " gazebo_collision_primitives:=true",
        ]),
        value_type=str
    )

    robot_state_publisher_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description,
                     "use_sim_time": True}]
    )

    gazebo = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory("ros_gz_sim"), "launch"), "/gz_sim.launch.py"]),
                launch_arguments={
                    "gz_args": [" -v 4 -r ", LaunchConfiguration("world")]
                }.items(),
                condition=UnlessCondition(LaunchConfiguration("headless")),
             )
    gazebo_headless = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory("ros_gz_sim"), "launch"), "/gz_sim.launch.py"]),
                launch_arguments={
                    "gz_args": [" -s -v 4 -r ", LaunchConfiguration("world")]
                }.items(),
                condition=IfCondition(LaunchConfiguration("headless")),
             )

    gz_spawn_entity = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=["-topic", "robot_description",
                   "-name", "so101"],
    )

    (
        joint_state_broadcaster_spawner,
        arm_controller_spawner,
        gripper_controller_spawner,
    ) = controller_spawner_nodes()
    gz_ros2_bridge = attachment_bridge_node()

    # Gazebo Sim 8 starts DetachableJoint attached despite the SDF option.  The
    # initializer waits for the plugin's real Gazebo Transport subscription,
    # publishes exactly once, and has an outer total timeout.  Public command
    # bridging and controllers remain unavailable until initialization passes.
    initial_detach_publisher = ExecuteProcess(
        cmd=initial_detach_command(),
        output="screen",
    )
    start_detach_after_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=gz_spawn_entity,
            on_exit=lambda event, context: actions_after_success_or_shutdown(
                event,
                [initial_detach_publisher],
                "SO-101 robot spawn",
            ),
        )
    )
    start_readiness_after_detach = RegisterEventHandler(
        OnProcessExit(
            target_action=initial_detach_publisher,
            on_exit=lambda event, context: actions_after_success_or_shutdown(
                event,
                [
                    gz_ros2_bridge,
                    joint_state_broadcaster_spawner,
                    arm_controller_spawner,
                    gripper_controller_spawner,
                ],
                "SO-101 initial detach",
            ),
        )
    )

    return LaunchDescription([
        model_arg,
        world_arg,
        base_height_arg,
        headless_arg,
        gazebo_resource_path,
        robot_state_publisher_node,
        gazebo,
        gazebo_headless,
        start_detach_after_spawn,
        start_readiness_after_detach,
        gz_spawn_entity,
    ])
