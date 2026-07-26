import os
from pathlib import Path
from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.substitutions import Command, LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


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
                }.items()
             )

    gz_spawn_entity = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=["-topic", "robot_description",
                   "-name", "so101"],
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
        ],
    )
    arm_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "arm_controller",
            "--controller-manager",
            "/controller_manager",
        ],
    )
    gripper_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "gripper_controller",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    coke_contact_gz_topic = (
        "/world/so101_pick_place/model/coke/link/body/"
        "sensor/coke_contact_sensor/contact"
    )

    gz_ros2_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            (
                f"{coke_contact_gz_topic}"
                "@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts"
            ),
        ],
        remappings=[
            (coke_contact_gz_topic, "/coke/contacts"),
        ]
    )

    return LaunchDescription([
        model_arg,
        world_arg,
        base_height_arg,
        gazebo_resource_path,
        robot_state_publisher_node,
        gazebo,
        gz_spawn_entity,
        joint_state_broadcaster_spawner,
        arm_controller_spawner,
        gripper_controller_spawner,
        gz_ros2_bridge
    ])
