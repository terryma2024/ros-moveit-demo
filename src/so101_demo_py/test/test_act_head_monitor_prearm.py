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


def prepared(simulation=False):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    from so101_demo.act.head_monitor import digest
    bound=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document()) if simulation else None
    node,observer,_,_=ready_monitor(simulation=simulation);observer._active=False;observer.watchdog_polls.clear()
    options={'simulation_policy':bound} if simulation else {}
    runtime=HeadMonitorRuntime(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()),**options)
    runtime._observer=observer;runtime._configured=True;runtime._configure_future=completed(True)
    runtime.epoch.bind_policy(bound.feedback_values() if simulation else policy(),'a'*64);runtime._watchdog_wall=10.
    runtime._policy={'sha256':'a'*64}
    runtime._node=node;node.get_name=lambda:'controlled_cpu_observer'
    if simulation:
        # This guard fixture supplies a frozen unit-only readback. Actual owned
        # CPU/native readonly service queries are covered in runtime_process.
        runtime._native_policy_readback=dict(unit_only=True,simulation_policy_sha256=digest(bound.readback()))
        runtime._native_policy_readback_sha256=digest(runtime._native_policy_readback)
    return node,runtime,observer


def test_simulation_prearm_progress_uses_supervision_budget_not_reaction_budget():
    from test_act_head_monitor_ros import refresh_simulation_inputs
    node,runtime,observer=prepared(simulation=True)
    try:
        node.wall=10.3;node.sim=1.3;refresh_simulation_inputs(node,observer)
        ack=runtime.prearm_ready({'policy_sha256':'a'*64})
        assert ack['current_inputs_guarded'] is True and not runtime.revoked
        assert runtime._watchdog_wall==10. and runtime.epoch.stage=='POLICY_READY'
    finally:observer.close(timeout_s=1.)


def test_simulation_passive_prearm_inputs_preserve_original_supervision_progress():
    from test_act_head_monitor_ros import refresh_simulation_inputs
    node,runtime,observer=prepared(simulation=True)
    try:
        node.wall=10.3;node.sim=1.3;refresh_simulation_inputs(node,observer)
        ack=runtime.prearm_inputs({'policy_sha256':'a'*64})
        assert ack['inputs_ready'] is True and ack['watchdog_wall_s']==10.
        assert not observer._active and runtime._watchdog_wall==10. and not runtime.revoked
    finally:observer.close(timeout_s=1.)


def test_simulation_prearm_exact_supervision_expiry_closes_original_generation():
    from test_act_head_monitor_ros import refresh_simulation_inputs
    node,runtime,observer=prepared(simulation=True)
    try:
        node.wall=10.5;node.sim=1.5;refresh_simulation_inputs(node,observer)
        with pytest.raises(PermissionError):runtime.prearm_ready({'policy_sha256':'a'*64})
        assert runtime.revoked and runtime.epoch.fault['fault_wall_s']==pytest.approx(10.5,abs=1e-12)
        assert runtime._watchdog_wall==10.
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['missing','changed'])
def test_simulation_prearm_cannot_skip_or_replace_bound_native_readback(damage):
    _,runtime,observer=prepared(simulation=True)
    if damage=='missing':runtime._native_policy_readback=None
    else:runtime._native_policy_readback['simulation_policy_sha256']='f'*64
    try:
        with pytest.raises(PermissionError):runtime.prearm_ready({'policy_sha256':'a'*64})
        assert runtime.revoked and not runtime._prearm_guarded and runtime.epoch.inventory=={}
    finally:observer.close(timeout_s=1.)


def test_cpu_heartbeat_ack_clock_follows_original_copied_progress(monkeypatch):
    from so101_demo.adapters.act import head_monitor_runtime as module
    node,runtime,observer=prepared();node.wall=10.001
    def ack_clock():
        # Another worker can publish immediately after the clock read but
        # before the caller resumes. It must not enter an earlier ACK snapshot.
        runtime._watchdog_wall=10.002;observer._executor_wall=10.002
        return 10.001
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=ack_clock))
    try:
        reply=runtime.heartbeat(dict(wall_s=10.001,executor_wall_s=10.,inference_deadline_wall_s=None))
        assert reply['watchdog_wall_s']==reply['executor_wall_s']==10.
        assert reply['ack_wall_s']==10.001
    finally:observer.close(timeout_s=1.)


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


def input_ready():
    node,runtime,observer=prepared()
    observer._images={1_000_000_000:dict(observer._camera)}
    return node,runtime,observer


def test_passive_cpu_inputs_receipt_does_not_activate_or_refresh_watchdog():
    _,runtime,observer=input_ready()
    try:
        before=runtime._watchdog_wall;polls=list(observer.watchdog_polls)
        ack=runtime.prearm_inputs({'policy_sha256':'a'*64})
        assert ack['inputs_ready'] is True and ack['motion_authority'] is False
        assert not observer._active and not runtime._prearm_guarded
        assert runtime._watchdog_wall==before and list(observer.watchdog_polls)==polls
        assert runtime.epoch.stage=='POLICY_READY'
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('damage',['image_missing','image_old','info_mismatch','info_old',
        'future_source','joint_stale','clock_missing','heartbeat_stale','watchdog_stale','moving','inference_expired'])
def test_passive_cpu_status_waits_for_own_current_originals_without_granting_arm(damage):
    node,runtime,observer=input_ready()
    if damage=='image_missing':observer._images.clear()
    elif damage=='image_old':observer._images[1_000_000_000]['wall_s']=9.94
    elif damage=='info_mismatch':observer._infos={1_100_000_000:dict(observer._infos[1_000_000_000])}
    elif damage=='info_old':observer._infos[1_000_000_000]['wall_s']=9.94
    elif damage=='future_source':node.sim=.999
    elif damage=='joint_stale':observer.port._head_feedback['wall_s']=9.9
    elif damage=='clock_missing':observer._clock=None
    elif damage=='heartbeat_stale':observer._primary['wall_s']=9.98
    elif damage=='watchdog_stale':runtime._watchdog_wall=9.98
    elif damage=='moving':observer.port._head_feedback['velocities']=(.1,)
    else:observer._primary['inference_deadline_wall_s']=9.9
    try:
        ack=runtime.prearm_inputs({'policy_sha256':'a'*64})
        assert ack['inputs_ready'] is False
        assert not observer._active and not runtime._prearm_guarded
        assert not runtime.revoked and runtime.epoch.stage=='POLICY_READY'
    finally:observer.close(timeout_s=1.)


def test_bad_policy_or_revoked_status_cannot_report_ready():
    _,runtime,observer=input_ready()
    try:
        with pytest.raises(PermissionError):runtime.prearm_inputs({'policy_sha256':'b'*64})
        runtime.fault('already revoked',10.)
        with pytest.raises(PermissionError):runtime.prearm_inputs({'policy_sha256':'a'*64})
    finally:observer.close(timeout_s=1.)


def test_authenticated_server_passive_inputs_routes_real_runtime_without_activation(tmp_path):
    _,runtime,observer=input_ready()
    configuration=dict(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))
    protocol=MonitorRuntimeProtocol(configuration,tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=completed(True)
    try:
        ack=protocol.handle({'operation':'PREARM_INPUTS','policy':{'policy_sha256':'a'*64}})
        assert ack['request']=='PREARM_INPUTS' and ack['inputs_ready'] is True
        assert ack['policy_sha256']=='a'*64 and ack['monitor_peer']==_peer(os.getpid())
        assert ack['stage']=='POLICY_READY' and ack['motion_authority'] is False
        assert not observer._active and not runtime._prearm_guarded
        protocol._policy_future=Future()
        with pytest.raises(PermissionError,match='POLICY_ACK_REQUIRED'):
            protocol.handle({'operation':'PREARM_INPUTS','policy':{'policy_sha256':'a'*64}})
    finally:observer.close(timeout_s=1.)


@pytest.mark.parametrize('pending',[False,True])
def test_passive_original_receipt_traverses_actual_authenticated_codec(tmp_path,pending):
    from so101_demo.act.head_monitor_ipc import HeadMonitorCodec
    _,runtime,observer=input_ready()
    if pending:observer._images.clear()
    configuration=dict(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))
    protocol=MonitorRuntimeProtocol(configuration,tmp_path)
    protocol._future=completed(runtime);protocol._policy_future=completed(True)
    try:
        reply=protocol.handle({'operation':'PREARM_INPUTS','policy':{'policy_sha256':'a'*64}})
        scope=dict(secret=b'x'*32,epoch='attempt',generation=5,session_id='session')
        sender=HeadMonitorCodec(**scope,role='monitor');receiver=HeadMonitorCodec(**scope,role='primary')
        received=receiver.decode(sender.encode(reply))
        assert received['inputs_ready'] is (not pending)
        assert received['original_snapshot']['joint']['positions']==list(observer.port._head_feedback['positions'])
        assert received['original_snapshot']['joint']['source_ns']==observer.port._head_feedback['source_ns']
        assert not observer._active and not runtime._prearm_guarded
    finally:observer.close(timeout_s=1.)
