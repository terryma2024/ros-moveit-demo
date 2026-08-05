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
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.utilities import perform_substitutions
from launch_ros.actions import Node


PACKAGE_DIR = Path(__file__).resolve().parents[1]
GAZEBO_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_gazebo.launch.py'
CONTROLLER_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_controller.launch.py'
DISPLAY_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_display.launch.py'
MOVEIT_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_moveit.launch.py'
MOVE_GROUP_HEADLESS_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_move_group_headless.launch.py'
PICK_PLACE_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_pick_place.launch.py'
PICK_PLACE_WORLD_TEST = PACKAGE_DIR / 'test' / 'test_so101_pick_place_world.py'
TELEOP_LAUNCH = PACKAGE_DIR / 'launch' / 'so101_teleop.launch.py'


@pytest.mark.parametrize('launch_path', [MOVEIT_LAUNCH, MOVE_GROUP_HEADLESS_LAUNCH])
def test_move_group_allows_low_speed_simulation_execution_jitter(launch_path):
    source = launch_path.read_text()
    assert '"trajectory_execution.allowed_execution_duration_scaling": 1.5' in source
    assert '"trajectory_execution.allowed_goal_duration_margin": 1.0' in source


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


def test_teleop_launch_is_explicitly_simulation_only_and_never_wildcard_bound():
    arguments = {
        entity.name: launch_default_text(entity)
        for entity in load_launch_description(TELEOP_LAUNCH).entities
        if isinstance(entity, DeclareLaunchArgument)
    }

    assert arguments['bind_address'] == '127.0.0.1'
    assert arguments['simulation_only'] == 'true'
    assert arguments['bind_address'] != '0.0.0.0'
    assert {'port', 'world_name', 'tcp_frame', 'simulation_session_id'} <= set(arguments)


def test_teleop_launch_declares_web_preflight_and_defers_server_node():
    description = load_launch_description(TELEOP_LAUNCH)
    arguments = {
        entity.name: launch_default_text(entity)
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    assert arguments['build_web_if_needed'] == 'true'
    assert arguments['web_source_dir'] == ''
    assert 'gz_partition' in arguments
    assert any(isinstance(entity, OpaqueFunction) for entity in description.entities)
    assert not any(isinstance(entity, Node) for entity in description.entities)
    assert 'name="so101_teleop_server_process"' not in TELEOP_LAUNCH.read_text()


def test_teleop_launch_preflight_completes_before_server_node(monkeypatch, tmp_path):
    module = load_launch_module(TELEOP_LAUNCH)
    source = tmp_path / 'web'
    source.mkdir()
    (source / 'package.json').write_text('{}')
    dist = source / 'dist'
    dist.mkdir()
    called = []
    monkeypatch.setattr(module, 'ensure_web_bundle', lambda path, build_if_needed: called.append((Path(path), build_if_needed)) or dist)
    context = LaunchContext()
    context.launch_configurations.update({
        'bind_address': '127.0.0.1', 'port': '8000', 'world_name': 'world',
        'tcp_frame': 'tcp', 'simulation_session_id': 'session',
        'gz_partition': 'camera-test-partition',
        'web_source_dir': str(source), 'build_web_if_needed': 'true',
    })
    nodes = module.launch_setup(context)
    assert called == [(source, True)]
    assert len(nodes) == 1 and isinstance(nodes[0], Node)
    process = vars(nodes[0])['_ExecuteLocal__process_description']
    additional_env = {
        perform_substitutions(context, key): perform_substitutions(context, value)
        for key, value in vars(process)['_Executable__additional_env']
    }
    assert additional_env['SO101_TELEOP_WEB_ROOT'] == str(dist)
    assert additional_env['GZ_PARTITION'] == 'camera-test-partition'


def test_teleop_launch_preflight_failure_prevents_server_node(monkeypatch, tmp_path):
    module = load_launch_module(TELEOP_LAUNCH)
    source = tmp_path / 'web'
    source.mkdir()
    (source / 'package.json').write_text('{}')
    monkeypatch.setattr(module, 'ensure_web_bundle', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('build failed')))
    context = LaunchContext()
    context.launch_configurations.update({
        'bind_address': '127.0.0.1', 'port': '8000', 'world_name': 'world',
        'tcp_frame': 'tcp', 'simulation_session_id': 'session',
        'gz_partition': 'camera-test-partition',
        'web_source_dir': str(source), 'build_web_if_needed': 'true',
    })
    with pytest.raises(RuntimeError, match='build failed'):
        module.launch_setup(context)


def test_gazebo_uses_canonical_base_height_default():
    gazebo_default = launch_default_text(
        declared_argument(GAZEBO_LAUNCH, 'base_height')
    )
    assert gazebo_default == '0.1899186'


def test_pick_place_runtime_launch_is_safe_by_default_and_wires_all_cli_gates():
    description = load_launch_description(PICK_PLACE_LAUNCH)
    arguments = {
        entity.name: launch_default_text(entity)
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    assert arguments['run_mode'] == 'dry_run'
    assert arguments['start_simulation'] == 'false'
    assert arguments['headless'] == 'false'
    assert arguments['plan_only_state'] == ''
    assert {'stop_after', 'resume', 'checkpoint_path', 'simulation_session_id'} <= set(arguments)

    runtime = next(
        entity
        for entity in description.entities
        if isinstance(entity, Node)
        and entity.node_package == 'so101_gazebo_demo'
        and entity.node_executable == 'pick_place_state_machine'
    )
    source = PICK_PLACE_LAUNCH.read_text()
    assert '--mode' in source
    assert '--plan-only-state' in source
    assert '--checkpoint' in source
    assert '--session-id' in source
    assert '"headless": headless, "object_config": object_config' in source
    assert (
        'docs/pick-place-launch-parameters.md'
        in declared_argument(PICK_PLACE_LAUNCH, 'plan_only_state').description
    )


def test_pick_place_cli_exposes_plan_only_state_and_uses_it_for_provenance():
    source = (
        PACKAGE_DIR / 'src' / 'pick_place' / 'pick_place_state_machine.cpp'
    ).read_text()
    assert '--plan-only-state STATE' in source
    assert 'options->request.plan_only_state.value_or(' in source


def test_pick_place_runtime_launch_wires_three_independent_installed_policy_files():
    description = load_launch_description(PICK_PLACE_LAUNCH)
    arguments = {
        entity.name: launch_default_text(entity)
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }

    assert arguments['object_config'].endswith(
        '/config/task_objects/light_plastic_cup.yaml'
    )
    assert arguments['motion_policy'].endswith(
        '/config/motion_policies/light_cup_wall_pick.yaml'
    )
    assert arguments['validation_policy'].endswith(
        '/config/validation_policies/light_cup_wall_pick.yaml'
    )
    source = PICK_PLACE_LAUNCH.read_text()
    assert '--object-config' in source
    assert '--motion-policy' in source
    assert '--validation-policy' in source


def test_pick_place_runtime_strips_ros_arguments_before_cli_parsing():
    source = (
        PACKAGE_DIR / 'src' / 'pick_place' / 'pick_place_state_machine.cpp'
    ).read_text()
    assert 'rclcpp::remove_ros_arguments(argc, argv)' in source


def test_moveit_uses_canonical_base_height_and_same_package_resources():
    """MoveIt must use the same package-local model as the simulator."""
    moveit_default = launch_default_text(
        declared_argument(MOVEIT_LAUNCH, 'base_height')
    )
    assert moveit_default == '0.1899186'

    launch_source = MOVEIT_LAUNCH.read_text()
    assert 'package_name="so101_gazebo_demo"' in launch_source
    assert 'lerobot_' not in launch_source


def test_moveit_descriptions_load_the_same_configured_adapter_geometry():
    object_suffix = '/config/task_objects/light_plastic_cup.yaml'
    for launch_path in (MOVEIT_LAUNCH, MOVE_GROUP_HEADLESS_LAUNCH):
        assert 'object_config' in declared_arguments(launch_path)
        assert launch_default_text(
            declared_argument(launch_path, 'object_config')
        ).endswith(object_suffix)
        source = launch_path.read_text()
        assert '"object_config": LaunchConfiguration("object_config")' in source


def test_gazebo_launch_exposes_world_and_base_height():
    """Catch a Gazebo launch that cannot select world or base height."""
    assert {'model', 'world', 'base_height', 'headless', 'object_config'} <= declared_arguments(
        GAZEBO_LAUNCH
    )


def test_gazebo_launch_selects_bullet_featherstone_for_gui_and_headless():
    """Catch either server mode silently falling back to the default engine."""
    module = load_launch_module(GAZEBO_LAUNCH)

    assert module.physics_engine_arguments() == [
        '--physics-engine',
        'gz-physics-bullet-featherstone-plugin',
    ]
    source = inspect.getsource(module.generate_launch_description)
    assert source.count('physics_engine_arguments()') == 2


def test_gazebo_launch_prepares_vhacd_sdf_before_file_spawn():
    """Catch a return to direct URDF spawn, which strips mesh optimization."""
    module = load_launch_module(GAZEBO_LAUNCH)
    command = module.simulation_model_preparation_command(
        '/tmp/source.xacro', '/tmp/model.sdf', '0.1899186', '/tmp/object.yaml'
    )

    assert any('prepare_simulation_model.py' in str(part) for part in command)
    assert command.count('--manifest') == 2
    manifests = [command[index + 1] for index, part in enumerate(command) if part == '--manifest']
    assert any(str(path).endswith('fixed_finger_contact/manifest.json') for path in manifests)
    assert any(str(path).endswith('moving_jaw_contact/manifest.json') for path in manifests)
    assert '--max-convex-hulls' not in command
    assert '--voxel-resolution' not in command
    assert command[-2:] == ['--object-config', '/tmp/object.yaml']
    source = inspect.getsource(module.generate_launch_description)
    assert 'target_action=simulation_model_preparation' in source
    assert 'arguments=["-file", simulation_model_path' in source


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


def test_gazebo_launch_bridges_scoped_task_object_contacts_to_ros_name():
    """Catch a contact sensor that is observable only on Gazebo Transport."""
    module = load_launch_module(GAZEBO_LAUNCH)
    bridge = module.attachment_bridge_node()

    assert len(module.TASK_OBJECT_CONTACT_GZ_TOPICS) == 13
    assert all('/model/plastic_cup/' in topic for topic in module.TASK_OBJECT_CONTACT_GZ_TOPICS)
    expected_arguments = {
        f'{topic}@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts'
        for topic in module.TASK_OBJECT_CONTACT_GZ_TOPICS
    }
    assert expected_arguments <= set(bridge._Node__arguments)
    remappings = {
        (
            ''.join(substitution.text for substitution in source),
            ''.join(substitution.text for substitution in destination),
        )
        for source, destination in bridge._Node__remappings
    }
    assert {
        (topic, '/task_object/contacts')
        for topic in module.TASK_OBJECT_CONTACT_GZ_TOPICS
    } <= remappings


def test_gazebo_launch_bridges_attachment_commands_and_teleop_world_observation():
    """Catch telemetry sources that remain trapped in Gazebo Transport."""
    module = load_launch_module(GAZEBO_LAUNCH)
    bridge = module.attachment_bridge_node()

    assert {
        '/so101/attach_object@std_msgs/msg/Empty]gz.msgs.Empty',
        '/so101/detach_object@std_msgs/msg/Empty]gz.msgs.Empty',
        '/so101/object_attached_event@std_msgs/msg/String[gz.msgs.StringMsg',
    } <= set(bridge._Node__arguments)
    assert any('/pose/info@tf2_msgs/msg/TFMessage' in argument
               for argument in bridge._Node__arguments)
    assert any('/stats@ros_gz_interfaces/msg/WorldStatistics' in argument
               for argument in bridge._Node__arguments)


def test_initial_detach_helper_is_bounded_without_gazebo_plugin_subscription():
    """Catch an initialization helper that can wait forever for Gazebo."""
    module = load_launch_module(GAZEBO_LAUNCH)
    assert hasattr(module, 'initial_detach_command')

    environment = os.environ.copy()
    environment['GZ_PARTITION'] = f'so101_missing_plugin_{uuid.uuid4().hex}'
    started = time.monotonic()
    completed = subprocess.run(
        module.initial_detach_command(timeout_seconds=2),
        capture_output=True,
        text=True,
        timeout=12,
        env=environment,
    )
    elapsed = time.monotonic() - started

    assert completed.returncode == 124
    assert 1 <= elapsed < 4


def test_initial_detach_command_without_durable_detached_state_fails_closed(tmp_path):
    """A delivered command is not proof that the detachable joint changed state."""
    module = load_launch_module(GAZEBO_LAUNCH)
    environment = os.environ.copy()
    marker = tmp_path / 'detach-command-observed'
    fake_gz = tmp_path / 'gz'
    fake_gz.write_text(
        '#!/bin/sh\n'
        'case "$*" in\n'
        '  *"topic -i -t /so101/object_attached_event"*)\n'
        '    echo "Subscribers [fake-relay]" ;;\n'
        '  *"topic -i -t /so101/detach_object"*)\n'
        '    echo "Subscribers [fake-plugin]" ;;\n'
        '  *"topic -t /so101/detach_object"*)\n'
        '    : > "$SO101_DETACH_MARKER" ;;\n'
        '  *"topic -e -t /so101/object_attached"*)\n'
        '    if [ -e "$SO101_DETACH_MARKER" ]; then exit 0; '
        'else echo "data: attached"; fi ;;\n'
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


def test_attachment_relay_ready_rejects_foreign_gz_subscriber_without_own_signal(tmp_path):
    """A foreign raw-topic subscriber cannot release spawn for this relay."""
    module = load_launch_module(GAZEBO_LAUNCH)
    environment = os.environ.copy()
    foreign_subscriber = tmp_path / 'foreign-subscriber-observed'
    fake_gz = tmp_path / 'gz'
    fake_gz.write_text(
        '#!/bin/sh\n'
        ': > "$SO101_FOREIGN_SUBSCRIBER"\n'
        'echo "Subscribers [foreign-default-partition-consumer]"\n'
    )
    fake_gz.chmod(0o755)
    fake_ros2 = tmp_path / 'ros2'
    fake_ros2.write_text(
        '#!/bin/sh\n'
        'sleep 5\n'
    )
    fake_ros2.chmod(0o755)
    environment['PATH'] = f'{tmp_path}:{environment["PATH"]}'
    environment['SO101_FOREIGN_SUBSCRIBER'] = str(foreign_subscriber)

    foreign = subprocess.run(
        ['gz', 'topic', '-i', '-t', '/so101/object_attached_event'],
        capture_output=True,
        text=True,
        timeout=2,
        env=environment,
    )

    completed = subprocess.run(
        module.attachment_relay_ready_command(timeout_seconds=1),
        capture_output=True,
        text=True,
        timeout=4,
        env=environment,
    )

    assert foreign.returncode == 0
    assert 'foreign-default-partition-consumer' in foreign.stdout
    assert foreign_subscriber.exists(), 'test setup must provide foreign evidence'
    assert completed.returncode == 124


def test_launch_starts_relay_before_initial_detach_and_gates_on_durable_state():
    """Lock the evidence chain: raw relay -> durable attach -> command -> detach."""
    module = load_launch_module(GAZEBO_LAUNCH)
    source = inspect.getsource(module.generate_launch_description)
    command = ' '.join(module.initial_detach_command(timeout_seconds=2))

    assert 'OnProcessStart' in source
    assert 'target_action=attachment_state_relay' in source
    assert '/so101/object_attached' in command
    assert 'detached' in command
    assert command.index('topic -e -t /so101/object_attached') < command.index(
        'topic -t /so101/detach_object'
    )


def test_spawn_waits_for_attachment_relay_transport_subscription():
    """Catch the CP35I race where spawn can publish before relay subscription."""
    module = load_launch_module(GAZEBO_LAUNCH)
    description = module.generate_launch_description()
    handlers = [
        entity.event_handler
        for entity in description.entities
        if entity.__class__.__name__ == 'RegisterEventHandler'
    ]

    def event_target(handler):
        return vars(handler)['_OnActionEventBase__action_matcher']

    def actions_on_success(handler):
        callback = vars(handler).get('_OnActionEventBase__on_event')
        if callback is not None:
            return list(callback(SimpleNamespace(returncode=0), None))
        return list(vars(handler)['_OnActionEventBase__actions_on_event'])

    def is_node(action, package, executable):
        return (
            isinstance(action, Node)
            and action.node_package == package
            and action.node_executable == executable
        )

    relay_starters = [
        handler
        for handler in handlers
        if any(
            is_node(action, 'so101_gazebo_demo', 'gazebo_attachment_state_relay')
            for action in actions_on_success(handler)
        )
    ]
    assert relay_starters, 'the relay must be a launch action before spawn'
    relay = next(
        action
        for action in actions_on_success(relay_starters[0])
        if is_node(action, 'so101_gazebo_demo', 'gazebo_attachment_state_relay')
    )
    relay_parameters = {
        ''.join(part.text for part in key): ''.join(part.text for part in value)
        for parameter_set in relay._Node__parameters
        for key, value in parameter_set.items()
    }
    ready_topic = relay_parameters['ready_topic'].splitlines()[0]
    assert ready_topic.startswith('/so101/object_attachment_relay_ready_')

    relay_ready_starters = [
        handler
        for handler in handlers
        if handler.__class__.__name__ == 'OnProcessStart'
        and event_target(handler) is relay
        and any(isinstance(action, ExecuteProcess) for action in actions_on_success(handler))
    ]
    assert relay_ready_starters, 'relay start must begin a pre-spawn readiness gate'
    ready_action = next(
        action
        for action in actions_on_success(relay_ready_starters[0])
        if isinstance(action, ExecuteProcess)
    )
    spawn_starters = [
        handler
        for handler in handlers
        if handler.__class__.__name__ == 'OnProcessExit'
        and event_target(handler) is ready_action
        and any(
            is_node(action, 'ros_gz_sim', 'create')
            for action in actions_on_success(handler)
        )
    ]
    assert spawn_starters, 'spawn must wait for relay transport readiness to exit cleanly'

    command = ' '.join(
        ''.join(part.text for part in command_part)
        for command_part in vars(ready_action)['_ExecuteLocal__process_description']
        ._Executable__cmd
    )
    assert command.startswith('/usr/bin/timeout --signal=TERM --kill-after=1 120')
    assert 'ros2 topic echo --once' in command
    assert '--qos-durability transient_local' in command
    assert ready_topic in command
    assert 'std_msgs/msg/Empty' in command


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
