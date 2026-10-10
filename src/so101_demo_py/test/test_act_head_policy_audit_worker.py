"""Actual owned audit exec tests: no ROS, CUDA, controller or approval."""
import os
from pathlib import Path
import signal
import sys
import time

import pytest

from test_act_head_policy_audit import audit_input


@pytest.fixture
def worker_environment(tmp_path):
    from so101_demo.act import head_feedback_measurement
    source=Path(head_feedback_measurement.__file__).parents[1]
    alias=tmp_path/'source-alias'/'so101_demo';alias.mkdir(parents=True)
    (alias/'__init__.py').write_text('__path__='+repr([str(source)])+'\n')
    return dict(os.environ,PYTHONPATH=str(alias.parent)+os.pathsep+os.environ.get('PYTHONPATH',''))


def test_one_actual_readonly_exec_binds_before_audit_and_retires_with_same_peer(audit_input,worker_environment):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    context,document,reference,_,_=audit_input
    worker=PolicyAuditWorker(context=context,environment=worker_environment,python_executable=sys.executable)
    entry=worker.entry
    try:
        assert worker.is_alive() and entry['motion_authority'] is False
        assert entry['context']==context and entry['parent_peer']['pid']==os.getpid()
        assert entry['peer']['pid']!=os.getpid()
        assert entry['ros_imported'] is False and entry['cuda_imported'] is False
        assert entry['dont_write_bytecode'] is True and entry['collector']['enabled'] is True
        receipt=worker.audit(reference,stop_latency_s=.07)
        assert receipt['peer']==entry['peer'] and receipt['context']==context
        assert receipt['motion_authority'] is False and receipt['audit']['reference']==reference
        assert receipt['audit']['computed']['counts']['decisions']==4000
        assert worker.is_alive()
    finally:retirement=worker.close()
    assert retirement['shutdown_ack'] is True and retirement['exit_code']==0
    assert retirement['peer']==entry['peer'] and not worker.is_alive()


def test_same_entry_cannot_rebind_or_repeat_a_measurement_job(audit_input,worker_environment):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    context,_,reference,_,_=audit_input
    worker=PolicyAuditWorker(context=context,environment=worker_environment,python_executable=sys.executable)
    try:
        worker.audit(reference,stop_latency_s=.07)
        with pytest.raises(PermissionError):worker.audit(reference,stop_latency_s=.07)
    finally:worker.close()
    assert not worker.is_alive()


def test_actual_child_loss_cannot_return_a_verified_measurement_or_fabricate_retirement(audit_input,worker_environment):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    context,_,reference,_,_=audit_input
    worker=PolicyAuditWorker(context=context,environment=worker_environment,python_executable=sys.executable)
    peer=worker.entry['peer']
    try:
        os.kill(peer['pid'],signal.SIGTERM)
        deadline=time.monotonic()+2.
        while worker.is_alive() and time.monotonic()<deadline:time.sleep(.002)
        assert not worker.is_alive()
        with pytest.raises((PermissionError,OSError)):worker.audit(reference,stop_latency_s=.07)
    finally:retirement=worker.close()
    assert retirement['peer']==peer and retirement['shutdown_ack'] is False
    assert retirement['exit_code']!=0


def test_readonly_child_hash_refusal_never_returns_positive_authority(audit_input,worker_environment):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    context,_,reference,_,_=audit_input
    worker=PolicyAuditWorker(context=context,environment=worker_environment,python_executable=sys.executable)
    try:
        with pytest.raises((PermissionError,ValueError)):
            worker.audit(dict(reference,sha256='f'*64),stop_latency_s=.07)
    finally:retirement=worker.close()
    assert not worker.is_alive() and retirement['shutdown_ack'] is False


@pytest.mark.parametrize('damage',['peer','parent','generation','bool_generation','module_hash',
    'module_path','authority','collector','ros','cuda','extra'])
def test_entry_tamper_refuses_and_reaps_the_actual_owned_child(audit_input,worker_environment,monkeypatch,damage):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    original=PolicyAuditWorker._read;owned=[]
    def corrupt(self,deadline):
        value=original(self,deadline);owned.append(self._process)
        if damage=='peer':value['peer']['start_ticks']+=1
        elif damage=='parent':value['parent_peer']['pid']+=1
        elif damage=='generation':value['context']['generation']+=1
        elif damage=='bool_generation':value['context']['generation']=True
        elif damage=='module_hash':next(iter(value['module_origins'].values()))['sha256']='0'*64
        elif damage=='module_path':next(iter(value['module_origins'].values()))['path']='/foreign/module.py'
        elif damage=='authority':value['motion_authority']=True
        elif damage=='collector':value['collector']['thresholds'][0]+=1
        elif damage=='ros':value['ros_imported']=True
        elif damage=='cuda':value['cuda_imported']=True
        else:value['approval']=True
        return value
    monkeypatch.setattr(PolicyAuditWorker,'_read',corrupt)
    with pytest.raises((PermissionError,ValueError)):
        PolicyAuditWorker(context=audit_input[0],environment=worker_environment)
    assert len(owned)==1 and owned[0].poll() is not None


@pytest.mark.parametrize('damage',['peer','parent','context','reference','authority','clock','extra'])
def test_verified_reply_cannot_escape_the_entry_scope(audit_input,worker_environment,monkeypatch,damage):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    worker=PolicyAuditWorker(context=audit_input[0],environment=worker_environment)
    original=worker._read
    def corrupt(deadline):
        value=original(deadline)
        if damage=='peer':value['peer']['start_ticks']+=1
        elif damage=='parent':value['parent_peer']['pid']+=1
        elif damage=='context':value['audit']['context']['session_id']='foreign'
        elif damage=='reference':value['audit']['reference']['sha256']='0'*64
        elif damage=='authority':value['audit']['motion_authority']=True
        elif damage=='clock':value['completed_wall_s']=value['started_wall_s']-1
        else:value['approval']=True
        return value
    monkeypatch.setattr(worker,'_read',corrupt)
    try:
        with pytest.raises((PermissionError,ValueError)):
            worker.audit(audit_input[2],stop_latency_s=.07)
    finally:receipt=worker.close()
    assert receipt['shutdown_ack'] is False and not worker.is_alive()


@pytest.mark.parametrize('damage',['unknown_operation','oversize_request','wrong_context'])
def test_child_protocol_refuses_malformed_requests_without_an_audit(audit_input,worker_environment,damage):
    import json
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    worker=PolicyAuditWorker(context=audit_input[0],environment=worker_environment)
    try:
        if damage=='oversize_request':os.write(worker._process.stdin.fileno(),b'x'*8193+b'\n')
        else:
            request={'operation':'UNKNOWN'}
            if damage=='wrong_context':
                request=dict(operation='AUDIT_MEASUREMENT',reference=audit_input[2],
                    context=dict(audit_input[0],session_id='foreign'),stop_latency_s=.07)
            os.write(worker._process.stdin.fileno(),(json.dumps(request)+'\n').encode('ascii'))
        with pytest.raises(PermissionError):worker._read(time.monotonic()+2.)
    finally:receipt=worker.close()
    assert receipt['shutdown_ack'] is False and receipt['exit_code']==2


def test_oversize_reply_is_refused_at_the_actual_bounded_pipe_reader(audit_input,worker_environment):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    worker=PolicyAuditWorker(context=audit_input[0],environment=worker_environment)
    old=worker._process.stdout;read_fd,write_fd=os.pipe()
    import threading
    def publish():
        try:
            with os.fdopen(write_fd,'wb') as pipe:pipe.write(b'x'*16385+b'\n')
        except BrokenPipeError:pass
    thread=threading.Thread(target=publish);thread.start()
    worker._process.stdout=os.fdopen(read_fd,'rb',buffering=0)
    try:
        with pytest.raises(PermissionError,match='TOO_LARGE'):worker._read(time.monotonic()+2.)
    finally:
        worker._process.stdout.close();thread.join(1.)
        worker._process.stdout=old;worker.close()
    assert not thread.is_alive() and not worker.is_alive()


def test_hung_child_is_owned_reaped_without_a_positive_retirement(audit_input,worker_environment):
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    worker=PolicyAuditWorker(context=audit_input[0],environment=worker_environment)
    os.kill(worker.entry['peer']['pid'],signal.SIGSTOP)
    receipt=worker.close()
    assert receipt['exit_code']==-signal.SIGKILL and receipt['shutdown_ack'] is False
    assert not worker.is_alive()


def test_parent_death_terminates_the_entry_bound_child(audit_input,worker_environment):
    import json
    import subprocess
    from so101_demo.act.head_policy_audit import peer
    script='''import json,sys,time
from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
worker=PolicyAuditWorker(context=json.loads(sys.argv[1]))
print(json.dumps(worker.entry),flush=True)
sys.stdin.read()
worker.close()
'''
    parent=subprocess.Popen([sys.executable,'-B','-c',script,json.dumps(audit_input[0])],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=worker_environment)
    child=None
    try:
        import select
        assert select.select([parent.stdout],[],[],2.)[0]
        entry=json.loads(parent.stdout.readline());child=entry['peer']
        assert entry['parent_peer']['pid']==parent.pid and peer(child['pid'])==child
        parent.terminate();parent.wait(timeout=2.)
        deadline=time.monotonic()+2.
        while time.monotonic()<deadline:
            try:peer(child['pid'])
            except (OSError,PermissionError):break
            time.sleep(.002)
        else:pytest.fail('entry-bound child survived its exact parent')
    finally:
        if parent.poll() is None:parent.kill();parent.wait(timeout=2.)
        for handle in (parent.stdin,parent.stdout,parent.stderr):handle.close()
        if child is not None:
            try:
                if peer(child['pid'])==child:os.kill(child['pid'],signal.SIGKILL)
            except (OSError,PermissionError):pass


def test_large_original_audit_keeps_parent_decoding_bounded_and_progress_original(audit_input,worker_environment,monkeypatch):
    import gc
    import json
    import threading
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    collector=(gc.isenabled(),gc.get_threshold())
    worker=PolicyAuditWorker(context=audit_input[0],environment=worker_environment)
    decoder=json.loads;decoded=[];ticks=[];result=[];errors=[]
    def bounded(payload,*args,**kwargs):
        decoded.append(len(payload));assert len(payload)<=16384
        return decoder(payload,*args,**kwargs)
    monkeypatch.setattr(json,'loads',bounded)
    def run():
        try:result.append(worker.audit(audit_input[2],stop_latency_s=.07))
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=run);thread.start()
    try:
        while thread.is_alive():ticks.append(time.monotonic());thread.join(.002)
        assert not errors and result[0]['audit']['computed']['counts']['decisions']==4000
        assert len(ticks)>10 and decoded and max(decoded)<=16384
        assert (gc.isenabled(),gc.get_threshold())==collector
    finally:worker.close();thread.join(2.)
    assert not worker.is_alive()








def test_pdeathsig_is_bound_to_the_actual_creating_thread(audit_input,worker_environment):
    import threading
    from so101_demo.adapters.act.head_policy_audit_worker import PolicyAuditWorker
    owned=[]
    thread=threading.Thread(target=lambda:owned.append(PolicyAuditWorker(
        context=audit_input[0],environment=worker_environment)))
    thread.start();thread.join(2.)
    assert not thread.is_alive() and len(owned)==1
    worker=owned[0]
    try:
        deadline=time.monotonic()+2.
        while worker.is_alive() and time.monotonic()<deadline:time.sleep(.002)
        assert not worker.is_alive()
    finally:receipt=worker.close()
    assert receipt['exit_code']==-signal.SIGTERM and receipt['shutdown_ack'] is False
