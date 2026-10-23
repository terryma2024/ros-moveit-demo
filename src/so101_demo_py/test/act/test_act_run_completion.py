"""Read-only completion gates use actual durable Coordinator records, with an explicit QC-reader double."""
import hashlib
import json

import pytest

from test_act_result_qc import controlled_committed_result,copied_commit_fixture


@pytest.mark.parametrize('fault',[None,'missing_cleanup','false_action','foreign_batch',
    'false_coordinator','numeric_success','extra_action','symlink_cleanup'])
def test_completion_reader_requires_original_cleanup_after_actual_commit(tmp_path,monkeypatch,fault):
    from so101_demo.act import result_store
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch,completed=True)
    proof=result_store.verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs)
    originals={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in run.rglob('*') if path.is_file()}
    copied=tmp_path/'copy';copied_commit_fixture(run,copied)
    copied_location=copied/location.relative_to(run)
    copied_proof=result_store.verify_coordinator_commit(copied/'coordinator',location=copied_location,scope=scope,inputs_manifest=inputs)
    path=copied/'cleanup-gates.json';document=json.loads(path.read_bytes())
    if fault=='missing_cleanup':path.rename(copied/'retained-original-cleanup.json')
    if fault=='false_action':document['actions']['confirm_goal_cancelled']['succeeded']=False
    if fault=='foreign_batch':document['batch_id']='foreign'
    if fault=='false_coordinator':document['coordinator_completion']['succeeded']=False
    if fault=='numeric_success':document['coordinator_completion']['attempted']=1
    if fault=='extra_action':document['actions']['unregistered_action']=document['process_cleanup']
    if fault=='symlink_cleanup':
        retained=copied/'retained-original-cleanup.json'
        path.rename(retained);path.symlink_to(retained)
    if fault not in (None,'missing_cleanup','symlink_cleanup'):path.write_text(json.dumps(document))
    reader=getattr(result_store,'verify_coordinator_cleanup',None)
    assert callable(reader),'actual cleanup journal/artifact readback is absent'
    if fault:
        with pytest.raises(ValueError,match='RESULT_CLEANUP_READBACK_INVALID'):
            reader(copied/'coordinator',commit_proof=copied_proof)
    else:
        actual=reader(copied/'coordinator',commit_proof=copied_proof)
        assert actual['status']=='PASS' and actual['cleanup_sequence']>copied_proof['commit_sequence']
        assert actual['cleanup_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in originals.items())


def test_cleanup_reader_does_not_acquire_authority_or_fsync(tmp_path,monkeypatch):
    from so101_demo.act import result_store
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    import os
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch,completed=True)
    proof=result_store.verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs)
    def forbidden(*args,**kwargs):pytest.fail('cleanup reader performed a writer operation')
    monkeypatch.setattr(os,'fsync',forbidden)
    monkeypatch.setattr(CoordinatorJournal,'acquire',forbidden)
    assert result_store.verify_coordinator_cleanup(run/'coordinator',commit_proof=proof)['status']=='PASS'


def test_cleanup_artifact_without_journaled_completion_is_not_success(tmp_path,monkeypatch):
    from so101_demo.act import result_store
    completed,_,_,_,_=controlled_committed_result(tmp_path/'completed',monkeypatch,completed=True)
    run,location,scope,inputs,_=controlled_committed_result(tmp_path/'uncompleted',monkeypatch)
    # Explicit controlled artifact has all true flags; the original actual Coordinator never completed cleanup.
    (run/'cleanup-gates.json').write_bytes((completed/'cleanup-gates.json').read_bytes())
    proof=result_store.verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs)
    with pytest.raises(ValueError,match='RESULT_CLEANUP_READBACK_INVALID'):
        result_store.verify_coordinator_cleanup(run/'coordinator',commit_proof=proof)
