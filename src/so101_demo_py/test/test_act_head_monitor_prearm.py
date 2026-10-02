"""Current own CPU inputs are a separate prerequisite from a stopped-window ACK."""
from concurrent.futures import Future
import os
from types import SimpleNamespace
import pytest
from test_act_head_monitor_ros import ready_monitor
from test_act_head_feedback_freshness import policy
from so101_demo.adapters.act.head_monitor_runtime import HeadMonitorRuntime,_peer
from so101_demo.adapters.act.head_monitor_process import MonitorRuntimeProtocol


def completed(value):
    future=Future();future.set_result(value);return future


def prepared():
    node,observer,_,_=ready_monitor();observer._active=False;observer.watchdog_polls.clear()
    runtime=HeadMonitorRuntime(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))
    runtime._observer=observer;runtime._configured=True;runtime._configure_future=completed(True)
    runtime.epoch.bind_policy(policy(),'a'*64);runtime._watchdog_wall=10.
    runtime._policy={'sha256':'a'*64}
    runtime._node=node;node.get_name=lambda:'controlled_cpu_observer'
    return node,runtime,observer


def prearm(runtime,record):
    # Existing POLICY_READY acknowledges the measured window without current
    # admission checks. This baseline grants no native or SDK authority.
    method=getattr(runtime,'prearm_ready',None)
    if method is None:return dict(stage='POLICY_READY',motion_authority=False)
    return method(record)


def test_prearm_checks_current_originals_without_granting_armed_ready():
    _,runtime,observer=prepared()
    try:
        polls=list(observer.watchdog_polls)
        ack=prearm(runtime,{'policy_sha256':'a'*64})
        assert observer._active and ack['current_inputs_guarded'] is True
        assert ack['stage']=='POLICY_READY' and ack['motion_authority'] is False
        assert runtime.epoch.stage=='POLICY_READY' and not runtime.epoch.inventory
        assert list(observer.watchdog_polls)==polls
        assert runtime._watchdog_wall==10.
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['joint_source','moving','camera','clock','executor','heartbeat','watchdog','policy'])
def test_stopped_policy_ack_cannot_hide_invalid_current_prearm_inputs(damage):
    node,runtime,observer=prepared()
    if damage=='joint_source':node.sim=1.1
    elif damage=='moving':observer.port._head_feedback['velocities']=(.1,)
    elif damage=='camera':observer._camera=None;observer._images.clear()
    elif damage=='clock':observer._clock=None
    elif damage=='executor':observer._executor_wall=9.98
    elif damage=='heartbeat':observer._primary=None
    elif damage=='watchdog':runtime._watchdog_wall=9.98
    record={'policy_sha256':'b'*64 if damage=='policy' else 'a'*64}
    try:
        with pytest.raises(PermissionError):prearm(runtime,record)
        assert runtime.revoked and observer.port._head_policy_binding_failed
    finally:observer.close(timeout_s=1.)


def test_server_protocol_routes_prearm_only_after_actual_policy_validation(tmp_path):
    _,runtime,observer=prepared()
    config=dict(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))
    protocol=MonitorRuntimeProtocol(config,tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=completed(True)
    try:
        ack=protocol.handle({'operation':'PREARM_READY','policy':{'policy_sha256':'a'*64}})
        assert ack['request']=='PREARM_READY' and ack['current_inputs_guarded'] is True
        assert ack['motion_authority'] is False and ack['stage']=='POLICY_READY'
        assert ack['monitor_peer']==_peer(os.getpid()) and runtime.epoch.stage=='POLICY_READY'
    finally:observer.close(timeout_s=1.)


def test_repeated_prearm_rpc_cannot_refresh_a_stalled_owned_watchdog():
    node,runtime,observer=prepared()
    try:
        prearm(runtime,{'policy_sha256':'a'*64})
        node.wall=10.011;observer.executor_progress()
        observer.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,inference_deadline_wall_s=None))
        with pytest.raises(PermissionError):prearm(runtime,{'policy_sha256':'a'*64})
        assert runtime._watchdog_wall==10. and not observer.watchdog_polls and runtime.revoked
        assert runtime.epoch.fault['fault_wall_s']==pytest.approx(10.010,abs=1e-12)
    finally:observer.close(timeout_s=1.)


def test_pending_policy_validation_cannot_activate_prearm_via_server_protocol(tmp_path):
    _,runtime,observer=prepared()
    config=dict(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))
    protocol=MonitorRuntimeProtocol(config,tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=Future()
    try:
        with pytest.raises(PermissionError,match='POLICY_ACK_REQUIRED'):
            protocol.handle({'operation':'PREARM_READY','policy':{'policy_sha256':'a'*64}})
        assert not observer._active and not runtime._prearm_guarded
    finally:observer.close(timeout_s=1.)


def test_three_reported_identities_cannot_skip_the_current_prearm_guard():
    _,runtime,observer=prepared();queries=[]
    identity=dict(generation=5,incarnation='controller',boot='boot')
    owner=_peer(os.getppid())
    def query():queries.append(True);return dict(identity)
    runtime._revoker=SimpleNamespace(native_owner=owner,identity=query)
    runtime._provisions={'main':{'sha256':'b'*64},'primary_fault':{'sha256':'c'*64}}
    reports={key:dict(identity=dict(identity),native_owner=owner,provision_sha256=runtime._provisions[key]['sha256'])
             for key in ('main','primary_fault')}
    try:
        with pytest.raises(PermissionError,match='READY_STAGE_INVALID'):runtime.armed_ready(reports)
        assert not queries and runtime.epoch.stage=='POLICY_READY' and not observer._active
    finally:observer.close(timeout_s=1.)
