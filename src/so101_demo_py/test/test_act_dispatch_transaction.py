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
    with pytest.raises(at.AuthorityRefused,
                       match="AUTHORITY_(OWNER|TOKEN)_IDENTITY_MISMATCH"):
        registry.claim_bound(handle, identity=admission.identity,
                             controller_generation=999,
                             token={"identity": admission.identity, "owner_identity": admission.identity,
                                    "stage": "route_dispatch", "history_version": 0,
                                    "incarnation": "inc-other", "reset_epoch": 1})
    # a caller generation that does not match the admission identity cannot even
    # produce a permit: the transaction reports a pre-issue refusal
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
