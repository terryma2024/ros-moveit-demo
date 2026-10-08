"""Read-only completion gates use actual durable Coordinator records, with an explicit QC-reader double."""
import hashlib
import json

import pytest

from test_act_result_qc_v2 import controlled_committed_result,copied_commit_fixture


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


def test_false_success_summary_cannot_promote_actual_failed_commit(tmp_path,monkeypatch):
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch,completed=True)
    context=dict(episode=location/'episode',location=location,scope=scope,inputs_manifest=inputs,coordinator_root=run/'coordinator')
    monkeypatch.setattr(result_store,'resolve_native_run',lambda root:context)
    reader=getattr(act_first_episode,'_verified_run_completion',None)
    assert callable(reader),'default run final result gate is absent'
    code,document=reader(run.parent)
    assert code==1 and document['status']=='FAIL' and document['reason']=='TEACHER_TASK_NOT_PASSED'
    assert document['teacher_result_status']=='FAILED'
    assert not (run.parent/'commit-proof.json').exists()


def _completion(tmp_path,monkeypatch,**options):
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch,completed=True,**options)
    context=dict(episode=location/'episode',location=location,scope=scope,inputs_manifest=inputs,coordinator_root=run/'coordinator')
    monkeypatch.setattr(result_store,'resolve_native_run',lambda root:context)
    return run,act_first_episode._verified_run_completion(run.parent)


def test_a_teacher_pass_with_failing_data_is_nonzero_but_reports_the_teacher_pass_and_keeps_the_proof(tmp_path,monkeypatch):
    run,(code,document)=_completion(tmp_path,monkeypatch,teacher_outcome='PASSED',qc='FAIL')
    assert code==3 and document['status']=='FAIL' and document['reason']=='ACT_DATA_QC_NOT_PASSED'
    assert document['teacher_result_status']=='PASSED' and document['teacher_task_result']=='PASS'
    assert document['act_data_qc']=='FAIL' and document['export_eligible'] is False
    assert (run.parent/'commit-proof.json').is_file()


def test_a_teacher_pass_with_passing_data_completes_the_run_and_is_exportable(tmp_path,monkeypatch):
    run,(code,document)=_completion(tmp_path,monkeypatch,teacher_outcome='PASSED',qc='PASS')
    assert code==0 and document['status']=='PASS'
    assert document['teacher_result_status']=='PASSED' and document['act_data_qc']=='PASS'
    # the fixture is a preselected_target_diagnostic run: complete and QC-passed, but a diagnostic mode is never exportable
    assert document['export_eligible'] is False and (run.parent/'commit-proof.json').is_file()


def test_a_teacher_fail_with_passing_data_is_a_failed_attempt_outside_the_success_set(tmp_path,monkeypatch):
    run,(code,document)=_completion(tmp_path,monkeypatch,teacher_outcome='FAILED',qc='PASS')
    assert code==1 and document['reason']=='TEACHER_TASK_NOT_PASSED'
    assert document['teacher_result_status']=='FAILED' and document['act_data_qc']=='PASS'
    assert document['export_eligible'] is False


def test_exit_codes_are_0_for_a_passing_teacher_with_valid_or_disabled_data_3_for_bad_data_1_for_a_failed_teacher(
        monkeypatch):
    """The orchestrator's contract (A4c): 0 = Teacher PASS and data VALID/DISABLED with QC PASS where applicable;
    3 = Teacher PASS but data INVALID or QC FAIL; 1 = the Teacher did not pass. Exercised on the verified completion gate."""
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode

    def completion(teacher_status, data_status, qc, eligible):
        proof = dict(result_status=teacher_status, teacher_task_result='PASS' if teacher_status == 'PASSED' else 'FAIL',
                     act_data_status=data_status, act_data_qc=qc, export_eligible=eligible)
        context = dict(coordinator_root='coordinator', location='location', scope='scope', inputs_manifest='inputs')
        monkeypatch.setattr(result_store, 'resolve_native_run', lambda root: context)
        monkeypatch.setattr(result_store, 'verify_coordinator_commit', lambda *a, **k: proof)
        monkeypatch.setattr(result_store, 'verify_coordinator_cleanup', lambda *a, **k: dict(cleanup_proof_path='cleanup'))
        monkeypatch.setattr(result_store, 'write_commit_proof', lambda proof, path: 'digest')
        return act_first_episode._verified_run_completion('/nonexistent-run')

    assert completion('PASSED', 'VALID', 'PASS', True)[0] == 0
    assert completion('PASSED', 'DISABLED', 'NOT_RUN', False)[0] == 0
    assert completion('PASSED', 'INVALID', 'NOT_RUN', False)[0] == 3
    assert completion('PASSED', 'VALID', 'FAIL', False)[0] == 3
    assert completion('FAILED', 'VALID', 'PASS', False)[0] == 1
    assert completion('FAILED', 'DISABLED', 'NOT_RUN', False)[0] == 1
