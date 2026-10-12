"""Collection driver lifecycle checks with controlled external Worker I/O."""

import asyncio
import hashlib
import importlib
from types import SimpleNamespace
import time
import threading
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from test_shard_owner import fixture as owner_fixture
from so101_teleop.unified.ipc import IpcRequest


def fixture(tmp_path):
    owner,registry,calls,root=owner_fixture(tmp_path,(0,''))
    path=root/'control/worker-spec.json'
    path.write_text('{}')
    identity=dict(manifest_sha256='a'*64,runtime_config_sha256='b'*64,
        collection_config_sha256='c'*64,contact_policy_fingerprint='d'*64)
    spec=owner.spec|dict(workload_kind='act_collection',business_identity=identity)
    observed=[]
    class Worker:
        def run(self):observed.append('run');return ()
        def request_stop(self):observed.append('stop')
    class Runtime:
        def shutdown_owned(self):observed.append('helpers-closed')
    def build(document,*,stack,shard_spec):
        observed.append(('build',document));return Worker(),Runtime()
    async def retire(**kwargs):
        observed.append('native-retire')
        return dict(goals_stopped=True,controllers_stopped=True,ros_children_exited=True,ros_graph_empty=True,forced=False)
    module=importlib.import_module('so101_demo.runtime.container_campaign.collection_driver')
    driver=module.CollectionShardDriver(spec=spec,stack=object(),retirement=SimpleNamespace(retire=retire),
                                         worker_builder=build)
    payload=identity|dict(launch_generation=1,worker_spec=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    deadline=time.monotonic_ns()+5_000_000_000
    packet=IpcRequest(version=1,operation='act_collection_start',command_id='worker-run',deadline_ns=deadline,
        service_epoch='epoch',runtime_id='runtime',service_token='e'*64,campaign_id='campaign',worker_id='w00',
        session_id='campaign-w00-g1',attempt_id='wave-0',execution_generation=1,
        token=dict(operation_id='operation',child_id='w00',runtime_id='runtime',execution_generation=1,
                   deadline_ns=deadline,revocation_revision=0),payload=payload)
    return driver,packet,observed,registry


def test_collection_worker_run_is_single_use_and_native_retirement_is_once(tmp_path):
    driver,packet,observed,registry=fixture(tmp_path)
    async def run():
        driver.start_task=asyncio.create_task(asyncio.sleep(0))
        result=await driver.act_collection_start(packet)
        assert result['worker_id']=='w00' and result['launch_generation']==1
        with pytest.raises(ValueError,match='COLLECTION_SHARD_ALREADY_RUN'):
            await driver.act_collection_start(packet)
        first,second=await asyncio.gather(driver.stop_act('close'),driver.stop_act('close'))
        assert first is second is True and observed.count('native-retire')==1
        assert observed.count('helpers-closed')==1
    try:asyncio.run(run())
    finally:registry.close()


def test_stop_waits_for_inflight_builder_and_closes_its_helpers(tmp_path):
    driver,packet,observed,registry=fixture(tmp_path)
    entered,released=threading.Event(),threading.Event()
    build=driver.worker_builder
    def blocked_builder(*args,**kwargs):
        entered.set()
        assert released.wait(3.)
        return build(*args,**kwargs)
    driver.worker_builder=blocked_builder
    async def run():
        driver.start_task=asyncio.create_task(asyncio.sleep(0))
        collection=asyncio.create_task(driver.act_collection_start(packet))
        assert await asyncio.to_thread(entered.wait,3.)
        stop=asyncio.create_task(driver.stop_act('owner-lost'))
        await asyncio.sleep(0)
        released.set()
        assert await asyncio.wait_for(stop,3.) is True
        with pytest.raises(ValueError,match='COLLECTION_SHARD_FENCED'):
            await collection
        assert 'run' not in observed
        assert observed.count('stop')==1 and observed.count('helpers-closed')==1
        assert observed.count('native-retire')==1
    try:asyncio.run(run())
    finally:released.set();registry.close()


def test_worker_stop_failure_still_retires_native_stack_and_returns_unproven(tmp_path):
    driver,packet,observed,registry=fixture(tmp_path)
    async def run():
        driver.start_task=asyncio.create_task(asyncio.sleep(0))
        await driver.act_collection_start(packet)
        def broken_stop():raise RuntimeError('stop-unconfirmed')
        driver.worker.request_stop=broken_stop
        assert await driver.stop_act('close') is False
        assert observed.count('native-retire')==1 and observed.count('helpers-closed')==1
        assert driver.cleanup_errors==[dict(stage='worker-stop',type='RuntimeError',reason='stop-unconfirmed')]
    try:asyncio.run(run())
    finally:registry.close()


def test_actual_child_socket_routes_collection_start_and_cancel(tmp_path):
    from so101_demo.runtime.container_campaign.control_client import ContainerControlClient
    from so101_demo.runtime.container_campaign.process_identity import (
        ContainerOwnerKey,ContainerChildBinding,read_process_owner,pid_namespace_inode,
    )
    from so101_demo.runtime.container_campaign.heartbeat import OwnerHeartbeatMonitor
    from so101_teleop.unified.child_runtime import ChildRuntime,ContainerChildIpcServer
    from so101_teleop.unified.contracts import OwnerKey
    driver,packet,observed,registry=fixture(tmp_path)
    (tmp_path/'transport').mkdir()
    owner,other_registry,calls,root=owner_fixture(tmp_path/'transport',(0,''))
    # Use the original driver private socket root; only external Worker/stop
    # ports are controlled. Child dispatch, schema and socket I/O are real.
    control=packet.payload['worker_spec']['path']
    control=Path(control).parent
    control.chmod(0o700)
    process=read_process_owner(os.getpid())
    binding=ContainerChildBinding(ContainerOwnerKey('f'*64,'2026-10-12T01:02:03.123Z',owner.image['digest'],1),
        process,pid_namespace_inode(),str(control/'normal.sock'))
    runtime=ChildRuntime(driver,owner=OwnerKey(**asdict(process)),service_epoch='epoch',runtime_id='runtime',
        normal_queue_limit=2,act_campaign_id='campaign',act_worker_id='w00',act_generation=1)
    server=ContainerChildIpcServer(runtime,socket_root=control,owner=runtime.owner,
        service_epoch='epoch',service_token='e'*64,process_owner=process,
        owner_monitor=OwnerHeartbeatMonitor(generation=1,timeout_ns=5_000_000_000))
    client=ContainerControlClient(binding=binding,context=owner.context,runtime_id='runtime',
        service_token='e'*64,max_bytes=owner.max_bytes,ready_probe=lambda:True)
    async def run():
        driver.start_task=asyncio.create_task(asyncio.sleep(0))
        await server.start()
        try:
            reply=await client.call(packet)
            assert reply.accepted and reply.code=='OK'
            assert reply.result==dict(operation_id='operation',campaign_id='campaign',worker_id='w00',
                execution_generation=1,body=dict(worker_id='w00',launch_generation=1,results=[]))
            cancel=packet.model_copy(update=dict(operation='cancel',command_id='cancel',payload=dict(reason='close')))
            reply=await client.call(cancel)
            assert reply.accepted and reply.result['body']==dict(stopped_confirmed=True)
            assert observed.count('native-retire')==1 and observed.count('helpers-closed')==1
        finally:await server.close()
    try:asyncio.run(run())
    finally:registry.close();other_registry.close()


@pytest.mark.parametrize('problem',['wrong_hash','foreign_file','wrong_identity'])
def test_bad_worker_reference_never_builds_or_runs(tmp_path,problem):
    driver,packet,observed,registry=fixture(tmp_path)
    payload=dict(packet.payload)
    if problem=='wrong_hash':payload['worker_spec']=payload['worker_spec']|dict(sha256='f'*64)
    elif problem=='foreign_file':payload['worker_spec']=payload['worker_spec']|dict(path=str(tmp_path/'foreign.json'))
    else:payload['manifest_sha256']='f'*64
    packet=packet.model_copy(update={'payload':payload})
    async def run():
        with pytest.raises(ValueError):await driver.act_collection_start(packet)
        assert observed==[]
    try:asyncio.run(run())
    finally:registry.close()
