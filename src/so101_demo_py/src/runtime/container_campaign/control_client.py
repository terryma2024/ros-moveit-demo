"""One bounded control exchange against the exact registered private shard."""

import asyncio
import os
from pathlib import Path
import stat
import time

from so101_demo.runtime.container_campaign.process_identity import ContainerChildBinding
from so101_demo.runtime.inference.codec import open_socket_parent
from so101_demo.runtime.parallel_ipc.frames import transport_address
from so101_teleop.unified.contracts import AdmittedCampaignContext
from so101_teleop.unified.ipc import IpcRequest,IpcReply


class ContainerControlClient:
    def __init__(self,*,binding,context,runtime_id,service_token,max_bytes,ready_probe):
        if (type(binding) is not ContainerChildBinding or type(context) is not AdmittedCampaignContext
                or type(runtime_id) is not str or not runtime_id or type(service_token) is not str
                or not service_token or type(max_bytes) is not int or max_bytes<=0 or not callable(ready_probe)):
            raise ValueError('CONTAINER_CONTROL_CLIENT_INVALID')
        self.binding,self.context,self.runtime_id=binding,context,runtime_id
        self.token,self.max_bytes,self.ready_probe=service_token,max_bytes,ready_probe

    async def call(self,packet):
        if (type(packet) is not IpcRequest or packet.service_epoch!=self.context.service_epoch
                or packet.runtime_id!=self.runtime_id or packet.service_token!=self.token
                or packet.deadline_ns>int(self.context.deadline_monotonic_s*1e9)):
            raise ValueError('CONTAINER_CONTROL_ENVELOPE_MISMATCH')
        if packet.token is not None:
            if (packet.token.operation_id!=self.context.operation_id
                    or packet.execution_generation!=self.context.execution_generation
                    or packet.campaign_id!=self.context.campaign_id):
                raise ValueError('CONTAINER_CONTROL_CONTEXT_MISMATCH')
        if not await asyncio.to_thread(self.ready_probe):
            raise ValueError('CONTAINER_CONTROL_OWNER_NOT_READY')
        remaining=(packet.deadline_ns-time.monotonic_ns())/1e9
        if remaining<=0:
            raise ValueError('CONTAINER_CONTROL_DEADLINE_EXPIRED')
        reply=await asyncio.wait_for(self._exchange(packet),remaining)
        if not await asyncio.to_thread(self.ready_probe):
            raise ValueError('CONTAINER_CONTROL_OWNER_CHANGED')
        if time.monotonic_ns()>=packet.deadline_ns:
            raise ValueError('CONTAINER_CONTROL_DEADLINE_EXPIRED')
        return reply

    async def _exchange(self,packet):
        path=Path(self.binding.control_socket)
        fd=open_socket_parent(path)
        writer=None
        try:
            info=os.stat(path.name,dir_fd=fd,follow_symlinks=False)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():
                raise ValueError('CONTAINER_CONTROL_SOCKET_INVALID')
            reader,writer=await asyncio.open_unix_connection(transport_address(path,fd),limit=self.max_bytes+1)
            data=packet.model_dump_json().encode()+b'\n'
            if len(data)>self.max_bytes:
                raise ValueError('CONTAINER_CONTROL_REQUEST_OVERSIZE')
            writer.write(data)
            await writer.drain()
            raw=await reader.readline()
            if not raw or len(raw)>self.max_bytes:
                raise ValueError('CONTAINER_CONTROL_REPLY_INVALID')
            return IpcReply.model_validate_json(raw,strict=True)
        finally:
            os.close(fd)
            if writer is not None:
                writer.close()
                await writer.wait_closed()
