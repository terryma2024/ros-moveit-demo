"""The quality gates over the two-phase combined proof: the data gates read the phase-2 locations, the Teacher gate the phase-1 manifest.

REAL: the sealed episode, the QC report and the topic-loss document come from the production writers through the controlled world
(`collection_qualification_world.seal_task`; its QC recomputation double is the one the existing readback tests use). The phase-2 output
directory is a copy of that sealed directory without `result.json`, plus a `processed-result.json` written here in the processor's
shape, so a gate that still read `result.json` for the data would fail. The phase-1 location is the original directory.
"""

import hashlib
import json
import shutil

import pytest

from collection_qualification_world import MODE, install_controlled_qc, seal_task
from so101_demo.act.collection_quality_gates import QUALITY_ORDER, evaluate_scene
from so101_demo.act.collection_scope import build_collection_scope, write_collection_scope
from so101_demo.act.processed_result import PROCESSED_KIND, canonical
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.runtime.parallel_ipc.frames import canonical_json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def real_scene(tmp_path, monkeypatch, *, outcome='PASSED', qc='PASS', loss=False, scene='load-00'):
    install_controlled_qc(monkeypatch)
    inputs = tmp_path/'inputs-manifest.json'
    inputs.write_bytes(canonical_json(dict(inputs_sha256='a'*64, mode=MODE))+b'\n')
    scope = tmp_path/'scope.json'
    write_collection_scope(build_collection_scope(MODE, scene_id=scene, seed=200, inputs_sha256='a'*64), scope)
    lease = LeaseIdentity(batch_id='c-wave-0', coordinator_epoch=1, worker_id='w00', worker_generation=1, point_id=scene,
        attempt_id=scene+'-lease-1', lease_generation=1, lease_issued_monotonic_s=10.25, lease_deadline_monotonic_s=10.75)
    sealed = seal_task(tmp_path/'task', lease, scope, inputs, seed=200, outcome=outcome, qc=qc, loss=loss)
    legacy = json.loads((sealed/'result.json').read_bytes())
    output = tmp_path/'processing'/scene/(lease.attempt_id+'-proc-1')
    shutil.copytree(sealed, output)
    (output/'result.json').unlink()
    document = dict(kind=PROCESSED_KIND, schema_version=1, task_id=scene+'-proc-1', scene_id=scene, proc_attempt=1,
        phase1_result_sha256=sha((sealed/'result.json').read_bytes()), receipt_sha256='r'*64, lease_identity=legacy['lease_identity'],
        identity={}, status=legacy['status'], processor_rc=0, diagnostic_fault='none', artifacts={},
        act_data_status=legacy['act_data_status'], act_data_reason=legacy['act_data_reason'], act_data_qc=legacy['act_data_qc'],
        episode_seal_sha256=legacy['episode_seal_sha256'], export_eligible=legacy['export_eligible'],
        qc_report_path='qc-report.json' if legacy['qc_report_sha256'] else None, qc_report_sha256=legacy['qc_report_sha256'],
        inputs_sha256=legacy['inputs_sha256'], scope_sha256=legacy['scope_sha256'],
        audit_manifest_sha256=legacy['audit_manifest_sha256'], collection_mode=legacy['collection_mode'])
    (output/'processed-result.json').write_bytes(canonical(document))
    proof = dict(location=str(sealed), result_sha256=document['phase1_result_sha256'], processing='PENDING')
    processed = dict(output_dir=str(output), data_dir=str(output),
                     processed_result=dict(path='processed-result.json', sha256=sha(canonical(document))),
                     phase1_result_sha256=document['phase1_result_sha256'])
    return proof, processed, output, sealed


def outcomes(verdicts):
    return {name: verdicts[name][0] for name in QUALITY_ORDER}


def test_the_data_gates_read_the_phase_2_locations_and_the_teacher_gate_the_phase_1_manifest(tmp_path, monkeypatch):
    proof, processed, output, sealed = real_scene(tmp_path, monkeypatch)
    verdicts, membership = evaluate_scene(proof, processed)
    assert outcomes(verdicts) == dict(recorder_lossless='PASS', frame_continuity='PASS', qc_valid_rate='PASS',
                                      teacher_physical_success_rate='PASS')
    assert all(error is None for _o, _s, error in verdicts.values()) and membership == (True, None)
    assert verdicts['recorder_lossless'][1]['path'] == str(output/'topic-loss.json')
    assert verdicts['frame_continuity'][1]['path'] == str(output/'episode'/'seal.json')
    assert verdicts['qc_valid_rate'][1]['path'] == str(output/'qc-report.json')
    assert verdicts['teacher_physical_success_rate'][1]['path'] == str(sealed/'dynamic'/'dynamic-execute-manifest.json')


def test_a_data_gate_failure_in_phase_2_and_a_teacher_failure_in_phase_1_are_graded_apart(tmp_path, monkeypatch):
    proof, processed, *_ = real_scene(tmp_path, monkeypatch, outcome='FAILED', loss=True)
    verdicts, _ = evaluate_scene(proof, processed)
    assert verdicts['recorder_lossless'][0] == 'FAIL' and verdicts['teacher_physical_success_rate'][0] == 'FAIL'


def test_a_scene_not_yet_processed_has_no_data_evidence_and_stays_in_every_population(tmp_path, monkeypatch):
    proof, _processed, *_ = real_scene(tmp_path, monkeypatch)
    verdicts, membership = evaluate_scene(proof, None)
    assert outcomes(verdicts) == dict(recorder_lossless='NO_EVIDENCE', frame_continuity='NO_EVIDENCE', qc_valid_rate='NO_EVIDENCE',
                                      teacher_physical_success_rate='PASS')
    assert all(error is None for _o, _s, error in verdicts.values()), 'missing evidence is not an evidence error'
    assert membership == (True, None), 'never a way out of the QC-valid denominator'


def test_a_scene_phase_1_never_recorded_has_no_evidence_for_any_gate(tmp_path):
    verdicts, membership = evaluate_scene(None, None)
    assert set(outcomes(verdicts).values()) == {'NO_EVIDENCE'} and membership == (True, None)
    assert all(error is None for _o, _s, error in verdicts.values())


DATA = ('recorder_lossless', 'frame_continuity', 'qc_valid_rate')


@pytest.mark.parametrize('damage,hit', [('processed-result.json', DATA), ('qc-report.json', DATA),
                                        ('topic-loss.json', ('recorder_lossless',)), ('episode/seal.json', ('frame_continuity',))])
def test_phase_2_evidence_that_contradicts_its_binding_is_evidence_invalid_for_the_gates_that_read_it(tmp_path, monkeypatch, damage, hit):
    proof, processed, output, _ = real_scene(tmp_path, monkeypatch)
    (output/damage).write_bytes(b'{}\n')
    verdicts, _ = evaluate_scene(proof, processed)
    for name in hit:
        assert verdicts[name][0] == 'NO_EVIDENCE' and verdicts[name][2] is not None, name
    assert verdicts['teacher_physical_success_rate'][0] == 'PASS', 'phase 1 evidence is independent of phase 2'


def test_a_processed_result_bound_to_another_phase_1_record_is_refused(tmp_path, monkeypatch):
    proof, processed, *_ = real_scene(tmp_path, monkeypatch)
    verdicts, _ = evaluate_scene(proof, dict(processed, phase1_result_sha256='0'*64))
    assert all(verdicts[name][2] is not None for name in DATA) and verdicts['teacher_physical_success_rate'][0] == 'PASS'
    with pytest.raises(ValueError, match='EVIDENCE_INVALID'):
        evaluate_scene(dict(proof, result_sha256='0'*64), processed)    # the phase-1 hash binds both phases


def test_an_invalid_processed_verdict_is_excluded_from_the_qc_valid_population_with_its_reason(tmp_path, monkeypatch):
    proof, processed, output, _ = real_scene(tmp_path, monkeypatch)
    document = json.loads((output/'processed-result.json').read_bytes())
    document.update(act_data_status='INVALID', act_data_qc='NOT_RUN', act_data_reason='OFFLINE_PROCESSOR_INVALID: rc=3',
                    export_eligible=False, qc_report_path=None, qc_report_sha256=None, inputs_sha256=None, scope_sha256=None,
                    audit_manifest_sha256=None, collection_mode=None)
    (output/'processed-result.json').write_bytes(canonical(document))
    processed = dict(processed, processed_result=dict(path='processed-result.json', sha256=sha(canonical(document))))
    verdicts, membership = evaluate_scene(proof, processed)
    assert outcomes(verdicts)['qc_valid_rate'] == 'NO_EVIDENCE' and membership == (False, 'NO_QC_EVIDENCE')
