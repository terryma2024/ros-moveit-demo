"""EXP-573 behavioral RED: one timestamp, one receipt.

Review 10 reproduced that after the *final* history validation the code still
called ``owner_is_active()`` and then rechecked only the permit deadline, so time
advancing inside that window could push the selected age to 250 ms (bound 50 ms)
and the transaction still accepted. A second probe showed the persisted claim
instant was the *first* receipt's time, not the final check's.

These probes exercise exactly those two windows through the real transaction.
"""

import threading

from test_act_dispatch_transaction import _run, _transaction
from test_act_physics_clock_history import SOURCE_BASE_NS, STEP_NS


def test_selected_age_advancing_after_the_last_history_check_refuses():
    """Time advancing inside the post-history window must not create an acceptance."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    entered = threading.Event()
    release = threading.Event()
    original_owner_is_active = admission.owner_is_active

    def owner_is_active_probe():
        result = original_owner_is_active()
        entered.set()
        release.wait(5.0)
        return result

    admission.owner_is_active = owner_is_active_probe
    outcome = {}

    def worker():
        try:
            outcome["state"] = _run(tx)
        except Exception as error:  # noqa: BLE001
            outcome["error"] = repr(error)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(5.0), "the post-history window was never entered"
    # selected freshness bound is 50 ms for this fixture; push it to 250 ms
    now[0] = history._last_source_end_ns + 250_000_000
    release.set()
    thread.join(10.0)
    assert not thread.is_alive(), "the transaction thread must terminate"
    assert "error" not in outcome, outcome
    assert outcome["state"] in ("REJECTED", "UNKNOWN"), (
        f"time advanced past the selected-age bound after the last history check yet the "
        f"transaction returned {outcome['state']} with accepted_commands={port.accepted_commands}")
    assert port.accepted_commands == 0


def test_persisted_claim_instant_is_the_final_history_validation_time():
    """The stored claim instant must be the single final validation time."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    original = admission.history_commit_receipt
    seen = []

    def recording_commit(**kwargs):
        receipt = original(**kwargs)
        seen.append(receipt["commit_monotonic_ns"])
        now[0] += 1_000_000            # time moves between checks
        return receipt

    admission.history_commit_receipt = recording_commit
    state = _run(tx)
    if state == "ACCEPTED":
        stored = registry._claim_instant.get(tx.handle.permit_id)
        assert stored == seen[-1], (
            f"persisted claim instant {stored} is not the final history validation time {seen[-1]}")
    else:
        # refusing is also acceptable, but then no claim instant may be persisted
        assert registry._claim_instant.get(tx.handle.permit_id) is None
