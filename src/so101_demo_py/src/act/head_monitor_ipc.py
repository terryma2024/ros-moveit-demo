"""Authenticated bounded Head monitor messages, without motion authority.

Use only on the operation/IPC worker, never on a watchdog or under its locks.
The owner authenticates an actual exec peer and privately supplies the key.
Connected socketpair credentials do not establish a child's post-exec identity.
"""

import hashlib
import hmac
import json
import math
import re
import socket
import struct
import threading
import time
from contextlib import contextmanager

from .head_evidence_identity import bounded_payload as _bounded_payload
from .head_evidence_identity import check_deadline as _check_deadline
from so101_demo.adapters.act.controller_reservation_provision import _process_start_ticks


_DOMAIN = b'SO101-HEAD-MONITOR-v1\0'
_MAX_BODY = 70000
_MAX_PAYLOAD = 65536
_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z', re.ASCII)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('HEAD_MONITOR_IPC_DUPLICATE_FIELD')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('HEAD_MONITOR_IPC_NONFINITE')


class HeadMonitorCodec:
    def __init__(self, *, secret, epoch, generation, session_id, role):
        if (not isinstance(secret, bytes) or len(secret) != 32 or not any(secret)
                or any(type(value) is not str or not _IDENTIFIER.fullmatch(value)
                       for value in (epoch, session_id))
                or type(generation) is not int or not 0 < generation < 2**64
                or type(role) is not str or role not in ('primary', 'monitor')):
            raise ValueError('HEAD_MONITOR_IPC_CONFIG_INVALID')
        self._secret = secret
        self._scope = (epoch, generation, session_id, role)
        self._sent = self._received = 0
        self._failed = False
        self._lock = threading.Lock()

    @property
    def epoch(self): return self._scope[0]

    @property
    def generation(self): return self._scope[1]

    @property
    def session_id(self): return self._scope[2]

    @property
    def role(self): return self._scope[3]

    @property
    def sequence(self): return self._sent

    @property
    def failed(self): return self._failed

    def fail(self):
        # Irreversible atomic latch in this CPython process: no lock, I/O or
        # serialization can delay fault publication or channel closure.
        self._failed = True

    @contextmanager
    def _state(self, deadline):
        _check_deadline(deadline)
        if deadline is None:
            acquired = self._lock.acquire()
        else:
            acquired = self._lock.acquire(timeout=max(0., deadline-time.monotonic()))
        if not acquired:
            raise TimeoutError('HEAD_MONITOR_IPC_LOCK_DEADLINE')
        try:
            _check_deadline(deadline)
            yield
        finally:
            self._lock.release()

    def _require(self):
        if self._failed:
            raise PermissionError('HEAD_MONITOR_IPC_REVOKED')

    def encode(self, payload, *, deadline=None):
        try:
            self._require()
            payload = _bounded_payload(payload, deadline)
            if len(_canonical(payload)) > _MAX_PAYLOAD:
                raise ValueError('HEAD_MONITOR_IPC_PAYLOAD_INVALID')
            _check_deadline(deadline)
            with self._state(deadline):
                self._require()
                sequence = self._sent+1
                if sequence >= 2**64:
                    raise ValueError('HEAD_MONITOR_IPC_SEQUENCE_EXHAUSTED')
                value = dict(version=1, epoch=self.epoch, generation=self.generation,
                             session_id=self.session_id, role=self.role,
                             sequence=sequence, payload=payload)
                value['mac'] = hmac.new(self._secret, _DOMAIN+_canonical(value),
                                        hashlib.sha256).hexdigest()
                body = _canonical(value)
                if len(body) > _MAX_BODY:
                    raise ValueError('HEAD_MONITOR_IPC_BODY_TOO_LARGE')
                _check_deadline(deadline)
                self._require()
                self._sent = sequence
                return body
        except OSError:
            self.fail()
            raise
        except (TypeError, ValueError, OverflowError, RuntimeError, RecursionError):
            self.fail()
            raise ValueError('HEAD_MONITOR_IPC_OUTBOUND_INVALID') from None

    def decode(self, body, *, deadline=None):
        try:
            self._require()
            _check_deadline(deadline)
            if type(body) is not bytes or not 0 < len(body) <= _MAX_BODY:
                raise ValueError('HEAD_MONITOR_IPC_BODY_INVALID')
            value = json.loads(body, object_pairs_hook=_pairs, parse_constant=_constant)
            fields = {'version', 'epoch', 'generation', 'session_id', 'role',
                      'sequence', 'payload', 'mac'}
            if type(value) is not dict or set(value) != fields or _canonical(value) != body:
                raise ValueError('HEAD_MONITOR_IPC_ENVELOPE_INVALID')
            supplied = value.pop('mac')
            if type(supplied) is not str or not re.fullmatch(r'[0-9a-f]{64}', supplied):
                raise ValueError('HEAD_MONITOR_IPC_MAC_INVALID')
            expected = hmac.new(self._secret, _DOMAIN+_canonical(value), hashlib.sha256).hexdigest()
            peer_role = 'monitor' if self.role == 'primary' else 'primary'
            if (not hmac.compare_digest(supplied, expected)
                    or type(value['version']) is not int or value['version'] != 1
                    or value['epoch'] != self.epoch or type(value['epoch']) is not str
                    or type(value['generation']) is not int or value['generation'] != self.generation
                    or value['session_id'] != self.session_id or type(value['session_id']) is not str
                    or value['role'] != peer_role or type(value['role']) is not str
                    or type(value['sequence']) is not int or not 0 < value['sequence'] < 2**64
                    or type(value['payload']) is not dict
                    or len(_canonical(value['payload'])) > _MAX_PAYLOAD):
                raise PermissionError('HEAD_MONITOR_IPC_AUTH_INVALID')
            _check_deadline(deadline)
            with self._state(deadline):
                self._require()
                if value['sequence'] != self._received+1:
                    raise PermissionError('HEAD_MONITOR_IPC_SEQUENCE_INVALID')
                self._received = value['sequence']
                return value['payload']
        except OSError:
            self.fail()
            raise
        except (TypeError, ValueError, OverflowError, RecursionError):
            self.fail()
            raise PermissionError('HEAD_MONITOR_IPC_REFUSED') from None


class HeadMonitorChannel:
    """Exact live connected peer, one deadline, no retries or error suppression."""

    def __init__(self, connection, *, codec, peer, timeout_s, simulation_policy=None):
        from .head_simulation_policy import HeadSimulationPolicy
        self._simulation_policy = (None if simulation_policy is None else
            simulation_policy if isinstance(simulation_policy, HeadSimulationPolicy) else
            HeadSimulationPolicy.parse(simulation_policy))
        limit = .010 if self._simulation_policy is None else self._simulation_policy.heartbeat_rpc_timeout_s
        if (not isinstance(connection, socket.socket) or connection.family != socket.AF_UNIX
                or connection.type != socket.SOCK_STREAM or not isinstance(codec, HeadMonitorCodec)
                or type(peer) is not dict or set(peer) != {'uid', 'pid', 'start_ticks'}
                or any(type(value) is not int for value in peer.values())
                or not 0 <= peer['uid'] < 2**32 or not 0 < peer['pid'] < 2**31
                or not 0 < peer['start_ticks'] < 2**64
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= limit
                or (self._simulation_policy is not None and timeout_s != limit)):
            raise ValueError('HEAD_MONITOR_CHANNEL_CONFIG_INVALID')
        self._connection, self._codec = connection, codec
        self._peer = dict(peer)
        self._timeout = timeout_s
        self._io_lock = threading.Lock()
        self._pending = None
        try:
            self._verify_peer()
        except (OSError, RuntimeError, PermissionError):
            self._fail()
            raise PermissionError('HEAD_MONITOR_CHANNEL_PEER_INVALID') from None

    def _verify_peer(self):
        pid, uid, _ = struct.unpack('3i', self._connection.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if (uid != self._peer['uid'] or pid != self._peer['pid']
                or _process_start_ticks(pid) != self._peer['start_ticks']):
            raise PermissionError('HEAD_MONITOR_CHANNEL_PEER_INVALID')

    def _fail(self):
        self._codec.fail()
        self._connection.close()

    def close(self):
        self._fail()

    def _remaining(self, deadline):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('HEAD_MONITOR_CHANNEL_DEADLINE')
        return remaining

    def _write(self, payload, deadline):
        self._verify_peer()
        body = self._codec.encode(payload, deadline=deadline)
        self._codec._require()
        self._connection.settimeout(self._remaining(deadline))
        self._connection.sendall(len(body).to_bytes(4, 'big')+body)
        self._verify_peer()
        self._remaining(deadline)

    def _read(self, deadline, operation=None):
        self._verify_peer()
        if self._pending is None:
            self._pending = dict(started_wall_s=self._operation_started_wall_s, prefix=bytearray(),
                body=bytearray(), size=None, decoded=None, operation=operation)
        pending = self._pending
        def read(result, size):
            while len(result) < size:
                self._connection.settimeout(self._remaining(deadline))
                part = self._connection.recv(size-len(result))
                if not part:
                    raise ConnectionError('HEAD_MONITOR_CHANNEL_INCOMPLETE')
                result.extend(part)
            return bytes(result)
        if pending['size'] is None:
            pending['size'] = int.from_bytes(read(pending['prefix'], 4), 'big')
        size = pending['size']
        if not 0 < size <= _MAX_BODY:
            raise PermissionError('HEAD_MONITOR_CHANNEL_LENGTH_INVALID')
        if pending['decoded'] is None:
            pending['decoded'] = self._codec.decode(read(pending['body'], size), deadline=deadline)
        value = pending['decoded']
        self._verify_peer()
        self._remaining(deadline)
        self._pending = None
        return value

    def _operation(self, operation, *, trace=None, wait_other_operation=None):
        started = time.monotonic();deadline = started+self._timeout
        acquired = False
        if trace is not None:
            trace.update(started_wall_s=started,deadline_wall_s=deadline,
                         phase='slot_wait',error_type=None,error_code=None)
        try:
            acquired = self._io_lock.acquire(timeout=self._remaining(deadline))
            if not acquired:
                raise TimeoutError('HEAD_MONITOR_CHANNEL_BUSY')
            if trace is not None:trace['slot_owned_wall_s']=time.monotonic()
            if self._pending is not None:
                if (self._simulation_policy is not None and type(wait_other_operation) is str
                        and type(self._pending['operation']) is str
                        and self._pending['operation']!=wait_other_operation):
                    raise TimeoutError('HEAD_MONITOR_CHANNEL_OTHER_OWNER_PENDING')
                raise PermissionError('HEAD_MONITOR_CHANNEL_PENDING_FRAME')
            self._operation_started_wall_s = started
            return operation(deadline)
        except BaseException as error:
            if trace is not None:
                args=BaseException.args.__get__(error)
                trace['error_type']=type(error).__name__
                trace['error_code']=args[0] if args and type(args[0]) is str and len(args[0])<=128 else None
            recoverable = (self._simulation_policy is not None and isinstance(error, TimeoutError)
                and ((acquired and self._pending is not None) or not acquired))
            if not recoverable and isinstance(error,(OSError,RuntimeError,ValueError,PermissionError)):
                self._fail()
            raise
        finally:
            if acquired:
                self._io_lock.release()
            if trace is not None:trace['ended_wall_s']=time.monotonic()

    def complete_pending(self, deadline_wall_s):
        """Finish only the original frame; this receipt alone grants no authority."""
        acquired = False
        try:
            self._codec._require()
            if self._simulation_policy is None or self._pending is None:
                raise PermissionError('HEAD_MONITOR_CHANNEL_NO_PENDING_FRAME')
            pending = self._pending
            cap = pending['started_wall_s'] + self._simulation_policy.supervision_stale_s
            if (type(deadline_wall_s) not in (int, float) or not math.isfinite(deadline_wall_s)
                    or deadline_wall_s > cap):
                raise ValueError('HEAD_MONITOR_CHANNEL_RECOVERY_DEADLINE_INVALID')
            acquired = self._io_lock.acquire(timeout=self._remaining(deadline_wall_s))
            if not acquired:
                raise TimeoutError('HEAD_MONITOR_CHANNEL_BUSY')
            if self._pending is not pending:
                raise PermissionError('HEAD_MONITOR_CHANNEL_PENDING_FRAME_CHANGED')
            return self._read(deadline_wall_s)
        except BaseException:
            self._fail()
            raise
        finally:
            if acquired:
                self._io_lock.release()

    def send(self, payload):
        return self._operation(lambda deadline: self._write(payload, deadline))

    def receive(self):
        return self._operation(self._read)

    def exchange(self, payload, *, trace=None):
        def mark(phase):
            if trace is not None:
                trace['phase']=phase;trace[phase+'_wall_s']=time.monotonic()
        def request(deadline):
            mark('write')
            self._write(payload, deadline)
            mark('read')
            reply=(self._read(deadline) if self._simulation_policy is None else
                self._read(deadline,operation=payload.get('operation')))
            mark('complete');return reply
        return self._operation(request,trace=trace)

    def exchange_built(self, payload_factory, *, trace=None, wait_other_operation=None):
        """Sample one new payload after the slot, within the caller's deadline."""
        def mark(phase):
            if trace is not None:
                trace['phase']=phase;trace[phase+'_wall_s']=time.monotonic()
        def request(deadline):
            self._remaining(deadline)
            mark('peer_check')
            self._verify_peer()
            if trace is not None:trace['peer_checked_wall_s']=time.monotonic()
            self._remaining(deadline)
            if not callable(payload_factory):
                raise ValueError('HEAD_MONITOR_CHANNEL_BUILDER_INVALID')
            try:
                mark('snapshot')
                payload = payload_factory()
            except BaseException:
                self._fail()
                raise
            self._remaining(deadline)
            mark('write')
            self._write(payload, deadline)
            mark('read')
            reply=(self._read(deadline) if self._simulation_policy is None else
                self._read(deadline,operation=payload.get('operation')))
            mark('complete');return reply
        return self._operation(request,trace=trace,wait_other_operation=wait_other_operation)
