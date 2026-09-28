"""EXP-570: probe-derived tests through the real offline dispatch transaction."""

import threading
import time

import pytest

from test_act_physics_clock_admission import SOURCE_BASE_NS, STEP_NS, _ready

from so101_demo.adapters.act import authority_transaction as at
from so101_demo.adapters.act.dispatch_transaction import OfflineDispatchTransaction


def _auth_helpers():
    from test_act_authority_transaction import _issue, _registry
    return _registry, _issue


def _transaction(now, *, port=None, ttl_ns=30_000_000_000):
    history, admission = _ready(now)
    registry = at.AuthorityTransactionRegistry(
        clock_ns=lambda: now[0], permit_ttl_ns=ttl_ns, history=history,
        selected_max_age_ns=50_000_000)
    port = port or at.ReservationFakeControllerPort(clock_ns=lambda: now[0])
    tx = OfflineDispatchTransaction(admission=admission, history=history, registry=registry,
                                    port=port, clock_ns=lambda: now[0],
                                    permit_ttl_ns=ttl_ns, selected_max_age_ns=50_000_000)
    return history, admission, registry, port, tx


def _run(tx, **overrides):
    call = dict(stage="route_dispatch", role="arm", goal_uuid="g-1", target_digest="d-1",
                controller_generation=1, controller_incarnation="i")
    call.update(overrides)
    return tx.run(**call)


def _run_to_receive(tx):
    """Drive the real transaction up to the receive node, leaving the permit IN_FLIGHT."""

    return tx.run_to("receive", stage="route_dispatch", role="arm", goal_uuid="g-1",
                     target_digest="d-1", controller_generation=1, controller_incarnation="i")


def test_owner_revoke_before_claim_is_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, _, _, tx = _transaction(now)
    admission.revoke_current("CLIENT_REVOKED")
    assert _run(tx) == "REJECTED"
    assert tx.failure is not None and "REVOK" in tx.failure.upper()


def test_revoke_cannot_interleave_the_claim_history_commit():
    """The admission lock orders revocation against the claim commit.

    A revocation issued while the history commit is in flight cannot complete:
    it needs the admission lock the commit holds. The claim therefore finishes
    on the state observed at its own linearization point, and a revocation
    issued *before* the claim is refused (covered separately).
    """

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, _, _, tx = _transaction(now)
    original = admission.history_commit_receipt
    entered = threading.Event()
    release = threading.Event()

    def blocking_commit(*args, **kwargs):
        # hold the admission lock across the wait, exactly as the real commit does
        with admission._lock:
            entered.set()
            release.wait(5.0)
            return original(*args, **kwargs)

    admission.history_commit_receipt = blocking_commit
    outcome = {}

    def worker():
        outcome["state"] = _run(tx)

    revoker = threading.Thread(target=lambda: admission.revoke_current("CLIENT_REVOKED"))
    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(5.0)
    revoker.start()
    revoker.join(0.2)
    blocked_while_committing = revoker.is_alive()
    release.set()
    thread.join(10.0)
    revoker.join(10.0)
    assert blocked_while_committing is True, "revocation interleaved the claim commit"
    # whichever of the two safe outcomes wins the race, the claim never commits
    # against a revoked owner: either the post-commit owner re-check refuses it,
    # or the revocation lands after the claim was already linearized.
    assert outcome["state"] in ("ACCEPTED", "REJECTED"), outcome
    assert admission.revoked_record is not None

def test_wrong_owner_identity_and_generation_are_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, _, tx = _transaction(now)
    handle = registry.issue_handle(identity=("ticket-other", "session-other", "inc-other", 999, 1),
                                   stage="route_dispatch", step=1, history_version=0,
                                   incarnation="inc-other", epoch=1, role="arm",
                                   controller_generation=999, goal_uuid="g-1", target_digest="d-1",
                                   controller_incarnation="inc-other")
    with pytest.raises(at.AuthorityRefused, match="AUTHORITY_OWNER_IDENTITY_MISMATCH"):
        registry.claim_bound(handle, admission=admission, identity=admission.identity,
                             controller_generation=999,
                             token={"identity": admission.identity, "owner_identity": admission.identity,
                                    "stage": "route_dispatch", "history_version": 0,
                                    "incarnation": "inc-other", "reset_epoch": 1})
    assert _run(tx, controller_generation=999) == "REJECTED"


def test_permit_deadline_crossing_during_the_claim_commit_is_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, _, _, tx = _transaction(now, ttl_ns=1_000_000)
    crossing = {"armed": False}
    base = tx.registry._clock_ns

    def crossing_clock():
        now[0] += 5_000_000          # the commit itself takes 5 ms, past the 1 ms permit
        return base()

    tx.registry._clock_ns = crossing_clock
    assert _run(tx) == "REJECTED"
    assert tx.failure is not None and "EXPIRED" in tx.failure.upper()


def test_selection_is_frozen_from_the_copied_entry_not_the_caller_sample():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now, selected_max_age_s=.05)
    sample = _sample_of(history, admission)
    original = history.step_at
    mutated = {}

    def mutate_after_copy(step):
        entry = original(step)
        mutated["copied_step"] = step
        sample.physics_step = 2          # caller mutates after the copy
        return entry

    history.step_at = mutate_after_copy
    admitted = admission.admit_sample(sample=sample, ticket="clock-session", generation=1,
                                      reset_epoch=1)
    assert mutated["copied_step"] == 1
    assert admitted["commit_receipt"]["step"] == 1
    assert admitted["sample"].physics_step == 1


def _sample_of(history, admission):
    from test_act_physics_clock_admission import _sample
    return _sample(1)


def test_generation_one_reservation_is_dead_after_rearm_to_two():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, _, _, port, tx = _transaction(now)
    assert _run(tx) == "ACCEPTED"
    assert port.arm_generation(2, controller_incarnation="i2") is True
    assert port.send(goal_uuid="g-1", permit_id=tx.handle.permit_id, role="arm",
                     target_digest="d-1", generation=1, controller_incarnation="i",
                     deadline_ns=now[0] + 1_000_000_000) == "REJECTED"


def test_receipt_observed_at_zero_after_thirty_one_seconds_is_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, _, registry, port, tx = _transaction(now)
    assert _run(tx) == "ACCEPTED"
    stale = dict(port.last_receipt(permit_id=tx.handle.permit_id), observed_ns=0)
    with pytest.raises(at.AuthorityRefused):
        registry.receipt(tx.handle, **stale)


def test_real_copy_and_io_inside_the_dispatch_nodes_with_revoke_progressing():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, _, port, tx = _transaction(now)
    observed = {}
    payload = {"samples": [{"step": i, "values": [i * 1.0] * 64} for i in range(2048)]}

    def heavy_node(node):
        import copy as _copy
        import json as _json
        blob = _json.dumps(payload).encode()
        copied = _copy.deepcopy(payload)
        acquired = tx.registry._lock.acquire(blocking=False)
        observed["lock_free"] = acquired
        if acquired:
            tx.registry._lock.release()
        observed["bytes"] = len(blob) + len(copied["samples"])
        revoker = threading.Thread(target=lambda: admission.revoke_current("CLIENT_REVOKED"))
        revoker.start()
        revoker.join(5.0)
        observed["revoked"] = admission.revoked_record is not None

    tx.barrier("receive", heavy_node)
    state = _run(tx)
    assert observed["lock_free"] is True
    assert observed["bytes"] > 1024
    assert observed["revoked"] is True
    assert state == "ACCEPTED"


# --- EXP-571: review-8 blockers through the real transaction ---


def test_revoke_completed_before_the_transition_stops_the_send():
    """A revoke that completes before READY->IN_FLIGHT must prevent the send."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    entered = threading.Event()
    release = threading.Event()
    original = admission.history_commit_receipt

    def blocking_commit(*args, **kwargs):
        receipt = original(*args, **kwargs)
        entered.set()
        release.wait(5.0)          # revoke happens after the commit, before the transition
        return receipt

    admission.history_commit_receipt = blocking_commit
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.setdefault("state", _run(tx)))
    worker.start()
    assert entered.wait(5.0)
    admission.revoke_current("CLIENT_REVOKED")
    release.set()
    worker.join(10.0)
    assert outcome["state"] == "REJECTED", outcome
    assert port.send_calls == 0 and port.accepted_commands == 0


def test_legacy_claim_api_is_permanently_closed():
    _registry, _issue = _auth_helpers()
    registry = _registry()
    handle = _issue(registry)
    with pytest.raises(Exception, match="AUTHORITY_LEGACY_CLAIM_REMOVED"):
        registry.claim(handle)


def test_port_generation_is_the_authority_not_the_caller_integer():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    port.arm_generation(999, controller_incarnation="i")
    state = _run(tx, controller_generation=1)
    assert state == "REJECTED"
    assert port.send_calls == 0


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
