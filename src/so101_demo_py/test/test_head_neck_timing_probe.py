"""Separate startup reset discontinuities from the measured holding epoch."""
from head_neck_timing_probe import continuous_updates


def row(update_id, simulation_ns, started_ns):
    return (1, 0, 3, update_id, update_id, 0, simulation_ns, 2_000_000,
            started_ns, started_ns + 1000, 1)


def test_startup_reset_before_holding_does_not_count_as_a_holding_gap():
    updates = [row(1, 2_000_000, 10), row(2, 62_000_000, 20),
               row(3, 64_000_000, 30), row(4, 66_000_000, 40)]
    assert continuous_updates(updates, 30, 40)


def test_holding_simulation_gap_is_refused():
    updates = [row(1, 2_000_000, 10), row(2, 62_000_000, 20)]
    assert not continuous_updates(updates, 10, 20)


def test_any_missing_completed_update_id_is_refused():
    updates = [row(1, 2_000_000, 10), row(3, 4_000_000, 20)]
    assert not continuous_updates(updates, 20, 20)


def test_the_collector_based_hold_probe_refuses_to_run():
    import pytest
    from head_neck_timing_probe import main
    with pytest.raises(RuntimeError, match='HEAD_TIMING_COLLECTOR_REMOVED'):
        main()
