"""EXP-571 deterministic behavioral probes for the review-8 blockers.

Each test reproduces an externally observable unsafe behavior through the real
OfflineDispatchTransaction. They must fail on the pre-EXP-571 revision and pass
on the fixed tree.
"""

import threading

import pytest

from test_act_dispatch_transaction import (_auth_helpers, _run, _transaction)
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


def test_revoke_at_the_atomic_claim_boundary_has_only_two_legal_serializations():
    """Real threads race a revoke against the claim boundary; only two outcomes are legal.

    The probe wraps the real ``admission.owner_is_active``: it takes the original
    True observation, signals, then waits briefly for a real revoker thread before
    returning that saved observation. On the pre-fix revision no outer claim guard
    is held, so the revoke completes in that window and an acceptance afterwards is
    unsafe and must fail this test. On the fixed revision the admission claim guard
    is held across the owner read and READY -> IN_FLIGHT, so the revoke cannot
    complete during the wait: the claim wins with exactly one acceptance, and the
    later revocation cannot manufacture a second one.
    """

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    entered = threading.Event()
    revoked = threading.Event()
    observed = {}
    barrier_timeout = 0.3
    original_owner_is_active = admission.owner_is_active

    def owner_is_active_probe():
        result = original_owner_is_active()
        observed["owner_active"] = result
        entered.set()
        revoked.wait(barrier_timeout)          # bounded wait for the real revoker
        return result                          # saved observation, not a re-read

    admission.owner_is_active = owner_is_active_probe
    outcome = {}

    def worker_body():
        try:
            outcome["state"] = _run(tx)
        except Exception as error:              # noqa: BLE001 - recorded for the assertion
            outcome["error"] = repr(error)

    def revoker_body():
        admission.revoke_current("CLIENT_REVOKED")
        revoked.set()

    worker = threading.Thread(target=worker_body)
    revoker = threading.Thread(target=revoker_body)
    worker.start()
    assert entered.wait(5.0), "the claim never observed the owner as active"
    assert observed["owner_active"] is True
    revoker.start()
    worker.join(10.0)
    revoke_completed_inside = revoked.is_set()
    revoker.join(10.0)
    assert not worker.is_alive() and not revoker.is_alive(), "threads must terminate"
    assert "error" not in outcome, outcome
    assert outcome["state"] in ("ACCEPTED", "REJECTED", "UNKNOWN"), outcome
    if revoke_completed_inside:
        # the revoke won the race inside the boundary: no send may happen at all
        assert outcome["state"] in ("REJECTED", "UNKNOWN"), (
            f"revoke completed inside the claim boundary yet the transaction returned "
            f"{outcome['state']} with accepted_commands={port.accepted_commands}")
        assert port.send_calls == 0 and port.accepted_commands == 0, port.send_calls
    else:
        # the claim owns the boundary: exactly one acceptance, and the later
        # revocation cannot retroactively create another one
        assert outcome["state"] == "ACCEPTED", outcome
        assert port.accepted_commands == 1
    assert admission.revoked_record is not None


def test_legacy_claim_api_is_permanently_closed():
    _registry, _issue = _auth_helpers()
    registry = _registry()
    handle = _issue(registry)
    with pytest.raises(Exception, match="AUTHORITY_LEGACY_CLAIM_REMOVED"):
        registry.claim(handle)


def test_port_generation_is_the_authority_not_the_caller_integer():
    """Rearming the controller invalidates permits even if the caller agrees with itself."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    port.arm_generation(999, controller_incarnation="i")   # controller moved on
    state = _run(tx, controller_generation=1)              # caller still believes gen 1
    assert state == "REJECTED", state
    # the *claim* must refuse: no reservation may even be attempted, so the
    # refusal cannot be an accident of the fake's own generation check
    assert port.reserve_calls == 0, port.reserve_calls
    assert port.send_calls == 0 and port.accepted_commands == 0


def test_timeout_terminalizes_both_transaction_and_registry():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, _, registry, port, tx = _transaction(now)
    state = _run(tx, timeout_ns=-1)
    assert state == "UNKNOWN"
    assert registry.state_of(tx.handle) == "UNKNOWN"
    late = dict(port.last_receipt(permit_id=tx.handle.permit_id))
    with pytest.raises(Exception):
        registry.receipt(tx.handle, **late)
    assert registry.state_of(tx.handle) == "UNKNOWN"


def test_malformed_receipt_terminalizes_and_cannot_be_corrected():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, _, registry, port, tx = _transaction(now)
    assert _run(tx, stop_at="receive") == "IN_FLIGHT"
    good = dict(port.last_receipt(permit_id=tx.handle.permit_id))
    with pytest.raises(Exception):
        registry.receipt(tx.handle, **dict(good, sequence=-1))
    assert registry.state_of(tx.handle) == "UNKNOWN"
    with pytest.raises(Exception):
        registry.receipt(tx.handle, **good)
    assert registry.state_of(tx.handle) == "UNKNOWN"


def test_wrong_controller_boot_incarnation_is_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, _, registry, port, tx = _transaction(now)
    assert _run(tx, stop_at="receive") == "IN_FLIGHT"
    good = dict(port.last_receipt(permit_id=tx.handle.permit_id))
    with pytest.raises(Exception):
        registry.receipt(tx.handle, **dict(good, controller_boot_incarnation="someone-else"))


def test_last_receipt_is_a_frozen_read_only_receive_record():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, _, registry, port, tx = _transaction(now)
    assert _run(tx, stop_at="receive") == "IN_FLIGHT"
    first = port.last_receipt(permit_id=tx.handle.permit_id)
    observed = first["observed_ns"]
    now[0] += 5_000_000_000            # time passes; the record must not change
    second = port.last_receipt(permit_id=tx.handle.permit_id)
    assert second["observed_ns"] == observed
    assert second["sequence"] == first["sequence"]
    assert second["claim_monotonic_ns"] == first["claim_monotonic_ns"]
    with pytest.raises(Exception):
        second["verdict"] = "REJECTED"
    assert registry.receipt(tx.handle, **dict(second)) == "ACCEPTED"
