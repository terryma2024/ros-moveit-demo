"""Explicit, authenticated Head main authority with one 50 ms exchange.

Main normal closure is distinct from the primary and CPU fault channels, whose
NativeRevocationClient keeps its separate hard 2 ms connection bound.
"""
import os
from pathlib import Path
import re
import socket
import stat
import struct
import time

from so101_demo.act.head_search_restarts import ReservationAuthority
from .controller_reservation_provision import _private_parent, _process_start_ticks


class _MainChannel:
    _connection_bound_s=.05

    def __init__(self, path, *, capability, native_owner, generation,
                 timeout_s, monotonic=time.monotonic):
        self.path=Path(path)
        self.capability=capability
        self.native_owner=dict(native_owner)
        self.generation=generation
        self.timeout=timeout_s
        self.monotonic=monotonic
        self._last_exchange=None
        if (type(generation) is not int or not 0<generation<2**64
                or type(timeout_s) not in (int,float) or timeout_s!=self._connection_bound_s
                or not callable(monotonic)
                or not isinstance(capability,bytes) or len(capability)!=32 or not any(capability)
                or set(self.native_owner)!= {'uid','pid','start_ticks'}
                or any(type(value) is not int for value in self.native_owner.values())
                or not 0<=self.native_owner['uid']<2**32
                or not 0<self.native_owner['pid']<2**31
                or not 0<self.native_owner['start_ticks']<2**64
                or len(os.fsencode(self.path))>107):
            raise ValueError('HEAD_MAIN_CONFIG_INVALID')
        self._scope=(self.capability,self.generation,dict(self.native_owner),self.path,self.timeout)

    def _verify_peer(self,connection):
        pid,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if (uid!=self.native_owner['uid'] or pid!=self.native_owner['pid']
                or _process_start_ticks(pid)!=self.native_owner['start_ticks']):
            raise PermissionError('HEAD_MAIN_NATIVE_PEER_INVALID')

    def _remaining(self, deadline):
        remaining=deadline-self.monotonic()
        if remaining<=0:raise TimeoutError('HEAD_MAIN_TIMEOUT')
        return remaining

    @property
    def exchange_trace(self):
        trace=self._last_exchange
        return None if trace is None else dict(trace,native_owner=dict(trace['native_owner']),phases=dict(trace['phases']))

    def _exchange(self, body, *, identity=False):
        if (self.capability,self.generation,self.native_owner,self.path,self.timeout)!=self._scope:
            raise PermissionError('HEAD_MAIN_SCOPE_CHANGED')
        started=self.monotonic();deadline=started+self.timeout
        trace=dict(request_wall_s=started,deadline_wall_s=deadline,
            native_owner=dict(self.native_owner),generation=self.generation,phase='path',phases={},error_type=None)
        self._last_exchange=trace
        try:
            result=self._exchange_bound(body,identity=identity,started=started,deadline=deadline,trace=trace)
            trace['phase']='complete'
            return result
        except BaseException as error:
            trace['error_type']=type(error).__name__
            raise
        finally:trace['ended_wall_s']=self.monotonic()

    def _exchange_bound(self, body, *, identity, started, deadline, trace):
        _private_parent(self.path)
        endpoint=self.path.lstat()
        if (not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid!=os.geteuid()
                or stat.S_IMODE(endpoint.st_mode)!=0o600):
            raise PermissionError('HEAD_MAIN_PATH_INVALID')
        trace['phases']['path_verified']=self.monotonic();trace['phase']='connect'
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(self._remaining(deadline))
            connection.connect(str(self.path))
            trace['phases']['connected']=self.monotonic();trace['phase']='request_peer'
            # Authenticate the connected endpoint before writing capability
            # bytes. A correct-looking reply from another process has no value.
            self._verify_peer(connection)
            trace['phases']['request_peer_verified']=self.monotonic();trace['phase']='send'
            connection.settimeout(self._remaining(deadline))
            connection.sendall(len(body).to_bytes(4,'big')+body)
            trace['phases']['sent']=self.monotonic();trace['phase']='receive'
            def read(size):
                result=bytearray()
                while len(result)<size:
                    connection.settimeout(self._remaining(deadline))
                    value=connection.recv(size-len(result))
                    if not value:raise RuntimeError('HEAD_MAIN_REPLY_INCOMPLETE')
                    result.extend(value)
                return bytes(result)
            if identity:
                size=int.from_bytes(read(4),'big')
                if not 17<=size<=145:raise RuntimeError('HEAD_MAIN_IDENTITY_INVALID')
                reply=read(size)
            else:reply=read(16)
            trace['phases']['reply_received']=self.monotonic();trace['phase']='reply_peer'
            self._verify_peer(connection)
            trace['phases']['reply_peer_verified']=self.monotonic();trace['phase']='final_deadline'
            self._remaining(deadline)
        return reply,dict(request_wall_s=started,ack_wall_s=self.monotonic(),
                          native_owner=dict(self.native_owner),generation=self.generation)



class HeadReservationAuthority(ReservationAuthority):
    def __init__(self,*,directory,capability,native_owner,generation,session_id,arm_guard,fault_callback):
        if (type(session_id) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',session_id)
                or not callable(arm_guard) or not callable(fault_callback)):
            raise ValueError('HEAD_MAIN_AUTHORITY_CONFIG_INVALID')
        self.arm_guard=arm_guard;self.fault_callback=fault_callback
        self._closed=False;self._fault_reported=False;self._fault_callback_error=None
        super().__init__(directory=directory,capabilities={'neck':capability},
            generation=generation,session_id=session_id,timeout_s=.05,transport_attempts=1,
            exchange=self._owned_exchange)
        self._channel=_MainChannel(self.directory/'neck.sock',capability=capability,
            native_owner=native_owner,generation=generation,timeout_s=.05)
        self.native_owner=dict(native_owner);self.exchange_receipts=[]
        self._session_id=session_id

    def _fault(self):
        self._registration_failed=True
        if not self._fault_reported:
            self._fault_reported=True
            try:self.fault_callback('HEAD_MAIN_AUTHORITY_FAILED')
            except Exception as error:self._fault_callback_error=type(error).__name__

    def _scope(self,role):
        if (role!='neck' or self._closed or self._registration_failed
                or self.session_id!=self._session_id or self.timeout_s!=.05
                or self.transport_attempts!=1 or self._channel.timeout!=.05
                or self.generation!=self._channel.generation
                or self.native_owner!=self._channel.native_owner):
            raise PermissionError('HEAD_MAIN_AUTHORITY_REVOKED')

    def _owned_exchange(self,role,frame,*,expect):
        self._scope(role)
        if (type(frame) is not bytes or len(frame)<8 or int.from_bytes(frame[:4],'big')!=len(frame)-4
                or expect not in ('ack','identity')):
            raise ValueError('HEAD_MAIN_FRAME_INVALID')
        reply,receipt=self._channel._exchange(frame[4:],identity=expect=='identity')
        if receipt['ack_wall_s']-receipt['request_wall_s']>.05:
            raise TimeoutError('HEAD_MAIN_CONNECTION_TIMEOUT')
        self.exchange_receipts.append(dict(receipt,operation=frame[4:8].decode('ascii'),reply_type=expect))
        return reply

    def _exchange_with_retry(self,role,frame,*,expect):
        # No frozen-frame retry, backoff, alternate endpoint or timeout refresh.
        return self._owned_exchange(role,frame,expect=expect)

    def arm(self,role):
        try:
            self._scope(role)
            if self._armed or self.arm_guard() is not True:
                raise PermissionError('HEAD_MAIN_ARM_PRECONDITION_REFUSED')
            self._scope(role)
            return super().arm(role)
        except Exception:
            self._fault();raise

    def identity(self,role):
        try:
            self._scope(role)
            if role not in self._armed:raise PermissionError('HEAD_MAIN_EXPLICIT_ARM_REQUIRED')
            identity=super().identity(role)
            if (identity['generation']!=self.generation
                    or any(type(identity[key]) is not str or not re.fullmatch(r'[\x20-\x7e]{1,64}',identity[key])
                           for key in ('incarnation','boot'))):
                raise PermissionError('HEAD_MAIN_IDENTITY_INVALID')
            return identity
        except Exception:
            self._fault();raise

    def reserve(self,role,*,goal,goal_uuid,before_reserve=None):
        try:
            self._scope(role)
            if role not in self._identities or not callable(before_reserve):
                raise PermissionError('HEAD_MAIN_INVENTORY_REQUIRED')
            return super().reserve(role,goal=goal,goal_uuid=goal_uuid,before_reserve=before_reserve)
        except Exception:
            self._fault();raise

    def close(self):
        try:
            self._scope('neck')
            if 'neck' not in self._armed:raise PermissionError('HEAD_MAIN_UNARMED_CLOSE')
            body=b'SOGR'+bytes((1,2))+self._capabilities['neck']+self.generation.to_bytes(8,'big')+bytes(16)
            response=self._owned_exchange('neck',len(body).to_bytes(4,'big')+body,expect='ack')
            if not self._ack(response,self.generation):raise PermissionError('HEAD_MAIN_CLOSE_REJECTED')
            self._closed=True;self._armed.clear()
            return dict(self.exchange_receipts[-1],ack_validated=True)
        except Exception:
            self._fault();raise
