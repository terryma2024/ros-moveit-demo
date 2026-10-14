"""Concurrent container waves: one Host-local loop per instance over four-operation task control.

The Host assigns one task at a time, polls status (which is also the container's liveness signal),
and registers a result only after a matching SUCCEEDED status. No lease, proof or replay protocol
exists here; a lost reply is queried, never resent, and any fault ends that instance only.
"""

import asyncio
import hashlib
import math
from pathlib import Path
import re
import time

from so101_demo.act.parallel_collection import reserve_qualification_scenes
from so101_demo.runtime.container_campaign.paths import host_task_output
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_demo.runtime.container_campaign.task_contracts import TASK_ID_PATTERN, InputRef, TaskSpec
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl
from so101_demo.runtime.container_campaign.task_journal import (
    ContainerTaskJournal, read_container_task_result,
)
from so101_demo.parallel_batch.contracts.linux_cuda import ParallelRuntimeConfigLinuxCuda
from so101_demo.runtime.inference.config import validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.contracts import AdmittedCampaignContext

TASK_INPUT_KIND = 'ACT_CONTAINER_COLLECTION_TASK'
PENDING, ASSIGNED, COLLECTED, FAULTED = 'PENDING', 'ASSIGNED', 'COLLECTED', 'FAULTED'
_REFUSED = ('TASK_ID_UNKNOWN', 'TASK_ID_MISMATCH')


def task_id_for(wave_id, worker_id, scene_id):
    return f'{wave_id}-{worker_id}-{scene_id}'


class WaveAssignment:
    """Which scene a worker may take next. Reserved scenes come first, then surplus; nothing is retried."""

    def __init__(self, *, scene_ids, worker_ids, assignment=None):
        scene_ids, worker_ids = tuple(scene_ids), tuple(worker_ids)
        if not scene_ids or len(set(scene_ids)) != len(scene_ids) or not worker_ids:
            raise ValueError('WAVE_ASSIGNMENT_INVALID')
        self.scene_ids, self.worker_ids = scene_ids, worker_ids
        self.states = {scene: PENDING for scene in scene_ids}
        self.reserved = self.surplus = None
        if assignment is not None:
            try:
                reserved = {worker: tuple(values) for worker, values in assignment['reserved_by_worker'].items()}
                surplus = tuple(assignment['surplus'])
                flat = [scene for values in reserved.values() for scene in values]+list(surplus)
                if (set(reserved) != set(worker_ids) or sorted(flat) != sorted(scene_ids)):
                    raise ValueError('coverage')
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                raise ValueError('WAVE_ASSIGNMENT_INVALID') from error
            self.reserved, self.surplus = reserved, surplus

    def next_scene(self, worker_id):
        """Claim the next scene for a worker (marking it ASSIGNED), or None."""
        if worker_id not in self.worker_ids:
            raise ValueError('WAVE_ASSIGNMENT_WORKER_UNKNOWN')
        scene = self._choose(worker_id)
        if scene is not None:
            self.states[scene] = ASSIGNED
        return scene

    def _choose(self, worker_id):
        if self.reserved is None:
            return next((scene for scene in self.scene_ids if self.states[scene] == PENDING), None)
        for scene in self.reserved[worker_id]:
            if self.states[scene] != COLLECTED:
                return scene if self.states[scene] == PENDING else None
        return next((scene for scene in self.surplus if self.states[scene] == PENDING), None)

    def has_next(self, worker_id):
        """Whether `next_scene` would claim a scene for this worker right now; claims nothing."""
        if worker_id not in self.worker_ids:
            raise ValueError('WAVE_ASSIGNMENT_WORKER_UNKNOWN')
        return self._choose(worker_id) is not None

    def _move(self, scene, state):
        if self.states.get(scene) != ASSIGNED:
            raise ValueError('WAVE_ASSIGNMENT_STATE_INVALID')
        self.states[scene] = state

    def mark_collected(self, scene):
        self._move(scene, COLLECTED)

    def mark_faulted(self, scene):
        self._move(scene, FAULTED)


class InstanceFault(RuntimeError):
    pass


class RecordingGate:
    """Limits when the Host may send an assignment: recording slots, tasks in flight and the gap between assignments.

    Three independent limits, all of which must hold; each is optional (None: no such limit).
    - `cap`: instances in the recording part of a task. An instance is in it from the moment the Host claims a scene for it
      until its polled status reports that its recorder has stopped, or its task has ended or its instance has faulted or
      finished. A status without a phase counts as recording until the task ends.
    - `max_in_flight`: instances with a task between the claim and the task's end, in every phase.
    - `min_gap_s`: Host monotonic seconds between two assignment sends, across all instances. The gap is measured from the
      send, and no claim is made while another claimed assignment has not been sent yet, so two sends are never closer.
    The gate only delays when the Host sends an assignment; which scene a worker gets is still decided by `WaveAssignment`.
    Everything runs on the Host event loop, so a check and the claim that follows it cannot interleave with another
    instance's."""

    def __init__(self, cap, max_in_flight=None, min_gap_s=None, clock=time.monotonic):
        self.cap, self.max_in_flight, self.min_gap_s, self.clock = cap, max_in_flight, min_gap_s, clock
        self.members, self.last_sent = [], None
        self._pulse = asyncio.Event()

    def blocked(self):
        """True while a count limit or an unsent claim prevents a new claim; the next pulse may change that."""
        if any(member.claiming() for member in self.members):
            return True
        if self.cap is not None and sum(1 for member in self.members if member.in_recording_part()) >= self.cap:
            return True
        return (self.max_in_flight is not None
                and sum(1 for member in self.members if member.in_flight()) >= self.max_in_flight)

    def gap_remaining(self):
        """Seconds until the minimum gap since the last send has elapsed (0. if none or none required)."""
        if self.min_gap_s is None or self.last_sent is None:
            return 0.
        return max(0., self.last_sent+self.min_gap_s-self.clock())

    def sent(self):
        self.last_sent = self.clock()

    def pulse(self):
        pulse, self._pulse = self._pulse, asyncio.Event()
        pulse.set()

    async def changed(self):
        await self._pulse.wait()


class InstanceDispatch:
    """The per-instance loop. `control` has the four-operation `ContainerTaskControl` shape."""

    def __init__(self, *, control, shard, assignment, journal, endpoints, scene_manifest, case_inputs,
                 config, context, dispatch_allowed, clock=time.monotonic, sleep=asyncio.sleep, gate=None):
        launch = shard.launch
        self.gate, self.recording_claim, self.done, self.unsent = gate, False, False, False
        self.control, self.shard, self.assignment, self.journal = control, shard, assignment, journal
        self.endpoints, self.scene_manifest, self.case_inputs = endpoints, scene_manifest, case_inputs
        self.config, self.context, self.dispatch_allowed = config, context, dispatch_allowed
        self.clock, self.sleep = clock, sleep
        self.launch_id, self.worker_id, self.wave_id = launch.launch_id, launch.worker_id, launch.wave_id
        self.generation, self.owner_root = launch.launch_generation, Path(launch.owned_root)
        self.status = self.fault = self.error = None
        self.current = self.polling = None
        self.collected = []
        self._poller = None
        self._pulse = asyncio.Event()

    def task_id(self, scene_id):
        return task_id_for(self.wave_id, self.worker_id, scene_id)

    # Status polling doubles as the container's liveness signal: it runs from start to terminate.
    async def _poll(self):
        last_ok = None
        interval, limit = self.config.heartbeat_interval_s, self.config.heartbeat_timeout_s
        while True:
            try:
                status = await asyncio.wait_for(self.control.get_status(self.polling), limit)
                last_ok = self.clock()
                self.status = status
                if status.state in ('STOPPING', 'TERMINATED') or status.fault_reason:
                    self.fault = 'CONTAINER_INSTANCE_REPORTED_FAULT: '+str(status.fault_reason or status.state)
            except Exception as error:
                if self.polling is not None and any(code in str(error) for code in _REFUSED):
                    self.fault = 'CONTAINER_STATUS_QUERY_REFUSED: '+str(error)[:200]
                elif last_ok is not None and self.clock()-last_ok >= limit:
                    self.fault = 'CONTAINER_INSTANCE_UNREACHABLE: '+(str(error) or type(error).__name__)[:200]
            finally:
                self._tick()
            if self.fault is not None:
                return
            await self.sleep(interval)

    def _tick(self):
        pulse, self._pulse = self._pulse, asyncio.Event()
        pulse.set()
        if self.gate is not None:
            self.gate.pulse()

    def _seen_current(self):
        seen = None if self.status is None else self.status.task
        if self.current is not None and seen is not None and seen.task_id == self.current[0].task_id:
            return seen
        return None

    def in_flight(self):
        """Whether this instance has a claimed task that has not ended: every phase, from the claim to the task's end."""
        if self.done or self.fault is not None or not self.recording_claim:
            return False
        seen = self._seen_current()
        return seen is None or seen.state not in ('SUCCEEDED', 'FAILED')

    def in_recording_part(self):
        """Whether this instance still occupies one of the gate's recording slots."""
        if not self.in_flight():
            return False
        seen = self._seen_current()
        return seen is None or seen.phase != 'POST_RECORDING'

    def claiming(self):
        """Whether a claimed assignment has not been sent yet (it is being prepared or journaled)."""
        return self.unsent and not self.done and self.fault is None

    async def _claim_scene(self, stop_reason):
        """The next scene for this worker, once the gate allows an assignment; None when there is nothing to do or to dispatch."""
        while True:
            if not self.dispatch_allowed() or stop_reason() is not None or self.fault is not None:
                return None
            if not self.assignment.has_next(self.worker_id):
                return None
            if self.gate.blocked():
                await self.gate.changed()
                continue
            remaining = self.gate.gap_remaining()
            if remaining > 0:
                # bounded so a stop or a fault is noticed within one heartbeat
                await self.sleep(min(remaining, self.config.heartbeat_interval_s))
                continue
            self.recording_claim = self.unsent = True
            return self.assignment.next_scene(self.worker_id)

    async def _wait(self):
        pulse = self._pulse
        if self._poller.done():
            await asyncio.sleep(0)
        else:
            await pulse.wait()

    async def start(self):
        """Start the instance and wait until a polled status says READY, within the initializing bound."""
        began = self.clock()
        self._poller = asyncio.create_task(self._poll())
        starting = asyncio.create_task(self.control.start())
        try:
            while True:
                if starting.done():
                    starting.result()
                    if self.fault is None and self.status is not None and self.status.state == 'READY':
                        return
                if self.fault is not None:
                    raise InstanceFault(self.fault)
                if self.clock()-began >= self.config.initializing_hard_timeout_s:
                    raise InstanceFault('CONTAINER_INSTANCE_READY_TIMEOUT')
                await self._wait()
        finally:
            if not starting.done():
                starting.cancel()
                await asyncio.gather(starting, return_exceptions=True)

    def prepare_task(self, scene_id):
        """Write the closed task input document with the durable primitive; return the TaskSpec."""
        task_id = self.task_id(scene_id)
        refs = self.case_inputs[scene_id]
        document = dict(schema_version=1, kind=TASK_INPUT_KIND, task_id=task_id, worker_id=self.worker_id,
            launch_generation=self.generation, wave_id=self.wave_id, scene_id=scene_id,
            scene_manifest=dict(self.scene_manifest), scope=dict(refs['scope']),
            inputs_manifest=dict(refs['inputs_manifest']))
        for role in ('teacher',):
            endpoint = self.endpoints[role]
            document[role] = dict(role=role, socket_path=str(self.shard.teacher_socket),
                service_generation=endpoint.service_generation, max_frame_bytes=endpoint.max_frame_bytes)
        config = self.config
        now = self.clock()
        deadline = min(now+config.initializing_hard_timeout_s+config.executing_hard_timeout_s
                       +config.finalizing_hard_timeout_s+config.worker_recovery_timeout_s,
                       self.context.deadline_monotonic_s)
        if deadline <= now:
            raise InstanceFault('CONTAINER_CAMPAIGN_DEADLINE_EXPIRED')
        path = self.owner_root/'task-inputs'/(task_id+'.json')
        _write(path, document)
        digest = hashlib.sha256(canonical_json(document)+b'\n').hexdigest()
        return TaskSpec(task_id=task_id, inputs_ref=InputRef(path=str(path), sha256=digest),
                        deadline_monotonic_s=deadline)

    async def _run_task(self, scene):
        task = await asyncio.to_thread(self.prepare_task, scene)
        output = host_task_output(self.owner_root, task.task_id)
        await asyncio.to_thread(self.journal.assign, instance_id=self.launch_id, task=task, host_output=output)
        self.current = (task, scene)
        if self.gate is not None:
            self.gate.sent()
            self.unsent = False
            self.gate.pulse()
        try:
            await self.control.assign_task(task)
        except Exception:
            # An uncertain exchange is only ever queried, never repeated.
            pass
        self.polling = task.task_id
        backstop = task.deadline_monotonic_s+self.config.heartbeat_timeout_s
        while True:
            if self.fault is not None:
                raise InstanceFault(self.fault)
            seen = self.status.task if self.status is not None else None
            if seen is not None and seen.task_id == task.task_id:
                if seen.state == 'FAILED':
                    raise InstanceFault('CONTAINER_TASK_FAILED: '+str(seen.fault_reason))
                if seen.state == 'SUCCEEDED':
                    break
            if self.clock() >= backstop:
                raise InstanceFault('CONTAINER_TASK_DEADLINE_EXCEEDED')
            await self._wait()
        try:
            result = await asyncio.to_thread(read_container_task_result, self.owner_root, task_id=task.task_id)
            await asyncio.to_thread(self.journal.collect, task_id=task.task_id, result=result)
        except ValueError as error:
            raise InstanceFault('CONTAINER_TASK_RESULT_UNREGISTERED: '+str(error)) from error
        self.assignment.mark_collected(scene)
        self.collected.append(task.task_id)
        self.current = None
        self.recording_claim = False
        if self.gate is not None:
            self.gate.pulse()

    async def run(self, stop_reason):
        """Dispatch scenes until none remain, dispatch is fenced or the instance faults; then terminate it."""
        reason = None
        try:
            while self.dispatch_allowed() and stop_reason() is None and self.fault is None:
                scene = (self.assignment.next_scene(self.worker_id) if self.gate is None
                         else await self._claim_scene(stop_reason))
                if scene is None:
                    break
                try:
                    await self._run_task(scene)
                except Exception:
                    self.assignment.mark_faulted(scene)
                    raise
            reason = self.fault
        except InstanceFault as fault:
            reason = str(fault)
        except Exception as error:
            reason = f'CONTAINER_TASK_DISPATCH_ERROR: {type(error).__name__}: {error}'
        if reason is not None:
            await self._record_fault(reason)
        return await self.finish('WAVE_COMPLETE' if reason is None else reason)

    async def _record_fault(self, reason):
        self.error = dict(type='InstanceFault', reason=reason[:300], worker_id=self.worker_id,
                          launch_id=self.launch_id, task_id=None if self.current is None else self.current[0].task_id)
        if self.current is not None:
            try:
                await asyncio.to_thread(self.journal.fail, task_id=self.current[0].task_id, reason=reason)
            except ValueError as error:
                self.error['journal_error'] = str(error)[:200]

    async def finish(self, reason):
        """Stop polling, then terminate this instance and nothing else."""
        self.done = True
        if self.gate is not None:
            self.gate.pulse()
        if self._poller is not None:
            self._poller.cancel()
            await asyncio.gather(self._poller, return_exceptions=True)
        try:
            status = await self.control.terminate(reason[:300])
        except Exception as error:
            self.error = self.error or dict(type='InstanceFault', reason='CONTAINER_INSTANCE_TERMINATE_FAILED: '
                +str(error)[:200], worker_id=self.worker_id, launch_id=self.launch_id, task_id=None)
            return None
        if not status.resources_released and self.error is None:
            self.error = dict(type='InstanceFault', reason='CONTAINER_INSTANCE_STOP_UNCONFIRMED',
                              worker_id=self.worker_id, launch_id=self.launch_id, task_id=None)
        return status


class ConcurrentCollectionCoordinator:
    def __init__(self, *, context, config, case_inputs, scene_manifest, control_factory=None,
                 clock=time.monotonic, sleep=asyncio.sleep, max_recording_shards=None,
                 max_tasks_in_flight=None, min_assignment_gap_s=None):
        if (type(context) is not AdmittedCampaignContext or context.workload_kind != 'act_collection_start'
                or type(config) is not ParallelRuntimeConfigLinuxCuda
                or type(case_inputs) is not dict or not case_inputs or type(scene_manifest) is not dict
                or not callable(clock) or not callable(sleep)
                or (control_factory is not None and not callable(control_factory))
                or (max_recording_shards is not None
                    and (type(max_recording_shards) is not int or max_recording_shards < 1))
                or (max_tasks_in_flight is not None
                    and (type(max_tasks_in_flight) is not int or max_tasks_in_flight < 1))
                or (min_assignment_gap_s is not None
                    and (type(min_assignment_gap_s) not in (int, float) or not math.isfinite(min_assignment_gap_s)
                         or min_assignment_gap_s < 0))):
            raise ValueError('CONTAINER_COORDINATOR_CONFIG_INVALID')
        for refs in case_inputs.values():
            if type(refs) is not dict or set(refs) != {'scope', 'inputs_manifest'}:
                raise ValueError('CONTAINER_COORDINATOR_CONFIG_INVALID')
        self.context, self.config, self.case_inputs = context, config, case_inputs
        self.scene_manifest = scene_manifest
        self.max_recording_shards = max_recording_shards
        self.max_tasks_in_flight, self.min_assignment_gap_s = max_tasks_in_flight, min_assignment_gap_s
        self.control_factory = control_factory or (lambda shard: ContainerTaskControl(owner=shard))
        self.clock, self.sleep = clock, sleep
        self.active = None
        self.stop_reason = None
        self.waves = {}

    def stop_dispatch(self, reason):
        if type(reason) is not str or not reason:
            raise ValueError('CONTAINER_DISPATCH_STOP_REASON_INVALID')
        if self.stop_reason is None:
            self.stop_reason = reason

    async def run_wave(self, *, plan, shards, endpoints, dispatch_allowed):
        if self.stop_reason is not None or self.active is not None or not dispatch_allowed():
            raise ValueError('CONTAINER_WAVE_DISPATCH_FENCED')
        if type(shards) is not tuple or len(shards) != self.context.worker_count:
            raise ValueError('CONTAINER_WAVE_SHARD_COUNT_INVALID')
        wave = plan['wave_index']
        root = shards[0].root.parents[2]/'host'/('wave-'+str(wave))
        if str(root.parents[1]) != self.context.evidence_root or wave in self.waves:
            raise ValueError('CONTAINER_WAVE_ROOT_INVALID')
        scene_order = tuple(plan['scene_ids'])
        worker_ids = tuple(shard.launch.worker_id for shard in shards)
        if len(set(worker_ids)) != len(worker_ids) or any(scene not in self.case_inputs for scene in scene_order):
            raise ValueError('CONTAINER_WAVE_INPUTS_INVALID')
        # Every identifier is checked before the first launch.
        for shard in shards:
            for scene in scene_order:
                if re.fullmatch(TASK_ID_PATTERN, task_id_for(shard.launch.wave_id, shard.launch.worker_id, scene)) is None:
                    raise ValueError('CONTAINER_TASK_ID_INVALID')
        if plan['assignment'] is not None and canonical_json(plan['assignment']) != canonical_json(
                reserve_qualification_scenes(scene_order, worker_ids)):
            raise ValueError('CONTAINER_WAVE_ASSIGNMENT_CHANGED')
        for scene in scene_order:
            for ref in (*self.case_inputs[scene].values(), self.scene_manifest):
                validate_file_ref(ref)
        if self.context.deadline_monotonic_s-self.clock() <= 0:
            raise ValueError('CONTAINER_CAMPAIGN_DEADLINE_EXPIRED')
        if (root/'task-journal').exists():
            raise ValueError('CONTAINER_WAVE_NEW_JOURNAL_REQUIRED')
        journal = ContainerTaskJournal(root/'task-journal', clock=self.clock, instances={
            shard.launch.launch_id: dict(owner_root=str(shard.launch.owned_root), worker_id=shard.launch.worker_id,
                launch_generation=shard.launch.launch_generation, wave_id=shard.launch.wave_id)
            for shard in shards})
        assignment = WaveAssignment(scene_ids=scene_order, worker_ids=worker_ids, assignment=plan['assignment'])
        # A limit that cannot bind (a count at least the shard count, or no gap) adds nothing; when none binds there is no gate
        # and dispatch is exactly the ungated path.
        count = len(shards)
        cap = self.max_recording_shards if self.max_recording_shards is not None and self.max_recording_shards < count else None
        in_flight = (self.max_tasks_in_flight if self.max_tasks_in_flight is not None
                     and self.max_tasks_in_flight < count else None)
        gap = self.min_assignment_gap_s if self.min_assignment_gap_s else None
        gate = (RecordingGate(cap, in_flight, gap, self.clock)
                if cap is not None or in_flight is not None or gap is not None else None)
        dispatches = [InstanceDispatch(control=self.control_factory(shard), shard=shard, assignment=assignment,
            journal=journal, endpoints=endpoints, scene_manifest=self.scene_manifest,
            case_inputs=self.case_inputs, config=self.config, context=self.context,
            dispatch_allowed=dispatch_allowed, clock=self.clock, sleep=self.sleep, gate=gate)
            for shard in shards]
        if gate is not None:
            gate.members = dispatches
        self.active = dispatches
        self.waves[wave] = journal
        try:
            await self._barrier(dispatches)
            outcomes = await asyncio.gather(*(item.run(lambda: self.stop_reason) for item in dispatches),
                                            return_exceptions=True)
            errors = [item.error for item in dispatches if item.error is not None]
            errors += [dict(type=type(value).__name__, reason=str(value)) for value in outcomes
                       if isinstance(value, BaseException)]
            if errors:
                self.stop_dispatch('CONTAINER_INSTANCE_EXECUTION_FAULT')
            records = journal.records()
            rows = {record['collected']['scene_id']: dict(scene_id=record['collected']['scene_id'],
                worker_id=record['collected']['worker_id'], location=record['collected']['host_output'],
                task_id=record['collected']['task_id'], launch_id=record['collected']['instance_id'])
                for record in records.values() if record['collected'] is not None}
            return dict(wave_index=wave, coordinator_root=str(root/'task-journal'),
                        case_results=[rows[scene] for scene in scene_order if scene in rows],
                        infra_errors=errors)
        finally:
            self.active = None

    async def _barrier(self, dispatches):
        """Start every instance; no task is assigned until all report READY. Any failure ends the whole wave."""
        starts = [asyncio.create_task(item.start()) for item in dispatches]
        try:
            await asyncio.wait(starts, return_when=asyncio.FIRST_EXCEPTION)
            failure = next((item.exception() for item in starts
                            if item.done() and not item.cancelled() and item.exception() is not None), None)
            if failure is None:
                await asyncio.gather(*starts)
                return
        except BaseException as error:
            failure = error
        for item in starts:
            item.cancel()
        await asyncio.gather(*starts, return_exceptions=True)
        await asyncio.gather(*(item.finish('WAVE_START_FAILED') for item in dispatches), return_exceptions=True)
        raise failure

    def complete_wave_cleanup(self, plan, shards):
        if any(shard._close_task is None or not shard._close_task.done()
               or shard._close_task.result()['terminated'] is not True for shard in shards):
            raise ValueError('CONTAINER_WAVE_CLEANUP_UNCONFIRMED')
        for shard in shards:
            shard.registry.prove_terminated(shard.launch.launch_id, shard.observe_exit())

    def close(self):
        pass
