"""Durable launch ownership survives owner loss without authorizing takeover."""

from dataclasses import asdict
import importlib

import pytest

from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey

#: The retired per-worker field; built from fragments so the source-tree absence test keeps matching nothing.
NS_FIELD = "ros" + "_namespace"


def module():
    return importlib.import_module('so101_demo.runtime.container_campaign.registry')


def launch(tmp_path, *, role='head', generation=1):
    return module().ContainerLaunch(launch_id=f'{role}-g{generation}', role=role,
        worker_id=None, wave_id=None, launch_generation=generation,
        container_name=f'so101-test-{role}-g{generation}', image_digest='sha256:'+'b'*64,
        owned_root=str(tmp_path))


def inspect_document(*, running=False, started='2026-10-12T01:02:03.123Z'):
    return dict(Id='a'*64, Image='sha256:'+'b'*64, State=dict(StartedAt=started,
        Running=running, Restarting=False, Pid=500 if running else 0,
        Status='running' if running else 'exited', ExitCode=0))


def test_intent_persisted_before_container_binding_and_reopened_without_resume(tmp_path):
    mod = module()
    path = tmp_path/'launches.sqlite3'
    registry = mod.ContainerLaunchRegistry(path)
    item = launch(tmp_path)
    registry.register(item)
    assert registry.records()[0]['launch'] == asdict(item)
    assert registry.records()[0]['owner'] is None
    registry.close()
    registry = mod.ContainerLaunchRegistry(path, create=False)
    assert registry.records()[0]['launch'] == asdict(item)
    with pytest.raises(ValueError, match='LAUNCH_OWNER_UNKNOWN'):
        registry.prove_terminated(item.launch_id, inspect_document())
    registry.close()


def test_only_same_actual_container_exit_can_settle_a_service_launch(tmp_path):
    mod = module()
    registry = mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3')
    item = launch(tmp_path)
    registry.register(item)
    owner = ContainerOwnerKey('a'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 1)
    registry.bind_container(item.launch_id, owner)
    with pytest.raises(ValueError, match='LAUNCH_STOP_UNCONFIRMED'):
        registry.prove_terminated(item.launch_id, inspect_document(running=True))
    with pytest.raises(ValueError, match='LAUNCH_STOP_UNCONFIRMED'):
        registry.prove_terminated(item.launch_id, inspect_document(started='2026-10-12T01:03:00Z'))
    assert registry.prove_terminated(item.launch_id, inspect_document()) is True
    assert registry.prove_terminated(item.launch_id, inspect_document()) is True
    assert registry.records()[0]['exit_inspect'] == inspect_document()
    assert registry.all_terminated(lambda cid: inspect_document())
    assert not registry.all_terminated(lambda cid: inspect_document(running=True))
    registry.close()


def test_unidentified_or_unsettled_launch_fences_registry_completion(tmp_path):
    registry = module().ContainerLaunchRegistry(tmp_path/'launches.sqlite3')
    assert not registry.all_terminated(lambda cid: inspect_document())
    item = launch(tmp_path)
    registry.register(item)
    assert not registry.all_terminated(lambda cid: inspect_document())
    registry.bind_container(item.launch_id, ContainerOwnerKey('a'*64,
        '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 1))
    assert not registry.all_terminated(lambda cid: inspect_document())
    registry.close()


def test_duplicate_role_and_foreign_binding_refused_without_overwrite(tmp_path):
    mod = module()
    registry = mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3')
    item = launch(tmp_path)
    registry.register(item)
    with pytest.raises(ValueError, match='LAUNCH_COLLISION'):
        registry.register(launch(tmp_path, generation=2))
    owner = ContainerOwnerKey('a'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'c'*64, 1)
    with pytest.raises(ValueError, match='LAUNCH_BINDING_MISMATCH'):
        registry.bind_container(item.launch_id, owner)
    assert registry.records()[0]['owner'] is None
    registry.close()


def test_shard_cannot_settle_from_docker_exit_without_inner_original_proof(tmp_path):
    mod = module()
    registry = mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3')
    item = mod.ContainerLaunch(launch_id='wave-00-w00-g1', role='shard', worker_id='w00',
        wave_id='wave-00', launch_generation=1, container_name='so101-shard-w00-g1',
        image_digest='sha256:'+'b'*64, owned_root=str(tmp_path), session_id='wave00-w00-g1')
    registry.register(item)
    registry.bind_container(item.launch_id, ContainerOwnerKey('a'*64,
        '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 1))
    with pytest.raises(ValueError, match='LAUNCH_STOP_UNCONFIRMED'):
        registry.prove_terminated(item.launch_id, inspect_document())
    assert registry.records()[0]['exit_inspect'] is None
    registry.close()


def test_existing_or_symlink_registry_cannot_be_created_as_new_campaign(tmp_path):
    mod = module()
    path = tmp_path/'launches.sqlite3'
    registry = mod.ContainerLaunchRegistry(path)
    registry.close()
    with pytest.raises(FileExistsError):
        mod.ContainerLaunchRegistry(path)
    link = tmp_path/'foreign.sqlite3'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='LAUNCH_REGISTRY_PATH_INVALID'):
        mod.ContainerLaunchRegistry(link, create=False)


@pytest.mark.parametrize('tamper', [False, True])
def test_shard_registry_recomputes_original_stop_before_slot_reuse(tmp_path, monkeypatch, tamper):
    import asyncio
    from test_shard_retirement import fixture as stop_fixture
    from so101_demo.runtime.container_campaign.process_identity import ContainerChildBinding, pid_namespace_inode
    _, root, process, _, retirement, _ = stop_fixture(tmp_path, monkeypatch)
    asyncio.run(retirement.retire(fenced=True))
    mod = module()
    registry = mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3')
    item = mod.ContainerLaunch(launch_id='wave-00-w00-g7', role='shard', worker_id='w00',
        wave_id='wave-00', launch_generation=7, container_name='so101-shard-w00-g7',
        image_digest='sha256:'+'b'*64, owned_root=str(root), session_id='session1')
    owner = ContainerOwnerKey('a'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 7)
    registry.register(item)
    registry.bind_container(item.launch_id, owner)
    binding = ContainerChildBinding(owner, process, pid_namespace_inode(), str(root/'control/normal.sock'))
    registry.bind_child(item.launch_id, binding)
    assert registry.prove_terminated(item.launch_id, inspect_document())
    assert registry.all_terminated(lambda cid: inspect_document())
    if tamper:
        (root/'retirement/controller-stop.json').write_text('{}')
        assert not registry.all_terminated(lambda cid: inspect_document())
    next_root = tmp_path/'next-owned'
    next_root.mkdir()
    next_launch = mod.ContainerLaunch(launch_id='wave-01-w00-g8', role='shard', worker_id='w00',
        wave_id='wave-01', launch_generation=8, container_name='so101-shard-w00-g8',
        image_digest='sha256:'+'b'*64, owned_root=str(next_root), session_id='session2')
    if tamper:
        with pytest.raises(ValueError, match='LAUNCH_STOP_UNCONFIRMED'):
            registry.register(next_launch)
    else:
        registry.register(next_launch)
        assert len(registry.records()) == 2
        assert not {'ros_domain_id', NS_FIELD} & set(registry.records()[1]['launch'])
        assert not registry.all_terminated(lambda cid: inspect_document())  # new launch still unknown
    registry.close()


# ---- the read-only open used by the independent qualification verifier ------------------------------------------------------


def tree_state(root):
    return sorted((str(path.relative_to(root)), path.read_bytes()) for path in root.rglob('*') if path.is_file())


def prepared_registry(tmp_path):
    mod = module()
    path = tmp_path/'launches.sqlite3'
    registry = mod.ContainerLaunchRegistry(path)
    item = launch(tmp_path)
    registry.register(item)
    owner = ContainerOwnerKey('a'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 1)
    registry.bind_container(item.launch_id, owner)
    registry.prove_terminated(item.launch_id, inspect_document())
    expected = registry.records()
    registry.close()
    return mod, path, item, owner, expected


def test_read_only_registry_reads_the_same_records_and_changes_nothing(tmp_path):
    mod, path, item, owner, expected = prepared_registry(tmp_path)
    before = tree_state(tmp_path)
    registry = mod.ContainerLaunchRegistry(path, create=False, read_only=True)
    try:
        assert registry.records() == expected
        assert registry.all_terminated(lambda cid: inspect_document())
        assert not registry.all_terminated(lambda cid: inspect_document(running=True))
    finally:
        registry.close()
    assert tree_state(tmp_path) == before
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ['launches.sqlite3']    # no journal, wal or shm file appears


def test_every_mutating_method_of_a_read_only_registry_refuses(tmp_path):
    mod, path, item, owner, expected = prepared_registry(tmp_path)
    before = tree_state(tmp_path)
    registry = mod.ContainerLaunchRegistry(path, create=False, read_only=True)
    try:
        other = mod.ContainerLaunch(**dict(asdict(item), launch_id='teacher-g9', role='teacher', container_name='so101-other'))
        with pytest.raises(ValueError, match='LAUNCH_REGISTRY_READ_ONLY'):
            registry.register(other)
        with pytest.raises(ValueError, match='LAUNCH_REGISTRY_READ_ONLY'):
            registry.bind_container(item.launch_id, owner)
        with pytest.raises(ValueError, match='LAUNCH_REGISTRY_READ_ONLY'):
            registry.bind_child(item.launch_id, None)
        assert registry.records() == expected
        # a stored settlement is re-proved from the original inspect document and never written back
        assert registry.prove_terminated(item.launch_id, inspect_document()) is True
        with pytest.raises(ValueError, match='LAUNCH_STOP_UNCONFIRMED'):
            registry.prove_terminated(item.launch_id, inspect_document(running=True))
    finally:
        registry.close()
    assert tree_state(tmp_path) == before


def test_read_only_registry_cannot_settle_an_unsettled_launch(tmp_path):
    mod = module()
    path = tmp_path/'launches.sqlite3'
    registry = mod.ContainerLaunchRegistry(path)
    item = launch(tmp_path)
    registry.register(item)
    registry.bind_container(item.launch_id, ContainerOwnerKey('a'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'b'*64, 1))
    registry.close()
    before = tree_state(tmp_path)
    registry = mod.ContainerLaunchRegistry(path, create=False, read_only=True)
    try:
        with pytest.raises(ValueError, match='LAUNCH_REGISTRY_READ_ONLY'):
            registry.prove_terminated(item.launch_id, inspect_document())
        assert registry.records()[0]['exit_inspect'] is None
        assert not registry.all_terminated(lambda cid: inspect_document())
    finally:
        registry.close()
    assert tree_state(tmp_path) == before


def test_read_only_open_refuses_creation_a_missing_file_and_bad_flags(tmp_path):
    mod = module()
    with pytest.raises(ValueError, match='LAUNCH_REGISTRY_PATH_INVALID'):
        mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3', create=True, read_only=True)
    with pytest.raises((ValueError, OSError)):
        mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3', create=False, read_only=True)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match='LAUNCH_REGISTRY_PATH_INVALID'):
        mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3', create=False, read_only='yes')


def test_a_launch_record_carries_no_ros_domain_or_namespace_and_the_registry_is_version_two(tmp_path):
    import sqlite3
    mod = module()
    path = tmp_path/'launches.sqlite3'
    registry = mod.ContainerLaunchRegistry(path)
    registry.register(launch(tmp_path))
    assert not {'ros_domain_id', NS_FIELD} & set(registry.records()[0]['launch'])
    with pytest.raises(TypeError):
        mod.ContainerLaunch(launch_id='x', role='shard', worker_id='w00', wave_id='wave-0', launch_generation=1,
            container_name='x', image_digest='sha256:'+'b'*64, owned_root=str(tmp_path), session_id='s1', **{NS_FIELD: '/a/w00'})
    registry.close()
    assert sqlite3.connect(path).execute('SELECT version, kind FROM metadata').fetchall() == [
        (2, 'ACT_CONTAINER_LAUNCH_REGISTRY')]


def test_two_live_shards_on_the_one_fixed_identity_do_not_collide(tmp_path):
    """The fixed ROS identity is shared by every shard, so the registry's only live-resource rules are the Host's own."""
    mod = module()
    registry = mod.ContainerLaunchRegistry(tmp_path/'launches.sqlite3')
    roots = []
    for index in range(2):
        root = tmp_path/f'w0{index}'
        root.mkdir()
        roots.append(root)
        registry.register(mod.ContainerLaunch(launch_id=f'wave-0-w0{index}-g1', role='shard', worker_id=f'w0{index}',
            wave_id='wave-0', launch_generation=1, container_name=f'so101-shard-w0{index}-g1',
            image_digest='sha256:'+'b'*64, owned_root=str(root), session_id=f'session-{index}'))
    assert len(registry.records()) == 2
    with pytest.raises(ValueError, match='LAUNCH_COLLISION: session reuse'):
        other = tmp_path/'w02'
        other.mkdir()
        registry.register(mod.ContainerLaunch(launch_id='wave-0-w02-g1', role='shard', worker_id='w02',
            wave_id='wave-0', launch_generation=1, container_name='so101-shard-w02-g1',
            image_digest='sha256:'+'b'*64, owned_root=str(other), session_id='session-0'))
    registry.close()
