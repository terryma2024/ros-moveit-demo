"""One local task at a time; status polling replaces Coordinator callbacks."""

import asyncio
import math
from pathlib import Path
import threading
import time

from .paths import _path
from .task_contracts import InstanceStatus, TaskRequest, TaskSpec, TaskStatus
from .task_results import write_task_result


def _positive(value):
    return (type(value) in (int, float) and math.isfinite(value) and value > 0)


def _thread_call(function, *args):
    """Run a blocking call on a daemon thread; late results after cancellation are dropped."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    future.add_done_callback(lambda done: done.cancelled() or done.exception())

    def deliver(setter, value):
        if not future.done():
            setter(value)

    def work():
        try:
            outcome = (future.set_result, function(*args))
        except BaseException as error:
            outcome = (future.set_exception, error)
        try:
            loop.call_soon_threadsafe(deliver, *outcome)
        except RuntimeError:
            pass
    threading.Thread(target=work, daemon=True).start()
    return future


class CleanupUnconfirmed(RuntimeError):
    """Helper cleanup finished without proving every named fact."""


class ContainerTaskExecutor:
    def __init__(self, *, instance_id, builder, retirement, output_root=Path('/act/output'),
                 owner_timeout_s, stop_timeout_s, retire_timeout_s, clock=time.monotonic, ready=True):
        if type(ready) is not bool:
            raise ValueError('TASK_EXECUTOR_CONFIG_INVALID')
        self._status = InstanceStatus(instance_id=instance_id, state='READY' if ready else 'STARTING')
        if (not callable(builder) or not callable(clock)
                or not _positive(owner_timeout_s) or not _positive(stop_timeout_s)
                or not _positive(retire_timeout_s)
                or not callable(getattr(retirement, 'retire', None))):
            raise ValueError('TASK_EXECUTOR_CONFIG_INVALID')
        self.output_root = _path(output_root, directory=True)
        self.builder, self.retirement = builder, retirement
        self.clock, self.owner_timeout_s = clock, owner_timeout_s
        self.stop_timeout_s, self.retire_timeout_s = stop_timeout_s, retire_timeout_s
        self._last_poll = clock()
        self._changed = asyncio.Event()
        self._stopped = asyncio.Event()
        self._closing = False
        self._tasks = {}
        self._task_status = {}
        self._current = self._execution = None
        self._build_task = self._run_task = self._stop_task = None
        self._cleanup_task = None
        self.cleanup_confirmed = False
        self.cleanup_errors = []
        self._watchdog = asyncio.create_task(self._watch())

    @property
    def closing(self):
        return self._closing

    def mark_ready(self):
        """STARTING -> READY once the native stack is proven; a stopping instance never becomes ready."""
        if self._closing or self._status.state != 'STARTING':
            return False
        self._status = self._status.model_copy(update={'state': 'READY'})
        self._changed.set()
        return True

    def _expired(self):
        now = self.clock()
        if now >= self._last_poll+self.owner_timeout_s:
            return 'Coordinator status polling timed out'
        if (self._current is not None and self._status.state == 'BUSY'
                and now >= self._current.deadline_monotonic_s):
            return 'task deadline reached'
        return None

    def _check_alive(self):
        reason = self._expired()
        if not self._closing and reason is not None:
            self._begin_stop(reason)
        if self._closing:
            raise ValueError('TASK_EXECUTOR_STOPPING')

    async def assign_task(self, task):
        if type(task) is not TaskSpec:
            raise ValueError('TASK_SPEC_REQUIRED')
        self._check_alive()
        if task.task_id in self._tasks:
            if self._tasks[task.task_id] != task:
                raise ValueError('TASK_INPUT_CHANGED')
            return self._task_status[task.task_id]
        if self._status.state != 'READY' or task.deadline_monotonic_s <= self.clock():
            raise ValueError('TASK_EXECUTOR_NOT_READY_OR_EXPIRED')
        self._tasks[task.task_id] = task
        status = TaskStatus(task_id=task.task_id, state='ACCEPTED')
        self._task_status[task.task_id] = status
        self._current = task
        self._execution = self._cleanup_task = self._build_task = None
        self._status = self._status.model_copy(update={'state': 'BUSY', 'task': status})
        self._run_task = asyncio.create_task(self._run(task))
        self._changed.set()
        return status

    async def get_status(self, task_id=None):
        if task_id is not None and task_id not in self._tasks:
            raise ValueError('TASK_ID_UNKNOWN')
        reason = self._expired()
        if reason is not None and not self._closing:
            self._begin_stop(reason)
        if not self._closing:
            self._last_poll = self.clock()
            self._changed.set()
        if task_id is not None:
            return self._status.model_copy(update={'task': self._task_status[task_id]})
        return self._status

    def _set_task(self, task, state, reason=None):
        status = TaskStatus(task_id=task.task_id, state=state, fault_reason=reason)
        self._task_status[task.task_id] = status
        if self._current is task:
            self._status = self._status.model_copy(update={'task': status})

    async def _run(self, task):
        try:
            self._check_alive()
            self._set_task(task, 'RUNNING')
            self._build_task = _thread_call(self.builder, task)
            self._execution = await asyncio.shield(self._build_task)
            self._check_alive()
            result = await _thread_call(self._execution.run)
            self._check_alive()
            if type(result) is not dict:
                raise ValueError('TASK_RESULT_REQUIRED')
            if await self._cleanup() is not True:
                raise ValueError('TASK_HELPER_CLEANUP_UNCONFIRMED')
            self._execution = self._cleanup_task = self._build_task = None
            self._check_alive()
            await _thread_call(write_task_result, self.output_root, task.task_id, result)
            self._check_alive()
            self._set_task(task, 'SUCCEEDED')
            self._status = self._status.model_copy(update={'state': 'READY'})
        except Exception as error:
            reason = (str(error) or type(error).__name__)[:300]
            if self._task_status[task.task_id].state != 'FAILED':
                self._set_task(task, 'FAILED', reason)
            if not self._closing:
                self._begin_stop(reason)
        finally:
            self._changed.set()

    def _cleanup_future(self):
        if self._execution is None:
            done = asyncio.get_running_loop().create_future()
            done.set_result(True)
            return done
        if self._cleanup_task is None:
            self._cleanup_task = _thread_call(self._execution.shutdown_owned)
        return self._cleanup_task

    async def _cleanup(self):
        return await asyncio.shield(self._cleanup_future())

    def _begin_stop(self, reason):
        self._closing = True
        self._status = self._status.model_copy(update={'state': 'STOPPING', 'fault_reason': reason})
        if self._current is not None:
            status = self._task_status[self._current.task_id]
            if status.state not in ('SUCCEEDED', 'FAILED'):
                self._set_task(self._current, 'FAILED', reason)
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._stop())
        self._changed.set()

    async def terminate(self, reason):
        TaskRequest(operation='terminate', deadline_ns=time.monotonic_ns(),
                    payload={'reason': reason})
        if self._stop_task is None:
            self._begin_stop(reason)
        await asyncio.shield(self._stop_task)
        return self._status

    async def _bounded(self, awaitable, timeout):
        future = asyncio.ensure_future(awaitable)
        done, _ = await asyncio.wait({future}, timeout=timeout)
        if not done:
            future.cancel()
            raise TimeoutError(f'timed out after {timeout}s')
        return future.result()

    async def _stop(self):
        helpers_stopped = True
        timeout = self.stop_timeout_s
        try:
            if self._build_task is not None:
                try:
                    self._execution = await self._bounded(asyncio.shield(self._build_task), timeout)
                except Exception as error:
                    helpers_stopped = False
                    self._build_task.cancel()
                    self._cleanup_error('construction', error)
            if self._execution is not None:
                try:
                    await self._bounded(_thread_call(self._execution.request_stop), timeout)
                except Exception as error:
                    helpers_stopped = False
                    self._cleanup_error('request_stop', error)
                try:
                    cleaned = await self._bounded(asyncio.shield(self._cleanup_future()), timeout)
                    helpers_stopped = cleaned is True and helpers_stopped
                    if cleaned is not True:
                        # the proofs are only in memory otherwise: name the ones that were not True
                        proofs = getattr(self._execution, 'retire_proofs', None)
                        failed = sorted(name for name, value in proofs.items() if value is not True) \
                            if isinstance(proofs, dict) else []
                        self._cleanup_error('helpers', CleanupUnconfirmed(
                            'unconfirmed proofs: ' + ', '.join(failed) if failed else 'cleanup returned no proof set'))
                except Exception as error:
                    helpers_stopped = False
                    self._cleanup_error('helpers', error)
            try:
                receipt = await self._bounded(self.retirement.retire(fenced=True),
                                              self.retire_timeout_s)
                self.cleanup_confirmed = helpers_stopped and all(receipt.get(name) is True for name in (
                    'goals_stopped', 'controllers_stopped', 'ros_children_exited', 'ros_graph_empty'))
                self.cleanup_confirmed = self.cleanup_confirmed and receipt.get('forced') is False
            except Exception as error:
                self._cleanup_error('native_retirement', error)
            if self._run_task is not None:
                done, _ = await asyncio.wait({self._run_task}, timeout=timeout)
                if not done:
                    self._run_task.cancel()
                    self.cleanup_confirmed = False
                    self._cleanup_error('run', TimeoutError(f'timed out after {timeout}s'))
        finally:
            self._stopped.set()

    def _cleanup_error(self, stage, error):
        self.cleanup_errors.append({'stage': stage, 'type': type(error).__name__,
                                    'reason': str(error)[:300]})

    async def _watch(self):
        while not self._closing:
            self._changed.clear()
            reason = self._expired()
            if reason is not None:
                self._begin_stop(reason)
                return
            deadline = self._last_poll+self.owner_timeout_s
            if self._current is not None and self._status.state == 'BUSY':
                deadline = min(deadline, self._current.deadline_monotonic_s)
            try:
                await asyncio.wait_for(self._changed.wait(), max(0., deadline-self.clock()))
            except asyncio.TimeoutError:
                pass

    async def wait_stopped(self):
        """The native shard main uses this to finish after owned cleanup."""
        await self._stopped.wait()
        return self.cleanup_confirmed
