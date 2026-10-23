"""A scene claimed at the phase-1 deadline is not a fault: it stays unrecorded (missing evidence through the partial-wave path), the
wave reports no infrastructure error and the scene is claimable state PENDING again."""

import pytest

from so101_demo.runtime.container_campaign.coordinator import PENDING
from test_phase1_deadline_gating import dispatch
from test_task_coordinator import config, make_world, run_wave  # noqa: F401 - `config` is a fixture of that module


@pytest.mark.parametrize("gated", [False, True])
def test_a_claim_past_the_phase_one_deadline_leaves_the_scene_unrecorded_without_an_infra_error(tmp_path, config, gated):
    world = make_world(tmp_path, config, workers=('w00', 'w01') if gated else ('w00',), scenes=('s1', 's2'))
    if gated:
        world.coordinator.max_tasks_in_flight = 1
    world.coordinator.set_phase1_deadline(world.clock.now)      # the deadline has passed by the first claim
    outcome = run_wave(world)
    assert outcome['infra_errors'] == [], outcome['infra_errors']
    assert outcome['case_results'] == [], "nothing was recorded"
    assert not list((world.shards[0].root/'task-inputs').glob('*.json')), "no task input was written for a refused claim"


def test_the_assignment_gives_a_released_scene_back(tmp_path, config):
    from so101_demo.runtime.container_campaign.coordinator import WaveAssignment

    assignment = WaveAssignment(scene_ids=('s1', 's2'), worker_ids=('w00',))
    scene = assignment.next_scene('w00')
    assignment.release(scene)
    assert assignment.states[scene] == PENDING and assignment.next_scene('w00') == scene
