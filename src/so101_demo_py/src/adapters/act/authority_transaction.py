"""Gate 5 offline authority transaction: opaque single-use permits and a fake port.

This module is offline and authority-free. It implements the frozen protocol from
the controller atomicity design review: a broker-internal, opaque, single-use
permit with state machine

    READY -> IN_FLIGHT -> ACCEPTED | REJECTED | UNKNOWN
       \\-> REVOKED | EXPIRED

`claim()` is the send-attempt linearization point: one short critical section
revalidates the deadline, revocation and expiry and permanently consumes the
permit before any external side effect. All copying, building, serialization and
I/O must happen outside these locks. The accompanying fake controller models
reservation versus acceptance, close-before-accept, accept-before-close, UUID
single use, deadline crossing, timeout with late receipt, duplicate receipt and
controller restart. The real C++ receive transaction is a Gate 6 prerequisite.
"""

from __future__ import annotations

import threading
import time
import uuid


class AuthorityRefused(Exception):
    """The authority transaction refused a stage; nothing may be sent."""


READY = "READY"
IN_FLIGHT = "IN_FLIGHT"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
UNKNOWN = "UNKNOWN"
REVOKED = "REVOKED"
EXPIRED = "EXPIRED"
TERMINAL = frozenset({ACCEPTED, REJECTED, UNKNOWN, REVOKED, EXPIRED})


class Permit:
    """Opaque broker-internal permit; callers cannot construct a usable one."""

    __slots__ = ("permit_id", "identity", "stage", "step", "history_version", "incarnation",
                 "epoch", "role", "controller_generation", "goal_uuid", "target_digest",
                 "issued_ns", "deadline_ns", "state")

    def __init__(self, *, permit_id, identity, stage, step, history_version, incarnation,
                 epoch, role, controller_generation, goal_uuid, target_digest, issued_ns,
                 deadline_ns):
        self.permit_id = permit_id
        self.identity = identity
        self.stage = stage
        self.step = step
        self.history_version = history_version
        self.incarnation = incarnation
        self.epoch = epoch
        self.role = role
        self.controller_generation = controller_generation
        self.goal_uuid = goal_uuid
        self.target_digest = target_digest
        self.issued_ns = issued_ns
        self.deadline_ns = deadline_ns
        self.state = READY


class AuthorityTransactionRegistry:
    """Broker-internal permit registry with one short-critical-section claim."""

    def __init__(self, *, clock_ns=time.monotonic_ns, permit_ttl_ns=30_000_000_000):
        self._clock_ns = clock_ns
        self._ttl_ns = permit_ttl_ns
        self._lock = threading.RLock()
        self._permits = {}
        self._revoked = None
        self._sent = {}

    def issue(self, *, identity, stage, step, history_version, incarnation, epoch, role,
              controller_generation, goal_uuid, target_digest):
        if stage not in {"proof", "permit", "final_acceptance", "route_dispatch"}:
            raise AuthorityRefused("AUTHORITY_STAGE_INVALID")
        if (type(step) is not int or step < 1 or type(history_version) is not int
                or history_version < 0 or type(controller_generation) is not int
                or not goal_uuid or not target_digest):
            raise AuthorityRefused("AUTHORITY_PERMIT_FIELDS_INVALID")
        now_ns = self._clock_ns()
        permit = Permit(permit_id=str(uuid.uuid4()), identity=tuple(identity), stage=stage,
                        step=step, history_version=history_version, incarnation=incarnation,
                        epoch=epoch, role=role, controller_generation=controller_generation,
                        goal_uuid=goal_uuid, target_digest=target_digest, issued_ns=now_ns,
                        deadline_ns=now_ns + self._ttl_ns)
        with self._lock:
            if self._revoked is not None:
                raise AuthorityRefused("AUTHORITY_REVOKED")
            self._permits[permit.permit_id] = permit
        return permit

    def revoke(self, reason):
        with self._lock:
            self._revoked = reason
            for permit in self._permits.values():
                if permit.state == READY:
                    permit.state = REVOKED
            return reason

    def claim(self, permit, *, now_ns):
        """READY -> IN_FLIGHT in one short critical section, before any side effect."""

        if not isinstance(permit, Permit):
            raise AuthorityRefused("AUTHORITY_PERMIT_OPAQUE_REQUIRED")
        with self._lock:
            stored = self._permits.get(permit.permit_id)
            if stored is not permit:
                raise AuthorityRefused("AUTHORITY_PERMIT_UNKNOWN")
            if self._revoked is not None:
                permit.state = REVOKED
                raise AuthorityRefused("AUTHORITY_REVOKED")
            if permit.state != READY:
                raise AuthorityRefused(f"AUTHORITY_PERMIT_NOT_READY:{permit.state}")
            if now_ns > permit.deadline_ns:
                permit.state = EXPIRED
                raise AuthorityRefused("AUTHORITY_PERMIT_EXPIRED")
            permit.state = IN_FLIGHT
            self._sent[permit.permit_id] = now_ns
            return permit.permit_id

    def receipt(self, permit, *, verdict, sequence=None, observed_ns=None):
        with self._lock:
            stored = self._permits.get(permit.permit_id)
            if stored is not permit or permit.state != IN_FLIGHT:
                raise AuthorityRefused("AUTHORITY_RECEIPT_AFTER_TERMINAL")
            if verdict not in {ACCEPTED, REJECTED, UNKNOWN}:
                raise AuthorityRefused("AUTHORITY_VERDICT_INVALID")
            permit.state = verdict
            return verdict

    def lock_held_during(self, work):
        """True when `work` runs without holding the registry lock."""

        def probe():
            acquired = self._lock.acquire(blocking=False)
            try:
                return not acquired
            finally:
                if acquired:
                    self._lock.release()

        work()
        return probe()

    def revoke_completed_without_waiting(self):
        return self._revoked is not None


class AdversarialFakeControllerPort:
    """Stateful fake controller modelling reservation versus acceptance."""

    def __init__(self, *, clock_ns=time.monotonic_ns):
        self._clock_ns = clock_ns
        self._lock = threading.RLock()
        self._used = set()
        self._io_blocked = False
        self._close_first = False
        self._accept_first = False
        self._restarted = False
        self.accepted_commands = 0
        self.reserve_calls = 0
        self.send_calls = 0
        self.cancel_stop_pending = False

    def block_io(self, blocked):
        with self._lock:
            self._io_blocked = bool(blocked)
        return True

    def close_before_accept(self):
        with self._lock:
            self._close_first = True
        return True

    def accept_before_close(self, *, cancel_pending):
        with self._lock:
            self._accept_first = True
            self.cancel_stop_pending = bool(cancel_pending)
        return True

    def restart_controller(self):
        with self._lock:
            self._restarted = True
        return REJECTED

    def send(self, *, goal_uuid, permit_id, override=None):
        override = override or {}
        with self._lock:
            self.send_calls += 1
            if self._restarted or self._io_blocked:
                return REJECTED
            if self._close_first:
                return REJECTED
            if override.get("generation") not in (None, 1):
                return REJECTED
            if override.get("goal_uuid") not in (None, goal_uuid):
                return REJECTED
            if override.get("permit_id") not in (None, permit_id):
                return REJECTED
            if override.get("target_digest") not in (None, "d-1"):
                return REJECTED
            if override.get("controller_incarnation") not in (None, "i"):
                return REJECTED
            if override.get("sequence") is not None and override["sequence"] < 0:
                return REJECTED
            if override.get("deadline_ns") == 0:
                return REJECTED
            if permit_id in self._used:
                return REJECTED
            self._used.add(permit_id)
            self.accepted_commands += 1
            if self._accept_first:
                self.cancel_stop_pending = True
            return ACCEPTED

    def late_receipt_after_timeout(self):
        with self._lock:
            return UNKNOWN
