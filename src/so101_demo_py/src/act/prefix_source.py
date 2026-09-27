"""Broker-local, one-use provenance for a physical observation and exact prefix.

Only a trusted in-process producer may issue a receipt. A receipt is evidence for
the later path proof; it is never a permit or command authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from .contracts import fields, finite, identifier, integer, sha256, validate_action_prefix
from .execution import prefix_sha256


SOURCE_KEYS = ("world", "scene", "contact", "head", "wrist", "arm", "neck")
SOURCE_KINDS = frozenset(("EXPERT_ROUTE", "ACT_POLICY"))
SOURCE_FIELDS = frozenset((
    "session_id", "attempt_id", "reset_epoch", "phase", "physics_step",
    "simulation_time_s", "observation_sha256", "source_received_wall_s",
))


@dataclass(frozen=True, slots=True)
class PrefixSourceReceipt:
    source_kind: str
    source_artifact_sha256: str
    contact_policy_fingerprint: str
    observation_sha256: str
    source_received_wall_s: tuple[tuple[str, float], ...]
    source_phase: str
    physics_step: int
    reset_epoch: int
    owner_ticket: tuple
    prefix_sha256: str
    sequence: int
    prefix_issued_wall_s: float

    @property
    def command_authority(self) -> bool:
        return False


class PrefixSourceAuthority:
    """Issue and consume one broker-private receipt per source step and sequence."""

    def __init__(self, *, ticket_guard: Callable, max_observation_age_s: float,
                 max_prefix_age_s: float, monotonic=time.monotonic):
        if not callable(ticket_guard) or not callable(monotonic):
            raise ValueError("PREFIX_SOURCE_CONFIG_INVALID")
        observation_age = finite(max_observation_age_s)
        prefix_age = finite(max_prefix_age_s)
        if observation_age <= 0 or prefix_age <= 0:
            raise ValueError("PREFIX_SOURCE_CONFIG_INVALID")
        self.ticket_guard = ticket_guard
        self.monotonic = monotonic
        self.max_observation_age_s = observation_age
        self.max_prefix_age_s = prefix_age
        self._lock = threading.RLock()
        self._pending: PrefixSourceReceipt | None = None
        self._issued: set[tuple] = set()
        self._revision = 0

    @staticmethod
    def _ticket(ticket, checked):
        if (not isinstance(ticket, tuple) or len(ticket) != 5
                or integer(ticket[0], minimum=1) != ticket[0]
                or identifier(ticket[1]) != ticket[1]
                or ticket[2] != "act"
                or ticket[3:] != (checked["session_id"], checked["attempt_id"])):
            raise ValueError("PREFIX_SOURCE_OWNER_INVALID")

    @staticmethod
    def _source(source, checked, ticket, *, now_wall_s):
        try:
            fields(source, SOURCE_FIELDS)
            if (source["session_id"] != ticket[3]
                    or source["attempt_id"] != ticket[4]
                    or integer(source["reset_epoch"], minimum=1)
                       != source["reset_epoch"]
                    or integer(source["physics_step"], minimum=1)
                       != source["physics_step"]
                    or identifier(source["phase"]) != source["phase"]
                    or finite(source["simulation_time_s"], nonnegative=True)
                       != checked["observation_time_s"]):
                raise ValueError("scope")
            digest = sha256(source["observation_sha256"])
            times = source["source_received_wall_s"]
            if type(times) is not dict or set(times) != set(SOURCE_KEYS):
                raise ValueError("receipts")
            ordered = tuple((key, finite(times[key], nonnegative=True))
                            for key in SOURCE_KEYS)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("PREFIX_SOURCE_SCOPE_INVALID") from error
        if any(received > now_wall_s for _, received in ordered):
            raise ValueError("PREFIX_SOURCE_TIME_INVALID")
        return digest, ordered

    def _guard(self, ticket):
        try:
            self.ticket_guard(ticket)
        except (KeyError, TypeError, ValueError, PermissionError) as error:
            raise PermissionError("PREFIX_SOURCE_OWNER_CHANGED") from error

    def issue(self, *, ticket, prefix, source, source_kind,
              source_artifact_sha256, contact_policy_fingerprint,
              output_received_wall_s=None) -> PrefixSourceReceipt:
        checked = validate_action_prefix(prefix)
        self._ticket(ticket, checked)
        self._guard(ticket)
        with self._lock:
            revision = self._revision
        if type(source_kind) is not str or source_kind not in SOURCE_KINDS:
            raise ValueError("PREFIX_SOURCE_KIND_INVALID")
        artifact = sha256(source_artifact_sha256)
        contact_policy = sha256(contact_policy_fingerprint)
        now = finite(self.monotonic(), nonnegative=True)
        observation, received = self._source(source, checked, ticket,
                                             now_wall_s=now)
        if not now - min(value for _, value in received) < self.max_observation_age_s:
            raise ValueError("PREFIX_OBSERVATION_STALE")
        if source_kind == "EXPERT_ROUTE":
            if output_received_wall_s is not None:
                raise ValueError("PREFIX_OUTPUT_TIME_UNEXPECTED")
            issued = now
        else:
            if output_received_wall_s is None:
                raise ValueError("PREFIX_OUTPUT_TIME_REQUIRED")
            issued = finite(output_received_wall_s, nonnegative=True)
            if issued < max(value for _, value in received) or issued > now:
                raise ValueError("PREFIX_OUTPUT_TIME_INVALID")
        if not now - issued < self.max_prefix_age_s:
            raise ValueError("PREFIX_SOURCE_STALE")
        receipt = PrefixSourceReceipt(
            source_kind=source_kind, source_artifact_sha256=artifact,
            contact_policy_fingerprint=contact_policy,
            observation_sha256=observation, source_received_wall_s=received,
            source_phase=source["phase"], physics_step=source["physics_step"],
            reset_epoch=source["reset_epoch"], owner_ticket=ticket,
            prefix_sha256=prefix_sha256(checked), sequence=checked["sequence"],
            prefix_issued_wall_s=issued,
        )
        key = (ticket, receipt.source_phase, receipt.physics_step,
               receipt.sequence)
        self._guard(ticket)
        with self._lock:
            if revision != self._revision:
                raise PermissionError("PREFIX_SOURCE_REVOKED")
            if key in self._issued:
                raise PermissionError("PREFIX_SOURCE_REPLAY")
            if self._pending is not None:
                raise PermissionError("PREFIX_SOURCE_BUSY")
            self._issued.add(key)
            self._pending = receipt
        return receipt

    def consume(self, *, ticket, prefix, source) -> PrefixSourceReceipt:
        with self._lock:
            receipt = self._pending
            self._pending = None
            revision = self._revision
        if receipt is None:
            raise PermissionError("PREFIX_SOURCE_UNAVAILABLE")
        if ticket != receipt.owner_ticket:
            raise PermissionError("PREFIX_SOURCE_OWNER_CHANGED")
        self._guard(ticket)
        now = finite(self.monotonic(), nonnegative=True)
        if (now < receipt.prefix_issued_wall_s
                or now - min(value for _, value in receipt.source_received_wall_s)
                   >= self.max_observation_age_s
                or now - receipt.prefix_issued_wall_s >= self.max_prefix_age_s):
            raise PermissionError("PREFIX_SOURCE_STALE")
        try:
            checked = validate_action_prefix(prefix)
            self._ticket(ticket, checked)
            observation, received = self._source(source, checked, ticket,
                                                 now_wall_s=now)
            if (prefix_sha256(checked) != receipt.prefix_sha256
                    or checked["sequence"] != receipt.sequence
                    or observation != receipt.observation_sha256
                    or received != receipt.source_received_wall_s
                    or source["phase"] != receipt.source_phase
                    or source["physics_step"] != receipt.physics_step
                    or source["reset_epoch"] != receipt.reset_epoch):
                raise ValueError("changed")
        except (KeyError, TypeError, ValueError) as error:
            raise PermissionError("PREFIX_SOURCE_CHANGED") from error
        self._guard(ticket)
        with self._lock:
            if revision != self._revision:
                raise PermissionError("PREFIX_SOURCE_REVOKED")
        return receipt

    def revoke(self) -> None:
        with self._lock:
            self._pending = None
            self._revision += 1
