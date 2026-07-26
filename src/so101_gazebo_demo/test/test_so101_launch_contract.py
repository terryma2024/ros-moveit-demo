"""Public launch-argument contract for the SO-101 simulation stack."""

import importlib.util
from pathlib import Path

from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node


PACKAGE_DIR = Path(__file__).resolve().parents[1]
GAZEBO_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_gazebo.launch.py'
CONTROLLER_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_controller.launch.py'
DISPLAY_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_display.launch.py'
MOVEIT_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_moveit.launch.py'


def load_launch_description(path):
    """Load a launch description directly from source."""
    module_name = f'{path.parent.parent.name}_{path.stem}'.replace('.', '_')
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.generate_launch_description()


def declared_arguments(path):
    """Return the public argument names of a launch description."""
    description = load_launch_description(path)
    return {
        entity.name
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }


def declared_argument(path, name):
    """Return one public launch argument by name."""
    description = load_launch_description(path)
    return next(
        entity
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument) and entity.name == name
    )


def launch_default_text(argument):
    """Render a literal launch default from TextSubstitution objects."""
    return ''.join(part.text for part in argument.default_value)


def test_gazebo_uses_canonical_base_height_default():
    gazebo_default = launch_default_text(
        declared_argument(GAZEBO_LAUNCH, 'base_height')
    )
    assert gazebo_default == '0.1899186'


def test_moveit_uses_canonical_base_height_and_same_package_resources():
    """MoveIt must use the same package-local model as the simulator."""
    moveit_default = launch_default_text(
        declared_argument(MOVEIT_LAUNCH, 'base_height')
    )
    assert moveit_default == '0.1899186'

    launch_source = MOVEIT_LAUNCH.read_text()
    assert 'package_name="so101_gazebo_demo"' in launch_source
    assert 'lerobot_' not in launch_source


def test_gazebo_launch_exposes_world_and_base_height():
    """Catch a Gazebo launch that cannot select world or base height."""
    assert {'model', 'world', 'base_height'} <= declared_arguments(GAZEBO_LAUNCH)


def test_controller_and_display_launch_expose_their_public_arguments():
    assert {'is_sim'} <= declared_arguments(CONTROLLER_LAUNCH)
    assert {'model'} <= declared_arguments(DISPLAY_LAUNCH)


def test_gazebo_launch_starts_expected_controller_spawners():
    """Catch a simulation launch that leaves all controllers unloaded."""
    description = load_launch_description(GAZEBO_LAUNCH)
    spawners = {
        entity._Node__arguments[0]
        for entity in description.entities
        if isinstance(entity, Node)
        and entity.node_package == 'controller_manager'
        and entity.node_executable == 'spawner'
    }
    assert {
        'joint_state_broadcaster',
        'arm_controller',
        'gripper_controller',
    } <= spawners


def test_controller_launch_starts_expected_controller_spawners():
    description = load_launch_description(CONTROLLER_LAUNCH)
    spawners = {
        entity._Node__arguments[0]
        for entity in description.entities
        if isinstance(entity, Node)
        and entity.node_package == 'controller_manager'
        and entity.node_executable == 'spawner'
    }
    assert {
        'joint_state_broadcaster',
        'arm_controller',
        'gripper_controller',
    } <= spawners


def test_gazebo_launch_bridges_scoped_coke_contacts_to_ros_name():
    """Catch a contact sensor that is observable only on Gazebo Transport."""
    raw_topic = (
        '/world/so101_pick_place/model/coke/link/body/'
        'sensor/coke_contact_sensor/contact'
    )
    expected_argument = (
        f'{raw_topic}@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts'
    )
    description = load_launch_description(GAZEBO_LAUNCH)
    bridge = next(
        entity
        for entity in description.entities
        if isinstance(entity, Node)
        and entity.node_package == 'ros_gz_bridge'
        and entity.node_executable == 'parameter_bridge'
    )

    assert expected_argument in bridge._Node__arguments
    remappings = {
        (
            ''.join(substitution.text for substitution in source),
            ''.join(substitution.text for substitution in destination),
        )
        for source, destination in bridge._Node__remappings
    }
    assert (raw_topic, '/coke/contacts') in remappings
