"""The Host caps how many shards record (hold a phase-1 task) at once.

Real: `ConcurrentCollectionCoordinator`, `InstanceDispatch`, `WaveAssignment`, the journal, the task-input writer and the
frozen runtime config. Controlled doubles: `RecordingInstance` (the container's control surface, ending a task on a virtual
clock) and `VirtualTime` (a clock whose sleeps resolve when the driver advances it). Task model: a phase-1 task needs PRE seconds
before recording and REC seconds of recording, then ends.
"""

import asyncio
import heapq

import pytest

from so101_demo.act.parallel_collection import reserve_qualification_scenes
from so101_demo.runtime.container_campaign import coordinator as coordinator_module
from so101_demo.runtime.container_campaign.coordinator import ConcurrentCollectionCoordinator, InstanceDispatch
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus, TaskStatus
from test_task_coordinator import Instance, config, make_world  # noqa: F401  (config is the module fixture)

PRE, REC = 30., 110.
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


class RecordingInstance(Instance):
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
        if elapsed >= PRE+REC:
            self._result(task_id, dict(teacher_task_result='PASS'))
            return InstanceStatus(instance_id=self.instance_id, state='READY',
                                  task=TaskStatus(task_id=task_id, state='SUCCEEDED'))
        return InstanceStatus(instance_id=self.instance_id, state='BUSY',
                              task=TaskStatus(task_id=task_id, state='RUNNING'))


def run_wave(tmp_path, config, *, workers, scenes, cap, assignment=True, in_flight=None, gap=None):
    world = make_world(tmp_path, config, workers=workers, scenes=scenes,
        plan_assignment=reserve_qualification_scenes(tuple(scenes), tuple(workers)) if assignment else None)
    vt, timeline = VirtualTime(), []
    prepared = {}
    real_prepare = InstanceDispatch.prepare_task

    def spy(self, scene_id):
        prepared[self.task_id(scene_id)] = vt()
        return real_prepare(self, scene_id)

    for control in world.controls.values():
        control.__class__ = RecordingInstance
        control.timeline, control.vt = timeline, vt
    coordinator = ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
        scene_manifest=world.manifest, clock=vt, sleep=vt.sleep, max_recording_shards=cap,
        **({} if in_flight is None else dict(max_tasks_in_flight=in_flight)),
        **({} if gap is None else dict(min_assignment_gap_s=gap)),
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
    run_wave.prepared = prepared
    return world, result, timeline, vt()-begin


def max_recording(timeline, span):
    """Largest number of tasks whose span [assigned, assigned+span) overlaps one instant."""
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
    return run_wave(tmp_path_factory.mktemp('uncapped'), config, workers=EIGHT_WORKERS, scenes=SCENES, cap=None)


def test_cap_bounds_recording_shards_and_keeps_reservations_and_throughput(tmp_path, config, uncapped):
    world, result, timeline, makespan = run_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4)
    assert result['infra_errors'] == []
    assert sorted(mapping(timeline)) == sorted(SCENES) and len(timeline) == len(SCENES)   # every scene exactly once
    assert max_recording(timeline, PRE+REC) <= 4
    reserved = reserve_qualification_scenes(SCENES, EIGHT_WORKERS)['reserved_by_worker']
    got = mapping(timeline)
    assert all(got[scene] == worker for worker, scenes in reserved.items() for scene in scenes)
    _, _, free_timeline, free_makespan = uncapped
    assert max_recording(free_timeline, PRE+REC) == 8
    print('makespan uncapped=%.0f capped=%.0f' % (free_makespan, makespan))
    # Twenty scenes on four slots take five task spans, on eight slots three; each span carries a few status-poll intervals
    # (measured 903 s and 479 s against 700 s and 420 s ideal).
    assert free_makespan < makespan <= 7*(PRE+REC)


def test_waiting_for_the_cap_does_not_start_the_task_deadline(tmp_path, config):
    _, _, timeline, _ = run_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4)
    span = (config.initializing_hard_timeout_s+config.executing_hard_timeout_s
            +config.finalizing_hard_timeout_s+config.worker_recovery_timeout_s)
    prepared = run_wave.prepared
    assert any(prepared[task] > 1000+PRE for task, _, _ in timeline)   # some tasks really waited for a slot
    # the deadline is derived when the task is prepared, after the wait, so it is exactly one task span from then
    assert all(deadline-prepared[task] == span for task, _, deadline in timeline)


@pytest.mark.parametrize('count', [1, 2])
def test_one_and_two_workers_never_build_a_gate_and_dispatch_the_same(tmp_path_factory, config, count, monkeypatch):
    def forbidden(cap):
        raise AssertionError('a gate that cannot bind must not exist')
    monkeypatch.setattr(coordinator_module, 'RecordingGate', forbidden)
    workers, scenes = EIGHT_WORKERS[:count], SCENES[:6]
    runs = []
    for cap in (None, count, 4):
        world, _, timeline, _ = run_wave(tmp_path_factory.mktemp('c'), config, workers=workers,
            scenes=scenes, cap=cap, assignment=False)
        runs.append(sorted(task.split('-', 3)[3] for task, _, _ in timeline))   # which worker takes which scene is first-come
    assert runs[0] == runs[1] == runs[2] and len(runs[0]) == 6


@pytest.mark.parametrize('cap', [0, -1, True, 2.5, '4'])
def test_cap_must_be_a_positive_integer(tmp_path, config, cap):
    world = make_world(tmp_path, config)
    with pytest.raises(ValueError, match='CONTAINER_COORDINATOR_CONFIG_INVALID'):
        ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
                                        scene_manifest=world.manifest, max_recording_shards=cap)


TOTAL = PRE+REC


def max_in_flight(timeline, span=TOTAL):
    return max_recording(timeline, span)   # same sweep: tasks live over [assigned, assigned+span)


def gaps(timeline):
    times = sorted(at for _, at, _ in timeline)
    return [later-earlier for earlier, later in zip(times, times[1:])]


def test_tasks_in_flight_and_gap_bound_a_wave_of_twenty_scenes_on_eight_shards(tmp_path, config, uncapped):
    world, result, timeline, makespan = run_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4,
                                                       in_flight=2, gap=30.)
    assert result['infra_errors'] == []
    assert sorted(mapping(timeline)) == sorted(SCENES) and len(timeline) == len(SCENES)   # every scene exactly once
    assert max_in_flight(timeline) <= 2
    assert max_recording(timeline, PRE+REC) <= 4
    assert min(gaps(timeline)) >= 30.
    reserved = reserve_qualification_scenes(SCENES, EIGHT_WORKERS)['reserved_by_worker']
    got = mapping(timeline)
    assert all(got[scene] == worker for worker, scenes in reserved.items() for scene in scenes)
    assert max_in_flight(timeline) == 2   # the limit binds, so the run really used it
    print('PROJECTED_WAVE_S=%.0f (%.1f min)' % (makespan, makespan/60))
    assert makespan <= 12*TOTAL   # ten rounds of two tasks plus status-poll intervals (measured 1648 s against 1400 s ideal)


def test_in_flight_cap_alone_and_gap_alone(tmp_path_factory, config):
    _, _, only_cap, _ = run_wave(tmp_path_factory.mktemp('a'), config, workers=EIGHT_WORKERS, scenes=SCENES,
                                       cap=None, in_flight=3)
    assert max_in_flight(only_cap) == 3 and len(only_cap) == len(SCENES)
    _, _, only_gap, _ = run_wave(tmp_path_factory.mktemp('b'), config, workers=EIGHT_WORKERS, scenes=SCENES,
                                       cap=None, gap=45.)
    assert min(gaps(only_gap)) >= 45. and len(only_gap) == len(SCENES)


def test_waiting_for_the_gate_does_not_start_the_task_deadline_with_new_limits(tmp_path, config):
    _, _, timeline, _ = run_wave(tmp_path, config, workers=EIGHT_WORKERS, scenes=SCENES, cap=4, in_flight=2, gap=30.)
    span = (config.initializing_hard_timeout_s+config.executing_hard_timeout_s
            +config.finalizing_hard_timeout_s+config.worker_recovery_timeout_s)
    prepared = run_wave.prepared
    assert any(prepared[task] > 1000+PRE for task, _, _ in timeline)
    assert all(deadline-prepared[task] == span for task, _, deadline in timeline)


@pytest.mark.parametrize('count', [1, 2, 8])
def test_any_worker_count_without_the_limits_builds_no_gate(tmp_path_factory, config, count, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('absent keys must mean no gate')
    monkeypatch.setattr(coordinator_module, 'RecordingGate', forbidden)
    workers, scenes = EIGHT_WORKERS[:count], SCENES[:6]
    _, _, timeline, _ = run_wave(tmp_path_factory.mktemp('n'), config, workers=workers, scenes=scenes, cap=None,
                                       assignment=False)
    assert len(timeline) == 6
    # a limit that cannot bind and no gap also builds no gate
    _, _, timeline, _ = run_wave(tmp_path_factory.mktemp('m'), config, workers=workers, scenes=scenes, cap=None,
                                       assignment=False, in_flight=count)
    assert len(timeline) == 6


@pytest.mark.parametrize('name,bad', [('max_tasks_in_flight', value) for value in (0, -1, True, 2.5, '5')]
                         + [('min_assignment_gap_s', value) for value in (-1, True, '60', float('nan'), float('inf'))])
def test_new_limits_are_validated(tmp_path, config, name, bad):
    world = make_world(tmp_path, config)
    with pytest.raises(ValueError, match='CONTAINER_COORDINATOR_CONFIG_INVALID'):
        ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
                                        scene_manifest=world.manifest, **{name: bad})
