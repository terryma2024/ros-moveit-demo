"""Case cleanup keeps the borrowed native stack/session and preserves stop fences."""

import importlib
from dataclasses import replace

import pytest

from test_shard_retirement import fixture as stack_fixture
from parallel_worker_runtime_support import _resources,_lease,_ProcessGroup
from so101_demo.parallel_batch.contracts.common import RunMode


@pytest.mark.parametrize('problem',[None,'controller','recorder','stopped','expired'])
def test_case_cleanup_never_replaces_native_instance_or_clears_uncertain_stop(tmp_path,monkeypatch,problem):
    _,root,process,native,retirement,calls=stack_fixture(tmp_path,monkeypatch)
    stack=retirement.stack
    from so101_demo.runtime.container_campaign.stack_launch import ContainerActStackLaunch
    old=stack.launch
    stack.launch=ContainerActStackLaunch(ros2_executable=old.ros2_executable,session_id=old.session_id,
        evidence_root=old.evidence_root,ros_domain_id=old.ros_domain_id,environment=old.environment,
        ros_namespace='/act/campaign/w00',readiness_timeout_s=180.)
    stack.process.poll=lambda:None
    resources=replace(_resources(tmp_path,'worker-1',0,181),worker_root=root,session_id='session1',
                      controller_namespace='/act/campaign/w00')
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
    from so101_demo.runtime.container_campaign.stack_launch import ContainerActStackLaunch
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    _,root,process,native,retirement,calls=stack_fixture(tmp_path,monkeypatch)
    stack=retirement.stack
    old=stack.launch
    stack.launch=ContainerActStackLaunch(ros2_executable=old.ros2_executable,session_id=old.session_id,
        evidence_root=old.evidence_root,ros_domain_id=old.ros_domain_id,environment=old.environment,
        ros_namespace='/act/campaign/w00',readiness_timeout_s=180.)
    stack.process.poll=lambda:None
    resources=replace(_resources(tmp_path,'w00',0,181),worker_root=root,session_id='session1',
                      controller_namespace='/act/campaign/w00')
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
