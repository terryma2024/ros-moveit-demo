"""Host readback of registered container tasks, the wave verifier and the frozen index.

Real producers: `ActCollectionResultStore`/`EpisodeRecorder`/`EpisodeAuditWriter` and the Teacher-result sealing in
`controlled_committed_result` (T/act/test_act_result_qc.py), the real `task_builder.result_summary`, real `task_results` files,
the real `ContainerTaskJournal` and `ContainerLaunchRegistry`. Controlled: the episode bytes (a synthetic one-record episode),
the independent QC recomputation (`episode_qc.recompute_native_qc` is replaced by the report the store published) and, for the
multi-scene scheduling tests only, the per-task readback (`controlled_readback`). The sealed fixture is produced by the old
Coordinator-driven helper, so its lease comes from a real BatchCoordinator rather than from `task_builder.local_lease`.
Nothing here is physical, Teacher or QC qualification evidence and no approval or qualification receipt is involved.
"""

import hashlib
import json
import os
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from test_act_result_qc import controlled_committed_result
from so101_demo.act.result_store import verify_container_task_registration, verify_coordinator_commit
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.runtime.container_campaign import result_verifier
from so101_demo.runtime.container_campaign.paths import host_task_output
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, pid_namespace_inode, read_process_owner,
)
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.result_verifier import ContainerWaveResultVerifier, build_frozen_index
from so101_demo.runtime.container_campaign.task_builder import result_summary
from so101_demo.runtime.container_campaign.task_contracts import InputRef, TaskSpec
from so101_demo.runtime.container_campaign.task_journal import ContainerTaskJournal, read_container_task_result
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result

INVALID = 'CONTAINER_TASK_READBACK_INVALID'


def ref(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write_input(owner, task_id, worker='w00', wave='wave-0', scene='point-1', generation=1):
    path = owner/'task-inputs'/(task_id+'.json')
    path.write_text(json.dumps(dict(task_id=task_id, worker_id=worker, launch_generation=generation,
                                    wave_id=wave, scene_id=scene)))
    return path


def make_journal(run, owners, wave='wave-0', clock=None):
    instances = {f'{wave}-{worker}-g1': dict(owner_root=str(owner), worker_id=worker, launch_generation=1,
                                              wave_id=wave) for worker, owner in owners.items()}
    return ContainerTaskJournal(run/'host'/wave/'task-journal', instances=instances, clock=clock or (lambda: 0.)), instances


def seal_manifest_free_perception_result(task_dir, lease, scope, inputs):
    """The real store's manifest-free form: no episode, no Teacher manifest, no QC (what a perception no-pose terminal seals)."""
    from so101_demo.act.result_store import ActCollectionResultStore
    workspace = task_dir/'attempts'/lease.point_id/lease.attempt_id
    store = ActCollectionResultStore(workspace, lease, clock=lambda: lease.lease_issued_monotonic_s+.5,
        audit_manifest=workspace/'working/episode/audit/audit-manifest.json', scope=scope, inputs_manifest=inputs)
    return store.seal(store.episode_root/'seal.json', teacher=dict(execution_status='INDETERMINATE',
        task_result='UNCONFIRMED', data_status='INVALID', data_reason='PERCEPTION_NO_POSE'))


def build_task(tmp_path, monkeypatch, *, teacher_outcome='PASSED', qc='FAIL', assigned_offset=-1., deadline_offset=5.,
               perception_no_pose=False):
    """One real sealed result under <owner>/output/tasks/<id>, its real summary, and the journal's collected record.

    With `perception_no_pose` the sealed result is the manifest-free perception form instead of a Teacher episode; the
    episode fixture then only supplies the lease, scope and inputs and is written outside the task directory."""
    run = tmp_path/'run'
    owner = run/'wave-0/w00/g1'
    (owner/'output').mkdir(parents=True)
    (owner/'task-inputs').mkdir()
    task_id = 'wave-0-w00-point-1'
    task_dir = reserve_task_output(owner/'output', task_id)
    fixture = tmp_path/'fixture'
    fixture.mkdir()
    _, location, scope, inputs, _ = controlled_committed_result(fixture, monkeypatch, teacher_outcome=teacher_outcome,
        commit=False, qc=qc, worker_root=fixture/'unused-worker' if perception_no_pose else task_dir,
        run_root=fixture/'unused-coordinator')
    audit = json.loads((location/'episode/audit/audit-manifest.json').read_text())
    lease = LeaseIdentity(**audit['identity']['lease'])
    if perception_no_pose:
        location = seal_manifest_free_perception_result(task_dir, lease, scope, inputs)
    summary = result_summary(task_input=SimpleNamespace(scene_id='point-1',
        refs=dict(scope=ref(scope), inputs_manifest=ref(inputs))), lease=lease,
        reset=SimpleNamespace(reset_epoch='reset-2', simulation_session_id='session-1'),
        location=str(location), task_root=task_dir)
    write_task_result(owner/'output', task_id, summary)
    journal, instances = make_journal(run, {'w00': owner}, clock=lambda: lease.lease_issued_monotonic_s+assigned_offset)
    input_path = write_input(owner, task_id)
    task = TaskSpec(task_id=task_id, inputs_ref=InputRef(**ref(input_path)),
                    deadline_monotonic_s=lease.lease_deadline_monotonic_s+deadline_offset)
    journal.assign(instance_id='wave-0-w00-g1', task=task, host_output=host_task_output(owner, task_id))
    journal.collect(task_id=task_id, result=read_container_task_result(owner, task_id=task_id))
    return SimpleNamespace(run=run, owner=owner, task_id=task_id, task_dir=task_dir, location=location, scope=scope,
        inputs=inputs, summary=summary, lease=lease, journal=journal, instances=instances,
        registration=journal.root/task_id/'collected.json')


def verify(world, **kwargs):
    return verify_container_task_registration(world.registration, scope=world.scope, inputs_manifest=world.inputs, **kwargs)


def rewrite_registration(world, **changes):
    document = json.loads(world.registration.read_text())
    document.update(changes)
    world.registration.write_text(json.dumps(document))


@pytest.fixture
def world(tmp_path, monkeypatch):
    return build_task(tmp_path, monkeypatch)


def test_registered_task_is_read_back_from_the_sealed_files(world):
    proof = verify(world)
    assert proof['kind'] == 'ACT_CONTAINER_TASK_READBACK' and proof['status'] == 'PASS'
    assert proof['teacher_task_result'] == 'PASS' and proof['act_data_qc'] == 'FAIL' and proof['export_eligible'] is False
    assert proof['location'] == str(world.location) and proof['task_id'] == world.task_id
    assert proof['result_sha256'] == world.summary['sealed']['result']['sha256']
    # nothing is modified by the readback
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in world.run.rglob('*') if p.is_file()}
    verify(world)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in world.run.rglob('*') if p.is_file()}


def test_qc_invalid_is_collected_but_cannot_export(world):
    proof = verify(world)
    assert proof['act_data_qc'] == 'FAIL' and proof['export_eligible'] is False
    wave = dict(case_results=[dict(scene_id='point-1', worker_id='w00', task_id=world.task_id, launch_id='wave-0-w00-g1',
        location=str(world.task_dir), proof=proof, registration=str(world.registration), owner_root=str(world.owner),
        scope_path=str(world.scope), inputs_manifest=str(world.inputs))])
    index = build_frozen_index(campaign_id='campaign', qualification=False, scene_count=1, waves=[wave])
    assert [task['task_id'] for task in index['collected_tasks']] == [world.task_id]
    assert index['collected_tasks'][0]['act_data_qc'] == 'FAIL' and index['committed_episodes'] == []


def test_host_readback_refuses_scope_outside_bound_manifest(world, tmp_path):
    """The Host's independent scope check against a bound scene manifest.

    Real: `freeze_inputs` binding the scene manifest, `verify_container_task_registration` and `require_scope_for_inputs`.
    Controlled: the sealed task in `world` was produced for a different (fake) inputs manifest, so a bound set can never pass
    the later original-input binding. The test therefore asserts WHICH check refused through the cause: the scope check runs
    first and names EPISODE_SCOPE_INPUTS_MISMATCH; a row of the bound manifest gets past it and fails only at that later binding.
    """
    from test_act_child_recorder_binding import _scope_for, frozen_child_inputs
    from test_act_formal_scene_scope import scene_file

    bound = tmp_path/'bound'
    bound.mkdir()
    manifest_path, manifest, _ = frozen_child_inputs(bound, mode='formal', scene_manifest=scene_file(bound),
                                                     scope_scene=('scene-a', 11))

    def refusal(scene, seed):
        scope = _scope_for(bound, f'scope-{scene}-{seed}.json', scene, seed, manifest['inputs_sha256'])
        with pytest.raises(ValueError, match=INVALID) as error:
            verify_container_task_registration(world.registration, scope=scope, inputs_manifest=manifest_path)
        return str(error.value.__cause__)

    for scene, seed in (('scene-z', 11), ('default', 0), ('scene-a', 12), ('scene-b', 11)):
        assert refusal(scene, seed) == 'EPISODE_SCOPE_INPUTS_MISMATCH', (scene, seed)
    for scene, seed in (('scene-a', 11), ('scene-b', 12)):
        assert refusal(scene, seed) == 'original input binding', (scene, seed)


def test_perception_no_pose_task_passes_host_readback_and_cannot_export(tmp_path, monkeypatch):
    world = build_task(tmp_path, monkeypatch, perception_no_pose=True)
    assert not (world.location/'episode/seal.json').exists() and not (world.location/'dynamic').exists()
    proof = verify(world)
    assert proof['kind'] == 'ACT_CONTAINER_TASK_READBACK' and proof['status'] == 'PASS'
    assert (proof['result_status'], proof['act_data_status'], proof['act_data_reason'], proof['act_data_qc']) == (
        'INDETERMINATE', 'INVALID', 'PERCEPTION_NO_POSE', 'NOT_RUN')
    assert proof['teacher_task_result'] == 'UNCONFIRMED' and proof['export_eligible'] is False
    assert proof['episode_seal_sha256'] is None and proof['qc_report_sha256'] is None
    wave = dict(case_results=[dict(scene_id='point-1', worker_id='w00', task_id=world.task_id, launch_id='wave-0-w00-g1',
        location=str(world.task_dir), proof=proof, registration=str(world.registration), owner_root=str(world.owner),
        scope_path=str(world.scope), inputs_manifest=str(world.inputs))])
    index = build_frozen_index(campaign_id='campaign', qualification=False, scene_count=1, waves=[wave])
    assert [task['task_id'] for task in index['collected_tasks']] == [world.task_id]
    assert index['collected_tasks'][0]['act_data_qc'] == 'NOT_RUN' and index['committed_episodes'] == []


@pytest.mark.parametrize('edit', ['task_result', 'sealed_result', 'sealed_qc'])
def test_registered_hash_detects_post_collection_edit(world, edit):
    target = {'task_result': world.task_dir/'task-result.json', 'sealed_result': world.location/'result.json',
              'sealed_qc': world.location/'qc-report.json'}[edit]
    target.write_bytes(target.read_bytes().replace(b'}', b' }', 1))
    with pytest.raises(ValueError, match=INVALID):
        verify(world)


@pytest.mark.parametrize('problem', ['assigned_after_issue', 'deadline_before_lease_end'])
def test_lease_outside_host_task_window_refused(tmp_path, monkeypatch, problem):
    world = build_task(tmp_path, monkeypatch,
        assigned_offset=1. if problem == 'assigned_after_issue' else -1.,
        deadline_offset=-1. if problem == 'deadline_before_lease_end' else 5.)
    with pytest.raises(ValueError, match=INVALID):
        verify(world)


@pytest.mark.parametrize('problem', ['foreign_owner', 'symlink_owner', 'foreign_output', 'other_task_dir', 'wrong_worker',
                                     'wrong_scene', 'wrong_generation', 'extra_field'])
def test_foreign_or_symlink_root_refused(world, tmp_path, problem):
    if problem == 'foreign_owner':
        other = tmp_path/'other/g1'
        (other/'output').mkdir(parents=True)
        rewrite_registration(world, owner_root=str(other))
    elif problem == 'symlink_owner':
        link = tmp_path/'alias'
        link.symlink_to(world.owner, target_is_directory=True)
        rewrite_registration(world, owner_root=str(link), host_output=str(link/'output/tasks'/world.task_id))
    elif problem == 'foreign_output':
        rewrite_registration(world, host_output=str(tmp_path))
    elif problem == 'other_task_dir':
        world.registration.rename(world.registration.parent/'moved.json')
        world.registration = world.registration.parent/'moved.json'
    elif problem == 'wrong_worker':
        rewrite_registration(world, worker_id='w01')
    elif problem == 'wrong_scene':
        rewrite_registration(world, scene_id='point-2')
    elif problem == 'wrong_generation':
        rewrite_registration(world, launch_generation=2)
    else:
        rewrite_registration(world, unexpected=True)
    with pytest.raises(ValueError, match=INVALID):
        verify(world)


@pytest.mark.parametrize('change', ['lease_worker', 'lease_attempt', 'sealed_path', 'extra_summary_field', 'inputs'])
def test_summary_identity_and_location_must_match_the_registered_task(world, change):
    summary = json.loads(json.dumps(world.summary))
    if change == 'lease_worker':
        summary['lease']['worker_id'] = 'w01'
    elif change == 'lease_attempt':
        summary['lease']['attempt_id'] = 'point-1-lease-2'
    elif change == 'sealed_path':
        summary['sealed']['path'] = 'attempts/point-1/point-1-lease-1/other'
    elif change == 'extra_summary_field':
        summary['extra'] = 1
    else:
        summary['inputs']['scope']['sha256'] = '0'*64
    # the registered hash is recomputed on purpose: only the summary content itself is under test
    path = world.task_dir/'task-result.json'
    path.write_text(json.dumps(dict(task_id=world.task_id, result=summary), sort_keys=True, separators=(',', ':'))+'\n')
    rewrite_registration(world, result=summary, task_result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match=INVALID):
        verify(world)


def test_readback_uses_the_scene_s_own_scope_and_inputs(world, tmp_path):
    other = tmp_path/'other-scope.json'
    other.write_bytes(world.scope.read_bytes()+b' ')
    with pytest.raises(ValueError, match=INVALID):
        verify_container_task_registration(world.registration, scope=other, inputs_manifest=world.inputs)
    assert verify(world)['status'] == 'PASS'


# ---- wave verifier -----------------------------------------------------------------------------------------------


def register(registry, run, worker, index, wave='wave-0'):
    owned = run/wave/worker/'g1'
    launch = ContainerLaunch(launch_id=f'{wave}-{worker}-g1', role='shard', worker_id=worker, wave_id=wave,
        launch_generation=1, container_name=f'so101-test-{worker}-g1', image_digest='sha256:'+'a'*64,
        owned_root=str(owned), ros_namespace=f'/act/campaign/{worker}', ros_domain_id=181+index, session_id=f'session-{index}')
    owner = ContainerOwnerKey(f'{index:x}'*64, '2026-10-12T01:02:03.123Z', 'sha256:'+'a'*64, 1)
    registry.register(launch)
    registry.bind_container(launch.launch_id, owner)
    registry.bind_child(launch.launch_id, ContainerChildBinding(owner, read_process_owner(os.getpid()),
        pid_namespace_inode(), str(owned/'control/normal.sock')))
    return SimpleNamespace(launch=launch, owner=owner)


def wave_outcome(world, journal=None, root=None):
    journal = journal or world.journal
    rows = [dict(scene_id=item['collected']['scene_id'], worker_id=item['collected']['worker_id'],
                 location=item['collected']['host_output'], task_id=task_id, launch_id=item['collected']['instance_id'])
            for task_id, item in journal.records().items() if item['collected'] is not None]
    return dict(wave_index=0, coordinator_root=str(journal.root), infra_errors=[], case_results=rows)


def real_verifier(world):
    registry = ContainerLaunchRegistry(world.run/'host/launches.sqlite3')
    shards = (register(registry, world.run, 'w00', 1),)
    verifier = ContainerWaveResultVerifier(root=world.run, registry=registry,
        case_inputs={'point-1': dict(scope=ref(world.scope), inputs_manifest=ref(world.inputs))})
    return registry, verifier, shards


def test_business_failure_passes_wave_verification_and_stays_in_denominator(world):
    registry, verifier, shards = real_verifier(world)
    plan = dict(wave_index=0, scene_ids=['point-1'], assignment=None)
    try:
        value = verifier.verify_wave(plan, wave_outcome(world), shards)
        row = value['case_results'][0]
        assert value['scene_count'] == 1 and row['proof']['teacher_task_result'] == 'PASS'
        assert row['proof']['act_data_qc'] == 'FAIL' and row['proof']['export_eligible'] is False
        assert row['registration'] == str(world.registration) and row['owner_root'] == str(world.owner)
        outcome = wave_outcome(world)
        for invalid in (outcome | {'case_results': []}, outcome | {'infra_errors': ['shard-crash']},
                        outcome | {'case_results': outcome['case_results']*2},
                        outcome | {'coordinator_root': str(world.run/'host/wave-0/coordinator')},
                        outcome | {'case_results': [dict(outcome['case_results'][0], worker_id='w01')]},
                        outcome | {'case_results': [dict(outcome['case_results'][0], task_id='wave-0-w00-other')]},
                        outcome | {'case_results': [{**outcome['case_results'][0], 'extra': 1}]}):
            with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
                verifier.verify_wave(plan, invalid, shards)
    finally:
        registry.close()


@pytest.mark.parametrize('problem', ['missing', 'foreign', 'symlink', 'duplicate'])
def test_unregistered_or_foreign_instance_cannot_relabel_a_task(world, problem):
    registry, verifier, shards = real_verifier(world)
    launch, owner = shards[0].launch, shards[0].owner
    plan = dict(wave_index=0, scene_ids=['point-1'], assignment=None)
    try:
        for name in ('w01/g1', 'w00/g2'):
            (world.run/'wave-0'/name).mkdir(parents=True)
        with pytest.raises(ValueError, match='CONTAINER_(WAVE_COMMIT_READBACK|LAUNCH_RECORD)_INVALID'):
            if problem == 'missing':
                shards = (SimpleNamespace(launch=ContainerLaunch(**dict(asdict(launch), launch_id='wave-0-w01-g1',
                    worker_id='w01', owned_root=str(world.run/'wave-0/w01/g1'))), owner=owner),)
            elif problem == 'foreign':
                shards = (SimpleNamespace(launch=ContainerLaunch(**dict(asdict(launch), owned_root=str(world.run/'wave-0/w00/g2'))),
                                          owner=owner),)
            elif problem == 'symlink':
                link = world.run/'wave-0/w00/alias'
                link.symlink_to(world.owner, target_is_directory=True)
                shards = (SimpleNamespace(launch=ContainerLaunch(**dict(asdict(launch), owned_root=str(link))), owner=owner),)
            else:
                shards = shards*2
            verifier.verify_wave(plan, wave_outcome(world), shards)
    finally:
        registry.close()


# ---- scheduling checks over a real journal with a controlled per-task readback ---------------------------------------


def controlled_readback(registration, *, scope, inputs_manifest, trust_independent_qc_memo=False):
    record = json.loads(registration.read_text())
    controlled_readback.calls.append((record['scene_id'], scope, inputs_manifest))
    return dict(kind='ACT_CONTAINER_TASK_READBACK', schema_version=1, status='PASS', task_id=record['task_id'],
        worker_id=record['worker_id'], scene_id=record['scene_id'], location=record['host_output'], export_eligible=False)


controlled_readback.calls = []


class Schedule:
    """Two real instances and a real journal; summaries are arbitrary because the per-task readback is controlled."""

    def __init__(self, tmp_path, monkeypatch, scenes, *, qualification, assignment=None):
        self.run = tmp_path/'run'
        self.owners = {worker: self.run/'wave-0'/worker/'g1' for worker in ('w00', 'w01')}
        for owner in self.owners.values():
            (owner/'output').mkdir(parents=True)
            (owner/'task-inputs').mkdir()
        self.time = 0.
        self.journal, _ = make_journal(self.run, self.owners, clock=self._tick)
        self.inputs = tmp_path/'inputs'
        self.inputs.mkdir()
        self.case_inputs = {}
        for scene in scenes:
            for name in ('scope', 'inputs'):
                (self.inputs/f'{name}-{scene}.json').write_text(json.dumps(dict(name=name, scene=scene)))
            self.case_inputs[scene] = dict(scope=ref(self.inputs/f'scope-{scene}.json'),
                                           inputs_manifest=ref(self.inputs/f'inputs-{scene}.json'))
        self.registry = ContainerLaunchRegistry(self.run/'host/launches.sqlite3')
        self.shards = tuple(register(self.registry, self.run, worker, index+1) for index, worker in enumerate(self.owners))
        self.verifier = ContainerWaveResultVerifier(root=self.run, registry=self.registry, case_inputs=self.case_inputs,
                                                    qualification=qualification)
        self.scenes, self.assignment = list(scenes), assignment
        monkeypatch.setattr(result_verifier, 'verify_container_task_registration', controlled_readback)
        controlled_readback.calls.clear()

    def _tick(self):
        self.time += 1.
        return self.time

    def run_task(self, worker, scene, *, collect=True):
        owner = self.owners[worker]
        task_id = f'wave-0-{worker}-{scene}'
        path = write_input(owner, task_id, worker=worker, scene=scene)
        task = TaskSpec(task_id=task_id, inputs_ref=InputRef(**ref(path)), deadline_monotonic_s=1e9)
        self.journal.assign(instance_id=f'wave-0-{worker}-g1', task=task, host_output=host_task_output(owner, task_id))
        if collect:
            reserve_task_output(owner/'output', task_id)
            write_task_result(owner/'output', task_id, dict(arbitrary=scene))
            self.journal.collect(task_id=task_id, result=read_container_task_result(owner, task_id=task_id))
        else:
            self.journal.fail(task_id=task_id, reason='execution fault')

    def verify(self):
        plan = dict(wave_index=0, scene_ids=self.scenes, assignment=self.assignment)
        return self.verifier.verify_wave(plan, wave_outcome(self, self.journal), self.shards)

    def close(self):
        self.registry.close()


@pytest.fixture
def schedule_factory(tmp_path, monkeypatch):
    made = []

    def make(scenes, **kwargs):
        value = Schedule(tmp_path, monkeypatch, scenes, **kwargs)
        made.append(value)
        return value
    yield make
    for value in made:
        value.close()


def test_failed_record_or_infra_error_fails_wave(schedule_factory):
    schedule = schedule_factory(['s1', 's2'], qualification=False)
    schedule.run_task('w00', 's1')
    schedule.run_task('w01', 's2', collect=False)
    with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
        schedule.verify()


def test_unfinished_assignment_fails_wave(schedule_factory):
    schedule = schedule_factory(['s1', 's2'], qualification=False)
    schedule.run_task('w00', 's1')
    owner = schedule.owners['w01']
    path = write_input(owner, 'wave-0-w01-s2', worker='w01', scene='s2')
    schedule.journal.assign(instance_id='wave-0-w01-g1', host_output=host_task_output(owner, 'wave-0-w01-s2'),
        task=TaskSpec(task_id='wave-0-w01-s2', inputs_ref=InputRef(**ref(path)), deadline_monotonic_s=1e9))
    with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
        schedule.verify()


def test_each_scene_is_read_back_against_its_own_scope_and_inputs(schedule_factory):
    schedule = schedule_factory(['s1', 's2'], qualification=False)
    schedule.run_task('w00', 's1')
    schedule.run_task('w01', 's2')
    value = schedule.verify()
    assert [row['scene_id'] for row in value['case_results']] == ['s1', 's2']
    for scene, scope, inputs in controlled_readback.calls:
        assert scope == schedule.inputs/f'scope-{scene}.json' and inputs == schedule.inputs/f'inputs-{scene}.json'
    assert len(controlled_readback.calls) == 2


def test_reservations_require_two_collected_tasks_per_instance(schedule_factory):
    scenes = ['s1', 's2', 's3', 's4']
    schedule = schedule_factory(scenes, qualification=True)
    for worker, scene in (('w00', 's1'), ('w01', 's2'), ('w01', 's3'), ('w01', 's4')):
        schedule.run_task(worker, scene)
    with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
        schedule.verify()    # w00 collected only one task


def test_qualification_wave_with_two_tasks_per_instance_passes(schedule_factory):
    schedule = schedule_factory(['s1', 's2', 's3', 's4'], qualification=True)
    for worker, scene in (('w00', 's1'), ('w01', 's2'), ('w00', 's3'), ('w01', 's4')):
        schedule.run_task(worker, scene)
    assert schedule.verify()['scene_count'] == 4


ASSIGNMENT = dict(reserved_by_worker=dict(w00=('s1', 's2'), w01=('s3', 's4')), surplus=('s5', 's6'))
SCENES = ['s1', 's2', 's3', 's4', 's5', 's6']


def test_reserved_scenes_must_be_collected_by_their_owner_and_surplus_after_them(schedule_factory):
    good = schedule_factory(SCENES, qualification=True, assignment=ASSIGNMENT)
    for worker, scene in (('w00', 's1'), ('w01', 's3'), ('w00', 's2'), ('w01', 's4'), ('w00', 's5'), ('w01', 's6')):
        good.run_task(worker, scene)
    assert good.verify()['scene_count'] == 6


def test_surplus_assigned_before_both_reserved_tasks_collected_is_refused(schedule_factory):
    early = schedule_factory(SCENES, qualification=True, assignment=ASSIGNMENT)
    for worker, scene in (('w00', 's1'), ('w00', 's5'), ('w00', 's2'), ('w01', 's3'), ('w01', 's4'), ('w01', 's6')):
        early.run_task(worker, scene)
    with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
        early.verify()


def test_reserved_scene_collected_by_another_instance_is_refused(schedule_factory):
    stolen = schedule_factory(SCENES, qualification=True, assignment=ASSIGNMENT)
    for worker, scene in (('w01', 's1'), ('w00', 's2'), ('w01', 's3'), ('w01', 's4'), ('w00', 's5'), ('w00', 's6')):
        stolen.run_task(worker, scene)
    with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
        stolen.verify()


# ---- the same recomputation from registry and journal records, with no live owner ---------------------------------------


def wave_records(registry, wave='wave-0'):
    return [record for record in registry.records() if record['launch']['wave_id'] == wave]


def test_verify_wave_records_equals_the_class_result_without_live_owners(world):
    registry, verifier, shards = real_verifier(world)
    plan = dict(wave_index=0, scene_ids=['point-1'], assignment=None)
    try:
        expected = verifier.verify_wave(plan, wave_outcome(world), shards)
        value = result_verifier.verify_wave_records(world.run, plan, wave_records(registry), verifier.case_inputs, False)
        assert value == expected and value['case_results'][0]['proof']['teacher_task_result'] == 'PASS'
        # the rows come from the collected journal records when no outcome is given, and equal an explicit outcome's rows
        assert result_verifier.verify_wave_records(world.run, plan, wave_records(registry), verifier.case_inputs, False,
            case_rows=wave_outcome(world)['case_results']) == expected
        # a read-only registry gives the same records and the same wave record
        readonly = ContainerLaunchRegistry(world.run/'host/launches.sqlite3', create=False, read_only=True)
        try:
            assert result_verifier.verify_wave_records(world.run, plan, wave_records(readonly), verifier.case_inputs,
                                                       False) == expected
        finally:
            readonly.close()
    finally:
        registry.close()


@pytest.mark.parametrize('problem', ['no_records', 'unbound_child', 'unbound_container', 'other_wave', 'duplicate_worker',
                                     'foreign_root', 'service_role', 'unknown_scene_inputs', 'extra_plan_scene'])
def test_verify_wave_records_refuses_records_that_are_not_this_waves_registered_shards(world, problem):
    registry, verifier, shards = real_verifier(world)
    plan = dict(wave_index=0, scene_ids=['point-1'], assignment=None)
    records, inputs = wave_records(registry), verifier.case_inputs
    try:
        record = records[0]
        if problem == 'no_records':
            records = []
        elif problem == 'unbound_child':
            records = [dict(record, binding=None)]
        elif problem == 'unbound_container':
            records = [dict(record, owner=None)]
        elif problem == 'other_wave':
            records = [dict(record, launch=dict(record['launch'], wave_id='wave-1'))]
        elif problem == 'duplicate_worker':
            records = [record, dict(record, launch=dict(record['launch'], launch_id='wave-0-w00-g9'))]
        elif problem == 'foreign_root':
            records = [dict(record, launch=dict(record['launch'], owned_root=str(world.run/'wave-0/w00/g2')))]
        elif problem == 'service_role':
            records = [dict(record, launch=dict(record['launch'], role='teacher'))]
        elif problem == 'unknown_scene_inputs':
            inputs = {'point-2': inputs['point-1']}
        else:
            plan = dict(plan, scene_ids=['point-1', 'point-2'])
        with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
            result_verifier.verify_wave_records(world.run, plan, records, inputs, False)
    finally:
        registry.close()


def test_verify_wave_records_reads_the_journal_without_creating_anything(world):
    registry, verifier, shards = real_verifier(world)
    registry.close()
    registry = ContainerLaunchRegistry(world.run/'host/launches.sqlite3', create=False, read_only=True)
    plan = dict(wave_index=0, scene_ids=['point-1'], assignment=None)
    before = sorted((str(p), p.is_dir()) for p in world.run.rglob('*'))
    try:
        result_verifier.verify_wave_records(world.run, plan, wave_records(registry), verifier.case_inputs, False)
        missing = dict(plan, wave_index=3)
        with pytest.raises(ValueError, match='CONTAINER_WAVE_COMMIT_READBACK_INVALID'):
            result_verifier.verify_wave_records(world.run, missing, [dict(wave_records(registry)[0],
                launch=dict(wave_records(registry)[0]['launch'], wave_id='wave-3'))], verifier.case_inputs, False)
    finally:
        registry.close()
    assert sorted((str(p), p.is_dir()) for p in world.run.rglob('*')) == before


def scheduled(worker, assigned, collected):
    return dict(worker_id=worker, assigned_monotonic_s=assigned, collected_monotonic_s=collected)


def test_check_wave_scheduling_is_a_module_function_with_coded_refusals():
    roots = {'w00': 'a', 'w01': 'b'}
    plan = dict(wave_index=0, scene_ids=['s1', 's2', 's3', 's4', 's5', 's6'], assignment=ASSIGNMENT)
    ok = {'s1': scheduled('w00', 1, 2), 's2': scheduled('w00', 3, 4), 's3': scheduled('w01', 1, 2),
          's4': scheduled('w01', 3, 4), 's5': scheduled('w00', 5, 6), 's6': scheduled('w01', 5, 6)}
    result_verifier.check_wave_scheduling(plan, ok, roots, True)
    with pytest.raises(ValueError, match='INSTANCE_SHORT:w00'):
        result_verifier.check_wave_scheduling(dict(plan, assignment=None), {name: dict(ok[name], worker_id='w01')
                                                                            for name in ok} | {'s1': ok['s1']}, roots, True)
    result_verifier.check_wave_scheduling(dict(plan, assignment=None), {'s1': ok['s1']}, {'w00': 'a'}, False)
    with pytest.raises(ValueError, match='RESERVED_COLLECTED_ELSEWHERE:s1'):
        result_verifier.check_wave_scheduling(plan, dict(ok, s1=scheduled('w01', 1, 2), s3=scheduled('w00', 1, 2)),
                                              roots, True)
    with pytest.raises(ValueError, match='SURPLUS_BEFORE_RESERVED:s5'):
        result_verifier.check_wave_scheduling(plan, dict(ok, s5=scheduled('w00', 3.5, 6)), roots, True)


# ---- the coordinator-commit readback of the schema 2 path stays valid --------------------------------------------------


def test_private_shard_commit_keeps_teacher_result_and_reads_original_journal(tmp_path, monkeypatch):
    worker = tmp_path/'container-campaign/wave-0/w00/g1'
    run, location, scope, inputs, receipt = controlled_committed_result(tmp_path, monkeypatch, teacher_outcome='PASSED',
        worker_root=worker)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    proof = verify_coordinator_commit(run/'coordinator', location=location, scope=scope, inputs_manifest=inputs,
                                      worker_roots={'w00': worker})
    assert proof['status'] == 'PASS' and proof['result_status'] == 'PASSED'
    assert proof['teacher_task_result'] == 'PASS' and proof['act_data_qc'] == 'FAIL'
    assert proof['export_eligible'] is False and proof['receipt'] == receipt
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in before.items())


@pytest.mark.parametrize('problem', ['missing', 'foreign', 'relative', 'symlink', 'duplicate'])
def test_unregistered_or_foreign_root_cannot_relabel_a_valid_commit(tmp_path, monkeypatch, problem):
    worker = tmp_path/'container-campaign/wave-0/w00/g1'
    run, location, scope, inputs, receipt = controlled_committed_result(tmp_path, monkeypatch, worker_root=worker)
    roots = {'w00': worker}
    if problem == 'missing':
        roots = {'w01': worker}
    elif problem == 'foreign':
        roots = {'w00': tmp_path/'other/g1'}
    elif problem == 'relative':
        roots = {'w00': 'wave-0/w00/g1'}
    elif problem == 'duplicate':
        roots['w01'] = worker
    else:
        link = tmp_path/'alias'
        link.symlink_to(worker, target_is_directory=True)
        roots = {'w00': link}
    with pytest.raises(ValueError, match='RESULT_COMMIT_READBACK_INVALID'):
        verify_coordinator_commit(run/'coordinator', location=location, scope=scope, inputs_manifest=inputs,
                                  worker_roots=roots)


def test_qualification_index_never_exports(world):
    proof = dict(verify(world), export_eligible=True)   # even an exportable verdict stays out of a qualification index
    wave = dict(case_results=[dict(scene_id='point-1', worker_id='w00', task_id=world.task_id, launch_id='wave-0-w00-g1',
        location=str(world.task_dir), proof=proof, registration=str(world.registration), owner_root=str(world.owner),
        scope_path=str(world.scope), inputs_manifest=str(world.inputs))])
    qualification = build_frozen_index(campaign_id='campaign', qualification=True, scene_count=1, waves=[wave])
    formal = build_frozen_index(campaign_id='campaign', qualification=False, scene_count=1, waves=[wave])
    assert qualification['committed_episodes'] == [] and len(qualification['collected_tasks']) == 1
    entry, = formal['committed_episodes']
    assert entry['schema_version'] == 3 and entry['verifier_sha256'] == proof['result_sha256']
    assert entry['collection_evidence']['registration'] == str(world.registration)
    assert set(entry['collection_evidence']) == {'registration', 'owner_root', 'task_id', 'result_location', 'scope_path',
                                                 'inputs_manifest'}
