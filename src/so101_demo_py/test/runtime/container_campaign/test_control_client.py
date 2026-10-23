"""Real bounded normal control sockets; external container readiness is controlled."""

import asyncio
from dataclasses import asdict
import importlib
import os
import time

import pytest

from test_shard_owner import fixture as owner_fixture
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerOwnerKey,ContainerChildBinding,read_process_owner,pid_namespace_inode,
)
from so101_teleop.unified.child_runtime import ContainerChildIdentity,ContainerChildIpcServer
from so101_teleop.unified.contracts import OwnerKey


def test_actual_normal_socket_uses_fd_address_and_checks_original_envelope(tmp_path):
    """The real client and the real container child server over the fd-addressed normal socket; only the executor is a double."""
    from so101_demo.runtime.container_campaign.task_contracts import InputRef,InstanceStatus,TaskRequest,TaskSpec,TaskStatus
    owner,registry,calls,root=owner_fixture(tmp_path,(0,''))
    (root/'control').chmod(0o700)
    module=importlib.import_module('so101_demo.runtime.container_campaign.control_client')
    process=read_process_owner(os.getpid())
    container=ContainerOwnerKey('f'*64,'2026-10-12T01:02:03.123Z',owner.image['digest'],1)
    binding=ContainerChildBinding(container,process,pid_namespace_inode(),str(root/'control/normal.sock'))
    seen=[]
    class Port:
        async def assign_task(self,task):
            seen.append(('assign_task',task.task_id));return TaskStatus(task_id=task.task_id,state='ACCEPTED')
        async def get_status(self,task_id=None):
            seen.append(('get_status',task_id))
            return InstanceStatus(instance_id=owner.launch.launch_id,state='READY')
        async def terminate(self,reason):
            seen.append(('terminate',reason))
            return InstanceStatus(instance_id=owner.launch.launch_id,state='STOPPING',fault_reason=reason)
    identity=ContainerChildIdentity(runtime_id=owner.spec['runtime_id'],act_campaign_id=owner.context.campaign_id,
        act_worker_id='w00',act_generation=1,normal_queue_limit=2)
    server=ContainerChildIpcServer(identity,socket_root=root/'control',owner=OwnerKey(**asdict(process)),
        service_epoch=owner.context.service_epoch,service_token=owner.token,max_bytes=owner.max_bytes,
        task_port=Port(),generation=1,close_timeout_s=1.,process_owner=process)
    client=module.ContainerControlClient(binding=binding,context=owner.context,runtime_id=owner.spec['runtime_id'],
        service_token=owner.token,max_bytes=owner.max_bytes,ready_probe=lambda:True)
    deadline=time.monotonic_ns()+5_000_000_000
    async def run():
        await server.start()
        try:
            assert server.normal_socket==root/'control/normal.sock' and server.socket_parent_fd is not None
            task=TaskSpec(task_id='scene-001',inputs_ref=InputRef(path='/act/inputs/scene-001.json',sha256='a'*64),
                deadline_monotonic_s=time.monotonic()+60)
            reply=await client.call_task(TaskRequest(operation='assign_task',payload=task.model_dump(),deadline_ns=deadline))
            assert reply=={'task_id':'scene-001','state':'ACCEPTED','fault_reason':None}
            reply=await client.call_task(TaskRequest(operation='get_status',payload={'task_id':None},deadline_ns=deadline))
            assert reply['state']=='READY' and reply['instance_id']==owner.launch.launch_id
            # the original envelope check still refuses a request past the campaign deadline before any socket I/O
            late=TaskRequest(operation='get_status',payload={'task_id':None},
                deadline_ns=int(owner.context.deadline_monotonic_s*1e9)+1)
            with pytest.raises(ValueError,match='CONTAINER_TASK_ENVELOPE_INVALID'):
                await client.call_task(late)
            assert seen==[('assign_task','scene-001'),('get_status',None)]
        finally:
            await server.close()
    try:
        asyncio.run(run())
    finally:
        registry.close()


def test_actual_task_socket_needs_only_task_id_and_no_legacy_token(tmp_path):
    """Real client/decoder exchange; the remote task executor is controlled."""
    from so101_demo.runtime.container_campaign.control_client import ContainerControlClient
    from so101_demo.runtime.container_campaign.task_contracts import TaskRequest
    from so101_demo.runtime.parallel_ipc.frames import transport_address
    from so101_demo.runtime.inference.codec import open_socket_parent
    from so101_teleop.unified.ipc import decode_container_task, encode, IpcReply

    owner, registry, _calls, root = owner_fixture(tmp_path, (0, ''))
    (root/'control').chmod(0o700)
    process = read_process_owner(os.getpid())
    container = ContainerOwnerKey('f'*64, '2026-10-12T01:02:03.123Z', owner.image['digest'], 1)
    binding = ContainerChildBinding(container, process, pid_namespace_inode(),
                                    str(root/'control/normal.sock'))
    client = ContainerControlClient(binding=binding, context=owner.context,
        runtime_id=owner.spec['runtime_id'], service_token=owner.token,
        max_bytes=owner.max_bytes, ready_probe=lambda: True)
    observed = []
    async def handle(reader, writer):
        try:
            packet = decode_container_task(await reader.readline(), max_bytes=owner.max_bytes)
            observed.append(packet.model_dump())
            writer.write(encode(IpcReply(accepted=True, result=dict(
                instance_id=owner.launch.launch_id, state='READY', resources_released=False,
                fault_reason=None, task=dict(task_id=packet.payload['task_id'],
                state='SUCCEEDED', fault_reason=None)))))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    async def run():
        fd = open_socket_parent(root/'control/normal.sock')
        server = await asyncio.start_unix_server(handle,
            path=transport_address(root/'control/normal.sock', fd))
        os.chmod(root/'control/normal.sock', 0o600)
        try:
            packet = TaskRequest(operation='get_status', payload={'task_id': 'scene-001'},
                deadline_ns=time.monotonic_ns()+5_000_000_000)
            response = await client.call_task(packet)
            assert response['task']['task_id'] == 'scene-001'
            assert response['task']['state'] == 'SUCCEEDED'
        finally:
            server.close()
            await server.wait_closed()
            os.close(fd)
    try:
        asyncio.run(run())
        assert len(observed) == 1
        assert set(observed[0]) == {'operation', 'deadline_ns', 'payload'}
        assert observed[0]['payload'] == {'task_id': 'scene-001'}
    finally:
        registry.close()
