"""EXP-573 review 12: a valid non-ACCEPTED receipt must still close the transaction."""

import pytest

from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


def _drive(verdict):
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    original = port.last_receipt

    def verdict_override(**kwargs):
        fields = dict(original(**kwargs))
        # only the verdict changes; every other field stays real and schema-valid
        fields["verdict"] = verdict
        return fields

    port.last_receipt = verdict_override
    state = _run(tx)
    return history, admission, registry, port, tx, state


@pytest.mark.parametrize("verdict", ["UNKNOWN", "REJECTED"])
def test_valid_non_accepted_receipt_is_terminal_closed_and_unusable(verdict):
    history, admission, registry, port, tx, state = _drive(verdict)
    assert state == verdict, f"terminal state {state} != receipt verdict {verdict}"
    assert registry.state_of(tx.handle) == verdict, "registry did not record the verdict"
    assert port.accepted_commands == 1, "the original physical send must still be counted once"
    assert getattr(tx, "unusable", False) is True, "the transaction remained reusable"
    assert port._close_first is True or getattr(tx, "fencing_required", False) is True, (
        "the port was neither closed nor fenced")
    assert tx.failure and verdict in tx.failure
    # the frozen schema carries no separate reason field, so the receipt verdict
    # itself is the preserved reason
    assert verdict in tx.failure
    # a second run must not send again
    with pytest.raises(Exception):
        tx.run(stage="route_dispatch", role="arm", goal_uuid="g-2", target_digest="d-1",
               controller_generation=1, controller_incarnation="i")
    assert port.accepted_commands == 1, "a second run reached the controller"
    assert port.send_calls == 1


def test_accepted_receipt_is_the_only_outcome_without_closure():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    assert _run(tx) == "ACCEPTED"
    assert port.accepted_commands == 1
    assert registry.state_of(tx.handle) == "ACCEPTED"
    assert getattr(tx, "unusable", False) is False
