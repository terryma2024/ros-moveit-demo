"""After acceptance, the controller_state reference is compared with the sealed quintic (design section 2)."""

import math

import pytest

from so101_demo.adapters.act.head_reference_monitor import HeadReferenceMonitor

HEADER = 10_000_000_000
FIRST = 100_000_000          # first point offset from the header
DURATION = 1_000_000_000
Q0, Q1 = 0.1, 0.5
RADIUS = 0.0021


def proof(**change):
    value = dict(
        header_stamp_ns=HEADER, first_point_offset_ns=FIRST, last_point_offset_ns=FIRST + DURATION,
        typed_curve=dict(positions_rad=[Q0, Q1], times_from_start_ns=[FIRST, FIRST + DURATION]),
        collision=dict(prefix_envelope_rad=[Q0 - RADIUS, Q0 + RADIUS]),
        max_velocity_rad_s=1.0, max_acceleration_rad_s2=2.0)
    value.update(change)
    return value


def quintic(tau_ns, q0=Q0, q1=Q1, duration_ns=DURATION):
    s = min(max(tau_ns / duration_ns, 0.0), 1.0)
    position = q0 + (q1 - q0) * (10 * s**3 - 15 * s**4 + 6 * s**5)
    velocity = (q1 - q0) / (duration_ns * 1e-9) * (30 * s**2 - 60 * s**3 + 30 * s**4)
    return position, velocity


def sample(sim_ns, position, velocity):
    return dict(sim_ns=sim_ns, reference_position=position, reference_velocity=velocity)


def armed():
    monitor = HeadReferenceMonitor()
    monitor.arm(proof())
    return monitor


def test_the_exact_quintic_never_diverges_from_before_the_header_to_after_the_end():
    monitor = armed()
    for sim in range(HEADER - 50_000_000, HEADER + FIRST + DURATION + 200_000_000, 2_000_000):
        position, velocity = (Q0, 0.0) if sim < HEADER + FIRST else quintic(sim - HEADER - FIRST)
        assert monitor.observe(sample(sim, position, velocity)) is None
    assert monitor.diverged is None and monitor.observed > 500


@pytest.mark.parametrize('shift_ns', [-4_000_000, -2_000_000, 2_000_000, 4_000_000])
def test_a_one_or_two_tick_time_misalignment_is_tolerated(shift_ns):
    monitor = armed()
    for sim in range(HEADER + FIRST, HEADER + FIRST + DURATION, 2_000_000):
        position, velocity = quintic(sim - HEADER - FIRST + shift_ns)
        assert monitor.observe(sample(sim, position, velocity)) is None


def test_the_prefix_before_the_first_point_may_move_inside_the_envelope_only():
    monitor = armed()
    assert monitor.observe(sample(HEADER + 10_000_000, Q0 + 0.0019, 0.03)) is None
    verdict = monitor.observe(sample(HEADER + 12_000_000, Q0 + 0.0030, 0.03))
    assert verdict['code'] == 'HEAD_REFERENCE_DIVERGED' and verdict['phase'] == 'PREFIX'


def test_a_foreign_goal_that_moves_the_reference_off_the_quintic_diverges():
    monitor = armed()
    for sim in range(HEADER + FIRST, HEADER + FIRST + 300_000_000, 2_000_000):
        position, velocity = quintic(sim - HEADER - FIRST)
        assert monitor.observe(sample(sim, position, velocity)) is None
    position, velocity = quintic(300_000_000)
    verdict = monitor.observe(sample(HEADER + FIRST + 300_000_000, position - 0.05, velocity))
    assert verdict['code'] == 'HEAD_REFERENCE_DIVERGED' and verdict['phase'] == 'MOVING'
    assert verdict['deviation_rad'] > 0.04 and verdict['sim_ns'] == HEADER + FIRST + 300_000_000
    assert monitor.diverged == verdict
    # the first divergence is kept; later samples do not rewrite it
    assert monitor.observe(sample(HEADER + FIRST + 302_000_000, 9.0, 0.0)) == verdict


def test_after_the_end_the_reference_holds_the_final_point():
    monitor = armed()
    end = HEADER + FIRST + DURATION
    assert monitor.observe(sample(end + 2_000_000, Q1, 0.0)) is None
    assert monitor.observe(sample(end + 4_000_000, Q1 + 0.5e-6, 0.0)) is None
    verdict = monitor.observe(sample(end + 6_000_000, Q1 + 0.01, 0.0))
    assert verdict['phase'] == 'HOLD'


def test_a_reference_velocity_above_the_limit_diverges_even_on_the_curve():
    monitor = armed()
    verdict = monitor.observe(sample(HEADER + FIRST + 500_000_000, quintic(500_000_000)[0], 1.2))
    assert verdict['code'] == 'HEAD_REFERENCE_DIVERGED' and verdict['reason'] == 'VELOCITY'


@pytest.mark.parametrize('bad', [math.nan, math.inf])
def test_a_non_finite_reference_diverges(bad):
    monitor = armed()
    assert monitor.observe(sample(HEADER + FIRST, bad, 0.0))['reason'] == 'NON_FINITE'


def test_nothing_is_checked_before_arming_after_disarming_or_for_a_stale_goal():
    monitor = HeadReferenceMonitor()
    assert monitor.observe(sample(HEADER, 99.0, 0.0)) is None
    monitor.arm(proof())
    monitor.disarm()
    assert monitor.observe(sample(HEADER, 99.0, 0.0)) is None and monitor.observed == 0


def test_rearming_replaces_the_goal_and_clears_the_verdict():
    monitor = armed()
    monitor.observe(sample(HEADER + FIRST + 500_000_000, 9.0, 0.0))
    assert monitor.diverged is not None
    monitor.arm(proof(header_stamp_ns=HEADER + 5_000_000_000))
    assert monitor.diverged is None
    assert monitor.observe(sample(HEADER + 5_000_000_000, Q0, 0.0)) is None


def test_an_invalid_proof_is_refused():
    for change in (dict(header_stamp_ns=-1), dict(typed_curve=dict(positions_rad=[Q0], times_from_start_ns=[0])),
                   dict(collision={})):
        with pytest.raises(ValueError, match='REFERENCE_MONITOR_PROOF_INVALID'):
            HeadReferenceMonitor().arm(proof(**change))


def test_the_callback_receives_the_first_divergence_once():
    seen = []
    monitor = HeadReferenceMonitor(on_diverged=seen.append)
    monitor.arm(proof())
    monitor.observe(sample(HEADER + FIRST + 500_000_000, 9.0, 0.0))
    monitor.observe(sample(HEADER + FIRST + 502_000_000, 9.0, 0.0))
    assert len(seen) == 1 and seen[0]['code'] == 'HEAD_REFERENCE_DIVERGED'
