from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    package_share = FindPackageShare('panda_gazebo_demo')
    headless = LaunchConfiguration('headless')
    run_state_machine = LaunchConfiguration('run_state_machine')

    runtime_defaults = {
        'velocity_scaling': '0.10',
        'acceleration_scaling': '0.10',
        'cartesian_eef_step': '0.005',
        'cartesian_min_fraction': '0.99',
        'joint_jump_threshold': '0.20',
        'tcp_position_tolerance': '0.020',
        'tcp_orientation_tolerance_rad': '0.0872665',
        'coke_position_tolerance': '0.010',
        'coke_orientation_tolerance_rad': '0.0872665',
        'gripper_open_position': '0.040',
        'gripper_open_min_position': '0.038',
        'gripper_close_position': '0.000',
        'gripper_grasp_min_position': '0.028',
        'gripper_grasp_max_position': '0.037',
        'gripper_symmetry_tolerance': '0.003',
        'joint_velocity_tolerance': '0.010',
        'motion_start_joint_tolerance': '0.010',
        'gripper_max_effort': '0.0',
        'gripper_action_timeout_seconds': '5.0',
        'attachment_timeout_seconds': '2.0',
        'planning_scene_timeout_seconds': '2.0',
        'state_poll_interval_seconds': '0.05',
        'gazebo_observation_max_age_seconds': '0.5',
        'coke_settle_interval_seconds': '0.05',
        'coke_settle_position_tolerance': '0.002',
        'coke_settle_orientation_tolerance_rad': '0.020',
        'recovery_safe_height': '0.987',
    }
    runtime_arguments = [
        DeclareLaunchArgument(name, default_value=value)
        for name, value in runtime_defaults.items()
    ]
    runtime_float_parameters = {
        name: ParameterValue(LaunchConfiguration(name), value_type=float)
        for name in runtime_defaults
    }
    runtime_arguments.extend(
        [
            DeclareLaunchArgument('run_state_machine', default_value='false'),
            DeclareLaunchArgument('mode', default_value='execute'),
            DeclareLaunchArgument('resume', default_value='false'),
            DeclareLaunchArgument('stop_after', default_value=''),
            DeclareLaunchArgument('simulation_session_id', default_value=''),
            DeclareLaunchArgument(
                'checkpoint_path',
                default_value='/tmp/panda_pick_place_checkpoint.json',
            ),
            DeclareLaunchArgument('max_state_transitions', default_value='100'),
            DeclareLaunchArgument('coke_settle_samples', default_value='5'),
        ]
    )

    world_file = PathJoinSubstitution([package_share, 'worlds', 'table_coke.sdf'])
    xacro_file = PathJoinSubstitution(
        [package_share, 'urdf', 'panda.gazebo.urdf.xacro']
    )

    robot_description = {
        'robot_description': ParameterValue(
            Command(['xacro ', xacro_file]),
            value_type=str,
        )
    }

    gazebo_launch_source = PythonLaunchDescriptionSource(
        PathJoinSubstitution(
            [FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py']
        )
    )

    gazebo_headless = IncludeLaunchDescription(
        gazebo_launch_source,
        launch_arguments={
            'gz_args': [
                '-s -r -v 4 ',
                '--physics-engine gz-physics-bullet-featherstone-plugin ',
                world_file,
            ],
        }.items(),
        condition=IfCondition(headless),
    )

    gazebo_with_gui = IncludeLaunchDescription(
        gazebo_launch_source,
        launch_arguments={
            'gz_args': [
                '-r -v 4 ',
                '--physics-engine gz-physics-bullet-featherstone-plugin ',
                world_file,
            ],
        }.items(),
        condition=UnlessCondition(headless),
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[robot_description],
        output='screen',
    )

    spawn_panda = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-name',
            'panda',
            '-topic',
            'robot_description',
            '-allow_renaming',
            'true',
        ],
        output='screen',
    )

    joint_state_broadcaster = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager-timeout',
            '60',
        ],
        output='screen',
    )

    panda_arm_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'panda_arm_controller',
            '--controller-manager-timeout',
            '60',
        ],
        output='screen',
    )

    panda_hand_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'panda_hand_controller',
            '--controller-manager-timeout',
            '60',
        ],
        output='screen',
    )

    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
        ],
        output='screen',
    )

    # V5-T004: 桥接 Gazebo RGBD 相机 topic 到 ROS 2
    # [ 表示 Gazebo → ROS 2 方向
    camera_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='camera_bridge',
        arguments=[
            '/camera@sensor_msgs/msg/Image[gz.msgs.Image',
            '/camera/depth@sensor_msgs/msg/Image[gz.msgs.Image',
            '/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
        ],
        output='screen',
    )

    moveit_config = (
        MoveItConfigsBuilder('moveit_resources_panda')
        .robot_description(
            file_path='config/panda.urdf.xacro',
            mappings={
                'ros2_control_hardware_type': 'mock_components',
            },
        )
        .robot_description_semantic(file_path='config/panda.srdf')
        .planning_scene_monitor(
            publish_robot_description=True,
            publish_robot_description_semantic=True,
        )
        .trajectory_execution(file_path='config/gripper_moveit_controllers.yaml')
        .planning_pipelines(
            pipelines=[
                'ompl',
                'chomp',
                'pilz_industrial_motion_planner',
                'stomp',
            ]
        )
        .to_moveit_configs()
    )

    # 其余 MoveIt 配置来自标准 Panda 配置包，
    # 但 URDF 必须替换成 Gazebo 和 robot_state_publisher 正在使用的版本。
    moveit_parameters = moveit_config.to_dict()
    moveit_parameters.update(robot_description)

    move_group_node = Node(
        package='moveit_ros_move_group',
        executable='move_group',
        output='screen',
        parameters=[
            moveit_parameters,
            {'use_sim_time': True},
        ],
        arguments=[
            '--ros-args',
            '--log-level',
            'info',
        ],
    )

    rviz_config = PathJoinSubstitution(
        [
            package_share,
            'config',
            'panda_gazebo.rviz',
        ]
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz',
        output='screen',
        arguments=['-d', rviz_config],
        parameters=[
            robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
            {'use_sim_time': True},
        ],
        condition=UnlessCondition(headless),
    )

    moveit_world_setup_node = Node(
        package='panda_gazebo_demo',
        executable='reset_moveit_world',
        output='screen',
    )

    attachment_state_relay = Node(
        package='panda_gazebo_demo',
        executable='gazebo_attachment_state_relay',
        output='screen',
        parameters=[
            {
                'event_topic': '/panda/coke_attached_event',
                'state_topic': '/panda/coke_attached',
                'detach_topic': '/panda/detach_coke',
                'enforce_initially_detached': True,
                'publish_period_seconds': 0.05,
            }
        ],
    )

    pick_place_state_machine = Node(
        package='panda_gazebo_demo',
        executable='pick_place_state_machine',
        output='screen',
        condition=IfCondition(run_state_machine),
        parameters=[
            runtime_float_parameters,
            {
                'use_sim_time': True,
                'mode': LaunchConfiguration('mode'),
                'resume': ParameterValue(
                    LaunchConfiguration('resume'), value_type=bool
                ),
                'stop_after': LaunchConfiguration('stop_after'),
                'simulation_session_id': LaunchConfiguration(
                    'simulation_session_id'
                ),
                'checkpoint_path': LaunchConfiguration('checkpoint_path'),
                'max_state_transitions': ParameterValue(
                    LaunchConfiguration('max_state_transitions'),
                    value_type=int,
                ),
                'coke_settle_samples': ParameterValue(
                    LaunchConfiguration('coke_settle_samples'),
                    value_type=int,
                ),
            },
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'headless',
                default_value='false',
                description='Run Gazebo server-only and do not start RViz',
            ),
            *runtime_arguments,
            gazebo_headless,
            gazebo_with_gui,
            clock_bridge,
            camera_bridge,
            attachment_state_relay,
            robot_state_publisher,
            spawn_panda,
            joint_state_broadcaster,
            panda_arm_controller,
            panda_hand_controller,
            move_group_node,
            moveit_world_setup_node,
            pick_place_state_machine,
            rviz_node,
        ]
    )
