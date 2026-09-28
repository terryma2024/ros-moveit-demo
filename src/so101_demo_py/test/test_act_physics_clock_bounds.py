"""The frozen bounds must dominate their measured populations with a documented margin."""

import pytest

from so101_demo.adapters.act import physics_clock_bounds as bounds
from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory


NOW_NS = 10_000_000_000


def test_frozen_bounds_dominate_their_measured_maxima():
    assert bounds.SOURCE_STEP_GAP_NS >= bounds.OBSERVED_SOURCE_GAP_CONTEXT_NS * 2
    assert bounds.MAX_AGE_S * 1e9 >= bounds.OBSERVED_AGE_AT_VALIDATION_ENVELOPE_NS * 2
    assert bounds.OBSERVED_AGE_AT_VALIDATION_ENVELOPE_NS == (
        bounds.OBSERVED_AGE_AT_CALLBACK_ENTRY_NS + bounds.OBSERVED_CALLBACK_COST_NS)
    assert bounds.MAX_SILENCE_S * 1e9 >= bounds.OBSERVED_IN_WINDOW_CHUNK_GAP_NS * 2
    assert bounds.MAX_SILENCE_S * 1e9 < bounds.OBSERVED_RESET_CROSSING_GAP_NS * 2
    assert bounds.FIRST_CHUNK_TIMEOUT_S * 1e9 >= bounds.OBSERVED_FIRST_CHUNK_NS * 3
    for value in (bounds.MAX_AGE_S, bounds.MAX_SILENCE_S, bounds.FIRST_CHUNK_TIMEOUT_S):
        assert round(value * 1000) % 50 == 0, value


def test_history_factory_applies_every_frozen_bound():
    now = [NOW_NS]
    history = bounds.history_config(session_id="clock-session", nq=2, nv=1,
                                    clock_ns=lambda: now[0])
    assert isinstance(history, PhysicsClockHistory)
    assert history.max_age_ns == round(bounds.MAX_AGE_S * 1e9)
    assert history.max_source_step_gap_ns == bounds.SOURCE_STEP_GAP_NS
    assert history.max_silence_ns == round(bounds.MAX_SILENCE_S * 1e9)
    assert history.first_chunk_timeout_ns == round(bounds.FIRST_CHUNK_TIMEOUT_S * 1e9)
    assert history.evidence_ready is False


def test_history_factory_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        bounds.history_config(session_id="", nq=2, nv=1, clock_ns=lambda: NOW_NS)
