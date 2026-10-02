"""Owned primary workers and original shared inputs; no simulator qualification."""
import os
import json
import secrets
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from test_act_head_monitor_ros import Node
from test_act_head_feedback_freshness import policy,sample
from so101_demo.adapters.act.ros_execution import RosControllerPort
from so101_demo.adapters.act.head_monitor_ros import _NoMotion
from so101_demo.adapters.act.head_monitor_process import MonitorProcess
from so101_demo.adapters.act.head_monitor_runtime import _peer
from so101_demo.adapters.act.head_original_router import HeadOriginalRouter
from so101_demo.adapters.act.head_revocation import NativeRevocationClient

try:
    from so101_demo.adapters.act.head_primary_supervisor import HeadPrimarySupervisor
except ModuleNotFoundError:
    class HeadPrimarySupervisor:
        def __init__(self,**kw):self.port=kw['port'];self.failed=False;self.threads=[];self.observer=None
        def start(self):pass
        def fault(self,*args):pass
        def close(self):return {}


def setup(tmp_path,native_damage=None):
    node=Node();node.create_timer=lambda period,callback,**kw:SimpleNamespace(period=period,callback=callback,**kw)
    node.destroy_timer=lambda timer:True
    events=[];requests=[]
    port=RosControllerPort(node,_NoMotion(),('neck_yaw_joint',),stop_velocity_rad_s=.002,max_age_s=.05,
        feedback_policy=policy())
    port._feedback(sample())
    monitor=object.__new__(MonitorProcess);monitor._identity=_peer(os.getppid())
    monitor.is_alive=lambda:True
    def reply(operation,stage,**kw):
        return dict(request=operation,stage=stage,epoch='attempt',generation=5,session_id='session',
            monitor_peer=monitor.identity,purpose='calibration',motion_authority=False,**kw)
    def request(value):
        requests.append(value);return reply(value['operation'],'POLICY_READY')
    monitor.request_runtime=request
    owner=_peer(os.getpid())
    # UNIX endpoint length stays production-valid; no socket is created here.
    endpoint=Path('/tmp')/('hs-primary-test-'+uuid.uuid4().hex[:8])
    revoker=NativeRevocationClient(endpoint/'neck-primary-revoke.sock',capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,timeout_s=.002)
    revoker.close_strict=lambda:dict(ack_validated=True,native_owner=owner,generation=5)
    refs={key:dict(path=str(endpoint/(key+'.provision')),socket_path=str(endpoint/(stem+'.sock')),sha256=letter*64)
        for key,stem,letter in [('main','neck','b'),('primary_fault','neck-primary-revoke','c'),('monitor_fault','neck-revoke','d')]}
    origin=dict(revoker.transport_origin)
    if native_damage=='path':origin['path']='/different/library.so'
    elif native_damage=='sha256':origin['sha256']='e'*64
    elif native_damage=='abi':origin['abi']=2
    elif native_damage=='clock':origin['clock']='CLOCK_REALTIME'
    configuration=reply('CONFIGURATION','CONFIGURED',provisions=refs,dependencies={'controlled':True},
        native_transport=origin)
    ack=reply('POLICY_STATUS','POLICY_READY',policy_sha256='a'*64)
    router=HeadOriginalRouter(port,lambda *args:None)
    try:
        sup=HeadPrimarySupervisor(node=node,port=port,router=router,monitor=monitor,revoker=revoker,
            epoch='attempt',generation=5,session_id='session',policy_reference={'path':str(tmp_path/'policy.json'),'sha256':'a'*64},
            policy_ack=ack,configuration_ack=configuration,stop_latency_s=.07,camera_max_age_s=.05,
            camera_frame_id='head_camera_frame',emit=lambda event,**kw:events.append((event,kw)))
    except BaseException:
        port.close_head_io(timeout_s=1.);raise
    return node,port,sup,requests,events,revoker


@pytest.mark.parametrize('damage',['path','sha256','abi','clock'])
def test_primary_refuses_cpu_with_different_installed_native_transport(tmp_path,damage):
    value=None
    try:
        with pytest.raises(PermissionError):value=setup(tmp_path,native_damage=damage)
    finally:
        if value is not None:value[2].close();value[1].close_head_io(timeout_s=1.)


def test_root_completion_discharges_both_original_and_earliest_cpu_deadlines(tmp_path):
    node,port,sup,_,events,_=setup(tmp_path)
    sup.observer.monotonic=lambda:node.wall
    try:
        sup.inference_deadline(10.05)
        sup.inference_deadline(10.048)
        node.wall=10.047
        sup.inference_deadline(None)
        receipt=next(row[1]['receipt'] for row in events if row[0]=='INFERENCE_DEADLINES_DISCHARGED')
        assert receipt['deadlines_ns']==[10_048_000_000,10_050_000_000]
        assert sup._inference_deadline is None
    finally:sup.close();port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',['expiry','extension','duplicate','revoked_clear'])
def test_selected_original_dispatch_deadline_cannot_extend_or_clear_late(tmp_path,damage):
    node,port,sup,_,_,_=setup(tmp_path)
    sup.observer.monotonic=lambda:node.wall
    try:
        sup.dispatch_observation_deadline(10.05)
        if damage=='expiry':node.wall=10.05
        elif damage=='revoked_clear':sup.fault('controlled prior revoke',10.)
        with pytest.raises(PermissionError):
            sup.dispatch_observation_deadline(10.06 if damage=='extension' else
                10.05 if damage=='duplicate' else None)
        assert sup.failed and sup._dispatch_observation_deadline==10.05
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_selected_original_deadline_is_separate_from_completed_cuda_deadline(tmp_path):
    node,port,sup,_,_,_=setup(tmp_path)
    sup.observer.monotonic=lambda:node.wall
    try:
        sup.inference_deadline(10.05);sup.inference_deadline(None)
        sup.dispatch_observation_deadline(10.05)
        node.wall=10.049;sup.dispatch_observation_deadline(None)
        assert sup._dispatch_observation_deadline is None and not sup.failed
        assert sup.observer._completed_inference_deadlines
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_expired_selected_frame_faults_even_when_its_cuda_job_was_completed(tmp_path):
    node,port,sup,_,_,_=setup(tmp_path)
    sup.observer.monotonic=lambda:node.wall
    try:
        sup.inference_deadline(10.05);sup.inference_deadline(None)
        sup.dispatch_observation_deadline(10.05);node.wall=10.05
        with pytest.raises(PermissionError):sup._check_dispatch_observation_deadline()
        assert sup.failed and sup._fault['fault_wall_s']==10.05
        assert port._head_policy_binding_failed and sup._fault_event.is_set()
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_root_cannot_clear_a_deadline_after_completion_boundary(tmp_path):
    node,port,sup,_,_,_=setup(tmp_path)
    sup.observer.monotonic=lambda:node.wall
    try:
        sup.inference_deadline(10.05)
        node.wall=10.05
        with pytest.raises(PermissionError):sup.inference_deadline(None)
        assert sup.failed and sup._inference_deadline==10.05
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_four_owned_workers_and_real_executor_tick_feed_actual_heartbeat(tmp_path):
    node,port,sup,requests,_,_=setup(tmp_path)
    try:
        sup.start();sup.timer.callback()
        deadline=time.monotonic()+.1
        while not requests and time.monotonic()<deadline:time.sleep(.001)
        assert len(sup.threads)==4 and all(thread.name.startswith('head-primary-') for thread in sup.threads)
        assert requests and requests[0]['operation']=='HEARTBEAT'
        heartbeat=requests[0]['heartbeat']
        assert heartbeat['executor_wall_s']<=heartbeat['wall_s']
        assert heartbeat['executor_wall_s']==sup.observer._executor_wall
        assert heartbeat['inference_deadline_wall_s'] is None
        assert sup.observer.port is port and sup.timer.period==.002
        assert len([row for row in node.subscriptions if row[1]=='/joint_states'])==1
        assert not any(row[1] in ('/clock','/head_camera/color','/head_camera/camera_info') for row in node.subscriptions)
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_primary_fault_closes_admission_before_callback_io(tmp_path):
    _,port,sup,_,_,_=setup(tmp_path)
    try:
        sup.fault('controlled fault',time.monotonic())
        assert sup.failed and port._head_policy_binding_failed
        assert sup._fault_event.is_set()
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_native_close_and_all_unknown_cancel_results_run_concurrently(tmp_path):
    node,port,sup,_,events,revoker=setup(tmp_path);release=threading.Event();entered=threading.Event()
    def close():entered.set();release.wait(.3);return dict(ack_validated=True)
    revoker.close_strict=close
    gids=[str(uuid.uuid4()),str(uuid.uuid4())]
    for gid in gids:port._goals[gid]=dict(accepted=None,handle=None,result=None,cancel_requested=False,cancel_ack=False,error=None)
    try:
        sup.start();sup.timer.callback();sup.fault('controlled fault',time.monotonic())
        assert entered.wait(.1)
        deadline=time.monotonic()+.1
        while len(node.calls)<4 and time.monotonic()<deadline:time.sleep(.001)
        assert len(node.calls)==4 and not release.is_set()
        observed={bytes(row[2].goal_info.goal_id.uuid if hasattr(row[2],'goal_info') else row[2].goal_id.uuid) for row in node.calls}
        assert observed=={uuid.UUID(gid).bytes for gid in gids}
        assert all(port.accepted(gid) is None for gid in gids)
        assert not any(event=='STOP_CONFIRMED' for event,_ in events)
    finally:release.set();sup.close();port.close_head_io(timeout_s=1.)


def test_close_requires_all_owned_threads_to_exit_before_retirement_receipt(tmp_path):
    _,port,sup,_,_,_=setup(tmp_path);release=threading.Event()
    thread=threading.Thread(target=release.wait,name='controlled-owned-primary');thread.start()
    sup.threads.append(thread)
    try:
        with pytest.raises(PermissionError,match='RETIRE_UNCONFIRMED'):sup.close()
        assert thread.is_alive()
    finally:release.set();thread.join(1.);sup.close();port.close_head_io(timeout_s=1.)


def test_retirement_receipt_serializes_original_stop_observations(tmp_path):
    _,port,sup,_,_,_=setup(tmp_path)
    port.stop_predicate_observations.append(dict(stopped=False,goal_states={}))
    try:
        receipt=sup.close()
        assert json.loads(json.dumps(receipt,allow_nan=False))['stop_observations']==[dict(stopped=False,goal_states={})]
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_real_heartbeat_in_flight_across_explicit_arm_transition_cannot_grant_ready(tmp_path):
    _,port,sup,_,_,_=setup(tmp_path)
    try:
        sup._started_wall=time.monotonic();sup.observer.executor_progress()
        def transition(record):
            assert record['operation']=='HEARTBEAT' and not sup.ready
            sup._arming=True;sup._shutdown.set()
            return dict(request='HEARTBEAT',stage='ARMED_READY',epoch='attempt',generation=5,
                session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',motion_authority=False)
        sup.monitor.request_runtime=transition
        sup._heartbeat()
        assert not sup.failed and not sup.ready and sup.epoch.stage=='POLICY_READY'
    finally:sup.close();port.close_head_io(timeout_s=1.)


def guarded(sup,port):
    """Controlled original callbacks and private ACK, never a live CPU receipt."""
    now=time.monotonic()
    port.node.sim=1.01;port._feedback(sample(1.01))
    for kind in ('CLOCK','IMAGE','INFO'):
        sup.observer.observe_original(kind,dict(source_ns=1_010_000_000,wall_s=now,
            valid=True,frame_id='head_camera_frame'))
    sup.observer.executor_progress()
    sup.observer.heartbeat(dict(wall_s=time.monotonic(),executor_wall_s=sup.observer._executor_wall,
        inference_deadline_wall_s=None))
    sup._started=True;sup._started_wall=now;sup._watchdog_wall=now
    def request(record):
        return dict(request=record['operation'],stage='POLICY_READY',epoch='attempt',generation=5,
            session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',motion_authority=False,
            policy_sha256='a'*64,current_inputs_guarded=True,ack_wall_s=time.monotonic())
    sup.monitor.request_runtime=request


def test_prearm_uses_both_current_observers_without_native_arm_or_sdk_send(tmp_path):
    _,port,sup,_,events,_=setup(tmp_path)
    try:
        guarded(sup,port)
        assert sup.prearm_guard() is True
        assert sup.epoch.stage=='POLICY_READY' and not sup.ready
        assert not port._goals and not sup._native_close
        assert any(event=='WATCHDOG_POLL' for event,_ in events)
        assert not sup.failed
    finally:sup.close();port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',['identity','purpose','hash','age','watchdog'])
def test_prearm_refusal_consumes_attempt_without_arming(tmp_path,damage):
    _,port,sup,_,_,_=setup(tmp_path)
    try:
        guarded(sup,port);original=sup.monitor.request_runtime
        def bad(record):
            ack=original(record)
            if damage=='identity':ack['monitor_peer']['pid']+=1
            elif damage=='purpose':ack['purpose']='production'
            elif damage=='hash':ack['policy_sha256']='e'*64
            elif damage=='age':ack['ack_wall_s']-=.020
            return ack
        sup.monitor.request_runtime=bad
        if damage=='watchdog':sup._watchdog_wall-=.020
        with pytest.raises(PermissionError):sup.prearm_guard()
        assert sup.failed and port._head_policy_binding_failed and not sup.ready
        with pytest.raises(PermissionError):sup.prearm_guard()
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_primary_events_preserve_original_scope_and_fault_before_logger(tmp_path):
    _,port,sup,_,events,_=setup(tmp_path)
    try:
        sup.observer._event('CONTROLLED_EVENT',source_ns=1_000_000_000)
        assert events[-1]==('CONTROLLED_EVENT',dict(epoch='attempt',generation=5,source_ns=1_000_000_000))
        def unavailable(*args,**kw):raise OSError('controlled writer failure')
        sup._sink=unavailable;sup.observer._event('WRITER_FAILED')
        assert sup.failed and port._head_policy_binding_failed and sup._fault_event.is_set()
    finally:sup.close();port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',[None,'primary_identity','monitor_identity','dependencies','policy','purpose'])
def test_arm_requires_three_same_scoped_native_identity_receipts(tmp_path,damage):
    from so101_demo.adapters.act.head_reservation_authority import HeadReservationAuthority
    _,port,sup,_,_,revoker=setup(tmp_path);calls=[]
    try:
        identity=dict(generation=5,incarnation='controlled-incarnation',boot='controlled-boot')
        authority=HeadReservationAuthority(directory=Path(sup._provisions['main']['socket_path']).parent,
            capability=secrets.token_bytes(32),native_owner=revoker.native_owner,generation=5,session_id='session',
            arm_guard=sup.prearm_guard,fault_callback=sup.fault)
        def native_arm(role):
            assert role=='neck' and sup.prearm_guard() is True
            calls.append('controlled-native-arm');authority._armed.add('neck');authority._identities['neck']=identity.copy()
            return 5
        authority.arm=native_arm;authority.identity=lambda role:identity.copy()
        revoker.identity=lambda:dict(identity,native_owner=revoker.native_owner)
        if damage=='primary_identity':revoker.identity=lambda:dict(identity,incarnation='foreign',native_owner=revoker.native_owner)
        def request(record):
            if record['operation']!='ARMED_READY':return prearm(record)
            assert record['identities']['main']['identity']==record['identities']['primary_fault']['identity']
            assert record['identities']['main']['provision_sha256']==sup._provisions['main']['sha256']
            assert record['identities']['primary_fault']['provision_sha256']==sup._provisions['primary_fault']['sha256']
            ack=dict(request='ARMED_READY',stage='ARMED_READY',epoch='attempt',generation=5,
                session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',motion_authority=False,
                identity=identity.copy(),policy_sha256='a'*64,provisions=sup._provisions.copy(),dependencies=sup._dependencies.copy())
            if damage=='monitor_identity':ack['identity']['incarnation']='foreign'
            elif damage=='dependencies':ack['dependencies']['controlled']=False
            elif damage=='policy':ack['policy_sha256']='e'*64
            elif damage=='purpose':ack['motion_authority']=True
            return ack
        # Start the controlled current-input interval after provision setup.
        guarded(sup,port);prearm=sup.monitor.request_runtime
        sup.monitor.request_runtime=request
        if damage is None:
            assert sup.arm(authority)==identity and sup.ready
            assert sup.epoch.stage=='ARMED_READY' and sup.dispatch_guard()
        else:
            with pytest.raises(PermissionError):sup.arm(authority)
            assert sup.failed and not sup.ready and port._head_policy_binding_failed
        assert calls==['controlled-native-arm'] and not port._goals
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_epoch_shadow_unknown_uuid_is_cancelled_when_local_sdk_insertion_failed(tmp_path):
    from so101_demo.act.head_monitor import canonical_bytes
    _,port,sup,_,_,_=setup(tmp_path);gid=str(uuid.uuid4())
    # A controlled committed epoch record models the failure boundary after
    # immutable registration and before SDK-port insertion. No acceptance exists.
    sup.epoch._inventory[gid]=(canonical_bytes(dict(goal_uuid=gid)),'a'*64)
    try:
        sup.fault('controlled local insertion failure')
        sup._cancel_and_stop()
        assert gid in port._goals and port.accepted(gid) is None and port.result(gid) is None
        assert sup.observer.wait_for_operations(timeout_s=.1)
        assert len(port.node.calls)==2
        assert port.stopped() is False
    finally:sup.close();port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('acknowledged',[False,True])
def test_diagnostic_later_identity_failure_cannot_report_zero_native_arms(acknowledged):
    from so101_demo.cli.head_feedback_bootstrap import _bind_native_diagnostic
    authority=SimpleNamespace(_armed={'neck'} if acknowledged else set(),exchange_receipts=[])
    def fail(value):raise PermissionError('controlled identity-stage failure')
    primary=SimpleNamespace(arm=fail);result=dict(native_arm_count=0)
    with pytest.raises(PermissionError):_bind_native_diagnostic(primary,authority,result)
    assert result['native_arm_count']==(1 if acknowledged else None)
    assert result['main_exchange_receipts']==[]


def input_status(sup,*,ready=True,**overrides):
    return dict(request='PREARM_INPUTS',stage='POLICY_READY',epoch='attempt',generation=5,
        session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',motion_authority=False,
        policy_sha256='a'*64,inputs_ready=ready,ack_wall_s=time.monotonic(),**overrides)


def test_passive_cpu_pending_then_fresh_does_not_activate_primary_or_arm(tmp_path):
    _,port,sup,_,events,_=setup(tmp_path);requests=[]
    def reply(record):
        requests.append(record)
        return input_status(sup,ready=len(requests)==2)
    sup.monitor.request_runtime=reply
    try:
        ack=sup.wait_cpu_inputs(timeout_s=.1)
        assert ack['inputs_ready'] and len(requests)==2
        assert not sup.ready and sup.epoch.stage=='POLICY_READY'
        assert not sup.observer._active and sup._watchdog_wall is None
        assert not port._goals and any(event=='CPU_INPUTS_READY' for event,_ in events)
    finally:sup.close();port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',['purpose','hash','generation','age','boolean'])
def test_invalid_passive_receipt_cannot_skip_current_prearm_or_reopen_scope(tmp_path,damage):
    _,port,sup,_,_,_=setup(tmp_path)
    reply=input_status(sup)
    if damage=='purpose':reply['purpose']='qualification'
    elif damage=='hash':reply['policy_sha256']='b'*64
    elif damage=='generation':reply['generation']=6
    elif damage=='age':reply['ack_wall_s']-=.1
    else:reply['inputs_ready']=1
    sup.monitor.request_runtime=lambda record:reply
    try:
        with pytest.raises(PermissionError):sup.wait_cpu_inputs(timeout_s=.1)
        assert sup.failed and not sup.ready and port._head_policy_binding_failed
        with pytest.raises(PermissionError):sup.wait_cpu_inputs(timeout_s=.1)
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_passive_wait_bound_includes_exchange_that_returns_fresh_but_too_late(tmp_path):
    _,port,sup,_,_,_=setup(tmp_path)
    def reply(record):
        time.sleep(.010)
        return input_status(sup)
    sup.monitor.request_runtime=reply
    try:
        with pytest.raises(TimeoutError):sup.wait_cpu_inputs(timeout_s=.004)
        assert sup.failed and not sup.ready
    finally:sup.close();port.close_head_io(timeout_s=1.)

@pytest.mark.parametrize('refused',[False,True])
def test_original_heartbeat_round_trip_is_retained_on_ack_and_transport_failure(tmp_path,refused):
    _,port,sup,_,events,_=setup(tmp_path)
    try:
        sup._started_wall=time.monotonic();sup.observer.executor_progress()
        def exchange(request):
            sup._shutdown.set()
            if refused:raise TimeoutError('controlled original transport deadline')
            return dict(request='HEARTBEAT',stage='POLICY_READY',epoch='attempt',generation=5,
                session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',
                motion_authority=False,ack_wall_s=time.monotonic())
        sup.monitor.request_runtime=exchange
        sup._heartbeat()
        record=next(fields for event,fields in events if event=='HEARTBEAT_ROUND_TRIP')
        assert record['request']['executor_wall_s']==sup.observer._executor_wall
        assert record['request']['executor_wall_s']<=record['request']['wall_s']
        assert record['request']['wall_s']<=record['rpc_started_wall_s']<=record['rpc_ended_wall_s']
        if refused:
            assert record['reply'] is None and record['error_type']=='TimeoutError'
            assert sup.failed and not sup.ready and port._head_policy_binding_failed
        else:
            assert record['reply']['ack_wall_s']<=record['rpc_ended_wall_s']
            assert record['error_type'] is None and not sup.failed and not sup.ready
        assert sup.epoch.stage==('REVOKED' if refused else 'POLICY_READY')
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_owned_heartbeat_worker_reports_original_fault_without_new_heartbeat(tmp_path):
    _,port,sup,_,events,_=setup(tmp_path);requests=[]
    wall=time.monotonic()
    def request(record):
        requests.append(record)
        assert sup.failed and port._head_policy_binding_failed and not sup.ready
        return dict(request='FAULT',stage='REVOKED',epoch='attempt',generation=5,
            session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',
            motion_authority=False,fault=dict(record['fault']),ack_wall_s=time.monotonic())
    sup.monitor.request_runtime=request
    try:
        sup.fault('controlled original fault',wall)
        sup._heartbeat()
        assert requests==[dict(operation='FAULT',fault=dict(reason='controlled original fault',fault_wall_s=wall))]
        receipt=next(fields for event,fields in events if event=='MONITOR_FAULT_NOTICE')
        assert receipt['ack']['fault']['fault_wall_s']==wall
        assert sup.failed and not sup.ready and sup.epoch.stage=='REVOKED'
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_cpu_fault_notice_is_independent_of_blocked_native_close_and_cancel(tmp_path):
    node,port,sup,_,events,revoker=setup(tmp_path)
    native_entered=threading.Event();release=threading.Event();noticed=threading.Event()
    def close():native_entered.set();release.wait(.3);return dict(ack_validated=True)
    revoker.close_strict=close
    def request(record):
        if record['operation']=='FAULT':
            noticed.set()
            return dict(request='FAULT',stage='REVOKED',epoch='attempt',generation=5,
                session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',
                motion_authority=False,fault=dict(record['fault']),ack_wall_s=time.monotonic())
        return dict(request='HEARTBEAT',stage='POLICY_READY',epoch='attempt',generation=5,
            session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',motion_authority=False)
    sup.monitor.request_runtime=request
    gid=str(uuid.uuid4());port._goals[gid]=dict(accepted=None,handle=None,result=None,
        cancel_requested=False,cancel_ack=False,error=None)
    try:
        sup.start();sup.timer.callback();sup.fault('controlled original fault',time.monotonic())
        assert native_entered.wait(.1) and noticed.wait(.1) and not release.is_set()
        deadline=time.monotonic()+.1
        while len(node.calls)<2 and time.monotonic()<deadline:time.sleep(.001)
        assert len(node.calls)>=2 and not release.is_set()
        assert len(sup.threads)==4 and sup.failed and not sup.ready
    finally:release.set();sup.close();port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',['peer','purpose','generation','authority','later_origin','late_ack','transport'])
def test_fault_notice_failure_never_confers_ready_or_native_close(tmp_path,damage):
    _,port,sup,_,events,_=setup(tmp_path)
    wall=time.monotonic();requests=[]
    def request(record):
        requests.append(record)
        if damage=='transport':raise TimeoutError('controlled unavailable peer')
        reply=dict(request='FAULT',stage='REVOKED',epoch='attempt',generation=5,
            session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',
            motion_authority=False,fault=dict(record['fault']),ack_wall_s=time.monotonic())
        if damage=='peer':reply['monitor_peer']=dict(sup.monitor.identity,pid=1)
        elif damage=='purpose':reply['purpose']='qualification'
        elif damage=='generation':reply['generation']=6
        elif damage=='authority':reply['motion_authority']=True
        elif damage=='later_origin':reply['fault']['fault_wall_s']+=.001
        elif damage=='late_ack':reply['ack_wall_s']-=.1
        return reply
    sup.monitor.request_runtime=request
    try:
        sup.fault('original root fault',wall);sup._heartbeat()
        assert len(requests)==1 and requests[0]['operation']=='FAULT'
        assert sup._fault_notice is None and sup._fault_notice_error is not None
        assert sup._native_close is None and sup.failed and not sup.ready
        assert port._head_policy_binding_failed and sup._fault['fault_wall_s']==wall
        assert any(event=='MONITOR_FAULT_NOTICE_UNCONFIRMED' for event,_ in events)
        assert not any(event=='MONITOR_FAULT_NOTICE' for event,_ in events)
    finally:sup.close();port.close_head_io(timeout_s=1.)


def test_fault_ack_tightens_earliest_shared_origin_without_reactivation(tmp_path):
    _,port,sup,_,events,_=setup(tmp_path);wall=time.monotonic()
    def request(record):
        return dict(request='FAULT',stage='REVOKED',epoch='attempt',generation=5,
            session_id='session',monitor_peer=sup.monitor.identity,purpose='calibration',
            motion_authority=False,fault=dict(reason='earlier CPU fault',fault_wall_s=wall-.002),
            ack_wall_s=time.monotonic())
    sup.monitor.request_runtime=request
    try:
        sup.fault('later root fault',wall);sup._heartbeat()
        assert sup._fault==dict(reason='earlier CPU fault',fault_wall_s=wall-.002)
        assert sup.epoch.stage=='REVOKED' and sup.failed and not sup.ready
        assert sup._fault_notice['ack']['fault']==sup._fault
        assert port._head_policy_binding_failed and sup._native_close is None
    finally:sup.close();port.close_head_io(timeout_s=1.)
