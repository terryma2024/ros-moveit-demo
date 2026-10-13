"""Native owner keys, the native exit proof, and native records in the shared launch registry.

Real: the key and proof functions, the registry (SQLite) and, for the full-record cases, the real owner and instance program
of `native_instance_world`.
"""

import asyncio
from dataclasses import replace
import hashlib

import pytest

from native_instance_world import build_world
from so101_demo.runtime.container_campaign.native_stop import observe_native_exit
from so101_demo.runtime.container_campaign.paths import make_campaign_paths
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, NativeOwnerKey, ProcessOwnerKey, native_exit_proven, owner_exit_proven,
    pid_namespace_inode, shard_stop_proven,
)
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry

SHA = 'a'*64


def process_key(pid=700):
    return ProcessOwnerKey(pid, pid, 12345, SHA, 'b'*64)


def native_key(pid=700, generation=1):
    return NativeOwnerKey.from_process(process_key(pid), launch_generation=generation)


def exit_document(key, **overrides):
    document = dict(schema_version=1, kind='native_instance_exit', pid=key.pid, pgid=key.pgid,
        started_ticks=key.started_ticks, argv_sha256=key.argv_sha256, owned_root='/run/x/wave-0/w00/g1',
        leader_state='absent', group_members=[], marker_survivors=[], graph_clear=True)
    return document | overrides


def test_a_native_owner_key_is_the_instance_process_leading_its_own_group():
    key = native_key()
    assert key.process_key() == process_key() and key.launch_generation == 1
    for damage in (dict(pgid=701), dict(pid=0, pgid=0), dict(started_ticks=0), dict(argv_sha256='x'),
                   dict(environment_sha256='B'*64), dict(launch_generation=0)):
        fields = dict(pid=700, pgid=700, started_ticks=1, argv_sha256=SHA, environment_sha256=SHA, launch_generation=1)
        with pytest.raises(ValueError, match='NATIVE_OWNER_KEY_INVALID'):
            NativeOwnerKey(**(fields | damage))
    with pytest.raises(ValueError, match='NATIVE_OWNER_KEY_INVALID'):
        NativeOwnerKey.from_process('process', launch_generation=1)


def test_the_native_exit_proof_needs_every_fact():
    key = native_key()
    for leader in ('absent', 'zombie', 'replaced'):
        assert native_exit_proven(key, exit_document(key, leader_state=leader)) is True
    for damage in (dict(leader_state='live'), dict(leader_state='unknown'), dict(group_members=[701]),
                   dict(marker_survivors=[-1]), dict(marker_survivors=[9]), dict(graph_clear=False),
                   dict(graph_clear=1), dict(pid=701), dict(started_ticks=1), dict(argv_sha256='c'*64),
                   dict(kind='other'), dict(schema_version=True), dict(extra=1)):
        assert native_exit_proven(key, exit_document(key, **damage)) is False, damage
    assert native_exit_proven(key, {k: v for k, v in exit_document(key).items() if k != 'owned_root'}) is False
    assert native_exit_proven(key, None) is False and native_exit_proven(process_key(), exit_document(key)) is False


def test_the_proof_of_an_owner_follows_the_owner_kind():
    container = ContainerOwnerKey('f'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'a'*64, 1)
    inspected = dict(Id=container.container_id, Image=container.image_digest, State=dict(StartedAt=container.docker_started_at,
        Running=False, Restarting=False, Pid=0, Status='exited', ExitCode=0))
    assert owner_exit_proven(container, inspected) is True
    assert owner_exit_proven(native_key(), inspected) is False
    assert owner_exit_proven(native_key(), exit_document(native_key())) is True
    assert owner_exit_proven(container, exit_document(native_key())) is False


def test_a_binding_and_a_shard_stop_accept_a_native_owner():
    key = native_key()
    binding = ContainerChildBinding(key, key.process_key(), pid_namespace_inode(), '/run/x/control/normal.sock')
    receipt = dict(schema_version=1, kind='shard_stop_receipt', generation=1,
        process_owner=dict(pid=key.pid, pgid=key.pgid, started_ticks=key.started_ticks, argv_sha256=key.argv_sha256,
                           environment_sha256=key.environment_sha256),
        pid_namespace_inode=binding.pid_namespace_inode, goals_stopped=True, controllers_stopped=True,
        ros_children_exited=True, ros_graph_empty=True, forced=False)
    assert shard_stop_proven(binding, receipt, exit_document(key)) is True
    assert shard_stop_proven(binding, dict(receipt, forced=True), exit_document(key)) is False
    assert shard_stop_proven(binding, dict(receipt, ros_graph_empty=False), exit_document(key)) is False
    assert shard_stop_proven(binding, dict(receipt, generation=2), exit_document(key)) is False
    assert shard_stop_proven(binding, receipt, exit_document(key, leader_state='live')) is False
    with pytest.raises(ValueError, match='CONTAINER_CHILD_BINDING_INVALID'):
        ContainerChildBinding('not a key', key.process_key(), 1, '/run/x/control/normal.sock')


def launch_fields(**overrides):
    fields = dict(launch_id='measurement-w00-g1', role='shard', worker_id='w00', wave_id='measurement',
        launch_generation=1, container_name=None, image_digest=None, owned_root='/', session_id='session-1',
        launcher='native')
    return fields | overrides


def test_a_native_launch_record_has_no_container_and_no_image():
    assert ContainerLaunch(**launch_fields()).launcher == 'native'
    for damage in (dict(container_name='so101-x'), dict(image_digest='sha256:'+'a'*64), dict(role='teacher'),
                   dict(launcher='remote'), dict(launch_id='bad id'), dict(session_id=None)):
        with pytest.raises(ValueError, match='CONTAINER_LAUNCH_RECORD_INVALID'):
            ContainerLaunch(**launch_fields(**damage))
    container = launch_fields(container_name='so101-x', image_digest='sha256:'+'a'*64, launcher='container')
    assert ContainerLaunch(**container).launcher == 'container'
    assert ContainerLaunch(**{k: v for k, v in container.items() if k != 'launcher'}).launcher == 'container'
    for damage in (dict(container_name=None), dict(image_digest=None)):
        with pytest.raises(ValueError, match='CONTAINER_LAUNCH_RECORD_INVALID'):
            ContainerLaunch(**(container | damage))


def test_native_launches_of_two_workers_do_not_collide_on_their_missing_container_names(tmp_path):
    paths = make_campaign_paths(tmp_path, 'campaign')
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    try:
        for worker in ('w00', 'w01'):
            root = paths['run']/'wave-0'/worker/'g1'
            root.mkdir(parents=True)
            registry.register(ContainerLaunch(**launch_fields(launch_id=f'wave-0-{worker}-g1', worker_id=worker,
                wave_id='wave-0', owned_root=str(root), session_id=f'session-{worker}')))
        assert len(registry.records()) == 2
        with pytest.raises(ValueError, match='LAUNCH_COLLISION'):
            registry.register(ContainerLaunch(**launch_fields(launch_id='other', worker_id='w02', wave_id='wave-0',
                owned_root=str(paths['run']/'wave-0/w00/g1'), session_id='session-w02')))
    finally:
        registry.close()


def test_only_a_native_record_binds_a_native_owner_and_each_process_binds_once(tmp_path):
    paths = make_campaign_paths(tmp_path, 'campaign')
    registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3')
    try:
        roots = []
        for name in ('a', 'b'):
            root = paths['run']/f'wave-0-{name}'/'w00'/'g1'
            root.mkdir(parents=True)
            roots.append(root)
        native = ContainerLaunch(**launch_fields(launch_id='native-w00-g1', owned_root=str(roots[0])))
        container = ContainerLaunch(**launch_fields(launch_id='container-w00-g1', worker_id='w00', session_id='session-2',
            owned_root=str(roots[1]), container_name='so101-x', image_digest='sha256:'+'a'*64, launcher='container'))
        # the container record is on the same worker, so give it its own worker to register next to the native one
        container = replace(container, worker_id='w01')
        registry.register(native)
        registry.register(container)
        key = native_key()
        with pytest.raises(ValueError, match='LAUNCH_BINDING_MISMATCH'):
            registry.bind_native(container.launch_id, key)
        with pytest.raises(ValueError, match='LAUNCH_BINDING_MISMATCH'):
            registry.bind_native(native.launch_id, native_key(generation=2))
        registry.bind_native(native.launch_id, key)
        assert registry.records()[0]['owner'] == dict(pid=700, pgid=700, started_ticks=12345, argv_sha256=SHA,
                                                      environment_sha256='b'*64, launch_generation=1)
        with pytest.raises(ValueError, match='LAUNCH_BINDING_MISMATCH'):
            registry.bind_native(native.launch_id, key)                       # a launch binds once
        with pytest.raises(ValueError, match='LAUNCH_BINDING_MISMATCH'):
            registry.bind_container(native.launch_id, ContainerOwnerKey('f'*64, '2026-10-12T01:02:03.123Z',
                                                                         'sha256:'+'a'*64, 1))
    finally:
        registry.close()


def test_a_registry_written_before_the_launcher_field_still_reads_as_container_records():
    document = {'launch': {'launch_id': 'x', 'role': 'shard'}, 'owner': {'container_id': 'c'}, 'exit_inspect': {'k': 1}}
    got = ContainerLaunchRegistry._exit_document(document, lambda container_id: {'inspected': container_id}, None)
    assert got == {'inspected': 'c'}


def test_a_settled_native_run_reproves_from_its_stored_exit_and_from_a_live_reading(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    async def body():
        await world.owner.start()
        assert (await world.owner.close())['terminated'] is True
        registry = world.registry
        calls = []
        assert registry.all_terminated(lambda container_id: calls.append(container_id)) is True    # stored exit, no Docker
        assert calls == []
        record = registry.records()[0]
        owner = NativeOwnerKey(**record['owner'])
        live = lambda item: observe_native_exit(NativeOwnerKey(**item['owner']), item['launch']['owned_root'],
                                                graph_probe=lambda: True)
        assert registry.all_terminated(None, inspect_native=live) is True
        dirty = lambda item: live(item) | dict(graph_clear=False)
        assert registry.all_terminated(None, inspect_native=dirty) is False
        # the instance is still the registered owner: a settled record cannot be re-proved against a different leader
        forged = lambda item: live(item) | dict(started_ticks=owner.started_ticks+1)
        assert registry.all_terminated(None, inspect_native=forged) is False
    try:
        asyncio.run(body())
    finally:
        world.cleanup()


def test_a_native_record_without_a_stored_exit_is_not_terminated(tmp_path, monkeypatch):
    world = build_world(tmp_path, monkeypatch)
    async def body():
        await world.owner.start()
        assert world.registry.all_terminated(lambda container_id: None) is False
        await world.owner.close()
    try:
        asyncio.run(body())
    finally:
        world.cleanup()


def test_the_unchanged_wave_verifier_takes_the_native_record_and_owner_as_it_takes_a_container_record(tmp_path, monkeypatch):
    """`verify_wave` compares the registry record with the live owner, then recomputes from registry records alone; both
    steps read only generic fields, so there is no native-specific verifier."""
    from dataclasses import asdict
    from so101_demo.runtime.container_campaign import result_verifier

    world = build_world(tmp_path, monkeypatch)
    inputs = tmp_path/'case-inputs'
    inputs.mkdir()
    refs = {}
    for name in ('scope', 'inputs_manifest'):
        (inputs/f'{name}.json').write_text('{}')
        refs[name] = dict(path=str(inputs/f'{name}.json'), sha256=hashlib.sha256(b'{}').hexdigest())
    reached = []
    monkeypatch.setattr(result_verifier, 'verify_wave_records', lambda *args, **kwargs: reached.append(args) or 'ok')
    async def body():
        await world.owner.start()
        assert (await world.owner.close())['terminated'] is True
        verifier = result_verifier.ContainerWaveResultVerifier(root=world.paths['run'], registry=world.registry,
            case_inputs={'scene-1': refs})
        outcome = dict(wave_index=0, coordinator_root=str(world.paths['run']/'host/wave-0/task-journal'),
                       case_results=[], infra_errors=[])
        assert verifier.verify_wave(dict(wave_index=0, scene_ids=['scene-1']), outcome, (world.owner,)) == 'ok'
        ((_root, _plan, records, *_rest),) = reached
        (record,) = records
        assert record['launch'] == asdict(world.owner.launch) and record['owner'] == asdict(world.owner.owner)
        assert record['launch']['launcher'] == 'native' and record['binding'] is not None
    try:
        asyncio.run(body())
    finally:
        world.cleanup()
