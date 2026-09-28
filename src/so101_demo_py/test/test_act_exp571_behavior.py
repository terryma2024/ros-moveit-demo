"""EXP-571 deterministic behavioral probes for the review-8 blockers.

Each test reproduces an externally observable unsafe behavior through the real
OfflineDispatchTransaction. They must fail on the pre-EXP-571 revision and pass
on the fixed tree.
"""

import threading

import pytest

from test_act_dispatch_transaction import _run, _transaction


def test_revoke_at_the_atomic_claim_boundary_has_only_two_legal_serializations():
    """Real threads race a revoke against the claim boundary; only two outcomes are legal.

    A barrier is installed *inside* the boundary (the history commit runs under the
    admission lock). If a revoke can still complete there, the claim was not atomic
    and must not accept; if it cannot, the claim owns the boundary and later
    revocation must not retroactively create a second acceptance.
    """

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    entered = threading.Event()
    release = threading.Event()
    original = admission.history_commit_receipt

    def boundary_probe(*args, **kwargs):
        entered.set()
        release.wait(5.0)
        return original(*args, **kwargs)

    admission.history_commit_receipt = boundary_probe
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.setdefault("state", _run(tx)))
    worker.start()
    assert entered.wait(5.0), "the claim never entered the atomic boundary"
    revoker = threading.Thread(target=lambda: admission.revoke_current("CLIENT_REVOKED"))
    revoker.start()
    revoker.join(0.3)
    revoke_completed_inside = not revoker.is_alive()
    release.set()
    worker.join(10.0)
    revoker.join(10.0)
    if revoke_completed_inside:
        # the revoke won the race inside the boundary: no send may happen at all
        assert outcome["state"] in ("REJECTED", "UNKNOWN"), outcome
        assert port.send_calls == 0 and port.accepted_commands == 0
    else:
        # the claim owns the boundary: exactly one acceptance, and the later
        # revocation cannot manufacture another one
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
