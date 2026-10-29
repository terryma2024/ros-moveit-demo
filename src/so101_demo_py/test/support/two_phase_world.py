"""Turns the 40-scene controlled world of `collection_qualification_world` into a two-phase run on disk. Not a test module.

REAL producer output: `ProcessingJournal` (the scheduler's own journal writer), `grade_episode` (the processor's own grading, over the
controlled QC double), `processed_result.canonical`, `verify_processing`, `build_campaign_result`, `build_frozen_index`, the registry
and the owner's `_write`.

CONTROLLED (labelled so nothing here reads as measured evidence): the phase-1 `PENDING_QC` form. The sealed results of the base world
carry an inline episode (a synthetic zero-row one), so phase 1 is derived from them: `pendingize_proof` turns the readback proof of a
scene with an episode into the phase-1 form (Teacher half, receipt hash) and the processed output directory is a copy of the sealed
directory without `result.json`. A scene without an episode (the manifest-free perception no-pose form) stays final at phase 1. The
recording receipts are minimal documents that carry the identity the processor would have bound. The processors are two registered and
settled processor launches; no container ran.
"""

import json
import shutil
from pathlib import Path

from so101_demo.act.processed_result import PROCESSED_KIND, canonical as processed_canonical
from so101_demo.act.result_store import export_eligible
from so101_demo.runtime.container_campaign import container_receipts, result_verifier, stage_records
from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingJournal
from so101_demo.runtime.container_campaign.processing_verifier import build_campaign_result, verify_processing
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_demo.runtime.container_campaign.task_journal import read_container_task_result
from so101_demo.runtime.container_campaign.process_identity import ContainerOwnerKey
from collection_qualification_world import (
    CAMPAIGN_ID, SHARD_IMAGE, STARTED, inspect_document, provenance_document, sha)

import hashlib

_BINDING = ('qc_report_sha256', 'inputs_sha256', 'scope_sha256', 'audit_manifest_sha256', 'collection_mode', 'episode_seal_sha256')


def _rewrite(path, document):
    Path(path).unlink()
    _write(path, document)


def receipt_path(sealed):
    return Path(sealed)/'raw'/'recording-receipt.json'


def pendingize_proof(proof):
    """The phase-1 form of a readback proof: only a scene with an episode is pending."""
    if proof['episode_seal_sha256'] is None:
        return proof
    return dict(proof, processing='PENDING', receipt_sha256=sha(receipt_path(proof['location'])), recording_files=1,
                recording_bytes=1, act_data_status='PENDING_QC', act_data_qc='NOT_RUN', export_eligible=False,
                **{name: None for name in _BINDING})


def pendingize_verified(verified):
    return dict(verified, case_results=[dict(row, proof=pendingize_proof(row['proof'])) for row in verified['case_results']])


def install_pending_verifier(patch):
    """`verify_wave_records` as the two-phase Host sees it: the recomputation yields phase-1 proofs."""
    original = result_verifier.verify_wave_records

    def wrapper(*args, **kwargs):
        return pendingize_verified(original(*args, **kwargs))
    patch.setattr(result_verifier, 'verify_wave_records', wrapper)


def register_processor(run, slot, generation, *, settle=True):
    """One processor launch in the registry, bound to its container and (by default) settled by its exit inspect."""
    registry = ContainerLaunchRegistry(Path(run)/'host'/'launches.sqlite3', create=False)
    try:
        worker = f'p{slot:02d}'
        owned = Path(run)/'processing'/worker/f'g{generation}'
        owned.mkdir(parents=True, exist_ok=True)
        launch = ContainerLaunch(launch_id=f'processing-{worker}-g{generation}', role='processor', worker_id=worker, wave_id=None,
            launch_generation=generation, container_name=f'so101-qualification-{worker}-g{generation}',
            image_digest=SHARD_IMAGE['digest'], owned_root=str(owned), session_id=None)
        owner = ContainerOwnerKey(hashlib.sha256(launch.container_name.encode()).hexdigest(), STARTED, SHARD_IMAGE['digest'],
                                  generation)
        registry.register(launch)
        registry.bind_container(launch.launch_id, owner)
        _write(owned/'actual-container-provenance.json', provenance_document(owner, SHARD_IMAGE))
        if settle:
            registry.prove_terminated(launch.launch_id, inspect_document(owner))
        return launch.launch_id
    finally:
        registry.close()


def fault_phase1_task(run, stored, scene, reason):
    """Turn a collected phase-1 task into a journaled task fault: `failed.json` replaces `collected.json`, the scene's row leaves its
    wave record and the wave lists the fault the way `verify_wave_records` does (CONTROLLED edit of the base world)."""
    for wave in stored:
        row = next((item for item in wave['case_results'] if item['scene_id'] == scene), None)
        if row is None:
            continue
        directory = Path(run)/'host'/f'wave-{wave["wave_index"]}'/'task-journal'/row['task_id']
        assigned = json.loads((directory/'assigned.json').read_bytes())
        (directory/'collected.json').unlink()
        _write(directory/'failed.json', dict({name: assigned[name] for name in (
            'task_id', 'instance_id', 'worker_id', 'launch_generation', 'wave_id', 'scene_id', 'owner_root', 'host_output')},
            schema_version=1, kind='ACT_CONTAINER_TASK_FAILED', reason=reason, failed_monotonic_s=1.))
        wave['case_results'] = [item for item in wave['case_results'] if item is not row]
        wave['faults'] = [dict(scene_id=scene, worker_id=row['worker_id'], task_id=row['task_id'], launch_id=row['launch_id'],
                               reason=reason)]
        return
    raise AssertionError('no such scene')


def convert(world, *, processors=2, missing=(), faults=(), exhausted=(), task_faults=()):
    """Rewrite a built world as a finished two-phase run; `missing`, `faults`, `exhausted` and `task_faults` are scene indexes
    (`task_faults`: the phase-1 task itself faulted)."""
    from so101_demo.runtime.act_processor.processing import grade_episode

    run = world.run
    stored = [json.loads((run/'host'/f'wave-{index}-verified.json').read_bytes()) for index in (0, 1)]
    for index in task_faults:
        fault_phase1_task(run, stored, world.scenes[index], 'CONTAINER_INSTANCE_REPORTED_FAULT: native stack died')
    journal = ProcessingJournal(run/'host'/'processing-journal.jsonl')
    summary, queue = [], []
    for wave in stored:
        for row in wave['case_results']:
            proof = row['proof']
            if proof['episode_seal_sha256'] is None:
                continue
            scene, sealed = row['scene_id'], Path(proof['location'])
            attempt = scene+'-lease-1'
            legacy = json.loads((sealed/'result.json').read_bytes())
            identity = dict(session_id='session-1', reset_epoch=2, attempt_id=attempt)
            receipt_path(sealed).parent.mkdir(exist_ok=True)
            lease = read_container_task_result(row['owner_root'], task_id=row['task_id'])['result']['lease']
            receipt_path(sealed).write_bytes(json.dumps(dict(identity=identity, lease_identity=lease), sort_keys=True).encode()+b'\n')
            queue.append((scene, sealed, legacy, identity, proof, lease))
    waves = [pendingize_verified(wave) for wave in stored]
    journal.append('phase2_start', queue=[item[0] for item in queue], processors=processors, max_attempts=3, deadline_s=1e9)
    for scene, sealed, legacy, identity, proof, lease in queue:
        index = world.scenes.index(scene)
        attempt = scene+'-lease-1'
        task = f'{scene}-proc-1'
        output = run/'processing'/scene/f'{attempt}-proc-1'
        if index in missing:
            journal.append('scene_missing', scene_id=scene, reason='PROCESSING_DEADLINE')
            summary.append(dict(scene_id=scene, status='MISSING', reason='PROCESSING_DEADLINE', attempts=0))
            continue
        journal.append('dispatch', scene_id=scene, task_id=task, proc_attempt=1, processor_id='p00', launch_generation=1,
                       output_dir=str(output))
        if index in faults:
            journal.append('result', scene_id=scene, task_id=task, proc_attempt=1, outcome='REFUSED', retryable=False,
                           reason='PHASE1_RECORD_REFUSED', processor_rc=None)
            journal.append('scene_fault', scene_id=scene, fault='PROCESSING_REFUSED', reason='PHASE1_RECORD_REFUSED')
            summary.append(dict(scene_id=scene, status='FAULT', fault='PROCESSING_REFUSED', reason='PHASE1_RECORD_REFUSED',
                                attempts=1))
            continue
        if index in exhausted:
            for number in (1, 2, 3):
                if number > 1:
                    journal.append('dispatch', scene_id=scene, task_id=f'{scene}-proc-{number}', proc_attempt=number,
                                   processor_id='p01', launch_generation=1, output_dir=str(output.parent/f'{attempt}-proc-{number}'))
                journal.append('result', scene_id=scene, task_id=f'{scene}-proc-{number}', proc_attempt=number,
                               outcome='INFRASTRUCTURE_FAILURE', retryable=True, reason='OFFLINE_PROCESSOR_FAILED: rc=4',
                               processor_rc=4)
                if number < 3:
                    journal.append('retry', scene_id=scene, next_attempt=number+1, reason='OFFLINE_PROCESSOR_FAILED: rc=4')
            journal.append('scene_fault', scene_id=scene, fault='PROCESSING_RETRIES_EXHAUSTED', reason='OFFLINE_PROCESSOR_FAILED: rc=4')
            summary.append(dict(scene_id=scene, status='FAULT', fault='PROCESSING_RETRIES_EXHAUSTED',
                                reason='OFFLINE_PROCESSOR_FAILED: rc=4', attempts=3))
            continue
        shutil.copytree(sealed, output)
        (output/'result.json').unlink()
        # a real phase-2 output directory has no dynamic/: the Teacher manifest is phase 1's sealed one, passed explicitly
        shutil.rmtree(output/'dynamic')
        graded = grade_episode(out=output, qc_output=output/'qc-report.json', lease=lease, identity=identity,
                               scope=world.scopes[scene], inputs_manifest=world.inputs_manifest, teacher_status=legacy['status'],
                               teacher_manifest=sealed/'dynamic'/'dynamic-execute-manifest.json')
        if graded['binding'] is None:
            raise AssertionError('controlled grading failed: '+str(graded['reason']))
        binding = graded['binding']
        document = dict(kind=PROCESSED_KIND, schema_version=1, task_id=task, scene_id=scene, proc_attempt=1,
            phase1_result_sha256=proof['result_sha256'], receipt_sha256=sha(receipt_path(sealed)),
            lease_identity=lease, identity=identity, status=legacy['status'], processor_rc=0,
            diagnostic_fault='none', artifacts={}, act_data_status=graded['status'], act_data_reason=graded['reason'],
            act_data_qc=graded['qc'], episode_seal_sha256=graded['episode_sha256'],
            export_eligible=export_eligible(legacy['status'], graded['qc'], binding['collection_mode']), **binding)
        (output/'processed-result.json').write_bytes(processed_canonical(document))
        outcome = 'VALID' if graded['status'] == 'VALID' and graded['qc'] == 'PASS' else 'INVALID'
        journal.append('result', scene_id=scene, task_id=task, proc_attempt=1, outcome=outcome, retryable=False,
                       reason=graded['reason'], processor_rc=0)
        summary.append(dict(scene_id=scene, status='FINAL', outcome=outcome, reason=graded['reason'], attempts=1,
                            output_dir=str(output), processed_result=dict(path='processed-result.json', sha256='x'*64)))
    journal.append('phase2_end', counts={}, processors_stopped=True)
    _write(run/'host'/'processing-result.json', dict(schema_version=1, kind='act_collection_processing_summary',
        campaign_id=CAMPAIGN_ID, processors=processors, processors_stopped=True, scenes=summary))
    for slot in range(processors):
        register_processor(run, slot, 1)
    for wave in waves:
        _rewrite(run/'host'/f'wave-{wave["wave_index"]}-verified.json', wave)
    combined = verify_processing(run, waves, world.scenes, readback_workers=1)
    _rewrite(run/'host'/'campaign-result.json', build_campaign_result(CAMPAIGN_ID, len(world.scenes), combined))
    _rewrite(run/'collection-index.json', build_frozen_index(campaign_id=CAMPAIGN_ID, qualification=True,
                                                           scene_count=len(world.scenes), combined=combined))
    cleanup = json.loads((run/'host'/'campaign-cleanup.json').read_bytes())
    cleanup['processors'] = [dict(terminated=True, launch_id=f'processing-p{slot:02d}-g1', errors=[]) for slot in range(processors)]
    _rewrite(run/'host'/'campaign-cleanup.json', cleanup)
    return combined


def to_staged(run, attempts=None, receipted_failures=()):
    """Turns the finished two-phase run `convert` left into the form a run collected stage by stage leaves (CONTROLLED edit).

    REAL producers: `stage_records.write_record` for phase1, phase2 and finalize, `container_receipts.container_entry` and
    `write_receipt` (the hash chain), the owner's `_write`. CONTROLLED: the saved logs (one small file per container), the stage record
    bodies (only the logic document ref) and the split of the single cleanup record into the three per-stage records the owner writes
    (`campaign-cleanup.json` for phase 1, `campaign-cleanup-phase2.json`, `campaign-cleanup-finalize.json`, each naming its receipt).

    `attempts` maps a stage to the attempt that completed it (default 1). For an attempt above 1 the stage record carries `attempt`, the
    cleanup record has the `.aN` name, and the failed attempts before it leave their own cleanup record (a stage that launched nothing).
    A stage in `receipted_failures` also leaves, for each failed attempt, an empty receipt `<stage>-a<N>` (what the owner writes for a
    failed attempt that started a Teacher; here the receipt has no container) that the failed attempt's cleanup record names."""
    attempts = attempts or {}
    host = Path(run)/'host'
    registry = ContainerLaunchRegistry(host/'launches.sqlite3', create=False, read_only=True)
    try:
        records = registry.records()
    finally:
        registry.close()
    whole = json.loads((host/'campaign-cleanup.json').read_bytes())
    groups = dict(phase1=[item for item in records if item['launch']['role'] != 'processor'],
                  phase2=[item for item in records if item['launch']['role'] == 'processor'], finalize=[])
    empty = dict(terminated=True, launch_ids=[], errors={})
    documents = dict(
        phase1=dict(services=whole['services'], shards=whole['shards']),
        phase2=dict(services=empty, shards=[], processors=whole['processors']),
        finalize=dict(services=empty, shards=[]))
    previous = None
    for number, stage in enumerate(('phase1', 'phase2', 'finalize'), start=1):
        attempt = attempts.get(stage, 1)
        previous = stage_records.write_record(host, stage, dict(campaign_config=dict(path='campaign-config.json', sha256='c'*64)),
                                              previous=previous, attempt=attempt)
        entries = []
        for item in groups[stage]:
            name = item['launch']['container_name']
            raw = f'log of {name}\n'.encode()
            directory = host/container_receipts.LOG_DIRECTORY/stage
            directory.mkdir(parents=True, exist_ok=True)
            (directory/f'{name}.log').write_bytes(raw)
            entries.append(dict(container_receipts.container_entry(item, item['exit_inspect']),
                                logs_path=f'{container_receipts.LOG_DIRECTORY}/{stage}/{name}.log',
                                logs_sha256=hashlib.sha256(raw).hexdigest(), removed=True, absent_after_removal=True))
        failed_receipts = {}
        if stage in receipted_failures:
            for failed in range(1, attempt):
                failed_receipts[failed] = container_receipts.write_receipt(host, stage=f'{stage}-a{failed}', stage_record_sha256=None,
                                                                           containers=[])
        receipt = container_receipts.write_receipt(host, stage=stage, stage_record_sha256=previous['sha256'], containers=entries)
        document = dict(documents[stage], terminated=True, stop_reason='CAMPAIGN_CLOSING',
                        container_receipt=f'containers-receipt-{receipt["seq"]:02d}-{stage}.json')
        path = host/('campaign-cleanup.json' if stage == 'phase1' else stage_records.cleanup_path(host, stage, attempt).name)
        if path.exists():
            path.unlink()
        _write(path, document)
        for failed in range(1, attempt):
            body = dict(terminated=True, services=empty, shards=[], stop_reason='CAMPAIGN_CLOSING')
            if failed in failed_receipts:
                body['container_receipt'] = f'containers-receipt-{failed_receipts[failed]["seq"]:02d}-{stage}-a{failed}.json'
            _write(stage_records.cleanup_path(host, stage, failed), body)
