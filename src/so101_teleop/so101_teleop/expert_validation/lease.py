"""Durable renewable operator lease independent from browser connections."""

from __future__ import annotations

from dataclasses import dataclass
import time
import uuid

from .store import StoreConflict


class LeaseConflict(RuntimeError):
    """A stale or unsafe lease operation was requested."""


@dataclass(frozen=True, slots=True)
class Lease:
    lease_id: str
    service_session_id: str
    generation: int
    expires_monotonic_ns: int


@dataclass(frozen=True, slots=True)
class LeaseCapabilities:
    duration_s: float
    renewal_margin_s: float


class ValidationLeaseService:
    def __init__(
        self,
        store,
        supervisor,
        *,
        clock_ns=time.monotonic_ns,
        duration_ns: int = 30_000_000_000,
        renewal_margin_ns: int = 10_000_000_000,
    ) -> None:
        self.store = store
        self.supervisor = supervisor
        self._clock_ns = clock_ns
        self._duration_ns = duration_ns
        self._renewal_margin_ns = renewal_margin_ns
        invalidated = self.store.invalidate_active_leases()
        self._unresolved = bool(invalidated) or bool(
            getattr(supervisor, "has_unresolved_campaign", lambda: False)()
        )

    @property
    def capabilities(self) -> LeaseCapabilities:
        return LeaseCapabilities(
            self._duration_ns / 1_000_000_000,
            self._renewal_margin_ns / 1_000_000_000,
        )

    def acquire(self, service_session_id: str) -> Lease:
        if not isinstance(service_session_id, str) or not service_session_id:
            raise LeaseConflict("SERVICE_SESSION_ID")
        generation = self.store.next_lease_generation()
        lease = Lease(
            lease_id="lease-" + uuid.uuid4().hex,
            service_session_id=service_session_id,
            generation=generation,
            expires_monotonic_ns=self._clock_ns() + self._duration_ns,
        )
        try:
            self.store.insert_lease(
                lease.lease_id,
                lease.service_session_id,
                lease.generation,
                lease.expires_monotonic_ns,
            )
        except StoreConflict as error:
            raise LeaseConflict(str(error)) from error
        return lease

    def current(self) -> Lease | None:
        row = self.store.current_lease()
        if row is None:
            return None
        return Lease(
            row["lease_id"],
            row["service_session_id"],
            row["generation"],
            row["expires_monotonic_ns"],
        )

    def renew(
        self, service_session_id: str, lease_id: str, generation: int
    ) -> Lease:
        current = self.current()
        if current is None:
            raise LeaseConflict("LEASE_NOT_ACTIVE")
        if current.lease_id != lease_id or current.service_session_id != service_session_id:
            raise LeaseConflict("LEASE_IDENTITY_MISMATCH")
        if current.generation != generation:
            raise LeaseConflict("STALE_LEASE_GENERATION")
        new_generation = self.store.next_lease_generation()
        renewed = Lease(
            lease_id,
            service_session_id,
            new_generation,
            self._clock_ns() + self._duration_ns,
        )
        try:
            self.store.renew_lease(
                lease_id,
                service_session_id,
                generation,
                new_generation,
                renewed.expires_monotonic_ns,
            )
        except StoreConflict as error:
            raise LeaseConflict(str(error)) from error
        return renewed

    def release(self, service_session_id: str, lease_id: str, generation: int) -> None:
        self.authorize(lease_id, generation, service_session_id=service_session_id)
        if getattr(self.supervisor, "has_unresolved_campaign", lambda: False)():
            raise LeaseConflict("ACTIVE_CAMPAIGN")
        try:
            self.store.set_lease_state(lease_id, generation, "RELEASED")
        except StoreConflict as error:
            raise LeaseConflict(str(error)) from error

    def authorize(
        self, lease_id: str, generation: int, *, service_session_id: str | None = None
    ) -> Lease:
        current = self.current()
        if current is None:
            raise LeaseConflict("LEASE_NOT_ACTIVE")
        if current.lease_id != lease_id:
            raise LeaseConflict("LEASE_IDENTITY_MISMATCH")
        if current.generation != generation:
            raise LeaseConflict("STALE_LEASE_GENERATION")
        if service_session_id is not None and current.service_session_id != service_session_id:
            raise LeaseConflict("LEASE_IDENTITY_MISMATCH")
        if self._clock_ns() >= current.expires_monotonic_ns:
            raise LeaseConflict("LEASE_EXPIRED")
        return current

    def browser_disconnected(self, _service_session_id: str) -> None:
        return None

    def expire_due(self, *, now_ns: int | None = None) -> bool:
        current = self.current()
        if current is None:
            return False
        now = self._clock_ns() if now_ns is None else now_ns
        if now < current.expires_monotonic_ns:
            return False
        self.store.set_lease_state(current.lease_id, current.generation, "EXPIRED")
        self._unresolved = True
        self.supervisor.cancel_for_reason("LEASE_EXPIRED")
        return True

    def can_start_campaign(self, service_session_id: str) -> bool:
        current = self.current()
        return (
            current is not None
            and current.service_session_id == service_session_id
            and self._clock_ns() < current.expires_monotonic_ns
            and not self._unresolved
            and not getattr(self.supervisor, "has_unresolved_campaign", lambda: False)()
        )

    def mark_recovered(self) -> None:
        self._unresolved = False
