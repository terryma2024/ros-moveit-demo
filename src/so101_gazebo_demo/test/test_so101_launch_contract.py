"""Public launch-argument contract for the SO-101 simulation stack."""

import importlib.util
import inspect
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import pytest
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node


PACKAGE_DIR = Path(__file__).resolve().parents[1]
GAZEBO_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_gazebo.launch.py'
CONTROLLER_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_controller.launch.py'
DISPLAY_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_display.launch.py'
MOVEIT_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_moveit.launch.py'
PICK_PLACE_WORLD_TEST = PACKAGE_DIR / 'test' / 'test_so101_pick_place_world.py'


def load_launch_module(path):
    """Load a launch module directly from source."""
    module_name = f'{path.parent.parent.name}_{path.stem}'.replace('.', '_')
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_launch_description(path):
    """Load a launch description directly from source."""
    return load_launch_module(path).generate_launch_description()


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
    assert {'model', 'world', 'base_height', 'headless'} <= declared_arguments(
        GAZEBO_LAUNCH
    )


def test_controller_and_display_launch_expose_their_public_arguments():
    assert {'is_sim'} <= declared_arguments(CONTROLLER_LAUNCH)
    assert {'model'} <= declared_arguments(DISPLAY_LAUNCH)


def test_gazebo_launch_starts_expected_controller_spawners():
    """Catch a simulation launch that leaves all controllers unloaded."""
    module = load_launch_module(GAZEBO_LAUNCH)
    spawners = {
        entity._Node__arguments[0]
        for entity in module.controller_spawner_nodes()
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
    module = load_launch_module(GAZEBO_LAUNCH)
    bridge = module.attachment_bridge_node()

    assert expected_argument in bridge._Node__arguments
    remappings = {
        (
            ''.join(substitution.text for substitution in source),
            ''.join(substitution.text for substitution in destination),
        )
        for source, destination in bridge._Node__remappings
    }
    assert (raw_topic, '/coke/contacts') in remappings


def test_gazebo_launch_bridges_only_attachment_commands_and_raw_event():
    """Catch attachment topics that later ROS consumers cannot observe or drive."""
    module = load_launch_module(GAZEBO_LAUNCH)
    bridge = module.attachment_bridge_node()

    assert {
        '/so101/attach_coke@std_msgs/msg/Empty]gz.msgs.Empty',
        '/so101/detach_coke@std_msgs/msg/Empty]gz.msgs.Empty',
        '/so101/coke_attached_event@std_msgs/msg/String[gz.msgs.StringMsg',
    } <= set(bridge._Node__arguments)
    assert not any('/pose/info@' in argument for argument in bridge._Node__arguments)


def test_initial_detach_helper_is_bounded_without_gazebo_plugin_subscription():
    """Catch an initialization helper that can wait forever for Gazebo."""
    module = load_launch_module(GAZEBO_LAUNCH)
    assert hasattr(module, 'initial_detach_command')

    environment = os.environ.copy()
    environment['GZ_PARTITION'] = f'so101_missing_plugin_{uuid.uuid4().hex}'
    started = time.monotonic()
    completed = subprocess.run(
        module.initial_detach_command(),
        capture_output=True,
        text=True,
        timeout=12,
        env=environment,
    )
    elapsed = time.monotonic() - started

    assert completed.returncode == 124
    assert 7 <= elapsed < 10


def test_initial_detach_command_without_raw_detached_event_fails_closed(tmp_path):
    """A delivered command is not proof that the detachable joint changed state."""
    module = load_launch_module(GAZEBO_LAUNCH)
    environment = os.environ.copy()
    marker = tmp_path / 'detach-command-observed'
    fake_gz = tmp_path / 'gz'
    fake_gz.write_text(
        '#!/bin/sh\n'
        'case "$*" in\n'
        '  *"topic -i -t /so101/coke_attached_event"*)\n'
        '    echo "Subscribers [fake-relay]" ;;\n'
        '  *"topic -i -t /so101/detach_coke"*)\n'
        '    echo "Subscribers [fake-plugin]" ;;\n'
        '  *"topic -t /so101/detach_coke"*)\n'
        '    : > "$SO101_DETACH_MARKER" ;;\n'
        '  *"topic -e -t /so101/coke_attached"*)\n'
        '    exit 0 ;;\n'
        'esac\n'
    )
    fake_gz.chmod(0o755)
    environment['PATH'] = f'{tmp_path}:{environment["PATH"]}'
    environment['SO101_DETACH_MARKER'] = str(marker)

    completed = subprocess.run(
        module.initial_detach_command(timeout_seconds=2),
        capture_output=True,
        text=True,
        timeout=4,
        env=environment,
    )

    assert marker.exists(), 'detach command must have been delivered in this scenario'
    assert completed.returncode == 124


def test_launch_starts_relay_before_initial_detach_and_gates_on_durable_state():
    """Lock the evidence chain: subscribe raw -> command -> raw event -> durable state."""
    module = load_launch_module(GAZEBO_LAUNCH)
    source = inspect.getsource(module.generate_launch_description)
    command = ' '.join(module.initial_detach_command(timeout_seconds=2))

    assert 'OnProcessStart' in source
    assert 'target_action=attachment_state_relay' in source
    assert '/so101/coke_attached_event' in command
    assert '/so101/coke_attached' in command
    assert 'detached' in command


def test_failed_prerequisite_stops_before_downstream_readiness_actions():
    """Catch spawn/init failure paths that still expose public readiness."""
    module = load_launch_module(GAZEBO_LAUNCH)
    assert hasattr(module, 'actions_after_success_or_shutdown')
    readiness_action = object()

    actions = module.actions_after_success_or_shutdown(
        SimpleNamespace(returncode=23),
        [readiness_action],
        'robot spawn',
    )

    assert readiness_action not in actions
    assert any(action.__class__.__name__ == 'EmitEvent' for action in actions)


def test_runtime_launch_child_exits_when_pytest_parent_is_terminated():
    """Catch CTest timeout cleanup that leaves an orphan simulation session."""
    runtime = load_launch_module(PICK_PLACE_WORLD_TEST)
    assert hasattr(runtime, 'arm_parent_death_signal')
    supervisor_script = f"""
import importlib.util
import signal
import subprocess

spec = importlib.util.spec_from_file_location(
    'so101_runtime_cleanup',
    {str(PICK_PLACE_WORLD_TEST)!r},
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
child = subprocess.Popen(
    ['/bin/sleep', '30'],
    start_new_session=True,
    preexec_fn=module.arm_parent_death_signal,
)
print(child.pid, flush=True)
signal.pause()
"""
    supervisor = subprocess.Popen(
        [sys.executable, '-c', supervisor_script],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    child_pid = int(supervisor.stdout.readline())
    try:
        os.kill(supervisor.pid, signal.SIGTERM)
        supervisor.wait(timeout=5)

        deadline = time.monotonic() + 5
        child_proc = Path(f'/proc/{child_pid}')
        while child_proc.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not child_proc.exists()
    finally:
        if supervisor.poll() is None:
            os.kill(supervisor.pid, signal.SIGKILL)
            supervisor.wait(timeout=5)
        if Path(f'/proc/{child_pid}').exists():
            os.kill(child_pid, signal.SIGKILL)


def test_runtime_attachment_ready_has_no_delayed_initializer_detach():
    """Keep early valid attachment after the old five-second window."""
    runtime = load_launch_module(PICK_PLACE_WORLD_TEST)
    runtime.prove_runtime_attachment_ready_has_no_delayed_initializer_detach()
