import os
from pathlib import Path

from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    RegisterEventHandler,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from moveit_configs_utils import MoveItConfigsBuilder


def gz_ros2_control_system_plugin_path(existing_path):
    plugin_directory = Path(get_package_prefix('gz_ros2_control')) / 'lib'
    paths = [str(plugin_directory)]
    if existing_path:
        paths.append(existing_path)
    return os.pathsep.join(paths)


def generate_launch_description():
    package_share = FindPackageShare('panda_gazebo_demo_cpp')
    headless = LaunchConfiguration('headless')
    run_state_machine = LaunchConfiguration('run_state_machine')
    controller_manager_timeout = LaunchConfiguration('controller_manager_timeout')
    controller_service_call_timeout = LaunchConfiguration(
        'controller_service_call_timeout'
    )
    gazebo_system_plugin_path = SetEnvironmentVariable(
        name='GZ_SIM_SYSTEM_PLUGIN_PATH',
        value=gz_ros2_control_system_plugin_path(
            os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH')
        ),
    )

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
        'gazebo_initial_observation_timeout_seconds': '30.0',
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
            DeclareLaunchArgument('controller_manager_timeout', default_value='240'),
            DeclareLaunchArgument(
                'controller_service_call_timeout', default_value='60'
            ),
            DeclareLaunchArgument('mode', default_value='execute'),
            DeclareLaunchArgument('resume', default_value='false'),
            DeclareLaunchArgument('stop_after', default_value=''),
            DeclareLaunchArgument(
                'plan_only_state',
                default_value='',
                description='See docs/pick-place-launch-parameters.md',
            ),
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

    # Gazebo Sim on macOS cannot run server and GUI in one process. Launch the
    # server and client separately; GZ_PARTITION connects them to the same world.
    gazebo_gui_server = IncludeLaunchDescription(
        gazebo_launch_source,
        launch_arguments={
            'gz_args': [
                '-s -r -v 4 ',
                '--physics-engine gz-physics-bullet-featherstone-plugin ',
                world_file,
            ],
        }.items(),
        condition=UnlessCondition(headless),
    )

    gazebo_gui_client = IncludeLaunchDescription(
        gazebo_launch_source,
        launch_arguments={'gz_args': '-g -v 4'}.items(),
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

    controllers_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'joint_state_broadcaster',
            'panda_arm_controller',
            'panda_hand_controller',
            '--controller-manager-timeout',
            controller_manager_timeout,
            '--service-call-timeout',
            controller_service_call_timeout,
            '--switch-timeout',
            controller_service_call_timeout,
            '--activate-as-group',
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
        package='panda_gazebo_demo_cpp',
        executable='reset_moveit_world',
        output='screen',
    )

    attachment_state_relay = Node(
        package='panda_gazebo_demo_cpp',
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
        package='panda_gazebo_demo_cpp',
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
                'plan_only_state': LaunchConfiguration('plan_only_state'),
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
                'gazebo_initial_observation_timeout_seconds': ParameterValue(
                    LaunchConfiguration('gazebo_initial_observation_timeout_seconds'),
                    value_type=float,
                ),
            },
        ],
    )

    spawn_to_controllers = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_panda,
            on_exit=[controllers_spawner],
        )
    )
    controllers_to_moveit_world = RegisterEventHandler(
        OnProcessExit(
            target_action=controllers_spawner,
            on_exit=[moveit_world_setup_node],
        )
    )
    moveit_world_to_state_machine = RegisterEventHandler(
        OnProcessExit(
            target_action=moveit_world_setup_node,
            on_exit=[pick_place_state_machine],
        )
    )

    return LaunchDescription(
        [
            gazebo_system_plugin_path,
            DeclareLaunchArgument(
                'headless',
                default_value='false',
                description='Run Gazebo server-only and do not start RViz',
            ),
            *runtime_arguments,
            gazebo_headless,
            gazebo_gui_server,
            gazebo_gui_client,
            clock_bridge,
            attachment_state_relay,
            robot_state_publisher,
            spawn_panda,
            spawn_to_controllers,
            controllers_to_moveit_world,
            moveit_world_to_state_machine,
            move_group_node,
            rviz_node,
        ]
    )
