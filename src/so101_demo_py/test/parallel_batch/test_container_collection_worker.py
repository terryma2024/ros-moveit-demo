"""Real Worker/Coordinator case transition keeps the instance generation fixed."""

import importlib
from types import SimpleNamespace

import pytest

from test_parallel_batch_coordinator import make,start,finish
from so101_demo.parallel_batch.contracts.common import AttemptStatus
from so101_demo.act.parallel_collection import ActFixedCollectionWorkload


@pytest.mark.parametrize('case_stopped',[True,False])
def test_case_transition_does_not_restart_instance_or_fence_shared_model(make,case_stopped):
    module=importlib.import_module('so101_demo.runtime.container_campaign.collection_worker')
    coordinator,clock,results,journal,request=make(worker_ids=('w00',))
    lease=start(coordinator,'w00')
    finish(coordinator,results,lease,AttemptStatus.FAILED)
    calls=[]
    runtime=SimpleNamespace(prepare_next_case=lambda current,**kwargs:calls.append((current,kwargs)) or case_stopped)
    class Receipts:
        def write_recovery_receipt(self,current,**kwargs):return 'original-case-receipt'
        def verify_recovery_receipt(self,*args,**kwargs):return True
    def forbidden(*args,**kwargs):pytest.fail('case transition fenced a campaign-lifetime model client')
    worker=module.ContainerCollectionWorker(dict(coordinator=coordinator,broker=SimpleNamespace(cancel_generation=forbidden),
        runtime=runtime,results=Receipts(),clock=clock,config=coordinator.config,worker_id='w00',generation=1,
        workload=ActFixedCollectionWorkload(scene_ids=('p1','p2'))))
    deadline=coordinator.snapshot().workers['w00'].recovery_deadline_monotonic_s
    assert worker._recover(lease,deadline,physical_action_proven_absent=False) is case_stopped
    assert worker._generation==1 and coordinator.snapshot().workers['w00'].generation==1
    if case_stopped:
        next_lease=coordinator.grant_lease('w00',generation=1)
        assert next_lease.point_id=='p2'
    else:
        assert worker._quarantined and coordinator.grant_lease('w00',generation=1) is None
