"""EXP-572 behavioral RED: the history final window must be inside the boundary.

Review 9 reproduced that after ``history.commit_receipt`` returned, another thread
could latch a hazard or advance the selected age past its bound and the running
transaction still accepted. These probes race exactly that window through the real
OfflineDispatchTransaction and must fail while the window is open.
"""

import threading

from test_act_dispatch_transaction import _auth_helpers, _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


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
        receipt = original(**kwargs)
        # another thread latches a hazard the instant the commit returns
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


def test_selected_age_crossing_after_the_commit_still_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    original = admission.history_commit_receipt
    last_end_ns = history._last_source_end_ns

    def commit_then_age_out(**kwargs):
        receipt = original(**kwargs)
        now[0] = last_end_ns + 250_000_000      # selected age crosses the 50 ms bound
        return receipt

    admission.history_commit_receipt = commit_then_age_out
    state = _run(tx)
    assert state in ("REJECTED", "UNKNOWN"), (
        f"a selected-age crossing inside the history window was ignored: state={state} "
        f"accepted_commands={port.accepted_commands}")
    assert port.accepted_commands == 0


# --- P1.2: full identity / generation binding and immutable scalar freezing ---


def test_owner_generation_one_with_rearmed_controller_and_caller_999_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    port.arm_generation(999, controller_incarnation="i")
    state = _run(tx, controller_generation=1)      # caller believes gen 1
    assert state == "REJECTED", state
    assert port.reserve_calls == 0 and port.accepted_commands == 0
    # a caller that simply agrees with the rearmed controller is still not authority:
    # the generation must equal the admission identity generation, so issuing the
    # permit itself refuses
    import pytest

    with pytest.raises(Exception):
        tx.run(stage="route_dispatch", role="arm", goal_uuid="g-1", target_digest="d-1",
               controller_generation=999, controller_incarnation="i")


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
