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
