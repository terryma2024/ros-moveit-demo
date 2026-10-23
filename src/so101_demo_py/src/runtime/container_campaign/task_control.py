"""Coordinator-side four-operation adapter for one owned container."""

import asyncio
import time

from .task_contracts import InstanceStatus, TaskRequest, TaskSpec, TaskStatus


class ContainerTaskControl:
    def __init__(self, *, owner):
        self.owner = owner
        self.instance_id = owner.launch.launch_id
        self._status = InstanceStatus(instance_id=self.instance_id, state='STARTING')
        self._started = self._closing = False
        self._stop_task = None
        self._prove_lock = asyncio.Lock()
        self._tasks = {}

    async def start(self):
        if self._started or self._closing:
            raise ValueError('TASK_INSTANCE_ALREADY_STARTED')
        self._started = True
        try:
            await self.owner.start()
        except BaseException:
            self._closing = True
            raise
        self._status = InstanceStatus(instance_id=self.instance_id, state='READY')
        return self._status

    def _request(self, operation, payload):
        budget = getattr(self.owner, 'status_budget', self.owner.startup_budget)
        deadline = min(time.monotonic()+budget, self.owner.context.deadline_monotonic_s)
        packet = TaskRequest(operation=operation, deadline_ns=int(deadline*1e9), payload=payload)
        packet.check_deadline(time.monotonic_ns())
        return packet

    async def assign_task(self, task):
        if type(task) is not TaskSpec:
            raise ValueError('TASK_SPEC_REQUIRED')
        if not self._started or self._closing or self._status.state not in ('READY', 'BUSY'):
            raise ValueError('TASK_INSTANCE_NOT_READY')
        if task.deadline_monotonic_s > self.owner.context.deadline_monotonic_s:
            raise ValueError('TASK_DEADLINE_OUTSIDE_CAMPAIGN')
        previous = self._tasks.get(task.task_id)
        if previous is not None:
            if previous != task:
                raise ValueError('TASK_INPUT_CHANGED')
            status = await self.get_status(task.task_id)
            if status.task is None:
                raise ValueError('TASK_STATUS_MISSING')
            return status.task
        if self._status.state == 'BUSY':
            raise ValueError('TASK_INSTANCE_BUSY')
        packet = self._request('assign_task', task.model_dump())
        # Record intent before sending. An uncertain exchange can only be queried.
        self._tasks[task.task_id] = task
        self._status = InstanceStatus(instance_id=self.instance_id, state='BUSY',
            task=TaskStatus(task_id=task.task_id, state='ACCEPTED'))
        response = await self.owner.control_client().call_task(packet)
        status = TaskStatus.model_validate(response)
        if status.task_id != task.task_id:
            raise ValueError('TASK_ID_MISMATCH')
        self._status = self._status.model_copy(update={'task': status})
        return status

    async def get_status(self, task_id=None):
        if self._closing:
            if task_id is not None and (self._status.task is None or self._status.task.task_id != task_id):
                raise ValueError('TASK_ID_MISMATCH')
            if self._stop_task is not None and self._stop_task.done():
                await self._reprove()
            return self._status
        if not self._started:
            raise ValueError('TASK_INSTANCE_NOT_STARTED')
        packet = self._request('get_status', dict(task_id=task_id))
        response = await self.owner.control_client().call_task(packet)
        status = InstanceStatus.model_validate(response)
        if status.instance_id != self.instance_id:
            raise ValueError('TASK_INSTANCE_MISMATCH')
        if task_id is not None and (status.task is None or status.task.task_id != task_id):
            raise ValueError('TASK_ID_MISMATCH')
        # Only the Host owner can prove that the original container has exited.
        if status.state == 'TERMINATED':
            status = status.model_copy(update={'state': 'STOPPING', 'resources_released': False})
        self._status = status
        return status

    async def terminate(self, reason):
        # Validate the reason without using an already-expired execution deadline.
        TaskRequest(operation='terminate', deadline_ns=time.monotonic_ns(),
                    payload=dict(reason=reason))
        self._closing = True
        first = self._stop_task is None
        if first:
            self._stop_task = asyncio.create_task(self._terminate(reason))
        status = await asyncio.shield(self._stop_task)
        if not first:
            status = await self._reprove()
        return status

    def _released(self, receipt):
        return (type(receipt) is dict and receipt.get('terminated') is True
                and receipt.get('launch_id') == self.instance_id)

    async def _terminate(self, reason):
        self._status = self._status.model_copy(update={'state': 'STOPPING',
            'resources_released': False})
        try:
            packet = self._request('terminate', dict(reason=reason))
            await self.owner.control_client().call_task(packet)
        except Exception:
            # Socket loss cannot prevent cleanup of the registered Docker owner.
            pass
        receipt = await self.owner.close()
        released = self._released(receipt)
        await self._adopt_fault(reason)
        self._status = self._status.model_copy(update={
            'state': 'TERMINATED' if released else 'STOPPING', 'resources_released': released})
        return self._status

    async def _adopt_fault(self, reason):
        """A fault the Host never polled comes from the child's own exit record, else from the terminate reason."""
        if self._status.fault_reason is not None:
            return
        read = getattr(self.owner, 'instance_exit', None)
        record = await asyncio.to_thread(read) if callable(read) else None
        fault = record.get('fault_reason') if type(record) is dict else None
        fault = fault if type(fault) is str and fault else reason[:300]
        self._status = self._status.model_copy(update={'fault_reason': fault})

    async def _reprove(self):
        """A late exit can still be proven by the original owner; no signal is sent here."""
        prove = getattr(self.owner, 'prove_stopped', None)
        if not callable(prove):
            return self._status
        async with self._prove_lock:
            if self._status.resources_released:
                return self._status
            if self._released(await prove()):
                self._status = self._status.model_copy(update={'state': 'TERMINATED', 'resources_released': True})
            return self._status
