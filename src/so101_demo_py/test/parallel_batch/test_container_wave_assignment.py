"""Exact-W8 reservations are consumed by real durable Coordinator grants."""

import importlib

from test_parallel_batch_coordinator import make,start,finish
from so101_demo.parallel_batch.contracts.common import AttemptStatus


def recover(coordinator,worker):
    deadline=coordinator.snapshot().workers[worker].recovery_deadline_monotonic_s
    coordinator.record_recovery(worker,generation=1,succeeded=True,
        recovery_deadline_monotonic_s=deadline,fenced=True,owned_processes_stopped=True,
        controllers_stopped=True,readmitted=True)


def test_fast_workers_do_not_steal_slow_reservations_and_failed_cases_count_terminal(make):
    module=importlib.import_module('so101_demo.runtime.container_campaign.coordinator')
    scenes=tuple(f'scene-{i:02d}' for i in range(20))
    workers=tuple(f'w{i:02d}' for i in range(8))
    selector=module.QualificationPointSelector(scene_ids=scenes,worker_ids=workers)
    coordinator,clock,results,journal,request=make(points=scenes,workers=8,worker_ids=workers,
                                                  point_selector=selector.choose)
    selector.bind(coordinator)
    counts={worker:[] for worker in workers}
    for worker in workers[:-1]:
        for index in range(2):
            lease=start(coordinator,worker)
            expected=scenes[2*workers.index(worker)+index]
            assert lease.point_id==expected
            status=AttemptStatus.FAILED if index==0 else AttemptStatus.PASSED
            finish(coordinator,results,lease,status)
            recover(coordinator,worker)
            counts[worker].append(lease.point_id)
    for expected in scenes[16:]:
        lease=start(coordinator,'w00')
        assert lease.point_id==expected
        finish(coordinator,results,lease,AttemptStatus.PASSED)
        recover(coordinator,'w00')
        counts['w00'].append(lease.point_id)
    assert coordinator.grant_lease('w00',generation=1) is None
    assert not set(scenes[14:16])&{scene for values in counts.values() for scene in values}
    for expected in scenes[14:16]:
        lease=start(coordinator,'w07')
        assert lease.point_id==expected
        finish(coordinator,results,lease,AttemptStatus.PASSED)
        recover(coordinator,'w07')
        counts['w07'].append(lease.point_id)
    assert all(len(values)>=2 for values in counts.values())
    grants=[event for event in journal.replay().events if event.type=='LEASE_GRANTED']
    assert len(grants)==20 and len({e.payload['response']['point_id'] for e in grants})==20
    assert all(point.terminal for point in coordinator.snapshot().points.values())
