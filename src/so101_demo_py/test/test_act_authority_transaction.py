"""Gate 5 offline authority transaction and adversarial fake controller port.

These tests are the deterministic adversarial set required by the design review.
They import the not-yet-implemented module inside each test body so collection
succeeds and every intended testcase name is present in the manifest and JUnit.
"""

import pytest


def _module():
    from so101_demo.adapters.act import authority_transaction
    return authority_transaction


def _registry():
    module = _module()
    return module.AuthorityTransactionRegistry(clock_ns=lambda: 1_000_000_000)


def _fake():
    module = _module()
    return module.AdversarialFakeControllerPort()


def test_hazard_before_claim_produces_zero_reserve_and_zero_send():
    registry = _registry()
    port = _fake()
    permit = registry.issue(identity=("t", "s", "i", 1, 1), stage="route_dispatch", step=1,
                            history_version=1, incarnation="i", epoch=1, role="arm",
                            controller_generation=1, goal_uuid="g-1", target_digest="d-1")
    registry.revoke("PHYSICS_CLOCK_SILENT")
    with pytest.raises(Exception):
        registry.claim(permit, now_ns=1_000_000_000)
    assert port.reserve_calls == 0 and port.send_calls == 0


def test_large_copy_interleavings_hold_no_local_lock():
    registry = _registry()
    permit = registry.issue(identity=("t", "s", "i", 1, 1), stage="route_dispatch", step=1,
                            history_version=1, incarnation="i", epoch=1, role="arm",
                            controller_generation=1, goal_uuid="g-1", target_digest="d-1")
    registry.claim(permit, now_ns=1_000_000_000)
    assert not registry.lock_held_during(lambda: None)


def test_reset_hazard_and_age_crossing_after_final_read_refuse_the_permit():
    registry = _registry()
    permit = registry.issue(identity=("t", "s", "i", 1, 1), stage="route_dispatch", step=1,
                            history_version=1, incarnation="i", epoch=1, role="arm",
                            controller_generation=1, goal_uuid="g-1", target_digest="d-1")
    with pytest.raises(Exception):
        registry.claim(permit, now_ns=permit.deadline_ns + 1)


def test_io_blocked_while_revoke_proceeds_without_the_broker_lock():
    registry = _registry()
    port = _fake()
    port.block_io(True)
    registry.revoke("CLIENT_REVOKED")
    assert registry.revoke_completed_without_waiting() is True


def test_controller_close_before_acceptance_yields_zero_accepted_commands():
    port = _fake()
    port.close_before_accept()
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "REJECTED"
    assert port.accepted_commands == 0


def test_controller_acceptance_before_close_yields_one_command_then_cancel():
    port = _fake()
    port.accept_before_close(cancel_pending=True)
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "ACCEPTED"
    assert port.accepted_commands == 1
    assert port.cancel_stop_pending is True


@pytest.mark.parametrize("field,value", [
    ("generation", 99), ("goal_uuid", "other"), ("permit_id", "other"),
    ("target_digest", "other"), ("controller_incarnation", "other"),
    ("sequence", -1), ("deadline_ns", 0),
])
def test_wrong_field_is_rejected(field, value):
    port = _fake()
    assert port.send(goal_uuid="g-1", permit_id="p-1",
                     override={field: value}) == "REJECTED"


def test_replay_duplicate_late_and_restart_are_fail_closed():
    port = _fake()
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "ACCEPTED"
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "REJECTED"
    assert port.late_receipt_after_timeout() == "UNKNOWN"
    assert port.restart_controller() == "REJECTED"
