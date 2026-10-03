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
from so101_demo.adapters.act import head_revocation
from so101_demo.adapters.act.controller_reservation_provision import _process_start_ticks
from so101_demo.adapters.act.controller_reservation_provision import _private_parent
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
            print(data.hex(),flush=True)
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


def client(path,owner,simulation=False):
    if simulation:
        from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
        return NativeRevocationClient(path,capability=secrets.token_bytes(32),
            native_owner=owner,generation=5,timeout_s=.05,
            simulation_policy=HeadSimulationPolicy.default_document())
    return NativeRevocationClient(path,capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,timeout_s=.002)


def test_actual_close_ack_from_exact_owned_process(native_server):
    path,owner,process=native_server(ack())
    revoker=client(path,owner);receipt=revoker.close_strict()
    assert receipt['ack_validated'] is True and receipt['native_owner']==owner
    assert receipt['ack_wall_s']>=receipt['request_wall_s']
    assert process.stdout.readline()=='RECEIVED\n'
    body=b'SOGR'+bytes((1,2))+revoker.capability+int(5).to_bytes(8,'big')+bytes(16)
    assert bytes.fromhex(process.stdout.readline())==len(body).to_bytes(4,'big')+body


def test_simulation_native_close_accepts_delayed_ack_only_under_explicit_bound(native_server):
    path,owner,process=native_server(ack(),delay=.02)
    revoker=client(path,owner,simulation=True)
    receipt=revoker.close_strict()
    assert receipt['ack_validated'] is True and receipt['native_owner']==owner
    assert .02<=receipt['ack_wall_s']-receipt['request_wall_s']<.05
    trace=revoker.exchange_trace
    assert abs(trace['deadline_wall_s']-trace['request_wall_s']-.05)<1e-9
    assert revoker.transport_origin['mode']=='mujoco_bounded_stop_search'
    assert process.stdout.readline()=='RECEIVED\n'
    body=b'SOGR'+bytes((1,2))+revoker.capability+int(5).to_bytes(8,'big')+bytes(16)
    assert bytes.fromhex(process.stdout.readline())==len(body).to_bytes(4,'big')+body


def test_simulation_native_entry_does_not_renew_callers_original_deadline(native_server):
    path,owner,_=native_server(ack());revoker=client(path,owner,simulation=True)
    actual=revoker._native_exchange
    def late_entry(*args):time.sleep(.06);return actual(*args)
    revoker._native_exchange=late_entry
    with pytest.raises(TimeoutError):revoker.close_strict()
    trace=revoker.exchange_trace
    assert trace['entry_wall_s']>trace['deadline_wall_s']
    assert trace['phases']=={} and trace['phase']=='path'


def test_simulation_close_budget_must_match_declared_policy(native_server):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    path,owner,_=native_server(ack())
    with pytest.raises(ValueError):NativeRevocationClient(path,capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,timeout_s=.05)
    with pytest.raises(ValueError):NativeRevocationClient(path,capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,timeout_s=.1,
        simulation_policy=HeadSimulationPolicy.default_document())


def test_close_checks_execute_outside_python_syscall_scheduling(native_server,monkeypatch):
    path,owner,_=native_server(ack())
    original=_private_parent
    def delayed_python_checks(endpoint):
        original(endpoint);time.sleep(.003)
    monkeypatch.setattr(head_revocation,'_private_parent',delayed_python_checks,raising=False)
    revoker=client(path,owner)
    receipt=revoker.close_strict()
    assert receipt['ack_validated'] is True
    assert receipt['ack_wall_s']-receipt['request_wall_s']<=.002
    assert revoker.transport_origin['abi']==1
    assert Path(revoker.transport_origin['path']).is_file()


@pytest.mark.parametrize('damage',['parent_mode','socket_mode','endpoint_symlink','ancestor_symlink','regular_file'])
@pytest.mark.parametrize('simulation',[False,True])
def test_compiled_path_checks_refuse_before_connecting(native_server,damage,tmp_path,simulation):
    path,owner,_=native_server(ack())
    destination=path
    if damage=='parent_mode':path.parent.chmod(0o755)
    elif damage=='socket_mode':path.chmod(0o666)
    elif damage=='endpoint_symlink':
        destination=path.parent/'link.sock';destination.symlink_to(path)
    elif damage=='ancestor_symlink':
        alias=path.parent.parent/('hs-link-'+uuid.uuid4().hex[:8]);alias.symlink_to(path.parent)
        destination=alias/path.name
    else:destination=path.parent/'regular';destination.write_text('not a socket')
    revoker=client(destination,owner,simulation=simulation)
    try:
        with pytest.raises(PermissionError):revoker.close_strict()
        assert revoker.exchange_trace['phase']=='path'
        assert 'connected' not in revoker.exchange_trace['phases']
    finally:
        if damage=='parent_mode':path.parent.chmod(0o700)


@pytest.mark.parametrize('damage',['capability','generation','peer','budget'])
@pytest.mark.parametrize('simulation',[False,True])
def test_mutated_client_scope_cannot_wrap_or_silently_substitute_original_authority(native_server,damage,simulation):
    path,owner,_=native_server(ack());revoker=client(path,owner,simulation=simulation)
    if damage=='capability':revoker.capability+=b'additional bytes'
    elif damage=='generation':revoker.generation+=2**64
    elif damage=='peer':revoker.native_owner['start_ticks']+=1
    else:revoker.timeout=.010
    with pytest.raises(PermissionError,match='HEAD_REVOKER_SCOPE_CHANGED'):revoker.close_strict()


@pytest.mark.parametrize('damage',['absent','abi'])
def test_native_library_is_required_without_python_transport_fallback(native_server,monkeypatch,tmp_path,damage):
    path,owner,_=native_server(ack())
    if damage=='absent':
        import ament_index_python.packages
        monkeypatch.setattr(ament_index_python.packages,'get_package_prefix',lambda _:str(tmp_path/'no-prefix'))
    else:
        from types import SimpleNamespace
        class Function:
            def __call__(self):return 2
        monkeypatch.setattr(head_revocation.ctypes,'CDLL',lambda _:SimpleNamespace(
            so101_head_revocation_abi=Function(),so101_head_revocation_result_size=Function()))
    with pytest.raises(RuntimeError,match='HEAD_REVOKER_NATIVE_TRANSPORT_REQUIRED'):client(path,owner)


@pytest.mark.parametrize('failure',[None,'receive','late_native_entry'])
def test_original_native_transport_trace_distinguishes_timeout_boundary(native_server,failure):
    path,owner,_=native_server(ack(),delay=.010 if failure=='receive' else 0.)
    revoker=client(path,owner)
    if failure=='late_native_entry':
        original=revoker._native_exchange
        def delayed_entry(*args):time.sleep(.003);return original(*args)
        revoker._native_exchange=delayed_entry
    if failure is None:assert revoker.close_strict()['ack_validated'] is True
    else:
        with pytest.raises(TimeoutError):revoker.close_strict()
    trace=revoker.exchange_trace
    assert trace['native_owner']==owner and trace['generation']==5
    assert abs(trace['deadline_wall_s']-trace['request_wall_s']-.002)<1e-9
    assert trace['ended_wall_s']>=trace['request_wall_s']
    assert all(trace['request_wall_s']<=value<=trace['ended_wall_s'] for value in trace['phases'].values())
    if failure!='late_native_entry':assert trace['phases']['sent']<=trace['ended_wall_s']
    if failure is None:
        assert trace['phase']=='complete' and trace['error_type'] is None
        assert trace['phases']['reply_received']<=trace['phases']['reply_peer_verified']
    elif failure=='receive':
        assert trace['phase']=='receive' and trace['error_type']=='TimeoutError'
        assert 'reply_received' not in trace['phases']
    else:
        assert trace['phase']=='path' and trace['error_type']=='TimeoutError'
        assert trace['phases']=={} and trace['entry_wall_s']>trace['deadline_wall_s']
    assert 'capability' not in repr(trace) and 'body' not in trace


@pytest.mark.parametrize('damage',['magic','version','reserved6','reserved7','generation','status'])
@pytest.mark.parametrize('simulation',[False,True])
def test_native_close_rejects_every_unvalidated_ack_field(native_server,damage,simulation):
    reply=bytearray(ack())
    position=dict(magic=0,version=4,reserved6=6,reserved7=7,generation=15,status=5)[damage]
    reply[position]^=1
    path,owner,_=native_server(bytes(reply))
    with pytest.raises(RuntimeError):client(path,owner,simulation=simulation).close_strict()


@pytest.mark.parametrize('damage',['pid','start_ticks','uid'])
@pytest.mark.parametrize('simulation',[False,True])
def test_foreign_or_reused_native_peer_receives_no_capability(native_server,damage,simulation):
    path,owner,process=native_server(ack())
    changed=dict(owner)
    changed[damage]=(os.getpid() if damage=='pid' else owner[damage]+1)
    with pytest.raises((PermissionError,RuntimeError,ValueError)):
        client(path,changed,simulation=simulation).close_strict()
    assert process.stdout.readline()=='EMPTY\n'


@pytest.mark.parametrize('simulation',[False,True])
def test_native_identity_requires_scoped_generation_incarnation_boot(native_server,simulation):
    body=b'SOID'+bytes((1,1,3))+int(5).to_bytes(8,'big')+b'\x03inc\x04boot'
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body)
    identity=client(path,owner,simulation=simulation).identity()
    assert (identity['generation'],identity['incarnation'],identity['boot'])==(5,'inc','boot')


@pytest.mark.parametrize('damage',['role','generation','control_character','truncated','trailing'])
@pytest.mark.parametrize('simulation',[False,True])
def test_native_identity_rejects_unbound_or_malformed_reply(native_server,damage,simulation):
    body=bytearray(b'SOID'+bytes((1,1,3))+int(5).to_bytes(8,'big')+b'\x03inc\x04boot')
    if damage=='role':body[6]=1
    elif damage=='generation':body[14]=6
    elif damage=='control_character':body[16]=0
    elif damage=='truncated':body=body[:-1]
    else:body+=b'x'
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body)
    with pytest.raises(RuntimeError):client(path,owner,simulation=simulation).identity()


def test_explicit_simulation_transport_cannot_fall_back_to_legacy_library(native_server,monkeypatch):
    path,owner,_=native_server(ack())
    actual_load=head_revocation.ctypes.CDLL
    class LegacyLibrary:
        def __getattr__(self,name):
            if 'simulation' in name:raise AttributeError(name)
            return getattr(self.actual,name)
    def legacy_only(path):
        library=LegacyLibrary();library.actual=actual_load(path);return library
    monkeypatch.setattr(head_revocation.ctypes,'CDLL',legacy_only)
    with pytest.raises(RuntimeError,match='HEAD_REVOKER_NATIVE_TRANSPORT_REQUIRED'):
        client(path,owner,simulation=True)


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
