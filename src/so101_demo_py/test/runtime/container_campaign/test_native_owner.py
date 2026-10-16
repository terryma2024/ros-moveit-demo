"""Host lifecycle of one native instance: durable intent, a real group-leader subprocess, a real ready binding.

Real: the owner, the launch registry, the instance program and its control sockets in a real subprocess. Controlled
doubles: the ROS stack the instance owns and the Host ROS graph probe (see `native_instance_world`).
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

from native_instance_world import build_world
from so101_demo.runtime.container_campaign.native_owner import native_instance_environment
from so101_demo.runtime.container_campaign.registry import ContainerLaunch
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl


def environ_of(pid):
    raw = Path(f'/proc/{pid}/environ').read_bytes().split(b'\x00')
    return dict(item.decode().partition('=')[::2] for item in raw if item)


def test_start_registers_the_intent_spawns_a_group_leader_and_binds_the_ready_record(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    owner, registry = world.owner, world.registry
    async def run():
        binding = await owner.start()
        pid = owner.process.pid
        record = registry.records()[0]
        assert record['launch']['launcher'] == 'native' and record['launch']['container_name'] is None
        assert record['owner']['pid'] == pid and record['owner']['pgid'] == pid
        assert os.getpgid(pid) == pid and os.getsid(pid) == pid          # a process group and session of its own
        assert record['binding']['control_socket'] == str(world.root/'control/normal.sock')
        assert binding.container == owner.owner and binding.process == owner.owner.process_key()
        argv = json.loads((world.root/'launch-argv.json').read_text())
        assert argv['argv'][-6:] == ['--spec', str(world.spec_path), '--install-prefix', str(tmp_path),
                                     '--ros2', str(tmp_path/'host-ros/bin/ros2')]
        environment = environ_of(pid)
        assert environment['ROS_DOMAIN_ID'] == '181' and 'ROS_NAMESPACE' not in environment
        assert environment['ROS_LOCALHOST_ONLY'] == '1' and environment['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'LOCALHOST'
        assert environment['SO101_ACT_INSTANCE_ROOT'] == str(world.root)
        assert environment['SO101_ACT_INSTANCE_OUTPUT'] == str(world.root/'output')
        assert environment['SO101_MUJOCO_SESSION_ID'] == world.session and environment['TMPDIR'] == str(world.root/'tmp')
        assert await owner.check_health() is True
        provenance = json.loads((world.root/'native-instance-provenance.json').read_text())
        assert provenance['process_owner']['pid'] == pid and provenance['install_prefix'] == str(tmp_path)
        assert (world.root/'native-instance.log').is_file()
        receipt = await owner.close()
        assert receipt == dict(terminated=True, launch_id=world.launch.launch_id, errors=[])
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_the_environment_is_the_hosts_with_the_fixed_identity_on_top(tmp_path):
    base = dict(PATH='/usr/bin', AMENT_PREFIX_PATH='/opt/ros', ROS_NAMESPACE='/act/w00', ROS_DOMAIN_ID='9',
                CUDA_VISIBLE_DEVICES='3', SO101_ACT_INSTANCE_ROOT='/stale', GZ_PARTITION='stale')
    environment = native_instance_environment(base, owned_root=tmp_path, session_id='s1', gpu_uuid='GPU-x')

    assert environment['PATH'] == '/usr/bin' and environment['AMENT_PREFIX_PATH'] == '/opt/ros'
    assert 'ROS_NAMESPACE' not in environment and 'GZ_PARTITION' not in environment
    assert environment['ROS_DOMAIN_ID'] == '181' and environment['ROS_LOCALHOST_ONLY'] == '1'
    assert environment['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'LOCALHOST' and environment['MUJOCO_GL'] == 'egl'
    assert environment['SO101_MUJOCO_SESSION_ID'] == 's1' and environment['CUDA_VISIBLE_DEVICES'] == 'GPU-x'
    assert environment['SO101_ACT_INSTANCE_ROOT'] == str(tmp_path)
    assert environment['FASTRTPS_DEFAULT_PROFILES_FILE'] == '/act/install/share/so101_demo_py/config/dds/fastdds-collection.xml'
    assert 'RMW_FASTRTPS_USE_QOS_FROM_XML' not in environment
    prefixed = native_instance_environment(base, owned_root=tmp_path, session_id='s1', gpu_uuid='GPU-x', install_prefix='/opt/p')
    assert prefixed['FASTRTPS_DEFAULT_PROFILES_FILE'] == '/opt/p/share/so101_demo_py/config/dds/fastdds-collection.xml'
    assert environment['SO101_ACT_INSTANCE_OUTPUT'] == str(tmp_path/'output')
    # the same private locations a container gets
    assert environment['TMPDIR'] == str(tmp_path/'tmp') and environment['ROS_LOG_DIR'] == str(tmp_path/'ros-logs')
    assert environment['ROS_HOME'] == str(tmp_path/'tmp/ros-home') and environment['PYTHONNOUSERSITE'] == '1'
    assert base['ROS_NAMESPACE'] == '/act/w00'                          # the Host's own mapping is untouched


def test_the_instance_sees_no_desktop_display_so_that_it_renders_headless_like_a_container(tmp_path):
    # EXP-585: the Host's DISPLAY made the MuJoCo node open a GLFW window on the desktop X server ("using GLFW") instead of the
    # headless EGL context every container run used; a container has no display
    base = dict(PATH='/usr/bin', DISPLAY=':1', WAYLAND_DISPLAY='wayland-0', XAUTHORITY='/run/user/1000/gdm/Xauthority')
    environment = native_instance_environment(base, owned_root=tmp_path, session_id='s1', gpu_uuid='GPU-x')
    assert not {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'} & set(environment) and environment['PATH'] == '/usr/bin'
    assert base['DISPLAY'] == ':1'


def test_a_failed_spawn_keeps_the_intent_and_never_claims_cleanup(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError('exec failed')
    world = build_world(tmp_path, monkeypatch, popen=refuse)
    async def run():
        with pytest.raises(ValueError, match='SHARD_NATIVE_LAUNCH_FAILED'):
            await world.owner.start()
        first, second = await asyncio.gather(world.owner.close(), world.owner.close())
        assert first == second and first['terminated'] is False
        assert first['errors'][0]['reason'] == 'LAUNCH_OWNER_UNKNOWN'
        assert world.registry.records()[0]['owner'] is None
        with pytest.raises(ValueError, match='SHARD_OWNER_ALREADY_STARTED'):
            await world.owner.start()
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_an_instance_that_exits_before_ready_is_never_reported_stopped(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch, mode='die_early')
    async def run():
        with pytest.raises(ValueError, match='SHARD_NATIVE_NOT_RUNNING|SHARD_NATIVE_EXITED_BEFORE_IDENTITY'):
            await world.owner.start()
        receipt = await world.owner.close()
        # the process is gone and the group is empty, but the instance left no stop receipt of its own
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'LAUNCH_STOP_UNCONFIRMED'
        assert world.registry.records()[0]['exit_inspect'] is None
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_close_before_start_fences_the_future_launch_without_effects(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    async def run():
        assert (await world.owner.close())['terminated'] is True
        with pytest.raises(ValueError, match='SHARD_OWNER_ALREADY_STARTED'):
            await world.owner.start()
        assert world.registry.records() == () and world.owner.process is None
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_changed_spec_is_refused_before_the_durable_intent_or_any_process(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    world.spec_path.write_text('{}')
    async def run():
        with pytest.raises(ValueError, match='SHARD_SPEC_CHANGED'):
            await world.owner.start()
        assert world.registry.records() == () and world.owner.process is None
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_native_owner_refuses_a_container_launch_record(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    container = ContainerLaunch(launch_id='measurement-w00-g1', role='shard', worker_id='w00', wave_id='measurement',
        launch_generation=1, container_name='so101-x', image_digest='sha256:'+'a'*64, owned_root=str(world.root),
        session_id=world.session)
    try:
        with pytest.raises(ValueError, match='SHARD_OWNER_CONFIG_INVALID'):
            type(world.owner)(admitted_context=world.context, launch=container, entry=world.owner.entry,
                paths=world.paths, registry=world.registry, service_token=world.token, startup_timeout_s=1.,
                status_timeout_s=1., max_frame_bytes=1, stop_timeout_s=1., install_prefix=tmp_path,
                ros2_executable=tmp_path/'ros2', teacher_socket=tmp_path/'t.sock', command=['x'], base_environment={}, graph_probe=lambda: True)
    finally:
        world.cleanup()


def test_the_control_client_serves_the_four_task_operations_over_the_instances_own_socket(tmp_path, monkeypatch):
    """Real task adapter and control client against the real instance program in the real subprocess."""
    world = build_world(tmp_path, monkeypatch)
    control = ContainerTaskControl(owner=world.owner)
    async def run():
        status = await control.start()
        assert status.state == 'READY'
        polled = await control.get_status()
        assert polled.instance_id == 'measurement-w00-g1' and polled.state in ('READY', 'STARTING')
        stopped = await control.terminate('native lifecycle test')
        assert stopped.state == 'TERMINATED' and stopped.resources_released is True
        assert world.registry.records()[0]['exit_inspect']['kind'] == 'native_instance_exit'
        record = world.owner.instance_exit()
        assert record['cleanup_confirmed'] is True and record['fault_reason'] == 'native lifecycle test'
        with pytest.raises(ValueError, match='SHARD_RUNTIME_NOT_READY'):
            world.owner.control_client()
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_no_exit_record_means_no_instance_exit(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    try:
        assert world.owner.instance_exit() is None
        (world.root/'instance-exit.json').write_text('{"fault_reason": "x"}')
        assert world.owner.instance_exit() is None
    finally:
        world.cleanup()
