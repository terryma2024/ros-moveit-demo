"""One task end to end through the real Host adapter, client, socket, child server and executor.

Real: ContainerTaskControl, ContainerControlClient (private Unix socket), ContainerChildIpcServer, ContainerTaskExecutor,
immutable task-result.json. Controlled doubles: the Host owner (Docker/registry side), the task execution and the native
retirement. No container, ROS or physical evidence is claimed.
"""

import asyncio
from dataclasses import asdict
import json
import os
import threading
import time

import pytest

from test_shard_owner import fixture as owner_fixture
from so101_demo.runtime.container_campaign.control_client import ContainerControlClient
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, pid_namespace_inode, read_process_owner,
)
from so101_demo.runtime.container_campaign.task_contracts import TaskSpec
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl
from so101_demo.runtime.container_campaign.task_executor import ContainerTaskExecutor
from so101_demo.runtime.container_campaign.task_results import read_task_result, reserve_task_output
from so101_teleop.unified.child_runtime import ContainerChildIdentity, ContainerChildIpcServer
from so101_teleop.unified.contracts import OwnerKey


class ExecutionDouble:
    """Controlled task execution: reserves real output and returns a business-failure summary."""

    def __init__(self, output, spec):
        reserve_task_output(output, spec.task_id)
        self.started = threading.Event()

    def run(self):
        self.started.set()
        return {'teacher_task_result': 'FAILED', 'act_data_status': 'INVALID'}

    def request_stop(self):
        pass

    def shutdown_owned(self):
        return True


class RetirementDouble:
    """Controlled native retirement."""

    def __init__(self):
        self.calls = 0

    async def retire(self, *, fenced):
        assert fenced is True
        self.calls += 1
        return dict(goals_stopped=True, controllers_stopped=True, ros_children_exited=True,
                    ros_graph_empty=True, forced=False)


class HostOwnerDouble:
    """Controlled Host owner: hands out the real control client and reports a proven container exit."""

    def __init__(self, base, client):
        self.launch, self.context = base.launch, base.context
        self.startup_budget = self.status_budget = 5.
        self.client, self.closed = client, 0

    async def start(self):
        return None

    def control_client(self):
        return self.client

    async def close(self):
        self.closed += 1
        return dict(terminated=True, launch_id=self.launch.launch_id, errors=[])


def test_assign_poll_collect_and_terminate_through_the_real_socket(tmp_path):
    base, registry, _calls, root = owner_fixture(tmp_path, (0, ''))
    (root/'control').chmod(0o700)
    output = tmp_path/'task-output'
    output.mkdir()
    process = read_process_owner(os.getpid())
    retirement = RetirementDouble()
    async def run():
        executor = ContainerTaskExecutor(instance_id=base.launch.launch_id,
            builder=lambda spec: ExecutionDouble(output, spec), retirement=retirement, output_root=output,
            owner_timeout_s=5., stop_timeout_s=2., retire_timeout_s=2., ready=False)
        identity = ContainerChildIdentity(runtime_id=base.spec['runtime_id'], act_campaign_id='campaign',
            act_worker_id='w00', act_generation=1, normal_queue_limit=2)
        server = ContainerChildIpcServer(identity, socket_root=root/'control',
            owner=OwnerKey(**asdict(process)), service_epoch=base.context.service_epoch,
            service_token=base.token, max_bytes=base.max_bytes, task_port=executor, generation=1,
            close_timeout_s=2., process_owner=process)
        binding = ContainerChildBinding(ContainerOwnerKey('f'*64, '2026-10-12T01:02:03.123Z',
            base.image['digest'], 1), process, pid_namespace_inode(), str(root/'control/normal.sock'))
        client = ContainerControlClient(binding=binding, context=base.context, runtime_id=base.spec['runtime_id'],
            service_token=base.token, max_bytes=base.max_bytes, ready_probe=lambda: True)
        owner = HostOwnerDouble(base, client)
        control = ContainerTaskControl(owner=owner)
        await server.start()
        try:
            await control.start()
            starting = await control.get_status()
            assert starting.state == 'STARTING' and starting.instance_id == base.launch.launch_id
            assert executor.mark_ready() is True
            assert (await control.get_status()).state == 'READY'
            task = TaskSpec(task_id='scene-001', inputs_ref=dict(path='/act/input/task.json', sha256='a'*64),
                            deadline_monotonic_s=time.monotonic()+10)
            assert (await control.assign_task(task)).state in ('ACCEPTED', 'RUNNING', 'SUCCEEDED')
            async def terminal():
                while True:
                    status = await control.get_status('scene-001')
                    if status.task.state in ('SUCCEEDED', 'FAILED'):
                        return status
                    await asyncio.sleep(.01)
            done = await asyncio.wait_for(terminal(), 5)
            assert done.task.state == 'SUCCEEDED' and done.state == 'READY'
            document = read_task_result(output, 'scene-001')
            assert document['task_id'] == 'scene-001' and document['result']['teacher_task_result'] == 'FAILED'
            assert (output/'tasks/scene-001/task-result.json').is_file()
            stopped = await control.terminate('finished')
            assert stopped.state == 'TERMINATED' and stopped.resources_released is True
            assert await asyncio.wait_for(executor.wait_stopped(), 5) is True
            assert retirement.calls == 1 and owner.closed == 1
            assert executor.cleanup_confirmed is True and executor.cleanup_errors == []
        finally:
            await server.close()
    try:
        asyncio.run(run())
    finally:
        registry.close()
