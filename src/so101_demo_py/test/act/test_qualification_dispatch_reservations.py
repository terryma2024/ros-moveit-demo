"""A qualification wave reserves two ordered cases for every exact-W8 Worker."""

import asyncio

import pytest


def reserve(scenes, workers):
    from so101_demo.act.parallel_collection import reserve_qualification_scenes
    return reserve_qualification_scenes(scenes,workers)


@pytest.mark.parametrize('slow_worker', range(8))
def test_fast_workers_cannot_consume_slow_workers_reserved_cases(slow_worker):
    scenes = tuple(f'scene-{index:02d}' for index in range(20))
    workers = tuple(f'w{index:02d}' for index in range(8))
    assignment = reserve(scenes,workers)
    assert assignment['reserved_by_worker'] == {
        worker:scenes[2*index:2*index+2] for index,worker in enumerate(workers)}
    assert assignment['surplus'] == scenes[16:]
    async def run():
        release = [asyncio.Event() for _ in workers]
        started = [asyncio.Event() for _ in workers]
        completions = {worker:[] for worker in workers}
        surplus = asyncio.Queue()
        for scene in assignment['surplus']:
            surplus.put_nowait(scene)
        async def worker_run(index,worker):
            started[index].set()
            await release[index].wait()
            for scene in assignment['reserved_by_worker'][worker]:
                await asyncio.sleep(0)
                completions[worker].append(scene)
            while not surplus.empty():
                completions[worker].append(surplus.get_nowait())
        tasks = [asyncio.create_task(worker_run(index,worker)) for index,worker in enumerate(workers)]
        for event in started:
            await event.wait()
        for index,event in enumerate(release):
            if index != slow_worker:
                event.set()
        await asyncio.gather(*(task for index,task in enumerate(tasks) if index != slow_worker))
        reserved_slow = set(assignment['reserved_by_worker'][workers[slow_worker]])
        assert not any(reserved_slow & set(values) for worker,values in completions.items()
                       if worker != workers[slow_worker])
        release[slow_worker].set()
        await tasks[slow_worker]
        assert all(len(values)>=2 for values in completions.values())
        flat = [scene for values in completions.values() for scene in values]
        assert len(flat) == len(set(flat)) == 20
        assert set(flat) == set(scenes)
    asyncio.run(run())


@pytest.mark.parametrize('problem',['short_wave','long_wave','duplicate_scene','empty_scene',
                                  'not_tuple','w2','duplicate_worker','unordered_worker'])
def test_reservations_refuse_any_other_wave_or_worker_shape(problem):
    scenes = tuple(f'scene-{index}' for index in range(20))
    workers = tuple(f'w{index:02d}' for index in range(8))
    if problem == 'short_wave': scenes = scenes[:19]
    elif problem == 'long_wave': scenes += ('extra',)
    elif problem == 'duplicate_scene': scenes = scenes[:19]+(scenes[0],)
    elif problem == 'empty_scene': scenes = scenes[:19]+('',)
    elif problem == 'not_tuple': scenes = list(scenes)
    elif problem == 'w2': workers = workers[:2]
    elif problem == 'duplicate_worker': workers = workers[:7]+(workers[0],)
    elif problem == 'unordered_worker': workers = workers[::-1]
    with pytest.raises(ValueError,match='QUALIFICATION_RESERVATIONS_INVALID'):
        reserve(scenes,workers)
