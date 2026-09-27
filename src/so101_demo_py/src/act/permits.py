"""Broker-local approval registry; clients cannot construct an approved permit."""

import copy
import hashlib
import json
import secrets
import threading
import time

from .contracts import fields, finite, identifier, validate_action_prefix
from .execution import prefix_sha256
from .path_proof import PathProof
from .prefix_source import PrefixSourceReceipt

PERMIT_FIELDS=frozenset(('permit_id','prefix_sha256','snapshot_sha256',
                        'valid_until_wall_s','lease_generation'))


def snapshot_sha256(snapshot):
    return hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


class PermitAuthority:
    def __init__(self,*,snapshot_port,check_port,generation_port,ttl_s,
                 monotonic=time.monotonic,proof_port=None,proof_state_port=None,
                 proof_ticket_port=None,proof_source_port=None,
                 max_observation_age_s=None,max_prefix_age_s=None):
        has_proof=proof_port is not None or proof_source_port is not None
        if (proof_port is not None and proof_source_port is not None
                or has_proof != (proof_state_port is not None)
                or has_proof != (proof_ticket_port is not None)):
            raise ValueError('PATH_PROOF_PORT_INVALID')
        self.snapshot_port,self.check_port=snapshot_port,check_port
        self.proof_port,self.proof_state_port=proof_port,proof_state_port
        self.proof_source_port=proof_source_port
        if proof_source_port is not None:
            if max_observation_age_s is None or max_prefix_age_s is None:
                raise ValueError('PATH_SOURCE_AGE_CONFIG_REQUIRED')
            self.max_observation_age_s=finite(max_observation_age_s)
            self.max_prefix_age_s=finite(max_prefix_age_s)
            if self.max_observation_age_s<=0 or self.max_prefix_age_s<=0:
                raise ValueError('PATH_SOURCE_AGE_CONFIG_INVALID')
        else:
            self.max_observation_age_s=None
            self.max_prefix_age_s=None
        self.proof_ticket_port=proof_ticket_port
        self.generation_port,self.monotonic=generation_port,monotonic
        self.ttl_s=finite(ttl_s)
        if self.ttl_s<=0:raise ValueError('PERMIT_TTL_INVALID')
        self._lock=threading.RLock();self._approved={};self._committing={};self._revision=0

    @staticmethod
    def _identity(snapshot):
        return (identifier(snapshot['session_id']),identifier(snapshot['attempt_id']),
                snapshot['reset_epoch'])

    def _proof_matches_current(self,proof,identity,generation,current=None):
        if current is None:current=self.proof_state_port()
        receipt=proof.relative_request.source_receipt
        return (proof.generation==generation
                and proof.owner_ticket==self.proof_ticket_port()
                and (receipt is None or (
                    receipt.owner_ticket==proof.owner_ticket
                    and receipt.reset_epoch==proof.reset_epoch
                    and receipt.contact_policy_fingerprint==proof.policy_fingerprint
                    and current.get('source_available') is True
                    and current.get('source_artifact_sha256')==receipt.source_artifact_sha256
                    and current.get('observation_sha256')==receipt.observation_sha256
                    and current.get('source_received_wall_s')==receipt.source_received_wall_s
                    and current.get('source_phase')==receipt.source_phase
                    and current.get('source_physics_step')==receipt.physics_step))
                and proof.reset_epoch==identity[2]
                and current['reset_epoch']==identity[2]
                and proof.matches_state(current['snapshot'])
                and proof.model_sha256==current['snapshot']['model_sha256']
                and all(getattr(proof,key)==current[key] for key in (
                    'policy_fingerprint','profile_sha256',
                    'contact_scope_sha256','checker_sha256')))

    def approve(self,prefix):
        return self._approve(prefix,source_receipt=None)

    def approve_with_source(self,prefix,receipt):
        if self.proof_source_port is None:
            raise PermissionError('PATH_SOURCE_PROOF_UNWIRED')
        return self._approve(prefix,source_receipt=receipt)

    def _approve(self,prefix,*,source_receipt):
        checked=validate_action_prefix(prefix)
        with self._lock:revision=self._revision
        generation=self.generation_port()
        snapshot=self.snapshot_port();identity=self._identity(snapshot)
        if identity[:2]!=(checked['session_id'],checked['attempt_id']):raise PermissionError('PERMIT_SCOPE_INVALID')
        # Physics and ROS waits run outside the permit registry lock. Revocation
        # is immediate and its revision fences the late check result.
        proof=None
        if source_receipt is not None:
            if (not isinstance(source_receipt,PrefixSourceReceipt)
                    or source_receipt.prefix_sha256!=prefix_sha256(checked)
                    or source_receipt.owner_ticket!=self.proof_ticket_port()
                    or source_receipt.owner_ticket[0]!=generation
                    or source_receipt.reset_epoch!=identity[2]):
                raise PermissionError('PATH_SOURCE_RECEIPT_INVALID')
            proof=self.proof_source_port(checked,snapshot,generation,
                                        source_receipt)
            if (not isinstance(proof,PathProof) or proof.status!='SAFE'
                    or proof.sample_count!=701
                    or proof.relative_request.source_receipt is not source_receipt
                    or proof.prefix_sha256!=prefix_sha256(checked)
                    or not proof.relative_request.matches_source(checked)
                    or not self._proof_matches_current(proof,identity,generation)):
                raise PermissionError('PATH_REJECTED')
            try:
                proof.relative_request.require_source_freshness(
                    now_wall_s=self.monotonic(),
                    max_observation_age_s=self.max_observation_age_s,
                    max_prefix_age_s=self.max_prefix_age_s,jitter_s=0.)
            except ValueError as error:
                raise PermissionError('PATH_SOURCE_STALE') from error
        elif self.proof_source_port is not None:
            raise PermissionError('PATH_SOURCE_RECEIPT_REQUIRED')
        elif self.proof_port is None:
            if self.check_port(checked,snapshot) is not True:
                raise PermissionError('PATH_REJECTED')
        else:
            proof=self.proof_port(checked,snapshot,generation)
            if (not isinstance(proof,PathProof) or proof.status!='SAFE'
                    or proof.sample_count!=701
                    or proof.prefix_sha256!=prefix_sha256(checked)
                    or not proof.relative_request.matches_source(checked)
                    or proof.relative_request.prefix_issued_wall_s
                       !=snapshot.get('prefix_issued_wall_s')
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
            elif proof.relative_request.source_receipt is not None:
                proof.relative_request.require_source_freshness(
                    now_wall_s=self.monotonic(),
                    max_observation_age_s=self.max_observation_age_s,
                    max_prefix_age_s=self.max_prefix_age_s,jitter_s=0.)
            current_identity=self._identity(self.snapshot_port())
            with self._lock:
                if (revision!=self._revision or self.generation_port()!=permit['lease_generation']
                        or self.monotonic()>=permit['valid_until_wall_s'] or current_identity!=identity):
                    raise ValueError('revoked/expired/reset')
                if proof is not None:
                    if len(self._committing)>=32:raise ValueError('proof queue full')
                    self._committing[id(proof)]=(proof,permit['valid_until_wall_s'],revision)
            return proof
        except (KeyError,TypeError,ValueError) as error:
            raise PermissionError('PERMIT_INVALID') from error

    def current_proof_state(self,proof):
        """Read fresh state for one consumed proof without rerunning physics."""
        try:
            if not isinstance(proof,PathProof) or self.proof_state_port is None:
                raise ValueError('proof mode')
            with self._lock:
                entry=self._committing.get(id(proof))
                if (entry is None or entry[0] is not proof
                        or entry[2]!=self._revision):
                    raise ValueError('proof closed')
                expiry=entry[1]
            if self.monotonic()>=expiry:raise ValueError('proof expired')
            generation=self.generation_port()
            identity=self._identity(self.snapshot_port())
            if identity!=(proof.owner_ticket[3],proof.owner_ticket[4],
                         proof.reset_epoch):
                raise ValueError('scope')
            current=copy.deepcopy(self.proof_state_port())
            if not self._proof_matches_current(proof,identity,generation,current):
                raise ValueError('state')
            current_identity=self._identity(self.snapshot_port())
            with self._lock:
                if (self._committing.get(id(proof)) is not entry
                        or entry[2]!=self._revision
                        or self.generation_port()!=generation
                        or self.monotonic()>=expiry
                        or current_identity!=identity):
                    raise ValueError('changed during readback')
            return current
        except (KeyError,TypeError,ValueError) as error:
            raise PermissionError('PATH_PROOF_CURRENT_INVALID') from error

    def close_proof(self,proof):
        with self._lock:
            entry=self._committing.get(id(proof))
            if entry is not None and entry[0] is proof:
                self._committing.pop(id(proof))

    def revoke(self,reason):
        identifier(reason)
        with self._lock:
            self._revision+=1;self._approved.clear();self._committing.clear()
