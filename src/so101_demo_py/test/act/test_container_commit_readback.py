"""Actual Coordinator/seal readback from an explicitly registered private shard root.

Only QC's external recomputation is controlled by the existing fixture. This
proves path/identity/commit handling, not live recording or actual QC quality.
"""

import hashlib
import json
from types import SimpleNamespace

import pytest

from test_act_result_qc import controlled_committed_result
from so101_demo.act.result_store import verify_coordinator_commit


def test_case_adapter_routes_actual_lease_to_original_case_binding(tmp_path,monkeypatch):
    from so101_demo.runtime.container_campaign.coordinator import ContainerCaseResultVerifier
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
    from so101_demo.parallel_batch.contracts.common import RunMode
    worker=tmp_path/'container-campaign/wave-0/w00/g1'
    run,location,scope,inputs,receipt=controlled_committed_result(tmp_path,monkeypatch,worker_root=worker)
    def ref(path):return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    adapter=ContainerCaseResultVerifier({'w00':worker},case_inputs={
        'point-1':dict(scope=ref(scope),inputs_manifest=ref(inputs))})
    adapter.bind_read_only_execution_journal(run/'coordinator','batch-1',1)
    current=None
    for event in CoordinatorJournal.read_only_replay(run/'coordinator','batch-1').events:
        if event.type=='RESULT_COMMITTED':break
        value=event.payload.get('delta',{}).get('workers',{}).get('w00')
        if value is not None and value.get('lease') is not None:
            current=LeaseIdentity(**value['lease'])
    assert current is not None
    verdict=adapter.verify(current,str(location),RunMode.EXECUTE)
    assert verdict['status']==receipt['status'] and verdict['sha256']==receipt['sha256']


def test_wave_verifier_reads_real_commit_under_registered_instance_and_retains_failed_data(tmp_path,monkeypatch):
    from so101_demo.runtime.container_campaign.registry import ContainerLaunch,ContainerLaunchRegistry
    from so101_demo.runtime.container_campaign.process_identity import (
        ContainerOwnerKey,ContainerChildBinding,read_process_owner,pid_namespace_inode,
    )
    from so101_demo.runtime.container_campaign.result_verifier import ContainerWaveResultVerifier
    import os
    root=tmp_path/'campaign';worker=root/'wave-0/w00/g1'
    run,location,scope,inputs,receipt=controlled_committed_result(tmp_path,monkeypatch,
        teacher_outcome='PASSED',worker_root=worker,run_root=root/'host/wave-0')
    registry=ContainerLaunchRegistry(root/'host/launches.sqlite3')
    launch=ContainerLaunch(launch_id='wave-0-w00-g1',role='shard',worker_id='w00',wave_id='wave-0',
        launch_generation=1,container_name='so101-test-w00-g1',image_digest='sha256:'+'a'*64,
        owned_root=str(worker),ros_namespace='/act/campaign/w00',ros_domain_id=181,session_id='session-1')
    owner=ContainerOwnerKey('b'*64,'2026-10-12T01:02:03.123Z','sha256:'+'a'*64,1)
    registry.register(launch);registry.bind_container(launch.launch_id,owner)
    registry.bind_child(launch.launch_id,ContainerChildBinding(owner,read_process_owner(os.getpid()),
        pid_namespace_inode(),str(worker/'control/normal.sock')))
    def ref(path):return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    verifier=ContainerWaveResultVerifier(root=root,registry=registry,
        case_inputs={'point-1':dict(scope=ref(scope),inputs_manifest=ref(inputs))})
    plan=dict(wave_index=0,scene_ids=['point-1'],assignment=None)
    outcome=dict(wave_index=0,coordinator_root=str(run/'coordinator'),infra_errors=[],
        case_results=[dict(scene_id='point-1',worker_id='w00',location=str(location))])
    try:
        value=verifier.verify_wave(plan,outcome,(SimpleNamespace(launch=launch,owner=owner),))
        proof=value['case_results'][0]['proof']
        assert value['scene_count']==1 and proof['teacher_task_result']=='PASS'
        assert proof['act_data_qc']=='FAIL' and proof['export_eligible'] is False
        for invalid in (outcome|{'case_results':[]},outcome|{'infra_errors':['shard-crash']},
                        outcome|{'case_results':outcome['case_results']*2}):
            with pytest.raises(ValueError,match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
                verifier.verify_wave(plan,invalid,(SimpleNamespace(launch=launch,owner=owner),))
    finally:
        registry.close()


def test_private_shard_commit_keeps_teacher_result_and_reads_original_journal(tmp_path,monkeypatch):
    worker = tmp_path/'container-campaign/wave-0/w00/g1'
    run,location,scope,inputs,receipt = controlled_committed_result(tmp_path,monkeypatch,
        teacher_outcome='PASSED',worker_root=worker)
    before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    proof = verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs,
                                     worker_roots={'w00':worker})
    assert proof['status'] == 'PASS' and proof['result_status'] == 'PASSED'
    assert proof['teacher_task_result'] == 'PASS' and proof['act_data_qc'] == 'FAIL'
    assert proof['export_eligible'] is False and proof['receipt'] == receipt
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p,sha in before.items())


@pytest.mark.parametrize('problem',['missing','foreign','relative','symlink','duplicate'])
def test_unregistered_or_foreign_root_cannot_relabel_a_valid_commit(tmp_path,monkeypatch,problem):
    worker = tmp_path/'container-campaign/wave-0/w00/g1'
    run,location,scope,inputs,receipt = controlled_committed_result(tmp_path,monkeypatch,worker_root=worker)
    roots = {'w00':worker}
    if problem == 'missing': roots = {'w01':worker}
    elif problem == 'foreign': roots = {'w00':tmp_path/'other/g1'}
    elif problem == 'relative': roots = {'w00':'wave-0/w00/g1'}
    elif problem == 'duplicate': roots['w01'] = worker
    else:
        link = tmp_path/'alias';link.symlink_to(worker,target_is_directory=True)
        roots = {'w00':link}
    with pytest.raises(ValueError,match='RESULT_COMMIT_READBACK_INVALID'):
        verify_coordinator_commit(run/'coordinator',location=location,scope=scope,inputs_manifest=inputs,
                                  worker_roots=roots)
