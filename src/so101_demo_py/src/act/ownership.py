"""Attempt-scoped atomic arm/gripper ownership and a stop-confirmation barrier."""

from contextlib import contextmanager
import secrets
import threading
import time

from .contracts import finite, identifier

OWNERS=frozenset(('act','teacher','teleop','recovery'))


class Ownership:
    def __init__(self,*,monotonic=time.monotonic,lease_timeout_s=None):
        self._lock=threading.RLock();self._lease=None;self._generation=0
        self._state='IDLE';self._monotonic=monotonic;self._expires=None
        self._ttl=None if lease_timeout_s is None else finite(lease_timeout_s)
        if self._ttl is not None and self._ttl<=0:raise ValueError('LEASE_TIMEOUT_INVALID')
        self.reason=None

    def _expire(self):
        if self._expires is not None and self._monotonic()>=self._expires:
            self.revoke('LEASE_EXPIRED')

    @property
    def state(self):
        with self._lock:self._expire();return self._state

    @property
    def generation(self):
        with self._lock:return self._generation

    def acquire(self,owner,session_id,attempt_id):
        if owner not in OWNERS:raise ValueError('OWNER_INVALID')
        identity=(owner,identifier(session_id),identifier(attempt_id))
        with self._lock:
            self._expire()
            if self._state!='IDLE' or self._lease is not None:raise PermissionError('CONTROL_BUSY')
            token=secrets.token_hex(32);self._generation+=1
            self._lease=(token,)+identity;self._state='RUNNING';self.reason=None
            self._expires=None if self._ttl is None else self._monotonic()+self._ttl
            return token

    def require(self,token,owner,session_id,attempt_id):
        with self._lock:
            self._expire()
            if self._state!='RUNNING' or self._lease!=(token,owner,session_id,attempt_id):
                raise PermissionError('LEASE_INVALID')

    def renew(self,token,owner,session_id,attempt_id):
        with self._lock:
            self.require(token,owner,session_id,attempt_id)
            if self._ttl is not None:self._expires=self._monotonic()+self._ttl

    def ticket(self,token,owner,session_id,attempt_id):
        with self._lock:
            self.require(token,owner,session_id,attempt_id)
            return (self._generation,token,owner,session_id,attempt_id)

    def require_ticket(self,ticket):
        with self._lock:
            if not isinstance(ticket,tuple) or len(ticket)!=5 or ticket[0]!=self._generation:
                raise PermissionError('LEASE_GENERATION_INVALID')
            self.require(*ticket[1:])

    @contextmanager
    def authorized(self,token,owner,session_id,attempt_id):
        # The broker queues/forwards while holding this critical section. Revoke
        # cannot interleave between authorization and forwarding. A queued ticket
        # must still be checked again at actual dispatch.
        with self._lock:
            ticket=self.ticket(token,owner,session_id,attempt_id)
            yield ticket

    def revoke(self,reason):
        identifier(reason)
        with self._lock:
            self._lease=None;self._expires=None;self._generation+=1
            self._state='STOPPING';self.reason=reason

    def confirm_stopped(self,stopped):
        with self._lock:
            if stopped is not True or self._state!='STOPPING':raise PermissionError('CONTROL_NOT_STOPPED')
            self._state='IDLE'

    def release(self,token,stopped):
        with self._lock:
            self._expire()
            if self._state!='RUNNING' or self._lease is None or self._lease[0]!=token:
                raise PermissionError('LEASE_INVALID')
            if stopped is not True:raise PermissionError('CONTROL_NOT_STOPPED')
            self._lease=None;self._expires=None;self._generation+=1;self._state='IDLE'
