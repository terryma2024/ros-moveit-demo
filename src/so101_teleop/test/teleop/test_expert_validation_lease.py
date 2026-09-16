import asyncio
from types import SimpleNamespace

import pytest

from so101_teleop.expert_validation.lease import LeaseConflict, ValidationLeaseService
from so101_teleop.expert_validation.store import SupervisorStore


class Clock:
    now = 1_000

    def __call__(self):
        return self.now


class Supervisor:
    def __init__(self):
        self.cancel_requests = []
        self.active = False

    def cancel_for_reason(self, reason):
        self.cancel_requests.append(reason)

    def has_unresolved_campaign(self):
        return self.active


def _lease(tmp_path):
    store = SupervisorStore.open(tmp_path.resolve())
    clock = Clock()
    supervisor = Supervisor()
    service = ValidationLeaseService(
        store,
        supervisor,
        clock_ns=clock,
        duration_ns=100,
        renewal_margin_ns=20,
    )
    return service, store, clock, supervisor


def test_browser_disconnect_does_not_release_lease(tmp_path):
    service, store, _clock, _supervisor = _lease(tmp_path)
    try:
        lease = service.acquire("browser-a")
        service.browser_disconnected("browser-a")
        assert service.current().lease_id == lease.lease_id
    finally:
        store.close()


def test_expiry_requests_cancel_and_blocks_new_campaign(tmp_path):
    service, store, clock, supervisor = _lease(tmp_path)
    try:
        lease = service.acquire("browser-a")
        clock.now = lease.expires_monotonic_ns + 1
        service.expire_due()
        assert supervisor.cancel_requests == ["LEASE_EXPIRED"]
        replacement = service.acquire("browser-b")
        assert replacement.service_session_id == "browser-b"
        assert service.can_start_campaign("browser-b") is False
    finally:
        store.close()


def test_renew_fences_stale_generation(tmp_path):
    service, store, _clock, _supervisor = _lease(tmp_path)
    try:
        first = service.acquire("browser-a")
        renewed = service.renew("browser-a", first.lease_id, first.generation)
        assert renewed.generation == first.generation + 1
        with pytest.raises(LeaseConflict, match="STALE_LEASE_GENERATION"):
            service.renew("browser-a", first.lease_id, first.generation)
    finally:
        store.close()


def test_expired_lease_cannot_be_resurrected_by_renewal(tmp_path):
    service, store, clock, _supervisor = _lease(tmp_path)
    try:
        first = service.acquire("browser-a")
        clock.now = first.expires_monotonic_ns
        with pytest.raises(LeaseConflict, match="LEASE_EXPIRED"):
            service.renew("browser-a", first.lease_id, first.generation)
        assert service.current() == first
    finally:
        store.close()


def test_replacement_holder_cannot_preflight_before_expired_campaign_recovery(tmp_path):
    from so101_teleop.expert_validation.production import ProductionExpertValidationService
    from so101_teleop.expert_validation.service import ServiceConflict

    lease_service, store, clock, supervisor = _lease(tmp_path)
    try:
        first = lease_service.acquire("browser-a")
        supervisor.active = True
        clock.now = first.expires_monotonic_ns
        lease_service.expire_due()
        replacement = lease_service.acquire("browser-b")
        service = object.__new__(ProductionExpertValidationService)
        service.lease_service = lease_service
        service.registry = SimpleNamespace(require=lambda *_args: SimpleNamespace(
            mode_availability={"SEQUENTIAL": SimpleNamespace(available=True)}
        ))
        service.layout = SimpleNamespace(yolo_weights_path=None, grounded_root=None)
        with pytest.raises(ServiceConflict, match="VALIDATION_RECOVERY_REQUIRED"):
            asyncio.run(service.preflight_api({
                "service_session_id": "browser-b", "lease_id": replacement.lease_id,
                "lease_generation": replacement.generation, "execution_mode": "SEQUENTIAL",
            }))
        assert supervisor.cancel_requests == ["LEASE_EXPIRED"]
    finally:
        store.close()


def test_active_campaign_rejects_release(tmp_path):
    service, store, _clock, supervisor = _lease(tmp_path)
    try:
        lease = service.acquire("browser-a")
        supervisor.active = True
        with pytest.raises(LeaseConflict, match="ACTIVE_CAMPAIGN"):
            service.release("browser-a", lease.lease_id, lease.generation)
    finally:
        store.close()


def test_restart_invalidates_previous_active_lease(tmp_path):
    root = tmp_path.resolve()
    service, store, _clock, _supervisor = _lease(root)
    first = service.acquire("browser-a")
    store.close()
    reopened = SupervisorStore.open(root)
    try:
        restarted = ValidationLeaseService(reopened, Supervisor(), clock_ns=Clock())
        assert restarted.current() is None
        with pytest.raises(LeaseConflict, match="LEASE_NOT_ACTIVE"):
            restarted.renew("browser-a", first.lease_id, first.generation)
    finally:
        reopened.close()
