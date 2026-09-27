"""Broker-local approval registry; clients cannot construct an approved permit."""

import hashlib
import json
import secrets
import threading
import time

from .contracts import fields, finite, identifier, validate_action_prefix
from .execution import prefix_sha256
from .path_proof import PathProof

PERMIT_FIELDS=frozenset(('permit_id','prefix_sha256','snapshot_sha256',
                        'valid_until_wall_s','lease_generation'))


def snapshot_sha256(snapshot):
    return hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


class PermitAuthority:
    def __init__(self,*,snapshot_port,check_port,generation_port,ttl_s,
                 monotonic=time.monotonic,proof_port=None,proof_state_port=None,
                 proof_ticket_port=None):
        if len([port for port in (proof_port,proof_state_port,proof_ticket_port)
                if port is not None]) not in (0,3):
            raise ValueError('PATH_PROOF_PORT_INVALID')
        self.snapshot_port,self.check_port=snapshot_port,check_port
        self.proof_port,self.proof_state_port=proof_port,proof_state_port
        self.proof_ticket_port=proof_ticket_port
        self.generation_port,self.monotonic=generation_port,monotonic
        self.ttl_s=finite(ttl_s)
        if self.ttl_s<=0:raise ValueError('PERMIT_TTL_INVALID')
        self._lock=threading.RLock();self._approved={};self._revision=0

    @staticmethod
    def _identity(snapshot):
        return (identifier(snapshot['session_id']),identifier(snapshot['attempt_id']),
                snapshot['reset_epoch'])

    def _proof_matches_current(self,proof,identity,generation):
        current=self.proof_state_port()
        return (proof.generation==generation
                and proof.owner_ticket==self.proof_ticket_port()
                and proof.reset_epoch==identity[2]
                and current['reset_epoch']==identity[2]
                and proof.matches_state(current['snapshot'])
                and proof.model_sha256==current['snapshot']['model_sha256']
                and all(getattr(proof,key)==current[key] for key in (
                    'policy_fingerprint','profile_sha256',
                    'contact_scope_sha256','checker_sha256')))

    def approve(self,prefix):
        checked=validate_action_prefix(prefix)
        with self._lock:revision=self._revision
        generation=self.generation_port()
        snapshot=self.snapshot_port();identity=self._identity(snapshot)
        if identity[:2]!=(checked['session_id'],checked['attempt_id']):raise PermissionError('PERMIT_SCOPE_INVALID')
        # Physics and ROS waits run outside the permit registry lock. Revocation
        # is immediate and its revision fences the late check result.
        proof=None
        if self.proof_port is None:
            if self.check_port(checked,snapshot) is not True:
                raise PermissionError('PATH_REJECTED')
        else:
            proof=self.proof_port(checked,snapshot,generation)
            if (not isinstance(proof,PathProof) or proof.status!='SAFE'
                    or proof.sample_count!=701
                    or proof.prefix_sha256!=prefix_sha256(checked)
                    or not self._proof_matches_current(proof,identity,generation)):
                raise PermissionError('PATH_REJECTED')
        current_identity=self._identity(self.snapshot_port())
        with self._lock:
            if (generation!=self.generation_port() or revision!=self._revision or identity!=current_identity):
                raise PermissionError('PERMIT_GENERATION_INVALID')
            now=finite(self.monotonic(),nonnegative=True)
            self._approved={key:value for key,value in self._approved.items()
                            if value[0]['valid_until_wall_s']>now}
            if len(self._approved)>=32:raise PermissionError('PERMIT_QUEUE_FULL')
            permit=dict(permit_id=secrets.token_hex(32),prefix_sha256=prefix_sha256(checked),
                        snapshot_sha256=snapshot_sha256(snapshot),
                        valid_until_wall_s=now+self.ttl_s,lease_generation=generation)
            self._approved[permit['permit_id']]=(dict(permit),identity,revision,proof)
            return permit

    def require(self,permit,prefix):
        try:
            fields(permit,PERMIT_FIELDS)
            with self._lock:approved=self._approved.pop(permit['permit_id'],None)
            if approved is None:raise ValueError('unknown/consumed')
            original,identity,revision,proof=approved
            if original!=permit or permit['prefix_sha256']!=prefix_sha256(prefix):raise ValueError('content')
            if self.monotonic()>=permit['valid_until_wall_s']:raise ValueError('expired')
            if self.generation_port()!=permit['lease_generation']:raise ValueError('generation')
            snapshot=self.snapshot_port()
            if self._identity(snapshot)!=identity:raise ValueError('reset/scope')
            if proof is None:
                if self.check_port(validate_action_prefix(prefix),snapshot) is not True:
                    raise ValueError('current path')
            elif not self._proof_matches_current(proof,identity,permit['lease_generation']):
                raise ValueError('current proof state')
            current_identity=self._identity(self.snapshot_port())
            with self._lock:
                if (revision!=self._revision or self.generation_port()!=permit['lease_generation']
                        or self.monotonic()>=permit['valid_until_wall_s'] or current_identity!=identity):
                    raise ValueError('revoked/expired/reset')
            return proof
        except (KeyError,TypeError,ValueError) as error:
            raise PermissionError('PERMIT_INVALID') from error

    def revoke(self,reason):
        identifier(reason)
        with self._lock:
            self._revision+=1;self._approved.clear()
