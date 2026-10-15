"""After phase 2 the owner writes `campaign-result.json` and `collection-index.json` from the combined per-scene proof of both phases.

The combiner is a recording double (its behaviour is `test_processing_verifier`); the owner's part is when it is called, with what, and
which documents it writes from the answer. `phase1-result.json` stays the phase-1 record."""

import asyncio
import json

import pytest

from so101_demo.runtime.container_campaign.processing_verifier import build_campaign_result
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index
from test_owner_phase1 import pending_verified
from test_owner_phase2 import phase2_world


def combined_for(waves, ids):
    rows = {row['scene_id']: row for wave in waves for row in wave['case_results']}
    scenes = []
    for scene in ids:
        row = rows.get(scene)
        if row is None:
            scenes.append(dict(scene_id=scene, state='MISSING', reason='PHASE1_NOT_RECORDED', phase1=None, phase2=None, attempts=[],
                               worker_id=None, task_id=None, launch_id=None, location=None, registration=None, owner_root=None,
                               scope_path=None, inputs_manifest=None,
                               verdict=dict(status='NOT_RECORDED', teacher_execution_status=None, teacher_task_result=None,
                                            act_data_status='PROCESSING_MISSING', act_data_reason=None, act_data_qc='NOT_RUN',
                                            export_eligible=False)))
            continue
        phase2 = dict(processed_result=dict(path='processed-result.json', sha256='d'*64), output_dir='/proc/'+scene)
        scenes.append(dict(scene_id=scene, state='PROCESSED', reason=None, phase1=row['proof'], phase2=phase2, attempts=[],
                           **{key: row[key] for key in ('worker_id', 'task_id', 'launch_id', 'location', 'registration',
                                                        'owner_root', 'scope_path', 'inputs_manifest')},
                           verdict=dict(status='PASSED', teacher_execution_status='COMPLETED', teacher_task_result='PASS',
                                        act_data_status='VALID', act_data_reason=None, act_data_qc='PASS', export_eligible=True)))
    counts = {state: sum(1 for item in scenes if item['state'] == state) for state in
              ('PROCESSED', 'FINAL_AT_PHASE1', 'FAULT', 'MISSING')}
    return dict(schema_version=1, kind='act_collection_combined_proof', scene_count=len(scenes), counts=counts,
                missing_evidence=[item['scene_id'] for item in scenes if item['phase1'] is None],
                processing=dict(summary=None, journal=None), scenes=scenes)


def test_the_campaign_result_and_the_index_come_from_the_combined_proof_after_phase_two(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8)
    owner = phase.owner
    calls = []

    def verify_processing(waves, ids):
        phase.order.append('combine')
        calls.append((waves, list(ids)))
        return combined_for(waves, ids)
    owner.verifier.verify_processing = verify_processing

    async def run():
        result = await owner.run(phase.world.manifest)
        assert phase.order[-2:] == ['phase2', 'combine'], 'the combined proof is built only after phase 2 ended'
        waves, ids = calls[0]
        assert ids == [f'scene-{i:02d}' for i in range(8)] and len(waves) == 1
        combined = combined_for(waves, ids)
        stored = json.loads((owner.root/'host/campaign-result.json').read_text())
        assert stored == json.loads(json.dumps(build_campaign_result(owner.context.campaign_id, 8, combined)))
        assert stored['kind'] == 'act_collection_campaign_result' and 'waves' not in stored
        index = json.loads((owner.root/'collection-index.json').read_text())
        assert index == json.loads(json.dumps(build_frozen_index(campaign_id=owner.context.campaign_id, qualification=False,
                                                                  scene_count=8, combined=combined)))
        assert len(index['committed_episodes']) == 8 and index['committed_episodes'][0]['schema_version'] == 4
        assert (owner.root/'host/phase1-result.json').is_file(), 'phase1-result.json stays the phase-1 record'
        phase1 = json.loads((owner.root/'host/phase1-result.json').read_text())
        assert phase1['processing'] == 'PENDING' and 'scenes' not in phase1
        assert result['processing'] == 'COMPLETE' and result['phase2']['counts']['VALID'] == 8
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_a_qualification_campaign_writes_an_index_without_committed_episodes(tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module('so101_demo.runtime.container_campaign.owner')
    phase = phase2_world(tmp_path, monkeypatch, scene_count=8, qualification=True)
    owner = phase.owner
    names = tuple(f'scene-{i:02d}' for i in range(8))
    monkeypatch.setattr(module, 'validate_run_contract', lambda document: ('functional', dict(
        worker_count=owner.context.worker_count, scene_manifest=None)))
    monkeypatch.setattr(module, 'scene_ids', lambda manifest, count=None: names)
    owner.verifier.verify_processing = combined_for

    async def run():
        await owner.run(phase.world.manifest)
        index = json.loads((owner.root/'collection-index.json').read_text())
        assert index['qualification'] is True and index['committed_episodes'] == [] and len(index['collected_tasks']) == 8
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_scenes_a_phase_one_deadline_left_unrecorded_appear_in_the_combined_documents(tmp_path, monkeypatch):
    order = []

    def verify(plan, outcome, shards, partial=False):
        return pending_verified(order)(plan, outcome, shards)
    phase = phase2_world(tmp_path, monkeypatch, scene_count=21, config={'collect_timeout_s': 1}, verify=verify)
    owner = phase.owner
    owner.verifier.verify_processing = combined_for

    async def run_wave(*, plan, shards, endpoints, dispatch_allowed):
        await asyncio.sleep(1.3)
        kept = plan['scene_ids'][:5]
        rows = [dict(scene_id=scene, worker_id='w00', location='/out/'+scene, task_id='wave-0-w00-'+scene, launch_id='l')
                for scene in kept]
        return dict(wave_index=plan['wave_index'], coordinator_root='x', case_results=rows, infra_errors=[])
    owner.coordinator.run_wave = run_wave

    async def run():
        await owner.run(phase.world.manifest)
        stored = json.loads((owner.root/'host/campaign-result.json').read_text())
        assert stored['missing_evidence'] == [f'scene-{i:02d}' for i in range(5, 21)]
        assert [item['scene_id'] for item in stored['scenes']] == [f'scene-{i:02d}' for i in range(21)]
        index = json.loads((owner.root/'collection-index.json').read_text())
        assert [item['scene_id'] for item in index['scenes_without_evidence']] == stored['missing_evidence']
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_a_task_fault_in_one_scene_does_not_stop_the_campaign_and_the_other_scenes_get_a_verdict(tmp_path, monkeypatch):
    order = []
    faulted = 'scene-03'

    def verify(plan, outcome, shards, partial=False):
        value = pending_verified(order)(plan, dict(outcome), shards)
        if faulted in plan['scene_ids']:
            value['case_results'] = [row for row in value['case_results'] if row['scene_id'] != faulted]
            value['faults'] = [dict(scene_id=faulted, worker_id='w00', task_id='wave-0-w00-'+faulted, launch_id='l',
                                    reason='CONTAINER_TASK_FAILED: boom')]
        return value
    phase = phase2_world(tmp_path, monkeypatch, scene_count=21, verify=verify)
    owner = phase.owner
    seen = []

    def verify_processing(waves, ids):
        seen.append((waves, list(ids)))
        return combined_for(waves, ids)
    owner.verifier.verify_processing = verify_processing

    async def run_wave(*, plan, shards, endpoints, dispatch_allowed):
        outcome = dict(wave_index=plan['wave_index'], coordinator_root='x', case_results=[], infra_errors=[])
        if faulted in plan['scene_ids']:
            outcome['scene_faults'] = [dict(scene_id=faulted, task_id='wave-0-w00-'+faulted, worker_id='w00')]
        return outcome
    owner.coordinator.run_wave = run_wave

    async def run():
        result = await owner.run(phase.world.manifest)
        assert owner.stop_reason is None, 'a task fault stops nothing'
        assert phase.order.count('syncfs') == 1 and len(seen) == 1, 'the owner went on to phase 2 and the combined proof'
        queued = [row['scene_id'] for row in phase.scheduler.calls[0]['rows']]
        assert faulted not in queued and len(queued) == 20
        assert result['task_faults'] == [dict(scene_id=faulted, reason='CONTAINER_TASK_FAILED: boom')]
        assert (owner.root/'host/campaign-result.json').is_file() and (owner.root/'collection-index.json').is_file()
        assert [wave.get('faults') for wave in seen[0][0]] == [[dict(scene_id=faulted, worker_id='w00',
            task_id='wave-0-w00-'+faulted, launch_id='l', reason='CONTAINER_TASK_FAILED: boom')], None]
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_an_infrastructure_error_in_a_wave_still_stops_the_campaign(tmp_path, monkeypatch):
    def refuse(plan, outcome, shards, partial=False):
        raise ValueError('CONTAINER_WAVE_COMMIT_READBACK_INVALID')
    phase = phase2_world(tmp_path, monkeypatch, scene_count=21, verify=refuse)

    async def run_wave(*, plan, shards, endpoints, dispatch_allowed):
        return dict(wave_index=plan['wave_index'], coordinator_root='x', case_results=[],
                    infra_errors=[dict(type='InstanceFault', reason='CONTAINER_INSTANCE_TERMINATE_FAILED: x')])
    phase.owner.coordinator.run_wave = run_wave

    async def run():
        with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
            await phase.owner.run(phase.world.manifest)
        assert phase.scheduler.calls == []
        await phase.owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()


def test_a_phase_two_fault_or_missing_scene_is_reported_as_a_task_fault_so_the_cli_exits_non_zero(tmp_path, monkeypatch):
    phase = phase2_world(tmp_path, monkeypatch, scene_count=4)
    owner = phase.owner

    def verify_processing(waves, ids):
        combined = combined_for(waves, ids)
        for scene, (state, reason) in zip(combined['scenes'][:2], (('FAULT', 'PROCESSOR_UNREACHABLE: X'), ('MISSING', 'PROCESSING_NOT_RUN'))):
            scene.update(state=state, reason=reason)
        combined['counts'] = {state: sum(1 for item in combined['scenes'] if item['state'] == state)
                              for state in ('PROCESSED', 'FINAL_AT_PHASE1', 'FAULT', 'MISSING')}
        return combined
    owner.verifier.verify_processing = verify_processing

    async def run():
        result = await owner.run(phase.world.manifest)
        assert result['task_faults'] == [dict(scene_id='scene-00', reason='PROCESSOR_UNREACHABLE: X'),
                                         dict(scene_id='scene-01', reason='PROCESSING_NOT_RUN')]
        await owner.close()
    try:
        asyncio.run(run())
    finally:
        phase.world.registry.close()
