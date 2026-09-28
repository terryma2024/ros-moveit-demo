"""EXP-573: an unvalidated readback Mapping must not escape the failure closure."""

import pytest

from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS

CASES = {"integer key": {1: "bad"}, "handle key": {"handle": "bad"}}


@pytest.mark.parametrize("name", sorted(CASES))
def test_malformed_readback_mapping_takes_the_known_permit_closure(name):
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    port.last_receipt = lambda **kwargs: dict(CASES[name])
    state = _run(tx)
    assert state == "UNKNOWN", f"{name}: transaction ended {state}"
    assert tx.failure, f"{name}: no failure reason"
    assert registry.state_of(tx.handle) == "UNKNOWN", f"{name}: permit not terminal"
    assert getattr(tx, "unusable", False) is True, f"{name}: transaction still usable"
    assert port._close_first is True or getattr(tx, "fencing_required", False) is True, (
        f"{name}: the port was neither closed nor fenced")
    with pytest.raises(Exception):
        tx.run(stage="route_dispatch", role="arm", goal_uuid="g-2", target_digest="d-1",
               controller_generation=1, controller_incarnation="i")


def test_extra_field_is_refused_and_never_sent_beyond_the_allowed_stage():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    port.last_receipt = lambda **kwargs: dict(protocol_version=1, permit_id="x", bogus="extra")
    state = _run(tx)
    assert state == "UNKNOWN"
    assert registry.state_of(tx.handle) == "UNKNOWN"
    assert getattr(tx, "unusable", False) is True
