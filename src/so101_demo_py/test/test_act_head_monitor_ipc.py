"""Authenticated direction, identity and sequence before monitor inventory."""

import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from so101_demo.act.head_monitor_ipc import HeadMonitorChannel, HeadMonitorCodec
from so101_demo.adapters.act.controller_reservation_provision import _process_start_ticks


SECRET=os.urandom(32)


def codec(selected_role, **changes):
    config=dict(secret=SECRET,epoch='attempt-a',generation=5,session_id='head-test',role=selected_role)
    config.update(changes)
    return HeadMonitorCodec(**config)


def signed(envelope):
    # Independently reconstruct canonical authenticated bytes, without calling
    # the production encoder. Tests deliberately use a trusted sender's key.
    value=copy.deepcopy(envelope);value.pop('mac',None)
    body=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
    value['mac']=hmac.new(SECRET,b'SO101-HEAD-MONITOR-v1\0'+body,hashlib.sha256).hexdigest()
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def test_messages_are_directional_and_sequence_is_contiguous():
    primary,monitor=codec('primary'),codec('monitor')
    original={'operation':'PRESENCE','identity':{'uid':7,'pid':12,'start_ticks':90}}
    first=primary.encode(original)
    original['identity']['pid']=99
    assert monitor.decode(first)['identity']['pid']==12
    assert primary.decode(monitor.encode({'ack':'PRESENT'}))=={'ack':'PRESENT'}
    assert monitor.decode(primary.encode({'operation':'HEARTBEAT'}))=={'operation':'HEARTBEAT'}
    assert SECRET not in first


@pytest.mark.parametrize('damage', ['mac','wrong_epoch','wrong_generation','wrong_session',
    'reflection','replay','sequence_gap','sequence_bool','extra_field','wrong_version',
    'noncanonical','duplicate_field','nonfinite','payload_not_object','oversize','missing_field'])
def test_bad_envelope_irreversibly_refuses_later_valid_messages(damage):
    primary,monitor=codec('primary'),codec('monitor')
    first=primary.encode({'operation':'PRESENCE'})
    value=json.loads(first)
    if damage=='mac':
        value['payload']['operation']='INVENTORY'
        bad=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    elif damage=='noncanonical':bad=b' '+first
    elif damage=='duplicate_field':bad=first[:-1]+b',"epoch":"attempt-a"}'
    elif damage=='nonfinite':bad=first.replace(b'"PRESENCE"',b'NaN')
    elif damage=='oversize':bad=b'x'*70001
    elif damage=='replay':monitor.decode(first);bad=first
    else:
        field,replacement={
            'wrong_epoch':('epoch','attempt-b'), 'wrong_generation':('generation',6),
            'wrong_session':('session_id','other'), 'reflection':('role','monitor'),
            'sequence_gap':('sequence',2), 'sequence_bool':('sequence',True),
            'extra_field':('extra',1), 'wrong_version':('version',2),
            'payload_not_object':('payload',[])}.get(damage,(None,None))
        if damage=='missing_field':value.pop('generation')
        else:value[field]=replacement
        bad=signed(value)
    with pytest.raises((PermissionError,ValueError)):monitor.decode(bad)
    with pytest.raises(PermissionError):monitor.decode(primary.encode({'operation':'HEARTBEAT'}))


@pytest.mark.parametrize('changes', [dict(secret=b'x'*31),dict(secret=bytes(32)),
    dict(epoch='../other'),dict(generation=True),dict(generation=0),
    dict(session_id=''),dict(role='revoker')])
def test_bad_config_cannot_authenticate(changes):
    with pytest.raises(ValueError):codec('primary',**changes)


def test_invalid_outbound_payload_closes_codec():
    primary=codec('primary')
    with pytest.raises(ValueError):primary.encode({'bad':float('nan')})
    with pytest.raises(PermissionError):primary.encode({'operation':'PRESENCE'})


def test_scope_has_no_public_replacement():
    primary=codec('primary')
    for field,value in [('epoch','attempt-b'),('generation',6),('session_id','other'),
                         ('role','monitor'),('failed',False),('sequence',77)]:
        with pytest.raises(AttributeError):setattr(primary,field,value)


SERVER=r'''
import socket,sys,os
path,mode=sys.argv[1:3]
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
    server.bind(path);os.chmod(path,0o600);server.listen(1)
    print('READY',flush=True)
    response=bytes.fromhex(sys.stdin.buffer.readline().decode().strip())
    with server.accept()[0] as connection:
        connection.settimeout(2.)
        size=connection.recv(4)
        print('PREFIX '+str(len(size)),flush=True)
        if size:
            body=b'';length=int.from_bytes(size,'big')
            while len(body)<length:
                more=connection.recv(length-len(body))
                if not more:break
                body+=more
            if mode=='timeout':sys.stdin.buffer.readline()
            else:
                length=len(response)+(1 if mode=='partial' else 0)
                if mode=='oversize':length=70001
                connection.sendall(length.to_bytes(4,'big')+response)
        # Keep the actual peer alive through the client's post-reply check.
        sys.stdin.buffer.readline()
'''


@pytest.fixture
def server(tmp_path,request):
    base=Path(os.environ.get('SO101_IPC_SOCKET_BASE',str(tmp_path)))
    base.mkdir(mode=0o700,parents=True,exist_ok=True)
    directory=base/('mi-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
    path=directory/'peer.socket'
    mode=getattr(request,'param','valid')
    child=subprocess.Popen([sys.executable,'-c',SERVER,str(path),mode],stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        assert child.stdout.readline()==b'READY\n'
        response=codec('monitor').encode({'ack':'PRESENT'})
        if mode=='tamper':response=response.replace(b'PRESENT',b'INVALID')
        child.stdin.write(response.hex().encode()+b'\n');child.stdin.flush()
        peer=dict(uid=os.geteuid(),pid=child.pid,start_ticks=_process_start_ticks(child.pid))
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.connect(str(path));yield connection,peer,child
    finally:
        if child.poll() is None:
            child.stdin.write(b'\n');child.stdin.flush()
            try:child.wait(timeout=2.)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=2.)
        # Retain task evidence and endpoint fixture; do not remove directories.


def test_real_connected_peer_authenticates_reply(server):
    connection,peer,child=server
    channel=HeadMonitorChannel(connection,codec=codec('primary'),peer=peer,timeout_s=.010)
    assert channel.exchange({'operation':'PRESENCE'})=={'ack':'PRESENT'}
    assert child.stdout.readline()==b'PREFIX 4\n'


def test_built_request_uses_real_connected_peer_authentication(server):
    connection,peer,child=server
    channel=HeadMonitorChannel(connection,codec=codec('primary'),peer=peer,timeout_s=.010)
    assert channel.exchange_built(lambda:{'operation':'PRESENCE'})=={'ack':'PRESENT'}
    assert child.stdout.readline()==b'PREFIX 4\n'


@pytest.mark.parametrize('field',['uid','pid','start_ticks'])
def test_built_request_rechecks_peer_before_original_snapshot(server,field):
    connection,peer,child=server
    primary=codec('primary')
    channel=HeadMonitorChannel(connection,codec=primary,peer=peer,timeout_s=.010)
    channel._peer[field]+=1
    def forbidden():raise AssertionError('foreign peer reached the snapshot')
    with pytest.raises(PermissionError):channel.exchange_built(forbidden)
    assert primary.failed and connection.fileno()==-1
    assert child.stdout.readline()==b'PREFIX 0\n'


@pytest.mark.parametrize('damage',['none','wait_expired','builder_expired','peer','builder_error','invalid_builder'])
def test_built_request_includes_slot_wait_and_sampling_in_original_deadline(monkeypatch,damage):
    import so101_demo.act.head_monitor_ipc as ipc
    clock=[10.0];events=[]
    monkeypatch.setattr(ipc,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    class Occupied:
        def acquire(self,timeout):
            assert timeout==pytest.approx(.010)
            clock[0]=10.010 if damage=='wait_expired' else 10.006
            events.append('slot');return True
        def release(self):events.append('release')
    channel=object.__new__(HeadMonitorChannel)
    channel._timeout=.010;channel._io_lock=Occupied();channel._codec=codec('primary')
    channel._connection=SimpleNamespace(close=lambda:events.append('closed'))
    def peer():
        events.append('peer')
        if damage=='peer':raise PermissionError('controlled peer changed while queued')
    channel._verify_peer=peer
    def builder():
        events.append('snapshot')
        if damage=='builder_error':raise TypeError('controlled snapshot refusal')
        clock[0]+=.005 if damage=='builder_expired' else .001
        return {'operation':'HEARTBEAT','original_snapshot_wall':clock[0]}
    def write(payload,deadline):
        events.append('write');channel._remaining(deadline)
        assert deadline==pytest.approx(10.010)
        assert payload=={'operation':'HEARTBEAT','original_snapshot_wall':pytest.approx(10.007)}
    channel._write=write;channel._read=lambda deadline:{'ack':'PRESENT'}
    if damage=='none':
        assert channel.exchange_built(builder)=={'ack':'PRESENT'}
        assert events==['slot','peer','snapshot','write','release']
        assert not channel._codec.failed
    else:
        with pytest.raises((OSError,PermissionError,TypeError,ValueError)):
            channel.exchange_built(None if damage=='invalid_builder' else builder)
        assert 'write' not in events and channel._codec.failed and 'closed' in events
        assert events[-1]=='release'
        assert events.count('snapshot')==(1 if damage in ('builder_expired','builder_error') else 0)


@pytest.mark.parametrize('boundary',['none','slot','peer','snapshot','read'])
def test_original_heartbeat_phase_trace_survives_same_deadline_refusal(monkeypatch,boundary):
    import inspect
    import so101_demo.act.head_monitor_ipc as ipc
    clock=[10.];calls=[];trace={}
    monkeypatch.setattr(ipc,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    class Slot:
        def acquire(self,timeout):
            assert timeout==pytest.approx(.010)
            if boundary=='slot':clock[0]=10.010;return False
            clock[0]=10.001;return True
        def release(self):calls.append('release')
    channel=object.__new__(HeadMonitorChannel);channel._timeout=.010;channel._io_lock=Slot()
    channel._codec=codec('primary');channel._connection=SimpleNamespace(close=lambda:calls.append('closed'))
    def peer():
        calls.append('peer')
        if boundary=='peer':clock[0]=10.011
    def snapshot():
        calls.append('snapshot')
        if boundary=='snapshot':raise PermissionError('controlled pre-send snapshot refusal')
        return dict(operation='HEARTBEAT')
    def read(deadline):
        calls.append('read')
        if boundary=='read':clock[0]=10.011;raise TimeoutError('controlled original read deadline')
        return dict(ack='PRESENT')
    channel._verify_peer=peer;channel._read=read
    channel._write=lambda payload,deadline:calls.append('write')
    # On the uninstrumented source, run the actual intended boundary rather
    # than counting an unknown optional keyword as the regression failure.
    def exchange():
        return channel.exchange_built(snapshot,trace=trace) if 'trace' in inspect.signature(
            channel.exchange_built).parameters else channel.exchange_built(snapshot)
    if boundary=='none':assert exchange()==dict(ack='PRESENT')
    else:
        with pytest.raises((PermissionError,TimeoutError)):exchange()
    assert trace['started_wall_s']==10. and trace['deadline_wall_s']==pytest.approx(10.010)
    assert trace['ended_wall_s']==clock[0]
    if boundary=='none':
        assert trace['phase']=='complete' and trace['error_type'] is None and not channel._codec.failed
    else:
        assert trace['phase']==dict(slot='slot_wait',peer='peer_check',snapshot='snapshot',read='read')[boundary]
        assert trace['error_type']==('PermissionError' if boundary=='snapshot' else 'TimeoutError')
        assert trace['error_code'] and channel._codec.failed and 'closed' in calls
        if boundary in ('slot','peer'):assert 'snapshot' not in calls and 'write' not in calls
    if boundary!='slot':assert trace['slot_owned_wall_s']==10.001 and calls[-1]=='release'


@pytest.mark.parametrize('field', ['uid','pid','start_ticks'])
def test_foreign_connected_peer_gets_no_message(server,field):
    connection,peer,child=server
    peer[field]+=1
    with pytest.raises(PermissionError):
        channel=HeadMonitorChannel(connection,codec=codec('primary'),peer=peer,timeout_s=.010)
        channel.exchange({'operation':'PRESENCE'})
    assert child.stdout.readline()==b'PREFIX 0\n'


@pytest.mark.parametrize('server',['tamper','partial','oversize','timeout'],indirect=True)
@pytest.mark.parametrize('built',[False,True])
def test_channel_fault_never_recovers_on_a_later_exchange(server,built):
    connection,peer,_=server
    primary=codec('primary')
    channel=HeadMonitorChannel(connection,codec=primary,peer=peer,timeout_s=.010)
    exchange=(lambda payload:channel.exchange_built(lambda:payload)) if built else channel.exchange
    with pytest.raises((OSError,PermissionError)):
        exchange({'operation':'PRESENCE'})
    assert primary.failed
    with pytest.raises((OSError,PermissionError)):
        exchange({'operation':'HEARTBEAT'})


def test_fault_latch_never_waits_for_contended_codec_lock():
    primary=codec('primary')
    primary._lock.acquire()
    timer=threading.Timer(.050,primary._lock.release);timer.start()
    try:
        started=time.monotonic();primary.fail();elapsed=time.monotonic()-started
        assert primary.failed
        assert elapsed<.010
    finally:timer.join()


def test_channel_contention_closes_before_holder_recovers(server):
    connection,peer,_=server
    primary=codec('primary')
    channel=HeadMonitorChannel(connection,codec=primary,peer=peer,timeout_s=.002)
    primary._lock.acquire()
    timer=threading.Timer(.050,primary._lock.release);timer.start()
    try:
        started=time.monotonic()
        with pytest.raises(OSError):channel.exchange({'operation':'PRESENCE'})
        assert time.monotonic()-started<.010
        assert connection.fileno()==-1 and primary.failed
    finally:timer.join()


def test_oversized_outbound_input_is_refused_before_serializing(monkeypatch):
    import so101_demo.act.head_monitor_ipc as ipc
    original=ipc._canonical
    payload={'huge':'x'*2_000_000}
    def forbid_unbounded_work(value):
        if value is payload:raise AssertionError('unbounded input reached serialization')
        return original(value)
    monkeypatch.setattr(ipc,'_canonical',forbid_unbounded_work)
    primary=codec('primary')
    with pytest.raises(ValueError):primary.encode(payload)
    assert primary.failed


def test_outbound_owns_the_bounded_snapshot_before_caller_mutation(monkeypatch):
    import so101_demo.act.head_monitor_ipc as ipc
    original=ipc._bounded_payload
    payload={'operation':'PRESENCE','identity':{'pid':12}}
    def mutate_after_copy(value,deadline):
        snapshot=original(value,deadline)
        value['operation']='CHANGED';value['identity']['pid']=99
        return snapshot
    monkeypatch.setattr(ipc,'_bounded_payload',mutate_after_copy)
    primary,monitor=codec('primary'),codec('monitor')
    assert monitor.decode(primary.encode(payload))=={'operation':'PRESENCE','identity':{'pid':12}}


def test_del_escape_cannot_bypass_payload_wire_byte_limit():
    primary=codec('primary')
    with pytest.raises(ValueError):primary.encode({'x':'\x7f'*11000})
    assert primary.failed
