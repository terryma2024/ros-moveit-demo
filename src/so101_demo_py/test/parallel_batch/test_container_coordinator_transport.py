"""Real sockets, local Worker authentication and actual durable Coordinator ACKs."""

import importlib

import pytest

from test_parallel_batch_coordinator import make,gate_summary
from so101_demo.parallel_batch.contracts.common import RunMode,AttemptStatus


def test_real_worker_socket_reaches_durable_grant_start_heartbeat_and_commit(make,tmp_path):
    module=importlib.import_module('so101_demo.runtime.container_campaign.worker_transport')
    coordinator,clock,results,journal,request=make(worker_ids=('w00',))
    control=tmp_path/'private-control';control.mkdir(mode=0o700)
    transport=module.CollectionCoordinatorTransport(coordinator=coordinator,worker_id='w00',
        generation=1,control_root=control,config=coordinator.config)
    transport.start()
    try:
        proxy=module.CollectionCoordinatorProxy(transport.socket_path,transport.token_path,
            worker_id='w00',generation=1,mode=RunMode.EXECUTE,coordinator_epoch=journal.coordinator_epoch)
        lease=proxy.grant_lease('w00',generation=1,request_key='grant')
        assert lease.point_id=='p1'
        lease=proxy.ack_lease(lease,request_key='ack').lease
        lease=proxy.ack_attempt_started(lease,request_key='start',gate_summary=gate_summary(lease)).lease
        assert proxy.heartbeat(lease).point_id=='p1'
        location=str(tmp_path/'external-seal')
        results.sealed[location]=(lease.attempt_id,AttemptStatus.FAILED)
        receipt=proxy.commit_result(lease,location,request_key='commit')
        assert receipt['status'] is AttemptStatus.FAILED
        commits=[e for e in journal.replay().events if e.type=='RESULT_COMMITTED']
        assert len(commits)==1 and commits[0].payload['identity']['point_id']=='p1'
        with pytest.raises(Exception,match='COLLECTION_RPC_OPERATION_REFUSED'):
            proxy._call('replace_resources',expected_generation=1)
    finally:
        transport.close()
    assert transport.socket_path.exists() and transport.token_path.is_file()
    transport.close()


def test_worker_proxy_does_not_retry_a_failed_exchange(make,tmp_path):
    module=importlib.import_module('so101_demo.runtime.container_campaign.worker_transport')
    coordinator,clock,results,journal,request=make(worker_ids=('w00',))
    control=tmp_path/'control';control.mkdir(mode=0o700)
    transport=module.CollectionCoordinatorTransport(coordinator=coordinator,worker_id='w00',
        generation=1,control_root=control,config=coordinator.config)
    proxy=module.CollectionCoordinatorProxy(transport.socket_path,transport.token_path,
        worker_id='w00',generation=1,mode=RunMode.EXECUTE,coordinator_epoch=journal.coordinator_epoch)
    calls=[]
    def lost(message):
        calls.append(message)
        raise OSError('ACK_LOST')
    proxy.client.call=lost
    try:
        with pytest.raises(OSError,match='ACK_LOST'):
            proxy.grant_lease('w00',generation=1,request_key='grant')
        assert len(calls)==1 and coordinator.snapshot().workers['w00'].lease is None
    finally:
        transport.close()
