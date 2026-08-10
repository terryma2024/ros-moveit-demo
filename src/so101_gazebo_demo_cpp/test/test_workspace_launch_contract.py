import importlib.util
from pathlib import Path

from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node


PACKAGE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_SAMPLE_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_workspace_sample.launch.py'


def load_launch_description(path):
    spec = importlib.util.spec_from_file_location('workspace_sample_launch', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.generate_launch_description()


def test_workspace_launch_starts_only_the_offline_sampler():
    description = load_launch_description(WORKSPACE_SAMPLE_LAUNCH)
    nodes = [entity for entity in description.entities if isinstance(entity, Node)]
    assert len(nodes) == 1
    assert nodes[0].node_package == 'so101_gazebo_demo'
    assert nodes[0].node_executable == 'sample_so101_workspace'
    source = WORKSPACE_SAMPLE_LAUNCH.read_text()
    assert 'moveit_ros_move_group' not in source
    assert 'ros_gz' not in source
    assert 'controller_manager' not in source


def test_workspace_launch_declares_approved_public_arguments():
    description = load_launch_description(WORKSPACE_SAMPLE_LAUNCH)
    arguments = {
        entity.name for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    assert {
        'output_dir', 'profile', 'resume', 'time_budget_seconds', 'batch_size',
        'minimum_samples', 'maximum_samples', 'position_voxel_size_m',
        'orientation_threshold_deg', 'stable_batches',
        'position_new_rate_threshold', 'orientation_new_rate_threshold',
        'base_height', 'object_config',
    } <= arguments


def test_output_directory_is_required_and_defaults_match_approved_profiles():
    description = load_launch_description(WORKSPACE_SAMPLE_LAUNCH)
    arguments = {
        entity.name: entity for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    assert arguments['output_dir'].default_value is None
    defaults = {
        name: ''.join(part.text for part in argument.default_value)
        for name, argument in arguments.items() if argument.default_value is not None
    }
    assert defaults['profile'] == 'full'
    assert defaults['resume'] == 'false'
    assert defaults['time_budget_seconds'] == '1800'
    assert defaults['batch_size'] == '25000'
    assert defaults['minimum_samples'] == '250000'
    assert defaults['maximum_samples'] == '2000000'
