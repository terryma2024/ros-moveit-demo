"""EXP-572 behavioral RED: the history final window must be inside the boundary.

Review 9 reproduced that after ``history.commit_receipt`` returned, another thread
could latch a hazard or advance the selected age past its bound and the running
transaction still accepted. These probes race exactly that window through the real
OfflineDispatchTransaction and must fail while the window is open.
"""

import threading
import time

from test_act_dispatch_transaction import _auth_helpers, _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS
from so101_demo.adapters.act.physics_clock_admission import AdmissionRefused


def _frozen_identity_probe(admission, registry, port, tx):
    """Common preconditions for the history-window probes."""

    state = _run(tx, stage="route_dispatch", role="arm", goal_uuid="g-1",
                 target_digest="d-1", controller_generation=1, controller_incarnation="i",
                 stop_at=None)
    return state


def test_hazard_latched_after_the_commit_still_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    original = admission.history_commit_receipt

    def commit_then_latch(**kwargs):
        # a re-entrant mutation inside the wrapped call: the receipt is valid,
        # but the history state no longer matches it when the claim is about to
        # transition, which the state-consistency check must refuse
        receipt = original(**kwargs)
        with history._lock:
            if history.hazard is None:
                history.hazard = "PHYSICS_CLOCK_SILENT"
                history.version += 1
        return receipt

    admission.history_commit_receipt = commit_then_latch
    state = _run(tx)
    assert state in ("REJECTED", "UNKNOWN"), (
        f"a hazard latched inside the history window was ignored: state={state} "
        f"accepted_commands={port.accepted_commands}")
    assert port.accepted_commands == 0


def test_selected_age_crossing_at_the_final_commit_refuses():
    """The clock may cross the selected-age bound at the *one* final commit.

    Coverage for a clock change after the declared linearization point lives in
    the EXP-573 owner-window probe; by design a post-linearization clock change
    does not retroactively invalidate the transition.
    """

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    original = admission.history_commit_receipt
    last_end_ns = history._last_source_end_ns

    def age_out_before_the_validation(**kwargs):
        # still inside the single final commit: the selection is older than the
        # 50 ms bound when the history-owned timestamp is taken
        now[0] = last_end_ns + 250_000_000
        return original(**kwargs)

    admission.history_commit_receipt = age_out_before_the_validation
    state = _run(tx)
    assert state in ("REJECTED", "UNKNOWN"), (
        f"a selected-age crossing at the final commit was ignored: state={state} "
        f"accepted_commands={port.accepted_commands}")
    assert port.accepted_commands == 0


def test_owner_generation_one_with_rearmed_controller_and_caller_999_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    port.arm_generation(999, controller_incarnation="i")
    state = _run(tx, controller_generation=1)      # caller believes gen 1
    # both terminal refusals are safe; neither may accept or reach the controller
    assert state in ("REJECTED", "UNKNOWN"), state
    assert port.reserve_calls == 0 and port.accepted_commands == 0
    # a caller that simply agrees with the rearmed controller is still not authority:
    # the generation must equal the admission identity generation, so the permit is
    # never issued and the transaction reports a pre-issue refusal instead
    # a transaction is single-use, so the caller-generation case uses a fresh one
    _, admission2, registry2, port2, tx2 = _transaction([SOURCE_BASE_NS + 3 * STEP_NS])
    assert tx2.run(stage="route_dispatch", role="arm", goal_uuid="g-1", target_digest="d-1",
                   controller_generation=999, controller_incarnation="i") == "REJECTED"
    assert tx2.failure and "PERMIT_FIELDS" in tx2.failure


def test_token_identity_must_equal_the_record_identity():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    handle = registry.issue_handle(identity=admission.identity, stage="route_dispatch", step=1,
                                   history_version=history.snapshot()["version"],
                                   incarnation=history.incarnation, epoch=admission.identity[4],
                                   role="arm", controller_generation=1, goal_uuid="g-1",
                                   target_digest="d-1", controller_incarnation="i")
    forged = {"identity": ("ticket-other", "session-other", history.incarnation, 1, 1),
              "owner_identity": admission.identity, "stage": "route_dispatch",
              "history_version": history.snapshot()["version"],
              "incarnation": history.incarnation, "reset_epoch": admission.identity[4],
              "physics_step": 1}
    try:
        registry.capture_controller_identity(handle)
        registry.claim_bound(handle, identity=admission.identity, controller_generation=1,
                             token=forged)
    except Exception:
        pass
    else:
        raise AssertionError("a token whose identity differs from the record was accepted")
    assert port.reserve_calls == 0 and port.accepted_commands == 0


def test_mutable_target_digest_cannot_change_the_frozen_record():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    mutable = ["d", "-", "1"]
    try:
        handle = registry.issue_handle(identity=admission.identity, stage="route_dispatch", step=1,
                                      history_version=1, incarnation="i", epoch=admission.identity[4],
                                      role="arm", controller_generation=1, goal_uuid="g-1",
                                      target_digest=mutable, controller_incarnation="i")
    except Exception:
        return          # a strict type check at issue time is the correct refusal
    mutable.append("-mutated")
    raise AssertionError("a mutable target_digest was accepted and frozen by reference")


# --- P1.3: one irreversible failure closure ---


def test_missing_receipt_field_terminalizes_and_cannot_be_corrected():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    assert tx.run_to("receive", stage="route_dispatch", role="arm", goal_uuid="g-1",
                     target_digest="d-1", controller_generation=1,
                     controller_incarnation="i") == "IN_FLIGHT"
    good = dict(port.last_receipt(permit_id=tx.handle.permit_id))
    incomplete = {key: value for key, value in good.items() if key != "sequence"}
    try:
        registry.receipt(tx.handle, **incomplete)
    except Exception:
        pass
    else:
        raise AssertionError("a receipt missing a required field was accepted")
    assert registry.state_of(tx.handle) == "UNKNOWN", (
        "a field-set error left the permit live")
    try:
        registry.receipt(tx.handle, **good)
    except Exception:
        pass
    else:
        raise AssertionError("a corrected receipt revived a terminalized permit")
    assert registry.state_of(tx.handle) == "UNKNOWN"


def test_send_exception_terminalizes_transaction_registry_and_port():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)

    def exploding_send(**kwargs):
        raise TimeoutError("controller did not answer")

    port.send = exploding_send
    try:
        state = tx.run(stage="route_dispatch", role="arm", goal_uuid="g-1",
                       target_digest="d-1", controller_generation=1,
                       controller_incarnation="i")
    except TimeoutError:
        state = "ESCAPED"
    assert state != "ESCAPED", "the controller exception escaped the transaction"
    assert state in ("UNKNOWN", "REJECTED"), state
    assert registry.state_of(tx.handle) == state, (
        f"transaction {state} but registry {registry.state_of(tx.handle)}")
    assert port.cancel_stop_pending is True or port._close_first is True, "port was left open"


def test_claim_monotonic_ns_must_equal_the_recorded_claim_instant():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    assert tx.run_to("receive", stage="route_dispatch", role="arm", goal_uuid="g-1",
                     target_digest="d-1", controller_generation=1,
                     controller_incarnation="i") == "IN_FLIGHT"
    good = dict(port.last_receipt(permit_id=tx.handle.permit_id))
    shifted = dict(good, claim_monotonic_ns=good["claim_monotonic_ns"] + 1)
    try:
        registry.receipt(tx.handle, **shifted)
    except Exception:
        pass
    else:
        raise AssertionError("a claim timestamp off by 1 ns was accepted")
    assert registry.state_of(tx.handle) == "UNKNOWN"


def test_pre_issue_refusal_is_a_transaction_result_without_side_effects():
    """A refused permit issuance is a REJECTED outcome, not a terminalization."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    state = tx.run(stage="route_dispatch", role="arm", goal_uuid="g-1", target_digest="d-1",
                   controller_generation=1 + 1, controller_incarnation="i")
    assert state == "REJECTED", state
    assert tx.failure and "PERMIT_FIELDS" in tx.failure, tx.failure
    # no permit was issued, so nothing was terminalized and the controller
    # generation was left untouched
    assert tx.handle is None
    assert port.reserve_calls == 0 and port.send_calls == 0
    assert port._close_first is False and port.cancel_stop_pending is False


# --- P1.5: barriers inside the real I/O and copy call sites ---


def test_revoke_completes_while_the_real_controller_send_is_blocked():
    """The controller send happens outside every registry/admission/history lock."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    entered = threading.Event()
    release = threading.Event()
    original_send = port.send

    def blocking_send(**kwargs):
        entered.set()
        release.wait(5.0)
        return original_send(**kwargs)

    port.send = blocking_send
    outcome = {}

    def worker():
        try:
            outcome["state"] = _run(tx)
        except Exception as error:  # noqa: BLE001
            outcome["error"] = repr(error)

    worker = threading.Thread(target=worker)
    worker.start()
    assert entered.wait(5.0), "the real port.send was never entered"
    began = time.monotonic()
    admission.revoke_current("CLIENT_REVOKED")
    elapsed = time.monotonic() - began
    revoke_completed_while_blocked = elapsed < 0.1
    release.set()
    worker.join(10.0)
    assert not worker.is_alive(), "the transaction thread must terminate"
    assert revoke_completed_while_blocked, (
        f"revocation could not complete while the controller send was blocked: {elapsed:.3f}s")
    assert admission.revoked_record is not None
    assert "error" not in outcome, outcome
    assert outcome["state"] in ("ACCEPTED", "REJECTED", "UNKNOWN"), outcome


def test_revoke_completes_while_the_real_step_at_copy_is_blocked():
    """The barrier fires inside the real deepcopy that step_at performs.

    ``step_at`` copies the selected entry while holding the history lock; the
    admission lock is *not* held there, so revocation must still complete.
    """

    from so101_demo.adapters.act import physics_clock_history as history_module

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    entered = threading.Event()
    release = threading.Event()
    real_deepcopy = history_module.copy.deepcopy
    payload = {"samples": [{"step": index, "values": [index * 1.0] * 64} for index in range(2048)]}
    seen = {"calls": 0}

    def blocking_deepcopy(obj, *args, **kwargs):
        seen["calls"] += 1
        entered.set()
        release.wait(5.0)
        return real_deepcopy(obj, *args, **kwargs)

    history_module.copy.deepcopy = blocking_deepcopy
    outcome = {}

    def worker_body():
        try:
            outcome["result"] = admission.admit_sample(
                sample=__import__("test_act_physics_clock_admission",
                                  fromlist=["_sample"])._sample(1),
                ticket="clock-session", generation=1, reset_epoch=1)
        except Exception as error:  # noqa: BLE001 - asserted below
            outcome["error"] = error

    worker = threading.Thread(target=worker_body)
    try:
        worker.start()
        assert entered.wait(5.0), "the real deepcopy inside step_at was never entered"
        assert seen["calls"] >= 1
        began = time.monotonic()
        admission.revoke_current("CLIENT_REVOKED")
        elapsed = time.monotonic() - began
        assert elapsed < 0.1, (
            f"revocation blocked behind the real step_at copy: {elapsed:.3f}s")
        release.set()
        worker.join(10.0)
        assert not worker.is_alive(), "the admission worker must terminate"
        assert admission.revoked_record is not None
        assert "error" in outcome, outcome
        assert isinstance(outcome["error"], AdmissionRefused), outcome
    finally:
        release.set()
        history_module.copy.deepcopy = real_deepcopy
        worker.join(5.0)


