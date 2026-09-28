"""EXP-573 review 13: one single-purpose terminalizer, no override, no overwrite."""

import inspect

import pytest

from so101_demo.adapters.act.authority_transaction import ACCEPTED, AuthorityTransactionRegistry
from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS
from test_act_exp573_terminal_receipt import _drive


def test_terminate_exposes_no_terminal_override():
    parameters = inspect.signature(AuthorityTransactionRegistry.terminate).parameters
    assert "terminal" not in parameters
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    with pytest.raises(TypeError):
        registry.terminate(tx.handle, reason="X", terminal=REJECTED if False else "REJECTED")


def test_terminating_an_in_flight_permit_returns_and_stores_unknown():
    from test_act_exp573_snapshot_authority import _issue, _token

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    handle = _issue(history, admission, registry)
    registry.capture_controller_identity(handle)
    registry.claim_bound(handle, identity=admission.identity,
                         controller_generation=admission.identity[3],
                         token=_token(history, admission, registry))
    assert registry.state_of(handle) == "IN_FLIGHT"
    state = registry.terminate(handle, reason="OPERATOR_STOP")
    assert state == "UNKNOWN"
    assert registry.state_of(handle) == "UNKNOWN"
    assert registry.state_of_terminal(handle) == "OPERATOR_STOP"
    # a terminated permit cannot be captured or claimed again
    with pytest.raises(Exception):
        registry.capture_controller_identity(handle)


@pytest.mark.parametrize("verdict", ["UNKNOWN", "REJECTED"])
def test_terminate_preserves_an_existing_receipt_terminal_state_and_reason(verdict):
    history, admission, registry, port, tx, state = _drive(verdict)
    assert state == verdict
    stored = registry.state_of(tx.handle)
    assert stored == verdict, f"stored state changed to {stored}"
    reason = registry.state_of_terminal(tx.handle)
    assert reason == f"AUTHORITY_RECEIPT_{verdict}:{verdict}", reason
    # a later terminate must not overwrite the receipt's authoritative reason
    again = registry.terminate(tx.handle, reason="LATE_TERMINATE")
    assert again == verdict, f"terminate returned {again}"
    assert registry.state_of(tx.handle) == verdict
    assert registry.state_of_terminal(tx.handle) == f"AUTHORITY_RECEIPT_{verdict}:{verdict}"


@pytest.mark.parametrize("verdict", ["UNKNOWN", "REJECTED"])
def test_valid_terminal_receipt_closure_end_to_end(verdict):
    history, admission, registry, port, tx, state = _drive(verdict)
    assert state == verdict
    assert registry.state_of(tx.handle) == verdict
    assert registry.state_of_terminal(tx.handle) == f"AUTHORITY_RECEIPT_{verdict}:{verdict}"
    assert tx.failure and verdict in tx.failure
    assert port.accepted_commands == 1
    assert port._close_first is True or getattr(tx, "fencing_required", False) is True
    assert getattr(tx, "unusable", False) is True
    with pytest.raises(Exception):
        tx.run(stage="route_dispatch", role="arm", goal_uuid="g-2", target_digest="d-1",
               controller_generation=1, controller_incarnation="i")
    assert port.accepted_commands == 1 and port.send_calls == 1


def test_accepted_positive_control_is_unaffected():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    assert _run(tx) == ACCEPTED
    assert registry.state_of(tx.handle) == ACCEPTED
    assert getattr(tx, "unusable", False) is False
    assert port.accepted_commands == 1
