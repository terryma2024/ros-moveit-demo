"""Original postresume observation windows, never ACT authority or live proof."""

import copy

import pytest

from test_act_physics_clock_history import _sample, _chunk
from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory


def window():
    samples = [_sample(step) for step in range(101, 151)]
    for sample in samples:
        sample.clock_interval_begin_monotonic_ns -= 200_000_000
        sample.clock_interval_end_monotonic_ns -= 200_000_000
    return _chunk(7, *samples)


def reader():
    return PhysicsClockHistory("clock-session", nq=2, nv=1, max_age_s=.2,
        max_source_step_gap_ns=3_000_000, clock_ns=lambda: 10_010_000_000)


def test_new_observation_window_retains_actual_chunk_step_and_source_clock():
    history, original = reader(), window()
    before = copy.deepcopy(original)
    history.arm_original_window(original, after_monotonic_ns=9_890_000_000)
    assert original == before
    assert history.step_at(101)["sample"] == before.samples[0]
    assert history.step_at(150)["sample"] == before.samples[-1]
    assert len(history.recent_with_receipts()) == 50
    assert history.original_window_start["first_physics_step"] == 101
    assert history.original_window_start["first_chunk_sequence"] == 7
    assert history.original_window_start["command_authority"] is False
    with pytest.raises(TypeError):
        history.original_window_start["first_physics_step"] = 1
    with pytest.raises(ValueError):
        history.arm_original_window(original, after_monotonic_ns=9_890_000_000)
    with pytest.raises(ValueError):
        history.arm(2, source_floor_s=0.)


def test_original_window_checks_continuity_of_the_next_unchanged_chunk():
    history = reader()
    history.arm_original_window(window(), after_monotonic_ns=9_890_000_000)
    following = _sample(151)
    following.clock_interval_begin_monotonic_ns -= 200_000_000
    following.clock_interval_end_monotonic_ns -= 200_000_000
    assert history.accept_chunk(_chunk(8, following))
    assert history.step_at(151)["sample"] == following
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(10, _sample(153)))
    assert history.hazard is not None


@pytest.mark.parametrize("fault", ["pre_resume", "stale", "future", "clock_gap", "step_gap", "loss"])
def test_postresume_window_refuses_ineligible_or_incomplete_originals(fault):
    history, original = reader(), window()
    floor = 9_890_000_000
    if fault == "pre_resume":
        floor = original.samples[0].clock_interval_begin_monotonic_ns + 1
    if fault == "stale":
        for sample in original.samples:
            sample.clock_interval_begin_monotonic_ns -= 300_000_000
            sample.clock_interval_end_monotonic_ns -= 300_000_000
        floor -= 300_000_000
    if fault == "future":
        original.samples[-1].clock_interval_end_monotonic_ns = 10_010_000_001
    if fault == "clock_gap":
        original.samples[25].clock_interval_begin_monotonic_ns += 4_000_000
        original.samples[25].clock_interval_end_monotonic_ns += 4_000_000
    if fault == "step_gap":
        original.samples[25].physics_step += 1
    if fault == "loss":
        original.evidence_loss = True
    with pytest.raises(ValueError):
        history.arm_original_window(original, after_monotonic_ns=floor)
    # An attempted observation arm is terminal even when its first body fails.
    with pytest.raises(ValueError):
        history.arm_original_window(window(), after_monotonic_ns=9_890_000_000)
    with pytest.raises(ValueError):
        history.arm(2, source_floor_s=0.)
    assert history.hazard is not None


def test_ordinary_act_history_still_requires_original_reset_prefix():
    history = reader()
    history.arm(1, source_floor_s=0.)
    with pytest.raises(ValueError):
        history.accept_chunk(window())
    assert history.hazard is not None
