"""EXP-573 P1.2: every known-permit failure funnels through one closure.

Review 10 showed the transaction state, registry state and port-close state were
inconsistent across paths, and that a malformed readback (``None``) escaped as a
``TypeError`` leaving tx IDLE / permit IN_FLIGHT / port open. Each row below drives
one path and asserts the closure properties that must hold for all of them.
"""

import threading

import pytest

from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


def _drive(now, mutate, *, ttl_ns=30_000_000_000):
    history, admission, registry, port, tx = _transaction(now, ttl_ns=ttl_ns)
    mutate(history, admission, registry, port, tx)
    state = _run(tx)
    return history, admission, registry, port, tx, state


def _claim_refusal(history, admission, registry, port, tx):
    original = registry.claim_bound

    def revoke_then_claim(*args, **kwargs):
        # the owner is revoked after the permit exists, so the *claim* refuses
        admission.revoke_current("CLIENT_REVOKED")
        return original(*args, **kwargs)

    registry.claim_bound = revoke_then_claim


def _reserve_refusal(history, admission, registry, port, tx):
    port.arm_generation(999, controller_incarnation="i")


def _reserve_exception(history, admission, registry, port, tx):
    def exploding_reserve(**kwargs):
        raise TimeoutError("reserve timed out")
    port.reserve = exploding_reserve


def _send_refusal(history, admission, registry, port, tx):
    port.close_before_accept()


def _send_exception(history, admission, registry, port, tx):
    def exploding_send(**kwargs):
        raise TimeoutError("send timed out")
    port.send = exploding_send


def _readback_exception(history, admission, registry, port, tx):
    original = port.last_receipt

    def exploding_readback(**kwargs):
        raise TimeoutError("readback timed out")
    port.last_receipt = exploding_readback


def _readback_none(history, admission, registry, port, tx):
    port.last_receipt = lambda **kwargs: None


def _readback_invalid_type(history, admission, registry, port, tx):
    port.last_receipt = lambda **kwargs: "not-a-mapping"


PRE_SEND_PATHS = {"claim refusal", "reserve refusal", "reserve exception",
                  "send refusal", "send exception"}

PATHS = {
    "claim refusal": _claim_refusal,
    "reserve refusal": _reserve_refusal,
    "reserve exception": _reserve_exception,
    "send refusal": _send_refusal,
    "send exception": _send_exception,
    "readback exception": _readback_exception,
    "readback None": _readback_none,
    "readback invalid type": _readback_invalid_type,
}


@pytest.mark.parametrize("name", sorted(PATHS))
def test_every_known_permit_failure_closes_transaction_registry_and_port(name):
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx, state = _drive(now, PATHS[name])
    # one consistent terminal state for the transaction and the registry
    assert state == "UNKNOWN", f"{name}: transaction ended {state}"
    if name in PRE_SEND_PATHS:
        assert port.accepted_commands == 0, f"{name}: a command was accepted before the send"
    else:
        # a readback/receipt failure happens after the controller consumed the
        # command; the closure requirement is terminalization, not a zero count
        assert port.accepted_commands == 1, f"{name}: unexpected accepted count"
    assert tx.failure, f"{name}: no failure reason recorded"
    if tx.handle is not None:
        # one terminal state for the permit; a revoke-caused refusal keeps the
        # more specific REVOKED, which is equally terminal and equally final
        permit_state = registry.state_of(tx.handle)
        assert permit_state in ("UNKNOWN", "REVOKED"), (
            f"{name}: permit state is {permit_state} (not terminal)")
    # the controller generation is fenced by closing the port, outside the locks
    assert port._close_first is True, f"{name}: the controller port was left open"
    # no revival: a later receipt cannot restore authority
    if tx.handle is not None:
        late = {"protocol_version": 1, "permit_id": tx.handle.permit_id, "goal_uuid": "g-1",
                "role": "arm", "generation": admission.identity[3], "target_digest": "d-1",
                "controller_incarnation": "i", "controller_boot_incarnation": "i-boot",
                "broker_incarnation": history.incarnation, "session_id": admission.identity[1],
                "deadline_ns": 0, "clock_domain": "monotonic", "claim_monotonic_ns": 0,
                "verdict": "ACCEPTED", "sequence": 1, "observed_ns": 0}
        with pytest.raises(Exception):
            registry.receipt(tx.handle, **late)
        assert registry.state_of(tx.handle) in ("UNKNOWN", "REVOKED"), (
            f"{name}: a late receipt revived the permit")


def test_port_close_failure_is_recorded_and_leaves_the_transaction_unusable():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)

    def failing_close(reason="CLOSED"):
        raise OSError("close failed")

    port.close = failing_close

    def exploding_send(**kwargs):
        raise TimeoutError("send timed out")

    port.send = exploding_send
    state = _run(tx)
    assert state == "UNKNOWN"
    assert getattr(tx, "close_failed", False) is True, "a failed port close was swallowed as success"
    assert getattr(tx, "fencing_required", False) is True, "fencing need was not recorded"
    assert tx.failure, "no failure reason recorded"
    assert getattr(tx, "unusable", False) is True, "the transaction was not marked unusable"
    with pytest.raises(Exception):
        tx.run(stage="route_dispatch", role="arm", goal_uuid="g-2", target_digest="d-1",
               controller_generation=1, controller_incarnation="i")
