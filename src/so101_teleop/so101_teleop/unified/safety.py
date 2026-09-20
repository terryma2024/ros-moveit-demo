"""Bounded, isolated cancellation lane.

Safety cancellation must never queue behind ordinary mutations, ordinary IPC backlog, or a
long arm action. The lane therefore owns its own small queue and its own processor task,
and it reaches exactly one owned goal per request. A cancel acknowledgement only means the
request was delivered; the lane keeps waiting for real stop evidence and blocks the whole
service when that evidence never arrives.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Literal

from .arbiter import GlobalMutationArbiter
from .contracts import (
    CHILD_ACKED,
    ActionKey,
    CancelReceipt,
    Domain,
    IntentCancelReceipt,
    MutationError,
    RequestAuthority,
    RevokeTarget,
)
from .goals import GoalRegistry

QUEUE_CLOSED = object()


@dataclass(frozen=True)
class SafetyLimits:
    delivery_s: float
    stop_s: float
    max_pending: int

    def __post_init__(self) -> None:
        if self.delivery_s <= 0 or self.stop_s <= 0 or self.max_pending <= 0:
            raise ValueError("safety limits must be positive")


@dataclass(frozen=True)
class SafetyAuthority:
    kind: Literal["browser", "maintenance", "watchdog"]
    domain: Domain
    service_epoch: str
    execution_generation: int
    instance: RequestAuthority | None


class SafetyLane:
    def __init__(
        self,
        registry: GoalRegistry,
        arbiter: GlobalMutationArbiter,
        *,
        limits: SafetyLimits,
        authorize: Callable[[SafetyAuthority, ActionKey], None],
        authorize_pending: Callable[[SafetyAuthority, RevokeTarget], None] | None = None,
        service_epoch: str | None = None,
    ) -> None:
        self.registry = registry
        self.arbiter = arbiter
        self.limits = limits
        self._authorize = authorize
        self._authorize_pending = authorize_pending
        self._service_epoch = service_epoch
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=limits.max_pending)
        self._processor: asyncio.Task | None = None
        self._receipts: dict[tuple, CancelReceipt] = {}
        self._revocations: dict[tuple, IntentCancelReceipt] = {}
        self._inflight: dict[tuple, asyncio.Future] = {}
        self._closed = False

    # -- public API --------------------------------------------------------------

    async def cancel(self, key: ActionKey, authority: SafetyAuthority) -> CancelReceipt:
        self._require_open()
        self._validate_authority(authority, key)
        if authority.kind == "browser" and authority.instance is None:
            raise MutationError("INSTANCE_AUTHORITY_REQUIRED: browser cancel needs an instance")
        self._authorize(authority, key)
        ident = ("cancel", key.operation_id, key.child_id, key.goal_uuid)
        recorded = self._receipts.get(ident)
        if recorded is not None:
            return recorded
        future = self._submit(ident, ("cancel", key, authority))
        return await asyncio.shield(future)

    async def revoke(self, target: RevokeTarget, authority: SafetyAuthority) -> IntentCancelReceipt:
        self._require_open()
        if self._authorize_pending is None:
            raise MutationError(
                "SAFETY_PENDING_AUTHORIZER_MISSING: production composition must inject the "
                "exact parent/child/runtime/generation owned-child validator"
            )
        self._validate_authority(authority, None)
        self._authorize_pending(authority, target)
        ident = (
            "revoke",
            target.key.operation_id,
            target.key.child_id,
            str(target.revocation_revision),
        )
        recorded = self._revocations.get(ident)
        if recorded is not None:
            return recorded
        future = self._submit(ident, ("revoke", target, authority))
        return await asyncio.shield(future)

    async def close(self) -> None:
        """Stop this lane's own processor. No foreign process is ever signalled."""
        if self._closed:
            return
        self._closed = True
        if self._processor is not None:
            await self._queue.put((None, QUEUE_CLOSED, None))
            await asyncio.shield(self._processor)
        for future in list(self._inflight.values()):
            if not future.done():
                future.set_exception(MutationError("SAFETY_LANE_CLOSED: lane shut down"))
            with_suppressed(future)
        self._inflight.clear()

    # -- internals ---------------------------------------------------------------

    def _require_open(self) -> None:
        if self._closed:
            raise MutationError("SAFETY_LANE_CLOSED: this safety lane is shut down")

    def _validate_authority(self, authority: SafetyAuthority, key: ActionKey | None) -> None:
        if self._service_epoch is not None and authority.service_epoch != self._service_epoch:
            raise MutationError(
                f"STALE_SERVICE_EPOCH: {authority.service_epoch} != {self._service_epoch}"
            )
        if authority.execution_generation <= 0:
            raise MutationError("STALE_EXECUTION_GENERATION: authority carries no generation")

    def _submit(self, ident: tuple, payload: tuple) -> asyncio.Future:
        existing = self._inflight.get(ident)
        if existing is not None:
            return existing
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait((ident, payload, future))
        except asyncio.QueueFull:
            self.arbiter.block("SAFETY_QUEUE_FULL")
            raise MutationError(
                f"SAFETY_QUEUE_FULL: {self.limits.max_pending} pending safety actions already"
            ) from None
        self._inflight[ident] = future
        self._ensure_processor()
        return future

    def _ensure_processor(self) -> None:
        if self._processor is None or self._processor.done():
            self._processor = asyncio.get_running_loop().create_task(self._run())

    async def _run(self) -> None:
        while True:
            ident, payload, future = await self._queue.get()
            if payload is QUEUE_CLOSED:
                self._queue.task_done()
                return
            kind = payload[0]
            try:
                if kind == "cancel":
                    receipt = await self._deliver_cancel(payload[1], payload[2])
                    self._receipts[ident] = receipt
                else:
                    receipt = await self._deliver_revoke(payload[1], payload[2])
                    self._revocations[ident] = receipt
            except BaseException as error:  # noqa: BLE001 - the lane must not die silently
                self.arbiter.block(f"SAFETY_LANE_ERROR: {type(error).__name__}: {error}")
                if not future.done():
                    future.set_exception(error)
            else:
                if not future.done():
                    future.set_result(receipt)
            finally:
                self._inflight.pop(ident, None)
                self._queue.task_done()

    async def _deliver_cancel(self, key: ActionKey, authority: SafetyAuthority) -> CancelReceipt:
        # Durable first: no later child of this parent may be dispatched.
        self.arbiter.cancel_parent(key.operation_id)
        goal = self.registry.require(key)
        try:
            accepted = await asyncio.wait_for(goal.cancel(), self.limits.delivery_s)
        except (asyncio.TimeoutError, TimeoutError):
            self.arbiter.block("CANCEL_DELIVERY_TIMEOUT")
            return CancelReceipt(key, False, None, "CANCEL_DELIVERY_TIMEOUT")
        if not accepted:
            self.arbiter.block("CANCEL_NOT_ACCEPTED")
            return CancelReceipt(key, False, None, "CANCEL_NOT_ACCEPTED")
        try:
            terminal = await asyncio.wait_for(goal.observe(), self.limits.stop_s)
        except (asyncio.TimeoutError, TimeoutError):
            self.arbiter.block("STOP_NOT_CONFIRMED")
            return CancelReceipt(key, True, None, "STOP_NOT_CONFIRMED")
        if not (terminal.stopped_confirmed or terminal.cleanup_confirmed):
            self.arbiter.block("STOP_NOT_CONFIRMED")
            return CancelReceipt(key, True, terminal, "STOP_NOT_CONFIRMED")
        self.arbiter.record_terminal(terminal)
        return CancelReceipt(key, True, terminal, None)

    async def _deliver_revoke(
        self, target: RevokeTarget, authority: SafetyAuthority
    ) -> IntentCancelReceipt:
        self.arbiter.cancel_parent(target.key.operation_id)
        parent = self.arbiter.store.parent_record(target.key.operation_id)
        linearized = bool(parent) and parent["revocation_revision"] >= target.revocation_revision
        child = self.arbiter.store.child_record(target.key.operation_id, target.key.child_id)
        submitted = bool(child) and child["phase"] == CHILD_ACKED
        if not linearized:
            self.arbiter.block("REVOKE_NOT_LINEARIZED")
            return IntentCancelReceipt(target, False, submitted, None, "REVOKE_NOT_LINEARIZED")
        return IntentCancelReceipt(target, True, submitted, None, None)


def with_suppressed(future: asyncio.Future) -> None:
    """Mark a resolved future's exception as retrieved without consuming it."""
    if future.done() and not future.cancelled():
        try:
            future.exception()
        except BaseException:  # noqa: BLE001 - already reported to the caller
            pass
