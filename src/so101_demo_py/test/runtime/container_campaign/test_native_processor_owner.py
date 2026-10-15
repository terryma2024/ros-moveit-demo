"""Host lifecycle of one native processor: durable intent, a real group-leader subprocess, a real ready binding, a stop proof by
the absence of its process tree.

Real: the owner, the launch registry, the processor program and its control sockets in a real subprocess (`native_processor_world`).
A processor has no ROS graph, so the graph reading of the exit proof is vacuously clear.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest

from native_processor_world import build_world
from so101_demo.runtime.container_campaign.native_processor_owner import native_processor_environment
from so101_demo.runtime.container_campaign.registry import ContainerLaunch
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl


def environ_of(pid):
    raw = Path(f'/proc/{pid}/environ').read_bytes().split(b'\x00')
    return dict(item.decode().partition('=')[::2] for item in raw if item)


def test_start_registers_the_intent_spawns_a_group_leader_and_binds_the_ready_record(tmp_path):
    world = build_world(tmp_path)
    owner, registry = world.owner, world.registry

    async def run():
        binding = await owner.start()
        pid = owner.process.pid
        record = registry.records()[0]
        assert record['launch']['role'] == 'processor' and record['launch']['launcher'] == 'native'
        assert record['launch']['container_name'] is None and record['launch']['launch_id'] == 'processing-p00-g1'
        assert record['owner']['pid'] == pid and record['owner']['pgid'] == pid
        assert os.getpgid(pid) == pid and os.getsid(pid) == pid
        assert record['binding']['control_socket'] == str(world.root/'control/normal.sock')
        assert binding.container == owner.owner and binding.process == owner.owner.process_key()
        argv = json.loads((world.root/'launch-argv.json').read_text())
        assert argv['argv'][-4:] == ['--spec', str(world.spec_path), '--install-prefix', str(tmp_path)]
        environment = environ_of(pid)
        assert environment['SO101_ACT_INSTANCE_ROOT'] == str(world.root) and environment['TMPDIR'] == str(world.root/'tmp')
        assert not {'ROS_DOMAIN_ID', 'ROS_NAMESPACE', 'SO101_MUJOCO_SESSION_ID'} & set(environment), 'no ROS identity'
        assert (world.root/'processor-ready.json').is_file()
        assert await owner.check_health() is True
        assert json.loads((world.root/'native-processor-provenance.json').read_text())['process_owner']['pid'] == pid
        receipt = await owner.close()
        assert receipt == dict(terminated=True, launch_id='processing-p00-g1', errors=[])
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_the_environment_is_the_hosts_without_a_ros_identity_a_display_or_a_gpu(tmp_path):
    base = dict(PATH='/usr/bin', AMENT_PREFIX_PATH='/opt/ros', ROS_NAMESPACE='/act/w00', ROS_DOMAIN_ID='9', CUDA_VISIBLE_DEVICES='3',
                SO101_ACT_INSTANCE_ROOT='/stale', DISPLAY=':1')
    environment = native_processor_environment(base, owned_root=tmp_path)
    assert environment['PATH'] == '/usr/bin' and environment['AMENT_PREFIX_PATH'] == '/opt/ros'
    assert not {'ROS_NAMESPACE', 'ROS_DOMAIN_ID', 'DISPLAY'} & set(environment)
    assert environment['CUDA_VISIBLE_DEVICES'] == '', 'a processor sees no GPU, as in its container'
    assert environment['SO101_ACT_INSTANCE_ROOT'] == str(tmp_path) and environment['TMPDIR'] == str(tmp_path/'tmp')
    assert environment['ROS_LOG_DIR'] == str(tmp_path/'ros-logs') and environment['PYTHONNOUSERSITE'] == '1'
    assert base['ROS_DOMAIN_ID'] == '9'


def test_close_proves_the_stop_by_the_absence_of_the_process_tree(tmp_path):
    world = build_world(tmp_path)

    async def run():
        await world.owner.start()
        pid = world.owner.process.pid
        assert (await world.owner.close())['terminated'] is True
        observed = json.loads((world.root/'final-exit.json').read_text())
        assert observed['leader_state'] in ('absent', 'zombie', 'replaced') and observed['group_members'] == []
        assert observed['marker_survivors'] == [] and observed['graph_clear'] is True and observed['pid'] == pid
        assert world.registry.records()[0]['exit_inspect'] == observed
        assert world.owner.instance_exit()['cleanup_confirmed'] is True
        assert (await world.owner.prove_stopped())['terminated'] is True and (world.root/'late-exit-proof.json').is_file()
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_stray_that_outlives_the_processor_makes_the_stop_unconfirmed_for_good(tmp_path):
    world = build_world(tmp_path, mode='orphan')

    async def run():
        await world.owner.start()
        receipt = await world.owner.close()
        assert receipt['terminated'] is False and receipt['errors'][0]['reason'] == 'SHARD_NATIVE_LEFTOVERS_TERMINATED'
        assert (world.root/'native-leftovers.json').is_file()
        assert (await world.owner.prove_stopped())['terminated'] is False
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_failed_spawn_keeps_the_intent_and_never_claims_cleanup(tmp_path):
    def refuse(*args, **kwargs):
        raise OSError('exec failed')
    world = build_world(tmp_path, popen=refuse)

    async def run():
        with pytest.raises(ValueError, match='PROCESSOR_NATIVE_LAUNCH_FAILED'):
            await world.owner.start()
        first, second = await asyncio.gather(world.owner.close(), world.owner.close())
        assert first == second and first['terminated'] is False and first['errors'][0]['reason'] == 'LAUNCH_OWNER_UNKNOWN'
        assert world.registry.records()[0]['owner'] is None
        with pytest.raises(ValueError, match='PROCESSOR_OWNER_ALREADY_STARTED'):
            await world.owner.start()
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_processor_that_exits_before_ready_is_never_reported_stopped_by_signal_alone(tmp_path):
    world = build_world(tmp_path, mode='die_early')

    async def run():
        with pytest.raises(ValueError, match='NOT_RUNNING|EXITED_BEFORE_IDENTITY'):
            await world.owner.start()
        receipt = await world.owner.close()
        assert world.registry.records()[0]['launch']['role'] == 'processor'
        assert receipt['launch_id'] == 'processing-p00-g1'
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_close_before_start_fences_the_future_launch_without_effects(tmp_path):
    world = build_world(tmp_path)

    async def run():
        assert (await world.owner.close())['terminated'] is True
        with pytest.raises(ValueError, match='PROCESSOR_OWNER_ALREADY_STARTED'):
            await world.owner.start()
        assert world.registry.records() == () and world.owner.process is None
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_changed_spec_is_refused_before_the_durable_intent_or_any_process(tmp_path):
    world = build_world(tmp_path)
    world.spec_path.write_text('{}')

    async def run():
        with pytest.raises(ValueError, match='PROCESSOR_SPEC_CHANGED'):
            await world.owner.start()
        assert world.registry.records() == () and world.owner.process is None
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_a_native_processor_owner_refuses_a_container_or_shard_launch_record(tmp_path):
    world = build_world(tmp_path)
    shard = ContainerLaunch(launch_id='wave-0-w00-g1', role='shard', worker_id='w00', wave_id='wave-0', launch_generation=1,
        container_name=None, image_digest=None, owned_root=str(world.root), session_id='s1', launcher='native')
    container = ContainerLaunch(launch_id='processing-p00-g1', role='processor', worker_id='p00', wave_id=None, launch_generation=1,
        container_name='so101-x', image_digest='sha256:'+'a'*64, owned_root=str(world.root))
    try:
        for launch in (shard, container):
            with pytest.raises(ValueError, match='PROCESSOR_OWNER_CONFIG_INVALID'):
                type(world.owner)(admitted_context=world.context, launch=launch, entry=world.owner.entry, paths=world.paths,
                    registry=world.registry, service_token=world.token, startup_timeout_s=1., status_timeout_s=1.,
                    max_frame_bytes=1, stop_timeout_s=1., install_prefix=tmp_path, command=['x'], base_environment={})
    finally:
        world.cleanup()


def test_the_control_client_serves_the_four_task_operations_over_the_processors_own_socket(tmp_path):
    """The real task adapter and control client against the real processor program in the real subprocess."""
    world = build_world(tmp_path)
    control = ContainerTaskControl(owner=world.owner)

    async def run():
        status = await control.start()
        assert status.state == 'READY'
        polled = await control.get_status()
        assert polled.instance_id == 'processing-p00-g1' and polled.state in ('READY', 'STARTING')
        stopped = await control.terminate('native processor lifecycle test')
        assert stopped.state == 'TERMINATED' and stopped.resources_released is True
        assert world.registry.records()[0]['exit_inspect']['kind'] == 'native_instance_exit'
        assert world.owner.instance_exit()['cleanup_confirmed'] is True
        with pytest.raises(ValueError, match='SHARD_RUNTIME_NOT_READY'):
            world.owner.control_client()
    try:
        asyncio.run(run())
    finally:
        world.cleanup()


def test_the_next_generation_of_a_slot_reads_its_predecessor_s_exit_again_first(tmp_path):
    first = build_world(tmp_path)

    async def run_first():
        await first.owner.start()
        assert (await first.owner.close())['terminated'] is True
    asyncio.run(run_first())
    second = build_world(tmp_path, generation=2, after=first)

    async def run_second():
        await second.owner.start()
        assert [item['launch']['launch_id'] for item in second.registry.records()] == ['processing-p00-g1', 'processing-p00-g2']
        assert (await second.owner.close())['terminated'] is True
    try:
        asyncio.run(run_second())
    finally:
        second.cleanup()
