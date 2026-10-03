"""Owned CPU-only exec presence, before native provisioning or motion.

This initial stage has no native capabilities, policy binding, arm, reservation
or action client. It cannot acknowledge dispatch readiness. The owner must later
bind the independently reviewed native/ROS monitor before using that authority.
"""

import argparse
from concurrent.futures import Future
import json
import math
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

from so101_demo.act.head_monitor_ipc import HeadMonitorChannel, HeadMonitorCodec
from .controller_reservation_provision import _private_parent, _process_start_ticks, _publish_private_provision


def _peer(pid):
    return dict(uid=os.geteuid(), pid=pid, start_ticks=_process_start_ticks(pid))


def _revoked_heartbeat_reply(reply,now):
    """A negative receipt preserves teardown, never heartbeat/readiness authority."""
    fields={'request','stage','monitor_peer','purpose','epoch','generation','session_id',
            'motion_authority','heartbeat_rejected','fault','ack_wall_s'}
    if (type(reply) is not dict or set(reply)!=fields or reply['request']!='HEARTBEAT'
            or reply['stage']!='REVOKED' or reply['heartbeat_rejected'] is not True
            or reply['motion_authority'] is not False):return False
    fault=reply['fault'];ack=reply['ack_wall_s']
    return (type(fault) is dict and set(fault)=={'reason','fault_wall_s'}
        and type(fault['reason']) is str and bool(fault['reason'])
        and type(fault['fault_wall_s']) in (int,float) and math.isfinite(fault['fault_wall_s'])
        and type(ack) in (int,float) and math.isfinite(ack)
        and 0<=fault['fault_wall_s']<=ack<=now)


def _event(handle, event, **fields):
    handle.write((json.dumps(dict(event=event, **fields), sort_keys=True)+'\n').encode('ascii'))
    handle.flush()


def _socket_path(directory):
    path = Path(directory)/'monitor.socket'
    _private_parent(path)
    if len(os.fsencode(path)) > 107:
        raise ValueError('HEAD_MONITOR_EXEC_PATH_TOO_LONG')
    if path.exists() or path.is_symlink():
        raise FileExistsError('HEAD_MONITOR_EXEC_PATH_OCCUPIED')
    return path


class MonitorProcess:
    def __init__(self, process, pid_fd, identity, channel, receipt, log_handle):
        self._process, self._pid_fd = process, pid_fd
        self._identity, self._receipt = dict(identity), dict(receipt)
        self._channel, self._log_handle = channel, log_handle
        self._closed = False
        self._runtime_requested = False
        self._runtime_receipt = None

    @property
    def identity(self): return dict(self._identity)

    @property
    def receipt(self): return dict(self._receipt, monitor_peer=dict(self._receipt['monitor_peer']))

    @property
    def heartbeat_trace(self):
        trace=getattr(self,'_heartbeat_trace',None)
        return None if trace is None else dict(trace)

    def is_alive(self):
        if self._closed or self._process.poll() is not None:
            return False
        try:
            return _peer(self._process.pid) == self._identity
        except (OSError, RuntimeError):
            return False

    def request(self, value):
        if self._closed or not self.is_alive():
            raise PermissionError('HEAD_MONITOR_EXEC_RETIRED')
        reply = self._channel.exchange(value)
        if (type(reply) is not dict or reply.get('request') != value.get('operation')
                or reply.get('stage') != 'EXEC_ONLY' or reply.get('motion_authority') is not False
                or reply.get('monitor_peer') != self._identity):
            self._channel.close()
            raise PermissionError('HEAD_MONITOR_EXEC_ACK_INVALID')
        return reply

    def request_runtime(self,value):
        """The staged calibration protocol; an EXEC_ONLY receipt grants none."""
        if self._closed or not self.is_alive():
            raise PermissionError('HEAD_MONITOR_EXEC_RETIRED')
        if type(value) is not dict or type(value.get('operation')) is not str:
            raise ValueError('HEAD_MONITOR_RUNTIME_REQUEST_INVALID')
        if value['operation']=='CONFIGURE':self._runtime_requested=True
        elif not self._runtime_requested:raise PermissionError('HEAD_MONITOR_CONFIGURE_REQUIRED')
        reply=self._channel.exchange(value)
        return self._runtime_reply(value,reply)

    def request_heartbeat(self,snapshot_factory):
        """Sample original progress only when the authenticated channel is owned."""
        if self._closed or not self.is_alive():
            raise PermissionError('HEAD_MONITOR_EXEC_RETIRED')
        if not self._runtime_requested:raise PermissionError('HEAD_MONITOR_CONFIGURE_REQUIRED')
        if not callable(snapshot_factory):raise ValueError('HEAD_MONITOR_HEARTBEAT_FACTORY_INVALID')
        self._heartbeat_trace={}
        reply=self._channel.exchange_built(
            lambda:dict(operation='HEARTBEAT',heartbeat=snapshot_factory()),trace=self._heartbeat_trace)
        return self._runtime_reply({'operation':'HEARTBEAT'},reply)

    def _runtime_reply(self,value,reply):
        codec=self._channel._codec
        negative=(type(reply) is dict and (reply.get('stage')=='REVOKED'
                  or 'heartbeat_rejected' in reply) and value['operation']=='HEARTBEAT')
        if (type(reply) is not dict or reply.get('request')!=value['operation']
                or reply.get('monitor_peer')!=self._identity or reply.get('purpose')!='calibration'
                or reply.get('epoch')!=codec.epoch or reply.get('generation')!=codec.generation
                or reply.get('session_id')!=codec.session_id or reply.get('motion_authority') is not False
                or (negative and not _revoked_heartbeat_reply(reply,time.monotonic()))
                or (reply.get('stage') not in ('CONFIGURE_PENDING','CONFIGURED','POLICY_READY',
                                             'POLICY_PENDING','ARMED_READY','PRESENT','RETIRE_PENDING','RETIRED')
                    and not (negative or value['operation']=='FAULT' and reply.get('stage')=='REVOKED'))):
            self._channel.close();raise PermissionError('HEAD_MONITOR_RUNTIME_ACK_INVALID')
        if value['operation']=='CONFIGURATION' and reply['stage']=='CONFIGURED':
            self._runtime_receipt=reply
        return reply

    def await_runtime(self,*,phase,timeout_s):
        """Wait for stopped setup work, then obtain the real authenticated ACK.

        The private marker signals completion only. It grants no policy,
        readiness or dispatch authority and never changes a channel deadline.
        """
        names={'configuration':('runtime-config-complete.json','CONFIGURATION'),
               'policy':('runtime-policy-complete.json','POLICY_STATUS'),
               'retirement':('runtime-retire-complete.json','RETIRE_STATUS')}
        if phase not in names or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('HEAD_MONITOR_SETUP_WAIT_INVALID')
        filename,operation=names[phase]
        path=Path(self._channel._connection.getpeername()).parent/filename
        deadline=time.monotonic()+timeout_s
        while time.monotonic()<deadline:
            if not self.is_alive():raise PermissionError('HEAD_MONITOR_EXEC_RETIRED')
            try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            except FileNotFoundError:
                time.sleep(.002);continue
            with os.fdopen(fd,'rb') as handle:
                info=os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=self._identity['uid'] or stat.S_IMODE(info.st_mode)!=0o600:
                    raise PermissionError('HEAD_MONITOR_SETUP_MARKER_INVALID')
                body=handle.read(2049)
            if len(body)>2048:raise PermissionError('HEAD_MONITOR_SETUP_MARKER_INVALID')
            record=json.loads(body);codec=self._channel._codec
            if (type(record) is not dict or set(record)!={'phase','epoch','generation','session_id','monitor_peer','success'}
                    or record['phase']!=phase or record['epoch']!=codec.epoch or record['generation']!=codec.generation
                    or record['session_id']!=codec.session_id or record['monitor_peer']!=self._identity
                    or type(record['success']) is not bool):
                raise PermissionError('HEAD_MONITOR_SETUP_MARKER_INVALID')
            return self.request_runtime({'operation':operation})
        raise TimeoutError('HEAD_MONITOR_STOPPED_SETUP_DEADLINE')

    def close(self):
        if self._closed:
            return dict(event='OWNED_REAP', peer=self.identity, exit_code=self._process.returncode)
        ack = False
        try:
            if self.is_alive():
                try:
                    if self._runtime_requested:
                        self.request_runtime({'operation':'RETIRE'})
                        receipt=self.await_runtime(phase='retirement',timeout_s=.5)
                        if receipt['stage']=='RETIRED':self._runtime_receipt=receipt;ack=True
                    else:self.request({'operation':'SHUTDOWN'}); ack = True
                except (OSError, PermissionError, RuntimeError, ValueError):
                    # Reaping is containment, never authoritative robot stop.
                    ack = False
        finally:
            self._channel.close()
            try:
                result = _retire(self._process, self._pid_fd, self._identity, self._log_handle,
                                 shutdown_ack=ack)
            finally:
                os.close(self._pid_fd)
                self._log_handle.close()
                self._closed = True
        return result


class MonitorRuntimeProtocol:
    """The authenticated server's lazy CPU configuration and owned retirement.

    Slow imports, ROS discovery and fsync run on owned workers. Every exchange
    retains the existing 10 ms channel deadline; no configuration time is motion
    authority and no unknown runtime operation falls back to EXEC_ONLY.
    """
    def __init__(self,config,directory):
        self.config=config;self._future=None;self._runtime=None;self._retire=None
        self._policy_future=None
        self._directory=Path(directory);self._after_send=None

    def _completed(self,phase,future):
        filename={'configuration':'runtime-config-complete.json','policy':'runtime-policy-complete.json',
                  'retirement':'runtime-retire-complete.json'}[phase]
        path=self._directory/filename;parent=_private_parent(path)
        body=json.dumps(dict(phase=phase,epoch=self.config['epoch'],generation=self.config['generation'],
            session_id=self.config['session_id'],monitor_peer=_peer(os.getpid()),success=future.exception() is None),
            sort_keys=True).encode('ascii')
        _publish_private_provision(path,body,parent)

    def after_send(self):
        work,self._after_send=self._after_send,None
        if work is not None:work()

    def handle(self,request):
        operation=request['operation']
        if operation=='CONFIGURE':
            if set(request)!={'operation','configuration'} or self._future is not None:
                raise PermissionError('HEAD_MONITOR_CONFIGURE_REUSED')
            configuration=json.loads(json.dumps(request['configuration'],allow_nan=False))
            self._future=Future()
            def configure():
                try:
                    from .head_monitor_runtime import HeadMonitorRuntime
                    self._runtime=HeadMonitorRuntime(epoch=self.config['epoch'],generation=self.config['generation'],
                        session_id=self.config['session_id'],primary=self.config['primary'])
                    self._runtime.configure(configuration)
                    self._future.set_result(self._runtime)
                    self._runtime._configure_future.add_done_callback(lambda f:self._completed('configuration',f))
                except BaseException as error:
                    if not self._future.done():self._future.set_exception(error)
                    self._completed('configuration',self._future)
            self._after_send=lambda:threading.Thread(target=configure,name='head-monitor-runtime-import',daemon=True).start()
            result=dict(stage='CONFIGURE_PENDING',motion_authority=False)
        elif operation=='CONFIGURATION':
            if set(request)!={'operation'} or self._future is None:
                raise PermissionError('HEAD_MONITOR_CONFIGURE_REQUIRED')
            result=(self._future.result().configuration() if self._future.done() else
                    dict(stage='CONFIGURE_PENDING',motion_authority=False))
        elif operation=='RETIRE':
            if set(request)!={'operation'} or self._retire is not None:
                raise PermissionError('HEAD_MONITOR_RETIRE_REUSED')
            self._retire=Future()
            def retire():
                try:
                    if self._future is not None:self._future.result(timeout=.5)
                    if self._runtime is not None and self._runtime._configure_future is not None:
                        self._runtime._configure_future.result(timeout=.5)
                    result=(self._runtime.close() if self._runtime is not None else
                            dict(stage='RETIRED',motion_authority=False))
                    self._retire.set_result(result)
                except BaseException as error:
                    if self._runtime is not None:self._runtime.fault('HEAD_MONITOR_RETIRE_FAILED',time.monotonic())
                    self._retire.set_exception(error)
                finally:self._completed('retirement',self._retire)
            self._after_send=lambda:threading.Thread(target=retire,name='head-monitor-runtime-retire',daemon=True).start()
            result=dict(stage='RETIRE_PENDING',motion_authority=False)
        elif operation=='RETIRE_STATUS':
            if set(request)!={'operation'} or self._retire is None:
                raise PermissionError('HEAD_MONITOR_RETIRE_REQUIRED')
            result=(self._retire.result() if self._retire.done() else
                    dict(stage='RETIRE_PENDING',motion_authority=False))
        elif operation=='POLICY_STATUS':
            if set(request)!={'operation'} or self._policy_future is None:
                raise PermissionError('HEAD_MONITOR_POLICY_REQUIRED')
            result=(self._policy_future.result() if self._policy_future.done() else
                    dict(stage='POLICY_PENDING',motion_authority=False))
        else:
            if self._future is None or not self._future.done():
                raise PermissionError('HEAD_MONITOR_CONFIGURE_REQUIRED')
            runtime=self._future.result()
            fields={'POLICY':'policy','PREARM_INPUTS':'policy','PREARM_READY':'policy','ARMED_READY':'identities','REGISTER':'inventory',
                    'DISPATCH':'binding','HEARTBEAT':'heartbeat','REJECTION':'response','FAULT':'fault',
                    'EXPOSURE_INPUTS':'exposure','EXPOSURE_ADMIT':'exposure','EXPOSURE_FINISH':'completion',
                    'CALIBRATION_FRAME_INPUTS':'exposure','CALIBRATION_FRAME_COMPLETION':'completion'}
            if operation not in fields or set(request)!={'operation',fields[operation]}:
                raise PermissionError('HEAD_MONITOR_RUNTIME_OPERATION_REFUSED')
            if operation not in ('FAULT','HEARTBEAT'):runtime.configuration()
            value=request[fields[operation]]
            if operation=='POLICY':
                if self._policy_future is not None:raise PermissionError('HEAD_MONITOR_POLICY_REUSED')
                self._policy_future=Future()
                def policy():
                    try:self._policy_future.set_result(runtime.bind_policy(value))
                    except BaseException as error:
                        runtime.fault('HEAD_MONITOR_POLICY_FAILED',time.monotonic())
                        self._policy_future.set_exception(error)
                    finally:self._completed('policy',self._policy_future)
                self._after_send=lambda:threading.Thread(target=policy,name='head-monitor-policy-validation',daemon=True).start()
                result=dict(stage='POLICY_PENDING',motion_authority=False)
            elif operation=='CALIBRATION_FRAME_INPUTS':result=runtime.calibration_frame_inputs(value)
            elif operation=='CALIBRATION_FRAME_COMPLETION':result=runtime.calibration_frame_completion(value)
            elif operation in ('PREARM_INPUTS','PREARM_READY','ARMED_READY','EXPOSURE_INPUTS','EXPOSURE_ADMIT','EXPOSURE_FINISH'):
                if self._policy_future is None or not self._policy_future.done():
                    raise PermissionError('HEAD_MONITOR_POLICY_ACK_REQUIRED')
                self._policy_future.result()
                result=(runtime.prearm_inputs(value) if operation=='PREARM_INPUTS' else
                        runtime.prearm_ready(value) if operation=='PREARM_READY' else
                        runtime.exposure_inputs(value) if operation=='EXPOSURE_INPUTS' else
                        runtime.exposure_admit(value) if operation=='EXPOSURE_ADMIT' else
                        runtime.exposure_finish(value) if operation=='EXPOSURE_FINISH' else runtime.armed_ready(value))
            elif operation=='REGISTER':result=runtime.register(value)
            elif operation=='DISPATCH':result=runtime.dispatch(value)
            elif operation=='HEARTBEAT':result=runtime.heartbeat(value)
            elif operation=='REJECTION':
                runtime.rejection(value);result=dict(stage=runtime.epoch.stage,motion_authority=False)
            else:
                # This receipt confirms only irreversible local revocation;
                # the owned native closer still has to prove its own ACK.
                result=runtime.notice_fault(value)
        return dict(result,request=operation,monitor_peer=_peer(os.getpid()),purpose='calibration',
                    epoch=self.config['epoch'],generation=self.config['generation'],
                    session_id=self.config['session_id'])

    def disconnected(self):
        if self._runtime is not None and not self._runtime._finished:
            self._runtime.fault('HEAD_MONITOR_CHANNEL_LOST',time.monotonic())
            self._runtime.close()


def _retire(process, pid_fd, identity, handle, *, shutdown_ack):
    def signal_if_live(number):
        if process.poll() is not None:return
        try:actual = _peer(process.pid)
        except (OSError, RuntimeError):
            # Popen/waitpid is authoritative for our own child's exit; a
            # disappearing /proc record or zombie must not interrupt reaping.
            if process.poll() is not None:return
            raise PermissionError('HEAD_MONITOR_EXEC_TEARDOWN_UNCONFIRMED') from None
        if actual != identity:
            raise PermissionError('HEAD_MONITOR_EXEC_TEARDOWN_IDENTITY_INVALID')
        try:signal.pidfd_send_signal(pid_fd, number)
        except ProcessLookupError:
            if process.poll() is None:raise
    try:
        process.wait(timeout=.5)
    except subprocess.TimeoutExpired:
        signal_if_live(signal.SIGTERM)
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            signal_if_live(signal.SIGKILL)
            process.wait(timeout=.5)
    result = dict(peer=dict(identity), exit_code=process.returncode, shutdown_ack=shutdown_ack)
    _event(handle, 'OWNED_REAP', **result)
    return dict(event='OWNED_REAP', **result)


def start_monitor(*, python_executable, ipc_directory, log_path, epoch, generation,
                  session_id, startup_timeout_s, environment=None):
    """Start exactly one exec child; fail closed and reap it if presence fails."""
    executable = Path(python_executable)
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise FileNotFoundError('HEAD_MONITOR_EXEC_EXECUTABLE_INVALID')
    if (type(startup_timeout_s) not in (int, float) or not math.isfinite(startup_timeout_s)
            or not 0 < startup_timeout_s <= 10 or not hasattr(os, 'pidfd_open')
            or not hasattr(signal, 'pidfd_send_signal')):
        raise ValueError('HEAD_MONITOR_EXEC_CONFIG_INVALID')
    path = _socket_path(ipc_directory)
    log = Path(log_path)
    if not log.is_absolute():
        raise ValueError('HEAD_MONITOR_EXEC_LOG_INVALID')
    secret = secrets.token_bytes(32)
    codec = HeadMonitorCodec(secret=secret, epoch=epoch, generation=generation,
                            session_id=session_id, role='primary')
    primary = _peer(os.getpid())
    config = dict(secret=secret.hex(), epoch=epoch, generation=generation,
                  session_id=session_id, primary=primary)
    body = json.dumps(config, sort_keys=True).encode('ascii')
    if len(body)+4 > 4096:
        raise ValueError('HEAD_MONITOR_EXEC_BOOTSTRAP_TOO_LARGE')
    env = dict(os.environ if environment is None else environment)
    if any(type(key) is not str or type(value) is not str for key, value in env.items()):
        raise ValueError('HEAD_MONITOR_EXEC_ENV_INVALID')
    env['CUDA_VISIBLE_DEVICES']='';env['HIP_VISIBLE_DEVICES']='';env['ROCR_VISIBLE_DEVICES']=''
    log_handle = log.open('xb')
    read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
    process = channel = None
    pid_fd = None
    identity = None
    connection = None
    started = time.monotonic()
    deadline = started+startup_timeout_s
    def remaining_startup():
        remaining = deadline-time.monotonic()
        if remaining <= 0:raise TimeoutError('HEAD_MONITOR_EXEC_STARTUP_DEADLINE')
        return remaining
    try:
        argv = [str(executable), '-m', 'so101_demo.adapters.act.head_monitor_process',
                '--bootstrap-fd', str(read_fd), '--socket', str(path)]
        process = subprocess.Popen(argv, pass_fds=(read_fd,), close_fds=True,
            stdin=subprocess.DEVNULL, stdout=log_handle, stderr=log_handle, env=env)
        identity = _peer(process.pid)
        pid_fd = os.pidfd_open(process.pid)
        _event(log_handle, 'OWNED_EXEC', peer=identity, executable=str(executable),
               resolved_executable=str(executable.resolve()), argv=argv)
        os.close(read_fd);read_fd=None
        if os.write(write_fd, len(body).to_bytes(4, 'big')+body) != len(body)+4:
            raise RuntimeError('HEAD_MONITOR_EXEC_BOOTSTRAP_INCOMPLETE')
        os.close(write_fd);write_fd=None
        while True:
            if process.poll() is not None:
                raise RuntimeError('HEAD_MONITOR_EXEC_EARLY_EXIT')
            remaining_startup()
            try:
                endpoint = path.lstat()
            except FileNotFoundError:
                time.sleep(.002);continue
            if (not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != primary['uid']
                    or stat.S_IMODE(endpoint.st_mode) != 0o600):
                raise PermissionError('HEAD_MONITOR_EXEC_ENDPOINT_INVALID')
            break
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(remaining_startup())
        connection.connect(str(path))
        channel = HeadMonitorChannel(connection, codec=codec, peer=identity,
                                     timeout_s=min(.010, remaining_startup()))
        reply = channel.exchange({'operation':'PRESENCE'})
        remaining_startup()
        fields = {'request','stage','motion_authority','monitor_peer','cpu_only','module_path'}
        if (type(reply) is not dict or set(reply) != fields or reply['request'] != 'PRESENCE'
                or reply['stage'] != 'EXEC_ONLY' or reply['motion_authority'] is not False
                or reply['monitor_peer'] != identity or reply['cpu_only'] is not True
                or type(reply['module_path']) is not str or not reply['module_path']):
            raise PermissionError('HEAD_MONITOR_EXEC_PRESENCE_INVALID')
        _event(log_handle, 'EXEC_ONLY', receipt=reply, elapsed_s=time.monotonic()-started)
        remaining_startup()
        return MonitorProcess(process, pid_fd, identity, channel, reply, log_handle)
    except BaseException:
        if channel is not None: channel.close()
        elif connection is not None: connection.close()
        try:
            if process is not None and identity is not None and pid_fd is not None:
                try:_retire(process, pid_fd, identity, log_handle, shutdown_ack=False)
                finally:os.close(pid_fd)
            elif process is not None:
                # The unpublished, unreaped child cannot have a reused PID.
                if process.poll() is None:process.terminate()
                process.wait(timeout=.5)
        finally:log_handle.close()
        raise
    finally:
        if read_fd is not None: os.close(read_fd)
        if write_fd is not None: os.close(write_fd)


def _bootstrap(fd):
    def read(size):
        data=bytearray()
        while len(data)<size:
            part=os.read(fd,size-len(data))
            if not part:raise PermissionError('HEAD_MONITOR_EXEC_PIPE_INCOMPLETE')
            data.extend(part)
        return bytes(data)
    size=int.from_bytes(read(4),'big')
    if not 0 < size <= 4092:raise PermissionError('HEAD_MONITOR_EXEC_PIPE_INVALID')
    body=read(size)
    if os.read(fd,1):raise PermissionError('HEAD_MONITOR_EXEC_PIPE_TRAILING_BYTES')
    os.close(fd)
    config=json.loads(body)
    if (type(config) is not dict
            or set(config)!={'secret','epoch','generation','session_id','primary'}
            or type(config['secret']) is not str or len(config['secret'])!=64
            or config['primary']!=_peer(os.getppid())):
        raise PermissionError('HEAD_MONITOR_EXEC_BOOTSTRAP_INVALID')
    return config


def main():
    parser=argparse.ArgumentParser(description='Unarmed CPU-only Head monitor exec presence')
    parser.add_argument('--bootstrap-fd',type=int,required=True)
    parser.add_argument('--socket',required=True)
    args=parser.parse_args()
    runtime_protocol=None
    try:
        config=_bootstrap(args.bootstrap_fd)
        codec=HeadMonitorCodec(secret=bytes.fromhex(config['secret']),epoch=config['epoch'],
            generation=config['generation'],session_id=config['session_id'],role='monitor')
        path=Path(args.socket)
        if _socket_path(path.parent)!=path:
            raise PermissionError('HEAD_MONITOR_EXEC_SOCKET_INVALID')
        cpu_only=not any(name in sys.modules for name in ('torch','mujoco'))
        if not cpu_only or os.environ.get('CUDA_VISIBLE_DEVICES')!='':
            raise PermissionError('HEAD_MONITOR_EXEC_CPU_ONLY_REQUIRED')
        identity=_peer(os.getpid());primary=config['primary']
        runtime_protocol=MonitorRuntimeProtocol(config,Path(args.socket).parent)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
            previous_mask=os.umask(0o177)
            try:server.bind(str(path))
            finally:os.umask(previous_mask)
            server.listen(1);server.setblocking(False)
            while True:
                if _peer(primary['pid'])!=primary:
                    raise PermissionError('HEAD_MONITOR_EXEC_PRIMARY_LOST')
                if select.select([server],[],[],.002)[0]:break
            with server.accept()[0] as connection:
                channel=HeadMonitorChannel(connection,codec=codec,peer=primary,timeout_s=.010)
                presented=False
                while True:
                    if _peer(primary['pid'])!=primary:
                        raise PermissionError('HEAD_MONITOR_EXEC_PRIMARY_LOST')
                    if not select.select([connection],[],[],.002)[0]:continue
                    request=channel.receive()
                    if type(request) is not dict or type(request.get('operation')) is not str:
                        raise PermissionError('HEAD_MONITOR_EXEC_OPERATION_REFUSED')
                    operation=request['operation']
                    if presented and operation in ('CONFIGURE','CONFIGURATION','POLICY','PREARM_INPUTS','PREARM_READY','ARMED_READY',
                            'POLICY_STATUS','REGISTER','DISPATCH','REJECTION','FAULT','RETIRE','RETIRE_STATUS',
                            'EXPOSURE_INPUTS','EXPOSURE_ADMIT','EXPOSURE_FINISH',
                            'CALIBRATION_FRAME_INPUTS','CALIBRATION_FRAME_COMPLETION'):
                        reply=runtime_protocol.handle(request)
                        channel.send(reply)
                        runtime_protocol.after_send()
                        if operation=='RETIRE_STATUS' and reply.get('stage')=='RETIRED':
                            # The owner must finish its post-ACK live-peer check
                            # before this exact exec peer exits. EOF after a
                            # verified retirement is normal, not protocol refusal.
                            while _peer(primary['pid'])==primary:
                                if select.select([connection],[],[],.002)[0]:
                                    if connection.recv(1):
                                        raise PermissionError('HEAD_MONITOR_EXEC_RETIRE_TRAILING_BYTES')
                                    break
                            break
                        continue
                    if operation=='HEARTBEAT' and runtime_protocol._future is not None:
                        channel.send(runtime_protocol.handle(request))
                        continue
                    if set(request)!={'operation'} or runtime_protocol._future is not None:
                        raise PermissionError('HEAD_MONITOR_EXEC_OPERATION_REFUSED')
                    if operation=='PRESENCE' and not presented:presented=True
                    elif operation in ('HEARTBEAT','SHUTDOWN') and presented:pass
                    else:raise PermissionError('HEAD_MONITOR_EXEC_OPERATION_REFUSED')
                    reply=dict(request=operation,stage='EXEC_ONLY',motion_authority=False,
                        monitor_peer=identity,cpu_only=cpu_only,module_path=str(Path(__file__).resolve()))
                    channel.send(reply)
                    if operation=='SHUTDOWN':
                        # Remain live for the owner's post-reply peer check.
                        while _peer(primary['pid'])==primary:
                            if select.select([connection],[],[],.002)[0]:
                                if connection.recv(1):
                                    raise PermissionError('HEAD_MONITOR_EXEC_SHUTDOWN_TRAILING_BYTES')
                                break
                        break
        return 0
    except (OSError,RuntimeError,ValueError,PermissionError):
        # No bootstrap payload, key, capability or exception data is logged.
        print(json.dumps(dict(event='EXEC_ONLY_REFUSED',motion_authority=False)),flush=True)
        return 2
    finally:
        if runtime_protocol is not None:
            try:runtime_protocol.disconnected()
            except BaseException:
                print(json.dumps(dict(event='RUNTIME_RETIRE_UNCONFIRMED',motion_authority=False)),flush=True)


if __name__=='__main__':
    raise SystemExit(main())
