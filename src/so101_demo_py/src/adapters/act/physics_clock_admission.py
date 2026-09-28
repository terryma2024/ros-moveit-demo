"""Broker-owned, identity-scoped, irreversible admission for physics-clock evidence.

This module is an **offline contract**: it grants no motion authority, sends no
goal and is not yet constructed by any production entry. It freezes the Gate 5
requirements that must hold before `RosPhysicsClockAdapter` may be wired into
`PickPlaceRosEvidence`:

- every admission stage is scoped by the complete broker identity
  ``(ticket, generation, reset_epoch)``;
- a hazard is captured together with the identity that was current when it
  happened, and revocation for that identity is irreversible;
- only a strictly newer identity clears revocation;
- an expensive checked stage runs outside the lock, so a blocking checker can
  never delay revocation, and the result is re-fenced before it is committed;
- a partial submit cancels the accepted routes and keeps the identity unusable
  until a confirmed stop is recorded;
- the expiry -> revoke -> confirmed-stop interval is recorded separately, and
  selected-state freshness is enforced independently of ingestion freshness.
"""

from __future__ import annotations

import copy
import math
import threading
import time


EXPIRY_REASONS = frozenset({
    "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT",
    "PHYSICS_CLOCK_SILENT",
    "PHYSICS_CLOCK_STALE",
})
STAGES = frozenset({"sample", "proof", "permit", "submit", "final_acceptance"})
MAX_IDENTITY_INT = 2 ** 63 - 1


def _validated_identity(ticket, generation, reset_epoch):
    """Validate one identity; invalid values are refused, never coerced."""

    if not isinstance(ticket, str) or not ticket:
        raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_INVALID")
    if type(generation) is not int or not 0 <= generation <= MAX_IDENTITY_INT:
        raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_INVALID")
    if type(reset_epoch) is not int or not 1 <= reset_epoch <= MAX_IDENTITY_INT:
        raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_INVALID")
    return (ticket, generation, reset_epoch)


def identity_is_successor(candidate, current):
    """Authoritative successor relation; never incidental tuple ordering.

    Same ticket: ``(generation, reset_epoch)`` must increase lexicographically on
    integers only. Ticket rotation: the generation must strictly increase, so a
    rotated ticket can never rewind or repeat the current generation.
    """

    if current is None:
        return True
    if candidate[0] == current[0]:
        return (candidate[1], candidate[2]) > (current[1], current[2])
    return candidate[1] > current[1]


class AdmissionRefused(ValueError):
    """The broker refused a stage because the clock identity is unusable."""


class PhysicsClockAdmission:
    """Broker-owned admission gate; every critical section is O(1)."""

    def __init__(self, history, *, selected_max_age_s, clock_ns=time.monotonic_ns):
        if (history is None or not callable(clock_ns)
                or isinstance(selected_max_age_s, bool)
                or not isinstance(selected_max_age_s, (int, float))
                or not math.isfinite(selected_max_age_s) or selected_max_age_s <= 0):
            raise ValueError("CLOCK_ADMISSION_CONFIG_INVALID")
        self._history = history
        self._clock_ns = clock_ns
        self._selected_max_age_ns = round(selected_max_age_s * 1_000_000_000)
        if self._selected_max_age_ns < 1:
            raise ValueError("CLOCK_ADMISSION_CONFIG_INVALID")
        self._lock = threading.RLock()
        self._identity = None
        self._revoked = None
        self._stop_confirmed = False
        self._stages = []
        self._stale_hazards = []
        self.checked_stages = 0

    # ---------------------------------------------------------------- identity

    def arm(self, *, ticket, generation, reset_epoch):
        identity = _validated_identity(ticket, generation, reset_epoch)
        with self._lock:
            if not identity_is_successor(identity, self._identity):
                raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_NOT_NEWER")
            self._identity = identity
            self._revoked = None
            self._stop_confirmed = False
            self._stages = []
            return identity

    @property
    def identity(self):
        with self._lock:
            return self._identity

    @property
    def revoked_record(self):
        with self._lock:
            return copy.deepcopy(self._revoked)

    @property
    def stop_confirmed(self):
        with self._lock:
            return self._stop_confirmed

    @property
    def stage_log(self):
        with self._lock:
            return copy.deepcopy(self._stages)

    # -------------------------------------------------------------- revocation

    def note_hazard(self, reason, *, origin_identity=None):
        """Capture a hazard together with the identity of the event that caused it.

        A hazard whose origin identity is not the current identity is recorded as
        a stale event and does **not** revoke the current identity: a delayed
        hazard from an older epoch must never close a newer arm.
        """

        if not isinstance(reason, str) or not reason:
            raise ValueError("CLOCK_ADMISSION_HAZARD_INVALID")
        origin = None if origin_identity is None else _validated_identity(*origin_identity)
        with self._lock:
            if origin is not None and origin != self._identity:
                self._stale_hazards.append({
                    "reason": reason, "origin_identity": origin,
                    "current_identity": self._identity,
                    "monotonic_ns": self._clock_ns(),
                })
                return {"applied": False, "reason": reason, "origin_identity": origin,
                        "current_identity": self._identity}
            if self._revoked is None:
                self._revoked = {
                    "reason": reason,
                    "identity": self._identity,
                    "monotonic_ns": self._clock_ns(),
                    "expiry": reason in EXPIRY_REASONS,
                    "confirmed_stop_monotonic_ns": None,
                    "expiry_to_stop_ns": None,
                }
            self._stop_confirmed = False
            record = copy.deepcopy(self._revoked)
            record["applied"] = True
            return record

    def revoke(self, reason):
        return self.note_hazard(reason)

    @property
    def stale_hazards(self):
        with self._lock:
            return copy.deepcopy(self._stale_hazards)

    def confirm_stop(self, *, identity, stopped):
        """Record a confirmed physical stop for the revoked identity."""

        with self._lock:
            if self._identity is None or tuple(identity) != self._identity:
                raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_CHANGED")
            if stopped is not True:
                raise AdmissionRefused("CLOCK_ADMISSION_STOP_NOT_CONFIRMED")
            if self._revoked is None:
                raise AdmissionRefused("CLOCK_ADMISSION_NOT_REVOKED")
            confirmed_ns = self._clock_ns()
            self._stop_confirmed = True
            self._revoked["confirmed_stop_monotonic_ns"] = confirmed_ns
            if self._revoked["expiry"]:
                self._revoked["expiry_to_stop_ns"] = (
                    confirmed_ns - self._revoked["monotonic_ns"])
            return copy.deepcopy(self._revoked)

    # ----------------------------------------------------------------- fencing

    def _fence_locked(self, identity, stage, now_ns):
        """Identity/revocation/stop-pending check plus the stage row. Lock held."""

        if self._identity is None:
            raise AdmissionRefused("CLOCK_ADMISSION_UNARMED")
        if identity != self._identity:
            raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_CHANGED")
        if self._revoked is not None:
            raise AdmissionRefused(f"CLOCK_ADMISSION_REVOKED:{self._revoked['reason']}")
        if not self._stop_confirmed and any(row["stop_pending"] for row in self._stages):
            raise AdmissionRefused("CLOCK_ADMISSION_STOP_PENDING")
        self._stages.append({"stage": stage, "identity": identity,
                             "monotonic_ns": now_ns, "stop_pending": False})
        return True

    def fence(self, *, ticket, generation, reset_epoch, stage):
        """Short, O(1) re-fence used by every admission stage."""

        if stage not in STAGES:
            raise ValueError("CLOCK_ADMISSION_STAGE_INVALID")
        identity = _validated_identity(ticket, generation, reset_epoch)
        with self._lock:
            now_ns = self._clock_ns()
            return self._fence_locked(identity, stage, now_ns)

    def run_checked_stage(self, *, ticket, generation, reset_epoch, stage, checker):
        """Run an expensive checker outside the lock, then re-fence before committing.

        Revocation never waits for the checker: the admission lock is only held
        for the entry fence and the commit fence.
        """

        if not callable(checker):
            raise ValueError("CLOCK_ADMISSION_CHECKER_INVALID")
        identity = _validated_identity(ticket, generation, reset_epoch)
        self.fence(ticket=ticket, generation=generation, reset_epoch=reset_epoch,
                   stage=stage)
        result = checker()
        # Commit linearization: the clock is sampled, the identity is re-fenced and
        # the result is committed inside one critical section. A revocation that
        # linearizes before this point refuses the stage; one that linearizes after
        # it leaves this committed result valid and closes the identity for every
        # later stage.
        with self._lock:
            now_ns = self._clock_ns()
            self._fence_locked(identity, stage, now_ns)
            self.checked_stages += 1
        return result

    # ------------------------------------------------------------- admissions

    def admit_sample(self, *, sample, ticket, generation, reset_epoch):
        """Admit one selected sample under identity fence and selected-state freshness."""

        identity = _validated_identity(ticket, generation, reset_epoch)
        # One critical section: identity/revocation, selected-state age and the
        # return decision are linearized together, so a revocation can never land
        # between the fence and the returned sample.
        with self._lock:
            now_ns = self._clock_ns()
            self._fence_locked(identity, "sample", now_ns)
            age_ns = now_ns - sample.clock_interval_end_monotonic_ns
            if not 0 <= age_ns <= self._selected_max_age_ns:
                raise AdmissionRefused("CLOCK_ADMISSION_SELECTED_STALE")
        return {"sample": sample, "command_authority": False, "stage": "sample"}

    def record_partial_submit(self, *, ticket, generation, reset_epoch,
                              accepted_routes, rejected_routes, cancel):
        """Cancel the accepted routes and keep the identity closed until a confirmed stop."""

        identity = _validated_identity(ticket, generation, reset_epoch)
        if not callable(cancel):
            raise ValueError("CLOCK_ADMISSION_CANCEL_INVALID")
        with self._lock:
            if self._identity is None or identity != self._identity:
                raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_CHANGED")
            if self._revoked is not None:
                raise AdmissionRefused(f"CLOCK_ADMISSION_REVOKED:{self._revoked['reason']}")
            self._stages.append({"stage": "partial_submit", "identity": identity,
                                 "monotonic_ns": self._clock_ns(), "stop_pending": True,
                                 "accepted_routes": tuple(accepted_routes),
                                 "rejected_routes": tuple(rejected_routes)})
        # Fail closed: only a cancellation call that returns a truthy confirmation
        # counts as cancelled. An exception or an unconfirmed return revokes with a
        # distinct reason, and either way the identity stays closed until a
        # matching confirmed stop is recorded.
        try:
            confirmed = bool(cancel(tuple(accepted_routes)))
        except BaseException:  # noqa: BLE001 - recorded as a failed cancellation
            confirmed = False
        if not confirmed:
            return self.note_hazard("PHYSICS_CLOCK_PARTIAL_CANCEL_FAILED")
        return self.note_hazard("PHYSICS_CLOCK_PARTIAL_SUBMIT")
