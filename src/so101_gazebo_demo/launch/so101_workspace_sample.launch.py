from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    package_share = Path(get_package_share_directory('so101_gazebo_demo'))
    arguments = [
        DeclareLaunchArgument('output_dir', description='Required absolute artifact directory'),
        DeclareLaunchArgument('profile', default_value='full'),
        DeclareLaunchArgument('resume', default_value='false'),
        DeclareLaunchArgument('time_budget_seconds', default_value='1800'),
        DeclareLaunchArgument('batch_size', default_value='25000'),
        DeclareLaunchArgument('minimum_samples', default_value='250000'),
        DeclareLaunchArgument('maximum_samples', default_value='2000000'),
        DeclareLaunchArgument('position_voxel_size_m', default_value='0.005'),
        DeclareLaunchArgument('orientation_threshold_deg', default_value='10.0'),
        DeclareLaunchArgument('stable_batches', default_value='5'),
        DeclareLaunchArgument('position_new_rate_threshold', default_value='0.001'),
        DeclareLaunchArgument('orientation_new_rate_threshold', default_value='0.002'),
        DeclareLaunchArgument('base_height', default_value='0.1899186'),
        DeclareLaunchArgument(
            'object_config',
            default_value=str(package_share / 'config' / 'task_objects' / 'light_plastic_cup.yaml'),
        ),
    ]
    moveit_config = (
        MoveItConfigsBuilder('so101', package_name='so101_gazebo_demo')
        .robot_description(
            file_path=str(package_share / 'urdf' / 'so101.urdf.xacro'),
            mappings={
                'base_height': LaunchConfiguration('base_height'),
                'object_config': LaunchConfiguration('object_config'),
            },
        )
        .robot_description_semantic(file_path=str(package_share / 'config' / 'so101.srdf'))
        .to_moveit_configs()
    )
    sampler = Node(
        package='so101_gazebo_demo',
        executable='sample_so101_workspace',
        output='screen',
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            {
                'output_dir': LaunchConfiguration('output_dir'),
                'profile': LaunchConfiguration('profile'),
                'resume': ParameterValue(LaunchConfiguration('resume'), value_type=bool),
                'time_budget_seconds': ParameterValue(
                    LaunchConfiguration('time_budget_seconds'), value_type=int),
                'batch_size': ParameterValue(LaunchConfiguration('batch_size'), value_type=int),
                'minimum_samples': ParameterValue(
                    LaunchConfiguration('minimum_samples'), value_type=int),
                'maximum_samples': ParameterValue(
                    LaunchConfiguration('maximum_samples'), value_type=int),
                'position_voxel_size_m': ParameterValue(
                    LaunchConfiguration('position_voxel_size_m'), value_type=float),
                'orientation_threshold_deg': ParameterValue(
                    LaunchConfiguration('orientation_threshold_deg'), value_type=float),
                'stable_batches': ParameterValue(
                    LaunchConfiguration('stable_batches'), value_type=int),
                'position_new_rate_threshold': ParameterValue(
                    LaunchConfiguration('position_new_rate_threshold'), value_type=float),
                'orientation_new_rate_threshold': ParameterValue(
                    LaunchConfiguration('orientation_new_rate_threshold'), value_type=float),
            },
        ],
    )
    return LaunchDescription([*arguments, sampler])
