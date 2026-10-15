"""The Host lowers a shard container's CPU weight during its offline processing and restores it on every exit path.

Real: `ConcurrentCollectionCoordinator`, `InstanceDispatch`, `ShardCpuShares`, `CpuShareJournal`, the journal and the
frozen runtime config. Controlled doubles: `PhaseInstance` (phase reported from a virtual clock), a fake docker runner and
a fake `cpu_target` per shard. The tests state the weight timeline per container, not how it is implemented.
Note: a cgroup CPU weight only matters under CPU contention; these tests check the Host's commands, not scheduling.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign import cpu_shares as cpu_module
from so101_demo.runtime.container_campaign.coordinator import ConcurrentCollectionCoordinator
from so101_demo.runtime.container_campaign.shard_owner import CpuTarget
from so101_demo.runtime.container_campaign.task_contracts import InstanceStatus
from test_recording_cap import PROC, REC, PRE, PhaseInstance, VirtualTime
from test_task_coordinator import config, make_world  # noqa: F401  (config is the module fixture)


class FakeDocker:
    def __init__(self, vt, fail_for=()):
        self.vt, self.calls, self.fail_for = vt, [], set(fail_for)

    def __call__(self, argv):
        assert argv[:3] == ['docker', 'update', '--cpu-shares'] and len(argv) == 5
        self.calls.append((self.vt(), argv[4], int(argv[3])))
        if int(argv[3]) in self.fail_for:
            return SimpleNamespace(returncode=1, stdout='', stderr='boom')
        return SimpleNamespace(returncode=0, stdout=argv[4], stderr='')

    def timeline(self, container):
        return [(at, value) for at, name, value in self.calls if name == container]


class FaultingPhaseInstance(PhaseInstance):
    fault_after = None

    async def get_status(self, task_id=None):
        status = await super().get_status(task_id)
        if self.fault_after is not None and task_id is not None and self.vt()-self.started_at[task_id] >= self.fault_after:
            return InstanceStatus(instance_id=self.instance_id, state='STOPPING', fault_reason='boom', task=status.task)
        return status


def run(tmp_path, config, *, shares, workers=('w00', 'w01'), scenes=('s1', 's2', 's3'), original=1024, fail_for=(),
        fault_after=None, bound=True):
    world = make_world(tmp_path, config, workers=workers, scenes=scenes)
    vt, timeline = VirtualTime(), []
    docker = FakeDocker(vt, fail_for)
    verified = []
    for shard in world.shards:
        name = 'c-'+shard.launch.worker_id
        verify = (lambda name=name: verified.append(name))
        shard.cpu_target = (lambda name=name, verify=verify: CpuTarget(
            container_id=name, original_cpu_shares=original, verify=verify, docker=docker)) if bound else (lambda: None)
    for control in world.controls.values():
        control.__class__ = PhaseInstance if fault_after is None else FaultingPhaseInstance
        control.report_phase, control.timeline, control.vt = True, timeline, vt
        if fault_after is not None:
            control.fault_after = fault_after
    kwargs = {} if shares is None else dict(post_recording_cpu_shares=shares)
    coordinator = ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
        scene_manifest=world.manifest, clock=vt, sleep=vt.sleep, control_factory=lambda s: world.controls[s.launch.worker_id],
        **kwargs)

    async def drive():
        wave = asyncio.create_task(coordinator.run_wave(plan=world.plan, shards=world.shards, endpoints=world.endpoints,
                                                        dispatch_allowed=lambda: True))
        while not wave.done():
            await asyncio.sleep(0.001)
            vt.advance()
        return await wave

    result = asyncio.run(drive())
    return world, result, docker, verified, timeline


def journal_lines(world):
    path = world.run/'host'/'wave-0'/cpu_module.JOURNAL_NAME
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_weight_is_low_only_during_offline_processing_and_restored_after_each_task(tmp_path, config):
    world, result, docker, verified, timeline = run(tmp_path, config, shares=64)
    assert result['infra_errors'] == []
    assigned = {}
    for task, at, _ in timeline:
        assigned.setdefault(task.split('-', 3)[2], []).append(at)
    for worker, starts in assigned.items():
        steps = docker.timeline('c-'+worker)
        assert [value for _, value in steps] == [64, 1024]*len(starts)   # lowered once, restored once per task
        for (at, value), start in zip(steps[::2], starts):
            assert at >= start+PRE+REC and value == 64   # not before the recorder stopped
        for (at, value), start in zip(steps[1::2], starts):
            assert at <= start+PRE+REC+PROC+5 and value == 1024   # restored when the task ends
    assert verified   # the container identity was checked before updates
    lines = journal_lines(world)
    assert len(lines) == len(docker.calls) and all(line['ok'] is True for line in lines)
    assert {line['container_id'] for line in lines} == {'c-w00', 'c-w01'}
    assert {line['requested'] for line in lines} == {64, 1024}


def test_feature_is_off_when_the_key_is_absent(tmp_path, config):
    world, result, docker, verified, _ = run(tmp_path, config, shares=None)
    assert result['infra_errors'] == [] and docker.calls == [] and verified == [] and journal_lines(world) == []


def test_restore_writes_the_launch_time_weight_not_a_constant(tmp_path, config):
    _, _, docker, _, _ = run(tmp_path, config, shares=64, original=512, workers=('w00',), scenes=('s1',))
    assert [value for _, _, value in docker.calls] == [64, 512]


def test_a_fault_during_offline_processing_restores_the_weight(tmp_path, config):
    world, result, docker, _, _ = run(tmp_path, config, shares=64, workers=('w00',), scenes=('s1', 's2'),
                                      fault_after=PRE+REC+20)
    assert result['infra_errors']   # the instance faulted
    values = [value for _, value in docker.timeline('c-w00')]
    assert values.count(64) >= 1 and values[-1] == 1024
    assert journal_lines(world)[-1]['requested'] == 1024


def test_a_failed_update_is_named_in_the_journal_and_never_stops_the_campaign(tmp_path, config):
    world, result, docker, _, _ = run(tmp_path, config, shares=64, workers=('w00',), scenes=('s1', 's2'), fail_for=(64,))
    assert result['infra_errors'] == [] and len(result['case_results']) == 2
    lines = journal_lines(world)
    assert lines and all(line['ok'] is False and line['reason'].startswith('CPU_SHARES_UPDATE_FAILED') for line in lines)
    assert all(line['requested'] == 64 and line['previous'] == 1024 for line in lines)
    assert [value for _, _, value in docker.calls] == [64, 64]   # one attempt per task, no retry storm, no spurious restore


def test_a_failed_restore_is_named_and_never_stops_the_campaign(tmp_path, config):
    world, result, docker, _, _ = run(tmp_path, config, shares=64, workers=('w00',), scenes=('s1',), fail_for=(1024,))
    assert result['infra_errors'] == []
    lines = journal_lines(world)
    assert lines[0]['ok'] is True and lines[0]['requested'] == 64 and len(lines) >= 2
    assert all(line['ok'] is False and line['reason'].startswith('CPU_SHARES_UPDATE_FAILED') for line in lines[1:])


def test_a_verify_failure_refuses_the_update_with_a_named_reason(tmp_path):
    def verify():
        raise ValueError('SHARD_CONTAINER_IDENTITY_CHANGED')
    docker = FakeDocker(lambda: 0.)
    target = CpuTarget(container_id='c', original_cpu_shares=1024, verify=verify, docker=docker)
    journal = cpu_module.CpuShareJournal(tmp_path/'j.jsonl')
    shares = cpu_module.ShardCpuShares(worker_id='w00', target=target, post_recording_shares=64, journal=journal)
    shares.want(True)
    assert docker.calls == [] and shares.current == 1024
    line = json.loads((tmp_path/'j.jsonl').read_text())
    assert line['ok'] is False and 'SHARD_CONTAINER_IDENTITY_CHANGED' in line['reason']


def test_a_shard_without_a_bound_container_keeps_its_weight_and_the_campaign_runs(tmp_path, config):
    world, result, docker, _, _ = run(tmp_path, config, shares=64, workers=('w00',), scenes=('s1',), bound=False)
    assert result['infra_errors'] == [] and docker.calls == []


@pytest.mark.parametrize('bad', (0, 1, 1025, -5, True, 64.0, '64'))
def test_out_of_range_or_mistyped_values_are_refused(tmp_path, config, bad):
    world = make_world(tmp_path, config)
    with pytest.raises(ValueError, match='CONTAINER_COORDINATOR_CONFIG_INVALID'):
        ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
                                        scene_manifest=world.manifest, post_recording_cpu_shares=bad)
    target = CpuTarget(container_id='c', original_cpu_shares=1024, verify=lambda: None, docker=lambda argv: None)
    with pytest.raises(ValueError, match='CPU_SHARES_VALUE_INVALID'):
        cpu_module.ShardCpuShares(worker_id='w', target=target, post_recording_shares=bad,
                                  journal=cpu_module.CpuShareJournal(tmp_path/'j'))


@pytest.mark.parametrize('good', (2, 64, 1024))
def test_bounds_are_accepted(tmp_path, config, good):
    world = make_world(tmp_path, config)
    ConcurrentCollectionCoordinator(context=world.context, config=config, case_inputs=world.case_inputs,
                                    scene_manifest=world.manifest, post_recording_cpu_shares=good)
