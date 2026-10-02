"""Exact native channel/ACK controls for Head's independent close-only client."""

import os
from pathlib import Path
import secrets
import select
import subprocess
import sys
import time
import uuid

import pytest

from so101_demo.adapters.act.head_revocation import NativeRevocationClient
from so101_demo.adapters.act.controller_reservation_provision import _process_start_ticks
from so101_demo.adapters.act.controller_reservation_provision import write_head_revocation_provision

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='native revoker requires Linux peer credentials')


SERVER="""
import os,socket,sys
import time
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
    listener.bind(sys.argv[1]);os.chmod(sys.argv[1],0o600);listener.listen(1)
    print('READY',flush=True)
    listener.settimeout(2)
    with listener.accept()[0] as connection:
        connection.settimeout(2)
        data=connection.recv(4096)
        print('RECEIVED' if data else 'EMPTY',flush=True)
        if data:
            time.sleep(float(sys.argv[3]))
            connection.sendall(bytes.fromhex(sys.argv[2]))
        sys.stdin.readline()
"""


@pytest.fixture
def native_server(tmp_path):
    processes=[]
    def start(reply,delay=0.):
        base=Path(os.environ['SO101_IPC_SOCKET_BASE'])
        directory=base/('hr-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
        path=directory/'r.sock'
        process=subprocess.Popen([sys.executable,'-c',SERVER,str(path),reply.hex(),str(delay)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        processes.append(process)
        poll=select.poll();poll.register(process.stdout,select.POLLIN|select.POLLHUP)
        assert poll.poll(2000) and process.stdout.readline()=='READY\n'
        owner=dict(uid=os.geteuid(),pid=process.pid,start_ticks=_process_start_ticks(process.pid))
        (tmp_path/('peer-'+str(process.pid)+'.json')).write_text(
            __import__('json').dumps(dict(path=str(path),native_owner=owner)))
        return path,owner,process
    yield start
    for process in processes:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=3)


def ack(generation=5):
    return b'SOGA'+bytes((1,0,0,0))+generation.to_bytes(8,'big')


def client(path,owner):
    return NativeRevocationClient(path,capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,timeout_s=.002)


def test_actual_close_ack_from_exact_owned_process(native_server):
    path,owner,process=native_server(ack())
    receipt=client(path,owner).close_strict()
    assert receipt['ack_validated'] is True and receipt['native_owner']==owner
    assert receipt['ack_wall_s']>=receipt['request_wall_s']
    assert process.stdout.readline()=='RECEIVED\n'


@pytest.mark.parametrize('failure',[None,'receive','post_reply_peer'])
def test_original_native_transport_trace_distinguishes_timeout_boundary(native_server,failure):
    path,owner,_=native_server(ack(),delay=.010 if failure=='receive' else 0.)
    revoker=client(path,owner)
    if failure=='post_reply_peer':
        original=revoker._verify_peer;checks=[]
        def verify(connection):
            original(connection);checks.append(True)
            if len(checks)==2:time.sleep(.003)
        revoker._verify_peer=verify
    if failure is None:assert revoker.close_strict()['ack_validated'] is True
    else:
        with pytest.raises(TimeoutError):revoker.close_strict()
    trace=revoker.exchange_trace
    assert trace['native_owner']==owner and trace['generation']==5
    assert trace['deadline_wall_s']==trace['request_wall_s']+.002
    assert trace['ended_wall_s']>=trace['request_wall_s']
    assert all(trace['request_wall_s']<=value<=trace['ended_wall_s'] for value in trace['phases'].values())
    assert trace['phases']['sent']<=trace['ended_wall_s']
    if failure is None:
        assert trace['phase']=='complete' and trace['error_type'] is None
        assert trace['phases']['reply_received']<=trace['phases']['reply_peer_verified']
    elif failure=='receive':
        assert trace['phase']=='receive' and trace['error_type']=='TimeoutError'
        assert 'reply_received' not in trace['phases']
    else:
        assert trace['phase']=='final_deadline' and trace['error_type']=='TimeoutError'
        assert trace['phases']['reply_received']<trace['phases']['reply_peer_verified']
    assert 'capability' not in repr(trace) and 'body' not in trace


@pytest.mark.parametrize('damage',['magic','version','reserved6','reserved7','generation','status'])
def test_native_close_rejects_every_unvalidated_ack_field(native_server,damage):
    reply=bytearray(ack())
    position=dict(magic=0,version=4,reserved6=6,reserved7=7,generation=15,status=5)[damage]
    reply[position]^=1
    path,owner,_=native_server(bytes(reply))
    with pytest.raises(RuntimeError):client(path,owner).close_strict()


@pytest.mark.parametrize('damage',['pid','start_ticks','uid'])
def test_foreign_or_reused_native_peer_receives_no_capability(native_server,damage):
    path,owner,process=native_server(ack())
    changed=dict(owner)
    changed[damage]=(os.getpid() if damage=='pid' else owner[damage]+1)
    with pytest.raises((PermissionError,RuntimeError,ValueError)):
        client(path,changed).close_strict()
    assert process.stdout.readline()=='EMPTY\n'


def test_native_identity_requires_scoped_generation_incarnation_boot(native_server):
    body=b'SOID'+bytes((1,1,3))+int(5).to_bytes(8,'big')+b'\x03inc\x04boot'
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body)
    identity=client(path,owner).identity()
    assert (identity['generation'],identity['incarnation'],identity['boot'])==(5,'inc','boot')


@pytest.mark.parametrize('damage',['role','generation','control_character','truncated','trailing'])
def test_native_identity_rejects_unbound_or_malformed_reply(native_server,damage):
    body=bytearray(b'SOID'+bytes((1,1,3))+int(5).to_bytes(8,'big')+b'\x03inc\x04boot')
    if damage=='role':body[6]=1
    elif damage=='generation':body[14]=6
    elif damage=='control_character':body[16]=0
    elif damage=='truncated':body=body[:-1]
    else:body+=b'x'
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body)
    with pytest.raises(RuntimeError):client(path,owner).identity()


def test_revoker_provision_binds_monitor_and_exact_native_owner(native_server):
    path,owner,_=native_server(ack())
    destination=path.parent/'neck-revoke.provision'
    endpoint=path.parent/'neck-revoke.sock'
    capability=write_head_revocation_provision(destination,session_id='head-test',
        native_owner=owner,socket_path=endpoint)
    body=destination.read_bytes()
    assert body[:8]==b'SOPR'+bytes((2,3,9,len(os.fsencode(endpoint))))
    assert int.from_bytes(body[8:12],'big')==os.geteuid()
    assert int.from_bytes(body[12:16],'big')==os.getpid()
    assert int.from_bytes(body[16:24],'big')==_process_start_ticks(os.getpid())
    assert body[24:56]==capability
    assert int.from_bytes(body[56:60],'big')==owner['uid']
    assert int.from_bytes(body[60:64],'big')==owner['pid']
    assert int.from_bytes(body[64:72],'big')==owner['start_ticks']
    assert body[72:]==b'head-test'+os.fsencode(endpoint)
    assert destination.stat().st_mode&0o777==0o600 and destination.stat().st_nlink==1
    with pytest.raises(FileExistsError):
        write_head_revocation_provision(destination,session_id='head-test',
            native_owner=owner,socket_path=endpoint)
    assert destination.read_bytes()==body


@pytest.mark.parametrize('damage',['self_peer','stale_ticks','session','role','endpoint'])
def test_revoker_provision_refuses_mixed_scope_before_publication(native_server,damage):
    path,owner,_=native_server(ack())
    destination=path.parent/'neck-revoke.provision';endpoint=path.parent/'neck-revoke.sock'
    session='head-test'
    if damage=='self_peer':
        owner=dict(uid=os.geteuid(),pid=os.getpid(),start_ticks=_process_start_ticks(os.getpid()))
    elif damage=='stale_ticks':owner=dict(owner,start_ticks=owner['start_ticks']+1)
    elif damage=='session':session='bad/session'
    elif damage=='role':destination=path.parent/'arm.provision'
    else:endpoint=path.parent/'arm.sock'
    with pytest.raises(ValueError):
        write_head_revocation_provision(destination,session_id=session,
            native_owner=owner,socket_path=endpoint)
    assert not destination.exists()
