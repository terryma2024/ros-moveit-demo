"""Case cleanup keeps the borrowed native stack/session and preserves stop fences."""

import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from test_shard_retirement import fixture as stack_fixture
from parallel_worker_runtime_support import _resources,_lease,_ProcessGroup
from so101_demo.parallel_batch.contracts.common import RunMode


@pytest.mark.parametrize('problem',[None,'controller','recorder','stopped','expired'])
def test_case_cleanup_never_replaces_native_instance_or_clears_uncertain_stop(tmp_path,monkeypatch,problem):
    _,root,process,native,retirement,calls=stack_fixture(tmp_path,monkeypatch)
    stack=retirement.stack
    stack.process.poll=lambda:None
    resources=replace(_resources(tmp_path,'worker-1',0,181),worker_root=root,session_id='session1')
    helpers=_ProcessGroup()
    module=importlib.import_module('so101_demo.runtime.container_campaign.collection_runtime')
    runtime=module.ContainerCollectionRuntime(resources,RunMode.EXECUTE,existing_stack=stack,
        capture_act_frame=lambda *args:None,process_group=helpers,
        ready_probe=lambda requirements:True,confirm_no_controller_goal=lambda lease:problem!='controller',
        monotonic=lambda:10.)
    runtime.start_physical_runtime()
    lease=_lease()
    runtime._active_lease=lease
    if problem=='recorder':runtime._recorders[runtime._lease_key(lease)]=object()
    if problem=='stopped':runtime._stop_requested.set()
    original=runtime.resources
    result=runtime.prepare_next_case(lease,deadline_monotonic_s=9. if problem=='expired' else 20.,
                                     physical_action_proven_absent=False)
    assert result is (problem is None)
    assert runtime.resources is original and runtime.resources.session_id=='session1'
    assert runtime.resources.generation==original.generation and calls==[]
    if problem is None:
        assert helpers.shutdown_calls==1 and runtime.worker_ready_gate() is True


def test_each_reset_binds_its_original_case_and_requires_prior_cleanup(tmp_path,monkeypatch):
    from test_case_artifacts import fixture as cases_fixture
    from so101_demo.runtime.container_campaign.case_artifacts import CollectionCaseArtifacts
    from so101_demo.runtime.container_campaign.collection_runtime import ContainerCollectionRuntime
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    _,root,process,native,retirement,calls=stack_fixture(tmp_path,monkeypatch)
    stack=retirement.stack
    stack.process.poll=lambda:None
    resources=replace(_resources(tmp_path,'w00',0,181),worker_root=root,session_id='session1')
    refs=cases_fixture(tmp_path)
    artifacts=CollectionCaseArtifacts(worker_id='w00',launch_generation=1,worker_root=root,
        case_inputs=refs,clock=lambda:11.)
    resets=[]
    def reset(lease):
        resets.append(lease.point_id)
        return ResetBoundaryReceipt('reset-2','session1',10.5,1.,2)
    runtime=ContainerCollectionRuntime(resources,RunMode.EXECUTE,existing_stack=stack,
        case_artifacts=artifacts,capture_act_frame=lambda *args:None,process_group=_ProcessGroup(),
        ready_probe=lambda requirements:True,confirm_no_controller_goal=lambda lease:True,
        reset_point=reset,reserve_workspace=artifacts.reserve_workspace,monotonic=lambda:11.)
    runtime.start_physical_runtime()
    leases=[LeaseIdentity('batch',1,'w00',1,scene,'attempt-'+scene,1,10.,100.) for scene in refs]
    runtime.reset_point(leases[0])
    with pytest.raises(ValueError,match='COLLECTION_PREVIOUS_CASE_NOT_CLEANED'):
        runtime.reset_point(leases[1])
    assert resets==['scene-a']
    assert runtime.prepare_next_case(leases[0],deadline_monotonic_s=20.,physical_action_proven_absent=False)
    runtime.reset_point(leases[1])
    assert runtime.episode_scope_path==refs['scene-b']['scope']['path']
    assert runtime.episode_inputs_manifest==refs['scene-b']['inputs_manifest']['path']
    assert resets==['scene-a','scene-b'] and calls==[]


def _borrowed(tmp_path,monkeypatch):
    from so101_demo.runtime.container_campaign.collection_runtime import ContainerCollectionRuntime
    _,root,process,native,retirement,calls=stack_fixture(tmp_path,monkeypatch)
    stack=retirement.stack
    stack.process.poll=lambda:None
    data=tmp_path/'data'/'tasks'/'task-1'
    data.mkdir(parents=True)
    resources=replace(_resources(tmp_path,'w00',0,181),worker_root=data,session_id='session1')
    def build(resources=resources,native_owned_root=root,**extra):
        options=dict(capture_act_frame=lambda *args:None,process_group=_ProcessGroup(),
            ready_probe=lambda requirements:True)|extra
        return ContainerCollectionRuntime(resources,RunMode.EXECUTE,existing_stack=stack,
            native_owned_root=native_owned_root,**options)
    return build,resources,root,stack,data


def test_task_data_root_separate_from_native_owned_root(tmp_path,monkeypatch):
    build,resources,root,stack,data=_borrowed(tmp_path,monkeypatch)
    runtime=build()
    assert runtime.resources.worker_root==data and runtime.stack is stack
    assert not data.is_relative_to(root) and stack.launch.evidence_root==root/'stack'


@pytest.mark.parametrize('problem',['stack_root','domain','session','data_inside_stack',
                                    'relative_root','missing_root','symlink_root','file_root'])
def test_foreign_stack_root_domain_or_session_refused(tmp_path,monkeypatch,problem):
    build,resources,root,stack,data=_borrowed(tmp_path,monkeypatch)
    kwargs={}
    if problem=='stack_root':kwargs['native_owned_root']=tmp_path/'data'
    elif problem=='domain':kwargs['resources']=replace(resources,ros_domain_id=182)
    elif problem=='session':kwargs['resources']=replace(resources,session_id='other')
    elif problem=='data_inside_stack':
        inside=root/'stack'/'tasks';inside.mkdir()
        kwargs['resources']=replace(resources,worker_root=inside)
    elif problem=='relative_root':kwargs['native_owned_root']=Path('owned')
    elif problem=='missing_root':kwargs['native_owned_root']=tmp_path/'nowhere'
    elif problem=='symlink_root':
        link=tmp_path/'link';link.symlink_to(root);kwargs['native_owned_root']=link
    else:kwargs['native_owned_root']=root/'stack'/'cleanup-receipt.json'
    with pytest.raises(ValueError):build(**kwargs)


def test_legacy_root_check_unchanged(tmp_path,monkeypatch):
    from so101_demo.runtime.container_campaign.collection_runtime import ContainerCollectionRuntime
    build,resources,root,stack,data=_borrowed(tmp_path,monkeypatch)
    def legacy(resources):
        return ContainerCollectionRuntime(resources,RunMode.EXECUTE,existing_stack=stack,
            capture_act_frame=lambda *args:None,process_group=_ProcessGroup(),ready_probe=lambda requirements:True)
    with pytest.raises(ValueError,match='COLLECTION_BORROWED_STACK_MISMATCH'):legacy(resources)
    assert legacy(replace(resources,worker_root=root)).resources.worker_root==root


def test_collection_facts_are_copied_at_the_write_and_cleared_by_the_next_reset(tmp_path,monkeypatch):
    """Real runtime and real record writer; the reset port is a controlled double."""
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    build,resources,root,stack,data=_borrowed(tmp_path,monkeypatch)
    runtime=build(reset_point=lambda lease:ResetBoundaryReceipt('reset-2','session1',10.5,1.,2))
    assert runtime.collection_facts is None
    facts={'processor':{'returncode':3,'qc':{'status':'NOT_RUN'}},'events':['a']}
    runtime._write_collection_record(data,facts,'OFFLINE_PROCESSOR_INVALID: rc=3')
    facts['events'].append('mutated later')
    assert runtime.collection_facts==({'processor':{'returncode':3,'qc':{'status':'NOT_RUN'}},'events':['a']},
                                      'OFFLINE_PROCESSOR_INVALID: rc=3')
    document=json.loads((data/'recorder-orchestration.json').read_bytes())
    assert document['reason']=='OFFLINE_PROCESSOR_INVALID: rc=3' and document['processor']['returncode']==3
    runtime.start_physical_runtime()
    runtime.reset_point(LeaseIdentity('batch',1,'w00',1,'scene-a','attempt-a',1,10.,100.))
    assert runtime.collection_facts is None


def _retire_rig(tmp_path,monkeypatch,**extra):
    """A real runtime over the real process tree; the stack process, ready probe and controller probe are doubles."""
    from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree
    build,resources,root,stack,data=_borrowed(tmp_path,monkeypatch)
    tree_options=extra.pop('tree',{})
    tree=WorkerOwnedProcessTree(manifest_path=data/'owned-runtime-processes.json',**tree_options)
    options=dict(process_group=tree,confirm_no_controller_goal=lambda lease:True,close_runtime=lambda:None)|extra
    runtime=build(**options)
    runtime.start_physical_runtime()
    lease=_lease('w00')
    runtime._active_lease=lease
    return runtime,lease,tree,stack,data


def _helper(runtime,role='helper'):
    from so101_demo.runtime.task_stack import StackProcessSpec
    return runtime._processes.start(StackProcessSpec(role,(sys.executable,'-c','import time\ntime.sleep(60)')))


def _on_disk_processes(data):
    return json.loads((data/'owned-runtime-processes.json').read_bytes())['processes']


def test_retire_case_stops_helpers_and_proves_every_named_fact(tmp_path,monkeypatch):
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch)
    identity=_helper(runtime)
    assert runtime.owned_process_manifest.processes==(identity,) and len(_on_disk_processes(data))==1
    proofs=runtime.retire_case(lease,cancelled=None,absent=False)
    assert proofs=={'processes_empty':True,'manifest_readback_empty':True,'recorder_proven':True,
                    'controller_proven':True,'runtime_closed':True,'stack_alive':True,'ready_gate':True}
    assert runtime.owned_process_manifest.processes==() and _on_disk_processes(data)==[]


@pytest.mark.parametrize('problem',['controller','recorder_registered','recorder_unproven','close_runtime',
                                    'stack_dead','not_ready','stale_manifest_file'])
def test_retire_case_names_the_fact_that_failed(tmp_path,monkeypatch,problem):
    options={}
    if problem=='controller':options['confirm_no_controller_goal']=lambda lease:None
    elif problem=='close_runtime':options['close_runtime']=lambda:1/0
    elif problem=='stale_manifest_file':
        from so101_demo.runtime.parallel_worker_parts.process_tree import WorkerOwnedProcessTree
        class Stale(WorkerOwnedProcessTree):
            def _write_manifest_locked(self):
                if self._manifest_path is not None:
                    self._manifest_path.write_text(json.dumps({'schema_version':1,'processes':[{'role':'x'}]}))
        options['process_group']=Stale(manifest_path=tmp_path/'unused.json')
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch,**options)
    if problem=='stale_manifest_file':
        runtime._processes._manifest_path=data/'owned-runtime-processes.json'
    if problem=='recorder_registered':runtime._recorders[runtime._lease_key(lease)]=object()
    elif problem=='recorder_unproven':runtime._recorder_stop_proofs[runtime._lease_key(lease)]=False
    elif problem=='stack_dead':stack.process.poll=lambda:1
    elif problem=='not_ready':runtime._ready_probe=lambda requirements:False
    proofs=runtime.retire_case(lease,cancelled=None,absent=False)
    failed={name for name,value in proofs.items() if value is not True}
    assert failed=={'controller':{'controller_proven'},'recorder_registered':{'recorder_proven'},
        'recorder_unproven':{'recorder_proven'},'close_runtime':{'runtime_closed'},'stack_dead':{'stack_alive'},
        'not_ready':{'ready_gate'},'stale_manifest_file':{'manifest_readback_empty'}}[problem]


def _reset_receipt():
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    return ResetBoundaryReceipt('reset-2','session1',10.5,1.,2)


def test_retire_case_resumes_a_simulation_the_task_left_paused(tmp_path,monkeypatch):
    """The reset freezes physics for the point gate and the gate resumes it. A fault in between must not hand the stack
    back to native retirement frozen: the stop check needs advancing physics and fresh samples."""
    resumed=[]
    receipt=_reset_receipt()
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch,reset_point=lambda lease:receipt,
        resume_physics=lambda lease,reset:resumed.append((lease,reset)) or True)
    runtime.reset_point(lease)
    assert resumed==[]
    proofs=runtime.retire_case(lease,cancelled=False,absent=False)
    assert resumed==[(lease,receipt)] and proofs['physics_resumed'] is True
    runtime.retire_case(lease,cancelled=False,absent=False)
    assert len(resumed)==1   # the hold is released once


def test_retire_case_reports_a_simulation_it_could_not_resume(tmp_path,monkeypatch):
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch,reset_point=lambda lease:_reset_receipt(),
        resume_physics=lambda lease,reset:False)
    runtime.reset_point(lease)
    proofs=runtime.retire_case(lease,cancelled=False,absent=False)
    assert proofs['physics_resumed'] is False
    assert runtime.retire_case(lease,cancelled=False,absent=False)['physics_resumed'] is False   # still held, tried again


def test_retire_case_leaves_a_running_simulation_alone(tmp_path,monkeypatch):
    resumed=[]
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch,
        resume_physics=lambda lease,reset:resumed.append(lease) or True)
    proofs=runtime.retire_case(lease,cancelled=None,absent=False)
    assert 'physics_resumed' not in proofs and resumed==[]


def test_retire_case_reports_a_helper_that_survives_its_signals(tmp_path,monkeypatch):
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch,
        tree=dict(signal_process=lambda pid,signum:None,interrupt_timeout_s=.2,terminate_timeout_s=.2))
    identity=_helper(runtime)
    try:
        proofs=runtime.retire_case(lease,cancelled=None,absent=False)
        assert proofs['processes_empty'] is False and proofs['manifest_readback_empty'] is False
        assert runtime.owned_process_manifest.processes==(identity,)
    finally:
        for _identity,child in list(tree._children):child.kill();child.wait()


def test_retire_case_controller_proof_follows_the_path_taken(tmp_path,monkeypatch):
    calls=[]
    def confirm(lease):
        calls.append(lease)
        return True
    runtime,lease,tree,stack,data=_retire_rig(tmp_path,monkeypatch,confirm_no_controller_goal=confirm)
    assert runtime.retire_case(lease,cancelled=None,absent=True)['controller_proven'] is True and calls==[]
    assert runtime.retire_case(lease,cancelled=None,absent=False)['controller_proven'] is True and len(calls)==1
    stopped=runtime.retire_case(lease,cancelled=True,absent=False)
    assert stopped['controller_proven'] is True and 'stack_alive' not in stopped and 'ready_gate' not in stopped
    assert runtime.retire_case(lease,cancelled=False,absent=False)['controller_proven'] is False
    assert runtime.retire_case(lease,cancelled=True,absent=True)['controller_proven'] is True
    runtime._active_lease=None
    before=len(calls)
    assert runtime.retire_case(None,cancelled=None,absent=False)['controller_proven'] is True and len(calls)==before
