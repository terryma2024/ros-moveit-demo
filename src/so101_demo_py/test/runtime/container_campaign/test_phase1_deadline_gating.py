"""Phase-1 dispatch gating at the task boundary: a scene is not claimed past the phase-1 deadline, a task already claimed keeps its
own bounds (a recording is not cut short by the phase deadline; the total still caps it)."""

import pytest

from so101_demo.runtime.container_campaign.coordinator import InstanceDispatch
from test_task_coordinator import config, make_world  # noqa: F401 - `config` is a fixture of that module


def dispatch(world, config, *, clock, phase1_deadline_s):
    kwargs = dict(control=None, shard=world.shards[0], assignment=None, journal=None, endpoints=world.endpoints,
        scene_manifest=world.manifest, case_inputs=world.case_inputs, config=config, dispatch_allowed=lambda: True,
        clock=lambda: clock, sleep=None, phase1_deadline_s=phase1_deadline_s)
    return InstanceDispatch(context=world.context, **kwargs)


def test_a_claim_before_the_phase_one_deadline_keeps_the_ordinary_task_deadline(tmp_path, config):
    world = make_world(tmp_path, config)
    plain = dispatch(world, config, clock=1000., phase1_deadline_s=None).prepare_task('s1')
    gated = dispatch(world, config, clock=1000., phase1_deadline_s=1500.).prepare_task('s2')
    assert gated.deadline_monotonic_s == plain.deadline_monotonic_s


def test_a_claim_at_or_after_the_phase_one_deadline_is_refused(tmp_path, config):
    world = make_world(tmp_path, config)
    for clock in (1500., 1500.5):
        with pytest.raises(Exception, match='CONTAINER_PHASE1_DEADLINE_EXPIRED'):
            dispatch(world, config, clock=clock, phase1_deadline_s=1500.).prepare_task('s1')
    assert not (world.shards[0].root/'task-inputs/wave-0-w00-s1.json').exists(), 'nothing is written for a refused claim'


def test_the_coordinator_hands_its_phase_one_deadline_to_every_instance(tmp_path, config):
    world = make_world(tmp_path, config)
    world.coordinator.set_phase1_deadline(1234.)
    assert world.coordinator.phase1_deadline_s == 1234.
    with pytest.raises(ValueError, match='CONTAINER_COORDINATOR_CONFIG_INVALID'):
        world.coordinator.set_phase1_deadline(-1.)
