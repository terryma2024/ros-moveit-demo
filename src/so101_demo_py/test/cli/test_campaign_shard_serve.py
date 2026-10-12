"""The shard main loop: real executor, control server, sockets, spec loader and durable writers.

Controlled doubles (no ROS, Docker or container): the native stack, its readiness probe and native retirement.
"""

import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import threading
import time

from test_campaign_shard import fixture


class StackDouble:
    """Controlled native stack: start() blocks until released."""

    def __init__(self):
        self.release = asyncio.Event()
        self.timeouts = []
        self.finished = False

    async def start(self, *, timeout_s):
        self.timeouts.append(timeout_s)
        await self.release.wait()
        self.finished = True


class ReadyDouble:
    """Controlled readiness probe."""

    readiness_bytes = b'{"ready":true}\n'


class RetirementDouble:
    """Controlled native retirement; records whether the stack start had settled when it ran."""

    def __init__(self, stack, *, forced=False):
        self.stack, self.forced, self.calls = stack, forced, []

    async def retire(self, *, fenced):
        assert fenced is True
        self.calls.append(self.stack.finished)
        return dict(goals_stopped=True, controllers_stopped=True, ros_children_exited=True,
                    ros_graph_empty=True, forced=self.forced)


def shard_parts(tmp_path, **retirement):
    from so101_demo.runtime.container_campaign.process_identity import read_process_owner
    mod = importlib.import_module('so101_demo.cli.campaign_shard')
    path, _document = fixture(tmp_path)
    spec, runtime = mod.load_spec(path)
    (Path(spec['owned_root'])/'tmp').mkdir()
    stack = StackDouble()
    arguments = dict(process=read_process_owner(os.getpid()), stack=stack, ready=ReadyDouble(),
        retirement=RetirementDouble(stack, **retirement), socket_root=Path(spec['owned_root'])/'control')
    return mod, spec, runtime, stack, arguments


async def control_call(root, operation, payload):
    from so101_demo.runtime.inference.codec import open_socket_parent
    from so101_demo.runtime.parallel_ipc.frames import transport_address
    socket_path = root/'control/normal.sock'
    fd = open_socket_parent(socket_path)
    try:
        reader, writer = await asyncio.open_unix_connection(transport_address(socket_path, fd))
        writer.write(json.dumps(dict(operation=operation, payload=payload,
            deadline_ns=time.monotonic_ns()+5_000_000_000)).encode()+b'\n')
        await writer.drain()
        reply = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return reply
    finally:
        os.close(fd)


async def wait_for(condition):
    async def poll():
        while not condition():
            await asyncio.sleep(.01)
    await asyncio.wait_for(poll(), 5)


def test_status_is_starting_until_native_readiness(tmp_path):
    mod, spec, runtime, stack, arguments = shard_parts(tmp_path)
    root = Path(spec['owned_root'])
    async def run():
        shard = asyncio.create_task(mod.serve_shard(spec, runtime, install_signals=False, **arguments))
        await wait_for(lambda: (root/'control/child-ready.json').exists() and stack.timeouts)
        starting = await control_call(root, 'get_status', dict(task_id=None))
        assert starting['accepted'] is True and starting['result']['state'] == 'STARTING'
        assert starting['result']['instance_id'] == 'wave-00-w00-g1'
        task = dict(task_id='task-001', inputs_ref=dict(path='/act/input/t.json', sha256='a'*64),
                    deadline_monotonic_s=time.monotonic()+5)
        refused = await control_call(root, 'assign_task', task)
        assert refused['accepted'] is False and refused['code'] == 'TASK_EXECUTOR_NOT_READY_OR_EXPIRED'
        assert not (root/'runtime-ready.json').exists() and not (root/'stack-readiness.json').exists()
        stack.release.set()
        await wait_for(lambda: (root/'stack-readiness.json').exists())
        ready = json.loads((root/'runtime-ready.json').read_text())
        assert ready['kind'] == 'ACT_SHARD_RUNTIME_READY' and ready['generation'] == 1
        assert ready['readiness_sha256'] == hashlib.sha256(ReadyDouble.readiness_bytes).hexdigest()
        assert (root/'stack-readiness.json').read_bytes() == ReadyDouble.readiness_bytes
        async def ready_state():
            while (await control_call(root, 'get_status', dict(task_id=None)))['result']['state'] != 'READY':
                await asyncio.sleep(.01)
        await asyncio.wait_for(ready_state(), 5)
        stopped = await control_call(root, 'terminate', dict(reason='test end'))
        assert stopped['result']['state'] == 'STOPPING'
        return await asyncio.wait_for(shard, 5)
    assert asyncio.run(run()) == 0
    assert stack.timeouts == [runtime.initializing_hard_timeout_s]


def test_main_exits_after_executor_stop(tmp_path, monkeypatch):
    mod, spec, runtime, stack, arguments = shard_parts(tmp_path)
    root = Path(spec['owned_root'])
    stack.release.set()
    async def fake_run_shard(loaded_spec, loaded_runtime):
        return await mod.serve_shard(loaded_spec, loaded_runtime, install_signals=False, **arguments)
    monkeypatch.setattr(mod, 'run_shard', fake_run_shard)
    async def stop_it():
        await wait_for(lambda: (root/'stack-readiness.json').exists())
        return await control_call(root, 'terminate', dict(reason='finished'))
    holder = {}
    thread = threading.Thread(target=lambda: holder.update(reply=asyncio.run(stop_it())))
    thread.start()
    assert mod.main(['--spec', str(tmp_path/'shard.json')]) == 0
    thread.join(5)
    assert holder['reply']['accepted'] is True
    assert json.loads((root/'instance-exit.json').read_text()) == dict(schema_version=1,
        kind='ACT_SHARD_INSTANCE_EXIT', state='STOPPING', fault_reason='finished', task=None,
        cleanup_confirmed=True, cleanup_errors=[])


def test_forced_retirement_exits_nonzero_and_records_unconfirmed_cleanup(tmp_path):
    mod, spec, runtime, stack, arguments = shard_parts(tmp_path, forced=True)
    root = Path(spec['owned_root'])
    stack.release.set()
    async def run():
        shard = asyncio.create_task(mod.serve_shard(spec, runtime, install_signals=False, **arguments))
        await wait_for(lambda: (root/'stack-readiness.json').exists())
        await control_call(root, 'terminate', dict(reason='finished'))
        return await asyncio.wait_for(shard, 5)
    assert asyncio.run(run()) == 1
    assert json.loads((root/'instance-exit.json').read_text())['cleanup_confirmed'] is False


def test_sigterm_terminates_executor_and_writes_instance_exit(tmp_path):
    mod, spec, runtime, stack, arguments = shard_parts(tmp_path)
    root = Path(spec['owned_root'])
    retirement = arguments['retirement']
    async def run():
        shard = asyncio.create_task(mod.serve_shard(spec, runtime, **arguments))
        await wait_for(lambda: stack.timeouts)
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(.2)
        # Retirement waits for the in-flight stack start before it runs.
        assert retirement.calls == [] and not shard.done()
        stack.release.set()
        return await asyncio.wait_for(shard, 5)
    assert asyncio.run(run()) == 0
    assert retirement.calls == [True]
    document = json.loads((root/'instance-exit.json').read_text())
    assert document['fault_reason'] == 'SIGTERM' and document['state'] == 'STOPPING'
    assert document['cleanup_confirmed'] is True and document['cleanup_errors'] == []
    assert not (root/'runtime-ready.json').exists()
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_executor_budgets_come_from_frozen_runtime_config(tmp_path, monkeypatch):
    from so101_demo.runtime.container_campaign import task_executor
    seen = {}
    class Recording(task_executor.ContainerTaskExecutor):
        def __init__(self, **arguments):
            seen.update(arguments)
            super().__init__(**arguments)
    monkeypatch.setattr(task_executor, 'ContainerTaskExecutor', Recording)
    mod, spec, runtime, stack, arguments = shard_parts(tmp_path)
    root = Path(spec['owned_root'])
    stack.release.set()
    async def run():
        shard = asyncio.create_task(mod.serve_shard(spec, runtime, install_signals=False, **arguments))
        await wait_for(lambda: (root/'stack-readiness.json').exists())
        await control_call(root, 'terminate', dict(reason='finished'))
        await asyncio.wait_for(shard, 5)
    asyncio.run(run())
    assert seen['instance_id'] == 'wave-00-w00-g1' and seen['ready'] is False
    assert seen['owner_timeout_s'] == runtime.heartbeat_timeout_s
    assert seen['stop_timeout_s'] == seen['retire_timeout_s'] == runtime.worker_recovery_timeout_s
    assert callable(seen['builder'])
