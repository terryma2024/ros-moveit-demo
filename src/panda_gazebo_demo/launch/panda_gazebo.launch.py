from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    package_share = FindPackageShare("panda_gazebo_demo")

    world_file = PathJoinSubstitution(
        [package_share, "worlds", "table_coke.sdf"]
    )
    xacro_file = PathJoinSubstitution(
        [package_share, "urdf", "panda.gazebo.urdf.xacro"]
    )

    robot_description = {
        "robot_description": ParameterValue(
            Command(["xacro ", xacro_file]),
            value_type=str,
        )
    }

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("ros_gz_sim"), "launch", "gz_sim.launch.py"]
            )
        ),
        launch_arguments={
            # 不加 -r：首次启动保持暂停，等 Controller 就绪后再播放。
            "gz_args": ["-r -v 4 ", 
                        "--physics-engine gz-physics-bullet-featherstone-plugin ", 
                        world_file,
            ],
        }.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[robot_description],
        output="screen",
    )

    spawn_panda = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-name", "panda",
            "-topic", "robot_description",
            "-allow_renaming", "true",
        ],
        output="screen",
    )

    joint_state_broadcaster = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager-timeout", "60",
        ],
        output="screen",
    )

    panda_arm_controller = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "panda_arm_controller",
            "--controller-manager-timeout", "60",
        ],
        output="screen",
    )

    panda_hand_controller = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "panda_hand_controller",
            "--controller-manager-timeout", "60",
        ],
        output="screen",
    )
    
    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
        ],
        output="screen",
    )
    
    
    moveit_config = (
        MoveItConfigsBuilder("moveit_resources_panda")
        .robot_description(
            file_path="config/panda.urdf.xacro",
            mappings={
                "ros2_control_hardware_type": "mock_components",
            },
        )
        .robot_description_semantic(file_path="config/panda.srdf")
        .planning_scene_monitor(
            publish_robot_description=True,
            publish_robot_description_semantic=True,
        )
        .trajectory_execution(
            file_path="config/gripper_moveit_controllers.yaml"
        )
        .planning_pipelines(
            pipelines=[
                "ompl",
                "chomp",
                "pilz_industrial_motion_planner",
                "stomp",
            ]
        )
        .to_moveit_configs()
    )

    # 其余 MoveIt 配置来自标准 Panda 配置包，
    # 但 URDF 必须替换成 Gazebo 和 robot_state_publisher 正在使用的版本。
    moveit_parameters = moveit_config.to_dict()
    moveit_parameters.update(robot_description)
    
    
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_parameters,
            {"use_sim_time": True},
        ],
        arguments=[
            "--ros-args",
            "--log-level",
            "info",
        ],
    )
    
    rviz_config = PathJoinSubstitution(
        [
            package_share,
            "config",
            "panda_gazebo.rviz",
        ]
    )
    
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz",
        output="screen",
        arguments=["-d", rviz_config],
        parameters=[
            robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
            {"use_sim_time": True},
        ],
    )

    return LaunchDescription([
        gazebo,
        clock_bridge,
        robot_state_publisher,
        spawn_panda,
        joint_state_broadcaster,
        panda_arm_controller,
        panda_hand_controller,
        move_group_node,
        rviz_node,
    ])