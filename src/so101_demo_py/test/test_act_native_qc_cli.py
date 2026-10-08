"""QC command composition with an explicit reader double; never a live PASS."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from test_act_qc_report_publication import fail_teacher_reference, report


@pytest.mark.parametrize('passed', [True, False])
def test_qc_command_uses_readonly_recomputation_and_durable_common_report(tmp_path, monkeypatch, passed):
    from so101_demo.act import episode_qc
    from so101_demo.cli import act_first_episode
    document=report()
    if not passed:
        fail_teacher_reference(document,'TEACHER_REFERENCE_END_AFTER_RECORDING')
    calls=[]
    def reader(root, *, scope, inputs_manifest):
        calls.append((root,scope,inputs_manifest))
        return copy.deepcopy(document)
    monkeypatch.setattr(episode_qc,'recompute_native_qc',reader,raising=False)
    monkeypatch.setattr(act_first_episode,'_run',lambda args:pytest.fail('QC started an execution stack'))
    target=tmp_path/'qc-report.json'
    code=act_first_episode.main(['qc','--episode',str(tmp_path/'episode'),'--scope',str(tmp_path/'common-scope.json'),
        '--inputs',str(tmp_path/'frozen'),'--output',str(target)])
    assert code==(0 if passed else 1)
    assert calls==[(tmp_path/'episode',tmp_path/'common-scope.json',tmp_path/'frozen/inputs-manifest.json')]
    assert episode_qc.read_qc_report(target)==document
    assert len(list(tmp_path.glob('.qc-report.json.*.pending')))==1


def test_real_qc_reader_refuses_absent_originals_without_creating_runtime(tmp_path):
    from so101_demo.act import episode_qc
    reader=getattr(episode_qc,'recompute_native_qc',None)
    assert callable(reader), 'fresh-process current native QC recomputation is absent'
    with pytest.raises((OSError,ValueError)):
        reader(tmp_path/'absent',scope=tmp_path/'common-scope.json',inputs_manifest=tmp_path/'inputs-manifest.json')
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('passed',[True,False])
def test_qc_run_uses_original_run_context_and_approved_exit_codes(tmp_path,monkeypatch,passed):
    from so101_demo.act import episode_qc,result_store
    from so101_demo.cli import act_first_episode
    document=report()
    if not passed:
        fail_teacher_reference(document,'TEACHER_REFERENCE_PHYSICS_STEP_ABSENT')
    context=dict(episode=tmp_path/'episode',scope=tmp_path/'scope.json',inputs_manifest=tmp_path/'frozen/inputs-manifest.json')
    def resolve(root):
        assert root==tmp_path/'live'
        return context
    def recompute(root,*,scope,inputs_manifest):
        assert (root,scope,inputs_manifest)==(context['episode'],context['scope'],context['inputs_manifest'])
        return copy.deepcopy(document)
    monkeypatch.setattr(result_store,'resolve_native_run',resolve,raising=False)
    monkeypatch.setattr(episode_qc,'recompute_native_qc',recompute)
    output=tmp_path/'qc.json'
    assert act_first_episode.main(['qc','--run',str(tmp_path/'live'),'--output',str(output)])==(0 if passed else 3)
    assert episode_qc.read_qc_report(output)==document


def test_qc_run_missing_originals_is_infrastructure_rc4(tmp_path):
    from so101_demo.cli import act_first_episode
    output=tmp_path/'qc.json'
    assert act_first_episode.main(['qc','--run',str(tmp_path/'missing'),'--output',str(output)])==4
    assert not output.exists()


@pytest.mark.parametrize('fault',[None,'missing_commit','publish_fsync'])
def test_verify_commit_command_reads_actual_journal_and_publishes_new_durable_proof(tmp_path,monkeypatch,fault):
    import os
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode
    from test_act_result_qc_v2 import controlled_committed_result,copied_commit_fixture
    run,location,scope,inputs,receipt=controlled_committed_result(tmp_path,monkeypatch)
    if fault=='missing_commit':
        copied=tmp_path/'uncommitted'
        copied_commit_fixture(run,copied,fault='missing_commit')
        location=copied/location.relative_to(run);run=copied
    context=dict(episode=location/'episode',location=location,scope=scope,inputs_manifest=inputs,coordinator_root=run/'coordinator')
    monkeypatch.setattr(result_store,'resolve_native_run',lambda root:context)
    if fault=='publish_fsync':
        def refuse(_fd):raise OSError('controlled fsync failure')
        monkeypatch.setattr(os,'fsync',refuse)
    output=tmp_path/'commit-proof.json'
    code=act_first_episode.main(['verify-commit','--run',str(run.parent),'--output',str(output)])
    assert code==(0 if fault is None else 3)
    if fault is None:
        proof=json.loads(output.read_bytes())
        assert proof['status']=='PASS' and proof['receipt']==receipt
        original=output.read_bytes()
        assert act_first_episode.main(['verify-commit','--run',str(run.parent),'--output',str(output)])==3
        assert output.read_bytes()==original
    else:
        assert not output.exists()


@pytest.mark.parametrize('fault',[None,'missing_commit','publish_fsync'])
def test_check_export_uses_both_common_boundaries_and_preserves_actual_originals(tmp_path,monkeypatch,fault):
    import os
    from so101_demo.act import result_store
    from so101_demo.cli import act_first_episode
    from test_act_result_qc_v2 import controlled_committed_result,copied_commit_fixture
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch)
    originals={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in run.rglob('*') if path.is_file()}
    if fault=='missing_commit':
        copied=tmp_path/'uncommitted';copied_commit_fixture(run,copied,fault='missing_commit')
        location=copied/location.relative_to(run);run=copied
    context=dict(episode=location/'episode',location=location,scope=scope,inputs_manifest=inputs,coordinator_root=run/'coordinator')
    monkeypatch.setattr(result_store,'resolve_native_run',lambda root:context)
    if fault=='publish_fsync':
        def refuse(_fd):raise OSError('controlled fsync failure')
        monkeypatch.setattr(os,'fsync',refuse)
    output=tmp_path/'export-rejection.json'
    assert act_first_episode.main(['check-export','--run',str(run.parent),'--output',str(output)])==(0 if fault is None else 3)
    if fault is None:
        proof=json.loads(output.read_bytes())
        assert proof['status']=='PASS' and proof['kind']=='ACT_DIAGNOSTIC_EXPORT_REJECTION'
        assert proof['dataset_produced'] is False and proof['perception_or_policy_models_loaded'] is False
        assert proof['checks']==dict(resolver='DIAGNOSTIC_EPISODE_NOT_TRAINABLE',direct_export='DIAGNOSTIC_EPISODE_NOT_TRAINABLE')
        original=output.read_bytes()
        assert act_first_episode.main(['check-export','--run',str(run.parent),'--output',str(output)])==3
        assert output.read_bytes()==original
    else:assert not output.exists()
    assert not (tmp_path/'export-rejection.json.dataset').exists()
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in originals.items())


