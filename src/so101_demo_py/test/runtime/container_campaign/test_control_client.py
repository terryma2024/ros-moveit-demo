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
