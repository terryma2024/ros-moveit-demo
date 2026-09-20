"""Fail-closed global mutation arbitration.

The arbiter is the single server-side reservation authority. It never dispatches work;
it decides whether a domain may start, keeps the reservation alive until real terminal
and cleanup proof converge, and blocks instead of guessing when proof is missing.
"""

from __future__ import annotations

from typing import Callable

from .contracts import (
    IDLE,
    ActionTerminal,
    CancelIntent,
    DispatchAck,
    DispatchToken,
    MutationError,
    OperationSpec,
    ParentProjection,
    Reservation,
)
from .intent_store import IntentStore


class GlobalMutationArbiter:
    def __init__(self, store: IntentStore, *, clock_ns: Callable[[], int]) -> None:
        self.store = store
        self.clock_ns = clock_ns
        store.set_clock(clock_ns)

    # -- admission ---------------------------------------------------------------

    def begin(self, spec: OperationSpec) -> Reservation:
        """Take the global reservation, or return the recorded one for a repeated command."""
        with self.store.immediate_transaction():
            repeated = self.store.repeat(spec.command_id, self.store.fingerprint(spec))
            if repeated is not None:
                return repeated
            self.store.require_idle()
            return self.store.insert_parent(spec)

    # -- parent lifecycle --------------------------------------------------------

    def prepare_child(self, operation_id: str, child_id: str) -> DispatchToken:
        with self.store.immediate_transaction():
            return self.store.prepare_child(operation_id, child_id, now_ns=self.clock_ns())

    def record_ack(self, token: DispatchToken, ack: DispatchAck) -> None:
        """Record the accepted operation identity, even when the parent was cancelled."""
        with self.store.immediate_transaction():
            self.store.record_ack(token, ack)

    def record_terminal(self, terminal: ActionTerminal) -> None:
        with self.store.immediate_transaction():
            self.store.record_terminal(terminal)

    def cancel_parent(self, operation_id: str) -> CancelIntent:
        with self.store.immediate_transaction():
            return self.store.cancel_parent(operation_id)

    def pause(self, operation_id: str) -> None:
        with self.store.immediate_transaction():
            self.store.pause(operation_id)

    def settle(self, operation_id: str, *, cleanup_confirmed: bool) -> ParentProjection:
        """Refusal fences commit first; the caller sees the refusal afterwards."""
        with self.store.immediate_transaction():
            outcome = self.store.settle_locked(operation_id, cleanup_confirmed=cleanup_confirmed)
        if outcome.code:
            raise MutationError(outcome.code)
        return outcome.projection

    # -- observation -------------------------------------------------------------

    def projection(self, operation_id: str) -> ParentProjection:
        return self.store.projection(operation_id)

    def is_idle(self) -> bool:
        return self.store.global_state()[0] == IDLE

    def is_blocked(self) -> bool:
        return self.store.global_state()[0] != IDLE

    def require_idle(self) -> None:
        with self.store.immediate_transaction():
            self.store.require_idle()

    def block(self, reason: str) -> None:
        self.store.block(reason)

    def state(self) -> str:
        return self.store.global_state()[0]

    def blocked_reason(self) -> str | None:
        return self.store.global_state()[1]


def refuse(code: str, detail: str) -> MutationError:
    return MutationError(f"{code}: {detail}")
