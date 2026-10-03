"""CPU exec presence is authenticated; it never grants motion readiness."""

import json
import io
import gc
import os
from pathlib import Path
import sys
import signal
import subprocess
import time
import uuid
from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.head_monitor_process import MonitorProcess,start_monitor
from so101_demo.adapters.act.controller_reservation_provision import _process_start_ticks


def test_cpu_execution_trace_retains_actual_gc_without_changing_collector():
    from so101_demo.adapters.act.head_monitor_process import MonitorExecutionTrace
    before=(gc.isenabled(),gc.get_threshold(),tuple(gc.callbacks))
    trace=MonitorExecutionTrace()
    try:
        trace.mark('request_received','HEARTBEAT')
        gc.collect(0)
        trace.mark('reply_sent','HEARTBEAT')
        result=trace.finish()
    finally:trace.finish()
    assert (gc.isenabled(),gc.get_threshold(),tuple(gc.callbacks))==before
    assert result['qualification'] is False and result['motion_authority'] is False
    assert result['collector_at_entry']==result['collector_at_exit']
    assert [r[1:3] for r in result['server_phases']]==[
        ('request_received','HEARTBEAT'),('reply_sent','HEARTBEAT')]
    events=[r for r in result['gc_events'] if r[2]==0]
    assert [r[1] for r in events][-2:]==['start','stop']
    assert events[-2][0]<=events[-1][0]
    assert json.loads(json.dumps(result,allow_nan=False))['clock']=='CLOCK_MONOTONIC'


def test_cpu_execution_trace_is_bounded_and_does_not_store_unknown_operation_payload():
    from so101_demo.adapters.act.head_monitor_process import MonitorExecutionTrace
    trace=MonitorExecutionTrace()
    try:
        for _ in range(4100):trace.mark('receive_started')
        trace.mark('request_received','unknown-secret-payload')
        result=trace.finish()
    finally:trace.finish()
    assert len(result['server_phases'])==4096
    assert result['server_phase_count']==4101 and result['server_phase_dropped']==5
    assert result['server_phases'][-1][2] is None
    assert 'unknown-secret-payload' not in json.dumps(result)


@pytest.fixture
def config(tmp_path):
    from so101_demo.adapters.act import head_monitor_process
    source=Path(head_monitor_process.__file__).parents[2]
    alias=tmp_path/'source-alias'/'so101_demo';alias.mkdir(parents=True)
    (alias/'__init__.py').write_text('__path__='+repr([str(source)])+'\n')
    environment=dict(os.environ)
    environment['PYTHONPATH']=str(alias.parent)+os.pathsep+environment.get('PYTHONPATH','')
    base=Path(environment.get('SO101_IPC_SOCKET_BASE',str(tmp_path)))
    base.mkdir(mode=0o700,parents=True,exist_ok=True)
    directory=base/('mp-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
    return dict(python_executable=sys.executable,ipc_directory=directory,
        log_path=tmp_path/'monitor.log',epoch='launch-a',generation=5,
        session_id='head-launch-test',startup_timeout_s=2.,environment=environment)


@pytest.mark.parametrize('damage', ['executable','epoch','generation','session','timeout',
    'relative','permissions','occupied','symlink','overlong'])
def test_invalid_start_never_returns_exec_presence(config,damage,tmp_path):
    config=dict(config)
    if damage=='executable':config['python_executable']=str(tmp_path/'missing-python')
    elif damage=='epoch':config['epoch']='../other'
    elif damage=='generation':config['generation']=True
    elif damage=='session':config['session_id']=''
    elif damage=='timeout':config['startup_timeout_s']=float('nan')
    elif damage=='relative':config['ipc_directory']=Path('relative-dir')
    elif damage=='permissions':config['ipc_directory'].chmod(0o755)
    elif damage=='occupied':(config['ipc_directory']/'monitor.socket').write_text('owned-existing')
    elif damage=='symlink':
        link=config['ipc_directory'].parent/('ml-'+uuid.uuid4().hex[:8]);link.symlink_to(config['ipc_directory'])
        config['ipc_directory']=link
    else:
        child=config['ipc_directory']/('x'*100);child.mkdir(mode=0o700);config['ipc_directory']=child
    with pytest.raises((ValueError,PermissionError,FileExistsError,FileNotFoundError)):
        start_monitor(**config)


@pytest.mark.parametrize('damage',['none','closed','unconfigured','peer','purpose','epoch','generation',
    'session_id','motion_authority','stage','request'])
def test_sampled_heartbeat_requires_configuration_and_complete_runtime_ack(damage):
    calls=[]
    reply=dict(request='HEARTBEAT',stage='POLICY_READY',monitor_peer={'pid':123},purpose='calibration',
        epoch='attempt',generation=5,session_id='session',motion_authority=False)
    if damage not in ('none','closed','unconfigured'):
        key='monitor_peer' if damage=='peer' else damage
        reply[key]={'pid':124} if damage=='peer' else True if damage=='motion_authority' else 'foreign'
    def exchange(factory,*,trace=None):
        calls.append(factory());return reply
    channel=SimpleNamespace(exchange_built=exchange,close=lambda:calls.append('closed'),
        _codec=SimpleNamespace(epoch='attempt',generation=5,session_id='session'))
    monitor=object.__new__(MonitorProcess)
    monitor._channel=channel;monitor._identity={'pid':123};monitor._closed=damage=='closed'
    monitor._runtime_requested=damage!='unconfigured';monitor.is_alive=lambda:True
    snapshot=dict(wall_s=10.006,executor_wall_s=10.005,inference_deadline_wall_s=None)
    if damage=='none':
        assert monitor.request_heartbeat(lambda:snapshot)==reply
        assert calls==[dict(operation='HEARTBEAT',heartbeat=snapshot)]
    else:
        with pytest.raises(PermissionError):monitor.request_heartbeat(lambda:snapshot)
        if damage in ('closed','unconfigured'):assert calls==[]
        else:assert calls[-1]=='closed'


@pytest.mark.parametrize('damage',['none','scope','transport'])
def test_runtime_request_carries_local_trace_without_changing_request_or_ack_checks(damage):
    trace={};request=dict(operation='CALIBRATION_FRAME_INPUTS',exposure={'original':'claim'})
    reply=dict(request=request['operation'],stage='CONFIGURED',monitor_peer={'pid':123},
        purpose='calibration',epoch='attempt',generation=5,session_id='session',motion_authority=False)
    calls=[]
    def exchange(value,*,trace=None):
        calls.append(value);trace.update(phase='read',started_wall_s=10.,deadline_wall_s=10.010)
        if damage=='transport':raise TimeoutError('controlled original timeout')
        if damage=='scope':reply['epoch']='foreign'
        return reply
    monitor=object.__new__(MonitorProcess);monitor._closed=False;monitor._runtime_requested=True
    monitor._identity={'pid':123};monitor.is_alive=lambda:True
    monitor._channel=SimpleNamespace(exchange=exchange,close=lambda:calls.append('closed'),
        _codec=SimpleNamespace(epoch='attempt',generation=5,session_id='session'))
    if damage=='none':assert monitor.request_runtime(request,trace=trace)==reply
    else:
        with pytest.raises((PermissionError,TimeoutError)):monitor.request_runtime(request,trace=trace)
    assert calls[0] is request and trace['phase']=='read' and trace['deadline_wall_s']==10.010
    if damage=='scope':assert calls[-1]=='closed'


def test_actual_exec_identity_and_no_key_in_argv_environment_logs(config):
    monitor=start_monitor(**config)
    try:
        assert monitor.identity['pid']!=os.getpid()
        assert _process_start_ticks(monitor.identity['pid'])==monitor.identity['start_ticks']
        assert monitor.receipt['stage']=='EXEC_ONLY'
        assert monitor.receipt['motion_authority'] is False
        assert monitor.receipt['cpu_only'] is True
        assert monitor.is_alive()
        pid=monitor.identity['pid']
        argv=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ')
        env=Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
        assert b'--bootstrap-fd' in argv
        assert not any(b'SECRET' in item or b'CAPABILITY' in item for item in env)
        assert b'CUDA_VISIBLE_DEVICES=' in env
        log=config['log_path'].read_text()
        assert 'EXEC_ONLY' in log and 'key=' not in log and 'secret=' not in log
        assert monitor.receipt['module_path']==str(Path(__file__).parents[1]/'src/adapters/act/head_monitor_process.py')
    finally:monitor.close()
    assert not monitor.is_alive()
    monitor.close()


def test_actual_exec_binds_explicit_simulation_policy_before_any_motion(config):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    from so101_demo.act.head_monitor import digest
    original=HeadSimulationPolicy.default_document()
    monitor=start_monitor(**config,simulation_policy=original)
    try:
        receipt=monitor.receipt
        assert receipt['simulation_policy']==original
        assert receipt['simulation_policy_sha256']==digest(original)
        assert receipt['stage']=='EXEC_ONLY' and receipt['motion_authority'] is False
        assert receipt['cpu_only'] is True and monitor.is_alive()
        original['supervision_stale_s']=2.
        heartbeat=monitor.request({'operation':'HEARTBEAT'})
        assert heartbeat['simulation_policy']['supervision_stale_s']==.5
        assert heartbeat['simulation_policy_sha256']==receipt['simulation_policy_sha256']
        assert heartbeat['stage']=='EXEC_ONLY' and heartbeat['motion_authority'] is False
    finally:reaped=monitor.close()
    assert reaped['shutdown_ack'] is True and reaped['exit_code']==0
    assert not monitor.is_alive()


@pytest.mark.parametrize('change',[dict(supervision_stale_s=True),dict(mode='hardware'),dict(extra=1)])
def test_invalid_simulation_bootstrap_refuses_before_spawning_peer(config,change):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    doc=dict(HeadSimulationPolicy.default_document(),**change)
    with pytest.raises(ValueError):start_monitor(**config,simulation_policy=doc)
    assert not config['log_path'].exists()


@pytest.mark.parametrize('field,value', [('schema_version',True),
    ('stop_confirmation_timeout_s',True),('max_reobservations_total',12.0)])
def test_actual_exec_reply_cannot_replace_exact_policy_with_equal_python_value(config,monkeypatch,field,value):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    monitor=start_monitor(**config,simulation_policy=HeadSimulationPolicy.default_document())
    exchange=monitor._channel.exchange
    def tamper_after_actual_authenticated_reply(request):
        reply=exchange(request)
        reply['simulation_policy'][field]=value
        return reply
    monkeypatch.setattr(monitor._channel,'exchange',tamper_after_actual_authenticated_reply)
    try:
        with pytest.raises(PermissionError):monitor.request({'operation':'HEARTBEAT'})
        assert monitor._channel._codec.failed
    finally:monitor.close()
    assert not monitor.is_alive()


@pytest.mark.parametrize('damage',['missing','different','boolean_version'])
def test_actual_simulation_exec_refuses_configuration_that_drops_entry_binding(config,damage):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    original=HeadSimulationPolicy.default_document()
    monitor=start_monitor(**config,simulation_policy=original)
    body={} if damage=='missing' else {'simulation_policy':dict(original)}
    if damage=='different':body['simulation_policy']['search_timeout_s']=40.
    if damage=='boolean_version':body['simulation_policy']['schema_version']=True
    try:
        with pytest.raises((PermissionError,OSError)):
            monitor.request_runtime({'operation':'CONFIGURE','configuration':body})
    finally:result=monitor.close()
    assert result['shutdown_ack'] is False
    assert result['exit_code']==2
    assert not monitor.is_alive()


@pytest.mark.parametrize('damage',['none','refused_false','refused_missing','extra','positive_stage',
    'request','peer','purpose','epoch','generation','session_id','motion_authority','fault_missing',
    'fault_extra','fault_boolean','fault_future','fault_nan','fault_reason','ack_missing','ack_boolean',
    'ack_future','ack_negative'])
def test_only_complete_scoped_negative_heartbeat_keeps_channel_open(damage):
    wall=time.monotonic();calls=[]
    reply=dict(request='HEARTBEAT',stage='REVOKED',monitor_peer={'pid':123},purpose='calibration',
        epoch='attempt',generation=5,session_id='session',motion_authority=False,
        heartbeat_rejected=True,fault=dict(reason='original expiry',fault_wall_s=wall-.001),ack_wall_s=wall)
    if damage=='refused_false':reply['heartbeat_rejected']=False
    elif damage=='refused_missing':del reply['heartbeat_rejected']
    elif damage=='extra':reply['ready']=True
    elif damage=='positive_stage':reply['stage']='ARMED_READY'
    elif damage in ('request','purpose','epoch','generation','session_id'):reply[damage]='foreign'
    elif damage=='peer':reply['monitor_peer']={'pid':124}
    elif damage=='motion_authority':reply['motion_authority']=True
    elif damage=='fault_missing':del reply['fault']
    elif damage=='fault_extra':reply['fault']['later']=True
    elif damage=='fault_boolean':reply['fault']['fault_wall_s']=True
    elif damage=='fault_future':reply['fault']['fault_wall_s']=wall+1
    elif damage=='fault_nan':reply['fault']['fault_wall_s']=float('nan')
    elif damage=='fault_reason':reply['fault']['reason']=''
    elif damage=='ack_missing':del reply['ack_wall_s']
    elif damage=='ack_boolean':reply['ack_wall_s']=True
    elif damage=='ack_future':reply['ack_wall_s']=wall+1
    elif damage=='ack_negative':reply['ack_wall_s']=-1
    channel=SimpleNamespace(exchange_built=lambda factory,**kw:reply,close=lambda:calls.append('closed'),
        _codec=SimpleNamespace(epoch='attempt',generation=5,session_id='session'))
    monitor=object.__new__(MonitorProcess);monitor._channel=channel;monitor._identity={'pid':123}
    monitor._closed=False;monitor._runtime_requested=True;monitor.is_alive=lambda:True
    if damage=='none':
        assert monitor.request_heartbeat(lambda:{})==reply and calls==[]
    else:
        with pytest.raises(PermissionError):monitor.request_heartbeat(lambda:{})
        assert calls==['closed']


def test_process_presence_refuses_inventory_and_revival(config):
    monitor=start_monitor(**config)
    try:
        with pytest.raises((PermissionError,ConnectionError,OSError)):
            monitor.request({'operation':'INVENTORY','record':{}})
        with pytest.raises((PermissionError,ConnectionError,OSError)):
            monitor.request({'operation':'PRESENCE'})
    finally:monitor.close()
    assert not monitor.is_alive()


def test_owned_startup_failure_reaps_only_its_child(config,tmp_path):
    config=dict(config)
    config['environment']=dict(config['environment'],PYTHONPATH=str(tmp_path/'absent-alias'))
    with pytest.raises((RuntimeError,ConnectionError,OSError)):
        start_monitor(**config)
    # The failed child's exact identity must be recorded even before IPC ready.
    records=[json.loads(line) for line in config['log_path'].read_text().splitlines()
             if line.startswith('{')]
    ownership=next(record for record in records if record.get('event')=='OWNED_EXEC')
    assert not Path('/proc/'+str(ownership['peer']['pid'])).exists()
    assert any(record.get('event')=='OWNED_REAP' for record in records)


def test_monitor_retires_if_primary_dies_before_connecting(config):
    script=r'''
import json,socket,sys
from so101_demo.adapters.act.head_monitor_process import start_monitor
original=socket.socket
class PausedConnect(original):
    def connect(self,path):
        print('BEFORE_CONNECT',flush=True)
        sys.stdin.readline()
        return super().connect(path)
socket.socket=PausedConnect
start_monitor(**json.loads(sys.stdin.readline()))
'''
    owner=subprocess.Popen([sys.executable,'-c',script],env=config['environment'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    owned_peer=None;pid_fd=None
    try:
        args={key:str(value) if isinstance(value,Path) else value
              for key,value in config.items() if key!='environment'}
        owner.stdin.write(json.dumps(args).encode()+b'\n');owner.stdin.flush()
        assert owner.stdout.readline()==b'BEFORE_CONNECT\n'
        records=[json.loads(line) for line in config['log_path'].read_text().splitlines()
                 if line.startswith('{')]
        owned_peer=next(record['peer'] for record in records if record.get('event')=='OWNED_EXEC')
        pid_fd=os.pidfd_open(owned_peer['pid'])
        owner.terminate();owner.wait(timeout=2.)
        deadline=time.monotonic()+.5
        while time.monotonic()<deadline:
            try:_process_start_ticks(owned_peer['pid'])
            except (OSError,RuntimeError):break
            time.sleep(.002)
        else:pytest.fail('CPU monitor survives primary death before IPC connect')
    finally:
        if owner.poll() is None:owner.terminate();owner.wait(timeout=2.)
        if pid_fd is not None:
            try:
                if _process_start_ticks(owned_peer['pid'])==owned_peer['start_ticks']:
                    signal.pidfd_send_signal(pid_fd,signal.SIGTERM)
            except (OSError,RuntimeError):pass
            os.close(pid_fd)


def test_presence_ack_after_startup_deadline_cannot_publish_success(config,monkeypatch):
    import so101_demo.adapters.act.head_monitor_process as process_module
    exchange=process_module.HeadMonitorChannel.exchange
    def delayed_return(channel,value):
        reply=exchange(channel,value)
        if value['operation']=='PRESENCE':time.sleep(.21)
        return reply
    monkeypatch.setattr(process_module.HeadMonitorChannel,'exchange',delayed_return)
    config=dict(config,startup_timeout_s=.2)
    monitor=None
    try:
        with pytest.raises(TimeoutError):monitor=start_monitor(**config)
    finally:
        if monitor is not None:monitor.close()
    records=[json.loads(line) for line in config['log_path'].read_text().splitlines()
             if line.startswith('{')]
    assert not any(record.get('event')=='EXEC_ONLY' for record in records)
    assert any(record.get('event')=='OWNED_REAP' for record in records)


@pytest.mark.parametrize('race',[FileNotFoundError,RuntimeError])
def test_owned_exit_race_finishes_wait_and_reap_record(monkeypatch,race):
    import so101_demo.adapters.act.head_monitor_process as process_module
    class Exited:
        pid=123;returncode=None;waits=0
        def wait(self,timeout):
            self.waits+=1
            if self.waits==1:raise subprocess.TimeoutExpired('owned monitor',timeout)
            self.returncode=0;return 0
        def poll(self):self.returncode=0;return 0
    def exited_peer(pid):raise race('owned child exited during identity read')
    def forbid_signal(*args):raise AssertionError('exited child was signalled')
    monkeypatch.setattr(process_module,'_peer',exited_peer)
    monkeypatch.setattr(process_module.signal,'pidfd_send_signal',forbid_signal)
    handle=io.BytesIO();child=Exited()
    result=process_module._retire(child,99,dict(uid=1,pid=123,start_ticks=456),handle,shutdown_ack=False)
    assert result['exit_code']==0 and child.waits>=2
    assert json.loads(handle.getvalue())['event']=='OWNED_REAP'
