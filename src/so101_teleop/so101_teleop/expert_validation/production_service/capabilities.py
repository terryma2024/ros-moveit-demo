"""Lease maintenance, capability documents and worker count availability."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib
import logging
from pathlib import Path

from so101_teleop.expert_validation.preflight import (
    FIXED_WORKER_COUNTS,
    MACOS_EXECUTION_PROFILES,
    MACOS_WORKER_COUNTS,
    UNSUPPORTED_ON_MACOS,
)


class ServiceCapabilities:
    def close(self) -> None:
        self.stop_maintenance()
        self.store.close()

    def start_maintenance(self) -> None:
        """Start the expiry loop. Synchronous on purpose: the lifecycle awaits a returned coroutine,
        so an ``async def`` here would block startup for as long as the loop runs."""
        if self._maintenance_task is not None and not self._maintenance_task.done():
            return
        self.maintenance_failed = False
        self._maintenance_task = asyncio.get_running_loop().create_task(self._maintain_leases())

    def stop_maintenance(self) -> None:
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            self._maintenance_task = None

    async def _maintain_leases(self) -> None:
        """Expire due leases until expiry itself stops working, then stop and say so."""
        while True:
            try:
                self.lease_service.expire_due()
            except Exception:  # noqa: BLE001 - a domain that cannot expire leases must stay visible
                logging.getLogger(__name__).exception("LEASE_MAINTENANCE_FAILED")
                self.maintenance_failed = True
                supervisor = getattr(self, "supervisor", None)
                cancel = getattr(supervisor, "cancel_for_reason", None)
                if cancel is not None:
                    try:
                        cancel("LEASE_MAINTENANCE_FAILED")
                    except Exception:  # noqa: BLE001 - the failure is already recorded
                        logging.getLogger(__name__).exception("LEASE_OWNER_CANCEL_FAILED")
                return
            await asyncio.sleep(self.MAINTENANCE_INTERVAL_S)

    def capabilities(self):
        lease = self.lease_service.capabilities
        document = self._execution_document()
        if document is not None and document.profile is not None:
            return self._macos_capabilities(document, lease)
        capability = self.registry.require("moveit_expert", "validate_pick_place")
        available_modes = tuple(
            mode
            for mode in capability.execution_modes
            if capability.mode_availability[mode].available
        )
        return {
            "available": bool(available_modes),
            "execution_modes": available_modes,
            "fixed_worker_counts": FIXED_WORKER_COUNTS,
            "worker_count_availability": self._worker_count_availability(),
            "start_guard_policy": self._start_guard_policy(),
            "default_execution_mode": capability.default_execution_mode,
            "lease_duration_s": lease.duration_s,
            "lease_renewal_margin_s": lease.renewal_margin_s,
        }

    def _execution_document(self):
        """The execution document this service would run, or ``None`` when it cannot be read."""

        from so101_teleop.expert_validation.preflight import describe_execution_document

        path = Path(self.layout.parallel_config_path)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None
        cached = getattr(self, "_document_cache", None)
        if cached is not None and cached[0] == (str(path), digest):
            return cached[1]
        try:
            document = describe_execution_document(path)
        except Exception:  # noqa: BLE001 - an unreadable document advertises nothing
            return None
        self._document_cache = ((str(path), digest), document)
        return document

    def _macos_capabilities(self, document, lease):
        """The platform-bound document: fixed W1/W2, and no budget or qualification authority.

        The StartGuard policy is still displayed, because a client has to be able to show the
        cutoffs a start is judged against; the note next to it says what it is not.
        """

        from so101_teleop.expert_validation.api import (
            START_GUARD_NOT_A_QUALIFICATION,
            WorkerCountAvailability,
        )

        profile = document.profile
        availability = tuple(
            WorkerCountAvailability(
                worker_count=count,
                selectable=count in MACOS_WORKER_COUNTS,
                status="SUPPORTED" if count in MACOS_WORKER_COUNTS else UNSUPPORTED_ON_MACOS,
                reason_codes=() if count in MACOS_WORKER_COUNTS else (UNSUPPORTED_ON_MACOS,),
                profile_sha256=None,
                qualification_sha256=None,
            )
            for count in FIXED_WORKER_COUNTS
        )
        return {
            "available": True,
            "platform": profile.platform,
            "execution_modes": ("SEQUENTIAL", "PARALLEL"),
            "default_execution_mode": profile.execution_mode,
            "fixed_worker_counts": FIXED_WORKER_COUNTS,
            "worker_count_availability": availability,
            "support_matrix": tuple(row.to_document() for row in MACOS_EXECUTION_PROFILES),
            "execution_profile": profile.profile,
            "execution_schema_version": document.schema_version,
            "execution_config_sha256": document.config_sha256,
            # No budget provider and no per-N qualification is consulted for the macOS matrix.
            "worker_qualifications": (),
            "adaptive_default_ladder": (),
            "start_guard_policy": self._start_guard_policy(),
            "start_guard_note": START_GUARD_NOT_A_QUALIFICATION,
            "lease_duration_s": lease.duration_s,
            "lease_renewal_margin_s": lease.renewal_margin_s,
        }

    def _start_guard_policy(self):
        """The enforced guard policy for display; never a resource qualification."""

        engine = getattr(getattr(self, "supervisor", None), "preflight_engine", None)
        probe = getattr(engine, "_resources", None)
        guard_object = getattr(probe, "_start_guard", None)
        if guard_object is None:
            return None
        try:
            policy = guard_object.policy
        except Exception:
            return None
        if policy is None:
            return None
        return {
            "timeout_s": policy.timeout_s,
            "cpu_busy_warn_fraction": policy.cpu_busy_warn_fraction,
            "ram_minimum_bytes": policy.ram_minimum_bytes,
            "ram_minimum_fraction": policy.ram_minimum_fraction,
            "gpu_minimum_bytes": policy.gpu_minimum_bytes,
            # Present only for the schema-v4 macOS MPS combination; null keeps the v3 answer
            # byte-identical for every existing consumer.
            "mps_minimum_headroom_bytes": getattr(policy, "mps_minimum_headroom_bytes", None),
        }

    def _worker_count_availability(self):
        """Every advertised count whose domains/ports exist; the guard decides at start."""

        from so101_teleop.expert_validation.api import WorkerCountAvailability

        configured = getattr(self, "configured_worker_counts", None)
        if configured is None:
            configured = tuple(range(2, FIXED_WORKER_COUNTS[-1] + 1))
        available = set(configured)
        return tuple(
            WorkerCountAvailability(
                worker_count=count,
                selectable=count in available,
                status="CONFIGURED" if count in available else "NOT_CONFIGURED",
                reason_codes=() if count in available else ("DOMAIN_OR_PORT_UNAVAILABLE",),
                profile_sha256=None,
                qualification_sha256=None,
            )
            for count in FIXED_WORKER_COUNTS[1:]
        )

    def acquire_lease(self, body):
        return asdict(self.lease_service.acquire(body["service_session_id"]))

    def renew_lease(self, lease_id, body):
        return asdict(
            self.lease_service.renew(
                body["service_session_id"], lease_id, body["generation"]
            )
        )

    def release_lease(self, lease_id, body):
        self.lease_service.release(
            body["service_session_id"], lease_id, body["generation"]
        )
        return {"lease_id": lease_id, "released": True}
