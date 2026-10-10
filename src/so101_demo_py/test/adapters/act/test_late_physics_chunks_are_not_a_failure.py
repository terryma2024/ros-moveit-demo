"""A late chunk (a user-authorized data-contract change) is no longer a failure of the data.

OLD rule (removed): every chunk had to reach the Recorder within 100 ms of its newest sample's begin, else the data was INVALID
(PHYSICS_RAW_CLOCK_INVALID, permanent). Measured: a single chunk 283 ms late, 26 chunks into a run, ended the L2 recording; the delay
is the end-to-end sample -> publish thread -> DDS -> spooler path, outside the Recorder's control, and the spooler does no real-time
intervention. NEW rule: lateness is admitted and recorded (telemetry); the data fails on what actually endangers it:
  - continuity (sequence, step contiguity, clocks), session/epoch and every content check: unchanged;
  - processing errors: refused content, overflow;
  - receiver lag beyond the frozen policy (newest received sample behind now > X s).
The spool backlog bound and the spool tests went with the chunk spool process (cleanup step 2).
"""
import copy
from types import SimpleNamespace

import pytest

from test_act_raw_physics_chunks import _chunk

STEP_NS = 2_000_000


def chunk_at(index, *, delay_ms=0.0):
    """Chunk number `index` (1-based): 5 steps, continuous in steps and clocks, delivered `delay_ms` after its newest sample began."""
    first = 101 + (index - 1) * 5
    base = 10_000_000_000 + (index - 1) * 5 * STEP_NS
    message = _chunk(sequence=index, first=first, receipt=base + 16_000_000)
    for offset, sample in enumerate(message.samples):
        begin = base + offset * STEP_NS
        sample.clock_interval_begin_monotonic_ns, sample.clock_interval_end_monotonic_ns = begin, begin + 1_800_000
    message.handoff_monotonic_ns = message.samples[-1].clock_interval_end_monotonic_ns + 100_000
    message.publish_monotonic_ns = message.handoff_monotonic_ns + 200_000
    return message, message.samples[-1].clock_interval_begin_monotonic_ns + 3_000_000 + int(delay_ms * 1e6)


def adapter(**kw):
    from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
    appended = []
    node = SimpleNamespace(create_subscription=lambda *a: "owned", destroy_subscription=lambda v: None)
    clock = kw.pop("clock", lambda: 0)
    value = RosEpisodePhysicsAdapter(node, session_id="live-source", reset_epoch=2, nq=2, nv=1,
        audit=SimpleNamespace(append_raw_physics=lambda record: appended.append(copy.deepcopy(record))),
        clock_ns=clock, **kw)
    return value, appended


def feed(value, index, *, delay_ms=0.0):
    """Deliver chunk `index`; a chunk behind a late one arrives right after it (receipts are in arrival order)."""
    message, receipt = chunk_at(index, delay_ms=delay_ms)
    receipt = max(receipt, getattr(value, "_test_last_receipt", 0) + 100_000)
    value._test_last_receipt = receipt
    value.accept_message(message, receipt_ns=receipt)


def test_a_300_ms_late_chunk_is_admitted_audited_and_recorded_as_lateness():
    value, appended = adapter()
    feed(value, 1)
    feed(value, 2, delay_ms=300.0)                       # the L2 case, bigger
    feed(value, 3)
    value.drain()
    assert value.hazard is None
    assert [record["chunk"]["chunk_sequence"] for record in appended] == [1, 2, 3]
    diagnostics = value.receipt_diagnostics()
    assert diagnostics["late_count"] >= 1 and diagnostics["max_delay_ms"] == pytest.approx(303.0, abs=1.0)
    assert diagnostics["latency_ms"]["total"]["max"] == pytest.approx(303.0, abs=1.0)


def test_a_late_first_chunk_is_admitted_too():
    value, appended = adapter()
    feed(value, 1, delay_ms=850.0)
    feed(value, 2)
    value.drain()
    assert value.hazard is None and len(appended) == 2
    assert value.receipt_diagnostics()["late_count"] >= 1


@pytest.mark.parametrize("case", ["sequence_gap", "step_gap", "foreign_session", "foreign_epoch", "source_loss"])
def test_continuity_session_and_content_checks_are_unchanged(case):
    value, _ = adapter()
    feed(value, 1)
    message, receipt = chunk_at(2)
    expected = "PHYSICS_RAW_CONTINUITY_INVALID"
    if case == "sequence_gap":
        message, receipt = chunk_at(3)                  # chunk 2 never arrived
    elif case == "step_gap":
        message.chunk_sequence = 2
        for sample in message.samples:
            sample.physics_step += 1                    # sequence contiguous, steps are not
        message.first_physics_step += 1
        message.last_physics_step += 1
    elif case == "foreign_session":
        message.simulation_session_id = "other"
        expected = "PHYSICS_RAW_SCOPE_INVALID"
    elif case == "foreign_epoch":
        message.reset_epoch = 3
        expected = "PHYSICS_RAW_SCOPE_INVALID"
    else:
        message.failed_publish_attempts = 1
        expected = "PHYSICS_RAW_SOURCE_LOSS"
    value.accept_message(message, receipt_ns=receipt)
    assert value.hazard == expected


def test_a_receipt_before_the_samples_ended_is_still_refused_as_a_clock_defect():
    """Not lateness: a receipt earlier than the chunk's own sample end cannot be a receipt."""
    value, _ = adapter()
    message, receipt = chunk_at(1)
    value.accept_message(message, receipt_ns=message.samples[-1].clock_interval_begin_monotonic_ns)
    assert value.hazard == "PHYSICS_RAW_CLOCK_INVALID"


def test_the_receiver_lag_policy_fails_the_data_when_the_newest_received_sample_is_too_far_behind_now():
    now = [10_000_000_000 + 40_000_000]
    value, appended = adapter(clock=lambda: now[0], receiver_lag_max_s=2.0)
    feed(value, 1)
    value.drain()
    now[0] += 1_900_000_000                               # 1.9 s behind: inside the policy
    value.drain()
    assert value.hazard is None
    now[0] += 200_000_000                                 # 2.1 s behind: outside
    with pytest.raises(ValueError, match="PHYSICS_RAW_RECEIVER_LAG_EXCEEDED"):
        value.drain()
    assert value.hazard == "PHYSICS_RAW_RECEIVER_LAG_EXCEEDED"


def test_the_lag_check_ends_with_the_recording_and_never_runs_before_the_first_chunk():
    now = [10_000_000_000]
    value, _ = adapter(clock=lambda: now[0], receiver_lag_max_s=2.0)
    now[0] += 60_000_000_000
    value.drain()                                         # no chunk yet: nothing is behind
    assert value.hazard is None
    feed(value, 1)
    value.end_lag_check()                                 # the recording ended: the simulation may stop publishing
    now[0] += 60_000_000_000
    value.drain()
    assert value.hazard is None


def test_the_latency_split_reports_percentiles_for_every_leg():
    value, _ = adapter()
    for index in range(1, 21):
        feed(value, index, delay_ms=index * 1.0)
    split = value.receipt_diagnostics()["latency_ms"]
    assert set(split) == {"sample_to_handoff", "handoff_to_publish", "publish_to_receipt", "total"}
    for name, block in split.items():
        assert set(block) == {"count", "p50", "p90", "p99", "max"} and block["count"] == 20, name
    assert split["handoff_to_publish"]["max"] == pytest.approx(0.2, abs=0.01)
    assert split["publish_to_receipt"]["max"] > split["publish_to_receipt"]["p50"] > 0
    assert split["total"]["max"] >= split["total"]["p99"] >= split["total"]["p90"] >= split["total"]["p50"]
    assert value.receipt_diagnostics()["max_publish_deferrals_total"] == 0


def test_a_chunk_from_a_plugin_that_does_not_stamp_has_no_split_but_the_total():
    value, _ = adapter()
    message, receipt = chunk_at(1)
    message.handoff_monotonic_ns = message.publish_monotonic_ns = 0
    value.accept_message(message, receipt_ns=receipt)
    split = value.receipt_diagnostics()["latency_ms"]
    assert split["total"]["count"] == 1 and split["publish_to_receipt"]["count"] == 0
