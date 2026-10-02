"""Owned CPU-only exec presence, before native provisioning or motion.

This initial stage has no native capabilities, policy binding, arm, reservation
or action client. It cannot acknowledge dispatch readiness. The owner must later
bind the independently reviewed native/ROS monitor before using that authority.
"""

import argparse
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
import time

from so101_demo.act.head_monitor_ipc import HeadMonitorChannel, HeadMonitorCodec
from .controller_reservation_provision import _private_parent, _process_start_ticks


def _peer(pid):
    return dict(uid=os.geteuid(), pid=pid, start_ticks=_process_start_ticks(pid))


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

    @property
    def identity(self): return dict(self._identity)

    @property
    def receipt(self): return dict(self._receipt, monitor_peer=dict(self._receipt['monitor_peer']))

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

    def close(self):
        if self._closed:
            return dict(event='OWNED_REAP', peer=self.identity, exit_code=self._process.returncode)
        ack = False
        try:
            if self.is_alive():
                try:
                    self.request({'operation':'SHUTDOWN'}); ack = True
                except (OSError, PermissionError):
                    # This is an unarmed exec-only teardown, never a stop proof.
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
                    if type(request) is not dict or set(request)!={'operation'}:
                        raise PermissionError('HEAD_MONITOR_EXEC_OPERATION_REFUSED')
                    operation=request['operation']
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


if __name__=='__main__':
    raise SystemExit(main())
