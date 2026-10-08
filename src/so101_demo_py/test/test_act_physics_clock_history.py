"""The 500 Hz source clock must stay bound to every original physical sample."""

import pytest

from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk

from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory


NOW_NS = 10_000_000_000
SOURCE_BASE_NS = 9_900_000_000
STEP_NS = 2_000_000


def _sample(step, *, epoch=1):
    sample = PhysicsStepEvidence()
    sample.simulation_session_id = "clock-session"
    sample.reset_epoch = epoch
    sample.physics_step = step
    sample.simulation_time_s = step * .002
    sample.clock_interval_begin_monotonic_ns = SOURCE_BASE_NS + step * STEP_NS
    sample.clock_interval_end_monotonic_ns = (
        sample.clock_interval_begin_monotonic_ns + 200_000)
    sample.model_qpos = [.1, .2]
    sample.model_qvel = [.3]
    return sample


def _chunk(sequence, *samples):
    chunk = PhysicsStepEvidenceChunk()
    chunk.chunk_sequence = sequence
    chunk.simulation_session_id = "clock-session"
    chunk.reset_epoch = samples[0].reset_epoch
    chunk.first_physics_step = samples[0].physics_step
    chunk.last_physics_step = samples[-1].physics_step
    chunk.first_simulation_time_s = samples[0].simulation_time_s
    chunk.last_simulation_time_s = samples[-1].simulation_time_s
    chunk.samples = list(samples)
    return chunk


def _history(now):
    history = PhysicsClockHistory(
        "clock-session", nq=2, nv=1, max_age_s=.2,
        max_source_step_gap_ns=3_000_000, clock_ns=lambda: now[0])
    history.arm(1, source_floor_s=0.0)
    return history


def test_physics_clock_history_keeps_every_step_across_chunks_and_copies_readback():
    now = [NOW_NS]
    history = _history(now)
    assert history.accept_chunk(_chunk(0, *(_sample(step) for step in range(1, 6))))
    assert history.accept_chunk(_chunk(1, *(_sample(step) for step in range(6, 11))))
    frames = history.recent_with_receipts()
    assert [entry["sample"].physics_step for entry in frames] == list(range(1, 11))
    assert all(entry["received_monotonic_ns"] == NOW_NS for entry in frames)
    assert all(entry["command_authority"] is False for entry in frames)
    selected = history.step_at(7)
    assert tuple(selected["sample"].model_qpos) == (.1, .2)
    assert selected["sample"].clock_interval_begin_monotonic_ns == (
        SOURCE_BASE_NS + 7 * STEP_NS)
    selected["sample"].model_qpos[0] = 9.
    assert tuple(history.step_at(7)["sample"].model_qpos) == (.1, .2)


@pytest.mark.parametrize("damage", [
    "clock_zero", "clock_reversed", "clock_overlap", "clock_gap", "clock_future",
    "clock_stale", "sim_gap", "step_gap", "truncated", "empty_qpos",
    "evidence_loss", "publish_retry",
])
def test_physics_clock_history_latches_invalid_original_chunk(damage):
    now = [NOW_NS]
    history = _history(now)
    first, second = _sample(1), _sample(2)
    chunk = _chunk(0, first, second)
    if damage == "clock_zero":
        first.clock_interval_begin_monotonic_ns = 0
    elif damage == "clock_reversed":
        second.clock_interval_end_monotonic_ns = second.clock_interval_begin_monotonic_ns - 1
    elif damage == "clock_overlap":
        second.clock_interval_begin_monotonic_ns = first.clock_interval_end_monotonic_ns - 1
    elif damage == "clock_gap":
        second.clock_interval_begin_monotonic_ns += 4_000_000
        second.clock_interval_end_monotonic_ns += 4_000_000
    elif damage == "clock_future":
        second.clock_interval_begin_monotonic_ns = NOW_NS + 1
        second.clock_interval_end_monotonic_ns = NOW_NS + 2
    elif damage == "clock_stale":
        first.clock_interval_begin_monotonic_ns -= 300_000_000
        first.clock_interval_end_monotonic_ns -= 300_000_000
    elif damage == "sim_gap":
        second.simulation_time_s = .005
    elif damage == "step_gap":
        second.physics_step = 3
    elif damage == "truncated":
        second.truncated = True
    elif damage == "empty_qpos":
        second.model_qpos = []
    elif damage == "evidence_loss":
        chunk.evidence_loss = True
    else:
        chunk.failed_publish_attempts = 1
    with pytest.raises(ValueError):
        history.accept_chunk(chunk)
    assert history.hazard is not None
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(0, _sample(1)))


def test_physics_clock_history_rejects_chunk_sequence_gap_and_stale_readback():
    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(2, _sample(2)))
    assert history.hazard is not None
    history.arm(2, source_floor_s=0.0)
    history.accept_chunk(_chunk(0, _sample(1, epoch=2)))
    now[0] += 300_000_000
    with pytest.raises(ValueError):
        history.recent_with_receipts()
    with pytest.raises(ValueError):
        history.step_at(1)


def test_stale_readback_latches_the_epoch_instead_of_only_raising():
    """A readback that finds no fresh sample must close the epoch, not just raise."""

    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    assert history.hazard is None
    now[0] += 300_000_000
    with pytest.raises(ValueError):
        history.recent_with_receipts()
    assert history.hazard == "PHYSICS_CLOCK_STALE"
    # Sticky: a later chunk cannot revive an epoch whose readback already failed.
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(1, _sample(2)))
    assert history.hazard == "PHYSICS_CLOCK_STALE"


def _bounded_history(now, *, max_silence_s=.05, first_chunk_timeout_s=.1):
    history = PhysicsClockHistory(
        "clock-session", nq=2, nv=1, max_age_s=.2,
        max_source_step_gap_ns=3_000_000, max_silence_s=max_silence_s,
        first_chunk_timeout_s=first_chunk_timeout_s, clock_ns=lambda: now[0])
    return history


def test_first_chunk_deadline_latches_before_any_sample_arrives():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now)
    assert history.check_health() is False  # unarmed: no health claim yet
    history.arm(1, source_floor_s=0.0)
    assert history.check_health() is True
    now[0] += 150_000_000
    assert history.check_health() is False
    assert history.hazard == "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(0, _sample(1)))
    assert history.check_health() is False


def test_silence_after_a_fresh_chunk_latches_stickily():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now)
    history.arm(1, source_floor_s=0.0)
    history.accept_chunk(_chunk(0, _sample(1)))
    assert history.hazard is None
    assert history.check_health() is True
    now[0] += 60_000_000
    assert history.check_health() is False
    assert history.hazard == "PHYSICS_CLOCK_SILENT"
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(1, _sample(2)))
    assert history.hazard == "PHYSICS_CLOCK_SILENT"


def test_unbounded_history_makes_no_silence_claim():
    """Without explicit bounds the history must not invent a health verdict."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    now[0] += 5_000_000_000
    assert history.check_health() is True
    assert history.hazard is None


def test_first_chunk_deadline_equality_is_strict():
    """Exactly at the deadline is still healthy; one nanosecond later is not."""

    timeout_ns = 100_000_000
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now, first_chunk_timeout_s=timeout_ns / 1e9)
    history.arm(1, source_floor_s=0.0)
    armed_ns = now[0]
    now[0] = armed_ns + timeout_ns
    assert history.check_health() is True
    assert history.hazard is None
    now[0] = armed_ns + timeout_ns + 1
    assert history.check_health() is False
    assert history.hazard == "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"


def test_silence_deadline_equality_is_strict():
    silence_ns = 50_000_000
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now, max_silence_s=silence_ns / 1e9)
    history.arm(1, source_floor_s=0.0)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    now[0] = last_end_ns + silence_ns
    assert history.check_health() is True
    assert history.hazard is None
    now[0] = last_end_ns + silence_ns + 1
    assert history.check_health() is False
    assert history.hazard == "PHYSICS_CLOCK_SILENT"


def test_evidence_ready_requires_an_accepted_chunk_in_an_armed_healthy_epoch():
    """A healthy pre-first-chunk verdict is not evidence and must not authorize."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now)
    assert history.evidence_ready is False
    history.arm(1, source_floor_s=0.0)
    assert history.check_health() is True
    assert history.evidence_ready is False
    history.accept_chunk(_chunk(0, _sample(1)))
    assert history.evidence_ready is True
    now[0] += 60_000_000
    assert history.check_health() is False
    assert history.evidence_ready is False


def test_evidence_ready_turns_false_when_the_retained_window_goes_stale():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _history(now)  # already armed on epoch 1 with a zero floor
    history.accept_chunk(_chunk(0, _sample(1)))
    assert history.evidence_ready is True
    now[0] += 300_000_000
    assert history.evidence_ready is False


def test_step_at_copies_only_the_selected_sample(monkeypatch):
    """A targeted read must not deep-copy the whole fresh window."""

    import so101_demo.adapters.act.physics_clock_history as module

    calls = {"count": 0}
    real = module.copy.deepcopy

    def counting(value, *args, **kwargs):
        calls["count"] += 1
        return real(value, *args, **kwargs)

    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, *(_sample(step) for step in range(1, 11))))
    history.accept_chunk(_chunk(1, *(_sample(step) for step in range(11, 21))))
    monkeypatch.setattr(module.copy, "deepcopy", counting)
    selected = history.step_at(15)
    assert selected["sample"].physics_step == 15
    assert calls["count"] <= 2, calls["count"]
    calls["count"] = 0
    frames = history.recent_with_receipts()
    assert len(frames) == 20
    assert calls["count"] == 20


def test_expired_first_chunk_deadline_blocks_a_late_chunk_without_any_poll():
    """A delayed watchdog must not let a chunk revive an expired deadline."""

    timeout_ns = 100_000_000
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now, first_chunk_timeout_s=timeout_ns / 1e9)
    history.arm(1, source_floor_s=0.0)
    armed_ns = now[0]
    now[0] = armed_ns + timeout_ns
    assert history.accept_chunk(_chunk(0, _sample(1))) is True          # exactly at the deadline
    history = _bounded_history(now, first_chunk_timeout_s=timeout_ns / 1e9)
    history.arm(1, source_floor_s=0.0)
    armed_ns = now[0]
    now[0] = armed_ns + timeout_ns + 1
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(0, _sample(1)))
    assert history.hazard == "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"
    assert history.evidence_ready is False


def test_expired_silence_deadline_blocks_reads_and_late_chunks_without_any_poll():
    silence_ns = 50_000_000
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now, max_silence_s=silence_ns / 1e9)
    history.arm(1, source_floor_s=0.0)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    now[0] = last_end_ns + silence_ns
    assert history.recent_with_receipts()[0]["sample"].physics_step == 1   # exactly at the deadline
    now[0] = last_end_ns + silence_ns + 1
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_SILENT"):
        history.step_at(1)
    assert history.hazard == "PHYSICS_CLOCK_SILENT"
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(1, _sample(2)))
    assert history.hazard == "PHYSICS_CLOCK_SILENT"
    assert history.evidence_ready is False


def test_armed_epoch_without_evidence_cannot_serve_any_sample():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now)
    history.arm(1, source_floor_s=0.0)
    assert history.check_health() is True
    assert history.evidence_ready is False
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_UNAVAILABLE"):
        history.step_at(1)
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_UNAVAILABLE"):
        history.recent_with_receipts()


def test_selected_sample_expiring_before_use_closes_the_epoch():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    assert history.evidence_ready is True
    assert history.step_at(1)["sample"].physics_step == 1
    now[0] += 300_000_000
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STALE"):
        history.step_at(1)
    assert history.hazard == "PHYSICS_CLOCK_STALE"
    assert history.evidence_ready is False


def _jumping_clock(*values):
    """Clock that returns the given values in order, repeating the last one."""

    state = {"index": 0}

    def clock():
        index = min(state["index"], len(values) - 1)
        state["index"] += 1
        return values[index]

    return clock


def test_first_chunk_deadline_crossed_during_validation_is_rejected():
    """A deadline crossed while validating must not commit the first chunk."""

    timeout_ns = 100_000_000
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = _bounded_history(now, first_chunk_timeout_s=timeout_ns / 1e9)
    history.arm(1, source_floor_s=0.0)
    armed_ns = now[0]
    at_deadline = armed_ns + timeout_ns
    history.clock_ns = _jumping_clock(at_deadline, at_deadline + 5_000_000)
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(0, _sample(1)))
    assert history.hazard == "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"
    assert history.evidence_ready is False
    assert history.check_health() is False


def test_accept_chunk_rejects_a_sample_that_ages_out_during_validation():
    """The acceptance linearization point must revalidate sample age."""

    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    fresh_at_entry = last_end_ns + 190_000_000
    stale_at_confirm = last_end_ns + 250_000_000
    history.clock_ns = _jumping_clock(fresh_at_entry, stale_at_confirm)
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(1, _sample(2)))
    assert history.hazard is not None
    assert history.evidence_ready is False


def test_step_at_rejects_a_sample_that_ages_out_during_the_copy():
    """The readback linearization point must revalidate freshness."""

    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    history.clock_ns = _jumping_clock(last_end_ns + 190_000_000,
                                      last_end_ns + 250_000_000)
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STALE"):
        history.step_at(1)
    assert history.hazard == "PHYSICS_CLOCK_STALE"
    assert history.evidence_ready is False


def test_recent_with_receipts_rejects_a_window_that_ages_out_during_the_copy():
    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    history.clock_ns = _jumping_clock(last_end_ns + 190_000_000,
                                      last_end_ns + 250_000_000)
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STALE"):
        history.recent_with_receipts()
    assert history.hazard == "PHYSICS_CLOCK_STALE"


def test_history_validates_and_retains_the_owned_snapshot(monkeypatch):
    """Validation and retention must both apply to the copied sample.

    A caller that mutates the live message between validation and retention must
    not be able to change what the history accepts or keeps.
    """

    import so101_demo.adapters.act.physics_clock_history as module

    real = module.copy.deepcopy
    state = {"fired": False}

    def mutating(value, *args, **kwargs):
        owned = real(value, *args, **kwargs)
        if not state["fired"] and isinstance(value, module.PhysicsStepEvidence):
            state["fired"] = True
            value.model_qpos = [9.0, 9.0]
            value.physics_step = 999
        return owned

    now = [NOW_NS]
    history = _history(now)
    sample = _sample(1)
    monkeypatch.setattr(module.copy, "deepcopy", mutating)
    assert history.accept_chunk(_chunk(0, sample)) is True
    monkeypatch.setattr(module.copy, "deepcopy", real)
    retained = history.step_at(1)
    assert tuple(retained["sample"].model_qpos) == (.1, .2)
    assert retained["sample"].physics_step == 1


# ---- R6: recent_steps() is the copy-free twin of recent_with_receipts() ----

def _readback_outcome(history, call):
    try:
        result, error = call(history), None
    except ValueError as exc:
        result, error = None, str(exc)
    return (result, error, history.hazard, history.version,
            (history.last_refusal_facts or {}).get("reason"))


def _steps_of(entries):
    return tuple(entry["sample"].physics_step for entry in entries)


def _parity_history(case):
    now = [NOW_NS]
    history = _history(now)
    if case == "unavailable":
        return history
    history.accept_chunk(_chunk(0, *(_sample(step) for step in range(1, 11))))
    if case == "hazard":
        with pytest.raises(ValueError):
            history.accept_chunk(_chunk(5, _sample(11)))
    elif case == "partially_stale":
        now[0] += 115_000_000
    elif case == "all_stale":
        now[0] += 300_000_000
    elif case == "confirm_stale":
        last_end_ns = history._last_source_end_ns
        history.clock_ns = _jumping_clock(last_end_ns + 190_000_000,
                                          last_end_ns + 250_000_000)
    return history


@pytest.mark.parametrize("case", [
    "fresh", "partially_stale", "all_stale", "hazard", "unavailable", "confirm_stale"])
def test_recent_steps_matches_recent_with_receipts_including_side_effects(case):
    full = _readback_outcome(_parity_history(case),
                             lambda h: _steps_of(h.recent_with_receipts()))
    steps = _readback_outcome(_parity_history(case), lambda h: h.recent_steps())
    assert steps == full, (case, steps, full)
    if case == "fresh":
        assert steps[0] == tuple(range(1, 11))
    if case == "partially_stale":
        assert 0 < len(steps[0]) < 10
    if case in ("all_stale", "confirm_stale"):
        assert steps[1] == "PHYSICS_CLOCK_STALE" and steps[2] == "PHYSICS_CLOCK_STALE"
    if case == "unavailable":
        assert steps[1] == "PHYSICS_CLOCK_UNAVAILABLE"


def test_recent_steps_makes_no_deepcopy(monkeypatch):
    import copy
    history = _parity_history("fresh")
    calls = []
    real = copy.deepcopy
    monkeypatch.setattr(copy, "deepcopy", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert history.recent_steps() == tuple(range(1, 11))
    assert calls == []
    assert len(history.recent_with_receipts()) == 10 and calls


# ---- A2a: the Teacher's own history audits raw-stream completeness instead of latching it ----

def _audit_history(now, **kwargs):
    history = PhysicsClockHistory(
        "clock-session", nq=2, nv=1, max_age_s=.2, max_source_step_gap_ns=3_000_000,
        clock_ns=lambda: now[0], audit_integrity=True, **kwargs)
    history.arm(1, source_floor_s=0.0)
    return history


def _steps(history):
    return [entry["sample"].physics_step for entry in history.recent_with_receipts()]


def test_audit_history_keeps_the_stream_through_a_lost_chunk_and_records_the_gap():
    now = [NOW_NS]
    history = _audit_history(now)
    assert history.accept_chunk(_chunk(0, *(_sample(step) for step in range(1, 6)))) is True
    # chunk 1 (steps 6-8) was lost: sequence, step, sim-time and source-clock gaps
    assert history.accept_chunk(_chunk(2, *(_sample(step) for step in range(9, 14)))) is True
    assert history.hazard is None and history.evidence_ready
    assert _steps(history) == [1, 2, 3, 4, 5, 9, 10, 11, 12, 13]
    audit = history.integrity_audit()
    assert audit["count"] >= 2
    assert {"PHYSICS_CHUNK_SCOPE_OR_LOSS", "PHYSICS_CHUNK_STEP_GAP"} <= set(audit["reasons"])
    assert history.accept_chunk(_chunk(3, *(_sample(step) for step in range(14, 16)))) is True
    assert history.hazard is None
    receipt = history.commit_receipt(expected_version=None, expected_incarnation=history.incarnation,
                                     expected_epoch=1, step=12, max_age_ns=history.max_age_ns)
    assert receipt["step"] == 12


def test_audit_history_accepts_truncated_and_hazard_marked_samples_without_latching():
    now = [NOW_NS]
    history = _audit_history(now)
    truncated, breached = _sample(1), _sample(2)
    truncated.truncated = True
    breached.diagnostic_hazard_breached = True
    assert history.accept_chunk(_chunk(0, truncated, breached)) is True
    assert history.hazard is None and _steps(history) == [1, 2]
    reasons = history.integrity_audit()["reasons"]
    assert "PHYSICS_SAMPLE_TRUNCATED" in reasons and "PHYSICS_SAMPLE_HAZARD_MARKED" in reasons
    # the retained original keeps its markers for the force supervision and the selection
    assert history.step_at(1)["sample"].truncated is True


def test_audit_history_skips_a_malformed_chunk_without_latching_and_recovers():
    now = [NOW_NS]
    history = _audit_history(now)
    assert history.accept_chunk(_chunk(0, _sample(1), _sample(2))) is True
    bad = _sample(3)
    bad.model_qpos = [.1]  # wrong model width
    assert history.accept_chunk(_chunk(1, bad)) is False
    assert history.hazard is None and _steps(history) == [1, 2]
    assert history.integrity_audit()["reasons"].get("PHYSICS_SAMPLE_INVALID") == 1
    assert history.accept_chunk(_chunk(2, _sample(4), _sample(5))) is True
    assert _steps(history) == [1, 2, 4, 5]


def test_audit_history_never_accepts_a_duplicate_or_backward_step():
    now = [NOW_NS]
    history = _audit_history(now)
    assert history.accept_chunk(_chunk(0, *(_sample(step) for step in range(1, 6)))) is True
    assert history.accept_chunk(_chunk(1, *(_sample(step) for step in range(3, 8)))) is False
    assert history.hazard is None and _steps(history) == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("fault", ["session", "epoch"])
def test_audit_history_still_latches_a_session_or_epoch_identity_fault(fault):
    now = [NOW_NS]
    history = _audit_history(now)
    chunk = _chunk(0, _sample(1))
    if fault == "session":
        chunk.simulation_session_id = "foreign-session"
    else:
        chunk.reset_epoch = 2
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_HISTORY_INVALID"):
        history.accept_chunk(chunk)
    assert history.hazard == "PHYSICS_CHUNK_SCOPE_OR_LOSS"


def test_audit_history_staleness_is_transient_and_a_fresh_chunk_recovers_it():
    now = [NOW_NS]
    history = _audit_history(now)
    assert history.accept_chunk(_chunk(0, _sample(1), _sample(2))) is True
    version = history.version
    now[0] = NOW_NS + 300_000_000
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STALE"):
        history.recent_with_receipts()
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STALE"):
        history.step_at(1)
    assert history.hazard is None and history.version == version
    late = _sample(3)
    late.clock_interval_begin_monotonic_ns = now[0] - 1_000_000
    late.clock_interval_end_monotonic_ns = now[0] - 800_000
    assert history.accept_chunk(_chunk(1, late)) is True
    assert _steps(history) == [3]
    assert history.integrity_audit()["reasons"].get("PHYSICS_CLOCK_STALE", 0) >= 1


def test_audit_history_silence_and_first_chunk_deadlines_do_not_latch():
    now = [NOW_NS]
    history = _audit_history(now, max_silence_s=.3, first_chunk_timeout_s=.4)
    now[0] = NOW_NS + 500_000_000
    assert history.check_health() is True and history.hazard is None
    assert history.integrity_audit()["reasons"].get("PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT") == 1
    assert history.check_health() is True
    assert history.integrity_audit()["reasons"].get("PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT") == 1


def test_audit_history_classifies_external_latch_requests():
    now = [NOW_NS]
    history = _audit_history(now)
    for reason in ("PHYSICS_CHUNK_CALLBACK_INVALID", "PHYSICS_CHUNK_PREARM_LOSS"):
        history.latch(reason)
        assert history.hazard is None
    assert history.integrity_audit()["count"] == 2
    history.latch("PHYSICS_SOURCE_SUPERVISION_FAILED")
    assert history.hazard == "PHYSICS_SOURCE_SUPERVISION_FAILED"
    strict = _history([NOW_NS])
    strict.latch("PHYSICS_CHUNK_PREARM_LOSS")
    assert strict.hazard == "PHYSICS_CHUNK_PREARM_LOSS"


def test_commit_receipt_ignores_the_version_only_when_none_is_given():
    now = [NOW_NS]
    history = _audit_history(now)
    assert history.accept_chunk(_chunk(0, _sample(1), _sample(2))) is True
    version = history.version
    assert history.accept_chunk(_chunk(1, _sample(3))) is True
    kwargs = dict(expected_incarnation=history.incarnation, expected_epoch=1, step=2,
                  max_age_ns=history.max_age_ns)
    assert history.commit_receipt(expected_version=None, **kwargs)["version"] == history.version
    with pytest.raises(ValueError, match="PHYSICS_COMMIT_VERSION_CHANGED"):
        history.commit_receipt(expected_version=version, **kwargs)
    with pytest.raises(ValueError, match="PHYSICS_COMMIT_INCARNATION_CHANGED"):
        history.commit_receipt(expected_version=None, **{**kwargs, "expected_incarnation": "other"})
    with pytest.raises(ValueError, match="PHYSICS_COMMIT_INCARNATION_CHANGED"):
        history.commit_receipt(expected_version=None, **{**kwargs, "expected_epoch": 2})


def test_step_at_accepts_an_explicit_longer_freshness_bound_and_keeps_the_default():
    # A2b: the Teacher proofs read a step with the Teacher state age; the default stays the history age.
    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    now[0] += 150_000_000  # the sample is about 248 ms old; the history age is 200 ms
    assert history.step_at(1, max_age_ns=500_000_000)["sample"].physics_step == 1
    assert history.hazard is None
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STALE"):
        history.step_at(1)
    assert history.hazard == "PHYSICS_CLOCK_STALE"


@pytest.mark.parametrize("bound", [0, -1, 1.5, True, "x"])
def test_step_at_rejects_an_invalid_explicit_freshness_bound(bound):
    now = [NOW_NS]
    history = _history(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    with pytest.raises(ValueError, match="max_age_ns invalid"):
        history.step_at(1, max_age_ns=bound)
    assert history.hazard is None
