"""Explicit, authenticated Head main authority with one 50 ms exchange.

Main normal closure is distinct from the primary and CPU fault channels, whose
NativeRevocationClient keeps its separate hard 2 ms connection bound.
"""
import re

from so101_demo.act.head_search_restarts import ReservationAuthority
from .head_revocation import NativeRevocationClient


class _MainChannel(NativeRevocationClient):
    _connection_bound_s=.05


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
