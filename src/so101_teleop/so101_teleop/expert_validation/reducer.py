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


@dataclass(frozen=True, slots=True)
class AttemptState:
    point_id: str
    attempt_id: str
    lifecycle: ExecutionPhase
    validity: AttemptValidity
    infrastructure: InfrastructureOutcome
    result_sha256: str | None = None

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

    def as_document(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "status": self.status.value,
            "phase": self.phase.value,
            "attempt_id": self.attempt_id,
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True, slots=True)
class CampaignReducerState:
    campaign_id: str
    batch_id: str
    runtime_identity_sha256: str
    config_sha256: str
    points: Mapping[str, PointState] = field(
        default_factory=lambda: MappingProxyType({})
    )
    attempts: Mapping[str, AttemptState] = field(
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
            "batch_business_terminal": self.batch_business_terminal,
            "batch_infrastructure_terminal": self.batch_infrastructure_terminal,
            "batch_cleanup_complete": self.batch_cleanup_complete,
            "recovery_fence": self.recovery_fence,
            "last_sequence": self.last_sequence,
            "last_event_sha256": self.last_event_sha256,
        }


class CanonicalCampaignReducer:
    """Pure reducer: the returned state is new, the state passed in is never modified."""

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
            return self._advance(state, sequence, event_hash)
        if event_type == "POINT_LEASED":
            return self._lease(state, payload, sequence, event_hash)
        if event_type == "ATTEMPT_STARTED":
            return self._attempt(state, payload, sequence, event_hash)
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
        return CampaignReducerState(
            campaign_id=_require_id("campaign_id", payload.get("campaign_id")),
            batch_id=_require_id("batch_id", payload.get("batch_id")),
            runtime_identity_sha256=_require_sha256(
                "runtime_identity_sha256", payload.get("runtime_identity_sha256")
            ),
            config_sha256=_require_sha256("config_sha256", payload.get("config_sha256")),
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

    def _lease(self, state, payload, sequence, event_hash) -> CampaignReducerState:
        point_id = _require_id("point_id", payload.get("point_id"))
        attempt_id = _require_id("attempt_id", payload.get("attempt_id"))
        point = state.points.get(point_id, PointState(point_id=point_id))
        if point.phase is ExecutionPhase.TERMINAL:
            raise ReducerError("REDUCER_ILLEGAL_TRANSITION", f"{point_id} is terminal")
        points = dict(state.points)
        points[point_id] = replace(
            point, phase=ExecutionPhase.LEASED, attempt_id=attempt_id
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
        return replace(
            state,
            batch_business_terminal=None if business is None else str(business),
            batch_infrastructure_terminal=(
                state.batch_infrastructure_terminal
                if infrastructure is None
                else str(infrastructure)
            ),
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )
