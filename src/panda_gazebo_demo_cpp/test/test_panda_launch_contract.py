"""Public launch-argument contract for Panda pick/place."""

import importlib.util
import os
from pathlib import Path
import re

from ament_index_python.packages import get_package_prefix
from launch.actions import DeclareLaunchArgument
import yaml


PANDA_LAUNCH = Path(__file__).resolve().parents[1] / 'launch' / 'panda_gazebo.launch.py'
LAUNCH_MANUAL = PANDA_LAUNCH.parents[3] / 'docs' / 'pick-place-launch-parameters.md'
CONTROLLERS_CONFIG = PANDA_LAUNCH.parent.parent / 'config' / 'controllers.yaml'


def test_launch_manual_preserves_panda_force_continue_exclusion():
    manual = LAUNCH_MANUAL.read_text()
    assert 'Panda declares no force-continue state' in manual
    assert 'attach_and_lift_demo' in manual


def load_launch_description(path):
    return load_launch_module(path).generate_launch_description()


def load_launch_module(path):
    spec = importlib.util.spec_from_file_location('panda_gazebo_launch', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def launch_default_text(argument):
    return ''.join(part.text for part in argument.default_value)


def test_plan_only_state_is_public_and_forwarded():
    description = load_launch_description(PANDA_LAUNCH)
    declared = {
        entity.name: entity
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    defaults = {name: launch_default_text(argument) for name, argument in declared.items()}
    source = PANDA_LAUNCH.read_text()

    assert defaults['plan_only_state'] == ''
    assert "'plan_only_state': LaunchConfiguration('plan_only_state')" in source
    assert 'docs/pick-place-launch-parameters.md' in declared['plan_only_state'].description


def test_launch_uses_renamed_ros_package_identity():
    source = PANDA_LAUNCH.read_text(encoding='utf-8')

    assert "FindPackageShare('panda_gazebo_demo_cpp')" in source
    assert source.count("package='panda_gazebo_demo_cpp'") == 3
    assert not re.search(
        r'(?<![A-Za-z0-9_])panda_gazebo_demo(?![A-Za-z0-9_])',
        source,
    )


def test_controller_manager_uses_sim_time_for_joint_state_timestamps():
    config = yaml.safe_load(CONTROLLERS_CONFIG.read_text())

    assert config['controller_manager']['ros__parameters']['use_sim_time'] is True


def test_controller_spawners_allow_for_slow_gazebo_startup():
    description = load_launch_description(PANDA_LAUNCH)
    declared = {
        entity.name: entity
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    source = PANDA_LAUNCH.read_text(encoding='utf-8')

    assert launch_default_text(declared['controller_manager_timeout']) == '240'
    assert launch_default_text(declared['controller_service_call_timeout']) == '60'
    assert source.count("LaunchConfiguration('controller_manager_timeout')") == 1
    assert re.search(
        r"LaunchConfiguration\(\s*'controller_service_call_timeout'\s*\)", source
    )
    assert source.count("executable='spawner'") == 1
    assert source.count('controller_manager_timeout,') == 1
    assert source.count('controller_service_call_timeout,') == 2
    assert "'joint_state_broadcaster'" in source
    assert "'panda_arm_controller'" in source
    assert "'panda_hand_controller'" in source
    assert "'--activate-as-group'" in source


def test_macos_gui_runs_gazebo_server_and_client_as_separate_processes():
    source = PANDA_LAUNCH.read_text(encoding='utf-8')

    assert 'gazebo_gui_server = IncludeLaunchDescription' in source
    assert 'gazebo_gui_client = IncludeLaunchDescription' in source
    assert "'-s -r -v 4 '" in source
    assert "'gz_args': '-g -v 4'" in source


def test_gazebo_control_plugin_directory_precedes_existing_search_path():
    module = load_launch_module(PANDA_LAUNCH)
    existing_path = os.pathsep.join(('/custom/first', '/custom/second'))
    plugin_directory = str(Path(get_package_prefix('gz_ros2_control')) / 'lib')

    configured_path = module.gz_ros2_control_system_plugin_path(existing_path)

    assert configured_path.split(os.pathsep) == [
        plugin_directory,
        '/custom/first',
        '/custom/second',
    ]


def test_plan_only_request_uses_common_validation_before_runtime_bootstrap():
    source = (
        PANDA_LAUNCH.parent.parent
        / 'src'
        / 'nodes'
        / 'pick_place_state_machine_node.cpp'
    ).read_text()

    assert (
        'pick_place_common::validateRunRequest(pick_place::pandaWorkflowDefinition(), request)'
        in source
    )
    assert source.index('validateRunRequest') < source.index('resolveSimulationSessionId')


def test_motion_plan_limit_parameters_are_mapped_by_name():
    source = (
        PANDA_LAUNCH.parent.parent
        / 'src'
        / 'nodes'
        / 'pick_place_state_machine_node.cpp'
    ).read_text()

    expected_assignments = {
        'min_cartesian_fraction': 'cartesian_min_fraction',
        'max_joint_jump': 'joint_jump_threshold',
        'max_lateral_deviation': 'tcp_position_tolerance',
        'max_orientation_error_rad': 'tcp_orientation_tolerance_rad',
        'endpoint_position_tolerance': 'tcp_position_tolerance',
        'endpoint_orientation_tolerance_rad': 'tcp_orientation_tolerance_rad',
        'carried_relative_position_tolerance': 'coke_position_tolerance',
        'carried_relative_orientation_tolerance_rad': 'coke_orientation_tolerance_rad',
        'start_joint_tolerance': 'motion_start_joint_tolerance',
    }

    for limit, parameter in expected_assignments.items():
        assert re.search(
            rf'motion_plan_limits\.{limit} =\s+parameters\.{parameter}', source
        )


def test_embedded_state_machine_has_a_distinct_initial_observation_wait_budget():
    description = load_launch_description(PANDA_LAUNCH)
    declared = {
        entity.name: entity
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    defaults = {name: launch_default_text(argument) for name, argument in declared.items()}
    source = PANDA_LAUNCH.read_text()

    assert defaults['gazebo_initial_observation_timeout_seconds'] == '30.0'
    assert re.search(
        r"'gazebo_initial_observation_timeout_seconds':\s*ParameterValue\(\s*"
        r"LaunchConfiguration\('gazebo_initial_observation_timeout_seconds'\)",
        source,
    )


def test_embedded_state_machine_is_sequenced_after_controller_and_scene_readiness():
    source = PANDA_LAUNCH.read_text()

    required_dependencies = {
        'spawn_panda': 'controllers_spawner',
        'controllers_spawner': 'moveit_world_setup_node',
        'moveit_world_setup_node': 'pick_place_state_machine',
    }
    for predecessor, successor in required_dependencies.items():
        assert re.search(
            rf'OnProcessExit\(\s*target_action={predecessor},\s*'
            rf'on_exit=\[{successor}\]',
            source,
        )
