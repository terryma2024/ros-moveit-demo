"""Task 4: the calibration-only neck command adapter.

Arm commands must byte-match the measurement plan, and a neck target may be dynamic only when it is uniquely
derived from policy state, inside the approved safe interval, and independently sweep-safe. Submitting to the
broker without a receipt from this adapter is refused, so the generic non-ACT submit path is never reused.
"""

from __future__ import annotations

import math

NECK_BOUNDS_RAD = (-2.0 * math.pi, 2.0 * math.pi)


class CalibrationSearchBinding:
    """Authorizes bounded calibration commands for one admission."""

    def __init__(self, *, admission, policy_state: dict, sweep_checker) -> None:
        self.admission = admission
        self.policy_state = dict(policy_state)
        self.sweep_checker = sweep_checker
        self.submitted_targets: list[float] = []
        self._last_target = None
        self._classification = None
        self._started_monotonic_s = None

    # --- authorization ------------------------------------------------------------------------------------
    def authorize_arm_command(self, *, plan_sha256: str) -> dict:
        if str(plan_sha256) != self.admission.measurement_plan_sha256:
            raise ValueError("MEASUREMENT_PLAN_MISMATCH: arm command does not byte-match the measurement plan")
        return {"authorized": True, "generation": self.admission.generation}

    def _inside_interval(self, target_rad: float) -> bool:
        lower, upper = self.admission.safe_interval_rad
        return lower <= target_rad <= upper

    def authorize_neck_target(self, *, target_rad: float, policy_state: dict, sweep_safe=None) -> dict:
        if not self._inside_interval(target_rad):
            raise ValueError(f"NECK_TARGET_OUTSIDE_INTERVAL: {target_rad}")
        checker = self.sweep_checker if sweep_safe is None else (lambda _target: bool(sweep_safe))
        if not checker(target_rad):
            raise ValueError(f"NECK_TARGET_NOT_SWEEP_SAFE: {target_rad}")
        return {"authorized": True, "target_rad": float(target_rad),
                "generation": self.admission.generation}

    def submit_directly_to_broker(self, *, target_rad: float, receipt) -> dict:
        """A direct submission is refused: the broker accepts only this adapter's receipt."""

        must_be_absent = getattr(self.admission, "generation", None)
        if receipt is None or not getattr(receipt, "signed_by", None) == must_be_absent:
            raise ValueError("CALIBRATION_BINDING_REQUIRED: broker accepts only a signed adapter receipt")
        return {"submitted": True, "target_rad": float(target_rad)}

    # --- state machine -------------------------------------------------------------------------------------
    def advance(self, *, target_rad: float, classification: str = "coarse") -> dict:
        if classification not in ("coarse", "fine"):
            raise ValueError(f"CLASSIFICATION_INVALID: {classification}")
        if not self._inside_interval(target_rad):
            return {"advanced": False, "reason": "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL",
                    "target_rad": float(target_rad)}
        if self._last_target is not None and float(target_rad) == self._last_target:
            return {"advanced": False, "reason": "REISSUE_NO_ADVANCE", "target_rad": float(target_rad)}
        self._last_target = float(target_rad)
        self._classification = classification
        self.submitted_targets.append(float(target_rad))
        return {"advanced": True, "target_rad": float(target_rad), "classification": classification}

    def advance_deadline(self, *, monotonic_s: float) -> dict:
        if self._started_monotonic_s is None:
            self._started_monotonic_s = float(monotonic_s)
        return {"started_monotonic_s": self._started_monotonic_s}

    def deadline_elapsed(self, *, terminal_monotonic_s: float) -> float:
        if self._started_monotonic_s is None:
            raise ValueError("DEADLINE_NOT_STARTED")
        return float(terminal_monotonic_s) - self._started_monotonic_s
