"""Retry orchestration through the real owner and combined verifier; container work is controlled."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign import processing_verifier
from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingJournal
from test_owner_phase2 import phase2_world


def retry_world(tmp_path, monkeypatch, *, rounds=2, outcomes=('INVALID', 'VALID'), config=None, scene_count=2):
    phase = phase2_world(tmp_path, monkeypatch, scene_count=scene_count,
                         config=dict(retry_invalid_max_rounds=rounds, **(config or {})))
    owner = phase.owner
    owner.coordinator.config = SimpleNamespace(initializing_hard_timeout_s=180, executing_hard_timeout_s=300,
                                               finalizing_hard_timeout_s=120, worker_recovery_timeout_s=60)
    phase.outputs, phase.proc_counts = {}, {}

    async def process(rows, *, deadline_s, round=0, host_dir=None):
        phase.order.append('phase2')
        phase.scheduler.calls.append(dict(round=round, rows=rows, host_dir=host_dir, deadline_s=deadline_s))
        host = owner.root / 'host' if host_dir is None else host_dir
        journal = ProcessingJournal(host / 'processing-journal.jsonl')
        journal.append('phase2_start', queue=[row['scene_id'] for row in rows], processors=1)
        journal.append('processor_started', processor_id='p00', launch_generation=round + 1)
        scenes = []
        for row in rows:
            scene = row['scene_id']
            number = phase.proc_counts.get(scene, 0) + 1
            phase.proc_counts[scene] = number
            outcome = outcomes[min(round, len(outcomes) - 1)] if scene == 'scene-00' else 'VALID'
            output = owner.root / 'processing' / scene / f'{scene}-lease-1-proc-{number}'
            journal.append('dispatch', scene_id=scene, task_id=f'{scene}-proc-{number}', proc_attempt=number,
                           processor_id='p00', launch_generation=round + 1, output_dir=str(output))
            journal.append('result', scene_id=scene, task_id=f'{scene}-proc-{number}', proc_attempt=number,
                           outcome=outcome, processor_rc=0)
            phase.outputs[str(output)] = dict(act_data_status=outcome, act_data_reason=None, act_data_qc='PASS',
                                              export_eligible=outcome == 'VALID', output_dir=str(output),
                                              processed_result=dict(path='processed-result.json', sha256='d' * 64))
            scenes.append(dict(scene_id=scene, status='FINAL', outcome=outcome, attempts=1, output_dir=str(output)))
        return dict(processors=1, processors_stopped=True, scenes=scenes, counts={})

    def read_processed(output, **kwargs):
        return phase.outputs[str(output)]

    phase.scheduler.run = process
    owner.verifier.verify_processing = lambda waves, ids: processing_verifier.verify_processing(
        owner.root, waves, ids, readback_workers=1, processed_reader=read_processed)
    owner.verifier.verify_rounds = lambda rounds, ids: processing_verifier.verify_rounds(
        owner.root, rounds, ids, readback_workers=1, processed_reader=read_processed)
    return phase


def drive(phase):
    async def run():
        try:
            return await phase.owner.run(phase.world.manifest)
        finally:
            await phase.owner.close()
    try:
        return asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_the_owner_retries_only_invalid_teacher_passes_and_commits_the_recovered_attempt(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch)
    result = drive(phase)
    assert phase.world.waves == [0, 1]
    assert [call['round'] for call in phase.scheduler.calls] == [0, 1]
    assert [row['scene_id'] for row in phase.scheduler.calls[1]['rows']] == ['scene-00']
    assert result['retry']['recovered'] == 1 and result['retry']['rounds_run'] == 1
    assert not result.get('task_faults')
    assert (phase.owner.root / 'host/retry-1/phase1-durability.json').exists()
    assert (phase.owner.root / 'host/retry-1/processing-result.json').exists()
    index = json.loads((phase.owner.root / 'collection-index.json').read_text())
    assert index['schema_version'] == 3 and len(index['committed_episodes']) == 2
    assert len(index['collected_tasks']) == 3
    decision = json.loads((phase.owner.root / 'host/retry-round-1.json').read_text())
    assert decision['status'] == 'RUN' and decision['candidates'] == ['scene-00']
    assert decision['plans'][0]['wave_index'] == 1


def test_two_retry_rounds_keep_wave_and_processing_numbers_increasing(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch, outcomes=('INVALID', 'INVALID', 'VALID'))
    result = drive(phase)
    assert phase.world.waves == [0, 1, 2] and phase.proc_counts['scene-00'] == 3
    assert result['retry']['rounds_run'] == 2 and result['retry']['recovered'] == 1


@pytest.mark.parametrize('reason', ['NO_CANDIDATES', 'RETRY_ROUND_DOES_NOT_FIT_DEADLINE', 'RETRY_ROUND_DISK'])
def test_ineligible_or_unaffordable_rounds_are_recorded_without_launching_shards(tmp_path, monkeypatch, reason):
    phase = retry_world(tmp_path, monkeypatch, outcomes=('VALID',) if reason == 'NO_CANDIDATES' else ('INVALID',))
    if reason == 'RETRY_ROUND_DOES_NOT_FIT_DEADLINE':
        phase.owner.config['verification_reserve_s'] = 3600
    if reason == 'RETRY_ROUND_DISK':
        phase.owner.disk_reader = lambda root: 99
    result = drive(phase)
    assert phase.world.waves == [0] and result['retry']['rounds_run'] == 0
    decision = json.loads((phase.owner.root / 'host/retry-round-1.json').read_text())
    assert decision['status'] == 'SKIPPED' and decision['reason'] == reason


@pytest.mark.parametrize('qualification,processing,reason', [
    (True, True, 'CAMPAIGN_RETRY_QUALIFICATION_FORBIDDEN'),
    (False, False, 'CAMPAIGN_RETRY_REQUIRES_PROCESSING'),
])
def test_retry_is_refused_before_any_service_effect(tmp_path, monkeypatch, qualification, processing, reason):
    phase = retry_world(tmp_path, monkeypatch)
    phase.owner.qualification = qualification
    if not processing:
        phase.owner.processing = None
    with pytest.raises(ValueError, match=reason):
        drive(phase)
    assert phase.world.calls == [] and phase.world.waves == []


def test_a_permanent_fault_after_the_phase1_deadline_is_never_reopened(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch)
    owner = phase.owner
    owner.stop_dispatch('CAMPAIGN_PHASE1_DEADLINE_EXPIRED')
    owner.stop_dispatch('operator')
    try:
        with pytest.raises(ValueError, match='CAMPAIGN_RETRY_DISPATCH_FENCED'):
            owner._reopen_recording(owner.context.deadline_monotonic_s - 600)
        assert owner.stop_reason == 'operator'
    finally:
        phase.world.registry.close()


def test_a_stopped_retry_infrastructure_failure_preserves_prior_final_results(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch)
    original = phase.owner.coordinator.run_wave

    async def run_wave(**kwargs):
        if kwargs['plan']['wave_index']:
            raise ValueError('RETRY_INFRASTRUCTURE_FAILURE')
        return await original(**kwargs)

    phase.owner.coordinator.run_wave = run_wave
    result = drive(phase)
    assert result['retry']['status'] == 'ABORTED' and result['retry']['recovered'] == 0
    assert not result.get('task_faults')
    combined = json.loads((phase.owner.root / 'host/campaign-result.json').read_text())
    assert combined['retry']['status'] == 'ABORTED'
    scene = combined['scenes'][0]
    assert scene['state'] == 'PROCESSED' and scene['recording_attempts'][-1]['state'] == 'MISSING'


def test_an_unproven_retry_stop_prevents_final_result_publication(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch)
    original = phase.owner.launcher

    def launch(**kwargs):
        shards = original(**kwargs)
        if kwargs['plan']['wave_index']:
            shards[0].release = False
        return shards

    phase.owner.launcher = launch
    with pytest.raises(ValueError, match='CAMPAIGN_RETRY_STOP_UNCONFIRMED'):
        drive(phase)
    assert not (phase.owner.root / 'collection-index.json').exists()


def test_the_monitor_does_not_enforce_the_old_recording_deadline_during_processing(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch)
    owner = phase.owner
    owner.phase1_deadline_s = owner.clock() / 1e9 - 1

    async def healthy():
        return None

    owner.services.check_health = healthy

    async def monitor():
        task = asyncio.create_task(owner._monitor())
        await asyncio.sleep(.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert owner.dispatch_stopped is False

    try:
        asyncio.run(monitor())
    finally:
        phase.world.registry.close()


def test_a_prepared_wave_closed_at_the_deadline_still_consumes_its_global_index(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch, scene_count=21)
    original = phase.owner.launcher

    def launch(**kwargs):
        shards = original(**kwargs)
        if kwargs['plan']['wave_index'] == 1:
            phase.owner.phase1_deadline_s = phase.owner.clock() / 1e9 - 1
        return shards

    phase.owner.launcher = launch
    result = drive(phase)
    assert phase.world.waves == [0, 2]
    assert phase.world.made[1].closes >= 1
    assert result['retry']['recovered'] == 1
    assert [item['scene_id'] for item in result['task_faults']] == ['scene-20']
