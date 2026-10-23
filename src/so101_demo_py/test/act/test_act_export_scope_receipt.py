"""Common resolver/direct exporter must trace original scope and actual durable commits."""
import copy
import hashlib
import json

from act_export_fixture import ROW_CONTENT

import pytest


def committed_diagnostic(tmp_path,monkeypatch):
    from test_act_result_qc import controlled_committed_result
    from so101_demo.act.result_store import verify_coordinator_commit
    run,location,scope,inputs,receipt=controlled_committed_result(tmp_path,monkeypatch)
    proof=verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs)
    entry=dict(kind='ACT_COMMITTED_EPISODE',schema_version=2,scene_id='default',split='train',status='PASSED',
        journal_sha256=proof['commit_frame_sha256'],verifier_sha256=proof['result_sha256'],
        collection_evidence=dict(coordinator_root=str(run/'coordinator'),result_location=str(location),
            scope_path=str(scope),inputs_manifest=str(inputs),receipt=receipt),
        content=copy.deepcopy(ROW_CONTENT))
    index=tmp_path/'campaign-index.json'
    index.write_text(json.dumps(dict(schema_version=2,committed_episodes=[entry])))
    return entry,index


@pytest.mark.parametrize('direct',[False,True])
def test_actual_diagnostic_commit_cannot_enter_either_common_export_boundary(tmp_path,monkeypatch,direct):
    from so101_demo.act.bundle import resolve_committed_episodes,export_dataset
    entry,index=committed_diagnostic(tmp_path,monkeypatch)
    original={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in (tmp_path/'run').rglob('*') if path.is_file()}
    output=tmp_path/'dataset'
    with pytest.raises(ValueError,match='DIAGNOSTIC_EPISODE_NOT_TRAINABLE'):
        if direct:
            export_dataset((entry,),output,source_manifest_sha256='a'*64,campaign_index_sha256='b'*64)
        else:
            resolve_committed_episodes(manifest=dict(episodes=[dict(scene_id='default',status='PASSED',split='train')]),campaign_index=index)
    assert not output.exists()
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in original.items())


@pytest.mark.parametrize('direct',[False,True])
def test_legacy_matching_hash_claims_without_mode_and_current_receipt_are_refused(tmp_path,direct):
    from so101_demo.act.bundle import resolve_committed_episodes,export_dataset
    entry=dict(scene_id='default',status='PASSED',split='train',journal_sha256='a'*64,verifier_sha256='a'*64,
        content=copy.deepcopy(ROW_CONTENT))
    index=tmp_path/'campaign-index.json';index.write_text(json.dumps(dict(committed_episodes=[entry])))
    with pytest.raises(ValueError,match='EPISODE_COLLECTION_EVIDENCE_REQUIRED'):
        if direct:export_dataset((entry,),tmp_path/'dataset',source_manifest_sha256='a'*64,campaign_index_sha256='b'*64)
        else:resolve_committed_episodes(manifest=dict(episodes=[entry]),campaign_index=index)
    assert not (tmp_path/'dataset').exists()


def test_duplicate_scene_receipts_are_ambiguous_even_when_hashes_match(tmp_path,monkeypatch):
    from act_export_fixture import complete_export_entries
    from so101_demo.act.bundle import resolve_committed_episodes
    entry=complete_export_entries(tmp_path,monkeypatch,('default',))[0]
    index=tmp_path/'campaign-index.json';index.write_text(json.dumps(dict(schema_version=2,committed_episodes=[entry,entry])))
    with pytest.raises(ValueError,match='EPISODE_RECEIPT_CONFLICT'):
        resolve_committed_episodes(manifest=dict(episodes=[dict(scene_id='default',status='PASSED')]),campaign_index=index)


@pytest.mark.parametrize('fault',['claimed_formal','claimed_eligible','receipt'])
def test_caller_flags_or_receipt_cannot_promote_actual_diagnostic_commit(tmp_path,monkeypatch,fault):
    from so101_demo.act.bundle import export_dataset
    entry,_=committed_diagnostic(tmp_path,monkeypatch)
    if fault=='claimed_formal':entry['collection_mode']='formal'
    if fault=='claimed_eligible':entry['eligible_for_training']=True
    if fault=='receipt':entry['collection_evidence']['receipt']['inputs_sha256']='b'*64
    expected={'claimed_formal':'EPISODE_COLLECTION_IDENTITY_INVALID','claimed_eligible':'DIAGNOSTIC_EPISODE_NOT_TRAINABLE',
        'receipt':'EPISODE_RECEIPT_CONFLICT'}[fault]
    with pytest.raises(ValueError,match=expected):
        export_dataset((entry,),tmp_path/'dataset',source_manifest_sha256='a'*64,campaign_index_sha256='b'*64)
    assert not (tmp_path/'dataset').exists()


@pytest.mark.parametrize('direct',[False,True])
def test_original_coordinator_index_rejects_diagnostic_without_inventing_campaign_receipt(tmp_path,monkeypatch,direct):
    from so101_demo.act.bundle import resolve_committed_episodes,export_dataset
    entry,_=committed_diagnostic(tmp_path,monkeypatch)
    entry['status']='FAILED'  # The controlled actual commit is a failure, and remains diagnostic.
    entry.pop('content')
    original_index=tmp_path/'run/coordinator/aggregate_results.json'
    before=original_index.read_bytes()
    with pytest.raises(ValueError,match='DIAGNOSTIC_EPISODE_NOT_TRAINABLE'):
        if direct:export_dataset((entry,),tmp_path/'dataset',source_manifest_sha256='a'*64,campaign_index_sha256='b'*64)
        else:resolve_committed_episodes(manifest=dict(episodes=[entry]),campaign_index=original_index)
    assert original_index.read_bytes()==before and not (tmp_path/'dataset').exists()
