"""EXP-573 P2: the *same* permit is barred at reserve by a controller change.

A deterministic hook fires in the same transaction after capture and claim, at
the reserve boundary. It mutates the controller generation or restarts it, so the
original permit — not a freshly issued one — must be refused by reserve, close the
transaction through the unified path, and never send.
"""

import pytest

from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


def _armed(mutate):
    """Run one transaction whose reserve mutates the controller first."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    original_reserve = port.reserve
    seen = {"permits": [], "mutated": False}

    def reserve_hook(**kwargs):
        seen["permits"].append(kwargs["permit_id"])
        if not seen["mutated"]:
            seen["mutated"] = True
            mutate(port)                       # same transaction, at reserve
        return original_reserve(**kwargs)

    port.reserve = reserve_hook
    state = _run(tx)
    return history, admission, registry, port, tx, state, seen


def _assert_closed(port, tx, registry, state, seen):
    assert seen["mutated"] is True, "the reserve-time hook never ran"
    assert state == "UNKNOWN", f"transaction ended {state}"
    assert port.reserve_calls == 1, f"reserve_calls={port.reserve_calls}"
    assert port.send_calls == 0, f"send_calls={port.send_calls}"
    assert port.accepted_commands == 0
    assert registry.state_of(tx.handle) == "UNKNOWN", "permit is not terminal"
    assert port._close_first is True or getattr(tx, "fencing_required", False) is True, (
        "the port was neither closed nor fenced")
    assert getattr(tx, "unusable", False) is True, "the transaction is still usable"
    assert tx.failure, "no failure reason recorded"
    with pytest.raises(Exception):
        registry.receipt(tx.handle, **{key: 0 for key in registry.receipt_field_names()})
    assert registry.state_of(tx.handle) == "UNKNOWN", "a late receipt revived the permit"


def test_generation_change_at_reserve_refuses_the_original_permit():
    _, _, registry, port, tx, state, seen = _armed(
        lambda port: port.arm_generation(2, controller_incarnation="i"))
    # the permit that reached reserve is the one issued for this transaction
    assert seen["permits"] == [tx.handle.permit_id]
    _assert_closed(port, tx, registry, state, seen)


def test_boot_restart_at_reserve_refuses_the_original_permit():
    _, _, registry, port, tx, state, seen = _armed(
        lambda port: port.restart_controller(controller_incarnation="i"))
    assert seen["permits"] == [tx.handle.permit_id]
    _assert_closed(port, tx, registry, state, seen)


def test_positive_control_without_a_controller_change_accepts():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    assert _run(tx) == "ACCEPTED"
    assert port.reserve_calls == 1 and port.accepted_commands == 1
