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
