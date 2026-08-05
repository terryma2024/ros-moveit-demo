"""Public launch-argument contract for Panda pick/place."""

import importlib.util
from pathlib import Path
import re

from launch.actions import DeclareLaunchArgument


PANDA_LAUNCH = Path(__file__).resolve().parents[1] / 'launch' / 'panda_gazebo.launch.py'


def load_launch_description(path):
    spec = importlib.util.spec_from_file_location('panda_gazebo_launch', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.generate_launch_description()


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
