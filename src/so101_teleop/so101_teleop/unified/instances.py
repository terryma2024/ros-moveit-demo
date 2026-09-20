"""Server-verified document instances and lease binding.

An instance is a browser document that proved possession of a server-generated proof on a
live channel. Control is a second, separate step: the domain lease endpoint binds exactly
one instance per domain inside one server transaction, so two documents that copy the same
valid lease cannot both control. The plaintext proof lives in server memory only and is
never persisted, logged, or written into a URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from dataclasses import dataclass, replace
from typing import Awaitable, Protocol

from .arbiter import GlobalMutationArbiter
from .contracts import (
    ChannelBinding,
    Domain,
    InstanceProof,
    LeaseIdentity,
    MutationError,
    RequestAuthority,
)
from .intent_store import (
    LEASE_BOUND,
    LEASE_CLAIMING,
    LEASE_RENEWING,
    IntentStore,
)

PROOF_BYTES = 32


def _digest(proof: str) -> str:
    return hashlib.sha256(proof.encode()).hexdigest()


@dataclass
class _InstanceRecord:
    instance_id: str
    domain: Domain
    proof_hash: str
    #: Kept in memory only so this service can hand the owning document back its own
    #: authority; never persisted, never logged.
    proof: str
    revision: int = 0
    connected: bool = False


@dataclass
class _ControllerBinding:
    instance_id: str
    domain: Domain
    channel_revision: int
    execution_generation: int
    lease: LeaseIdentity


class DomainLeasePort(Protocol):
    """The existing per-domain lease authority, adapted to a typed port."""

    def acquire(self, body: dict) -> Awaitable[LeaseIdentity]: ...

    def renew(self, lease: LeaseIdentity, body: dict) -> Awaitable[LeaseIdentity]: ...

    def release(self, lease: LeaseIdentity, body: dict) -> Awaitable[None]: ...


class InstanceRegistry:
    def __init__(
        self,
        arbiter: GlobalMutationArbiter,
        *,
        service_epoch: str,
        origin: str,
        clock_ns,
    ) -> None:
        self.arbiter = arbiter
        self.store: IntentStore = arbiter.store
        self.service_epoch = service_epoch
        self.origin = origin
        self.clock_ns = clock_ns
        self._instances: dict[str, _InstanceRecord] = {}
        self._controllers: dict[str, _ControllerBinding] = {}

    # -- registration and channels ----------------------------------------------

    def register(self, domain: Domain) -> InstanceProof:
        instance_id = uuid.uuid4().hex
        proof = secrets.token_urlsafe(PROOF_BYTES)
        self._instances[instance_id] = _InstanceRecord(
            instance_id=instance_id, domain=domain, proof_hash=_digest(proof), proof=proof
        )
        return InstanceProof(instance_id=instance_id, proof=proof, domain=domain)

    def connect(self, instance_id: str, proof: str, *, origin: str) -> ChannelBinding:
        if origin != self.origin:
            raise MutationError(f"ORIGIN_REJECTED: {origin} is not this service origin")
        record = self._require_instance(instance_id)
        if not secrets.compare_digest(_digest(proof), record.proof_hash):
            raise MutationError(f"INSTANCE_PROOF_MISMATCH: {instance_id}")
        record.revision += 1
        record.connected = True
        return ChannelBinding(instance_id=instance_id, revision=record.revision, domain=record.domain)

    def acquire_binding(self, instance_id: str, proof: str, *, channel_revision: int) -> ChannelBinding:
        """Resolve the live channel of an instance that is asking to become the controller.

        Design section 5.1: registration grants no control, and the acquire path validates the
        instance's live channel before the domain controller is bound to it. Nothing here claims
        the controller; the caller does that once the domain lease exists.
        """

        record = self._require_instance(instance_id)
        if not secrets.compare_digest(_digest(proof), record.proof_hash):
            raise MutationError(f"INSTANCE_PROOF_MISMATCH: {instance_id}")
        binding = ChannelBinding(
            instance_id=instance_id, revision=channel_revision, domain=record.domain
        )
        self._require_live(binding)
        return binding

    def disconnect(self, binding: ChannelBinding) -> None:
        record = self._instances.get(binding.instance_id)
        if record is None or record.revision != binding.revision:
            return
        record.connected = False

    def _require_instance(self, instance_id: str) -> _InstanceRecord:
        record = self._instances.get(instance_id)
        if record is None:
            raise MutationError(f"UNKNOWN_INSTANCE: {instance_id}")
        return record

    def _require_live(self, binding: ChannelBinding) -> _InstanceRecord:
        record = self._require_instance(binding.instance_id)
        if record.domain is not binding.domain:
            raise MutationError(f"INSTANCE_DOMAIN_MISMATCH: {binding.instance_id}")
        if not record.connected or record.revision != binding.revision:
            raise MutationError(f"CHANNEL_NOT_LIVE: {binding.instance_id}@{binding.revision}")
        return record

    def _require_lease_fresh(self, lease: LeaseIdentity) -> None:
        if lease.expires_monotonic_ns <= self.clock_ns():
            raise MutationError(f"LEASE_EXPIRED: {lease.lease_id}")

    # -- controller binding ------------------------------------------------------

    def claim(self, binding: ChannelBinding, lease: LeaseIdentity) -> RequestAuthority:
        with self.store.immediate_transaction():
            return self.claim_locked(binding, lease)

    def claim_locked(self, binding: ChannelBinding, lease: LeaseIdentity) -> RequestAuthority:
        """Bind the domain controller inside the caller's transaction."""
        record = self._require_live(binding)
        self._require_lease_fresh(lease)
        existing = self._controllers.get(str(binding.domain))
        if existing is not None and existing.instance_id != binding.instance_id:
            raise MutationError(
                f"CONTROLLER_ALREADY_BOUND: {binding.domain} is controlled by {existing.instance_id}"
            )
        generation = self.store.execution_generation(binding.domain)
        if existing is None:
            generation = self.store.bump_execution_generation_locked(binding.domain)
        self._controllers[str(binding.domain)] = _ControllerBinding(
            instance_id=binding.instance_id,
            domain=binding.domain,
            channel_revision=binding.revision,
            execution_generation=generation,
            lease=lease,
        )
        return RequestAuthority(
            domain=binding.domain,
            instance_id=binding.instance_id,
            proof=record.proof,
            channel_revision=binding.revision,
            execution_generation=generation,
        )

    def require_bound(self, authority: RequestAuthority) -> int:
        """Prove the request really carries this domain's live controller authority."""
        record = self._require_instance(authority.instance_id)
        if record.domain is not authority.domain:
            raise MutationError(f"INSTANCE_DOMAIN_MISMATCH: {authority.instance_id}")
        bound = self._controllers.get(str(authority.domain))
        if bound is None:
            raise MutationError(f"CONTROLLER_NOT_BOUND: {authority.domain}")
        if bound.instance_id != authority.instance_id:
            raise MutationError(
                f"CONTROLLER_INSTANCE_MISMATCH: {authority.domain} is controlled by {bound.instance_id}"
            )
        if not secrets.compare_digest(_digest(authority.proof), record.proof_hash):
            raise MutationError(f"INSTANCE_PROOF_MISMATCH: {authority.instance_id}")
        if not record.connected or record.revision != authority.channel_revision:
            raise MutationError(
                f"CHANNEL_REVISION_STALE: {authority.instance_id}@{authority.channel_revision}"
            )
        if authority.execution_generation != bound.execution_generation:
            raise MutationError(
                f"STALE_EXECUTION_GENERATION: {authority.execution_generation} "
                f"!= {bound.execution_generation}"
            )
        self._require_lease_fresh(bound.lease)
        return bound.execution_generation

    def authorize(self, authority: RequestAuthority, lease: LeaseIdentity) -> None:
        """Verify authority and accept a newer lease generation without rebinding."""
        with self.store.immediate_transaction():
            self._authorize_locked(authority, lease)

    def _authorize_locked(self, authority: RequestAuthority, lease: LeaseIdentity) -> None:
        self.require_bound(authority)
        bound = self._controllers[str(authority.domain)]
        if (
            lease.lease_id != bound.lease.lease_id
            or lease.service_session_id != bound.lease.service_session_id
        ):
            raise MutationError(
                f"LEASE_IDENTITY_MISMATCH: {lease.lease_id}/{lease.service_session_id}"
            )
        if lease.lease_generation < bound.lease.lease_generation:
            raise MutationError(
                f"STALE_LEASE_GENERATION: {lease.lease_generation} < {bound.lease.lease_generation}"
            )
        self._require_lease_fresh(lease)
        if lease.lease_generation > bound.lease.lease_generation:
            bound.lease = lease

    def renew_locked(self, authority: RequestAuthority, lease: LeaseIdentity) -> None:
        """Record a renewed lease projection; the execution generation never moves."""
        self.require_bound(authority)
        bound = self._controllers[str(authority.domain)]
        if lease.lease_id != bound.lease.lease_id:
            raise MutationError(f"LEASE_IDENTITY_MISMATCH: {lease.lease_id}")
        bound.lease = replace(lease, expires_monotonic_ns=max(lease.expires_monotonic_ns, bound.lease.expires_monotonic_ns))

    def execution_generation(self, domain: Domain) -> int:
        return self.store.execution_generation(domain)

    def current_lease(self, domain: Domain) -> LeaseIdentity:
        bound = self._controllers.get(str(domain))
        if bound is None:
            raise MutationError(f"CONTROLLER_NOT_BOUND: {domain}")
        return bound.lease

    def controller_instance(self, domain: Domain) -> str | None:
        bound = self._controllers.get(str(domain))
        return bound.instance_id if bound is not None else None

    # -- explicit handoff and abandoned-controller recovery ----------------------

    def handoff(
        self, current: RequestAuthority, target: ChannelBinding, lease: LeaseIdentity
    ) -> RequestAuthority:
        with self.store.immediate_transaction():
            self._authorize_locked(current, lease)
            record = self._require_live(target)
            if record.domain is not current.domain:
                raise MutationError(f"INSTANCE_DOMAIN_MISMATCH: {target.instance_id}")
            if not self.arbiter.is_idle():
                raise MutationError(
                    f"HANDOFF_BLOCKED: {current.domain} still owns {self.arbiter.state()}"
                )
            if self.store.open_lease_fences():
                raise MutationError("HANDOFF_BLOCKED: an unresolved lease fence is open")
            generation = self.store.bump_execution_generation_locked(current.domain)
            self._controllers[str(current.domain)] = _ControllerBinding(
                instance_id=target.instance_id,
                domain=current.domain,
                channel_revision=target.revision,
                execution_generation=generation,
                lease=lease,
            )
            return RequestAuthority(
                domain=current.domain,
                instance_id=target.instance_id,
                proof=record.proof,
                channel_revision=target.revision,
                execution_generation=generation,
            )

    def abandon_controller(self, domain: Domain, *, no_unconverged_owner: bool) -> None:
        """Operator-only recovery: requires proof that nothing is still owned."""
        with self.store.immediate_transaction():
            if not no_unconverged_owner:
                raise MutationError(
                    f"ABANDONED_OWNER_NOT_PROVEN: {domain} still has an unconverged owner"
                )
            if not self.arbiter.is_idle():
                raise MutationError(f"HANDOFF_BLOCKED: {domain} still owns {self.arbiter.state()}")
            bound = self._controllers.get(str(domain))
            if bound is None:
                return
            record = self._instances.get(bound.instance_id)
            if record is not None and record.connected:
                raise MutationError(
                    f"CONTROLLER_CHANNEL_STILL_LIVE: {bound.instance_id}"
                )
            del self._controllers[str(domain)]


class LeaseBindingCoordinator:
    """Persist a fence, then let the real domain lease and the binding meet once."""

    def __init__(self, store: IntentStore, registry: InstanceRegistry, lease_port: DomainLeasePort) -> None:
        self.store = store
        self.registry = registry
        self.lease_port = lease_port
        self._renew_events: dict[str, asyncio.Event] = {}

    async def acquire(self, binding: ChannelBinding, body: dict) -> RequestAuthority:
        claim_id = self.store.open_lease_fence(binding.domain, LEASE_CLAIMING)
        try:
            lease = await self.lease_port.acquire(body)
            with self.store.immediate_transaction():
                self.store.record_lease_identity(claim_id, lease)
                authority = self.registry.claim_locked(binding, lease)
                self.store.finish_lease_fence_locked(claim_id, LEASE_BOUND, expect=LEASE_CLAIMING)
        except BaseException as error:
            self.store.fail_lease_fence(claim_id, f"{type(error).__name__}: {error}")
            raise
        return authority

    async def renew(self, authority: RequestAuthority, body: dict) -> LeaseIdentity:
        self.registry.require_bound(authority)
        claim_id = self.store.open_lease_fence(authority.domain, LEASE_RENEWING)
        event = asyncio.Event()
        self._renew_events[claim_id] = event
        try:
            lease = await self.lease_port.renew(self.registry.current_lease(authority.domain), body)
            with self.store.immediate_transaction():
                self.registry.renew_locked(authority, lease)
                self.store.record_lease_identity(claim_id, lease)
                self.store.finish_lease_fence_locked(claim_id, LEASE_BOUND, expect=LEASE_RENEWING)
        except BaseException as error:
            self.store.fail_lease_fence(claim_id, f"{type(error).__name__}: {error}")
            raise
        finally:
            event.set()
            self._renew_events.pop(claim_id, None)
        return lease

    async def release(self, authority: RequestAuthority, body: dict) -> None:
        self.registry.require_bound(authority)
        lease = self.registry.current_lease(authority.domain)
        await self.lease_port.release(lease, body)

    async def guard_parent(self, parent, authority: RequestAuthority) -> None:
        """Wait out a domain renew fence up to the parent's own deadline, then re-prove."""
        domain = authority.domain
        while True:
            claim_id = self.store.open_renew_fence(domain)
            if claim_id is None:
                break
            remaining_ns = parent.spec.deadline_ns - self.registry.clock_ns()
            if remaining_ns <= 0:
                self.store.fail_lease_fence(claim_id, "RENEW_FENCE_TIMEOUT")
                self.registry.arbiter.block("RENEW_FENCE_TIMEOUT")
                raise MutationError(
                    f"RENEW_FENCE_TIMEOUT: {domain} renew did not finish before the parent deadline"
                )
            event = self._renew_events.get(claim_id)
            if event is None:
                self.store.fail_lease_fence(claim_id, "RENEW_FENCE_UNKNOWN")
                self.registry.arbiter.block("RENEW_FENCE_UNKNOWN")
                raise MutationError(
                    f"RENEW_FENCE_UNKNOWN: {domain} has a renew fence this instance cannot complete"
                )
            try:
                await asyncio.wait_for(asyncio.shield(event.wait()), min(remaining_ns / 1e9, 0.05))
            except (asyncio.TimeoutError, TimeoutError):
                continue
        self.registry.require_bound(authority)
