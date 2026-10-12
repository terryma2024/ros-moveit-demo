"""Real bounded normal control sockets; external container readiness is controlled."""

import asyncio
from dataclasses import asdict
import importlib
import os
from types import SimpleNamespace
import time

from test_shard_owner import fixture as owner_fixture
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerOwnerKey,ContainerChildBinding,read_process_owner,pid_namespace_inode,
)
from so101_demo.runtime.container_campaign.heartbeat import OwnerHeartbeatMonitor
from so101_teleop.unified.child_runtime import ChildRuntime,ContainerChildIpcServer
from so101_teleop.unified.contracts import OwnerKey
from so101_teleop.unified.ipc import IpcRequest


def test_actual_normal_socket_uses_fd_address_and_checks_original_envelope(tmp_path):
    owner,registry,calls,root=owner_fixture(tmp_path,(0,''))
    (root/'control').chmod(0o700)
    module=importlib.import_module('so101_demo.runtime.container_campaign.control_client')
    process=read_process_owner(os.getpid())
    container=ContainerOwnerKey('f'*64,'2026-10-12T01:02:03.123Z',owner.image['digest'],1)
    binding=ContainerChildBinding(container,process,pid_namespace_inode(),str(root/'control/normal.sock'))
    async def stop_act(reason):return True
    runtime=ChildRuntime(SimpleNamespace(stop_act=stop_act),owner=OwnerKey(**asdict(process)),
        service_epoch=owner.context.service_epoch,runtime_id=owner.spec['runtime_id'],normal_queue_limit=2,
        act_campaign_id=owner.context.campaign_id,act_worker_id='w00',act_generation=1)
    monitor=OwnerHeartbeatMonitor(generation=1,timeout_ns=5_000_000_000)
    server=ContainerChildIpcServer(runtime,socket_root=root/'control',owner=runtime.owner,
        service_epoch=owner.context.service_epoch,service_token=owner.token,owner_monitor=monitor,
        process_owner=process)
    client=module.ContainerControlClient(binding=binding,context=owner.context,runtime_id=owner.spec['runtime_id'],
        service_token=owner.token,max_bytes=owner.max_bytes,ready_probe=lambda:True)
    async def run():
        await server.start()
        try:
            packet=IpcRequest(version=1,operation='observe',command_id='observation',
                deadline_ns=time.monotonic_ns()+5_000_000_000,service_epoch=owner.context.service_epoch,
                runtime_id=owner.spec['runtime_id'],service_token=owner.token)
            reply=await client.call(packet)
            assert reply.accepted and reply.code=='OK'
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
