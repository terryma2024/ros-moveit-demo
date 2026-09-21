"""Verification-only projection sources (design section 9).

A projection source has exactly two jobs: verify that the upstream history it reads belongs to
the durable execution binding it was created for, and hand the verified events to the canonical
reducer. It must never merge a `payload.delta`, never derive point status and never decide a
terminal - that is the reducer's job, and the store applies both in one transaction.

`CoordinatorJournalSource` is the macOS W1/W2 and fixed-coordinator source: it reuses the existing
journal verification (`_verified_history`, manifest verification, contiguous hash chain, the
read-only upstream binding) and returns `VerifiedEvent` values in the batch's own order together
with the cursor a caller may accept once the batch has been reduced and persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    _default_manifest_verifier,
    _event_view,
    _next_cursor,
    _verified_history,
    _verify_reader_binding,
)

#: Event types whose payload points at a sealed result manifest that must verify before the event
#: can be reduced.
_RESULT_EVENT_TYPES = frozenset({"RESULT_COMMITTED", "VALIDATION_COMMITTED"})


@dataclass(frozen=True, slots=True)
class VerifiedEvent:
    """One verified committed event, with no projection applied."""

    type: str  # noqa: A003 - mirrors the journal's public event.type contract
    payload: Mapping[str, object]
    idempotency_key: str
    coordinator_epoch: int
    sequence: int
    frame_sha256: str
    batch_id: str

    @classmethod
    def from_view(cls, view, batch_id: str) -> "VerifiedEvent":
        sequence = int(getattr(view, "sequence"))
        frame_sha256 = str(getattr(view, "frame_sha256"))
        idempotency_key = getattr(view, "idempotency_key", None) or (
            f"{batch_id}/{sequence}/{frame_sha256}"
        )
        return cls(
            type=str(getattr(view, "type")),
            payload=dict(getattr(view, "payload")),
            idempotency_key=str(idempotency_key),
            coordinator_epoch=int(getattr(view, "owner_epoch", getattr(view, "coordinator_epoch", 0))),
            sequence=sequence,
            frame_sha256=frame_sha256,
            batch_id=batch_id,
        )

    def as_document(self) -> dict[str, object]:
        return {
            "type": self.type,
            "payload": dict(self.payload),
            "idempotency_key": self.idempotency_key,
            "coordinator_epoch": self.coordinator_epoch,
            "sequence": self.sequence,
            "frame_sha256": self.frame_sha256,
            "batch_id": self.batch_id,
        }


@dataclass(frozen=True, slots=True)
class VerifiedEventBatch:
    """Verified events plus the cursor a caller may accept after reducing and persisting them."""

    events: tuple[VerifiedEvent, ...]
    next_cursor: AcceptedCoordinatorCursor
    unconfirmed_durability: bool = False


class ProjectionSource(Protocol):
    """Anything the service may read verified campaign events from."""

    def read_after(self, cursor: AcceptedCoordinatorCursor | None) -> VerifiedEventBatch: ...


class CoordinatorJournalSource:
    """The coordinator journal as a verification-only projection source."""

    kind = "COORDINATOR"

    def __init__(
        self,
        journal,
        binding: CampaignUpstreamBinding,
        *,
        manifest_verifier=None,
    ) -> None:
        _verify_reader_binding(journal, binding, "COORDINATOR")
        self.journal = journal
        self.binding = binding
        self.manifest_verifier = manifest_verifier or _default_manifest_verifier
        self.initial_cursor = AcceptedCoordinatorCursor.initial(binding)

    def read_after(self, cursor: AcceptedCoordinatorCursor | None) -> VerifiedEventBatch:
        effective = cursor if cursor is not None else self.initial_cursor
        history, fresh = _verified_history(
            self.journal, self.binding, effective, owner_kind="COORDINATOR"
        )
        for event in history:
            if event.type in _RESULT_EVENT_TYPES:
                response = event.payload.get("response")
                if not isinstance(response, Mapping):
                    from .coordinator_events import CoordinatorProjectionError

                    raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
                self.manifest_verifier(response, self.binding)
        return VerifiedEventBatch(
            events=tuple(
                VerifiedEvent.from_view(
                    _event_view(event, self.binding.batch_id), self.binding.batch_id
                )
                for event in fresh
            ),
            next_cursor=_next_cursor(history, self.binding),
        )
