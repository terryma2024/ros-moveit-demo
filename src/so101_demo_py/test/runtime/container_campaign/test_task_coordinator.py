"""Host wave assignment and per-instance task loop.

Real: `WaveAssignment`, `InstanceDispatch`, `ConcurrentCollectionCoordinator`, `ContainerTaskJournal`,
`task_results` files, `TaskSpec`/`TaskStatus`/`InstanceStatus`, the frozen runtime config, the Host
task-input writer and (in one test) the container's `load_task_input`. Controlled doubles: the
instance control (`Instance`, shaped like `ContainerTaskControl`, standing in for the container
and its socket) and the clock/sleep. No simulator, container or qualification evidence is involved.
"""

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.parallel_collection import reserve_qualification_scenes
from so101_demo.cli.mujoco_batch.request import _load_runtime_config
from so101_demo.runtime.container_campaign.coordinator import (
    COLLECTED, FAULTED, ConcurrentCollectionCoordinator, InstanceDispatch, WaveAssignment,
)
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus, TaskStatus
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result
from so101_teleop.unified.contracts import AdmittedCampaignContext
from paths import PACKAGE_ROOT

TEACHER_SOCKET = Path('/act/ipc/teacher/inference.sock')
GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
BUSINESS_FAILURE = dict(teacher_task_result='FAILED', act_data_status='INVALID', act_data_qc='FAIL')


@pytest.fixture(scope='module')
def config():
    return _load_runtime_config(PACKAGE_ROOT/'config/mujoco/parallel_batch_act_offline.yaml')


def ref(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


class Clock:
    """Fake monotonic time advanced by the polling sleep; a tiny real pause keeps it from outrunning file I/O."""

    def __init__(self):
        self.now = 1000.

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds
        await asyncio.sleep(.0005)


class Instance:
    """Controlled double shaped like `ContainerTaskControl`; `script` maps a scene to its behaviour."""

    def __init__(self, shard, script, journal_root):
        self.instance_id, self.owner, self.script = shard.launch.launch_id, shard.root, script
        self.journal_root = journal_root
        self.gate = self.start_error = None
        self.started = False
        self.calls, self.assigned, self.delivered, self.written = [], [], {}, set()
        self.polls = 0
        self.outage = lambda poll: False
        self.override = lambda poll: None
        self.terminate_mode = 'ok'
        self.terminate_reason = None

    async def start(self):
        self.calls.append('start')
        if self.gate is not None:
            await self.gate.wait()
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        return InstanceStatus(instance_id=self.instance_id, state='READY')

    async def assign_task(self, task):
        self.calls.append('assign_task')
        self.assigned.append(task.task_id)
        mode = self.script.get(task.task_id.rsplit('-', 1)[-1], 'ok')
        if mode == 'lost_undelivered':
            raise ConnectionError('request lost')
        self.delivered[task.task_id] = 0
        if mode == 'lost':
            raise ConnectionError('reply lost')
        return TaskStatus(task_id=task.task_id, state='ACCEPTED')

    def _result(self, task_id, result):
        if task_id not in self.written:
            self.written.add(task_id)
            reserve_task_output(self.owner/'output', task_id)
            write_task_result(self.owner/'output', task_id, result)

    async def get_status(self, task_id=None):
        self.calls.append('get_status')
        self.polls += 1
        if not self.started:
            raise ValueError('SHARD_RUNTIME_NOT_READY')
        if self.outage(self.polls):
            raise ConnectionError('socket lost')
        reported = self.override(self.polls)
        if reported is not None:
            return reported
        if task_id is None:
            return InstanceStatus(instance_id=self.instance_id, state='READY')
        if task_id not in self.delivered:
            raise ValueError('CONTAINER_TASK_REFUSED: TASK_ID_UNKNOWN')
        self.delivered[task_id] += 1
        count, mode = self.delivered[task_id], self.script.get(task_id.rsplit('-', 1)[-1], 'ok')
        state, instance = 'RUNNING', 'BUSY'
        if mode == 'slow' and count == 1:
            self._result(task_id, dict(early=True))
        if mode == 'failed' and count >= 2:
            state = 'FAILED'
        elif mode != 'hang' and count >= (5 if mode == 'slow' else 2):
            self._result(task_id, BUSINESS_FAILURE if mode == 'business' else dict(teacher_task_result='PASS'))
            state, instance = 'SUCCEEDED', 'READY'
        if state == 'RUNNING':
            assert not (self.journal_root/task_id/'collected.json').exists()
        return InstanceStatus(instance_id=self.instance_id, state=instance,
            task=TaskStatus(task_id=task_id, state=state, fault_reason='boom' if state == 'FAILED' else None))

    async def terminate(self, reason):
        self.calls.append('terminate')
        self.terminate_reason = reason
        if self.terminate_mode == 'raises':
            raise RuntimeError('docker unreachable')
        if self.terminate_mode == 'unreleased':
            return InstanceStatus(instance_id=self.instance_id, state='STOPPING')
        return InstanceStatus(instance_id=self.instance_id, state='TERMINATED', resources_released=True)


def make_world(tmp_path, config, *, workers=('w00',), scenes=('s1', 's2'), script=None, plan_assignment=None):
    run = tmp_path/'run'
    run.mkdir()
    clock = Clock()
    shards = []
    for worker in workers:
        owned = run/'wave-0'/worker/'g1'
        (owned/'output').mkdir(parents=True)
        (owned/'task-inputs').mkdir()
        shards.append(SimpleNamespace(root=owned, teacher_socket=TEACHER_SOCKET, launch=SimpleNamespace(launch_id=f'wave-0-{worker}-g1',
            worker_id=worker, launch_generation=1, wave_id='wave-0', owned_root=str(owned))))
    inputs = tmp_path/'inputs'
    inputs.mkdir()
    manifest = inputs/'scenes.json'
    manifest.write_text('{"scenarios": []}')
    case_inputs = {}
    for scene in scenes:
        for name in ('scope', 'inputs'):
            (inputs/f'{name}-{scene.replace("/", "_")}.json').write_text(json.dumps(dict(name=name, scene=scene)))
        case_inputs[scene] = dict(scope=ref(inputs/f'scope-{scene.replace("/", "_")}.json'),
            inputs_manifest=ref(inputs/f'inputs-{scene.replace("/", "_")}.json'))
    journal_root = run/'host/wave-0/task-journal'
    controls = {shard.launch.worker_id: Instance(shard, script or {}, journal_root) for shard in shards}
    made = []
    context = AdmittedCampaignContext(campaign_id='campaign', operation_id='operation',
        workload_kind='act_collection_start', service_epoch='epoch', execution_generation=1,
        stable_host_id='host', physical_gpu_uuid=GPU, worker_count=len(workers), source_sha256='d'*64,
        manifest_sha256='d'*64, runtime_config_sha256='d'*64, collection_config_sha256='d'*64,
        contact_policy_fingerprint='d'*64, domain_session_map_sha256='d'*64, resource_binding_id='binding',
        evidence_root=str(run), admitted_at_monotonic_s=1, deadline_monotonic_s=clock.now+1e6)
    coordinator = ConcurrentCollectionCoordinator(context=context, config=config, case_inputs=case_inputs,
        scene_manifest=ref(manifest), clock=clock, sleep=clock.sleep,
        control_factory=lambda shard: made.append(shard.launch.worker_id) or controls[shard.launch.worker_id])
    endpoints = {role: SimpleNamespace(service_generation='g-'+role, max_frame_bytes=4096)
                 for role in ('teacher',)}
    plan = dict(wave_index=0, scene_ids=list(scenes), assignment=plan_assignment)
    return SimpleNamespace(coordinator=coordinator, shards=tuple(shards), controls=controls, plan=plan,
        endpoints=endpoints, clock=clock, context=context, made=made, journal_root=journal_root, run=run,
        case_inputs=case_inputs, manifest=ref(manifest))


def run_wave(world, **kwargs):
    return asyncio.run(world.coordinator.run_wave(plan=world.plan, shards=world.shards,
        endpoints=world.endpoints, dispatch_allowed=lambda: True, **kwargs))


def test_reservations_require_two_real_terminal_tasks():
    scenes = tuple(f'scene-{i:02d}' for i in range(20))
    workers = tuple(f'w{i:02d}' for i in range(8))
    assignment = WaveAssignment(scene_ids=scenes, worker_ids=workers,
                                assignment=reserve_qualification_scenes(scenes, workers))
    taken = {worker: [] for worker in workers}
    for worker in workers[:-1]:
        for index in range(2):
            scene = assignment.next_scene(worker)
            assert scene == scenes[2*workers.index(worker)+index]
            assert assignment.next_scene(worker) is None   # in flight: no second task, no surplus
            assignment.mark_collected(scene)    # a business failure is collected like any other result
            taken[worker].append(scene)
    for expected in scenes[16:]:
        scene = assignment.next_scene('w00')
        assert scene == expected
        assignment.mark_collected(scene)
        taken['w00'].append(scene)
    assert assignment.next_scene('w00') is None
    assert not set(scenes[14:16]) & {scene for values in taken.values() for scene in values}
    for expected in scenes[14:16]:
        scene = assignment.next_scene('w07')
        assert scene == expected
        assignment.mark_collected(scene)
    assert assignment.next_scene('w07') is None and set(assignment.states.values()) == {COLLECTED}
    # Surplus waits for the second reserved task of the same worker, and a faulted scene is never reassigned.
    second = WaveAssignment(scene_ids=scenes, worker_ids=workers, assignment=reserve_qualification_scenes(scenes, workers))
    first = second.next_scene('w00')
    second.mark_collected(first)
    lost = second.next_scene('w00')
    second.mark_faulted(lost)
    assert second.states[lost] == FAULTED and second.next_scene('w00') is None
    assert all(second.next_scene(worker) != lost for worker in workers)
    plain = WaveAssignment(scene_ids=('a', 'b', 'c'), worker_ids=('w00', 'w01'))
    assert [plain.next_scene('w01'), plain.next_scene('w00')] == ['a', 'b']
    plain.mark_faulted('a')
    assert plain.next_scene('w00') == 'c' and plain.next_scene('w01') is None
    with pytest.raises(ValueError, match='WAVE_ASSIGNMENT_STATE_INVALID'):
        plain.mark_collected('a')
    with pytest.raises(ValueError, match='WAVE_ASSIGNMENT_INVALID'):
        WaveAssignment(scene_ids=scenes, worker_ids=workers, assignment=dict(reserved_by_worker={}, surplus=()))


def test_business_failure_stays_in_denominator_and_next_task_runs(tmp_path, config):
    world = make_world(tmp_path, config, script={'s1': 'business'})
    outcome = run_wave(world)
    control = world.controls['w00']
    assert outcome['infra_errors'] == [] and outcome['wave_index'] == 0
    assert [row['scene_id'] for row in outcome['case_results']] == ['s1', 's2']
    assert control.assigned == ['wave-0-w00-s1', 'wave-0-w00-s2']
    assert control.terminate_reason == 'WAVE_COMPLETE' and control.calls.count('terminate') == 1
    first = outcome['case_results'][0]
    assert set(first) == {'scene_id', 'worker_id', 'location', 'task_id', 'launch_id'}
    assert first['location'] == str(world.shards[0].root/'output/tasks/wave-0-w00-s1')
    assert outcome['coordinator_root'] == str(world.journal_root)
    records = json.loads((world.journal_root/'wave-0-w00-s1/collected.json').read_text())
    assert records['result'] == BUSINESS_FAILURE
    assert world.coordinator.stop_reason is None


def test_lost_assign_reply_is_queried_never_resent(tmp_path, config):
    world = make_world(tmp_path, config, script={'s1': 'lost'})
    outcome = run_wave(world)
    control = world.controls['w00']
    assert control.assigned == ['wave-0-w00-s1', 'wave-0-w00-s2'] and control.calls.count('assign_task') == 2
    assert [row['scene_id'] for row in outcome['case_results']] == ['s1', 's2'] and outcome['infra_errors'] == []
    # A request that never arrived can only be queried; it ends as that instance's fault and is not resent.
    (tmp_path/'second').mkdir()
    world = make_world(tmp_path/'second', config, script={'s1': 'lost_undelivered'})
    outcome = run_wave(world)
    control = world.controls['w00']
    assert control.assigned == ['wave-0-w00-s1'] and control.terminate_reason.startswith('CONTAINER_STATUS_QUERY_REFUSED')
    assert outcome['case_results'] == [] and len(outcome['infra_errors']) == 1
    failed = json.loads((world.journal_root/'wave-0-w00-s1/failed.json').read_text())
    assert failed['reason'].startswith('CONTAINER_STATUS_QUERY_REFUSED')


def test_fault_terminates_only_that_instance(tmp_path, config):
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', 's2', 's3', 's4'),
                       script={'s2': 'failed'})
    outcome = run_wave(world)
    healthy, broken = world.controls['w00'], world.controls['w01']
    assert broken.assigned == ['wave-0-w01-s2'] and broken.calls.count('terminate') == 1
    assert broken.terminate_reason.startswith('CONTAINER_TASK_FAILED: boom')
    assert healthy.calls.count('terminate') == 1 and healthy.terminate_reason == 'WAVE_COMPLETE'
    assert healthy.calls.index('terminate') == len(healthy.calls)-1
    assert healthy.assigned == ['wave-0-w00-s1', 'wave-0-w00-s3', 'wave-0-w00-s4']   # s2 is never reassigned
    assert [row['scene_id'] for row in outcome['case_results']] == ['s1', 's3', 's4']
    assert len(outcome['infra_errors']) == 1 and outcome['infra_errors'][0]['task_id'] == 'wave-0-w01-s2'
    assert world.coordinator.stop_reason == 'CONTAINER_INSTANCE_EXECUTION_FAULT'
    assert json.loads((world.journal_root/'wave-0-w01-s2/failed.json').read_text())['reason'].startswith('CONTAINER_TASK_FAILED')
    assert not (world.journal_root/'wave-0-w01-s2/collected.json').exists()
    # dispatch is stopped for later waves
    with pytest.raises(ValueError, match='CONTAINER_WAVE_DISPATCH_FENCED'):
        run_wave(world)


def test_ready_instance_is_polled_during_barrier(tmp_path, config):
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', 's2'))
    async def scenario():
        world.controls['w01'].gate = gate = asyncio.Event()
        wave = asyncio.create_task(world.coordinator.run_wave(plan=world.plan, shards=world.shards,
            endpoints=world.endpoints, dispatch_allowed=lambda: True))
        ready = world.controls['w00']
        for _ in range(2000):
            if ready.polls >= 4:
                break
            await asyncio.sleep(.001)
        polled, assigned_early = ready.polls, [c for c in world.controls.values() if c.assigned]
        gate.set()
        return polled, assigned_early, await wave

    polled, assigned_early, outcome = asyncio.run(scenario())
    assert polled >= 4 and assigned_early == []
    assert len(outcome['case_results']) == 2 and outcome['infra_errors'] == []


def test_barrier_failure_terminates_every_instance_and_assigns_nothing(tmp_path, config):
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', 's2'))
    world.controls['w01'].start_error = RuntimeError('SHARD_CONTAINER_LAUNCH_FAILED')
    with pytest.raises(RuntimeError, match='SHARD_CONTAINER_LAUNCH_FAILED'):
        run_wave(world)
    assert all(c.assigned == [] and c.calls.count('terminate') == 1 for c in world.controls.values())
    assert world.coordinator.active is None


def test_no_collection_while_running(tmp_path, config):
    world = make_world(tmp_path, config, scenes=('s1',), script={'s1': 'slow'})
    outcome = run_wave(world)
    control = world.controls['w00']
    # The result file existed from the first poll; the double asserts no collected record while RUNNING.
    assert control.delivered['wave-0-w00-s1'] >= 5 and 'wave-0-w00-s1' in control.written
    assert [row['scene_id'] for row in outcome['case_results']] == ['s1']
    assert json.loads((world.journal_root/'wave-0-w00-s1/collected.json').read_text())['result'] == dict(early=True)


@pytest.mark.parametrize('scene', ['bad/scene', 'x'*130, 'a b'])
def test_task_ids_validated_before_first_launch(tmp_path, config, scene):
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', scene))
    with pytest.raises(ValueError, match='CONTAINER_TASK_ID_INVALID'):
        run_wave(world)
    assert world.made == [] and not (world.run/'host').exists()
    assert all(c.calls == [] for c in world.controls.values())


def test_task_deadline_composes_stage_bounds_and_is_capped_by_campaign(tmp_path, config):
    world = make_world(tmp_path, config)
    kwargs = dict(control=None, shard=world.shards[0], assignment=None, journal=None, endpoints=world.endpoints,
        scene_manifest=world.manifest, case_inputs=world.case_inputs, config=config, dispatch_allowed=lambda: True,
        clock=lambda: 1000., sleep=None)
    stages = (config.initializing_hard_timeout_s+config.executing_hard_timeout_s
              +config.finalizing_hard_timeout_s+config.worker_recovery_timeout_s)
    task = InstanceDispatch(context=world.context, **kwargs).prepare_task('s1')
    assert task.deadline_monotonic_s == 1000.+stages
    capped = replace(world.context, deadline_monotonic_s=1100.)
    assert InstanceDispatch(context=capped, **kwargs).prepare_task('s2').deadline_monotonic_s == 1100.
    expired = replace(world.context, deadline_monotonic_s=1000.5)
    with pytest.raises(Exception, match='CONTAINER_CAMPAIGN_DEADLINE_EXPIRED'):
        InstanceDispatch(context=expired, **dict(kwargs, clock=lambda: 1001.)).prepare_task('s1')
    path = world.shards[0].root/'task-inputs/wave-0-w00-s1.json'
    assert task.inputs_ref.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_host_task_input_document_is_accepted_by_container_loader(tmp_path, monkeypatch):
    import time
    from test_task_builder import make_env
    from so101_demo.runtime.container_campaign.task_builder import load_task_input
    env = make_env(tmp_path, monkeypatch)
    shard = SimpleNamespace(root=env.root, teacher_socket=TEACHER_SOCKET, launch=SimpleNamespace(launch_id='wave-0-w00-g1', worker_id='w00',
        launch_generation=1, wave_id='wave-0', owned_root=str(env.root)))
    endpoints = {role: SimpleNamespace(service_generation='service-'+role,
                 max_frame_bytes=env.campaign[role+'_service']['max_frame_bytes']) for role in ('teacher',)}
    context = SimpleNamespace(deadline_monotonic_s=time.monotonic()+3000)
    dispatch = InstanceDispatch(control=None, shard=shard, assignment=None, journal=None, endpoints=endpoints,
        scene_manifest=env.document['scene_manifest'], config=env.runtime, context=context,
        case_inputs={'default': dict(scope=env.document['scope'], inputs_manifest=env.document['inputs_manifest'])},
        dispatch_allowed=lambda: True)
    task = dispatch.prepare_task('default')
    loaded = load_task_input(task, env.spec,teacher_socket=TEACHER_SOCKET)
    assert task.task_id == 'wave-0-w00-default' and loaded.scene_id == 'default' and loaded.root == env.root
    assert loaded.teacher['service_generation'] == 'service-teacher' and loaded.teacher['role'] == 'teacher'
    assert not hasattr(loaded, 'head')
    assert loaded.refs == {name: env.document[name] for name in ('scope', 'inputs_manifest')}


def test_the_task_document_carries_the_socket_the_owner_says_the_instance_reaches(tmp_path, monkeypatch):
    """The socket path is the shard owner's `teacher_socket`: the container mount for a container, the Host path for a native
    instance. The coordinator holds no path of its own."""
    import time
    from test_task_builder import make_env
    from so101_demo.runtime.container_campaign.task_builder import load_task_input
    env = make_env(tmp_path, monkeypatch)
    native = tmp_path/'run/ipc/teacher/inference.sock'
    shard = SimpleNamespace(root=env.root, teacher_socket=native, launch=SimpleNamespace(launch_id='wave-0-w00-g1',
        worker_id='w00', launch_generation=1, wave_id='wave-0', owned_root=str(env.root)))
    endpoints = {'teacher': SimpleNamespace(service_generation='service-teacher',
                 max_frame_bytes=env.campaign['teacher_service']['max_frame_bytes'])}
    dispatch = InstanceDispatch(control=None, shard=shard, assignment=None, journal=None, endpoints=endpoints,
        scene_manifest=env.document['scene_manifest'], config=env.runtime,
        context=SimpleNamespace(deadline_monotonic_s=time.monotonic()+3000),
        case_inputs={'default': dict(scope=env.document['scope'], inputs_manifest=env.document['inputs_manifest'])},
        dispatch_allowed=lambda: True)
    task = dispatch.prepare_task('default')
    assert json.loads(open(task.inputs_ref.path).read())['teacher']['socket_path'] == str(native)
    assert load_task_input(task, env.spec, teacher_socket=native).teacher['socket_path'] == str(native)
    with pytest.raises(ValueError):
        load_task_input(task, env.spec, teacher_socket=TEACHER_SOCKET)


def test_task_document_names_only_launched_services(tmp_path, monkeypatch):
    """The Host writes exactly the loader's closed field set; a Head endpoint is neither written nor accepted."""
    import copy
    import time
    from test_task_builder import make_env, make_task
    from so101_demo.runtime.container_campaign import task_builder
    from so101_demo.runtime.container_campaign.task_builder import load_task_input
    env = make_env(tmp_path, monkeypatch)
    shard = SimpleNamespace(root=env.root, teacher_socket=TEACHER_SOCKET, launch=SimpleNamespace(launch_id='wave-0-w00-g1', worker_id='w00',
        launch_generation=1, wave_id='wave-0', owned_root=str(env.root)))
    # the launched set has one service; an extra, unlaunched Head endpoint in the mapping is never written
    endpoints = {role: SimpleNamespace(service_generation='service-'+role,
                 max_frame_bytes=env.campaign[role+'_service']['max_frame_bytes']) for role in ('head', 'teacher')}
    dispatch = InstanceDispatch(control=None, shard=shard, assignment=None, journal=None, endpoints=endpoints,
        scene_manifest=env.document['scene_manifest'], config=env.runtime,
        context=SimpleNamespace(deadline_monotonic_s=time.monotonic()+3000),
        case_inputs={'default': dict(scope=env.document['scope'], inputs_manifest=env.document['inputs_manifest'])},
        dispatch_allowed=lambda: True)
    task = dispatch.prepare_task('default')
    document = json.loads(open(task.inputs_ref.path).read())
    assert set(document) == task_builder._FIELDS and 'head' not in document and 'teacher' in document
    assert load_task_input(task, env.spec,teacher_socket=TEACHER_SOCKET).teacher == document['teacher']
    # a document that names a Head endpoint is a different, refused shape
    stale = copy.deepcopy(document)
    stale['head'] = dict(role='head', socket_path='/act/ipc/head/inference.sock', service_generation='service-head',
                         max_frame_bytes=document['teacher']['max_frame_bytes'])
    with pytest.raises(ValueError):
        load_task_input(make_task(env, stale, task_id=document['task_id']), env.spec,teacher_socket=TEACHER_SOCKET)
    # and one that omits Teacher is refused too
    missing = {key: value for key, value in document.items() if key != 'teacher'}
    with pytest.raises(ValueError):
        load_task_input(make_task(env, missing, task_id=document['task_id']), env.spec,teacher_socket=TEACHER_SOCKET)


def outage_from(poll):
    return lambda current: current >= poll


@pytest.mark.parametrize('kind', ['unreachable', 'deadline'])
def test_unreachable_or_deadline_faults_instance_and_keeps_others(tmp_path, config, kind):
    script = {'s2': 'hang'} if kind == 'deadline' else {}
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', 's2', 's3', 's4'), script=script)
    if kind == 'unreachable':
        world.controls['w01'].outage = outage_from(4)
    outcome = run_wave(world)
    healthy, broken = world.controls['w00'], world.controls['w01']
    expected = 'CONTAINER_INSTANCE_UNREACHABLE' if kind == 'unreachable' else 'CONTAINER_TASK_DEADLINE_EXCEEDED'
    assert broken.terminate_reason.startswith(expected) and broken.calls.count('terminate') == 1
    assert healthy.terminate_reason == 'WAVE_COMPLETE' and healthy.calls.count('terminate') == 1
    assert len(outcome['infra_errors']) == 1 and outcome['infra_errors'][0]['worker_id'] == 'w01'
    failed = [path for path in world.journal_root.glob('*/failed.json')]
    assert len(failed) == 1 and json.loads(failed[0].read_text())['reason'].startswith(expected)
    assert {row['worker_id'] for row in outcome['case_results']} >= {'w00'}
    assert world.coordinator.stop_reason == 'CONTAINER_INSTANCE_EXECUTION_FAULT'


def test_transient_status_errors_below_the_unreachable_bound_are_tolerated(tmp_path, config):
    world = make_world(tmp_path, config)
    world.controls['w00'].outage = lambda poll: poll in (4, 5)
    outcome = run_wave(world)
    assert outcome['infra_errors'] == [] and len(outcome['case_results']) == 2


def test_barrier_timeout_terminates_every_instance(tmp_path, config):
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', 's2'))

    async def scenario():
        world.controls['w01'].gate = asyncio.Event()   # never released
        return await world.coordinator.run_wave(plan=world.plan, shards=world.shards,
            endpoints=world.endpoints, dispatch_allowed=lambda: True)

    with pytest.raises(Exception, match='CONTAINER_INSTANCE_READY_TIMEOUT'):
        asyncio.run(scenario())
    assert all(c.assigned == [] and c.calls.count('terminate') == 1 for c in world.controls.values())
    assert world.coordinator.active is None


@pytest.mark.parametrize('kind', ['stopping', 'fault_reason'])
def test_reported_stopping_or_fault_status_faults_instance(tmp_path, config, kind):
    world = make_world(tmp_path, config, workers=('w00', 'w01'), scenes=('s1', 's2', 's3', 's4'))
    state = 'STOPPING' if kind == 'stopping' else 'BUSY'
    world.controls['w01'].override = lambda poll: (InstanceStatus(instance_id='wave-0-w01-g1', state=state,
        fault_reason='native stack died') if poll >= 4 else None)
    outcome = run_wave(world)
    assert world.controls['w01'].terminate_reason.startswith('CONTAINER_INSTANCE_REPORTED_FAULT: native stack died')
    assert world.controls['w00'].terminate_reason == 'WAVE_COMPLETE'
    assert len(outcome['infra_errors']) == 1 and outcome['infra_errors'][0]['worker_id'] == 'w01'
    assert world.coordinator.stop_reason == 'CONTAINER_INSTANCE_EXECUTION_FAULT'


@pytest.mark.parametrize('mode,expected', [('raises', 'CONTAINER_INSTANCE_TERMINATE_FAILED'),
                                           ('unreleased', 'CONTAINER_INSTANCE_STOP_UNCONFIRMED')])
def test_terminate_failure_or_unreleased_status_is_recorded_as_infra_error(tmp_path, config, mode, expected):
    world = make_world(tmp_path, config)
    world.controls['w00'].terminate_mode = mode
    outcome = run_wave(world)
    assert [error['reason'].split(':')[0] for error in outcome['infra_errors']] == [expected]
    assert len(outcome['case_results']) == 2 and world.coordinator.stop_reason == 'CONTAINER_INSTANCE_EXECUTION_FAULT'


def test_changed_reservation_plan_is_refused(tmp_path, config):
    workers = tuple(f'w{i:02d}' for i in range(8))
    scenes = tuple(f'scene-{i:02d}' for i in range(20))
    good = reserve_qualification_scenes(scenes, workers)
    swapped = dict(good, reserved_by_worker=dict(good['reserved_by_worker'], w00=good['reserved_by_worker']['w01'],
                                                 w01=good['reserved_by_worker']['w00']))
    world = make_world(tmp_path, config, workers=workers, scenes=scenes, plan_assignment=swapped)
    with pytest.raises(ValueError, match='CONTAINER_WAVE_ASSIGNMENT_CHANGED'):
        run_wave(world)
    assert world.made == [] and not (world.run/'host').exists()
