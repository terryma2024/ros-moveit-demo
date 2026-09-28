"""Task 14: a retry needs a known-empty cup, an unspent budget and a wall-clock allowance."""

import pytest

from so101_demo.act.session import retry_allowed


def test_no_retry_with_unknown_or_held_cup():
    assert not retry_allowed(0, "UNKNOWN", True)
    assert not retry_allowed(0, "HOLDING", True)
    assert retry_allowed(0, "EMPTY", True)
    assert not retry_allowed(1, "EMPTY", True)


def test_the_budget_and_the_inputs_are_closed():
    assert retry_allowed(0, "EMPTY", True) is True
    assert retry_allowed(0, "EMPTY", False) is False        # no budget left in the wall clock
    assert retry_allowed(2, "EMPTY", True) is False          # two spent retries is simply not a retry
    for attempts in (-1, True, 1.0, "0"):                    # malformed counts are refused
        with pytest.raises(ValueError, match="RETRY_ATTEMPTS_INVALID"):
            retry_allowed(attempts, "EMPTY", True)
    for state in ("empty", "HELD", "", None):
        with pytest.raises(ValueError, match="RETRY_CUP_STATE_INVALID"):
            retry_allowed(0, state, True)
    for budget in (1, None, "yes"):
        with pytest.raises(ValueError, match="RETRY_BUDGET_INVALID"):
            retry_allowed(0, "EMPTY", budget)
