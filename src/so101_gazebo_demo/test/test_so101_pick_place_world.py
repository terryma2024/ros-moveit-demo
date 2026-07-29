"""Contract tests for the SO-101 pick-place Gazebo world."""

import ctypes
import itertools
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

import pytest
import yaml


PACKAGE_DIR = Path(__file__).resolve().parents[1]
WORLD_PATH = PACKAGE_DIR / 'worlds' / 'so101_pick_place.sdf'
XACRO_PATH = PACKAGE_DIR / 'urdf' / 'so101.urdf.xacro'
DYNAMIC_POSE_TOPIC = '/world/so101_pick_place/dynamic_pose/info'
LOAD_BEARING_COLLISIONS = (
    'collision',
    'gripper_collision',
    'gripper_collision_1',
    'jaw_collision',
    'fixed_finger_contact',
    'moving_finger_contact',
    'moving_jaw_contact',
)
RUNTIME_ROS_DOMAIN_IDS = itertools.count(100 + os.getpid() % 100)


def parse_vector(text):
    """Parse an SDF vector into floats."""
    return tuple(float(value) for value in text.split())


def model(world, name):
    """Return a named top-level model or fail with a useful message."""
    result = world.find(f"./model[@name='{name}']")
    assert result is not None, f'missing model {name}'
    return result


def joint(robot, name):
    """Return a named URDF joint or fail with a useful message."""
    result = robot.find(f"./joint[@name='{name}']")
    assert result is not None, f'missing joint {name}'
    return result


def run(command, environment, timeout=15):
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )


def isolated_runtime_environment(partition_prefix):
    """Return fresh ROS and Gazebo transport namespaces for one launch."""
    environment = os.environ.copy()
    environment.update({
        'GZ_PARTITION': f'{partition_prefix}_{uuid.uuid4().hex}',
        'ROS_DOMAIN_ID': str(next(RUNTIME_ROS_DOMAIN_IDS)),
        'ROS2CLI_DISABLE_DAEMON': '1',
    })
    return environment


def arm_parent_death_signal():
    """Make a launch process receive SIGINT if its pytest parent disappears."""
    parent_pid = os.getppid()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGINT) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if os.getppid() != parent_pid:
        os.kill(os.getpid(), signal.SIGINT)


def wait_for_ros_topics(environment, required, launch, log, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launch.poll() is not None:
            log.seek(0)
            pytest.fail(f'simulation launch exited early:\n{log.read()}')
        completed = subprocess.run(
            ['ros2', 'topic', 'list'],
            capture_output=True,
            text=True,
            timeout=5,
            env=environment,
        )
        if completed.returncode == 0 and required <= set(completed.stdout.split()):
            return
        time.sleep(0.25)
    pytest.fail(f'timed out waiting for ROS topics: {sorted(required)}')


def pose_positions(payload):
    positions = {}
    for match in re.finditer(
        r'pose \{.*?name: "([^"]+)".*?position \{(.*?)\n\s*\}',
        payload,
        re.DOTALL,
    ):
        position = []
        for axis in ('x', 'y', 'z'):
            value = re.search(rf'\b{axis}: ([^\s]+)', match.group(2))
            position.append(float(value.group(1)) if value else 0.0)
        positions[match.group(1)] = tuple(position)
    return positions


def sample_dynamic_positions(environment):
    completed = run(
        ['gz', 'topic', '-e', '-n', '1', '-t', DYNAMIC_POSE_TOPIC],
        environment,
        timeout=10,
    )
    positions = pose_positions(completed.stdout)
    assert {'coke', 'gripper'} <= positions.keys(), completed.stdout
    return positions


def sample_joint_state(environment):
    output = run(
        ['ros2', 'topic', 'echo', '/joint_states', '--once'],
        environment,
        timeout=10,
    ).stdout
    payload_start = output.find('header:')
    assert payload_start >= 0, output
    return yaml.safe_load(output[payload_start:].split('---', 1)[0])


def publish_attachment_command(environment, command):
    run(
        [
            'ros2', 'topic', 'pub', '--once',
            f'/so101/{command}_coke', 'std_msgs/msg/Empty', '{}',
        ],
        environment,
        timeout=10,
    )


def wait_for_durable_attachment_state(environment, expected, timeout=5):
    """Read the relay's periodic durable state, never the edge-triggered event."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        completed = subprocess.run(
            [
                'gz', 'topic', '-e', '-n', '1',
                '-t', '/so101/coke_attached',
            ],
            capture_output=True,
            text=True,
            timeout=2,
            env=environment,
        )
        if completed.returncode == 0 and f'data: "{expected}"' in completed.stdout:
            return completed.stdout.strip()
    pytest.fail(f'durable attachment state did not become {expected}')


def command_arm(environment, joint_1):
    message = (
        "{joint_names: ['1', '2', '3', '4', '5'], points: ["
        f"{{positions: [{joint_1}, 0.0, 0.0, 0.0, 0.0], "
        "time_from_start: {sec: 2, nanosec: 0}}]}"
    )
    run(
        [
            'ros2', 'topic', 'pub', '--once',
            '/arm_controller/joint_trajectory',
            'trajectory_msgs/msg/JointTrajectory', message,
        ],
        environment,
        timeout=15,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        sample = sample_joint_state(environment)
        position = dict(zip(sample['name'], sample['position']))
        if abs(position['1'] - joint_1) < 0.01:
            return
    pytest.fail(f'joint 1 did not reach {joint_1}')


def distance(first, second):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def relative_position(child, parent):
    return tuple(a - b for a, b in zip(child, parent))


def load_bearing_collision_failures(output):
    """Return only DART failures relevant to Coke and finger contact geometry."""
    output_without_ansi = re.sub(r'\x1b\[[0-9;]*m', '', output)
    failures = []
    for line in output_without_ansi.splitlines():
        lowered = line.lower()
        named_failure = any(
            f'collision [{name}]' in line
            and any(
                marker in lowered
                for marker in (
                    "couldn't be created",
                    'failed to create',
                    'failed to construct',
                    'unable to create',
                    'unable to construct',
                )
            )
            for name in LOAD_BEARING_COLLISIONS
        )
        primitive_dart_failure = (
            ('dart' in lowered or 'dartsim' in lowered)
            and ('cylinder' in lowered or 'box' in lowered)
            and any(
                marker in lowered
                for marker in (
                    "couldn't",
                    'failed',
                    'unable',
                    'not been implemented',
                )
            )
        )
        if named_failure or primitive_dart_failure:
            failures.append(line)
    return failures


def test_pick_place_world_has_canonical_support_and_coke_geometry():
    """Catch missing, separated, or dimensionally inconsistent geometry."""
    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    assert world is not None
    pedestal = model(world, 'base_pedestal')
    table = model(world, 'table')
    coke = model(world, 'coke')

    assert pedestal.findtext('static') == 'true'
    pedestal_pose = parse_vector(pedestal.findtext('pose'))
    pedestal_size = parse_vector(pedestal.findtext('.//box/size'))
    assert pedestal_pose == pytest.approx((0, 0, 0.17, 0, 0, 0))
    assert pedestal_size == pytest.approx((0.18, 0.18, 0.10))

    assert table.findtext('static') == 'true'
    table_pose = parse_vector(table.findtext('pose'))
    table_size = parse_vector(table.findtext('.//box/size'))
    assert table_pose == pytest.approx((0, -0.20, 0.10, 0, 0, 0))
    assert table_size == pytest.approx((0.50, 0.60, 0.04))

    coke_pose = parse_vector(coke.findtext('pose'))
    assert coke.find('static') is None
    assert coke_pose == pytest.approx((0.02, -0.28, 0.181, 0, 0, 0))
    assert float(coke.findtext('.//cylinder/radius')) == pytest.approx(0.033)
    assert float(coke.findtext('.//cylinder/length')) == pytest.approx(0.122)
    assert float(coke.findtext('.//mass')) == pytest.approx(0.1)
    assert float(coke.findtext('.//sensor/update_rate')) == pytest.approx(200.0)
    coke_collision = coke.find("./link/collision[@name='collision']")
    assert coke_collision is not None
    assert coke_collision.find('./geometry/cylinder') is not None
    assert coke_collision.find('./geometry/mesh') is None

    table_top = table_pose[2] + table_size[2] / 2
    table_rear_edge = table_pose[1] + table_size[1] / 2
    pedestal_bottom = pedestal_pose[2] - pedestal_size[2] / 2
    pedestal_top = pedestal_pose[2] + pedestal_size[2] / 2
    pedestal_rear_edge = pedestal_pose[1] + pedestal_size[1] / 2
    coke_bottom = coke_pose[2] - 0.122 / 2

    assert table_top == pytest.approx(0.12)
    assert pedestal_bottom == pytest.approx(table_top)
    assert pedestal_top == pytest.approx(0.22)
    assert coke_bottom == pytest.approx(table_top)
    assert table_rear_edge - pedestal_rear_edge == pytest.approx(0.01)


def test_pick_place_world_starts_without_system_initialization_errors():
    """Catch systems attached to unsupported SDF entities."""
    environment = os.environ.copy()
    environment['GZ_PARTITION'] = 'so101_pick_place_world_contract'
    completed = subprocess.run(
        [
            'gz',
            'sim',
            '-s',
            '-r',
            '--iterations',
            '1',
            str(WORLD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    output = completed.stdout + completed.stderr
    assert 'Failed to initialize' not in output
    assert 'should be attached to a model entity' not in output


@pytest.mark.parametrize(
    'message',
    (
        "The geometry element of collision [collision] couldn't be created",
        'Failed to construct DART collision [fixed_finger_contact]',
        'Unable to create shape for collision [moving_finger_contact]',
        'dartsim cylinder construction has not been implemented',
    ),
)
def test_load_bearing_collision_failure_scanner_covers_runtime_variants(message):
    assert load_bearing_collision_failures(message) == [message]


def prove_runtime_attachment_ready_has_no_delayed_initializer_detach():
    """Catch a startup helper that detaches a valid early client attachment."""
    environment = isolated_runtime_environment('so101_task1_ready')

    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
        launch = subprocess.Popen(
            [
                'ros2', 'launch', 'so101_gazebo_demo',
                'so101_gazebo.launch.py', 'headless:=true',
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
            preexec_fn=arm_parent_death_signal,
        )
        try:
            wait_for_ros_topics(
                environment,
                {'/so101/attach_coke'},
                launch,
                log,
            )
            readiness_observed_at = time.monotonic()
            publish_attachment_command(environment, 'attach')

            wait_for_ros_topics(
                environment,
                {
                    '/joint_states',
                    '/arm_controller/joint_trajectory',
                },
                launch,
                log,
            )
            old_initializer_window = 5.1
            time.sleep(max(
                0.0,
                old_initializer_window
                - (time.monotonic() - readiness_observed_at),
            ))

            before_motion = sample_dynamic_positions(environment)
            command_arm(environment, 0.25)
            carried = sample_dynamic_positions(environment)
            gripper_delta = distance(
                before_motion['gripper'], carried['gripper']
            )
            coke_delta = distance(before_motion['coke'], carried['coke'])
            relative_delta = distance(
                relative_position(
                    before_motion['coke'], before_motion['gripper']
                ),
                relative_position(carried['coke'], carried['gripper']),
            )

            assert gripper_delta > 0.01
            assert coke_delta > 0.01
            assert relative_delta < 0.01
            print(
                'SO101_READY_ATTACHMENT_EVIDENCE '
                f'wait_after_readiness={old_initializer_window:.1f} '
                f'gripper_delta={gripper_delta:.9f} '
                f'coke_delta={coke_delta:.9f} '
                f'relative_delta={relative_delta:.9f}'
            )
        finally:
            if launch.poll() is None:
                os.killpg(launch.pid, signal.SIGINT)
                try:
                    launch.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(launch.pid, signal.SIGKILL)
                    launch.wait(timeout=5)

        log.seek(0)
        output = log.read()
        assert not load_bearing_collision_failures(output), output
        assert 'Failed to initialize' not in output, output


def test_runtime_joint_and_detachable_joint_observation_smoke():
    """Prove finite joint evidence and physical attach/follow/detach behavior."""
    environment = isolated_runtime_environment('so101_task1')

    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
        launch = subprocess.Popen(
            [
                'ros2', 'launch', 'so101_gazebo_demo',
                'so101_gazebo.launch.py', 'headless:=true',
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
            preexec_fn=arm_parent_death_signal,
        )
        try:
            wait_for_ros_topics(
                environment,
                {
                    '/joint_states',
                    '/arm_controller/joint_trajectory',
                    '/so101/attach_coke',
                    '/so101/detach_coke',
                    '/so101/coke_attached_event',
                },
                launch,
                log,
            )

            joint_sample = sample_joint_state(environment)
            assert joint_sample['name'] == [str(number) for number in range(1, 7)]
            assert len(joint_sample['velocity']) == 6
            assert all(math.isfinite(value) for value in joint_sample['velocity'])
            durable_initial = wait_for_durable_attachment_state(
                environment, 'detached'
            )

            initial_detached = sample_dynamic_positions(environment)
            command_arm(environment, 0.25)
            detached_probe = sample_dynamic_positions(environment)
            initial_detached_gripper_delta = distance(
                initial_detached['gripper'], detached_probe['gripper']
            )
            initial_detached_coke_delta = distance(
                initial_detached['coke'], detached_probe['coke']
            )
            assert initial_detached_gripper_delta > 0.01
            assert initial_detached_coke_delta < 0.01

            command_arm(environment, 0.0)
            before_attach = sample_dynamic_positions(environment)
            publish_attachment_command(environment, 'attach')
            durable_attached = wait_for_durable_attachment_state(
                environment, 'attached'
            )
            after_attach = sample_dynamic_positions(environment)
            attach_jump = distance(before_attach['coke'], after_attach['coke'])
            assert attach_jump < 0.005

            command_arm(environment, 0.25)
            carried = sample_dynamic_positions(environment)
            carried_delta = distance(after_attach['coke'], carried['coke'])
            assert carried_delta > 0.01
            assert distance(
                relative_position(after_attach['coke'], after_attach['gripper']),
                relative_position(carried['coke'], carried['gripper']),
            ) < 0.01

            publish_attachment_command(environment, 'detach')
            durable_detached = wait_for_durable_attachment_state(
                environment, 'detached'
            )
            detached = sample_dynamic_positions(environment)
            command_arm(environment, 0.0)
            after_detached_motion = sample_dynamic_positions(environment)
            gripper_delta = distance(
                detached['gripper'], after_detached_motion['gripper']
            )
            independent_coke_delta = distance(
                detached['coke'], after_detached_motion['coke']
            )
            assert gripper_delta > 0.01
            assert independent_coke_delta < 0.01

            log.seek(0)
            startup_log = log.read()
            raw_detached = startup_log.index(
                'RAW_ATTACHMENT_EVENT state=detached'
            )
            durable_detached_log = startup_log.index(
                'DURABLE_ATTACHMENT_STATE state=detached'
            )
            bridge_started = startup_log.index(
                '[parameter_bridge-', durable_detached_log
            )
            controller_started = startup_log.index(
                '[spawner-', durable_detached_log
            )
            assert raw_detached < durable_detached_log < bridge_started
            assert raw_detached < durable_detached_log < controller_started

            print(
                'SO101_RUNTIME_EVIDENCE '
                f'velocity={joint_sample["velocity"]} '
                f'initial_detached_gripper_delta={initial_detached_gripper_delta:.9f} '
                f'initial_detached_coke_delta={initial_detached_coke_delta:.9f} '
                f'attach_jump={attach_jump:.9f} '
                f'carried_coke_delta={carried_delta:.9f} '
                f'detached_gripper_delta={gripper_delta:.9f} '
                f'detached_coke_delta={independent_coke_delta:.9f} '
                f'before_attach={before_attach["coke"]} '
                f'carried={carried["coke"]} '
                f'after_detached_motion={after_detached_motion["coke"]}'
                f' durable_initial={durable_initial!r}'
                f' durable_attached={durable_attached!r}'
                f' durable_detached={durable_detached!r}'
            )
        finally:
            if launch.poll() is None:
                os.killpg(launch.pid, signal.SIGINT)
                try:
                    launch.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(launch.pid, signal.SIGKILL)
                    launch.wait(timeout=5)

        log.seek(0)
        output = log.read()
        assert not load_bearing_collision_failures(output), output
        forbidden = (
            'Failed to initialize',
            'Failed to construct DART',
            'should be attached to a model entity',
        )
        assert not [message for message in forbidden if message in output], output


def test_pick_place_world_has_approved_gui_presentation():
    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    gui = world.find('gui')
    assert gui is not None
    assert gui.attrib['fullscreen'] == '0'

    plugins = {plugin.attrib['filename'] for plugin in gui.findall('plugin')}
    assert plugins == {
        'MinimalScene',
        'GzSceneManager',
        'InteractiveViewControl',
        'CameraTracking',
        'SelectEntities',
        'WorldControl',
        'WorldStats',
        'EntityTree',
        'ViewAngle',
        'Screenshot',
    }

    scene = gui.find("./plugin[@filename='MinimalScene']")
    assert scene.findtext('engine') == 'ogre2'
    assert parse_vector(scene.findtext('ambient_light')) == pytest.approx(
        (0.4, 0.4, 0.4)
    )
    assert parse_vector(scene.findtext('background_color')) == pytest.approx(
        (0.8, 0.8, 0.8)
    )
    assert scene.findtext('camera_pose') == '0.4281 0.2175 0.4608 0 0.4 -2.3'
    assert scene.find('horizontal_fov') is None


@pytest.mark.parametrize(
    'filename',
    (
        'GzSceneManager',
        'InteractiveViewControl',
        'CameraTracking',
        'SelectEntities',
    ),
)
def test_pick_place_world_keeps_service_plugins_compact(filename):
    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    plugin = world.find(f"./gui/plugin[@filename='{filename}']")
    assert plugin is not None

    panel = plugin.find('gz-gui')
    assert panel is not None
    properties = {
        prop.attrib['key']: (prop.attrib['type'], prop.text)
        for prop in panel.findall('property')
    }
    assert properties == {
        'resizable': ('bool', 'false'),
        'width': ('double', '5'),
        'height': ('double', '5'),
        'state': ('string', 'floating'),
        'showTitleBar': ('bool', 'false'),
    }


def test_xacro_places_base_mesh_on_pedestal_without_changing_tcp():
    """Catch a base-frame/mesh offset gap or accidental TCP drift."""
    completed = subprocess.run(
        ['xacro', str(XACRO_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    robot = ET.fromstring(completed.stdout)
    base_origin = joint(robot, 'base_joint').find('origin')
    tcp_origin = joint(robot, 'so101_tcp_joint').find('origin')

    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    pedestal = model(world, 'base_pedestal')
    pedestal_pose = parse_vector(pedestal.findtext('pose'))
    pedestal_size = parse_vector(pedestal.findtext('.//box/size'))
    pedestal_top = pedestal_pose[2] + pedestal_size[2] / 2

    # Lowest transformed vertex of the base link's visual/collision meshes.
    base_mesh_bottom_from_base_frame = 0.0300814
    expected_base_z = pedestal_top - base_mesh_bottom_from_base_frame
    base_xyz = parse_vector(base_origin.attrib['xyz'])

    assert base_xyz == pytest.approx((0, 0, expected_base_z))
    assert base_xyz[2] + base_mesh_bottom_from_base_frame == pytest.approx(
        pedestal_top
    )
    assert parse_vector(tcp_origin.attrib['xyz']) == pytest.approx(
        (0.0214, 0, -0.083949)
    )
    assert parse_vector(tcp_origin.attrib['rpy']) == pytest.approx((0, 0, 0))
