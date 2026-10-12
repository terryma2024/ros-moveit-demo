"""Local task lifecycle with real immutable output and controlled external execution."""

import asyncio
import importlib
from pathlib import Path
import threading
import time

import pytest

from so101_demo.runtime.container_campaign.task_contracts import TaskSpec
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, read_task_result


def module():
    import so101_demo.runtime.container_campaign as package
    assert (Path(package.__file__).parent/'task_executor.py').is_file(), 'local task executor missing'
    return importlib.import_module('so101_demo.runtime.container_campaign.task_executor')


def task(task_id='task-001', deadline=None):
    return TaskSpec(task_id=task_id, inputs_ref={'path': '/act/input/task.json', 'sha256': 'a'*64},
                    deadline_monotonic_s=time.monotonic()+10 if deadline is None else deadline)


class ExternalExecution:
    def __init__(self, output, spec, *, result=None, error=None, blocked=False):
        reserve_task_output(output, spec.task_id)
        self.result = result or {'teacher_task_result': 'FAILED', 'act_data_status': 'INVALID'}
        self.error = error
        self.run_started = threading.Event()
        self.run_allowed = threading.Event()
        if not blocked:
            self.run_allowed.set()
        self.stops = self.cleanups = 0

    def run(self):
        self.run_started.set()
        assert self.run_allowed.wait(2), 'external fixture run was not released'
        if self.error is not None:
            raise self.error
        return self.result

    def request_stop(self):
        self.stops += 1
        self.run_allowed.set()

    def shutdown_owned(self):
        self.cleanups += 1
        return True


class ExternalRetirement:
    def __init__(self):
        self.calls = 0

    async def retire(self, *, fenced):
        assert fenced is True
        self.calls += 1
        return dict(goals_stopped=True, controllers_stopped=True,
                    ros_children_exited=True, ros_graph_empty=True, forced=False)


async def terminal(executor, task_id):
    async def wait():
        while True:
            status = await executor.get_status(task_id)
            if status.task.state in ('SUCCEEDED', 'FAILED'):
                return status
            await asyncio.sleep(.005)
    return await asyncio.wait_for(wait(), 2)


def test_business_failure_is_success_and_next_task_runs(tmp_path):
    executions = []
    def builder(spec):
        execution = ExternalExecution(tmp_path, spec)
        executions.append(execution)
        return execution
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
            retirement=ExternalRetirement(), output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=5.)
        try:
            assert (await executor.assign_task(task())).state == 'ACCEPTED'
            assert (await terminal(executor, 'task-001')).task.state == 'SUCCEEDED'
            assert read_task_result(tmp_path, 'task-001')['result']['teacher_task_result'] == 'FAILED'
            await executor.assign_task(task('task-002'))
            assert (await terminal(executor, 'task-002')).task.state == 'SUCCEEDED'
            assert read_task_result(tmp_path, 'task-002')['task_id'] == 'task-002'
            assert [x.cleanups for x in executions] == [1, 1]
        finally:
            await executor.terminate('fixture end')
    asyncio.run(run())


def test_qc_process_crash_is_execution_fault(tmp_path):
    retirement = ExternalRetirement()
    def builder(spec):
        return ExternalExecution(tmp_path, spec, error=RuntimeError('QC process crashed'))
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
            retirement=retirement, output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=5.)
        await executor.assign_task(task())
        status = await terminal(executor, 'task-001')
        assert status.task.state == 'FAILED' and 'QC process crashed' in status.task.fault_reason
        assert not (tmp_path/'tasks/task-001/task-result.json').exists()
        with pytest.raises(ValueError):
            await executor.assign_task(task('task-002'))
        await executor.terminate('fixture end')
        assert retirement.calls == 1
    asyncio.run(run())


def test_success_waits_for_closed_bag_and_seal(tmp_path):
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec, blocked=True)
        return execution
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
            retirement=ExternalRetirement(), output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=5.)
        try:
            await executor.assign_task(task())
            while execution is None:
                await asyncio.sleep(.005)
            assert await asyncio.to_thread(execution.run_started.wait, 1)
            assert (await executor.get_status('task-001')).task.state == 'RUNNING'
            assert not (tmp_path/'tasks/task-001/task-result.json').exists()
            # The controlled run returns only once its bag/seal boundary completes.
            execution.run_allowed.set()
            assert (await terminal(executor, 'task-001')).task.state == 'SUCCEEDED'
            assert read_task_result(tmp_path, 'task-001')['task_id'] == 'task-001'
        finally:
            if execution is not None:
                execution.run_allowed.set()
            await executor.terminate('fixture end')
    asyncio.run(run())


def test_terminate_during_builder_stops_late_helpers(tmp_path):
    building = threading.Event()
    release = threading.Event()
    execution = None
    retirement = ExternalRetirement()
    def builder(spec):
        nonlocal execution
        building.set()
        assert release.wait(2), 'builder fixture not released'
        execution = ExternalExecution(tmp_path, spec)
        return execution
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
            retirement=retirement, output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=5.)
        await executor.assign_task(task())
        assert await asyncio.to_thread(building.wait, 1)
        stop = asyncio.create_task(executor.terminate('stop during construction'))
        try:
            await asyncio.sleep(0)
            assert (await executor.get_status()).state == 'STOPPING'
        finally:
            release.set()
            await stop
        assert not execution.run_started.is_set()
        assert execution.stops == 1 and execution.cleanups == 1 and retirement.calls == 1
        assert executor.cleanup_confirmed is True
        assert not (tmp_path/'tasks/task-001/task-result.json').exists()
    asyncio.run(run())


def test_stale_status_poll_triggers_owned_stop(tmp_path):
    clock_value = [time.monotonic()]
    retirement = ExternalRetirement()
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01',
            builder=lambda spec: ExternalExecution(tmp_path, spec), retirement=retirement,
            output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=1., clock=lambda: clock_value[0])
        clock_value[0] += 2
        status = await executor.get_status()
        assert status.state == 'STOPPING'
        await executor.terminate('fixture end')
        assert retirement.calls == 1 and executor.cleanup_confirmed is True
        assert status.resources_released is False
    asyncio.run(run())


def test_task_deadline_stops_running_execution(tmp_path):
    clock_value = [time.monotonic()]
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec, blocked=True)
        return execution
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
            retirement=ExternalRetirement(), output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=5.,
            clock=lambda: clock_value[0])
        await executor.assign_task(task(deadline=clock_value[0]+1))
        while execution is None:
            await asyncio.sleep(.005)
        clock_value[0] += 2
        try:
            status = await executor.get_status('task-001')
            assert status.task.state == 'FAILED' and status.state == 'STOPPING'
            await executor.terminate('fixture end')
            assert execution.stops == 1 and execution.cleanups == 1
            assert not (tmp_path/'tasks/task-001/task-result.json').exists()
        finally:
            execution.run_allowed.set()
    asyncio.run(run())


def test_watchdog_stops_without_any_status_query(tmp_path):
    retirement = ExternalRetirement()
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01',
            builder=lambda spec: ExternalExecution(tmp_path, spec, blocked=True),
            retirement=retirement, output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=.03)
        await executor.assign_task(task())
        assert await asyncio.wait_for(executor.wait_stopped(), 1) is True
        status = await executor.get_status('task-001')
        assert status.state == 'STOPPING' and status.task.state == 'FAILED'
        assert 'polling timed out' in status.fault_reason
        assert retirement.calls == 1 and not (tmp_path/'tasks/task-001/task-result.json').exists()
    asyncio.run(run())


def test_unknown_task_query_does_not_extend_liveness(tmp_path):
    clock_value = [time.monotonic()]
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01',
            builder=lambda spec: ExternalExecution(tmp_path, spec), retirement=ExternalRetirement(),
            output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=1., clock=lambda: clock_value[0])
        clock_value[0] += .5
        with pytest.raises(ValueError, match='TASK_ID_UNKNOWN'):
            await executor.get_status('not-assigned')
        clock_value[0] += .6
        assert (await executor.get_status()).state == 'STOPPING'
        await executor.terminate('fixture end')
    asyncio.run(run())


def test_stop_exception_does_not_skip_native_retirement(tmp_path):
    retirement = ExternalRetirement()
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec, blocked=True)
        def broken_stop():
            execution.run_allowed.set()
            raise RuntimeError('stop helper failed')
        execution.request_stop = broken_stop
        return execution
    async def run():
        executor = module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
            retirement=retirement, output_root=tmp_path, stop_timeout_s=1., retire_timeout_s=1.,
            owner_timeout_s=5.)
        try:
            await executor.assign_task(task())
            await started(lambda: execution)
            result = await executor.terminate('fixture end')
            assert result.state == 'STOPPING' and result.resources_released is False
            assert executor.cleanup_confirmed is False and retirement.calls == 1
            assert execution.cleanups == 1
            assert executor.cleanup_errors[0]['stage'] == 'request_stop'
        finally:
            if execution is not None:
                execution.run_allowed.set()
    asyncio.run(run())


async def started(get):
    async def wait():
        while get() is None or not get().run_started.is_set():
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), 2)


def make(tmp_path, builder, retirement=None, **kwargs):
    options = dict(stop_timeout_s=.05, retire_timeout_s=.05, owner_timeout_s=5.)
    options.update(kwargs)
    return module().ContainerTaskExecutor(instance_id='instance-01', builder=builder,
        retirement=retirement or ExternalRetirement(), output_root=tmp_path, **options)


def stages(executor):
    return [x['stage'] for x in executor.cleanup_errors]


def test_hung_helper_shutdown_still_retires_and_stops(tmp_path):
    release = threading.Event()
    retirement = ExternalRetirement()
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec, blocked=True)
        def hung():
            execution.cleanups += 1
            release.wait(10)
            return True
        execution.shutdown_owned = hung
        return execution
    async def run():
        executor = make(tmp_path, builder, retirement)
        try:
            await executor.assign_task(task())
            await started(lambda: execution)
            await asyncio.wait_for(executor.terminate('fixture end'), 2)
            assert await asyncio.wait_for(executor.wait_stopped(), 1) is False
            assert retirement.calls == 1 and 'helpers' in stages(executor)
            assert execution.cleanups == 1
        finally:
            release.set()
            if execution is not None:
                execution.run_allowed.set()
    asyncio.run(run())


def test_hung_builder_does_not_block_stop(tmp_path):
    release = threading.Event()
    building = threading.Event()
    retirement = ExternalRetirement()
    def builder(spec):
        building.set()
        release.wait(10)
        return ExternalExecution(tmp_path, spec)
    async def run():
        executor = make(tmp_path, builder, retirement)
        try:
            await executor.assign_task(task())
            while not building.is_set():
                await asyncio.sleep(.005)
            await asyncio.wait_for(executor.terminate('fixture end'), 2)
            assert await asyncio.wait_for(executor.wait_stopped(), 1) is False
            assert retirement.calls == 1 and 'construction' in stages(executor)
            assert not (tmp_path/'tasks/task-001/task-result.json').exists()
        finally:
            release.set()
    asyncio.run(run())


def test_hung_run_does_not_block_stop(tmp_path):
    release = threading.Event()
    retirement = ExternalRetirement()
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec, blocked=True)
        execution.request_stop = lambda: setattr(execution, 'stops', execution.stops+1)
        execution.run_allowed = release
        return execution
    async def run():
        executor = make(tmp_path, builder, retirement)
        try:
            await executor.assign_task(task())
            await started(lambda: execution)
            result = await asyncio.wait_for(executor.terminate('fixture end'), 2)
            assert await asyncio.wait_for(executor.wait_stopped(), 1) is False
            assert result.task.state == 'FAILED' and retirement.calls == 1
            assert 'run' in stages(executor)
            assert not (tmp_path/'tasks/task-001/task-result.json').exists()
        finally:
            release.set()
    asyncio.run(run())


def test_hung_retirement_is_bounded(tmp_path):
    class HungRetirement:
        calls = 0
        async def retire(self, *, fenced):
            self.calls += 1
            await asyncio.Event().wait()
    retirement = HungRetirement()
    async def run():
        executor = make(tmp_path, lambda spec: ExternalExecution(tmp_path, spec), retirement)
        await executor.assign_task(task())
        assert (await terminal(executor, 'task-001')).task.state == 'SUCCEEDED'
        await asyncio.wait_for(executor.terminate('fixture end'), 2)
        assert await asyncio.wait_for(executor.wait_stopped(), 1) is False
        assert retirement.calls == 1 and 'native_retirement' in stages(executor)
    asyncio.run(run())


def test_stuck_helper_thread_does_not_block_loop_shutdown(tmp_path):
    release = threading.Event()
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec, blocked=True)
        execution.shutdown_owned = lambda: release.wait(10)
        return execution
    async def run():
        executor = make(tmp_path, builder)
        await executor.assign_task(task())
        await started(lambda: execution)
        await asyncio.wait_for(executor.terminate('fixture end'), 2)
    begin = time.monotonic()
    try:
        asyncio.run(run())
        elapsed = time.monotonic()-begin
    finally:
        release.set()
        if execution is not None:
            execution.run_allowed.set()
    assert elapsed < 3


def test_terminate_after_success_does_not_restop_completed_execution(tmp_path):
    retirement = ExternalRetirement()
    execution = None
    def builder(spec):
        nonlocal execution
        execution = ExternalExecution(tmp_path, spec)
        return execution
    async def run():
        executor = make(tmp_path, builder, retirement)
        await executor.assign_task(task())
        assert (await terminal(executor, 'task-001')).task.state == 'SUCCEEDED'
        await executor.terminate('fixture end')
        assert execution.stops == 0 and execution.cleanups == 1
        assert retirement.calls == 1 and executor.cleanup_confirmed is True
        assert executor.cleanup_errors == []
    asyncio.run(run())


def test_second_assignment_terminate_does_not_reclean_first_execution(tmp_path):
    release = threading.Event()
    executions = []
    def builder(spec):
        if executions:
            release.wait(10)
        execution = ExternalExecution(tmp_path, spec)
        executions.append(execution)
        return execution
    async def run():
        executor = make(tmp_path, builder, stop_timeout_s=1.)
        try:
            await executor.assign_task(task())
            assert (await terminal(executor, 'task-001')).task.state == 'SUCCEEDED'
            await executor.assign_task(task('task-002'))
            stop = asyncio.create_task(executor.terminate('fixture end'))
            await asyncio.sleep(.02)
            release.set()
            await asyncio.wait_for(stop, 3)
            assert executions[0].cleanups == 1 and executions[0].stops == 0
        finally:
            release.set()
    asyncio.run(run())


@pytest.mark.parametrize('name', ['stop_timeout_s', 'retire_timeout_s'])
@pytest.mark.parametrize('value', [True, 0, -1, float('inf'), float('nan'), '1'])
def test_stop_timeouts_must_be_valid(tmp_path, name, value):
    async def run():
        with pytest.raises(ValueError, match='TASK_EXECUTOR_CONFIG_INVALID'):
            make(tmp_path, lambda spec: None, **{name: value})
    asyncio.run(run())


@pytest.mark.parametrize('name', ['stop_timeout_s', 'retire_timeout_s'])
def test_stop_timeouts_are_required(tmp_path, name):
    kwargs = dict(stop_timeout_s=1., retire_timeout_s=1., owner_timeout_s=5.)
    del kwargs[name]
    async def run():
        with pytest.raises(TypeError):
            module().ContainerTaskExecutor(instance_id='instance-01', builder=lambda spec: None,
                retirement=ExternalRetirement(), output_root=tmp_path, **kwargs)
    asyncio.run(run())
