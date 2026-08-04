"""Public launch-argument contract for Panda pick/place."""

import importlib.util
from pathlib import Path

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

    assert 'scope == StateParameterScope::PLAN_ONLY' in source
    assert source.index('validateRunRequest') < source.index('resolveSimulationSessionId')
