"""The unified service must actually run the validation lease-expiry loop.

`create_expert_validation_app` starts that loop in its own lifespan. The unified composition mounts
the validation *routes* without that lifespan, and `UnifiedLifecycle` looks for a ``start_maintenance``
hook on the validation service to take over the job. No implementation provided the hook, so nothing
expired anything - and the consequence was measured on the live service rather than inferred: an
expired lease stayed ``ACTIVE`` in the store more than a hundred seconds past its own deadline
(`monotonic now 1979295264158958` against `expires_monotonic_ns 1979185746783791`), and every later
``POST /expert-validation/lease`` was refused ``LEASE_ALREADY_HELD`` for good. One acquire by a session
that goes away would block every campaign on that domain, and `/health` still reported validation
"ready" because the failure flag is only set by an exception in a task that never ran.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from so101_teleop.expert_validation.production import ProductionExpertValidationService
from so101_teleop.unified.lifecycle import UnifiedLifecycle


class FakeValidationService:
    def __init__(self) -> None:
        self.started = 0

    def start_maintenance(self) -> None:
        self.started += 1


class FakeServices:
    def __init__(self, validation) -> None:
        self.validation = validation
        self.arbiter = None
        self.bridge = None
        self.teleop = None


def test_the_lifecycle_starts_the_maintenance_the_service_documents():
    validation = FakeValidationService()
    lifecycle = UnifiedLifecycle(FakeServices(validation))

    async def run() -> None:
        await lifecycle.startup()
        assert validation.started == 1, "startup must start the loop it documents"

    asyncio.run(run())


def test_the_production_service_provides_the_hook_and_reports_its_failure():
    assert hasattr(ProductionExpertValidationService, "start_maintenance"), (
        "without this hook the unified composition never expires a lease"
    )
    assert hasattr(ProductionExpertValidationService, "stop_maintenance")
    # Synchronous on purpose: the lifecycle awaits a returned coroutine, so an async hook would block
    # startup for as long as the loop runs.
    assert not asyncio.iscoroutinefunction(ProductionExpertValidationService.start_maintenance)


class _FakeLeaseService:
    def __init__(self, failures_after: int | None = None) -> None:
        self.calls = 0
        self.failures_after = failures_after

    def expire_due(self) -> bool:
        self.calls += 1
        if self.failures_after is not None and self.calls > self.failures_after:
            raise RuntimeError("STORE_UNAVAILABLE")
        return False


def _bare_service(lease_service, supervisor=None):
    service = object.__new__(ProductionExpertValidationService)
    service.lease_service = lease_service
    service.supervisor = supervisor
    service._maintenance_task = None
    service.maintenance_failed = False
    service.MAINTENANCE_INTERVAL_S = 0.01
    return service


def test_the_loop_expires_leases_repeatedly():
    lease = _FakeLeaseService()
    service = _bare_service(lease)

    async def run() -> None:
        service.start_maintenance()
        await asyncio.sleep(0.06)
        service.stop_maintenance()

    asyncio.run(run())
    assert lease.calls >= 3, f"the loop ran {lease.calls} times in 60 ms"
    assert service.maintenance_failed is False
    assert service._maintenance_task is None


def test_the_loop_stops_and_says_so_when_expiry_itself_fails():
    lease = _FakeLeaseService(failures_after=2)
    cancels: list[str] = []

    class Supervisor:
        def cancel_for_reason(self, reason):
            cancels.append(reason)

    service = _bare_service(lease, Supervisor())

    async def run() -> None:
        service.start_maintenance()
        deadline = time.monotonic() + 2.0
        while not service.maintenance_failed and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert service.maintenance_failed is True, "a dead expiry loop must not look healthy"
    assert lease.calls == 3, "the loop stops instead of spinning on a broken store"
    assert cancels == ["LEASE_MAINTENANCE_FAILED"]


def test_health_reports_a_dead_expiry_loop():
    lifecycle = UnifiedLifecycle(FakeServices(FakeValidationService()))
    lifecycle.services.validation.maintenance_failed = True
    assert lifecycle.health()["validation_maintenance_failed"] is True
    lifecycle.services.validation.maintenance_failed = False
    assert lifecycle.health()["validation_maintenance_failed"] is False
