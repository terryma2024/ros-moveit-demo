"""One durable shared point queue for a macOS service campaign (design section 8).

The W2 slots are concurrent *capacity*: every selected point enters this queue, `lease_next()`
hands one Worker exactly one point, and `commit_result()` is the only way a point reaches a
terminal business outcome. State is written through `runtime.task_artifacts.atomic_json`, which
fsyncs the payload and the directory before replacing the previous state, so a campaign that
crashes between a lease and its result is recovered by reopening the same root rather than by
guessing which points were already executed.

Invariants enforced here:

* only points of the bound selection can ever be leased, in the binding's own order;
* one lease carries one point and one attempt id, derived from the worker generation;
* the same worker asking twice gets the same lease instead of a second attempt;
* a lower generation than the slot already recorded is `QUEUE_STALE_GENERATION`;
* a slot that lost its Worker (higher generation) abandons the old lease, records the abandoned
  attempt, and re-leases the same point to the replacement;
* attempt-level `INVALID` is not a business outcome and cannot be committed as one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..runtime.task_artifacts import atomic_json
from .resource_identity import canonical_sha256
from .selection import FirstPassSelectionBinding, RetrySelectionBinding

STATE_SCHEMA_VERSION = 1
STATE_BASENAME = "queue-state.json"
BUSINESS_OUTCOMES: tuple[str, ...] = ("PASSED", "FAILED", "INDETERMINATE")


class QueueError(RuntimeError):
    """The durable point queue refused an operation."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise QueueError("QUEUE_ID_INVALID", f"{name}={value!r}")
    return value


def _require_sha256(name: str, value: object, *, code: str = "QUEUE_HASH_INVALID") -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise QueueError(code, f"{name}={value!r}")
    return value


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    """Which Worker is asking, in which slot, at which generation."""

    worker_id: str
    slot_id: str
    generation: int

    def __post_init__(self) -> None:
        _require_id("worker_id", self.worker_id)
        _require_id("slot_id", self.slot_id)
        if not isinstance(self.generation, int) or self.generation < 1:
            raise QueueError("QUEUE_GENERATION_INVALID", str(self.generation))

    def as_document(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "slot_id": self.slot_id,
            "generation": self.generation,
        }


@dataclass(frozen=True, slots=True)
class PointLease:
    """One Worker's claim on exactly one selected point and one attempt."""

    campaign_id: str
    batch_id: str
    point_id: str
    attempt_id: str
    generation: int
    worker_id: str
    slot_id: str
    point_sha256: str

    def __post_init__(self) -> None:
        for name in ("campaign_id", "batch_id", "point_id", "attempt_id", "worker_id", "slot_id"):
            _require_id(name, getattr(self, name))
        _require_sha256("point_sha256", self.point_sha256)
        if not isinstance(self.generation, int) or self.generation < 1:
            raise QueueError("QUEUE_GENERATION_INVALID", str(self.generation))

    @property
    def identity(self) -> tuple[str, str, str, str, int, str]:
        """The design's scheduling identity, in its documented order."""

        return (
            self.campaign_id,
            self.batch_id,
            self.point_id,
            self.attempt_id,
            self.generation,
            self.worker_id,
        )

    def as_document(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "point_id": self.point_id,
            "attempt_id": self.attempt_id,
            "generation": self.generation,
            "worker_id": self.worker_id,
            "slot_id": self.slot_id,
            "point_sha256": self.point_sha256,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_document())


@dataclass(frozen=True, slots=True)
class CommittedResult:
    """The durable outcome of one attempt; `INVALID` belongs to attempt validity, not here."""

    point_id: str
    attempt_id: str
    outcome: str
    evidence_sha256: str
    result_sha256: str

    def __post_init__(self) -> None:
        _require_id("point_id", self.point_id)
        _require_id("attempt_id", self.attempt_id)
        if self.outcome not in BUSINESS_OUTCOMES:
            raise QueueError("QUEUE_OUTCOME_INVALID", f"outcome={self.outcome!r}")
        _require_sha256("evidence_sha256", self.evidence_sha256)
        _require_sha256("result_sha256", self.result_sha256)

    def as_document(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "attempt_id": self.attempt_id,
            "outcome": self.outcome,
            "evidence_sha256": self.evidence_sha256,
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    """What the queue durably holds right now, in binding order."""

    pending_point_ids: tuple[str, ...]
    active_leases: tuple[PointLease, ...]
    results: tuple[CommittedResult, ...]
    abandoned_attempts: tuple[str, ...]


def _lease_from_document(document: dict[str, object]) -> PointLease:
    return PointLease(
        campaign_id=str(document["campaign_id"]),
        batch_id=str(document["batch_id"]),
        point_id=str(document["point_id"]),
        attempt_id=str(document["attempt_id"]),
        generation=int(document["generation"]),
        worker_id=str(document["worker_id"]),
        slot_id=str(document["slot_id"]),
        point_sha256=str(document["point_sha256"]),
    )


def _result_from_document(document: dict[str, object]) -> CommittedResult:
    return CommittedResult(
        point_id=str(document["point_id"]),
        attempt_id=str(document["attempt_id"]),
        outcome=str(document["outcome"]),
        evidence_sha256=str(document["evidence_sha256"]),
        result_sha256=str(document["result_sha256"]),
    )


class DurablePointQueue:
    """Fsync-backed shared queue over one immutable selection binding."""

    def __init__(
        self,
        *,
        root: Path,
        binding: FirstPassSelectionBinding | RetrySelectionBinding,
    ) -> None:
        if not isinstance(binding, (FirstPassSelectionBinding, RetrySelectionBinding)):
            raise QueueError(
                "QUEUE_BINDING_TYPE",
                f"{type(binding).__name__} is not a selection binding",
            )
        self._binding = binding
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._state_path = self._root / STATE_BASENAME
        self._selected_point_ids = tuple(binding.selected_point_ids)
        self._points_by_id = {point.point_id: point for point in binding.points} if hasattr(
            binding, "points"
        ) else {binding.point.point_id: binding.point}
        self._state = self._load_state()

    # -- state -------------------------------------------------------------------------

    def _fresh_state(self) -> dict[str, object]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "selection_sha256": self._binding.selection_sha256,
            "campaign_id": self._binding.campaign_id,
            "batch_id": self._binding.batch_id,
            "selected_point_ids": list(self._selected_point_ids),
            "active_leases": {},
            "committed_results": {},
            "abandoned_attempts": [],
            "slot_generations": {},
        }

    def _load_state(self) -> dict[str, object]:
        if not self._state_path.exists():
            return self._fresh_state()
        try:
            document = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise QueueError("QUEUE_STATE_UNREADABLE", str(self._state_path)) from error
        if not isinstance(document, dict) or document.get("schema_version") != STATE_SCHEMA_VERSION:
            raise QueueError("QUEUE_STATE_UNREADABLE", "schema")
        if document.get("selection_sha256") != self._binding.selection_sha256:
            raise QueueError(
                "QUEUE_STATE_BINDING_MISMATCH",
                f"{document.get('selection_sha256')} != {self._binding.selection_sha256}",
            )
        return document

    def _persist(self) -> None:
        atomic_json(self._state_path, self._state)

    @property
    def state_path(self) -> Path:
        return self._state_path

    # -- helpers -----------------------------------------------------------------------

    def _active_leases(self) -> dict[str, object]:
        return self._state["active_leases"]  # type: ignore[return-value]

    def _committed_results(self) -> dict[str, object]:
        return self._state["committed_results"]  # type: ignore[return-value]

    def _slot_generation(self, slot_id: str) -> int:
        generations = self._state["slot_generations"]  # type: ignore[assignment]
        return int(generations.get(slot_id, 0))

    def _point_of(self, point_id: str):
        point = self._points_by_id.get(point_id)
        if point is None:
            raise QueueError("QUEUE_UNSELECTED_POINT", point_id)
        return point

    # -- queue -------------------------------------------------------------------------

    def lease_next(self, worker: WorkerIdentity) -> PointLease | None:
        """Lease the next pending point to ``worker``; repeat calls return the same lease."""

        if not isinstance(worker, WorkerIdentity):
            raise QueueError("QUEUE_WORKER_TYPE", type(worker).__name__)
        recorded = self._slot_generation(worker.slot_id)
        if worker.generation < recorded:
            raise QueueError(
                "QUEUE_STALE_GENERATION",
                f"{worker.slot_id} already at generation {recorded}",
            )

        active = self._active_leases()
        for point_id in self._selected_point_ids:
            document = active.get(point_id)
            if document is None:
                continue
            lease = _lease_from_document(document)  # type: ignore[arg-type]
            if lease.worker_id == worker.worker_id and lease.slot_id == worker.slot_id:
                if lease.generation == worker.generation:
                    return lease

        changed = False
        if worker.generation > recorded:
            for point_id in list(active):
                lease = _lease_from_document(active[point_id])  # type: ignore[arg-type]
                if lease.slot_id != worker.slot_id:
                    continue
                abandoned = self._state["abandoned_attempts"]  # type: ignore[assignment]
                if lease.attempt_id not in abandoned:
                    abandoned.append(lease.attempt_id)
                del active[point_id]
            self._state["slot_generations"][worker.slot_id] = worker.generation  # type: ignore[index]
            changed = True

        committed = self._committed_results()
        for point_id in self._selected_point_ids:
            if point_id in active or point_id in committed:
                continue
            point = self._point_of(point_id)
            lease = PointLease(
                campaign_id=self._binding.campaign_id,
                batch_id=self._binding.batch_id,
                point_id=point_id,
                attempt_id=f"{point_id}-attempt-{worker.generation}",
                generation=worker.generation,
                worker_id=worker.worker_id,
                slot_id=worker.slot_id,
                point_sha256=point.point_sha256,
            )
            active[point_id] = lease.as_document()
            self._persist()
            return lease

        if changed:
            self._persist()
        return None

    def commit_result(
        self,
        lease: PointLease,
        result: CommittedResult,
        *,
        worker: WorkerIdentity | None = None,
    ) -> None:
        """Persist one business outcome for ``lease``.

        ``worker`` is optional: when the coordinator knows which Worker proposed the commit it
        must be supplied, and a proposal from another worker or an older generation is refused.
        Without it the presented lease itself must match the durable active lease exactly, so a
        forged or edited lease still cannot commit anything.
        """

        if not isinstance(lease, PointLease):
            raise QueueError("QUEUE_LEASE_TYPE", type(lease).__name__)
        if not isinstance(result, CommittedResult):
            raise QueueError("QUEUE_RESULT_TYPE", type(result).__name__)

        active = self._active_leases()
        document = active.get(lease.point_id)
        if document is None:
            if lease.point_id in self._committed_results():
                raise QueueError("QUEUE_POINT_TERMINAL", lease.point_id)
            if lease.point_id not in self._selected_point_ids:
                raise QueueError("QUEUE_UNSELECTED_POINT", lease.point_id)
            if lease.attempt_id in self._state["abandoned_attempts"]:  # type: ignore[operator]
                raise QueueError("QUEUE_LEASE_UNKNOWN", lease.attempt_id)
            raise QueueError("QUEUE_LEASE_UNKNOWN", lease.point_id)

        stored = _lease_from_document(document)  # type: ignore[arg-type]
        if stored.as_document() != lease.as_document():
            raise QueueError(
                "QUEUE_LEASE_MISMATCH",
                f"{lease.sha256} != stored {stored.sha256}",
            )

        if worker is not None:
            if worker.worker_id != lease.worker_id or worker.slot_id != lease.slot_id:
                raise QueueError(
                    "QUEUE_LEASE_OWNER_MISMATCH",
                    f"{worker.worker_id}/{worker.slot_id} != {lease.worker_id}/{lease.slot_id}",
                )
            if worker.generation < lease.generation:
                raise QueueError(
                    "QUEUE_STALE_GENERATION",
                    f"{worker.generation} < {lease.generation}",
                )
            if worker.generation != lease.generation:
                raise QueueError(
                    "QUEUE_GENERATION_MISMATCH",
                    f"{worker.generation} != {lease.generation}",
                )

        if result.point_id != lease.point_id or result.attempt_id != lease.attempt_id:
            raise QueueError(
                "QUEUE_RESULT_MISMATCH",
                f"{result.point_id}/{result.attempt_id} != {lease.point_id}/{lease.attempt_id}",
            )

        self._committed_results()[lease.point_id] = result.as_document()
        del active[lease.point_id]
        self._persist()

    def snapshot(self) -> QueueSnapshot:
        active = self._active_leases()
        committed = self._committed_results()
        leases = tuple(
            _lease_from_document(active[point_id])  # type: ignore[arg-type]
            for point_id in self._selected_point_ids
            if point_id in active
        )
        results = tuple(
            _result_from_document(committed[point_id])  # type: ignore[arg-type]
            for point_id in self._selected_point_ids
            if point_id in committed
        )
        pending = tuple(
            point_id
            for point_id in self._selected_point_ids
            if point_id not in active and point_id not in committed
        )
        return QueueSnapshot(
            pending_point_ids=pending,
            active_leases=leases,
            results=results,
            abandoned_attempts=tuple(self._state["abandoned_attempts"]),  # type: ignore[arg-type]
        )

    @property
    def selection_sha256(self) -> str:
        return self._binding.selection_sha256
