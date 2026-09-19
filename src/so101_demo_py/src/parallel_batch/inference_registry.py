"""The Coordinator's local, one-time inference request registry.

The v4 control channel carries no token, generation or lease (design section 7.2), so this
registry is the whole admission mechanism for inference results. It has to be exactly right:

* a `request_id` is opaque and never reused inside a campaign;
* registration atomically binds the slot, point, attempt, model, input-snapshot SHA, deadline and
  the current owned Broker's PID plus birth identity. Those bindings live only here and are never
  sent to the Broker;
* a successful consume removes the binding immediately, so a late or duplicate result cannot be
  admitted a second time;
* consume, cancel and the expiry sweep share one lock boundary, so a result and a cancellation can
  never both win;
* replacing the Broker invalidates every binding to the old identity at once.

This module deliberately does not decide robot safety. The Coordinator state machine still checks
the active point, operation order, controller state and result completeness; the registry only
decides whether a result is *the* result for *this* request.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Mapping

#: Binding states. Only PENDING may be consumed.
PENDING = "PENDING"
CONSUMED = "CONSUMED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"
INVALIDATED = "INVALIDATED"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")

#: A campaign can only have this many results outstanding at once. It is a bound on the
#: Coordinator's own memory, not a per-N resource budget.
DEFAULT_CAPACITY = 32


class RegistryError(RuntimeError):
    """A registry contract failed. The caller must not admit the result."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.match(value):
        raise RegistryError(name, repr(value))
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RegistryError(name, repr(value))
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.match(value):
        raise RegistryError(name, repr(value))
    return value


@dataclass(frozen=True)
class InferenceBinding:
    """One registered request. Nothing here is ever transmitted to the Broker."""

    request_id: str
    campaign_id: str
    slot_id: str
    point_id: str
    attempt: int
    model_id: str
    input_sha256: str
    deadline_monotonic_ns: int
    broker_pid: int
    broker_birth_identity: int
    registered_monotonic_s: float
    state: str = PENDING


@dataclass(frozen=True)
class RegistryEvent:
    """An append-only record of one decision, for evidence."""

    request_id: str
    reason: str
    monotonic_s: float
    detail: str = ""


@dataclass(frozen=True)
class ConsumeDecision:
    """The answer to "may this result be used?". Refusals carry the exact reason."""

    accepted: bool
    reason: str
    binding: InferenceBinding | None = None
    detail: str = ""


class InferenceRegistry:
    """The campaign's one-time request table. One instance per campaign, never shared."""

    def __init__(self, *, campaign_id: str, capacity: int = DEFAULT_CAPACITY,
                 clock=time.monotonic) -> None:
        self.campaign_id = _identifier("CAMPAIGN_ID", campaign_id)
        self.capacity = _positive_int("CAPACITY", capacity)
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: dict[str, InferenceBinding] = {}
        self._events: list[RegistryEvent] = []
        self._seen: set[str] = set()

    # -- registration --------------------------------------------------------------------

    def register_request(self, *, request_id: str, slot_id: str, point_id: str, attempt: int,
                         model_id: str, input_sha256: str, deadline_monotonic_ns: int,
                         broker_pid: int, broker_birth_identity: int) -> InferenceBinding:
        """Atomically bind a new opaque request id to its whole context."""

        request_id = _identifier("REQUEST_ID", request_id)
        slot_id = _identifier("SLOT_ID", slot_id)
        point_id = _identifier("POINT_ID", point_id)
        model_id = _identifier("MODEL_ID", model_id)
        attempt = _positive_int("ATTEMPT", attempt)
        input_sha256 = _sha256("INPUT_SHA256", input_sha256)
        broker_pid = _positive_int("BROKER_PID", broker_pid)
        broker_birth_identity = _positive_int("BROKER_BIRTH_IDENTITY", broker_birth_identity)
        if isinstance(deadline_monotonic_ns, bool) or not isinstance(
                deadline_monotonic_ns, int) or deadline_monotonic_ns <= 0:
            raise RegistryError("DEADLINE", repr(deadline_monotonic_ns))

        with self._lock:
            if request_id in self._seen:
                raise RegistryError("REQUEST_DUPLICATE", request_id)
            if len(self._pending) >= self.capacity:
                raise RegistryError(
                    "REGISTRY_CAPACITY", f"{len(self._pending)}/{self.capacity} outstanding")
            binding = InferenceBinding(
                request_id=request_id, campaign_id=self.campaign_id, slot_id=slot_id,
                point_id=point_id, attempt=attempt, model_id=model_id,
                input_sha256=input_sha256, deadline_monotonic_ns=deadline_monotonic_ns,
                broker_pid=broker_pid, broker_birth_identity=broker_birth_identity,
                registered_monotonic_s=self._clock(), state=PENDING,
            )
            self._pending[request_id] = binding
            self._seen.add(request_id)
            return binding

    # -- one-time consume ----------------------------------------------------------------

    def consume_result(self, request_id: str, *, output_sha256: str | None = None,
                       input_sha256: str | None = None, broker_pid: int | None = None,
                       broker_birth_identity: int | None = None) -> ConsumeDecision:
        """Decide whether one result may be admitted. Only the first success is admitted."""

        if not isinstance(request_id, str) or not request_id:
            return ConsumeDecision(False, "REQUEST_UNKNOWN", detail=repr(request_id))
        if output_sha256 is not None:
            _sha256("OUTPUT_SHA256", output_sha256)
        if input_sha256 is not None:
            _sha256("INPUT_SHA256", input_sha256)

        with self._lock:
            binding = self._pending.get(request_id)
            if binding is None:
                reason = self._terminal_reason(request_id)
                return ConsumeDecision(False, reason)
            if self._clock() > binding.deadline_monotonic_ns / 1_000_000_000:
                self._pending.pop(request_id, None)
                self._events.append(RegistryEvent(request_id, EXPIRED, self._clock(),
                                                  "deadline passed before the result arrived"))
                return ConsumeDecision(False, EXPIRED, binding=binding)
            if input_sha256 is not None and input_sha256 != binding.input_sha256:
                self._events.append(RegistryEvent(
                    request_id, "SNAPSHOT_MISMATCH", self._clock(),
                    f"binding {binding.input_sha256} != result {input_sha256}"))
                return ConsumeDecision(False, "SNAPSHOT_MISMATCH", binding=binding)
            if broker_pid is not None and broker_pid != binding.broker_pid:
                self._events.append(RegistryEvent(
                    request_id, "BROKER_IDENTITY_MISMATCH", self._clock(),
                    f"binding pid {binding.broker_pid} != result pid {broker_pid}"))
                return ConsumeDecision(False, "BROKER_IDENTITY_MISMATCH", binding=binding)
            if broker_birth_identity is not None and \
                    broker_birth_identity != binding.broker_birth_identity:
                self._events.append(RegistryEvent(
                    request_id, "BROKER_IDENTITY_MISMATCH", self._clock(),
                    f"binding birth {binding.broker_birth_identity} != result "
                    f"birth {broker_birth_identity}"))
                return ConsumeDecision(False, "BROKER_IDENTITY_MISMATCH", binding=binding)

            self._pending.pop(request_id, None)
            consumed = InferenceBinding(**{**binding.__dict__, "state": CONSUMED})
            self._events.append(RegistryEvent(request_id, CONSUMED, self._clock(),
                                              f"output {output_sha256 or 'unspecified'}"))
            return ConsumeDecision(True, CONSUMED, binding=consumed)

    def _terminal_reason(self, request_id: str) -> str:
        """Why an absent binding is absent. Never guessed: read from the event log."""

        for event in reversed(self._events):
            if event.request_id == request_id:
                if event.reason == CONSUMED:
                    return "REQUEST_ALREADY_CONSUMED"
                if event.reason == CANCELLED:
                    return "REQUEST_CANCELLED"
                if event.reason == EXPIRED:
                    return EXPIRED
                if event.reason == INVALIDATED:
                    return "REQUEST_INVALIDATED"
                return event.reason
        return "REQUEST_UNKNOWN"

    # -- cancel, sweep, invalidate -------------------------------------------------------

    def cancel_request(self, request_id: str, *, reason: str) -> InferenceBinding:
        """Release a pending binding. Cancelling twice is allowed; unknown is not."""

        with self._lock:
            binding = self._pending.pop(request_id, None)
            if binding is None:
                if request_id in self._seen:
                    return InferenceBinding(**{**self._last_binding(request_id).__dict__,
                                               "state": CANCELLED})
                raise RegistryError("REQUEST_UNKNOWN", request_id)
            self._events.append(RegistryEvent(request_id, CANCELLED, self._clock(), reason))
            return InferenceBinding(**{**binding.__dict__, "state": CANCELLED})

    def _last_binding(self, request_id: str) -> InferenceBinding:
        for event in reversed(self._events):
            if event.request_id == request_id:
                return InferenceBinding(
                    request_id=request_id, campaign_id=self.campaign_id, slot_id="-",
                    point_id="-", attempt=1, model_id="-", input_sha256="0" * 64,
                    deadline_monotonic_ns=1, broker_pid=1, broker_birth_identity=1,
                    registered_monotonic_s=event.monotonic_s, state=event.reason,
                )
        raise RegistryError("REQUEST_UNKNOWN", request_id)

    def cancel_request_safe(self, request_id: str, *, reason: str = "cancelled") -> bool:
        """Cancel if the request is pending. Returns whether it was removed, never raises.

        The recovery path needs a yes/no answer rather than an exception: it must be able to ask
        "is this request still ours to remove?" without treating an already-terminal request as an
        error.
        """

        with self._lock:
            binding = self._pending.pop(request_id, None)
            if binding is None:
                return False
            self._events.append(RegistryEvent(request_id, CANCELLED, self._clock(), reason))
            return True

    def sweep_expired(self) -> tuple[InferenceBinding, ...]:
        """Release every binding whose deadline has passed, in registration order."""

        now = self._clock()
        released: list[InferenceBinding] = []
        with self._lock:
            for request_id, binding in sorted(self._pending.items(),
                                              key=lambda item: item[1].registered_monotonic_s):
                if now > binding.deadline_monotonic_ns / 1_000_000_000:
                    self._pending.pop(request_id, None)
                    self._events.append(RegistryEvent(request_id, EXPIRED, now,
                                                      "released by the expiry sweep"))
                    released.append(InferenceBinding(**{**binding.__dict__, "state": EXPIRED}))
        return tuple(released)

    def invalidate_broker(self, *, broker_pid: int, broker_birth_identity: int
                          ) -> tuple[str, ...]:
        """Release every binding to one Broker identity, once, in a single lock boundary."""

        broker_pid = _positive_int("BROKER_PID", broker_pid)
        broker_birth_identity = _positive_int("BROKER_BIRTH_IDENTITY", broker_birth_identity)
        invalidated: list[str] = []
        with self._lock:
            for request_id, binding in sorted(self._pending.items()):
                if (binding.broker_pid, binding.broker_birth_identity) != (
                        broker_pid, broker_birth_identity):
                    continue
                self._pending.pop(request_id, None)
                self._events.append(RegistryEvent(
                    request_id, INVALIDATED, self._clock(),
                    f"broker {broker_pid}/{broker_birth_identity} was replaced"))
                invalidated.append(request_id)
        return tuple(invalidated)

    # -- inspection ----------------------------------------------------------------------

    def pending(self) -> tuple[InferenceBinding, ...]:
        with self._lock:
            return tuple(sorted(self._pending.values(),
                                key=lambda item: item.registered_monotonic_s))

    def history(self) -> tuple[RegistryEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def binding_for(self, request_id: str) -> InferenceBinding | None:
        with self._lock:
            return self._pending.get(request_id)

    def snapshot(self) -> Mapping[str, object]:
        """A JSON-safe view for evidence: outstanding ids, capacity and the event log."""

        with self._lock:
            return {
                "campaign_id": self.campaign_id,
                "capacity": self.capacity,
                "pending": [item.request_id for item in
                            sorted(self._pending.values(),
                                   key=lambda entry: entry.registered_monotonic_s)],
                "events": [
                    {"request_id": event.request_id, "reason": event.reason,
                     "monotonic_s": event.monotonic_s, "detail": event.detail}
                    for event in self._events
                ],
            }
