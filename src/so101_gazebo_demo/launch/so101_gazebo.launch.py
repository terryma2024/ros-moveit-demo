import os
from pathlib import Path
import sys
import tempfile
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
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.events import Shutdown
from launch.substitutions import Command, LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


# Loading the offline 64-piece jaw compound can take tens of seconds before
# Gazebo starts the DetachableJoint relay on a cold cache.
INITIAL_DETACH_TIMEOUT_SECONDS = 120
VHACD_MAX_CONVEX_HULLS = 64
VHACD_VOXEL_RESOLUTION = 400000
COKE_CONTACT_GZ_TOPIC = (
    "/world/so101_pick_place/model/coke/link/body/"
    "sensor/coke_contact_sensor/contact"
)


def physics_engine_arguments():
    """Return the engine selection shared by GUI and headless servers."""
    return [
        "--physics-engine",
        "gz-physics-bullet-featherstone-plugin",
    ]


def simulation_model_preparation_command(model, output, base_height):
    """Build the command that preserves VHACD metadata past URDF conversion."""
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "prepare_simulation_model.py"
    )
    return [
        sys.executable,
        str(script),
        "--xacro",
        model,
        "--output",
        output,
        "--base-height",
        base_height,
        "--max-convex-hulls",
        str(VHACD_MAX_CONVEX_HULLS),
        "--voxel-resolution",
        str(VHACD_VOXEL_RESOLUTION),
    ]


def initial_detach_command(timeout_seconds=INITIAL_DETACH_TIMEOUT_SECONDS):
    """Publish detach only after the relay listens, then require durable evidence."""
    wait_and_publish = (
        "while ! gz topic -i -t /so101/coke_attached_event 2>&1 "
        "| grep -q '^Subscribers \\['; do sleep 0.1; done; "
        "while ! gz topic -i -t /so101/detach_coke 2>&1 "
        "| grep -q '^Subscribers \\['; do sleep 0.1; done; "
        "while ! gz topic -e -t /so101/coke_attached_event -n 1 2>&1 "
        "| grep -q 'data:.*attached'; do sleep 0.1; done; "
        "gz topic -t /so101/detach_coke "
        "-m gz.msgs.Empty -p 'unused: true'; "
        "while ! gz topic -e -t /so101/coke_attached -n 1 2>&1 "
        "| grep -q 'data: \"detached\"'; do sleep 0.1; done"
    )
    return [
        "/usr/bin/timeout",
        "--signal=TERM",
        "--kill-after=1",
        str(timeout_seconds),
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
    simulation_model_path = os.path.join(
        tempfile.gettempdir(), f"so101-gazebo-{os.getpid()}.sdf"
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
                    "gz_args": [
                        " -v 4 -r ",
                        *[f"{argument} " for argument in physics_engine_arguments()],
                        LaunchConfiguration("world"),
                    ]
                }.items(),
                condition=UnlessCondition(LaunchConfiguration("headless")),
             )
    gazebo_headless = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory("ros_gz_sim"), "launch"), "/gz_sim.launch.py"]),
                launch_arguments={
                    "gz_args": [
                        " -s -v 4 -r ",
                        *[f"{argument} " for argument in physics_engine_arguments()],
                        LaunchConfiguration("world"),
                    ]
                }.items(),
                condition=IfCondition(LaunchConfiguration("headless")),
             )

    simulation_model_preparation = ExecuteProcess(
        cmd=simulation_model_preparation_command(
            LaunchConfiguration("model"),
            simulation_model_path,
            LaunchConfiguration("base_height"),
        ),
        output="screen",
    )
    gz_spawn_entity = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=["-file", simulation_model_path,
                   "-name", "so101"],
    )
    start_spawn_after_model_preparation = RegisterEventHandler(
        OnProcessExit(
            target_action=simulation_model_preparation,
            on_exit=lambda event, context: actions_after_success_or_shutdown(
                event,
                [gz_spawn_entity],
                "SO-101 VHACD model preparation",
            ),
        )
    )

    (
        joint_state_broadcaster_spawner,
        arm_controller_spawner,
        gripper_controller_spawner,
    ) = controller_spawner_nodes()
    gz_ros2_bridge = attachment_bridge_node()
    attachment_state_relay = Node(
        package="so101_gazebo_demo",
        executable="gazebo_attachment_state_relay",
        output="screen",
    )

    # Gazebo Sim 8 starts DetachableJoint attached despite the SDF option.  The
    # relay starts first and subscribes to the raw plugin event.  The initializer
    # waits for the plugin's initial attached event before publishing detach,
    # then succeeds only after observing the relay's durable detached state.
    # Public command bridging and
    # controllers remain unavailable until that evidence chain completes.
    initial_detach_publisher = ExecuteProcess(
        cmd=initial_detach_command(),
        output="screen",
    )
    start_relay_after_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=gz_spawn_entity,
            on_exit=lambda event, context: actions_after_success_or_shutdown(
                event,
                [attachment_state_relay],
                "SO-101 robot spawn",
            ),
        )
    )
    start_detach_after_relay = RegisterEventHandler(
        OnProcessStart(
            target_action=attachment_state_relay,
            on_start=[initial_detach_publisher],
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
        start_relay_after_spawn,
        start_detach_after_relay,
        start_readiness_after_detach,
        start_spawn_after_model_preparation,
        simulation_model_preparation,
    ])
