"""Irreversible scoped fault receipts, not readiness or native close receipts."""
from types import SimpleNamespace
import os
import time
import pytest
from test_act_head_monitor_prearm import prepared,completed
from so101_demo.adapters.act.head_monitor_process import MonitorRuntimeProtocol,MonitorProcess
from so101_demo.adapters.act.head_monitor_runtime import _peer


def protocol(tmp_path,runtime):
    value=MonitorRuntimeProtocol(dict(epoch='attempt',generation=5,session_id='session',
        primary=_peer(os.getppid())),tmp_path)
    value._future=completed(runtime)
    return value


def test_actual_protocol_fault_returns_revoked_receipt_without_readiness(tmp_path):
    _,runtime,observer=prepared();wall=time.monotonic()
    try:
        ack=protocol(tmp_path,runtime).handle(dict(operation='FAULT',fault=dict(reason='controlled root fault',fault_wall_s=wall)))
        assert ack['stage']=='REVOKED' and ack['motion_authority'] is False
        assert ack['fault']==dict(reason='controlled root fault',fault_wall_s=wall)
        assert ack['request']=='FAULT' and ack['epoch']=='attempt' and ack['generation']==5
        assert runtime.revoked and runtime._fault_event.is_set() and observer.port._head_policy_binding_failed
        assert wall<=ack['ack_wall_s']<=time.monotonic()
        assert runtime.epoch.inventory=={}
    finally:observer.close(timeout_s=1.)


def test_repeated_authenticated_fault_can_only_tighten_earliest_origin(tmp_path):
    _,runtime,observer=prepared();wall=time.monotonic()
    try:
        runtime.fault('earlier CPU fault',wall-.001)
        value=protocol(tmp_path,runtime)
        later=value.handle(dict(operation='FAULT',fault=dict(reason='later root fault',fault_wall_s=wall)))
        assert later['fault']==dict(reason='earlier CPU fault',fault_wall_s=wall-.001)
        earlier=value.handle(dict(operation='FAULT',fault=dict(reason='earliest root fault',fault_wall_s=wall-.002)))
        assert earlier['fault']==dict(reason='earliest root fault',fault_wall_s=wall-.002)
        assert runtime.revoked and observer.failed and runtime.epoch.stage=='REVOKED'
        with pytest.raises(PermissionError):value.handle(dict(operation='DISPATCH',binding={}))
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['none','extra','future','boolean','missing'])
def test_revoked_heartbeat_cannot_renew_originals_or_inference_inventory(tmp_path,damage):
    _,runtime,observer=prepared();wall=time.monotonic()
    original=dict(reason='earliest CPU expiry',fault_wall_s=wall-.001)
    runtime.fault(**dict(reason=original['reason'],wall=original['fault_wall_s']))
    previous=observer._primary;executor=observer._executor_wall;watchdog=runtime._watchdog_wall
    record=dict(wall_s=wall,executor_wall_s=wall,inference_deadline_wall_s=wall-.001)
    if damage=='extra':record['new_lease']=True
    elif damage=='future':record['wall_s']=wall+1
    elif damage=='boolean':record['executor_wall_s']=True
    elif damage=='missing':del record['inference_deadline_wall_s']
    try:
        if damage=='none':
            reply=protocol(tmp_path,runtime).handle(dict(operation='HEARTBEAT',heartbeat=record))
            assert reply['stage']=='REVOKED' and reply['heartbeat_rejected'] is True
            assert reply['fault']==original and reply['motion_authority'] is False
            assert reply['ack_wall_s']>=wall
        else:
            with pytest.raises((PermissionError,ValueError)):
                protocol(tmp_path,runtime).handle(dict(operation='HEARTBEAT',heartbeat=record))
        assert observer._primary is previous and observer._executor_wall==executor
        assert runtime._watchdog_wall==watchdog and runtime._fault==original
        assert runtime.epoch.inventory=={} and runtime.epoch.stage=='REVOKED'
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('observer_raises',[False,True])
def test_concurrent_revocation_during_heartbeat_returns_only_original_negative(tmp_path,observer_raises):
    _,runtime,observer=prepared();wall=time.monotonic();calls=[]
    fault=dict(reason='concurrent CPU expiry',fault_wall_s=wall)
    def concurrent(record):
        calls.append(record);runtime.fault(fault['reason'],fault['fault_wall_s'])
        if observer_raises:raise PermissionError('HEAD_MONITOR_ROS_REVOKED')
    observer.heartbeat=concurrent
    record=dict(wall_s=wall,executor_wall_s=wall,inference_deadline_wall_s=wall)
    try:
        reply=protocol(tmp_path,runtime).handle(dict(operation='HEARTBEAT',heartbeat=record))
        assert reply['stage']=='REVOKED' and reply['heartbeat_rejected'] is True
        assert reply['fault']==fault and reply['motion_authority'] is False
        assert calls==[record] and runtime.revoked and runtime.epoch.inventory=={}
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('operation',['FAULT','HEARTBEAT','DISPATCH'])
def test_client_accepts_revoked_receipt_only_for_fault_operation(operation):
    monitor=object.__new__(MonitorProcess);monitor._closed=False;monitor._runtime_requested=True
    monitor._identity=_peer(os.getpid());monitor.is_alive=lambda:True
    closed=[];reply=dict(request=operation,stage='REVOKED',monitor_peer=monitor.identity,
        purpose='calibration',epoch='attempt',generation=5,session_id='session',motion_authority=False)
    monitor._channel=SimpleNamespace(exchange=lambda request:reply,close=lambda:closed.append(True),
        _codec=SimpleNamespace(epoch='attempt',generation=5,session_id='session'))
    if operation=='FAULT':
        assert monitor.request_runtime(dict(operation=operation))==reply and not closed
    else:
        with pytest.raises(PermissionError):monitor.request_runtime(dict(operation=operation))
        assert closed==[True]


@pytest.mark.parametrize('damage',['future','negative','nan','infinity','boolean','reason','extra'])
def test_invalid_original_fault_notice_revokes_and_cannot_ack(tmp_path,damage):
    _,runtime,observer=prepared();wall=time.monotonic()
    record=dict(reason='controlled root fault',fault_wall_s=wall)
    if damage=='future':record['fault_wall_s']=wall+1.
    elif damage=='negative':record['fault_wall_s']=-1.
    elif damage=='nan':record['fault_wall_s']=float('nan')
    elif damage=='infinity':record['fault_wall_s']=float('inf')
    elif damage=='boolean':record['fault_wall_s']=True
    elif damage=='reason':record['reason']=''
    else:record['unexpected']=True
    try:
        with pytest.raises(ValueError,match='HEAD_MONITOR_FAULT_NOTICE_INVALID'):
            protocol(tmp_path,runtime).handle(dict(operation='FAULT',fault=record))
        assert runtime.revoked and observer.failed and observer.port._head_policy_binding_failed
        assert runtime._fault['reason']=='HEAD_MONITOR_FAULT_NOTICE_INVALID'
    finally:observer.close(timeout_s=1.)
