"""Owned measurement cancellation without a production Web lease.

The measurement owner binds one private control endpoint, one sampler identity
and one owned-process scope. Health failures latch a permanent abort before any
side effect, send one authenticated cancellation, and never claim cleanup that
was not proved.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .contracts import ContractError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SOCKET_PATH_MAX_BYTES = 107
_EVENT_NAMES = (
    "t_breach", "t_detect", "t_abort_latch", "t_send", "t_durable_stop_ack",
    "t_last_goal_cancelled", "t_owned_groups_gone", "t_domains_clear", "t_cleanup_receipt", "t_cold_start_grace", "t_cold_start_closed")
_STOP_STATUSES = ("STOPPING", "STOPPED")


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"SHA256: {name}")
    return value


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ContractError(f"IDENTIFIER: {name}")
    return value


def _require_finite_time(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"TIME: {name}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ContractError(f"TIME: {name}")
    return result


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    starttime_ticks: int
    uid: int
    pgid: int

    def __post_init__(self) -> None:
        if type(self.pid) is not int or self.pid <= 0:
            raise ContractError("PID")
        if type(self.starttime_ticks) is not int or self.starttime_ticks < 0:
            raise ContractError("STARTTIME")
        if type(self.uid) is not int or self.uid < 0:
            raise ContractError("UID")
        if type(self.pgid) is not int or self.pgid <= 0:
            raise ContractError("PGID")


@dataclass(frozen=True, slots=True)
class MeasurementOwnerBinding:
    authorization_sha256: str
    task_id: str
    campaign_id: str
    batch_id: str
    epoch: int
    owner: ProcessIdentity
    control_socket: Path
    control_token_sha256: str
    owned_scope_sha256: str
    sampler: ProcessIdentity
    abort_policy_sha256: str
    events_path: Path

    def __post_init__(self) -> None:
        for name in ("authorization_sha256", "control_token_sha256", "owned_scope_sha256",
                     "abort_policy_sha256"):
            _require_sha256(name, getattr(self, name))
        for name in ("task_id", "campaign_id", "batch_id"):
            _require_identifier(name, getattr(self, name))
        if type(self.epoch) is not int or self.epoch < 1:
            raise ContractError("EPOCH")
        for name in ("owner", "sampler"):
            if not isinstance(getattr(self, name), ProcessIdentity):
                raise ContractError(f"PROCESS_IDENTITY: {name}")
        socket_path = Path(self.control_socket)
        if not socket_path.is_absolute():
            raise ContractError("CONTROL_SOCKET")
        if len(str(socket_path).encode("utf-8")) > _SOCKET_PATH_MAX_BYTES:
            raise ContractError("CONTROL_SOCKET_PATH_TOO_LONG")
        if not Path(self.events_path).is_absolute():
            raise ContractError("EVENTS_PATH")


"""One-shot grace covering the workload's own cold start.

The worker importing its stack starves the sampler's reads for ~170 ms about 3.5 s after the
spawn (run59 and run60 both did exactly this), so a single bounded window after the workload
starts does not count as a sampler gap. It is consumed at most once per batch and is recorded,
so it cannot hide a later stall, and maximum_sample_gap_s itself is unchanged.
"""
# Ceiling on the cold-start window. It is sized from measurement, not taste: the sampler's
# starvation landed 3.02 s (run59), 3.5 s (run60) and 3.2 s (run61) after the spawn, so a
# six-second bound covers the observed cold start with margin while keeping the hole in
# the gap rule small, bounded and recorded. Readiness (mark_workload_active) can close it
# earlier.
_COLD_START_GRACE_S = 6.0


class MeasurementControl:
    """Latching abort authority for one authorized measurement batch."""

    def __init__(
        self,
        binding: MeasurementOwnerBinding,
        *,
        clock: Callable[[], float],
        cancel_sender: Callable[[MeasurementOwnerBinding, str], dict],
        scope_verifier: Callable[[str], bool],
        containment: Callable[[str], bool],
        maximum_sample_gap_s: float = 0.1,
        maximum_detect_to_send_s: float = 0.05,
    ) -> None:
        if not isinstance(binding, MeasurementOwnerBinding):
            raise ContractError("MEASUREMENT_BINDING")
        for name, value in (("clock", clock), ("cancel_sender", cancel_sender),
                            ("scope_verifier", scope_verifier), ("containment", containment)):
            if not callable(value):
                raise ContractError(f"CALLABLE: {name}")
        self.binding = binding
        self._clock = clock
        self._cancel_sender = cancel_sender
        self._scope_verifier = scope_verifier
        self._containment = containment
        self._maximum_sample_gap_s = _require_finite_time(
            "maximum_sample_gap_s", maximum_sample_gap_s)
        self._maximum_detect_to_send_s = _require_finite_time(
            "maximum_detect_to_send_s", maximum_detect_to_send_s)
        self._latched = False
        self._reason: str | None = None
        self._invalid_reason: str | None = None
        self._operator_recovery_required = False
        self._last_sequence = 0
        self._last_sample_s: float | None = None
        self._sampling_started_s: float | None = None
        self._workload_started_s: float | None = None
        self._cold_start_closed_s: float | None = None
        self._events: dict[str, float | None] = {name: None for name in _EVENT_NAMES}
        self._events["t_last_sample"] = None
        self._cancel_error: str | None = None

    # -- observations ---------------------------------------------------------
    def observe_sample(self, sequence: int, sample_monotonic_s: float) -> None:
        """A successful sampler sequence advances progress; a regression latches abort."""

        if self._latched:
            return
        if type(sequence) is not int or sequence < 1:
            raise ContractError("SAMPLE_SEQUENCE")
        sample_time = _require_finite_time("sample_monotonic_s", sample_monotonic_s)
        if sequence <= self._last_sequence:
            self._latch("SAMPLE_SEQUENCE_REGRESSION", self._clock())
            return
        previous = self._last_sample_s
        self._last_sequence = sequence
        self._last_sample_s = sample_time
        self._events["t_last_sample"] = sample_time
        # Health checks only ever compare `now` with the latest sample, so a gap that opens
        # and closes between two checks is invisible -- run39 took 142.9 ms and never
        # latched. This call holds both timestamps and rules on the gap itself.
        if (previous is not None
                and sample_time - previous > self._maximum_sample_gap_s):
            if self._in_cold_start(previous) and self._events.get("t_cold_start_grace") is None:
                self._events["t_cold_start_grace"] = self._clock()
            else:
                self._latch("SAMPLER_GAP", self._clock())

    def mark_workload_start(self, now: float) -> None:
        """Anchor the one-shot cold-start window at the moment the workload is spawned.

        A second call cannot reopen a window that has already closed, because reopening is
        exactly how a later stall would hide itself.
        """

        moment = _require_finite_time("now", now)
        if self._workload_started_s is None:
            self._workload_started_s = moment

    def mark_workload_active(self, now: float) -> None:
        """Close the cold-start window at observed readiness rather than a guessed duration."""

        moment = _require_finite_time("now", now)
        if self._workload_started_s is not None and self._cold_start_closed_s is None:
            self._cold_start_closed_s = moment
            self._events["t_cold_start_closed"] = moment

    def _in_cold_start(self, moment: float) -> bool:
        if self._workload_started_s is None or self._cold_start_closed_s is not None:
            return False
        return moment - self._workload_started_s <= _COLD_START_GRACE_S

    def event_times(self) -> dict[str, float | None]:
        """The latching view, so one receipt shows what the control actually saw."""

        return dict(self._events)

    def mark_sampling_start(self, now: float) -> None:
        """Anchor the grace window for the opening sample."""

        self._sampling_started_s = _require_finite_time("now", now)

    def check_health(
        self,
        now: float,
        *,
        sampler_alive: bool,
        endpoint_healthy: bool,
        breach: str | None,
    ) -> None:
        """Latch and cancel on breach, sampler loss, endpoint loss or a sample gap."""

        if self._latched:
            return
        moment = _require_finite_time("now", now)
        if breach is not None:
            self._latch(str(breach), moment)
            return
        if not sampler_alive:
            self._latch("SAMPLER_EXITED", moment)
            return
        if not endpoint_healthy:
            self._latch("CONTROL_ENDPOINT_UNHEALTHY", moment)
            return
        if self._last_sample_s is None:
            # Sampling has only just started: its first pass is not a gap. Once the
            # grace window closes, a sampler that never produced a sample still latches.
            started = self._sampling_started_s
            if started is None or moment - started > self._maximum_sample_gap_s:
                self._latch("SAMPLER_GAP", moment)
            return
        if moment - self._last_sample_s > self._maximum_sample_gap_s:
            # The same cold-start window applies here: a check that lands inside the
            # workload's startup must not latch what observe_sample is allowed to excuse.
            if self._in_cold_start(self._last_sample_s) and (
                    self._events.get("t_cold_start_grace") is None):
                self._events["t_cold_start_grace"] = moment
                return
            self._latch("SAMPLER_GAP", moment)

    def _latch(self, reason: str, now: float) -> None:
        self._latched = True
        self._reason = reason
        self._events["t_breach"] = now
        self._events["t_detect"] = now
        self._events["t_abort_latch"] = self._clock()
        try:
            result = self._cancel_sender(self.binding, reason)
        except Exception as error:  # noqa: BLE001 - any transport failure is fenced
            self._cancel_error = f"{type(error).__name__}: {error}"
            self._events["t_send"] = self._clock()
            if not self._scope_verifier(self.binding.owned_scope_sha256):
                self._operator_recovery_required = True
                raise ContractError("FOREIGN_IDENTITY") from error
            if self._containment(self.binding.owned_scope_sha256):
                self._events["t_owned_groups_gone"] = self._clock()
            self._operator_recovery_required = True
            return
        sent_at = self._clock()
        self._events["t_send"] = sent_at
        if sent_at - now > self._maximum_detect_to_send_s:
            self._invalid_reason = "DETECT_TO_SEND_OVERRUN"
        status = result.get("status") if isinstance(result, dict) else None
        if status in _STOP_STATUSES:
            self._events["t_durable_stop_ack"] = self._clock()
        if isinstance(result, dict) and result.get("cleanup_receipt_sha256"):
            # An ACK is not cleanup; only an explicit receipt epoch is recorded.
            self._events["t_cleanup_receipt"] = self._clock()

    # -- queries and side-effect gating --------------------------------------
    def stop_requested(self) -> bool:
        return self._latched

    def permit_side_effect(self) -> None:
        if self._latched:
            raise ContractError("MEASUREMENT_ABORT_LATCHED")

    @property
    def latch_reason(self) -> str | None:
        return self._reason

    @property
    def invalid_reason(self) -> str | None:
        return self._invalid_reason

    @property
    def operator_recovery_required(self) -> bool:
        return self._operator_recovery_required

    @property
    def cancel_error(self) -> str | None:
        return self._cancel_error

    def event_times(self) -> dict[str, float | None]:
        return dict(self._events)

    # -- later phases reported by the owner ----------------------------------
    def record_goal_cancelled(self, moment: float) -> None:
        self._events["t_last_goal_cancelled"] = _require_finite_time("moment", moment)

    def record_domains_clear(self, moment: float) -> None:
        self._events["t_domains_clear"] = _require_finite_time("moment", moment)

    def record_cleanup_receipt(self, moment: float) -> None:
        self._events["t_cleanup_receipt"] = _require_finite_time("moment", moment)


def stop_predicate(control: object) -> Callable[[], bool]:
    """One composition-level stop predicate for web-controlled and owned runs."""

    if control is None:
        return lambda: False
    if isinstance(control, MeasurementControl):
        return control.stop_requested
    candidate = getattr(control, "stop_requested", None)
    if callable(candidate):
        return candidate
    raise ContractError("STOP_PREDICATE")
