"""Task 14: what may be retried, and under whose command.

A retry re-drives the arm toward a cup. That is only defensible when the cup's state is actually known and
empty: a held cup would be crushed or dropped, and an unknown state might be either. The attempt budget is
deliberately one — the plan's baseline does not retry a failed placement on hope.
"""

from __future__ import annotations

CUP_STATES = ("EMPTY", "HOLDING", "UNKNOWN")
_SAFE_TO_RETRY = "EMPTY"


def retry_allowed(attempts: int, cup_state: str, budget_available: bool) -> bool:
    """Whether one more attempt may be started, given what is known about the cup.

    `attempts` counts retries already used: 0 means the single retry is still unspent, 1 means it is gone.
    """

    if type(attempts) is not int or attempts < 0:
        raise ValueError("RETRY_ATTEMPTS_INVALID")
    if cup_state not in CUP_STATES:
        raise ValueError("RETRY_CUP_STATE_INVALID")
    if type(budget_available) is not bool:
        raise ValueError("RETRY_BUDGET_INVALID")
    if cup_state != _SAFE_TO_RETRY:
        # holding or unknown: evidence first, and never a blind re-approach
        return False
    return attempts == 0 and budget_available
