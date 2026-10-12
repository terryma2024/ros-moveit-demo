"""Host Worker dispatch uses real child sockets and durable Coordinator RPC.

Only the physical Worker and external inference/container observations are
controlled. This is a transport integration test, not collection qualification.
"""

import asyncio
from dataclasses import asdict,replace
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

from test_parallel_batch_coordinator import make,gate_summary
from test_shard_owner import fixture as owner_fixture
from test_config_identity import campaign_fixture,write_config
from so101_demo.runtime.container_campaign.collection_driver import CollectionShardDriver
from so101_demo.runtime.container_campaign.control_client import ContainerControlClient
from so101_demo.runtime.container_campaign.heartbeat import OwnerHeartbeatMonitor
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerOwnerKey,ContainerChildBinding,read_process_owner,pid_namespace_inode,
)
from so101_demo.runtime.container_campaign.service_owner import ServiceEndpoint
from so101_demo.runtime.container_campaign.worker_transport import CollectionCoordinatorProxy
from so101_demo.parallel_batch.contracts.common import RunMode,AttemptStatus
from so101_demo.parallel_batch.worker_parts.contracts import WorkerRunResult
from so101_teleop.unified.child_runtime import ChildRuntime,ContainerChildIpcServer
from so101_teleop.unified.contracts import OwnerKey


def ref(path):
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize('failure',[None,'refusal','infra'])
def test_real_host_dispatch_keeps_original_commits_and_never_retries(make,tmp_path,failure):
    module=importlib.import_module('so101_demo.runtime.container_campaign.worker_runner')
    coordinator,clock,results,journal,request=make(worker_ids=('w00',))
    owner,registry,calls,root=owner_fixture(tmp_path,(0,''))
    campaign=campaign_fixture(tmp_path)
    campaign['gpu_uuid']=owner.context.physical_gpu_uuid
    campaign['shard_image']=owner.image
    config_path=write_config(tmp_path,campaign)
    owner.context=replace(owner.context,campaign_config_path=str(config_path),
        campaign_config_sha256=ref(config_path)['sha256'],
        runtime_config_sha256=campaign['controlled_runtime']['sha256'])
    control=root/'control';control.chmod(0o700)
    identity={name:getattr(owner.context,name) for name in (
        'manifest_sha256','runtime_config_sha256','collection_config_sha256','contact_policy_fingerprint')}
    owner.spec=owner.spec|dict(workload_kind='act_collection',business_identity=identity)
    scene=tmp_path/'scenes.json'
    scene.write_text(json.dumps(dict(scenarios=[dict(scene_id=p,split='qualification',
        cup_position_world_m=[.2,.1,.02]) for p in request.selected_point_ids])))
    case_inputs={}
    for point in request.selected_point_ids:
        scope=tmp_path/(point+'-scope.json');scope.write_text('{}')
        inputs=tmp_path/(point+'-inputs.json');inputs.write_text('{}')
        case_inputs[point]=dict(scope=ref(scope),inputs_manifest=ref(inputs))
    documents=[]
    class Worker:
        def run(self):
            document=documents[-1]
            proxy=CollectionCoordinatorProxy(Path(document['coordinator']['socket_path']),
                Path(document['coordinator']['token_path']),worker_id='w00',generation=1,
                mode=RunMode.EXECUTE,coordinator_epoch=journal.coordinator_epoch)
            lease=proxy.grant_lease('w00',generation=1,request_key='grant')
            lease=proxy.ack_lease(lease,request_key='ack').lease
            lease=proxy.ack_attempt_started(lease,request_key='start',gate_summary=gate_summary(lease)).lease
            location=str(tmp_path/'external-seal')
            results.sealed[location]=(lease.attempt_id,AttemptStatus.FAILED)
            proxy.commit_result(lease,location,request_key='commit')
            return (WorkerRunResult(lease.point_id,AttemptStatus.INVALID if failure=='infra' else AttemptStatus.FAILED,
                failure!='infra','PORT_FAILURE' if failure=='infra' else 'POINT_TERMINAL'),)
        def request_stop(self):pass
    class Helpers:
        def shutdown_owned(self):pass
    def build(document,**kwargs):
        documents.append(document)
        if failure=='refusal':raise ValueError('EXTERNAL_WORKER_REFUSED')
        return Worker(),Helpers()
    async def retire(**kwargs):
        return dict(goals_stopped=True,controllers_stopped=True,ros_children_exited=True,ros_graph_empty=True,forced=False)
    from types import SimpleNamespace
    driver=CollectionShardDriver(spec=owner.spec,stack=object(),
        retirement=SimpleNamespace(retire=retire),worker_builder=build)
    process=read_process_owner(os.getpid())
    runtime=ChildRuntime(driver,owner=OwnerKey(**asdict(process)),service_epoch='epoch',runtime_id='runtime',
        normal_queue_limit=2,act_campaign_id='campaign',act_worker_id='w00',act_generation=1)
    server=ContainerChildIpcServer(runtime,socket_root=control,owner=runtime.owner,
        service_epoch='epoch',service_token=owner.token,process_owner=process,
        owner_monitor=OwnerHeartbeatMonitor(generation=1,timeout_ns=5_000_000_000))
    binding=ContainerChildBinding(ContainerOwnerKey('f'*64,'2026-10-12T01:02:03.123Z',owner.image['digest'],1),
        process,pid_namespace_inode(),str(control/'normal.sock'))
    client=ContainerControlClient(binding=binding,context=owner.context,runtime_id='runtime',
        service_token=owner.token,max_bytes=owner.max_bytes,ready_probe=lambda:True)
    owner.control_client=lambda:client
    async def health():return True
    owner.check_health=health
    endpoints={role:ServiceEndpoint(role,tmp_path/role/'inference.sock','service-'+role,
               campaign[role+'_service']['max_frame_bytes'])
               for role in ('head','teacher')}
    runner=module.ContainerWorkerRunner(context=owner.context,parallel_runtime=owner.spec['controlled_runtime'],
        scene_manifest=ref(scene),case_inputs=case_inputs)
    async def run():
        driver.start_task=asyncio.create_task(asyncio.sleep(0))
        await server.start()
        try:
            arguments=dict(coordinator=coordinator,journal=journal,shard=owner,endpoints=endpoints,
                config=coordinator.config,dispatch_allowed=lambda:True)
            if failure:
                with pytest.raises(ValueError,match='COLLECTION_WORKER_REPLY_REJECTED' if failure=='refusal'
                                   else 'COLLECTION_WORKER_INFRA_FAILURE'):
                    await runner(**arguments)
                assert (control/'worker-run-failure.json').is_file()
                if failure=='infra':
                    assert len([e for e in journal.replay().events if e.type=='RESULT_COMMITTED'])==1
            else:
                assert (await runner(**arguments))['worker_id']=='w00'
                assert len([e for e in journal.replay().events if e.type=='RESULT_COMMITTED'])==1
            with pytest.raises(ValueError,match='COLLECTION_WORKER_ALREADY_DISPATCHED'):
                await runner(**arguments)
            assert len(documents)==1
            assert documents[0]['teacher']['socket_path']=='/act/ipc/teacher/inference.sock'
            assert set(documents[0]['case_inputs'])==set(request.selected_point_ids)
            assert (control/'coordinator.sock').exists()
            assert not runner.transports[owner.launch.launch_id]._thread.is_alive()
        finally:
            await driver.stop_act('test-close')
            await server.close()
    try:asyncio.run(run())
    finally:registry.close()
