"""Functional eight-worker debug runs are planned like a qualification wave, but never as the gate plane."""

import pytest

WORKERS = tuple(f'w{index:02d}' for index in range(8))


def scenes(count):
    return tuple(f'functional-{index:02d}' for index in range(count))


def test_sixteen_functional_scenes_on_eight_workers_are_two_adjacent_cases_each():
    from so101_demo.act.parallel_collection import plan_campaign_waves, reserve_qualification_scenes
    plans = plan_campaign_waves(scenes(16),WORKERS,plane='functional')
    assert [plan['wave_index'] for plan in plans] == [0]
    assert plans[0]['scene_ids'] == list(scenes(16))
    assignment = plans[0]['assignment']
    assert assignment['reserved_by_worker'] == {
        worker:scenes(16)[2*index:2*index+2] for index,worker in enumerate(WORKERS)}
    assert assignment['surplus'] == ()
    # same shape as a qualification wave: a mapping over exactly the eight workers, tuple values, tuple surplus
    reference = reserve_qualification_scenes(scenes(20),WORKERS)
    assert set(assignment) == set(reference) and list(assignment['reserved_by_worker']) == list(WORKERS)


def test_eight_functional_scenes_on_eight_workers_are_one_case_each():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    assignment = plan_campaign_waves(scenes(8),WORKERS,plane='functional')[0]['assignment']
    assert assignment['reserved_by_worker'] == {worker:(scenes(8)[index],) for index,worker in enumerate(WORKERS)}
    assert assignment['surplus'] == ()


@pytest.mark.parametrize('workers',[1,2])
def test_functional_runs_on_fewer_workers_keep_dynamic_assignment(workers):
    from so101_demo.act.parallel_collection import plan_campaign_waves
    plans = plan_campaign_waves(scenes(8),WORKERS[:workers],plane='functional')
    assert [plan['assignment'] for plan in plans] == [None]


def test_gate_plane_keeps_two_reserved_and_four_surplus_per_wave():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    forty = tuple(f'gate-{index:02d}' for index in range(40))
    plans = plan_campaign_waves(forty,WORKERS,plane='gate')
    assert len(plans) == 2 and all(len(plan['assignment']['surplus']) == 4 for plan in plans)


def test_formal_plane_has_no_reservations():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    assert [plan['assignment'] for plan in plan_campaign_waves(scenes(30),WORKERS,plane=None)] == [None,None]


@pytest.mark.parametrize('count',[0,7,9,10,20,24,40])
def test_functional_reservation_refuses_other_scene_counts(count):
    from so101_demo.act.parallel_collection import reserve_functional_scenes
    with pytest.raises(ValueError,match='FUNCTIONAL_RESERVATIONS_INVALID'):
        reserve_functional_scenes(scenes(count),WORKERS)


@pytest.mark.parametrize('workers',[WORKERS[:2],WORKERS[::-1],WORKERS[:7],WORKERS+('w08',)])
def test_functional_reservation_needs_exactly_the_eight_ordered_workers(workers):
    from so101_demo.act.parallel_collection import reserve_functional_scenes
    with pytest.raises(ValueError,match='FUNCTIONAL_RESERVATIONS_INVALID'):
        reserve_functional_scenes(scenes(16),workers)


def test_scheduling_check_requires_each_workers_own_reserved_count():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    from so101_demo.runtime.container_campaign.result_verifier import check_wave_scheduling
    for count,per_worker in ((8,1),(16,2)):
        plan = plan_campaign_waves(scenes(count),WORKERS,plane='functional')[0]
        by_scene = {scene:dict(worker_id=worker,collected_monotonic_s=float(index),assigned_monotonic_s=0.0)
                    for worker,reserved in plan['assignment']['reserved_by_worker'].items()
                    for index,scene in enumerate(reserved)}
        assert all(len(v) == per_worker for v in plan['assignment']['reserved_by_worker'].values())
        check_wave_scheduling(plan,by_scene,{worker:None for worker in WORKERS},True)
        missing = dict(by_scene)
        gone = plan['assignment']['reserved_by_worker']['w03'][0]
        del missing[gone]
        with pytest.raises(ValueError):
            check_wave_scheduling(plan,missing,{worker:None for worker in WORKERS},True)


# ---- the spot-check plane: one worker, one scene, no reservation, no two-tasks-per-instance owed count -------------------------

def test_a_spot_check_campaign_is_one_unreserved_wave_marked_with_its_plane():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    plans = plan_campaign_waves(('spot-00',), ('w00',), plane='spot_check')
    assert plans == [dict(wave_index=0, scene_ids=['spot-00'], assignment=None, plane='spot_check')]
    # the marker belongs to the spot-check plane only: every other plane's plans keep their exact keys
    for plane, count in (('gate', 20), ('functional', 8), (None, 8)):
        assert all('plane' not in plan for plan in plan_campaign_waves(scenes(count), WORKERS, plane=plane))
    # eight workers never turn a spot check into a reserved wave
    assert plan_campaign_waves(scenes(8), WORKERS, plane='spot_check')[0]['assignment'] is None
    with pytest.raises(ValueError, match='CAMPAIGN_ROUND_INVALID'):
        plan_campaign_waves(('spot-00',), ('w00',), plane='spot_check', recording_round=1)


def test_the_two_tasks_per_instance_count_is_owed_by_every_plane_but_the_spot_check():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    from so101_demo.runtime.container_campaign.result_verifier import check_wave_scheduling
    by_scene = {'spot-00': dict(worker_id='w00', collected_monotonic_s=1.0, assigned_monotonic_s=0.0)}
    spot = plan_campaign_waves(('spot-00',), ('w00',), plane='spot_check')[0]
    check_wave_scheduling(spot, by_scene, {'w00': None}, True)
    # the same one-scene wave on the functional plane (no plane marker) still owes two tasks to its instance
    plain = plan_campaign_waves(('spot-00',), ('w00',), plane='functional')[0]
    with pytest.raises(ValueError, match='INSTANCE_SHORT:w00'):
        check_wave_scheduling(plain, by_scene, {'w00': None}, True)
