"""Gate 5 offline authority transaction: private immutable permits, opaque handles.

Offline and authority-free. Implements the frozen protocol: the registry keeps
private immutable records; callers receive only an opaque handle exposing an
identifier. `claim()` uses the registry's **own** clock, binds to the real
admission identity and the history-owned O(1) commit receipt, and consumes the
permit in one short critical section before any external side effect. Receipts
are validated field by field; timeouts, late or duplicate receipts and restarts
never revive a permit. The real C++ receive transaction is a Gate 6 prerequisite.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field


class AuthorityRefused(Exception):
    """The transaction refused the stage; nothing may be sent."""


READY, IN_FLIGHT, ACCEPTED, REJECTED, UNKNOWN, REVOKED, EXPIRED = (
    "READY", "IN_FLIGHT", "ACCEPTED", "REJECTED", "UNKNOWN", "REVOKED", "EXPIRED")
TERMINAL = frozenset({ACCEPTED, REJECTED, UNKNOWN, REVOKED, EXPIRED})
FIXED_STAGES = ("sample", "proof", "permit", "route_dispatch", "final_acceptance")
RECEIPT_FIELDS = ("protocol_version", "permit_id", "goal_uuid", "role", "generation",
                  "target_digest", "controller_incarnation", "controller_boot_incarnation",
                  "broker_incarnation", "session_id", "deadline_ns", "clock_domain",
                  "claim_monotonic_ns", "verdict", "sequence", "observed_ns")


@dataclass(frozen=True)
class _Record:
    permit_id: str
    identity: tuple
    stage: str
    step: int
    history_version: int
    incarnation: str
    epoch: int
    role: str
    controller_incarnation: str
    controller_generation: int
    goal_uuid: str
    target_digest: str
    issued_ns: int
    deadline_ns: int


class PermitHandle:
    """Opaque handle: only the identifier is readable, nothing is settable."""

    __slots__ = ("_permit_id",)

    def __init__(self, permit_id):
        object.__setattr__(self, "_permit_id", permit_id)

    @property
    def permit_id(self):
        return self._permit_id

    def __setattr__(self, name, value):
        raise AuthorityRefused("AUTHORITY_HANDLE_IMMUTABLE")


@dataclass(frozen=True)
class ClaimReceipt:
    permit_id: str
    identity: tuple
    stage: str
    step: int
    history_version: int
    incarnation: str
    epoch: int
    commit_monotonic_ns: int
    selected_age_ns: int
    deadline_ns: int


class AuthorityTransactionRegistry:
    """Private registry; callers never see a mutable record."""

    def __init__(self, *, clock_ns=time.monotonic_ns, permit_ttl_ns=30_000_000_000,
                 admission=None, selected_max_age_ns=None, history=None, port=None):
        if type(permit_ttl_ns) is not int or permit_ttl_ns < 1:
            raise AuthorityRefused("AUTHORITY_TTL_INVALID")
        self._clock_ns = clock_ns
        self._ttl_ns = permit_ttl_ns
        self._admission = admission
        self._selected_max_age_ns = selected_max_age_ns
        self._history = history
        self._admission = admission
        self._port = port
        self._lock = threading.RLock()
        self._records = {}
        self._states = {}
        self._terminal_reasons = {}
        self._claim_boot = {}
        self._sealed = False
        self._revoked = None

    # ---------------------------------------------------------------- issuing
    def issue_handle(self, *, identity, stage, step, history_version, incarnation, epoch, role,
                     controller_generation, goal_uuid, target_digest, controller_incarnation):
        if stage not in FIXED_STAGES:
            raise AuthorityRefused("AUTHORITY_STAGE_INVALID")
        if (type(step) is not int or step < 1 or type(history_version) is not int
                or history_version < 0 or type(epoch) is not int or epoch < 1
                or type(controller_generation) is not int or controller_generation < 0
                or not isinstance(incarnation, str) or not incarnation
                or not isinstance(controller_incarnation, str) or not controller_incarnation
                or not goal_uuid or not target_digest or role not in ("arm", "gripper", "neck")):
            raise AuthorityRefused("AUTHORITY_PERMIT_FIELDS_INVALID")
        now_ns = self._clock_ns()
        record = _Record(permit_id=str(uuid.uuid4()), identity=tuple(identity), stage=stage,
                         step=step, history_version=history_version, incarnation=incarnation,
                         epoch=epoch, role=role, controller_incarnation=controller_incarnation,
                         controller_generation=controller_generation,
                         goal_uuid=goal_uuid, target_digest=target_digest, issued_ns=now_ns,
                         deadline_ns=now_ns + self._ttl_ns)
        with self._lock:
            if self._revoked is not None:
                raise AuthorityRefused("AUTHORITY_REVOKED")
            self._records[record.permit_id] = record
            self._states[record.permit_id] = READY
        return PermitHandle(record.permit_id)

    def revoke(self, reason):
        with self._lock:
            self._revoked = reason
            for permit_id, state in self._states.items():
                if state == READY:
                    self._states[permit_id] = REVOKED
        return reason

    def state_of(self, handle):
        if not isinstance(handle, PermitHandle):
            raise AuthorityRefused("AUTHORITY_HANDLE_REQUIRED")
        with self._lock:
            return self._states.get(handle.permit_id, "UNKNOWN_PERMIT")

    # -------------------------------------------------------------- claiming
    def claim(self, *args, **kwargs):  # pragma: no cover - removed API
        """Legacy claim API: removed, never merely deprecated.

        It accepted caller-substituted admission/history and a caller-supplied
        time. The only supported path is ``claim_bound`` over sealed,
        broker-owned dependencies.
        """

        raise AuthorityRefused("AUTHORITY_LEGACY_CLAIM_REMOVED")

    def claim_bound(self, handle, *, identity, controller_generation, token):
        """Broker-internal claim bound to the live owner, generation and history receipt.

        The admission/history objects are supplied by the broker itself, never by the
        caller. Identity, revocation/retirement state and the controller generation are
        validated before the history commit, and the permit deadline is re-checked with
        the registry clock *after* the commit but still before READY -> IN_FLIGHT.
        """

        if not isinstance(handle, PermitHandle):
            raise AuthorityRefused("AUTHORITY_HANDLE_REQUIRED")
        admission, history, port = self._domain()
        if not hasattr(admission, "claim_guard"):
            raise AuthorityRefused("AUTHORITY_ADMISSION_DOMAIN_REQUIRED")
        with self._lock, admission.claim_context():
            record = self._records.get(handle.permit_id)
            if record is None:
                raise AuthorityRefused("AUTHORITY_PERMIT_UNKNOWN")
            if self._revoked is not None:
                self._states[record.permit_id] = REVOKED
                raise AuthorityRefused("AUTHORITY_REVOKED")
            if self._states[record.permit_id] != READY:
                raise AuthorityRefused(
                    f"AUTHORITY_PERMIT_NOT_READY:{self._states[record.permit_id]}")
            if tuple(identity) != record.identity:
                raise AuthorityRefused("AUTHORITY_OWNER_IDENTITY_MISMATCH")
            if controller_generation != record.controller_generation:
                raise AuthorityRefused("AUTHORITY_CONTROLLER_GENERATION_CHANGED")
            if port is not None:
                # the controller port's *current* armed generation is the authority,
                # not a caller-provided integer that happens to match
                current = port.current_generation()
                if current != record.controller_generation:
                    raise AuthorityRefused("AUTHORITY_CONTROLLER_GENERATION_CHANGED")
            now_ns = self._clock_ns()
            if now_ns > record.deadline_ns:
                self._states[record.permit_id] = EXPIRED
                raise AuthorityRefused("AUTHORITY_PERMIT_EXPIRED")
            try:
                receipt = admission.history_commit_receipt(
                    token=token, step=record.step, max_age_ns=self._selected_max_age_ns)
            except Exception as error:  # noqa: BLE001
                raise AuthorityRefused(f"AUTHORITY_COMMIT_REFUSED:{error}") from error
            try:
                final = admission.history_commit_receipt(
                    token=token, step=record.step, max_age_ns=self._selected_max_age_ns)
            except AuthorityRefused as error:
                raise AuthorityRefused(
                    f"AUTHORITY_HISTORY_CHANGED_IN_BOUNDARY:{error}") from error
            except ValueError as error:
                raise AuthorityRefused(
                    f"AUTHORITY_HISTORY_CHANGED_IN_BOUNDARY:{error}") from error
            if (final["version"] != receipt["version"]
                    or final["incarnation"] != receipt["incarnation"]
                    or final["epoch"] != receipt["epoch"]):
                raise AuthorityRefused("AUTHORITY_HISTORY_CHANGED_IN_BOUNDARY")
            if not admission.owner_is_active():
                self._states[record.permit_id] = REVOKED
                raise AuthorityRefused("AUTHORITY_REVOKED_DURING_COMMIT")
            if receipt["version"] != record.history_version \
                    or receipt["incarnation"] != record.incarnation \
                    or receipt["epoch"] != record.epoch:
                raise AuthorityRefused("AUTHORITY_COMMIT_IDENTITY_CHANGED")
            if self._clock_ns() > record.deadline_ns:
                self._states[record.permit_id] = EXPIRED
                raise AuthorityRefused("AUTHORITY_PERMIT_EXPIRED_AT_COMMIT")
            self._states[record.permit_id] = IN_FLIGHT
            if port is not None and hasattr(port, "boot_incarnation"):
                self._claim_boot[record.permit_id] = port.boot_incarnation()
            return ClaimReceipt(permit_id=record.permit_id, identity=record.identity,
                                stage=record.stage, step=record.step,
                                history_version=receipt["version"],
                                incarnation=receipt["incarnation"], epoch=receipt["epoch"],
                                commit_monotonic_ns=receipt["commit_monotonic_ns"],
                                selected_age_ns=receipt["age_ns"],
                                deadline_ns=record.deadline_ns)

    def bind(self, *, admission=None, history=None, port=None):
        """Broker-only wiring; refused once the domain is sealed."""

        if self._sealed:
            raise AuthorityRefused("AUTHORITY_DOMAIN_SEALED")
        if admission is not None:
            self._admission = admission
        if history is not None:
            self._history = history
        if port is not None:
            self._port = port
        return self

    def seal(self):
        """Freeze the dependency bindings; no further substitution is possible."""

        if self._admission is None or self._history is None or self._port is None:
            raise AuthorityRefused("AUTHORITY_DOMAIN_INCOMPLETE")
        self._sealed = True
        return self

    def _domain(self):
        if not self._sealed:
            raise AuthorityRefused("AUTHORITY_DOMAIN_UNSEALED")
        return self._admission, self._history, self._port

    def terminate(self, handle, reason="AUTHORITY_TERMINAL"):
        """One irreversible terminalization for timeout/reject/exception/invalid receipt.

        Any non-terminal permit becomes UNKNOWN exactly once; later receipts are
        refused and can never restore authority.
        """

        if not isinstance(handle, PermitHandle):
            raise AuthorityRefused("AUTHORITY_HANDLE_REQUIRED")
        with self._lock:
            record = self._records.get(handle.permit_id)
            if record is None:
                raise AuthorityRefused("AUTHORITY_PERMIT_UNKNOWN")
            state = self._states[record.permit_id]
            if state in TERMINAL:
                return state
            self._states[record.permit_id] = UNKNOWN
            self._terminal_reasons[record.permit_id] = reason
            return UNKNOWN

    def state_of_terminal(self, handle):
        with self._lock:
            return self._terminal_reasons.get(handle.permit_id)

    def receipt(self, handle, **fields):
        """Strict receipt validation; a receipt never grants authority."""

        if not isinstance(handle, PermitHandle):
            raise AuthorityRefused("AUTHORITY_HANDLE_REQUIRED")
        if set(fields) != set(RECEIPT_FIELDS):
            raise AuthorityRefused("AUTHORITY_RECEIPT_FIELDS_INVALID")
        with self._lock:
            record = self._records.get(handle.permit_id)
            if record is None:
                raise AuthorityRefused("AUTHORITY_PERMIT_UNKNOWN")
            if self._states[record.permit_id] != IN_FLIGHT:
                raise AuthorityRefused("AUTHORITY_RECEIPT_AFTER_TERMINAL")
            if (fields["protocol_version"] != 1 or fields["permit_id"] != record.permit_id
                    or fields["goal_uuid"] != record.goal_uuid or fields["role"] != record.role
                    or fields["generation"] != record.controller_generation
                    or fields["target_digest"] != record.target_digest
                    or fields["controller_incarnation"] != record.controller_incarnation
                    or not isinstance(fields["controller_boot_incarnation"], str)
                    or not fields["controller_boot_incarnation"]
                    or (record.permit_id in self._claim_boot
                        and fields["controller_boot_incarnation"]
                        != self._claim_boot[record.permit_id])
                    or fields["broker_incarnation"] != record.incarnation
                    or fields["session_id"] != record.identity[1]
                    or fields["deadline_ns"] != record.deadline_ns
                    or fields["clock_domain"] != "monotonic"
                    or type(fields["claim_monotonic_ns"]) is not int
                    or not record.issued_ns <= fields["claim_monotonic_ns"] <= self._clock_ns()
                    or type(fields["sequence"]) is not int or fields["sequence"] < 1
                    or type(fields["observed_ns"]) is not int
                    or not fields["claim_monotonic_ns"] <= fields["observed_ns"] <= self._clock_ns()
                    or fields["observed_ns"] > record.deadline_ns
                    or fields["verdict"] not in (ACCEPTED, REJECTED, UNKNOWN)):
                # any malformed, late or unknown receive result is irreversible
                self._states[record.permit_id] = UNKNOWN
                raise AuthorityRefused("AUTHORITY_RECEIPT_INVALID")
            self._states[record.permit_id] = fields["verdict"]
            return fields["verdict"]

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


class ReservationFakeControllerPort:
    """Stateful reservation/acceptance fake with armed generation and single-use UUIDs."""

    def __init__(self, *, clock_ns=time.monotonic_ns, generation=1,
                 controller_incarnation="i"):
        self._clock_ns = clock_ns
        self._lock = threading.RLock()
        self._generation = generation
        self._incarnation = controller_incarnation
        self._reservations = {}
        self._accepted_uuids = set()
        self._close_first = False
        self._close_reason = None
        self._accept_first = False
        self._boot_incarnation = f"{controller_incarnation}-boot"
        self._restarted = False
        self._io_blocked = False
        self.accepted_commands = 0
        self._consumed = {}
        self._received = {}
        self._sequence = 1
        self.reserve_calls = 0
        self.send_calls = 0
        self.cancel_stop_pending = False

    def reserve(self, *, permit_id, goal_uuid, role, target_digest, generation,
                controller_incarnation, deadline_ns, stage, session_id="clock-session",
                broker_incarnation=None, claim_monotonic_ns=None):
        with self._lock:
            self.reserve_calls += 1
            if stage != "route_dispatch":
                # only route dispatch may use the controller reservation/receive protocol
                return REJECTED
            if (self._restarted or generation != self._generation
                    or controller_incarnation != self._incarnation
                    or deadline_ns <= self._clock_ns() or goal_uuid in self._accepted_uuids):
                return REJECTED
            self._reservations[permit_id] = {"goal_uuid": goal_uuid, "role": role,
                                             "target_digest": target_digest,
                                             "deadline_ns": deadline_ns,
                                             "generation": generation,
                                             "controller_incarnation": controller_incarnation,
                                             "boot_incarnation": self._boot_incarnation,
                                             "session_id": session_id,
                                             "broker_incarnation": broker_incarnation,
                                             "claim_monotonic_ns": (claim_monotonic_ns
                                                                    if claim_monotonic_ns is not None
                                                                    else self._clock_ns())}
            return ACCEPTED

    def boot_incarnation(self):
        with self._lock:
            return self._boot_incarnation

    def current_generation(self):
        with self._lock:
            return self._generation

    def arm_generation(self, generation, *, controller_incarnation=None):
        with self._lock:
            # rearm invalidates every outstanding reservation under the controller mutex
            self._reservations.clear()
            self._generation = generation
            if controller_incarnation is not None:
                self._incarnation = controller_incarnation
        return True

    def close(self, reason="CLOSED"):
        with self._lock:
            self._reservations.clear()
            self._close_first = True
            self._close_reason = reason
        return True

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

    def restart_controller(self, *, controller_incarnation="restarted"):
        with self._lock:
            self._restarted = True
            self._incarnation = controller_incarnation
            self._reservations.clear()
        return REJECTED

    def send(self, *, goal_uuid, permit_id, role, target_digest, generation,
             controller_incarnation, sequence=None, deadline_ns=None):
        with self._lock:
            self.send_calls += 1
            if self._restarted or self._io_blocked or self._close_first:
                return REJECTED
            reservation = self._reservations.get(permit_id)
            if reservation is None:
                return REJECTED
            if reservation["goal_uuid"] != goal_uuid:
                return REJECTED
            if role != reservation["role"] or target_digest != reservation["target_digest"]:
                return REJECTED
            if generation != self._generation or generation != reservation["generation"]:
                return REJECTED
            if (controller_incarnation != self._incarnation
                    or controller_incarnation != reservation["controller_incarnation"]):
                return REJECTED
            if sequence is not None and sequence < 1:
                return REJECTED
            if deadline_ns is not None and deadline_ns != reservation["deadline_ns"]:
                return REJECTED
            if self._clock_ns() > reservation["deadline_ns"]:
                del self._reservations[permit_id]
                return REJECTED
            if goal_uuid in self._accepted_uuids:
                return REJECTED
            self._consumed[permit_id] = dict(reservation)
            self._received[permit_id] = {
                "protocol_version": 1, "permit_id": permit_id,
                "goal_uuid": reservation["goal_uuid"], "role": reservation["role"],
                "generation": reservation["generation"],
                "target_digest": reservation["target_digest"],
                "controller_incarnation": reservation["controller_incarnation"],
                "controller_boot_incarnation": reservation["boot_incarnation"],
                "broker_incarnation": reservation["broker_incarnation"],
                "session_id": reservation["session_id"],
                "deadline_ns": reservation["deadline_ns"],
                "clock_domain": "monotonic",
                "claim_monotonic_ns": reservation["claim_monotonic_ns"],
                "observed_ns": self._clock_ns(),      # frozen at receive, not later
                "sequence": self._sequence,
                "verdict": ACCEPTED}
            self._sequence += 1
            del self._reservations[permit_id]
            self._accepted_uuids.add(goal_uuid)
            self.accepted_commands += 1
            if self._accept_first:
                self.cancel_stop_pending = True
            return ACCEPTED

    def last_receipt(self, *, permit_id):
        """The immutable receive event recorded at the controller receive point."""

        from types import MappingProxyType

        with self._lock:
            received = self._received.get(permit_id)
            if received is None:
                raise AuthorityRefused("AUTHORITY_NO_RECEIVED_COMMAND")
            return MappingProxyType(dict(received))

    def late_receipt_after_timeout(self):
        with self._lock:
            return UNKNOWN
