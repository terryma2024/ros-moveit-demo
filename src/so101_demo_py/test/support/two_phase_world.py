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
from so101_demo.runtime.container_campaign import result_verifier
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


def convert(world, *, processors=2, missing=(), faults=(), exhausted=()):
    """Rewrite a built world as a finished two-phase run; `missing`, `faults` and `exhausted` are scene indexes."""
    from so101_demo.runtime.act_processor.processing import grade_episode

    run = world.run
    stored = [json.loads((run/'host'/f'wave-{index}-verified.json').read_bytes()) for index in (0, 1)]
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
        graded = grade_episode(out=output, qc_output=output/'qc-report.json', lease=lease, identity=identity,
                               scope=world.scopes[scene], inputs_manifest=world.inputs_manifest, teacher_status=legacy['status'])
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
