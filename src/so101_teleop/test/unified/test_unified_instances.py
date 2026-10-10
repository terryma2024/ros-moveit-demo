"""Contract tests for server-verified document instances and lease binding fences."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    Domain,
    LeaseIdentity,
    MutationError,
    OperationSpec,
    RequestAuthority,
)
from so101_teleop.unified.instances import InstanceRegistry, LeaseBindingCoordinator
from so101_teleop.unified.intent_store import IntentStore

ORIGIN = "http://127.0.0.1:8000"


def registry_for(store: IntentStore, *, epoch: str = "e1") -> InstanceRegistry:
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    return InstanceRegistry(arbiter, service_epoch=epoch, origin=ORIGIN, clock_ns=lambda: 1)


def test_copied_lease_cannot_control_and_renewal_does_not_change_execution(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    arb = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    r = InstanceRegistry(arb, service_epoch="e1", origin="http://127.0.0.1:8000", clock_ns=lambda: 1)
    one, two = r.register(Domain.TELEOP), r.register(Domain.TELEOP)
    a = r.connect(one.instance_id, one.proof, origin="http://127.0.0.1:8000")
    b = r.connect(two.instance_id, two.proof, origin="http://127.0.0.1:8000")
    lease = LeaseIdentity("l1", "s1", 1, 100)
    owner = r.claim(a, lease)
    with pytest.raises(MutationError, match="CONTROLLER_ALREADY_BOUND"):
        r.claim(b, lease)
    copied = RequestAuthority(Domain.TELEOP, two.instance_id, two.proof, b.revision, owner.execution_generation)
    with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_MISMATCH"):
        r.authorize(copied, lease)
    renewed = LeaseIdentity("l1", "s1", 2, 120)
    r.authorize(owner, renewed)
    assert r.execution_generation(Domain.TELEOP) == owner.execution_generation
    moved = r.handoff(owner, b, renewed)
    assert moved.execution_generation == owner.execution_generation + 1
    with pytest.raises(MutationError):
        r.authorize(owner, lease)
    store.close()


def test_instances_are_registered_per_domain_and_proofs_never_persist(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    r = registry_for(store)
    proof = r.register(Domain.TELEOP)
    assert len(proof.proof) >= 32
    assert proof.domain is Domain.TELEOP
    raw = (store.root / "intents.sqlite3").read_bytes()
    assert proof.proof.encode() not in raw, "instance proof must never be written to disk"
    store.close()


def test_new_service_epoch_rejects_previous_proofs(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    first = registry_for(store, epoch="e1")
    proof = first.register(Domain.TELEOP)
    first.connect(proof.instance_id, proof.proof, origin=ORIGIN)
    second = registry_for(store, epoch="e2")
    with pytest.raises(MutationError, match="UNKNOWN_INSTANCE"):
        second.connect(proof.instance_id, proof.proof, origin=ORIGIN)
    store.close()


def test_cross_domain_proof_swap_and_wrong_origin_are_refused(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    r = registry_for(store)
    teleop, validation = r.register(Domain.TELEOP), r.register(Domain.VALIDATION)
    with pytest.raises(MutationError, match="ORIGIN_REJECTED"):
        r.connect(teleop.instance_id, teleop.proof, origin="http://evil.example")
    with pytest.raises(MutationError, match="INSTANCE_PROOF_MISMATCH"):
        r.connect(teleop.instance_id, validation.proof, origin=ORIGIN)
    binding = r.connect(teleop.instance_id, teleop.proof, origin=ORIGIN)
    swapped = RequestAuthority(
        Domain.VALIDATION, teleop.instance_id, teleop.proof, binding.revision, 1
    )
    r.connect(validation.instance_id, validation.proof, origin=ORIGIN)
    with pytest.raises(MutationError, match="INSTANCE_DOMAIN_MISMATCH"):
        r.authorize(swapped, LeaseIdentity("l1", "s1", 1, 100))
    store.close()


def test_claim_requires_a_live_channel(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    r = registry_for(store)
    proof = r.register(Domain.TELEOP)
    binding = r.connect(proof.instance_id, proof.proof, origin=ORIGIN)
    r.disconnect(binding)
    with pytest.raises(MutationError, match="CHANNEL_NOT_LIVE"):
        r.claim(binding, LeaseIdentity("l1", "s1", 1, 100))
    store.close()


def test_reconnect_bumps_revision_and_rejects_late_requests(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    r = registry_for(store)
    proof = r.register(Domain.TELEOP)
    first = r.connect(proof.instance_id, proof.proof, origin=ORIGIN)
    lease = LeaseIdentity("l1", "s1", 1, 1000)
    owner = r.claim(first, lease)
    second = r.connect(proof.instance_id, proof.proof, origin=ORIGIN)
    assert second.revision == first.revision + 1
    with pytest.raises(MutationError, match="CHANNEL_REVISION_STALE"):
        r.authorize(owner, lease)
    r.disconnect(first)
    assert r.require_bound(r.claim(second, lease)) == owner.execution_generation
    store.close()


def test_handoff_requires_an_idle_service_and_succeeds_only_once(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    r = registry_for(store)
    one, two = r.register(Domain.TELEOP), r.register(Domain.TELEOP)
    a = r.connect(one.instance_id, one.proof, origin=ORIGIN)
    b = r.connect(two.instance_id, two.proof, origin=ORIGIN)
    lease = LeaseIdentity("l1", "s1", 1, 1000)
    owner = r.claim(a, lease)
    parent = r.arbiter.begin(OperationSpec("arm-1", Domain.TELEOP, "execute", {}, "R1", 1, 1000))
    with pytest.raises(MutationError, match="HANDOFF_BLOCKED"):
        r.handoff(owner, b, lease)
    token = r.arbiter.prepare_child(parent.operation_id, "arm")
    from so101_teleop.unified.contracts import ActionKey, ActionTerminal, DispatchAck, OwnerKey

    key = ActionKey(parent.operation_id, "arm", "g1", OwnerKey(1, 1, 1, "a", "e"), "R1", 1)
    r.arbiter.record_ack(token, DispatchAck(key, True))
    r.arbiter.record_terminal(ActionTerminal(key, True, True, True))
    r.arbiter.settle(parent.operation_id, cleanup_confirmed=True)
    moved = r.handoff(owner, b, lease)
    assert moved.instance_id == two.instance_id
    with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_MISMATCH"):
        r.handoff(owner, b, lease)
    store.close()


def test_abandoned_controller_requires_proof_of_no_owner(tmp_path):
    store = IntentStore.open(tmp_path / "state")
    r = registry_for(store)
    proof = r.register(Domain.TELEOP)
    binding = r.connect(proof.instance_id, proof.proof, origin=ORIGIN)
    lease = LeaseIdentity("l1", "s1", 1, 1000)
    r.claim(binding, lease)
    r.disconnect(binding)
    with pytest.raises(MutationError, match="ABANDONED_OWNER_NOT_PROVEN"):
        r.abandon_controller(Domain.TELEOP, no_unconverged_owner=False)
    other = r.register(Domain.TELEOP)
    other_binding = r.connect(other.instance_id, other.proof, origin=ORIGIN)
    with pytest.raises(MutationError, match="CONTROLLER_ALREADY_BOUND"):
        r.claim(other_binding, lease)
    r.abandon_controller(Domain.TELEOP, no_unconverged_owner=True)
    rebound = r.claim(other_binding, lease)
    assert rebound.instance_id == other.instance_id
    store.close()


class SqliteLeasePort:
    """Test-owned domain lease authority with its own independent SQLite transaction."""

    def __init__(self, path: Path, *, hang: bool = False) -> None:
        self.path = path
        self.hang = hang
        self.calls: list[tuple[str, dict]] = []
        self.release_gate = asyncio.Event() if hang else None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.execute("CREATE TABLE IF NOT EXISTS leases (lease_id TEXT PRIMARY KEY, generation INTEGER)")
        return connection

    async def acquire(self, body: dict) -> LeaseIdentity:
        self.calls.append(("acquire", body))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT OR REPLACE INTO leases VALUES (?, ?)", ("l1", 1))
            connection.execute("COMMIT")
        finally:
            connection.close()
        return LeaseIdentity("l1", "s1", 1, 10_000)

    async def renew(self, lease: LeaseIdentity, body: dict) -> LeaseIdentity:
        self.calls.append(("renew", body))
        if self.release_gate is not None:
            await self.release_gate.wait()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE leases SET generation = ? WHERE lease_id = ?", (lease.lease_generation + 1, lease.lease_id))
            connection.execute("COMMIT")
        finally:
            connection.close()
        return LeaseIdentity(lease.lease_id, lease.service_session_id, lease.lease_generation + 1, lease.expires_monotonic_ns + 10_000)

    async def release(self, lease: LeaseIdentity, body: dict) -> None:
        self.calls.append(("release", body))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM leases WHERE lease_id = ?", (lease.lease_id,))
            connection.execute("COMMIT")
        finally:
            connection.close()


def coordinator_for(store: IntentStore, port: SqliteLeasePort, *, epoch: str = "e1"):
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    registry = InstanceRegistry(arbiter, service_epoch=epoch, origin=ORIGIN, clock_ns=lambda: 1)
    return registry, LeaseBindingCoordinator(store, registry, port)


def test_coordinator_acquire_binds_controller_and_clears_the_fence(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        port = SqliteLeasePort(tmp_path / "domain-leases.sqlite3")
        registry, coordinator = coordinator_for(store, port)
        proof = registry.register(Domain.TELEOP)
        binding = registry.connect(proof.instance_id, proof.proof, origin=ORIGIN)
        authority = await coordinator.acquire(binding, {"command": "acquire"})
        assert authority.instance_id == proof.instance_id
        assert registry.require_bound(authority) == authority.execution_generation
        assert store.open_lease_fences() == ()
        store.close()

    asyncio.run(run())


def test_coordinator_failure_after_domain_commit_leaves_no_executable_binding(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        port = SqliteLeasePort(tmp_path / "domain-leases.sqlite3")
        registry, coordinator = coordinator_for(store, port)
        proof = registry.register(Domain.TELEOP)
        binding = registry.connect(proof.instance_id, proof.proof, origin=ORIGIN)

        def refuse(*_args, **_kwargs):
            raise MutationError("CONTROLLER_ALREADY_BOUND: injected binding failure")

        registry.claim_locked = refuse  # type: ignore[assignment]
        with pytest.raises(MutationError, match="CONTROLLER_ALREADY_BOUND"):
            await coordinator.acquire(binding, {"command": "acquire"})
        assert [name for name, _ in port.calls] == ["acquire"], "the domain lease really committed"
        assert store.open_lease_fences(), "a failed binding must leave a durable fence"
        with pytest.raises(MutationError, match="BLOCKED"):
            registry.arbiter.begin(OperationSpec("arm-1", Domain.TELEOP, "execute", {}, "R1", 1, 1000))
        store.close()
        reopened = IntentStore.open(tmp_path / "state")
        assert reopened.global_state()[0] != "IDLE"
        assert reopened.open_lease_fences()
        reopened.close()

    asyncio.run(run())


def test_guard_parent_waits_for_renew_fence_without_changing_execution(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        port = SqliteLeasePort(tmp_path / "domain-leases.sqlite3", hang=True)
        registry, coordinator = coordinator_for(store, port)
        proof = registry.register(Domain.TELEOP)
        binding = registry.connect(proof.instance_id, proof.proof, origin=ORIGIN)
        authority = await coordinator.acquire(binding, {"command": "acquire"})
        parent = registry.arbiter.begin(
            OperationSpec("all-1", Domain.TELEOP, "execute_all", {}, "R1", 1, 10**18)
        )
        renewing = asyncio.create_task(coordinator.renew(authority, {"command": "renew"}))
        await asyncio.sleep(0)
        guard = asyncio.create_task(coordinator.guard_parent(parent, authority))
        await asyncio.sleep(0.05)
        assert not guard.done(), "child dispatch must wait for the renew fence"
        port.release_gate.set()
        await renewing
        await asyncio.wait_for(guard, 1)
        assert registry.execution_generation(Domain.TELEOP) == authority.execution_generation
        assert registry.require_bound(authority) == authority.execution_generation
        store.close()

    asyncio.run(run())


def test_guard_parent_times_out_at_the_parent_deadline_and_blocks(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        port = SqliteLeasePort(tmp_path / "domain-leases.sqlite3", hang=True)
        registry, coordinator = coordinator_for(store, port)
        proof = registry.register(Domain.TELEOP)
        binding = registry.connect(proof.instance_id, proof.proof, origin=ORIGIN)
        authority = await coordinator.acquire(binding, {"command": "acquire"})
        parent = registry.arbiter.begin(
            OperationSpec("all-2", Domain.TELEOP, "execute_all", {}, "R1", 1, 1)
        )
        renewing = asyncio.create_task(coordinator.renew(authority, {"command": "renew"}))
        await asyncio.sleep(0)
        with pytest.raises(MutationError, match="RENEW_FENCE_TIMEOUT"):
            await coordinator.guard_parent(parent, authority)
        assert not registry.arbiter.is_idle()
        port.release_gate.set()
        with pytest.raises(MutationError):
            await renewing
        store.close()

    asyncio.run(run())
