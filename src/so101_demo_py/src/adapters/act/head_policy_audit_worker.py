"""One entry-bound read-only calibration audit child of the CPU monitor."""
from copy import deepcopy
import gc
import json
import math
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import time

from so101_demo.act import head_policy_audit as audit

class PolicyAuditWorker:
    def __init__(self, *, context, environment=None, python_executable=None, startup_timeout_s=2.):
        audit.validate_context(context)
        executable=Path(sys.executable if python_executable is None else python_executable)
        if not executable.is_absolute() or not os.access(executable,os.X_OK):
            raise ValueError('HEAD_POLICY_AUDIT_EXECUTABLE_INVALID')
        if type(startup_timeout_s) not in (int,float) or not math.isfinite(startup_timeout_s) or startup_timeout_s<=0:
            raise ValueError('HEAD_POLICY_AUDIT_STARTUP_TIMEOUT_INVALID')
        self._context=deepcopy(context);self._parent=audit.peer(os.getpid())
        self._entry=None;self._identity=None;self._closed=False;self._failed=False;self._used=False
        self._receipt=None;self._pid_fd=None;self._lock=threading.Lock()
        env=dict(os.environ if environment is None else environment)
        env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
        self._process=subprocess.Popen([str(executable),'-B','-m','so101_demo.act.head_policy_audit'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,close_fds=True,env=env)
        try:
            self._pid_fd=os.pidfd_open(self._process.pid)
            self._identity=audit.peer(self._process.pid)
            os.set_blocking(self._process.stdin.fileno(),False)
            os.set_blocking(self._process.stdout.fileno(),False)
            deadline=time.monotonic()+startup_timeout_s
            self._write(dict(operation='BIND_ENTRY',parent_peer=self._parent,context=self._context),deadline)
            entry=self._read(deadline)
            self._check_common(entry)
            if (set(entry)!={'event','peer','parent_peer','context','motion_authority','module_origins',
                            'collector','dont_write_bytecode','ros_imported','cuda_imported'}
                    or entry['event']!='POLICY_AUDIT_ENTRY'
                    or entry['module_origins']!=audit.module_origins()
                    or entry['collector']!=dict(enabled=gc.isenabled(),thresholds=list(gc.get_threshold()))
                    or entry['dont_write_bytecode'] is not True
                    or entry['ros_imported'] is not False or entry['cuda_imported'] is not False
                    or not self.is_alive()):
                raise PermissionError('HEAD_POLICY_AUDIT_ENTRY_INVALID')
            self._entry=deepcopy(entry)
        except BaseException:
            self._failed=True
            self._finish(shutdown_ack=False)
            raise

    @property
    def entry(self):
        if self._entry is None:raise PermissionError('HEAD_POLICY_AUDIT_UNBOUND')
        return deepcopy(self._entry)

    def is_alive(self):
        if self._closed or self._process.poll() is not None:return False
        try:return audit.peer(self._process.pid)==self._identity
        except (OSError,PermissionError):return False

    def _check_common(self,reply):
        if (type(reply) is not dict or reply.get('peer')!=self._identity
                or reply.get('parent_peer')!=self._parent or reply.get('context')!=self._context
                or reply.get('motion_authority') is not False):
            raise PermissionError('HEAD_POLICY_AUDIT_REPLY_SCOPE_INVALID')
        for key in ('peer','parent_peer'):
            value=reply[key]
            if (type(value) is not dict or set(value)!={'uid','pid','start_ticks'}
                    or any(type(item) is not int for item in value.values())):
                raise PermissionError('HEAD_POLICY_AUDIT_REPLY_SCOPE_INVALID')
        audit.validate_context(reply['context'])

    def _write(self,record,deadline):
        data=(json.dumps(record,sort_keys=True,allow_nan=False)+'\n').encode('ascii')
        if len(data)>audit._REQUEST_LIMIT:raise ValueError('HEAD_POLICY_AUDIT_REQUEST_TOO_LARGE')
        offset=0;fd=self._process.stdin.fileno()
        while offset<len(data):
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([], [fd], [], remaining)[1]:
                raise TimeoutError('HEAD_POLICY_AUDIT_WRITE_DEADLINE')
            try:offset+=os.write(fd,data[offset:])
            except BlockingIOError:continue

    def _read(self,deadline):
        data=bytearray();fd=self._process.stdout.fileno()
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([fd],[],[],remaining)[0]:
                raise TimeoutError('HEAD_POLICY_AUDIT_READ_DEADLINE')
            try:chunk=os.read(fd,audit._REPLY_LIMIT+1-len(data))
            except BlockingIOError:continue
            if not chunk:raise PermissionError('HEAD_POLICY_AUDIT_EOF')
            data.extend(chunk)
            if len(data)>audit._REPLY_LIMIT:raise PermissionError('HEAD_POLICY_AUDIT_REPLY_TOO_LARGE')
            if b'\n' in data:
                if data.index(b'\n')!=len(data)-1:
                    raise PermissionError('HEAD_POLICY_AUDIT_REPLY_TRAILING_BYTES')
                return json.loads(data)

    def audit(self,reference,*,stop_latency_s):
        with self._lock:
            if self._used or self._failed or not self.is_alive():
                raise PermissionError('HEAD_POLICY_AUDIT_JOB_REFUSED')
            self._used=True
            try:
                started=time.monotonic();deadline=started+5.
                self._write(dict(operation='AUDIT_MEASUREMENT',context=self._context,
                    reference=reference,stop_latency_s=stop_latency_s),deadline)
                reply=self._read(deadline);self._check_common(reply)
                if (set(reply)!={'event','peer','parent_peer','context','motion_authority','audit',
                                 'started_wall_s','completed_wall_s'}
                        or reply['event']!='MEASUREMENT_VERIFIED' or not self.is_alive()):
                    raise PermissionError('HEAD_POLICY_AUDIT_JOB_REPLY_INVALID')
                result=reply['audit']
                if (type(result) is not dict
                        or set(result)!={'purpose','motion_authority','reference','context','body_sha256','computed'}
                        or result['purpose']!='calibration' or result['motion_authority'] is not False
                        or result['reference']!=reference or result['context']!=self._context
                        or type(result['body_sha256']) is not str or not audit._SHA.fullmatch(result['body_sha256'])
                        or type(result['computed']) is not dict
                        or result['computed'].get('purpose')!='calibration'
                        or result['computed'].get('motion_authority') is not False):
                    raise PermissionError('HEAD_POLICY_AUDIT_RESULT_INVALID')
                clocks=(reply['started_wall_s'],reply['completed_wall_s'])
                if (any(type(t) not in (int,float) or not math.isfinite(t) for t in clocks)
                        or not started<=clocks[0]<=clocks[1]<=time.monotonic()):
                    raise PermissionError('HEAD_POLICY_AUDIT_RESULT_CLOCK_INVALID')
                return deepcopy(reply)
            except BaseException:
                self._failed=True
                raise

    def _finish(self,*,shutdown_ack):
        try:
            try:self._process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                if self._pid_fd is not None:
                    try:signal.pidfd_send_signal(self._pid_fd,signal.SIGTERM)
                    except ProcessLookupError:pass
                else:self._process.terminate()
                try:self._process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    if self._pid_fd is not None:signal.pidfd_send_signal(self._pid_fd,signal.SIGKILL)
                    else:self._process.kill()
                    self._process.wait(timeout=.2)
            self._receipt=dict(event='POLICY_AUDIT_OWNED_REAP',peer=self._identity,
                exit_code=self._process.returncode,shutdown_ack=shutdown_ack and self._process.returncode==0,
                motion_authority=False)
        finally:
            self._process.stdin.close();self._process.stdout.close()
            if self._pid_fd is not None:os.close(self._pid_fd);self._pid_fd=None
            self._closed=True
        return deepcopy(self._receipt)

    def close(self):
        if self._closed:return deepcopy(self._receipt)
        ack=False;locked=self._lock.acquire(timeout=.010)
        try:
            if locked and not self._failed and self.is_alive():
                deadline=time.monotonic()+.2
                try:
                    self._write(dict(operation='RETIRE'),deadline)
                    reply=self._read(deadline);self._check_common(reply)
                    if (set(reply)!={'event','peer','parent_peer','context','motion_authority','collector'}
                            or reply['event']!='POLICY_AUDIT_RETIRED'
                            or reply['collector']!=self._entry['collector'] or not self.is_alive()):
                        raise PermissionError('HEAD_POLICY_AUDIT_RETIRE_INVALID')
                    ack=True
                except (OSError,PermissionError,ValueError,TimeoutError):self._failed=True
            self._process.stdin.close()
            return self._finish(shutdown_ack=ack)
        finally:
            if locked:self._lock.release()
