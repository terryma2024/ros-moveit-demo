"""Single lifecycle owner for the unified web service.

Startup order is fixed: verify configuration and durable store locks, establish the arbiter
and domain state, then start validation lease maintenance, subscriptions and the configured
ROS bridge. Shutdown stops accepting new mutations first, keeps the renewal and cancellation
safety path alive while owned work converges, and only then closes maintenance, IPC and
stores. Losing ROS lowers Teleop readiness; it never becomes a reason to guess a runtime.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any


class UnifiedLifecycle:
    def __init__(self, services: Any) -> None:
        self.services = services
        self.service_epoch = uuid.uuid4().hex
        self.started = False
        self.accepting_mutations = False
        self.teleop_error: str | None = None
        self.validation_error: str | None = None
        self._tasks: list[asyncio.Task] = []

    # -- startup -----------------------------------------------------------------

    async def startup(self) -> None:
        """Establish ownership before serving; never auto-start a simulation."""
        self.started = False
        self.accepting_mutations = False
        if self.services.arbiter is not None:
            self.services.arbiter.require_idle()
        await self._start_validation_maintenance()
        await self._start_bridge()
        self.accepting_mutations = True
        self.started = True

    async def _start_validation_maintenance(self) -> None:
        validation = self.services.validation
        start = getattr(validation, "start_maintenance", None) if validation is not None else None
        if start is None:
            return
        try:
            result = start()
            if asyncio.iscoroutine(result):
                await result
        except Exception as error:  # noqa: BLE001 - a blocked domain must stay visible
            self.validation_error = f"{type(error).__name__}: {error}"

    async def _start_bridge(self) -> None:
        bridge = self.services.bridge
        if bridge is None:
            return
        try:
            owner = await bridge.start()
        except Exception as error:  # noqa: BLE001 - ROS absence only lowers Teleop readiness
            self.teleop_error = f"{type(error).__name__}: {error}"
            if self.services.teleop is not None:
                self.services.teleop = None
            return
        del owner

    # -- shutdown ----------------------------------------------------------------

    async def shutdown(self) -> None:
        """Refuse new mutations first, then converge, then close maintenance and IPC."""
        self.accepting_mutations = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        bridge = self.services.bridge
        if bridge is not None:
            with contextlib.suppress(Exception):
                await bridge.stop_owned()
        self.started = False

    # -- qualification gate ------------------------------------------------------

    def budget_adapter(self):
        """The read-only adapter over the independently owned qualification provider."""
        from .budget_adapter import BudgetAdapter

        return BudgetAdapter(self.services.budget_source)

    def require_start(self, selected_n: int, runtime_identity: str):
        """Fresh live qualification check; a start must never trust a cached view."""
        return self.budget_adapter().require_start(selected_n, runtime_identity=runtime_identity)

    # -- observation -------------------------------------------------------------

    def teleop_ready(self) -> bool:
        return self.accepting_mutations and self.services.teleop is not None

    def health(self) -> dict:
        validation = self.services.validation
        return {
            "service_epoch": self.service_epoch,
            "started": self.started,
            "accepting_mutations": self.accepting_mutations,
            # A lease-expiry loop that died leaves the domain unable to issue another lease, so it is
            # reported next to the other domain errors rather than only in a log line.
            "validation_maintenance_failed": bool(
                getattr(validation, "maintenance_failed", False)
            ),
            "teleop_error": self.teleop_error,
            "validation_error": self.validation_error,
        }
