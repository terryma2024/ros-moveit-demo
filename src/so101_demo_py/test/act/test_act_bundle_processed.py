"""Export from the two-phase combined proof (schema 4 committed episodes): the Teacher half is the phase-1 readback, the data half the
phase-2 `processed-result.json` readback, and the episode is read from the phase-2 output directory.

Controlled: both readbacks are replaced by documents built here (the real ones are `test_task_commit_readback` and
`test_processed_result`); the sealed episode, the QC report and the Teacher manifest are real files from the export fixture.
"""

import copy
import json
from pathlib import Path
import shutil

import pytest

from so101_demo.act.bundle import export_dataset, resolve_committed_episodes
from so101_demo.act.training import attach_episode_content
from test_act_bundle import frozen_index

MANIFEST = {"episodes": [{"scene_id": "001", "status": "PASSED"}]}


def schema4_entries(tmp_path, monkeypatch, scene_ids=('001',), processed_overrides=None, proof_overrides=None, **kwargs):
    from act_export_fixture import complete_export_entries
    from so101_demo.act import processed_result, result_store
    legacy_entries = complete_export_entries(tmp_path, monkeypatch, scene_ids, **kwargs)
    entries, documents = [], {}
    for entry in legacy_entries:
        scene = entry['scene_id']
        evidence = entry['collection_evidence']
        legacy = Path(evidence['result_location'])
        root = legacy.parent
        output = root/'processing'/scene/(scene+'-lease-1-proc-1')
        output.parent.mkdir(parents=True)
        shutil.copytree(legacy, output)
        sealed = root/'owner'/'attempts'/scene/(scene+'-lease-1')/'sealed'
        (sealed/'dynamic').mkdir(parents=True)
        shutil.copy(legacy/'dynamic'/'dynamic-execute-manifest.json', sealed/'dynamic'/'dynamic-execute-manifest.json')
        registration = root/'journal'/('task-'+scene)/'collected.json'
        proof = dict(kind='ACT_CONTAINER_TASK_READBACK', schema_version=1, status='PASS', result_schema_version=3,
            result_status='PASSED', teacher_execution_status='COMPLETED', teacher_task_result='PASS', act_data_status='PENDING_QC',
            act_data_reason=None, act_data_qc='NOT_RUN', export_eligible=False, qc_report_sha256=None, inputs_sha256=None,
            scope_sha256=None, audit_manifest_sha256=None, collection_mode=None, episode_seal_sha256=None,
            result_sha256='c'*64, task_result_sha256='e'*64, task_id='task-'+scene, scene_id=scene, worker_id='w00',
            location=str(sealed), processing='PENDING', receipt_sha256='r'*64, recording_files=4, recording_bytes=100)
        proof.update((proof_overrides or {}).get(scene, {}))
        processed = dict(kind='ACT_PROCESSED_RESULT_READBACK', schema_version=1, status='PASS', scene_id=scene, task_id=scene+'-proc-1',
            proc_attempt=1, output_dir=str(output), data_dir=str(output),
            processed_result=dict(path='processed-result.json', sha256='f'*64), phase1_result_sha256='c'*64, receipt_sha256='r'*64,
            diagnostic_fault='none', processor_rc=0, act_data_status='VALID', act_data_reason=None, act_data_qc='PASS',
            export_eligible=True, episode_seal_sha256=json.loads((legacy/'qc-report.json').read_bytes())['episode_seal_sha256'],
            qc_report_path='qc-report.json', qc_report_sha256='q'*64, inputs_sha256='a'*64, scope_sha256='s'*64,
            audit_manifest_sha256='m'*64, collection_mode='formal')
        processed.update((processed_overrides or {}).get(scene, {}))
        documents[str(registration)] = proof
        documents[str(output)] = processed
        entries.append(dict(kind='ACT_COMMITTED_EPISODE', schema_version=4, scene_id=scene, split=entry['split'],
            verifier_sha256='c'*64, task_result_sha256='e'*64, processed_result_sha256='f'*64,
            collection_evidence=dict(registration=str(registration), owner_root=str(root/'owner'), task_id='task-'+scene,
                result_location=str(sealed), scope_path=evidence['scope_path'], inputs_manifest=evidence['inputs_manifest'],
                processing_output=str(output))))
    calls = []

    def registration(path, *, scope, inputs_manifest, trust_independent_qc_memo=False):
        calls.append(('registration', str(path)))
        return copy.deepcopy(documents[str(path)])

    def processed(output, **kwargs):
        calls.append(('processed', str(output), kwargs))
        record = documents[str(output)]
        if isinstance(record, Exception):
            raise record
        return copy.deepcopy(record)
    monkeypatch.setattr(result_store, 'verify_container_task_registration', registration)
    monkeypatch.setattr(processed_result, 'verify_processed_result', processed)
    return entries, calls, documents


def test_a_processed_pass_resolves_from_the_frozen_index_and_exports_from_the_phase_2_directory(tmp_path, monkeypatch):
    entries, calls, _ = schema4_entries(tmp_path, monkeypatch)
    index = frozen_index(tmp_path/'collection-index.json', entries)
    resolved, = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)
    assert resolved['schema_version'] == 4 and resolved['processed_result_sha256'] == 'f'*64
    assert resolved['collection_evidence']['processing_output'].endswith('/processing/001/001-lease-1-proc-1')
    kind, _path, kwargs = calls[1]
    assert kind == 'processed' and kwargs['result_sha256'] == 'c'*64 and kwargs['receipt_sha256'] == 'r'*64
    assert kwargs['sealed'] == Path(entries[0]['collection_evidence']['result_location']) and kwargs['scene_id'] == '001'
    exported = export_dataset(attach_episode_content((resolved,), root=tmp_path), tmp_path/'dataset',
                              source_manifest_sha256='a'*64, campaign_index_sha256='b'*64)
    assert exported['scene_count'] == 1


@pytest.mark.parametrize('what,match', [
    (dict(processed={'export_eligible': False}), 'EXPORT_EPISODE_DATA_QC_NOT_PASSED'),
    (dict(processed={'act_data_qc': 'FAIL'}), 'EXPORT_EPISODE_DATA_QC_NOT_PASSED'),
    (dict(proof={'result_status': 'FAILED'}), 'EXPORT_EPISODE_NOT_PASSED'),
    (dict(processed={'collection_mode': 'preselected_target_diagnostic'}), 'EPISODE_COLLECTION_IDENTITY_INVALID'),
    (dict(processed={'diagnostic_fault': 'topic_drop'}), 'EPISODE_COLLECTION_IDENTITY_INVALID'),
    (dict(proof={'processing': 'NOT_PENDING'}), 'EPISODE_COLLECTION_IDENTITY_INVALID'),
    (dict(processed={'processed_result': dict(path='processed-result.json', sha256='0'*64)}), 'EPISODE_RECEIPT_CONFLICT'),
])
def test_schema_4_keeps_every_export_gate_and_cross_checks_both_phases(tmp_path, monkeypatch, what, match):
    entries, _, _ = schema4_entries(tmp_path, monkeypatch, processed_overrides={'001': what.get('processed', {})},
                                    proof_overrides={'001': what.get('proof', {})})
    index = frozen_index(tmp_path/'collection-index.json', entries)
    with pytest.raises(ValueError, match=match):
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)


def test_a_processed_readback_that_refuses_is_a_refused_episode(tmp_path, monkeypatch):
    entries, _, documents = schema4_entries(tmp_path, monkeypatch)
    documents[entries[0]['collection_evidence']['processing_output']] = ValueError('PROCESSED_RESULT_INVALID')
    index = frozen_index(tmp_path/'collection-index.json', entries)
    with pytest.raises(ValueError, match='EPISODE_COLLECTION_IDENTITY_INVALID'):
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)


@pytest.mark.parametrize('edit', ['foreign_output', 'extra_evidence', 'bad_hash', 'verifier_conflict'])
def test_schema_4_entries_are_closed(tmp_path, monkeypatch, edit):
    entries, _, _ = schema4_entries(tmp_path, monkeypatch)
    entry = entries[0]
    if edit == 'foreign_output':
        entry['collection_evidence']['processing_output'] = str(tmp_path/'elsewhere'/'001'/'x')
    elif edit == 'extra_evidence':
        entry['collection_evidence']['coordinator_root'] = '/x'
    elif edit == 'bad_hash':
        entry['processed_result_sha256'] = 'short'
    else:
        entry['verifier_sha256'] = 'b'*64
    index = frozen_index(tmp_path/'collection-index.json', [entry])
    with pytest.raises(ValueError, match='EPISODE_COLLECTION_EVIDENCE_REQUIRED|EPISODE_RECEIPT_INVALID|EPISODE_COLLECTION_IDENTITY_INVALID|EPISODE_RECEIPT_CONFLICT'):
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)


def test_a_qualification_index_never_exports_schema_4_either(tmp_path, monkeypatch):
    entries, calls, _ = schema4_entries(tmp_path, monkeypatch)
    index = frozen_index(tmp_path/'collection-index.json', entries, qualification=True)
    with pytest.raises(ValueError, match='EPISODE_FROZEN_INDEX_REQUIRED'):
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)
    assert calls == []


def test_a_schema_3_retry_index_exports_the_final_attempt_once(tmp_path, monkeypatch):
    entries, calls, documents = schema4_entries(tmp_path, monkeypatch)
    evidence = entries[0]['collection_evidence']
    first = evidence['processing_output']
    final = str(Path(first).with_name('001-lease-1-proc-2'))
    shutil.copytree(first, final)
    document = copy.deepcopy(documents[first])
    document.update(output_dir=final, data_dir=final, proc_attempt=2, task_id='001-proc-2')
    documents[final] = document
    evidence['processing_output'] = final
    index = frozen_index(tmp_path / 'collection-index.json', entries)
    stored = json.loads(index.read_text())
    stored.update(schema_version=3, collected_tasks=[dict(scene_id='001', recording_round=0, final=False),
                                                   dict(scene_id='001', recording_round=1, final=True)])
    index.write_text(json.dumps(stored))
    resolved, = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)
    assert resolved['collection_evidence']['processing_output'] == final
    assert [call[1] for call in calls if call[0] == 'processed'] == [final]
    exported = export_dataset(attach_episode_content((resolved,), root=tmp_path), tmp_path / 'dataset',
                              source_manifest_sha256='a' * 64, campaign_index_sha256='b' * 64)
    assert exported['scene_count'] == 1
