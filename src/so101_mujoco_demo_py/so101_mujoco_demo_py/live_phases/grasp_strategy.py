"""Immutable MuJoCo grasp actions proved by the TASK15 five-win campaign."""

from __future__ import annotations

import math

# This is an actuator target, not a contact-classification threshold. TASK15-FULL-B
# proved this exact target through five consecutive physical micro-lifts. Keep it
# shared by CONTACT_HOLD and MICRO_LIFT until Project B replaces these transitional
# phase scripts with the typed state-action implementation.
FIVE_WIN_SEATING_PRELOAD_Q6_RAD = -0.04850794875050089


def seating_preload_target(detected_contact_q6_rad: float) -> float:
    """Apply the frozen preload without reopening an already tighter grasp."""

    if not math.isfinite(detected_contact_q6_rad):
        raise ValueError("detected contact q6 must be finite")
    return min(detected_contact_q6_rad, FIVE_WIN_SEATING_PRELOAD_Q6_RAD)
