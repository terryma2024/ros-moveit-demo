"""The canonical reducer over verified committed campaign events (design section 9).

One reducer owns the campaign projection. Projection sources adapt and verify events; they never
merge a `payload.delta` themselves, and React/OpenAPI only ever read the state this module
produces. The reducer keeps four orthogonal axes apart:

* point status: ``UNRUN`` / ``PASSED`` / ``FAILED`` / ``INDETERMINATE`` (business truth only);
* execution phase: ``QUEUED`` / ``LEASED`` / ``RUNNING`` / ``TERMINAL``;
* attempt validity (``VALID`` / ``INVALID``) and infrastructure outcome (``NONE`` / ``FAILED``);
* batch business terminal, infrastructure terminal, cleanup complete and recovery fence.

`RESULT_COMMITTED` is the only event that derives a point terminal; `POINT_TERMINAL` merely
confirms the same result hash. An attempt-level `INVALID` or an infrastructure failure never
becomes a business `FAILED`, and `BATCH_TERMINAL` never implies that cleanup happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ReducerError(RuntimeError):
    """An event cannot be reduced into the campaign state."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class PointStatus(StrEnum):
    UNRUN = "UNRUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class ExecutionPhase(StrEnum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    TERMINAL = "TERMINAL"


class AttemptValidity(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


class InfrastructureOutcome(StrEnum):
    NONE = "NONE"
    FAILED = "FAILED"


BUSINESS_OUTCOMES = (PointStatus.PASSED, PointStatus.FAILED, PointStatus.INDETERMINATE)

_FINAL_EVENT = "CLEANUP_COMMITTED"
_TERMINAL_EVENT = "BATCH_TERMINAL"


def _require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ReducerError("REDUCER_PAYLOAD_INVALID", f"{name}={value!r}")
    return value


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ReducerError("REDUCER_PAYLOAD_INVALID", f"{name}={value!r}")
    return value


def _optional_hash(value: object) -> str | None:
    """Read a persisted identity hash that a layout may never have published."""

    return None if value is None else str(value)


@dataclass(frozen=True, slots=True)
class AttemptState:
    point_id: str
    attempt_id: str
    lifecycle: ExecutionPhase
    validity: AttemptValidity
    infrastructure: InfrastructureOutcome
    result_sha256: str | None = None

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "AttemptState":
        return cls(
            point_id=str(document["point_id"]),
            attempt_id=str(document["attempt_id"]),
            lifecycle=ExecutionPhase(str(document["lifecycle"])),
            validity=AttemptValidity(str(document["validity"])),
            infrastructure=InfrastructureOutcome(str(document["infrastructure"])),
            result_sha256=document.get("result_sha256"),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "attempt_id": self.attempt_id,
            "lifecycle": self.lifecycle.value,
            "validity": self.validity.value,
            "infrastructure": self.infrastructure.value,
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True, slots=True)
class PointState:
    point_id: str
    status: PointStatus = PointStatus.UNRUN
    phase: ExecutionPhase = ExecutionPhase.QUEUED
    attempt_id: str | None = None
    result_sha256: str | None = None
    worker_id: str | None = None
    slot_id: str | None = None

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "PointState":
        return cls(
            point_id=str(document["point_id"]),
            status=PointStatus(str(document["status"])),
            phase=ExecutionPhase(str(document["phase"])),
            attempt_id=document.get("attempt_id"),
            result_sha256=document.get("result_sha256"),
            worker_id=document.get("worker_id"),
            slot_id=document.get("slot_id"),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "status": self.status.value,
            "phase": self.phase.value,
            "attempt_id": self.attempt_id,
            "result_sha256": self.result_sha256,
            "worker_id": self.worker_id,
            "slot_id": self.slot_id,
        }


@dataclass(frozen=True, slots=True)
class WorkerState:
    """What the canonical event stream knows about one worker."""

    worker_id: str
    worker_generation: int
    lease_count: int = 0
    slot_id: str | None = None

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "WorkerState":
        return cls(
            worker_id=str(document["worker_id"]),
            worker_generation=int(document.get("worker_generation", 1)),
            lease_count=int(document.get("lease_count", 0)),
            slot_id=document.get("slot_id"),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "worker_generation": self.worker_generation,
            "lease_count": self.lease_count,
            "slot_id": self.slot_id,
        }


@dataclass(frozen=True, slots=True)
class CampaignReducerState:
    """The campaign state the reducer derives from one committed event stream.

    ``runtime_identity_sha256`` is ``None`` for a layout that does not publish one. The macOS
    campaign journal starts with ``CAMPAIGN_STARTED`` carrying ``campaign_id``/``batch_id`` only,
    and inventing an identity hash for it would be a fabricated fact; the field stays null and is
    never presented as an observed runtime identity.
    """

    campaign_id: str
    batch_id: str
    runtime_identity_sha256: str | None
    config_sha256: str | None
    points: Mapping[str, PointState] = field(
        default_factory=lambda: MappingProxyType({})
    )
    attempts: Mapping[str, AttemptState] = field(
        default_factory=lambda: MappingProxyType({})
    )
    workers: Mapping[str, WorkerState] = field(
        default_factory=lambda: MappingProxyType({})
    )
    batch_business_terminal: str | None = None
    batch_infrastructure_terminal: str | None = None
    batch_cleanup_complete: bool = False
    recovery_fence: bool = False
    last_sequence: int = 0
    last_event_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", MappingProxyType(dict(self.points)))
        object.__setattr__(self, "attempts", MappingProxyType(dict(self.attempts)))
        object.__setattr__(self, "workers", MappingProxyType(dict(self.workers)))

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "CampaignReducerState":
        return cls(
            campaign_id=str(document["campaign_id"]),
            batch_id=str(document["batch_id"]),
            runtime_identity_sha256=_optional_hash(document.get("runtime_identity_sha256")),
            config_sha256=_optional_hash(document.get("config_sha256")),
            points={
                point_id: PointState.from_document(point)
                for point_id, point in dict(document.get("points", {})).items()
            },
            attempts={
                attempt_id: AttemptState.from_document(attempt)
                for attempt_id, attempt in dict(document.get("attempts", {})).items()
            },
            workers={
                worker_id: WorkerState.from_document(worker)
                for worker_id, worker in dict(document.get("workers", {})).items()
            },
            batch_business_terminal=document.get("batch_business_terminal"),
            batch_infrastructure_terminal=document.get("batch_infrastructure_terminal"),
            batch_cleanup_complete=bool(document.get("batch_cleanup_complete", False)),
            recovery_fence=bool(document.get("recovery_fence", False)),
            last_sequence=int(document.get("last_sequence", 0)),
            last_event_sha256=document.get("last_event_sha256"),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "config_sha256": self.config_sha256,
            "points": {
                point_id: self.points[point_id].as_document()
                for point_id in sorted(self.points)
            },
            "attempts": {
                attempt_id: self.attempts[attempt_id].as_document()
                for attempt_id in sorted(self.attempts)
            },
            "workers": {
                worker_id: self.workers[worker_id].as_document()
                for worker_id in sorted(self.workers)
            },
            "batch_business_terminal": self.batch_business_terminal,
            "batch_infrastructure_terminal": self.batch_infrastructure_terminal,
            "batch_cleanup_complete": self.batch_cleanup_complete,
            "recovery_fence": self.recovery_fence,
            "last_sequence": self.last_sequence,
            "last_event_sha256": self.last_event_sha256,
        }


class CanonicalCampaignReducer:
    """Pure reducer: the returned state is new, the state passed in is never modified.

    ``identity_required`` is the one contract switch. It is ``True`` for the canonical coordinator
    stream, whose ``CAMPAIGN_STARTED`` must carry the runtime identity and the config hash, so the
    guard there is exactly what it always was. A projection source for a layout that publishes no
    runtime identity (the macOS campaign journal) builds its reducer with
    ``identity_required=False``: the event must then either omit the pair or carry well-formed
    hashes, and the state records ``None`` rather than a fabricated value. A published identity
    that *drifts* between two ``CAMPAIGN_STARTED`` events is still refused either way.
    """

    def __init__(self, *, identity_required: bool = True) -> None:
        self.identity_required = bool(identity_required)

    def _identity_pair(self, payload: Mapping[str, object]) -> tuple[str | None, str | None]:
        runtime = payload.get("runtime_identity_sha256")
        config = payload.get("config_sha256")
        if self.identity_required:
            return (
                _require_sha256("runtime_identity_sha256", runtime),
                _require_sha256("config_sha256", config),
            )
        return (
            None if runtime is None else _require_sha256("runtime_identity_sha256", runtime),
            None if config is None else _require_sha256("config_sha256", config),
        )

    def apply(self, state: CampaignReducerState | None, event) -> CampaignReducerState:
        event_type = getattr(event, "type", None)
        payload = getattr(event, "payload", None)
        sequence = getattr(event, "sequence", None)
        event_hash = getattr(event, "frame_sha256", None)
        batch_id = getattr(event, "batch_id", None)
        if not isinstance(event_type, str) or not event_type:
            raise ReducerError("REDUCER_EVENT_INVALID", "type")
        if not isinstance(payload, Mapping):
            raise ReducerError("REDUCER_EVENT_INVALID", "payload")
        if type(sequence) is not int or sequence < 1:
            raise ReducerError("REDUCER_EVENT_INVALID", "sequence")

        if state is None:
            if event_type != "CAMPAIGN_STARTED":
                raise ReducerError("REDUCER_STATE_REQUIRED", event_type)
            return self._start(event, payload, sequence, event_hash)

        if batch_id != state.batch_id:
            raise ReducerError("REDUCER_BATCH_MISMATCH", f"{batch_id!r}")
        if sequence == state.last_sequence:
            if event_hash == state.last_event_sha256:
                return state
            raise ReducerError("REDUCER_SEQUENCE_REGRESSION", f"sequence {sequence}")
        if sequence < state.last_sequence:
            raise ReducerError("REDUCER_SEQUENCE_REGRESSION", f"{sequence} < {state.last_sequence}")

        if state.batch_cleanup_complete:
            raise ReducerError("REDUCER_APPEND_AFTER_TERMINAL", event_type)
        if state.batch_business_terminal is not None and event_type != _FINAL_EVENT:
            raise ReducerError("REDUCER_APPEND_AFTER_TERMINAL", event_type)

        if event_type == "CAMPAIGN_STARTED":
            return self._restart(state, payload, sequence, event_hash)
        if event_type == "WORKER_REGISTERED":
            return self._registered(state, payload, sequence, event_hash)
        if event_type == "POINT_LEASED":
            return self._lease(state, payload, sequence, event_hash)
        if event_type == "ATTEMPT_STARTED":
            return self._attempt(state, payload, sequence, event_hash)
        if event_type == "ATTEMPT_FAILED":
            return self._failed_attempt(state, payload, sequence, event_hash)
        if event_type == "RESULT_COMMITTED":
            return self._result(state, payload, sequence, event_hash)
        if event_type == "POINT_TERMINAL":
            return self._confirm_terminal(state, payload, sequence, event_hash)
        if event_type == _TERMINAL_EVENT:
            return self._batch_terminal(state, payload, sequence, event_hash)
        if event_type == _FINAL_EVENT:
            return replace(
                state,
                batch_cleanup_complete=bool(payload.get("cleanup_complete", True)),
                last_sequence=sequence,
                last_event_sha256=event_hash,
            )
        raise ReducerError("REDUCER_UNKNOWN_EVENT", event_type)

    # -- transitions --------------------------------------------------------------------

    def _start(self, event, payload, sequence, event_hash) -> CampaignReducerState:
        runtime_identity, config_sha256 = self._identity_pair(payload)
        return CampaignReducerState(
            campaign_id=_require_id("campaign_id", payload.get("campaign_id")),
            batch_id=_require_id("batch_id", payload.get("batch_id")),
            runtime_identity_sha256=runtime_identity,
            config_sha256=config_sha256,
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )

    def _restart(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        for field, observed, identity in (
            ("campaign_id", payload.get("campaign_id"), state.campaign_id),
            ("batch_id", payload.get("batch_id"), state.batch_id),
            (
                "runtime_identity_sha256",
                payload.get("runtime_identity_sha256"),
                state.runtime_identity_sha256,
            ),
            ("config_sha256", payload.get("config_sha256"), state.config_sha256),
        ):
            if observed != identity:
                raise ReducerError("REDUCER_IDENTITY_DRIFT", f"{field}={observed!r}")
        return self._advance(state, sequence, event_hash)

    def _advance(self, state, sequence, event_hash) -> CampaignReducerState:
        return replace(state, last_sequence=sequence, last_event_sha256=event_hash)

    def _registered(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        return replace(
            self._advance(state, sequence, event_hash),
            workers=_observe_worker(state, payload, leased=False),
        )

    def _lease(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        point_id = _require_id("point_id", payload.get("point_id"))
        attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
        point = state.points.get(point_id, PointState(point_id=point_id))
        if point.phase is ExecutionPhase.TERMINAL:
            raise ReducerError("REDUCER_ILLEGAL_TRANSITION", f"{point_id} is terminal")
        points = dict(state.points)
        points[point_id] = replace(
            point,
            phase=ExecutionPhase.LEASED,
            attempt_id=attempt_id,
            worker_id=payload.get("worker_id"),
            slot_id=payload.get("slot_id"),
        )
        attempts = dict(state.attempts)
        attempts[attempt_id] = AttemptState(
            point_id=point_id,
            attempt_id=attempt_id,
            lifecycle=ExecutionPhase.LEASED,
            validity=AttemptValidity.VALID,
            infrastructure=InfrastructureOutcome.NONE,
        )
        return replace(
            state,
            points=points,
            attempts=attempts,
            workers=_observe_worker(state, payload, leased=True),
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )

    def _attempt(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        point_id = _require_id("point_id", payload.get("point_id"))
        attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
        attempt = state.attempts.get(attempt_id)
        if attempt is None or attempt.point_id != point_id:
            raise ReducerError("REDUCER_ATTEMPT_WITHOUT_LEASE", attempt_id)
        validity = AttemptValidity(str(payload.get("attempt_validity", "VALID")))
        infrastructure = InfrastructureOutcome(
            str(payload.get("infrastructure_outcome", "NONE"))
        )
        attempts = dict(state.attempts)
        attempts[attempt_id] = replace(
            attempt,
            lifecycle=ExecutionPhase.RUNNING,
            validity=validity,
            infrastructure=infrastructure,
        )
        points = dict(state.points)
        point = state.points.get(point_id, PointState(point_id=point_id))
        # An invalid attempt or an infrastructure failure is not a business outcome: the point
        # status stays UNRUN and only the infrastructure terminal records what happened.
        if validity is AttemptValidity.VALID and infrastructure is InfrastructureOutcome.NONE:
            points[point_id] = replace(point, phase=ExecutionPhase.RUNNING)
        infrastructure_terminal = state.batch_infrastructure_terminal
        if validity is AttemptValidity.INVALID or infrastructure is InfrastructureOutcome.FAILED:
            infrastructure_terminal = "ATTEMPT_INVALID"
        return replace(
            state,
            points=points,
            attempts=attempts,
            batch_infrastructure_terminal=infrastructure_terminal,
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )

    def _result(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        point_id = _require_id("point_id", payload.get("point_id"))
        attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
        result_sha256 = _require_sha256("result_sha256", payload.get("result_sha256"))
        try:
            outcome = PointStatus(str(payload.get("outcome")))
        except ValueError as error:
            raise ReducerError(
                "REDUCER_OUTCOME_INVALID", f"outcome={payload.get('outcome')!r}"
            ) from error
        if outcome not in BUSINESS_OUTCOMES:
            raise ReducerError("REDUCER_OUTCOME_INVALID", f"outcome={outcome.value}")
        point = state.points.get(point_id, PointState(point_id=point_id))
        points = dict(state.points)
        points[point_id] = replace(
            point,
            status=outcome,
            phase=ExecutionPhase.TERMINAL,
            attempt_id=attempt_id,
            result_sha256=result_sha256,
        )
        attempts = dict(state.attempts)
        attempt = state.attempts.get(attempt_id)
        if attempt is not None:
            attempts[attempt_id] = replace(
                attempt,
                lifecycle=ExecutionPhase.TERMINAL,
                validity=AttemptValidity(str(payload.get("attempt_validity", "VALID"))),
                result_sha256=result_sha256,
            )
        return replace(
            state,
            points=points,
            attempts=attempts,
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )

    def _failed_attempt(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        point_id = _require_id("point_id", payload.get("point_id"))
        attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
        reason = _require_id("infrastructure_code", payload.get("infrastructure_code"))
        attempt = state.attempts.get(attempt_id)
        point = state.points.get(point_id)
        if (
            attempt is None or point is None or attempt.point_id != point_id
            or attempt.lifecycle is not ExecutionPhase.RUNNING
            or point.attempt_id != attempt_id or point.result_sha256 is not None
        ):
            raise ReducerError("REDUCER_FAILURE_WITHOUT_ACTIVE_ATTEMPT", attempt_id)
        attempts = dict(state.attempts)
        attempts[attempt_id] = replace(
            attempt, lifecycle=ExecutionPhase.TERMINAL,
            validity=AttemptValidity.INVALID, infrastructure=InfrastructureOutcome.FAILED,
        )
        points = dict(state.points)
        points[point_id] = replace(point, phase=ExecutionPhase.TERMINAL)
        return replace(
            state, attempts=attempts, points=points,
            batch_infrastructure_terminal=reason,
            last_sequence=sequence, last_event_sha256=event_hash,
        )

    def _confirm_terminal(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        point_id = _require_id("point_id", payload.get("point_id"))
        result_sha256 = _require_sha256("result_sha256", payload.get("result_sha256"))
        point = state.points.get(point_id)
        if point is None or point.result_sha256 is None:
            raise ReducerError("REDUCER_TERMINAL_WITHOUT_RESULT", point_id)
        if point.result_sha256 != result_sha256:
            raise ReducerError(
                "REDUCER_TERMINAL_RESULT_MISMATCH",
                f"{result_sha256} != {point.result_sha256}",
            )
        return self._advance(state, sequence, event_hash)

    def _batch_terminal(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        business = payload.get("business_terminal")
        infrastructure = payload.get("infrastructure_terminal")
        points = dict(state.points)
        attempts = dict(state.attempts)
        if infrastructure is not None:
            # A committed infrastructure terminal closes the batch's remaining leases. It does
            # not assert any business outcome for points without a RESULT_COMMITTED event.
            for point_id, point in points.items():
                if point.phase is not ExecutionPhase.TERMINAL:
                    points[point_id] = replace(point, phase=ExecutionPhase.TERMINAL)
            for attempt_id, attempt in attempts.items():
                if attempt.lifecycle is not ExecutionPhase.TERMINAL:
                    attempts[attempt_id] = replace(
                        attempt, lifecycle=ExecutionPhase.TERMINAL,
                        validity=AttemptValidity.INVALID,
                        infrastructure=InfrastructureOutcome.FAILED,
                    )
        return replace(
            state,
            points=points,
            attempts=attempts,
            batch_business_terminal=None if business is None else str(business),
            batch_infrastructure_terminal=(
                state.batch_infrastructure_terminal
                if infrastructure is None
                else str(infrastructure)
            ),
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )


def _observe_worker(
    state: CampaignReducerState, payload: Mapping[str, object], *, leased: bool
) -> Mapping[str, WorkerState]:
    """Record the leasing/registered worker. Canonical events carry no lifecycle enum."""

    worker_id = payload.get("worker_id")
    if not isinstance(worker_id, str) or not worker_id:
        return state.workers
    observed = state.workers.get(worker_id, WorkerState(worker_id=worker_id, worker_generation=1))
    generation = payload.get("worker_generation")
    if type(generation) is not int or generation <= 0:
        generation = observed.worker_generation
    slot_id = payload.get("slot_id")
    workers = dict(state.workers)
    workers[worker_id] = WorkerState(
        worker_id=worker_id,
        worker_generation=generation,
        lease_count=observed.lease_count + (1 if leased else 0),
        slot_id=slot_id if isinstance(slot_id, str) else observed.slot_id,
    )
    return workers


def _worker_state(worker: WorkerState, leased: bool, cleaned_up: bool) -> str:
    """Derive the consumer-facing worker state from canonical facts only."""

    if leased:
        return "EXECUTING"
    if cleaned_up:
        return "STOPPED"
    return "AVAILABLE"


def projection_document(state: CampaignReducerState) -> dict[str, object]:
    """A read-only view of the canonical state for the service's existing consumers.

    Every field is derived from the reducer state - never from a `payload.delta`. The shape keeps
    the keys the fixed-coordinator projection reads: per point status/phase/attempts/terminal/
    active attempt, the leasing worker, the batch business terminal and the cleanup flag.
    """

    attempts_by_point: dict[str, int] = {}
    for attempt in state.attempts.values():
        attempts_by_point[attempt.point_id] = attempts_by_point.get(attempt.point_id, 0) + 1
    points: dict[str, dict[str, object]] = {}
    active_lease: dict[str, tuple[str, str]] = {}
    for point_id in sorted(state.points):
        point = state.points[point_id]
        if point.phase in (ExecutionPhase.LEASED, ExecutionPhase.RUNNING) and point.attempt_id:
            active_lease[point.worker_id or ""] = (point_id, point.attempt_id)
    workers: dict[str, dict[str, object]] = {}
    for worker_id in sorted(state.workers):
        worker = state.workers[worker_id]
        lease = active_lease.get(worker_id)
        workers[worker_id] = {
            "worker_id": worker_id,
            "generation": worker.worker_generation,
            "state": _worker_state(worker, lease is not None, state.batch_cleanup_complete),
            "lease_count": worker.lease_count,
            "slot_id": worker.slot_id,
            "lease": None if lease is None else {"point_id": lease[0], "attempt_id": lease[1]},
        }
    for point_id in sorted(state.points):
        point = state.points[point_id]
        terminal = point.phase is ExecutionPhase.TERMINAL
        active_attempt = (
            point.attempt_id
            if point.phase in (ExecutionPhase.LEASED, ExecutionPhase.RUNNING)
            else None
        )
        points[point_id] = {
            "status": point.status.value,
            "phase": point.phase.value,
            "attempts": attempts_by_point.get(point_id, 0),
            "terminal": terminal,
            "active_attempt": active_attempt,
            "attempt_id": point.attempt_id,
            "result_sha256": point.result_sha256,
            "worker_id": point.worker_id,
            "slot_id": point.slot_id,
        }
    return {
        "points": points,
        "workers": workers,
        "terminal_reason": state.batch_business_terminal,
        "batch_infrastructure_terminal": state.batch_infrastructure_terminal,
        "batch_cleanup_complete": state.batch_cleanup_complete,
        "recovery_fence": state.recovery_fence,
    }
