"""The end of phase 1 in the campaign owner: shard stop proof, one syncfs, the host record and the phase-2 hook.

Controlled doubles as in `test_owner` (shard owner, wave coordinator, wave verifier); the service owner, registry and campaign
owner are the real ones.
"""

import asyncio
import json

import pytest

from test_owner import fixture, wave_owner


def pending_verified(order):
    def verified(plan, outcome, shards):
        order.append('verify:'+str(plan['wave_index']))
        rows = []
        for scene in plan['scene_ids']:
            task = 'wave-'+str(plan['wave_index'])+'-w00-'+scene
            proof = dict(result_status='PASSED', teacher_execution_status='COMPLETED', teacher_task_result='PASS',
                act_data_status='PENDING_QC', act_data_reason=None, act_data_qc='NOT_RUN', export_eligible=False,
                result_sha256='a'*64, task_result_sha256='b'*64, location='/loc/'+task, processing='PENDING',
                receipt_sha256='c'*64, recording_files=4, recording_bytes=100)
            rows.append(dict(scene_id=scene, worker_id='w00', task_id=task, launch_id='l', location='/out/'+task, proof=proof,
                registration='/host/'+task+'/collected.json', owner_root='/owner', scope_path='/scope',
                inputs_manifest='/inputs'))
        return dict(wave_index=plan['wave_index'], scene_count=len(rows), coordinator_root='x', case_results=rows)
    return verified


def test_one_syncfs_follows_the_last_verified_wave_and_pending_proofs_write_no_final_index(tmp_path, monkeypatch):
    order = []
    world = wave_owner(tmp_path, monkeypatch, scene_count=21, verify=pending_verified(order))
    owner = world.owner
    owner.syncfs = lambda path: order.append('syncfs') or dict(method='syncfs', path=str(path))

    async def run():
        result = await owner.run(world.manifest)
        assert order == ['verify:0', 'verify:1', 'syncfs'], 'exactly one syncfs, after every phase-1 wave was verified'
        record = json.loads((owner.root/'host/phase1-durability.json').read_text())
        assert record['kind'] == 'act_collection_phase1_durability' and record['method'] == 'syncfs'
        assert record['path'] == str(owner.root) and record['waves'] == 2 and record['scene_count'] == 21
        assert record['shards_proven_stopped'] is True
        assert result['processing'] == 'PENDING' and len(result['waves']) == 2
        phase1 = json.loads((owner.root/'host/phase1-result.json').read_text())
        assert phase1['processing'] == 'PENDING' and len(phase1['waves']) == 2
        assert not (owner.root/'collection-index.json').exists() and not (owner.root/'host/campaign-result.json').exists()
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_a_processed_campaign_still_syncs_once_and_writes_its_index(tmp_path, monkeypatch):
    syncs = []
    world = wave_owner(tmp_path, monkeypatch, scene_count=8)
    owner = world.owner
    owner.syncfs = lambda path: syncs.append(path) or dict(method='syncfs', path=str(path))

    async def run():
        result = await owner.run(world.manifest)
        assert len(syncs) == 1 and 'processing' not in result
        assert (owner.root/'collection-index.json').is_file() and (owner.root/'host/campaign-result.json').is_file()
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_a_failed_syncfs_fences_dispatch_and_writes_nothing_final(tmp_path, monkeypatch):
    world = wave_owner(tmp_path, monkeypatch, scene_count=8, verify=pending_verified([]))
    owner = world.owner

    def broken(path):
        raise OSError(5, 'Input/output error')
    owner.syncfs = broken

    async def run():
        with pytest.raises(ValueError, match='CAMPAIGN_PHASE1_SYNC_FAILED'):
            await owner.run(world.manifest)
        assert owner.dispatch_stopped and owner.stop_reason == 'CAMPAIGN_PHASE1_SYNC_FAILED'
        assert not (owner.root/'host/phase1-durability.json').exists() and not (owner.root/'host/phase1-result.json').exists()
        assert not (owner.root/'collection-index.json').exists()
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_unproven_shard_stops_block_the_syncfs_and_phase_two(tmp_path, monkeypatch):
    order = []
    world = wave_owner(tmp_path, monkeypatch, scene_count=8, verify=pending_verified(order))
    owner = world.owner
    owner.syncfs = lambda path: order.append('syncfs')
    owner.registry.role_terminated = lambda role, inspect_container, inspect_native=None: False

    async def run():
        with pytest.raises(ValueError, match='CAMPAIGN_PHASE1_STOP_UNPROVEN'):
            await owner.run(world.manifest)
        assert 'syncfs' not in order and owner.stop_reason == 'CAMPAIGN_PHASE1_STOP_UNPROVEN'
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_the_phase_two_hook_runs_after_the_durability_record_and_only_then(tmp_path, monkeypatch):
    order = []
    world = wave_owner(tmp_path, monkeypatch, scene_count=8, verify=pending_verified(order))
    owner = world.owner
    owner.syncfs = lambda path: order.append('syncfs') or dict(method='syncfs', path=str(path))

    async def phase_two(waves):
        order.append('phase2')
        assert (owner.root/'host/phase1-durability.json').is_file() and len(waves) == 1
    owner.start_phase_two = phase_two

    async def run():
        await owner.run(world.manifest)
        assert order == ['verify:0', 'syncfs', 'phase2']
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        world.registry.close()


def test_the_registry_proves_one_role_at_a_time(tmp_path):
    owner, service, registry, calls, containers, manifest, stopped = fixture(tmp_path)
    try:
        assert registry.role_terminated('shard', service.inspect_container) is True, 'no shard was launched'
    finally:
        registry.close()


def test_sync_filesystem_flushes_the_filesystem_of_the_path(tmp_path):
    from so101_demo.runtime.container_campaign.durability import sync_filesystem
    record = sync_filesystem(tmp_path)
    assert record['path'] == str(tmp_path) and record['method'] in ('os.syncfs', 'libc.syncfs', 'os.sync')
    assert isinstance(record['elapsed_s'], float) and record['elapsed_s'] >= 0.
