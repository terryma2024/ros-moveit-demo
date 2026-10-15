"""Phase-1 host verification: PENDING_QC task results are read back together with their recording receipt.

Real producers as in `test_task_commit_readback` (store, summary, task results, journal, registry); the sealed fixture is the
phase-1 form (Teacher manifest and result, raw bag files, recording receipt, no episode, no QC). Anything that needs a processed
episode refuses with PROCESSING_PENDING instead of passing silently. Nothing here is qualification evidence.
"""

import hashlib
import json

import pytest

from test_task_commit_readback import (
    INVALID, build_task, real_verifier, ref, verify, wave_outcome, wave_records, rewrite_registration)  # noqa: F401
from so101_demo.runtime.container_campaign import result_verifier
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index


@pytest.fixture
def pending(tmp_path, monkeypatch):
    return build_task(tmp_path, monkeypatch, phase1_pending=True)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_pending_task_is_read_back_with_its_receipt_into_a_phase_one_proof(pending):
    assert not (pending.location/'episode/seal.json').exists() and (pending.location/'raw/recording-receipt.json').is_file()
    proof = verify(pending)
    assert proof['kind'] == 'ACT_CONTAINER_TASK_READBACK' and proof['status'] == 'PASS'
    assert (proof['result_status'], proof['act_data_status'], proof['act_data_qc'], proof['export_eligible']) == (
        'PASSED', 'PENDING_QC', 'NOT_RUN', False)
    assert (proof['teacher_execution_status'], proof['teacher_task_result']) == ('COMPLETED', 'PASS')
    assert proof['processing'] == 'PENDING'
    assert proof['receipt_sha256'] == _sha(pending.location/'raw/recording-receipt.json')
    assert proof['result_sha256'] == pending.summary['sealed']['result']['sha256']
    assert proof['task_result_sha256'] and proof['location'] == str(pending.location)
    assert proof['episode_seal_sha256'] is None and proof['qc_report_sha256'] is None
    assert proof['recording_files'] >= 4 and proof['recording_bytes'] > 0


def test_a_processed_task_reports_no_pending_processing(tmp_path, monkeypatch):
    proof = verify(build_task(tmp_path, monkeypatch))
    assert proof['processing'] == 'NOT_PENDING' and proof['receipt_sha256'] is None


@pytest.mark.parametrize('edit', ['bag_byte', 'unlisted_file', 'missing_file', 'receipt_removed', 'receipt_edited', 'orchestration_edited', 'orchestration_removed'])
def test_a_pending_task_whose_receipt_does_not_match_its_files_is_refused(pending, edit):
    raw = pending.location/'raw'
    if edit == 'bag_byte':
        (raw/'bag/bag_0.db3').write_bytes(b'bag' * 4095 + b'xyz')
    elif edit == 'unlisted_file':
        (raw/'extra.bin').write_bytes(b'x')
    elif edit == 'missing_file':
        (raw/'record-stats.json').unlink()
    elif edit == 'orchestration_edited':
        (pending.location/'recorder-orchestration.json').write_text('{"fault_deferred_to_processing": "bag_drop"}\n')
    elif edit == 'orchestration_removed':
        (pending.location/'recorder-orchestration.json').unlink()
    elif edit == 'receipt_removed':
        (raw/'recording-receipt.json').unlink()
    else:
        document = json.loads((raw/'recording-receipt.json').read_text())
        document['raw_files'][0]['sha256'] = '0' * 64
        (raw/'recording-receipt.json').write_text(json.dumps(document))
    with pytest.raises(ValueError, match=INVALID):
        verify(pending)


def test_a_receipt_for_another_lease_is_refused(pending):
    path = pending.location/'raw/recording-receipt.json'
    document = json.loads(path.read_text())
    document['lease_identity']['attempt_id'] = 'other-lease-1'
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=INVALID):
        verify(pending)


def test_a_receipt_bound_to_other_inputs_is_refused(pending):
    path = pending.location/'raw/recording-receipt.json'
    document = json.loads(path.read_text())
    document['documents']['scope']['sha256'] = '1' * 64
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=INVALID):
        verify(pending)


def _wave(world, proof):
    return dict(case_results=[dict(scene_id='point-1', worker_id='w00', task_id=world.task_id, launch_id='wave-0-w00-g1',
        location=str(world.task_dir), proof=proof, registration=str(world.registration), owner_root=str(world.owner),
        scope_path=str(world.scope), inputs_manifest=str(world.inputs))])


def test_the_frozen_index_refuses_a_pending_proof_instead_of_listing_it(pending):
    proof = verify(pending)
    with pytest.raises(ValueError, match='PROCESSING_PENDING'):
        build_frozen_index(campaign_id='campaign', qualification=False, scene_count=1, waves=[_wave(pending, proof)])


def test_the_export_gates_refuse_a_pending_proof_with_the_pending_reason():
    from so101_demo.act.bundle import _export_gates
    proof = dict(status='PASS', result_schema_version=3, result_status='PASSED', processing='PENDING', act_data_qc='NOT_RUN',
                 export_eligible=False)
    with pytest.raises(ValueError, match='EXPORT_EPISODE_PROCESSING_PENDING'):
        _export_gates({'mode': 'formal'}, proof, {})


def test_a_receipt_of_another_session_identity_is_refused(pending):
    path = pending.location/'raw/recording-receipt.json'
    document = json.loads(path.read_text())
    document['identity']['session_id'] = 'session-other'
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=INVALID):
        verify(pending)


def test_the_wave_verifier_returns_the_phase_one_proof_and_the_record_equals_the_offline_recomputation(pending):
    registry, verifier, shards = real_verifier(pending)
    plan = dict(wave_index=0, scene_ids=['point-1'], assignment=None)
    try:
        value = verifier.verify_wave(plan, wave_outcome(pending), shards)
        row = value['case_results'][0]
        assert row['proof']['processing'] == 'PENDING' and row['proof']['receipt_sha256']
        assert value == result_verifier.verify_wave_records(pending.run, plan, wave_records(registry), verifier.case_inputs, False)
    finally:
        registry.close()
