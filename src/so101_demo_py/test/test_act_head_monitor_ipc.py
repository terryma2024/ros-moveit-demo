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


@pytest.mark.parametrize('field', ['uid','pid','start_ticks'])
def test_foreign_connected_peer_gets_no_message(server,field):
    connection,peer,child=server
    peer[field]+=1
    with pytest.raises(PermissionError):
        channel=HeadMonitorChannel(connection,codec=codec('primary'),peer=peer,timeout_s=.010)
        channel.exchange({'operation':'PRESENCE'})
    assert child.stdout.readline()==b'PREFIX 0\n'


@pytest.mark.parametrize('server',['tamper','partial','oversize','timeout'],indirect=True)
def test_channel_fault_never_recovers_on_a_later_exchange(server):
    connection,peer,_=server
    primary=codec('primary')
    channel=HeadMonitorChannel(connection,codec=primary,peer=peer,timeout_s=.010)
    with pytest.raises((OSError,PermissionError)):
        channel.exchange({'operation':'PRESENCE'})
    assert primary.failed
    with pytest.raises((OSError,PermissionError)):
        channel.exchange({'operation':'HEARTBEAT'})


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
