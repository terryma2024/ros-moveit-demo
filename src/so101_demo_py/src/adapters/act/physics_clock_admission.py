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
_MISSING = object()


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
        # Same session incarnation: the reset epoch may never roll back, and the
        # pair must still advance. Moving from (generation 7, epoch 9) to
        # (8, 1) requires an explicit new session/history incarnation instead.
        if candidate[2] < current[2]:
            return False
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
            if self._revoked is not None and not self._stop_confirmed:
                # The previous target has not been authoritatively stopped or
                # retired, so no new generation may take over this gate.
                raise AdmissionRefused("CLOCK_ADMISSION_TAKEOVER_BLOCKED")
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

    def _revoke_locked(self, reason, *, now_ns):
        """Apply an irreversible revocation for the current identity. Lock held."""

        if self._revoked is None:
            self._revoked = {
                "reason": reason,
                "identity": self._identity,
                "monotonic_ns": now_ns,
                "expiry": reason in EXPIRY_REASONS,
                "confirmed_stop_monotonic_ns": None,
                "expiry_to_stop_ns": None,
            }
        self._stop_confirmed = False
        record = copy.deepcopy(self._revoked)
        record["applied"] = True
        return record

    def note_hazard(self, reason, *, origin_identity=_MISSING):
        """Capture a callback hazard; the event's origin identity is mandatory.

        The origin identity is required and must be one half of the complete
        ``(ticket, generation, reset_epoch)`` identity carried by the event. An
        omitted or ``None`` origin is refused and changes no state, so a caller
        omission can never recreate the delayed-old-callback failure. A hazard
        whose origin is not the current identity is recorded in ``stale_hazards``
        and does **not** revoke the current identity.
        """

        if not isinstance(reason, str) or not reason:
            raise ValueError("CLOCK_ADMISSION_HAZARD_INVALID")
        if origin_identity is _MISSING or origin_identity is None:
            raise AdmissionRefused("CLOCK_ADMISSION_ORIGIN_IDENTITY_REQUIRED")
        origin = _validated_identity(*origin_identity)
        with self._lock:
            now_ns = self._clock_ns()
            if origin != self._identity:
                self._stale_hazards.append({
                    "reason": reason, "origin_identity": origin,
                    "current_identity": self._identity, "monotonic_ns": now_ns,
                })
                return {"applied": False, "reason": reason, "origin_identity": origin,
                        "current_identity": self._identity}
            return self._revoke_locked(reason, now_ns=now_ns)

    def revoke_current(self, reason):
        """Broker-administrative revoke of whatever identity is current.

        This is deliberately a **separate, explicitly named** API: it takes no
        event identity, it refuses an unarmed gate, and it is irreversible for the
        current identity.
        """

        if not isinstance(reason, str) or not reason:
            raise ValueError("CLOCK_ADMISSION_HAZARD_INVALID")
        with self._lock:
            if self._identity is None:
                raise AdmissionRefused("CLOCK_ADMISSION_UNARMED")
            return self._revoke_locked(reason, now_ns=self._clock_ns())

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
        if self._history is not None and self._history.hazard is not None:
            raise AdmissionRefused(
                f"CLOCK_ADMISSION_HISTORY_HAZARD:{self._history.hazard}")
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

    def run_checked_stage(self, *, ticket, generation, reset_epoch, stage,
                          side_effect_free=_MISSING, checker):
        """Run an expensive **side-effect-free** checker, then re-fence at commit.

        Revocation never waits for the checker: the admission lock is only held for
        the entry fence and the commit fence. This API must not send commands:
        proof, permit, each route submit and final acceptance use the atomic
        `consume_stage` fence instead, because a command that was already sent
        cannot be repaired by refusing its result afterwards.
        """

        if side_effect_free is not True:
            raise ValueError("CLOCK_ADMISSION_SIDE_EFFECT_FREE_REQUIRED")
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
        """Admit one selected sample, bound atomically to the trusted history.

        Lock order: the admission lock is always taken before the history lock and
        is never held across a large copy. The sample is not trusted: its session,
        epoch and step are re-derived from the history, which must itself be
        evidence-ready and hazard-free at this linearization point.
        """

        identity = _validated_identity(ticket, generation, reset_epoch)
        with self._lock:
            now_ns = self._clock_ns()
            self._fence_locked(identity, "sample", now_ns)
            history = self._history
            if history is None or not history.evidence_ready:
                raise AdmissionRefused("CLOCK_ADMISSION_HISTORY_NOT_READY")
            if history.session_id != identity[0] or history.epoch != identity[2]:
                raise AdmissionRefused("CLOCK_ADMISSION_HISTORY_IDENTITY_MISMATCH")
            if (sample.simulation_session_id != identity[0]
                    or sample.reset_epoch != identity[2]):
                raise AdmissionRefused("CLOCK_ADMISSION_SAMPLE_IDENTITY_MISMATCH")
            try:
                entry = history.step_at(sample.physics_step)
            except ValueError as error:
                raise AdmissionRefused(
                    f"CLOCK_ADMISSION_HISTORY_STEP_UNAVAILABLE:{error}") from error
            age_ns = now_ns - entry["sample"].clock_interval_end_monotonic_ns
            if not 0 <= age_ns <= self._selected_max_age_ns:
                raise AdmissionRefused("CLOCK_ADMISSION_SELECTED_STALE")
            return {"sample": copy.deepcopy(entry["sample"]),
                    "received_monotonic_ns": entry["received_monotonic_ns"],
                    "identity": identity, "command_authority": False, "stage": "sample"}

    def consume_stage(self, *, ticket, generation, reset_epoch, stage, consume):
        """Atomic consume fence for a real authority stage (permit, submit, ...).

        The short consume callable runs inside the same critical section as the
        identity/revocation fence, so a revocation can never interleave between
        the check and the consumption. Callables must be short and non-blocking;
        expensive side-effect-free computation belongs in `run_checked_stage`.
        """

        if stage not in STAGES or stage == "sample":
            raise ValueError("CLOCK_ADMISSION_STAGE_INVALID")
        if not callable(consume):
            raise ValueError("CLOCK_ADMISSION_CONSUME_INVALID")
        identity = _validated_identity(ticket, generation, reset_epoch)
        with self._lock:
            now_ns = self._clock_ns()
            self._fence_locked(identity, stage, now_ns)
            consume()
            return True

    def record_partial_submit(self, *, ticket, generation, reset_epoch,
                              accepted_routes, rejected_routes, cancel):
        """Close the original identity first, then cancel; bind completion to it.

        The identity is revoked *before* the external cancellation starts, so the
        old target can never be taken over while its cancellation is in flight,
        and a late cancellation result can never revoke a newer identity.
        """

        identity = _validated_identity(ticket, generation, reset_epoch)
        if not callable(cancel):
            raise ValueError("CLOCK_ADMISSION_CANCEL_INVALID")
        with self._lock:
            if self._identity is None or identity != self._identity:
                raise AdmissionRefused("CLOCK_ADMISSION_IDENTITY_CHANGED")
            if self._revoked is not None:
                raise AdmissionRefused(f"CLOCK_ADMISSION_REVOKED:{self._revoked['reason']}")
            now_ns = self._clock_ns()
            self._stages.append({"stage": "partial_submit", "identity": identity,
                                 "monotonic_ns": now_ns, "stop_pending": True,
                                 "accepted_routes": tuple(accepted_routes),
                                 "rejected_routes": tuple(rejected_routes)})
            original = self._revoke_locked("PHYSICS_CLOCK_PARTIAL_SUBMIT", now_ns=now_ns)
        try:
            confirmed = bool(cancel(tuple(accepted_routes)))
        except BaseException:  # noqa: BLE001 - recorded as a failed cancellation
            confirmed = False
        with self._lock:
            if self._identity == identity and self._revoked is not None:
                self._revoked["cancel_confirmed"] = confirmed
                if not confirmed:
                    self._revoked["reason"] = "PHYSICS_CLOCK_PARTIAL_CANCEL_FAILED"
                record = copy.deepcopy(self._revoked)
                record["applied"] = True
                return record
            # The gate moved on: the late completion is recorded, never applied.
            self._stale_hazards.append({"reason": "PHYSICS_CLOCK_LATE_CANCEL_COMPLETION",
                                        "origin_identity": identity,
                                        "current_identity": self._identity,
                                        "confirmed": confirmed,
                                        "monotonic_ns": self._clock_ns()})
            return {"applied": False, "reason": "PHYSICS_CLOCK_LATE_CANCEL_COMPLETION",
                    "origin_identity": identity, "current_identity": self._identity}
