"""Actual result publication/report readback with an explicit QC-reader double, never live QC."""

import copy
from dataclasses import asdict
import hashlib
import json
import os
import shutil
import struct
from pathlib import Path

import pytest

from test_act_qc_report_publication import fail_teacher_reference, report
from test_act_seal_and_downgrade import lease, sealed_episode
from paths import PACKAGE_ROOT


def controlled_committed_result(tmp_path,monkeypatch,*,completed=False,teacher_outcome='FAILED',commit=True,qc='FAIL',
                                worker_root=None,run_root=None):
    """Actual Coordinator/durable result with an explicit failed-QC reader double.

    The attempt status is the Teacher's (`teacher_outcome`); the QC double grades the data `qc` (FAIL by default; PASS
    with a controlled QC readback double). With
    `commit=False` the sealed result is returned with a callable that performs the commit, so a test can alter the
    sealed record first.
    """
    from act_result_teacher import sealed_teacher
    from so101_demo.act import episode_qc
    from so101_demo.act.collection_scope import write_collection_scope
    from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
    from so101_demo.act.recorder import EpisodeRecorder
    from so101_demo.act.result_store import ActCollectionResultStore,ActCollectionResultVerifier
    from so101_demo.parallel_batch.contracts.common import RunMode
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        BatchKind,
        BatchRequest,
        load_parallel_runtime_config_linux_cuda,
    )
    from so101_demo.parallel_batch.coordinator import BatchCoordinator
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    from test_act_seal_and_downgrade import SCOPE,IDENTITY,PROVENANCE
    run=tmp_path/'run' if run_root is None else Path(run_root)
    worker=run/'workers/w00' if worker_root is None else Path(worker_root)
    journal=CoordinatorJournal.create(run/'coordinator','batch-1')
    scope=tmp_path/'scope.json';write_collection_scope(SCOPE,scope)
    inputs=tmp_path/'inputs-manifest.json';inputs.write_text(json.dumps(dict(inputs_sha256='a'*64,mode=SCOPE['mode'])))
    verifier=ActCollectionResultVerifier({'w00':worker},scope=scope,inputs_manifest=inputs)
    verifier.bind_execution_journal(journal)
    config=load_parallel_runtime_config_linux_cuda(PACKAGE_ROOT/'config/mujoco/parallel_batch_linux_cuda.yaml')
    coordinator=BatchCoordinator(journal,BatchRequest('batch-1',RunMode.EXECUTE,('point-1',),1,run,
        BatchKind.FIRST_PASS),config=config,clock=lambda:10.,result_port=verifier)
    coordinator.register_worker('w00',generation=1)
    current=coordinator.grant_lease('w00',generation=1)
    coordinator.ack_lease(current,request_key='ack')
    identity={key:value for key,value in asdict(current).items() if not key.startswith('lease_issued') and not key.startswith('lease_deadline')}
    gate=dict(schema_version=1,kind='POINT_INITIAL_GATE',**identity,reset_epoch='reset-2',
        simulation_session_id='session-1',reset_completed_monotonic_s=10.1,source_frame_monotonic_s=10.2,
        canonical_joints=True,no_controller_goal=True,no_attachment=True,no_contact=True,no_stale_node=True)
    current=coordinator.ack_attempt_started(current,request_key='start',gate_summary=gate).lease
    store=ActCollectionResultStore(worker/'attempts'/current.point_id/current.attempt_id,current,
        clock=lambda:10.5,scope=scope,inputs_manifest=inputs)
    recorder=EpisodeRecorder(store.episode_root,session_id='session-1',attempt_id=current.attempt_id,
        reset_epoch=2,provenance=PROVENANCE)
    writer=EpisodeAuditWriter(store.episode_root,SCOPE,{**IDENTITY,'attempt_id':current.attempt_id,'lease':asdict(current)},dict(inputs_sha256='a'*64))
    audit=writer.seal(dict(start_s=1.,end_s=1.,label_cutoff_s=1.))
    store.audit_manifest=audit
    passing=qc=='PASS'
    seal=recorder.finish(dict(status='FAILED',reason='controlled stop',pick_place_validation_success=False,stopped_confirmed=True),
        audit_manifest=audit,scope=scope)
    expected=report();expected['identity']=writer.identity
    expected.update(inputs_sha256='a'*64,
        scope_sha256=hashlib.sha256(scope.read_bytes()).hexdigest(),audit_manifest_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),
        episode_seal_sha256=hashlib.sha256(seal.read_bytes()).hexdigest())
    if not passing:
        expected['counts']={key:0 for key in expected['counts']}
        fail_teacher_reference(expected,'TEACHER_REFERENCE_END_AFTER_RECORDING')
    else:
        # controlled QC reader double: this episode is not a gradable PASSED recording, so the independent verdict
        # (the report the store published from the double above) is read back as PASS
        from so101_demo.act import result_store
        def verified(report_path,**kwargs):
            return (episode_qc.read_qc_report(report_path),
                hashlib.sha256(Path(report_path).read_bytes()).hexdigest(),SCOPE['mode'])
        monkeypatch.setattr(result_store,'_verify_result_qc',verified)
    monkeypatch.setattr(episode_qc,'recompute_native_qc',lambda *args,**kwargs:copy.deepcopy(expected))
    location=store.seal(seal,teacher=sealed_teacher(store,teacher_outcome))
    def commit_result():
        try:
            final=coordinator.begin_finalizing(current,request_key='finalize').lease
            receipt=coordinator.commit_result(final,str(location),request_key='result')
            if completed:
                coordinator.complete_cleanup(owned_processes_stopped=True,controllers_stopped=True)
                success=dict(succeeded=True,error_type=None,error_message=None)
                (run/'cleanup-gates.json').write_text(json.dumps(dict(schema_version=1,batch_id='batch-1',
                    actions={key:success for key in ('stop_leases','cancel_goal','confirm_goal_cancelled','request_recovery')},
                    process_cleanup=success,container_cleanup=success,cleanup_gates_passed=True,
                    coordinator_completion=dict(attempted=True,succeeded=True,error_type=None,error_message=None),
                    batch_cleanup_complete=True)))
            return receipt
        finally:
            journal.close()
    if not commit:
        return run,location,scope,inputs,commit_result
    return run,location,scope,inputs,commit_result()


def test_actual_durable_coordinator_receipt_binds_qc_and_original_inputs(tmp_path,monkeypatch):
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    run,location,scope,inputs,receipt=controlled_committed_result(tmp_path,monkeypatch)
    result=json.loads((location/'result.json').read_bytes())
    for key in ('qc_report_sha256','inputs_sha256','scope_sha256','audit_manifest_sha256','collection_mode'):
        assert receipt[key]==result[key]
    committed=[event for event in CoordinatorJournal.read_only_replay(run/'coordinator','batch-1').events if event.type=='RESULT_COMMITTED']
    assert len(committed)==1 and committed[0].payload['response']==receipt


def test_readonly_commit_proof_replays_actual_journal_projection_and_report(tmp_path,monkeypatch):
    from so101_demo.act import result_store
    run,location,scope,inputs,receipt=controlled_committed_result(tmp_path,monkeypatch)
    before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in run.rglob('*') if path.is_file()}
    reader=getattr(result_store,'verify_coordinator_commit',None)
    assert callable(reader),'actual durable Coordinator commit readback is absent'
    proof=reader(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs)
    assert proof['status']=='PASS' and proof['result_status']=='FAILED' and proof['receipt']==receipt
    assert proof['qc_report_sha256']==receipt['qc_report_sha256']
    assert proof['commit_sequence']>1 and len(proof['commit_frame_sha256'])==64
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in before.items())


def test_fresh_commit_reader_never_fsyncs_or_acquires_writer_authority(tmp_path,monkeypatch):
    from so101_demo.act.result_store import verify_coordinator_commit
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch)
    def forbidden(*args,**kwargs):pytest.fail('readback performed a writer operation')
    monkeypatch.setattr(os,'fsync',forbidden)
    monkeypatch.setattr(CoordinatorJournal,'acquire',forbidden)
    assert verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs)['status']=='PASS'


def copied_commit_fixture(run,destination,*,fault=None):
    """Relocate only controlled copies and re-sign their journal framing for semantic negatives."""
    from test_parallel_batch_journal import frames
    shutil.copytree(run,destination)
    old,new=str(run),str(destination)
    def relocated(value):
        return json.loads(json.dumps(value).replace(old,new))
    previous='0'*64;sequence=0
    for path in sorted((destination/'coordinator/events').glob('segment-*.journal')):
        output=[]
        for _,value in frames(path):
            value=relocated(value)
            if value.get('type')=='RESULT_COMMITTED' and fault=='missing_commit':continue
            if value.get('type')=='RESULT_COMMITTED' and fault=='receipt':
                value['payload']['response']['qc_report_sha256']='f'*64
            if 'prev_frame_sha256' in value:
                sequence+=1
                value['prev_frame_sha256']=previous
                value['sequence']=sequence
            else:value['prev_segment_sha256']=previous
            payload=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            encoded=struct.pack('>Q',len(payload))+hashlib.sha256(payload).hexdigest().encode()+payload+b'\n'
            output.append(encoded);previous=hashlib.sha256(encoded).hexdigest()
        path.write_bytes(b''.join(output))
    index=destination/'coordinator/aggregate_results.json'
    document=relocated(json.loads(index.read_bytes()))
    if fault=='index':document['points']['point-1']['status']='PASSED'
    index.write_text(json.dumps(document,sort_keys=True,separators=(',',':')))


@pytest.mark.parametrize('fault',['missing_commit','receipt','index','report'])
def test_commit_reader_rejects_semantic_copy_faults_after_copy_positive(tmp_path,monkeypatch,fault):
    from so101_demo.act.result_store import verify_coordinator_commit
    run,location,scope,inputs,_=controlled_committed_result(tmp_path,monkeypatch)
    originals={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in run.rglob('*') if path.is_file()}
    positive=tmp_path/'positive';copied_commit_fixture(run,positive)
    relative=location.relative_to(run)
    assert verify_coordinator_commit(positive/'coordinator',location=positive/relative,scope=scope,inputs_manifest=inputs)['status']=='PASS'
    negative=tmp_path/'negative';copied_commit_fixture(run,negative,fault=fault)
    if fault=='report':
        path=negative/relative/'qc-report.json'
        path.rename(negative/relative/'retained-original-report.json')
    with pytest.raises(ValueError,match='RESULT_COMMIT_READBACK_INVALID') as error:
        verify_coordinator_commit(negative/'coordinator',location=negative/relative,scope=scope,inputs_manifest=inputs)
    cause=error.value.__cause__
    assert str(cause)=={'missing_commit':'COMMIT_MISSING_OR_CONFLICTING','receipt':'COMMIT_RECEIPT_MISMATCH',
        'index':'COMMIT_INDEX_MISMATCH','report':'RESULT_QC_READBACK_INVALID'}[fault]
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in originals.items())


def setup_result(tmp_path, monkeypatch, seal_outcome='PASSED'):
    from so101_demo.act import episode_qc
    from so101_demo.act.result_store import ActCollectionResultStore
    current = lease()
    inputs = tmp_path/'inputs-manifest.json'
    inputs.write_text(json.dumps(dict(inputs_sha256='a'*64, mode='preselected_target_diagnostic')))
    store = ActCollectionResultStore(tmp_path/'w00/attempts/point-1/attempt-1', current,
        clock=lambda:15., inputs_manifest=inputs)
    audit, seal = sealed_episode(tmp_path, episode_root=store.episode_root, audit_lease=current,
        outcome=dict(status=seal_outcome, reason='controlled completion', pick_place_validation_success=seal_outcome == 'PASSED',
                     stopped_confirmed=True))
    store.audit_manifest, store.scope = audit, audit.parent/'source.json'
    document = report()
    document['identity'] = json.loads(audit.read_bytes())['identity']
    document['identity']['lease'] = asdict(current)
    document.update(episode_seal_sha256=hashlib.sha256(seal.read_bytes()).hexdigest(),
        audit_manifest_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(), inputs_sha256='a'*64,
        scope_sha256=hashlib.sha256(store.scope.read_bytes()).hexdigest())
    document['counts']['records'] = json.loads(seal.read_bytes())['record_count']
    def recompute(root, *, scope, inputs_manifest):
        assert inputs_manifest == inputs
        assert json.loads((root/'seal.json').read_bytes())['record_count']==document['counts']['records']
        assert hashlib.sha256(scope.read_bytes()).hexdigest()==document['scope_sha256']
        return copy.deepcopy(document)
    monkeypatch.setattr(episode_qc,'recompute_native_qc',recompute)
    return store, seal, document, inputs


def test_default_result_publishes_owned_durable_qc_and_verifies_same_originals(tmp_path, monkeypatch):
    from so101_demo.act import episode_qc
    from so101_demo.act.result_store import ActCollectionResultVerifier
    from so101_demo.parallel_batch.contracts.common import RunMode
    from act_result_teacher import sealed_teacher
    store, seal, expected, inputs = setup_result(tmp_path, monkeypatch)
    before = seal.read_bytes()
    location = store.seal(seal, teacher=sealed_teacher(store, 'PASSED'))
    result = json.loads((location/'result.json').read_bytes())
    assert result['schema_version']==3 and result['qc_report_path']=='qc-report.json'
    assert result['qc_report_sha256']==hashlib.sha256((location/'qc-report.json').read_bytes()).hexdigest()
    assert result['inputs_sha256']=='a'*64 and result['collection_mode']=='preselected_target_diagnostic'
    assert episode_qc.read_qc_report(location/'qc-report.json')==expected
    assert (location/'episode/seal.json').read_bytes()==before
    assert json.loads(before)['committed'] is False
    verifier=ActCollectionResultVerifier({'w00':tmp_path/'w00'},scope=location/'episode/audit/source.json',
        inputs_manifest=inputs)
    verdict=verifier.verify(lease(),str(location),RunMode.EXECUTE)
    assert verdict['status']=='PASSED' and verdict['qc_report_sha256']==result['qc_report_sha256']
    # diagnostic mode (the fixture's scope): QC passes but the result is never export eligible
    assert verdict['act_data_qc']=='PASS' and verdict['export_eligible'] is False


def test_recomputed_reference_fail_does_not_downgrade_a_teacher_pass(tmp_path, monkeypatch):
    from act_result_teacher import sealed_teacher
    from so101_demo.act.result_store import ActCollectionResultVerifier
    from so101_demo.parallel_batch.contracts.common import RunMode
    store, seal, expected, inputs = setup_result(tmp_path, monkeypatch)
    fail_teacher_reference(expected, 'TEACHER_REFERENCE_PHYSICS_STEP_ABSENT')
    location = store.seal(seal, teacher=sealed_teacher(store, 'PASSED'))
    result = json.loads((location/'result.json').read_bytes())
    assert json.loads((location/'episode/seal.json').read_bytes())['status']=='PASSED'
    # The data QC failed; the attempt status is still the Teacher's PASSED, and the episode is not exportable.
    assert result['schema_version']==3 and result['status']=='PASSED' and result['act_data_qc']=='FAIL'
    assert result['export_eligible'] is False and 'qc_passed' not in result
    verifier = ActCollectionResultVerifier({'w00':tmp_path/'w00'},
        scope=location/'episode/audit/source.json', inputs_manifest=inputs)
    verdict = verifier.verify(lease(),str(location),RunMode.EXECUTE)
    assert verdict['status']=='PASSED' and verdict['act_data_qc']=='FAIL'


def test_a_teacher_fail_with_valid_data_gets_data_qc_pass_and_still_cannot_export(tmp_path, monkeypatch):
    """QC no longer judges task success: a FAILED episode seal with consistent, valid data is data QC PASS."""
    from act_result_teacher import sealed_teacher
    from so101_demo.act.result_store import ActCollectionResultVerifier
    from so101_demo.parallel_batch.contracts.common import RunMode
    store, seal, expected, inputs = setup_result(tmp_path, monkeypatch, seal_outcome='FAILED')
    assert json.loads(seal.read_bytes())['status']=='FAILED'
    location = store.seal(seal, teacher=sealed_teacher(store, 'FAILED'))
    result = json.loads((location/'result.json').read_bytes())
    assert result['status']=='FAILED' and result['act_data_qc']=='PASS' and result['act_data_status']=='PENDING_QC'
    assert result['export_eligible'] is False
    verifier = ActCollectionResultVerifier({'w00':tmp_path/'w00'},
        scope=location/'episode/audit/source.json', inputs_manifest=inputs)
    verdict = verifier.verify(lease(),str(location),RunMode.EXECUTE)
    assert verdict['status']=='FAILED' and verdict['act_data_qc']=='PASS' and verdict['export_eligible'] is False
    assert 'endpoint' not in verdict and 'endpoint' not in result


@pytest.mark.parametrize('fault',['foreign_identity','changed_count','changed_reference','failed_report','wrong_location'])
def test_result_refuses_wrong_supplied_report_without_publishing_success(tmp_path,monkeypatch,fault):
    from so101_demo.act.episode_qc import write_qc_report
    store,seal,original,_=setup_result(tmp_path,monkeypatch)
    changed=copy.deepcopy(original)
    if fault=='foreign_identity':changed['identity']['reset_epoch']+=1
    if fault=='changed_count':changed['counts']['records']+=1
    if fault=='changed_reference':changed['checks']['teacher_reference_consistency']['details']['start_reference']['simulation_step']+=1
    if fault=='failed_report':
        fail_teacher_reference(changed,'TEACHER_REFERENCE_END_MISSING')
    path=tmp_path/'unowned-report.json' if fault=='wrong_location' else store.working/'qc-report.json'
    write_qc_report(changed,path)
    from act_result_teacher import sealed_teacher
    with pytest.raises((ValueError,RuntimeError),match='RESULT_QC_'):
        store.seal(seal,teacher=sealed_teacher(store,'PASSED'),qc_report_path=path)
    assert not (store.workspace/'sealed').exists() and not (store.working/'result.json').exists()
    assert path.is_file() and seal.is_file()


@pytest.mark.parametrize('fault',['missing_report','resigned_report','missing_v2','manifest_hash','mode'])
def test_independent_result_reader_rejects_report_and_manifest_tamper_after_positive(tmp_path,monkeypatch,fault):
    from so101_demo.act import episode_qc
    from so101_demo.act.result_store import ActCollectionResultVerifier
    from so101_demo.parallel_batch.contracts.common import RunMode
    from act_result_teacher import sealed_teacher
    store,seal,_,inputs=setup_result(tmp_path,monkeypatch)
    location=store.seal(seal,teacher=sealed_teacher(store,'PASSED'))
    scope=location/'episode/audit/source.json'
    verifier=ActCollectionResultVerifier({'w00':tmp_path/'w00'},scope=scope,inputs_manifest=inputs)
    assert verifier.verify(lease(),str(location),RunMode.EXECUTE)['status']=='PASSED'
    originals={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in location.rglob('*') if path.is_file()}
    copied_worker=tmp_path/'isolated/w00'
    shutil.copytree(tmp_path/'w00',copied_worker)
    location=copied_worker/'attempts/point-1/attempt-1/sealed'
    verifier=ActCollectionResultVerifier({'w00':copied_worker},scope=location/'episode/audit/source.json',inputs_manifest=inputs)
    result_path=location/'result.json';result=json.loads(result_path.read_bytes())
    qc_path=location/'qc-report.json'
    if fault=='missing_report':
        # Keep the original bytes, but remove the expected pathname from the isolated fixture.
        qc_path.rename(location/'retained-original-qc.json')
    if fault=='resigned_report':
        qc=json.loads(qc_path.read_bytes());qc['counts']['records']+=1
        qc_path.write_bytes(episode_qc._report_canonical(qc))
        result['qc_report_sha256']=hashlib.sha256(qc_path.read_bytes()).hexdigest()
    if fault=='missing_v2':
        # a schema 1 record presented to a verifier that holds the frozen QC inputs is refused
        result={key:value for key,value in result.items() if key in {
            'kind','schema_version','lease_identity','status','qc_passed','episode_seal_sha256','completed_monotonic_s'}}
        result['schema_version']=1
    if fault=='manifest_hash':result['audit_manifest_sha256']='b'*64
    if fault=='mode':result['collection_mode']='formal'
    result_path.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
    with pytest.raises((ValueError,OSError),match='RESULT_QC_|RESULT_SCHEMA_INVALID|RESULT_DATA_INCONSISTENT'):
        verifier.verify(lease(),str(location),RunMode.EXECUTE)
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in originals.items())
