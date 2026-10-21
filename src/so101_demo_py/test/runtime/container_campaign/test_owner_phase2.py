"""The campaign owner around phase 2: the hook calls the scheduler after the phase-1 durability record, the time limits gate phase-1
dispatch, and the processors are part of cleanup. Controlled doubles as in `test_owner_phase1`; the scheduler is a recording fake
(its own behaviour is `test_processing_scheduler`)."""

import asyncio
from dataclasses import replace
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from test_owner import wave_owner
from test_owner_phase1 import pending_verified


class FakeProcessor:
    def __init__(self):
        self.closes = 0

    async def close(self):
        self.closes += 1
        return dict(terminated=True, launch_id='processing-p00-g1', errors=[])


class FakeScheduler:
    def __init__(self, order, *, stopped=True):
        self.order, self.calls, self.stopped = order, [], stopped
        self.owners = [FakeProcessor()]

    async def run(self, rows, *, deadline_s):
        self.order.append('phase2')
        self.calls.append(dict(rows=rows, deadline_s=deadline_s, started=time.monotonic()))
        return dict(schema_version=1, kind='act_collection_processing_summary', processors=1, processors_stopped=self.stopped,
                    counts=dict(VALID=len(rows), INVALID=0, FAULT=0, MISSING=0), scenes=[])


def phase2_world(tmp_path, monkeypatch, *, scene_count=8, config=None, qualification=False, stopped=True, verify=None, run_wave=None):
    order = []
    world = wave_owner(tmp_path, monkeypatch, scene_count=scene_count, verify=verify or pending_verified(order))
    owner = world.owner
    owner.syncfs = lambda path: order.append('syncfs') or dict(method='syncfs', path=str(path))
    owner.config = {**owner.config, **(config or {})}
    owner.context = owner.services.context = replace(owner.context, admitted_at_monotonic_s=time.monotonic())
    owner.qualification = qualification
    scheduler = FakeScheduler(order, stopped=stopped)
    owner.processing = scheduler
    if run_wave is not None:
        owner.coordinator.run_wave = run_wave
    return SimpleNamespace(world=world, owner=owner, order=order, scheduler=scheduler)


@pytest.mark.parametrize('qualification,plane,count', [(False, None, 8), (True, 'gate', 40), (True, 'functional', 8)])
def test_phase_two_runs_on_the_gate_the_functional_and_the_unqualified_plane(tmp_path, monkeypatch, qualification, plane, count):
    import importlib
    module = importlib.import_module('so101_demo.runtime.container_campaign.owner')
    phase = phase2_world(tmp_path, monkeypatch, scene_count=count, qualification=qualification)
    owner = phase.owner
    if qualification:
        names = tuple(f'scene-{i:02d}' for i in range(count))
        monkeypatch.setattr(module, 'validate_run_contract', lambda document: (plane, dict(worker_count=owner.context.worker_count,
                                                                                         scene_manifest=None)))
        monkeypatch.setattr(module, 'scene_ids', lambda manifest, count=None: names)

    async def run():
        result = await owner.run(phase.world.manifest)
        assert phase.order[-2:] == ['syncfs', 'phase2'] and phase.order.count('syncfs') == 1
        assert [row['scene_id'] for row in phase.scheduler.calls[0]['rows']] == [f'scene-{i:02d}' for i in range(count)]
        assert result['phase2']['counts']['VALID'] == count
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_pending_rows_reach_the_scheduler_after_syncfs_and_the_summary_is_recorded(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8)
    owner = phase.owner

    async def run():
        result = await owner.run(phase.world.manifest)
        assert phase.order == ['verify:0', 'syncfs', 'phase2']
        call, = phase.scheduler.calls
        assert [row['scene_id'] for row in call['rows']] == [f'scene-{i:02d}' for i in range(8)]
        assert all(row['proof']['processing'] == 'PENDING' for row in call['rows'])
        assert call['deadline_s'] == owner.context.deadline_monotonic_s - 600, 'phase 2 ends one verification reserve before the total'
        record = json.loads((owner.root/'host/processing-result.json').read_text())
        assert record['kind'] == 'act_collection_processing_summary' and record['counts']['VALID'] == 8
        assert result['phase2']['counts']['VALID'] == 8 and result['processing'] == 'PENDING'
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_only_pending_rows_are_queued_and_a_campaign_with_none_starts_no_processor(tmp_path, monkeypatch):
    def final_only(plan, outcome, shards):
        rows = []
        for scene in plan['scene_ids']:
            task = 'wave-0-w00-'+scene
            proof = dict(result_status='FAILED', teacher_execution_status='FAILED', teacher_task_result='UNCONFIRMED',
                act_data_status='INVALID', act_data_reason='DYNAMIC_TARGET_UNREACHABLE', act_data_qc='NOT_RUN', export_eligible=False,
                result_sha256='a'*64, task_result_sha256='b'*64, location='/loc/'+task, processing='NOT_PENDING',
                receipt_sha256=None, recording_files=None, recording_bytes=None)
            rows.append(dict(scene_id=scene, worker_id='w00', task_id=task, launch_id='l', location='/out/'+task, proof=proof,
                registration='/host/'+task+'/collected.json', owner_root='/owner', scope_path='/scope', inputs_manifest='/inputs'))
        return dict(wave_index=plan['wave_index'], scene_count=len(rows), coordinator_root='x', case_results=rows)
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8, verify=final_only)

    async def run():
        await phase.owner.run(phase.world.manifest)
        assert phase.scheduler.calls == [] and not (phase.owner.root/'host/processing-result.json').exists()
        await phase.owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_a_teacher_final_scene_is_not_queued_beside_pending_ones(tmp_path, monkeypatch):
    def mixed(plan, outcome, shards):
        value = pending_verified([])(plan, outcome, shards)
        row = value['case_results'][0]
        row['proof'].update(processing='NOT_PENDING', act_data_status='INVALID', act_data_reason='DYNAMIC_TARGET_UNREACHABLE',
                            receipt_sha256=None, recording_files=None, recording_bytes=None)
        return value
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8, verify=mixed)

    async def run():
        await phase.owner.run(phase.world.manifest)
        assert [row['scene_id'] for row in phase.scheduler.calls[0]['rows']] == [f'scene-{i:02d}' for i in range(1, 8)]
        await phase.owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_process_timeout_is_measured_from_the_start_of_phase_two(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, config={'process_timeout_s': 300})

    async def run():
        before = time.monotonic()
        await phase.owner.run(phase.world.manifest)
        call, = phase.scheduler.calls
        assert before + 300 <= call['deadline_s'] <= call['started'] + 300 + 1e-3
        await phase.owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_processors_that_are_not_proven_stopped_fence_the_campaign(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, stopped=False)

    async def run():
        with pytest.raises(ValueError, match='CAMPAIGN_PROCESSORS_STOP_UNCONFIRMED'):
            await phase.owner.run(phase.world.manifest)
        assert phase.owner.stop_reason == 'CAMPAIGN_PROCESSORS_STOP_UNCONFIRMED'
        await phase.owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_cleanup_closes_the_processor_owners_and_reports_them(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch)

    async def run():
        await phase.owner.run(phase.world.manifest)
        cleanup = await phase.owner.close()
        assert phase.scheduler.owners[0].closes == 1 and cleanup['processors'] == [
            dict(terminated=True, launch_id='processing-p00-g1', errors=[])]
        assert cleanup['terminated'] is True
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


# ---- time limits -----------------------------------------------------------------------------------------------------------

def test_limits_that_do_not_fit_the_admitted_total_are_refused_before_anything_starts(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch)
    owner = phase.owner
    total = owner.context.deadline_monotonic_s - owner.context.admitted_at_monotonic_s
    owner.config = {**owner.config, 'collect_timeout_s': int(total) // 2 + 100, 'process_timeout_s': int(total) // 2 + 100}

    async def run():
        with pytest.raises(ValueError, match='CAMPAIGN_PHASE_LIMITS_EXCEED_TOTAL'):
            await owner.run(phase.world.manifest)
        assert phase.world.waves == [] and phase.world.calls == []
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_dispatch_is_allowed_until_the_phase_one_deadline_and_not_after(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, config={'collect_timeout_s': 1})
    owner = phase.owner
    assert owner.dispatch_allowed()

    async def run():
        owner.phase1_deadline_s = time.monotonic() + .15
        assert owner.dispatch_allowed()
        await asyncio.sleep(.2)
        assert not owner.dispatch_allowed() and not owner.dispatch_stopped
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_the_default_reserve_leaves_processing_time_before_the_total(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch)
    owner = phase.owner

    async def run():
        await owner.run(phase.world.manifest)
        assert owner.phase1_deadline_s == owner.context.deadline_monotonic_s - 1800
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_a_phase_one_deadline_mid_run_stops_new_waves_verifies_the_partial_wave_and_still_processes(tmp_path, monkeypatch):
    seen = {}

    async def run_wave(*, plan, shards, endpoints, dispatch_allowed):
        seen.setdefault('waves', []).append(plan['wave_index'])
        await asyncio.sleep(1.3)    # the 1 s collect limit passes during the first wave
        kept = plan['scene_ids'][:5]
        rows = [dict(scene_id=scene, worker_id='w00', location='/out/'+scene, task_id='wave-0-w00-'+scene, launch_id='l')
                for scene in kept]
        return dict(wave_index=plan['wave_index'], coordinator_root='x', case_results=rows, infra_errors=[])

    order = []
    verified_with = []

    def verify(plan, outcome, shards, partial=False):
        verified_with.append((list(plan['scene_ids']), plan['assignment'], partial))
        return pending_verified(order)(plan, outcome, shards)
    phase = phase2_world(tmp_path, monkeypatch, scene_count=21, config={'collect_timeout_s': 1}, run_wave=run_wave, verify=verify)
    owner = phase.owner
    owner.coordinator.stop_dispatch = lambda reason: seen.setdefault('stops', []).append(reason)

    async def run():
        result = await owner.run(phase.world.manifest)
        assert seen['waves'] == [0], 'the second wave is never started'
        assert verified_with == [([f'scene-{i:02d}' for i in range(5)], None, True)]
        limit = json.loads((owner.root/'host/phase1-limit.json').read_text())
        assert limit['stop_reason'] == 'CAMPAIGN_PHASE1_DEADLINE_EXPIRED'
        assert limit['missing_scenes'] == [f'scene-{i:02d}' for i in range(5, 21)]
        assert [row['scene_id'] for row in phase.scheduler.calls[0]['rows']] == [f'scene-{i:02d}' for i in range(5)]
        assert result['missing_evidence'] == limit['missing_scenes']
        assert not (owner.root/'collection-index.json').exists() and (owner.root/'host/phase1-result.json').is_file()
        assert (owner.root/'host/phase1-durability.json').is_file()
        cleanup = await owner.close()
        assert cleanup['terminated'] is True
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_a_deadline_before_the_first_wave_records_everything_as_missing_and_starts_no_processor(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8, config={'collect_timeout_s': 1})
    owner = phase.owner
    owner.context = owner.services.context = replace(owner.context, admitted_at_monotonic_s=time.monotonic() - 100)

    async def run():
        result = await owner.run(phase.world.manifest)
        assert phase.world.waves == [] and phase.scheduler.calls == []
        assert result['missing_evidence'] == [f'scene-{i:02d}' for i in range(8)]
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_the_health_and_disk_monitor_keeps_running_through_phase_two(tmp_path, monkeypatch):
    stamps = []

    async def run_wave(*, plan, shards, endpoints, dispatch_allowed):
        await asyncio.sleep(1.3)    # the 1 s collect limit passes during the first wave
        rows = [dict(scene_id=scene, worker_id='w00', location='/out/'+scene, task_id='wave-0-w00-'+scene, launch_id='l')
                for scene in plan['scene_ids'][:5]]
        return dict(wave_index=plan['wave_index'], coordinator_root='x', case_results=rows, infra_errors=[])

    def verify(plan, outcome, shards, partial=False):
        return pending_verified([])(plan, outcome, shards)
    phase = phase2_world(tmp_path, monkeypatch, scene_count=21, config={'collect_timeout_s': 1}, run_wave=run_wave, verify=verify)
    owner = phase.owner
    owner.coordinator.stop_dispatch = lambda reason: None
    guard = owner._disk_guard
    owner._disk_guard = lambda: stamps.append(time.monotonic()) or guard()

    async def slow_phase_two(rows, *, deadline_s):
        phase.scheduler.calls.append(dict(rows=rows, deadline_s=deadline_s, started=time.monotonic()))
        await asyncio.sleep(2.6)
        phase.scheduler.calls[-1]['ended'] = time.monotonic()
        return dict(schema_version=1, kind='act_collection_processing_summary', processors=1, processors_stopped=True,
                    counts=dict(VALID=len(rows), INVALID=0, FAULT=0, MISSING=0), scenes=[])
    phase.scheduler.run = slow_phase_two

    async def run():
        await owner.run(phase.world.manifest)
        call = phase.scheduler.calls[0]
        during = [stamp for stamp in stamps if call['started'] <= stamp <= call['ended']]
        assert len(during) >= 2, 'the monitor sampled disk and health during phase 2'
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_stop_after_phase1_leaves_the_run_for_the_later_stages(tmp_path, monkeypatch):
    import hashlib
    from so101_demo.runtime.container_campaign import stage_records
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8)
    phase.owner.stop_after_phase1 = True

    async def run():
        result = await phase.owner.run(phase.world.manifest)
        await phase.owner.close()
        return result
    try:
        result = asyncio.run(run())
    finally:
        phase.world.registry.close()
    host = phase.owner.root / 'host'
    assert result['processing'] == 'PENDING' and result['stop'] == 'PHASE1_ONLY'
    assert phase.scheduler.calls == [] and phase.order.count('syncfs') == 1       # phase 1 is durable, phase 2 never started
    assert not (host / 'processing-result.json').exists() and not (host / 'campaign-result.json').exists()
    assert not (phase.owner.root / 'collection-index.json').exists()
    record = stage_records.read_record(host, stage_records.PHASE1)
    assert record['previous'] is None and record['scene_count'] == 8 and record['qualification'] is False
    assert record['phase1_result_sha256'] == hashlib.sha256((host / 'phase1-result.json').read_bytes()).hexdigest()
    assert record['durability_sha256'] == hashlib.sha256((host / 'phase1-durability.json').read_bytes()).hexdigest()
    assert record['campaign_config'] == dict(path=phase.owner.context.campaign_config_path,
                                             sha256=phase.owner.context.campaign_config_sha256)
    assert stage_records.require_previous(host, stage_records.PHASE2, logic=record['campaign_config'])['sha256'] == record['sha256']
