"""The Host caps how many shards are in the recording part of a task at once.

Real: `ConcurrentCollectionCoordinator`, `InstanceDispatch`, `WaveAssignment`, the journal, the task-input writer and the
frozen runtime config. Controlled doubles: `PhaseInstance` (the container's control surface, reporting the recording phase of a
task from a virtual clock) and `VirtualTime` (a clock whose sleeps resolve when the driver advances it). Phase model: the
task needs PRE seconds before recording, REC seconds of recording and PROC seconds of offline processing.
"""

import asyncio
import heapq

import pytest

from so101_demo.act.parallel_collection import reserve_qualification_scenes
from so101_demo.runtime.container_campaign import coordinator as coordinator_module
from so101_demo.runtime.container_campaign.coordinator import ConcurrentCollectionCoordinator, InstanceDispatch
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus, TaskStatus
from test_task_coordinator import Instance, config, make_world  # noqa: F401  (config is the module fixture)

PRE, REC, PROC = 30., 110., 250.
EIGHT_WORKERS = tuple(f'w{i:02d}' for i in range(8))
SCENES = tuple(f'scene-{i:02d}' for i in range(20))


class VirtualTime:
    def __init__(self, start=1000.):
        self.now, self._timers, self._count = start, [], 0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self._count += 1
        heapq.heappush(self._timers, (self.now+seconds, self._count, future))
        await future

    def advance(self):
        if not self._timers:
            return
        self.now = max(self.now, self._timers[0][0])
        while self._timers and self._timers[0][0] <= self.now:
            _, _, future = heapq.heappop(self._timers)
            if not future.done():
                future.set_result(None)


class PhaseInstance(Instance):
    report_phase = True
    timeline = None   # shared list of (task_id, assigned_at, deadline)
    vt = None

    async def assign_task(self, task):
        status = await super().assign_task(task)
        self.started_at = getattr(self, 'started_at', {})
        self.started_at[task.task_id] = self.vt()
        self.timeline.append((task.task_id, self.vt(), task.deadline_monotonic_s))
        return status

    async def get_status(self, task_id=None):
        self.calls.append('get_status')
        if task_id is None:
            return InstanceStatus(instance_id=self.instance_id, state='READY')
        elapsed = self.vt()-self.started_at[task_id]
        if elapsed >= PRE+REC+PROC:
            self._result(task_id, dict(teacher_task_result='PASS'))
            return InstanceStatus(instance_id=self.instance_id, state='READY',
                                  task=TaskStatus(task_id=task_id, state='SUCCEEDED'))
        phase = ('RECORDING' if elapsed < PRE+REC else 'POST_RECORDING') if self.report_phase else None
        return InstanceStatus(instance_id=self.instance_id, state='BUSY',
                              task=TaskStatus(task_id=task_id, state='RUNNING', phase=phase))


def run_phase_wave(tmp_path, config, *, workers, scenes, cap, report_phase=True, assignment=True):
    world = make_world(tmp_path, config, workers=workers, scenes=scenes,
        plan_assignment=reserve_qualification_scenes(tuple(scenes), tuple(workers)) if assignment else None)
    vt, timeline = VirtualTime(), []
    prepared = {}
    real_prepare = InstanceDispatch.prepare_task

    def spy(self, scene_id):
        prepared[self.task_id(scene_id)] = vt()
        return real_prepare(self, scene_id)

    for control in world.controls.values():
        control.__class__ = PhaseInstance
        control.report_phase, control.timeline, control.vt = report_phase, timeline, vt
    coordinator = ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
        scene_manifest=world.manifest, clock=vt, sleep=vt.sleep, max_recording_shards=cap,
        control_factory=lambda shard: world.controls[shard.launch.worker_id])

    async def drive():
        wave = asyncio.create_task(coordinator.run_wave(plan=world.plan, shards=world.shards,
            endpoints=world.endpoints, dispatch_allowed=lambda: True))
        while not wave.done():
            await asyncio.sleep(0.001)
            vt.advance()
        return await wave

    begin = vt()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(InstanceDispatch, 'prepare_task', spy)
        result = asyncio.run(drive())
    run_phase_wave.prepared = prepared
    return world, result, timeline, vt()-begin


def max_recording(timeline, span):
    """Largest number of tasks whose recording part [assigned, assigned+span) overlaps one instant."""
    events = sorted([(at, 1) for _, at, _ in timeline]+[(at+span, -1) for _, at, _ in timeline],
                    key=lambda event: (event[0], event[1]))
    live = peak = 0
    for _, delta in events:
        live += delta
        peak = max(peak, live)
    return peak


def mapping(timeline):
    """scene -> worker, from task ids of the form wave-0-<worker>-<scene>."""
    return {task.split('-', 3)[3]: task.split('-', 3)[2] for task, _, _ in timeline}


@pytest.fixture(scope='module')
def uncapped(tmp_path_factory, config):
    return run_phase_wave(tmp_path_factory.mktemp('uncapped'), config, workers=EIGHT_WORKERS, scenes=SCENES, cap=None)


def test_cap_bounds_recording_shards_and_keeps_reservations_and_throughput(tmp_path, config, uncapped):
    world, result, timeline, makespan = run_phase_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4)
    assert result['infra_errors'] == []
    assert sorted(mapping(timeline)) == sorted(SCENES) and len(timeline) == len(SCENES)   # every scene exactly once
    assert max_recording(timeline, PRE+REC) <= 4
    reserved = reserve_qualification_scenes(SCENES, EIGHT_WORKERS)['reserved_by_worker']
    got = mapping(timeline)
    assert all(got[scene] == worker for worker, scenes in reserved.items() for scene in scenes)
    _, _, free_timeline, free_makespan = uncapped
    assert max_recording(free_timeline, PRE+REC) == 8
    print('makespan uncapped=%.0f capped=%.0f' % (free_makespan, makespan))
    # The stagger costs at most one recording stage; it never costs a processing stage.
    assert makespan <= free_makespan+PRE+REC+10


def test_waiting_for_the_cap_does_not_start_the_task_deadline(tmp_path, config):
    _, _, timeline, _ = run_phase_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4)
    span = (config.initializing_hard_timeout_s+config.executing_hard_timeout_s
            +config.finalizing_hard_timeout_s+config.worker_recovery_timeout_s)
    prepared = run_phase_wave.prepared
    assert any(prepared[task] > 1000+PRE for task, _, _ in timeline)   # some tasks really waited for a slot
    # the deadline is derived when the task is prepared, after the wait, so it is exactly one task span from then
    assert all(deadline-prepared[task] == span for task, _, deadline in timeline)


def test_missing_phase_counts_the_shard_until_its_task_ends(tmp_path, config):
    _, result, timeline, _ = run_phase_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4, report_phase=False)
    assert result['infra_errors'] == [] and len(timeline) == len(SCENES)
    assert max_recording(timeline, PRE+REC+PROC) <= 4


@pytest.mark.parametrize('count', [1, 2])
def test_one_and_two_workers_never_build_a_gate_and_dispatch_the_same(tmp_path_factory, config, count, monkeypatch):
    def forbidden(cap):
        raise AssertionError('a gate that cannot bind must not exist')
    monkeypatch.setattr(coordinator_module, 'RecordingGate', forbidden)
    workers, scenes = EIGHT_WORKERS[:count], SCENES[:6]
    runs = []
    for cap in (None, count, 4):
        world, _, timeline, _ = run_phase_wave(tmp_path_factory.mktemp('c'), config, workers=workers,
            scenes=scenes, cap=cap, assignment=False)
        runs.append(sorted(task.split('-', 3)[3] for task, _, _ in timeline))   # which worker takes which scene is first-come
    assert runs[0] == runs[1] == runs[2] and len(runs[0]) == 6


@pytest.mark.parametrize('cap', [0, -1, True, 2.5, '4'])
def test_cap_must_be_a_positive_integer(tmp_path, config, cap):
    world = make_world(tmp_path, config)
    with pytest.raises(ValueError, match='CONTAINER_COORDINATOR_CONFIG_INVALID'):
        ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
                                        scene_manifest=world.manifest, max_recording_shards=cap)
