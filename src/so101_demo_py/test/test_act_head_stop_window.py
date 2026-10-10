"""The 51-sample controller_state stop window (design section 3), as a pure evaluator."""

import math

import pytest

from so101_demo.act.head_neck_limits import (
    STOP_WINDOW_MAX_AGE_NS, STOP_WINDOW_SAMPLES, STOP_WINDOW_STEP_NS)
from so101_demo.act.head_stop_window import StopWindow

BASE_SIM = 5_000_000_000
BASE_MONO = 1_000_000_000_000


def feed(window, count, *, start=0, mono_step=1_000_000, ref=0.25, fb=0.0, vref=0.0,
         sim_base=BASE_SIM, mono_base=BASE_MONO, now=None):
    first_done = None
    for index in range(start, start + count):
        mono = mono_base + index * mono_step
        last = window.observe(sim_ns=sim_base + index * STOP_WINDOW_STEP_NS, receive_mono_ns=mono,
                              feedback_velocity=fb, reference_velocity=vref,
                              reference_position=ref, now_mono_ns=mono if now is None else now)
        first_done = first_done or last
    return first_done


def test_the_window_completes_on_the_51st_consecutive_quiet_sample():
    window = StopWindow()
    assert feed(window, STOP_WINDOW_SAMPLES - 1) is None
    assert window.completed is None
    done = feed(window, 1, start=STOP_WINDOW_SAMPLES - 1)
    assert done is not None and window.completed == done
    assert done['n'] == 51
    assert done['first_sim_ns'] == BASE_SIM
    assert done['last_sim_ns'] == BASE_SIM + 50 * STOP_WINDOW_STEP_NS
    assert done['reference_position'] == 0.25
    assert done['max_abs_feedback_velocity'] == 0.0 and done['max_abs_reference_velocity'] == 0.0
    assert done['max_age_ns'] == 50 * 1_000_000


def test_the_window_reports_the_largest_velocities_it_saw():
    window = StopWindow()
    for index in range(51):
        fb = 0.0015 if index == 7 else 0.0001
        vref = -0.0019 if index == 30 else 0.0
        done = window.observe(sim_ns=BASE_SIM + index * 2_000_000, receive_mono_ns=BASE_MONO + index,
                              feedback_velocity=fb, reference_velocity=vref, reference_position=1.0,
                              now_mono_ns=BASE_MONO + index)
    assert done['max_abs_feedback_velocity'] == 0.0015
    assert done['max_abs_reference_velocity'] == 0.0019


@pytest.mark.parametrize('jump_ns', [4_000_000, 1_000_000, 0, -2_000_000])
def test_a_sim_stamp_off_the_2ms_grid_restarts_the_window(jump_ns):
    window = StopWindow()
    feed(window, 30)
    sim = BASE_SIM + 29 * STOP_WINDOW_STEP_NS + jump_ns
    window.observe(sim_ns=sim, receive_mono_ns=BASE_MONO + 40_000_000, feedback_velocity=0.0,
                   reference_velocity=0.0, reference_position=0.25, now_mono_ns=BASE_MONO + 40_000_000)
    assert window.resets['SIM_TIME_GAP'] == 1
    # the gapped sample opens the new window: 50 more complete it, 49 do not
    done = None
    for index in range(1, 50):
        done = window.observe(sim_ns=sim + index * 2_000_000, receive_mono_ns=BASE_MONO + 41_000_000 + index,
                              feedback_velocity=0.0, reference_velocity=0.0, reference_position=0.25,
                              now_mono_ns=BASE_MONO + 41_000_000 + index)
    assert done is None
    done = window.observe(sim_ns=sim + 50 * 2_000_000, receive_mono_ns=BASE_MONO + 41_000_050,
                          feedback_velocity=0.0, reference_velocity=0.0, reference_position=0.25,
                          now_mono_ns=BASE_MONO + 41_000_050)
    assert done is not None and done['first_sim_ns'] == sim


@pytest.mark.parametrize('field', ['feedback_velocity', 'reference_velocity'])
def test_a_velocity_above_the_bound_empties_the_window_and_is_not_kept(field):
    window = StopWindow()
    feed(window, 40)
    values = dict(feedback_velocity=0.0, reference_velocity=0.0)
    values[field] = 0.0021
    window.observe(sim_ns=BASE_SIM + 40 * 2_000_000, receive_mono_ns=BASE_MONO + 41_000_000,
                   reference_position=0.25, now_mono_ns=BASE_MONO + 41_000_000, **values)
    assert window.resets['VELOCITY'] == 1 and window.completed is None
    done = feed(window, 51, start=41, mono_base=BASE_MONO + 2_000_000_000)
    assert done['first_sim_ns'] == BASE_SIM + 41 * 2_000_000


def test_exactly_the_bound_is_quiet():
    window = StopWindow()
    for index in range(51):
        done = window.observe(sim_ns=BASE_SIM + index * 2_000_000, receive_mono_ns=BASE_MONO + index,
                              feedback_velocity=-0.002, reference_velocity=0.002, reference_position=0.0,
                              now_mono_ns=BASE_MONO + index)
    assert done is not None


def test_a_changed_reference_position_restarts_the_window_with_the_new_sample():
    window = StopWindow()
    feed(window, 25, ref=0.25)
    window.observe(sim_ns=BASE_SIM + 25 * 2_000_000, receive_mono_ns=BASE_MONO + 26_000_000,
                   feedback_velocity=0.0, reference_velocity=0.0, reference_position=0.2500001,
                   now_mono_ns=BASE_MONO + 26_000_000)
    assert window.resets['REFERENCE_CHANGED'] == 1
    done = None
    for index in range(26, 76):
        done = window.observe(sim_ns=BASE_SIM + index * 2_000_000, receive_mono_ns=BASE_MONO + 27_000_000 + index,
                              feedback_velocity=0.0, reference_velocity=0.0, reference_position=0.2500001,
                              now_mono_ns=BASE_MONO + 27_000_000 + index)
    assert done is not None
    assert done['first_sim_ns'] == BASE_SIM + 25 * 2_000_000
    assert done['reference_position'] == 0.2500001


@pytest.mark.parametrize('damage', [
    dict(feedback_velocity=math.nan), dict(reference_velocity=math.inf),
    dict(reference_position=math.nan), dict(sim_ns=0), dict(sim_ns=-2), dict(sim_ns=1.5),
    dict(receive_mono_ns=None), dict(feedback_velocity='0'),
])
def test_an_invalid_sample_restarts_the_window(damage):
    window = StopWindow()
    feed(window, 20)
    values = dict(sim_ns=BASE_SIM + 20 * 2_000_000, receive_mono_ns=BASE_MONO + 21_000_000,
                  feedback_velocity=0.0, reference_velocity=0.0, reference_position=0.25,
                  now_mono_ns=BASE_MONO + 21_000_000)
    values.update(damage)
    window.observe(**values)
    assert window.resets['INVALID_SAMPLE'] == 1 and window.completed is None
    assert feed(window, 50, start=21, mono_base=BASE_MONO + 5_000_000_000) is None


def test_a_receive_time_regression_restarts_the_window():
    window = StopWindow()
    feed(window, 10)
    window.observe(sim_ns=BASE_SIM + 10 * 2_000_000, receive_mono_ns=BASE_MONO, feedback_velocity=0.0,
                   reference_velocity=0.0, reference_position=0.25, now_mono_ns=BASE_MONO + 11_000_000)
    assert window.resets['RECEIVED_TIME_REGRESSION'] == 1


def test_a_window_whose_oldest_sample_is_older_than_200ms_does_not_complete():
    window = StopWindow()
    # 51 samples received 5 ms apart span 250 ms: at completion the oldest is 250 ms old
    done = feed(window, 51, mono_step=5_000_000)
    assert done is None and window.completed is None
    # the next sample slides the window; the oldest is now 250 ms old still, so it never completes
    assert feed(window, 5, start=51, mono_step=5_000_000) is None
    # fast samples push the stale ones out of the window
    done = feed(window, 60, start=56, mono_step=100_000, mono_base=BASE_MONO + 1_000_000_000)
    assert done is not None
    assert done['max_age_ns'] <= STOP_WINDOW_MAX_AGE_NS


def test_age_is_measured_at_the_evaluation_clock_not_at_the_last_receipt():
    window = StopWindow()
    done = feed(window, 51, mono_step=1_000_000, now=BASE_MONO + 50_000_000 + STOP_WINDOW_MAX_AGE_NS + 1_000_000)
    assert done is None
    window = StopWindow()
    done = feed(window, 51, mono_step=1_000_000, now=BASE_MONO + 200_000_000)
    assert done is not None and done['max_age_ns'] == 200_000_000


def test_a_goal_voids_the_window_and_the_next_window_needs_51_new_samples():
    window = StopWindow()
    feed(window, 45)
    window.void('GOAL_SENT')
    assert window.voids == ['GOAL_SENT']
    assert feed(window, 50, start=45) is None
    done = feed(window, 1, start=95)
    assert done is not None and done['first_sim_ns'] == BASE_SIM + 45 * 2_000_000


def test_the_first_completion_is_latched_until_rearm():
    window = StopWindow()
    first = feed(window, 51)
    again = feed(window, 5, start=51)
    assert again is None and window.completed == first
    window.rearm()
    assert window.completed is None
    done = feed(window, 51, start=60)
    assert done['first_sim_ns'] == BASE_SIM + 60 * 2_000_000 and window.completed == done


# ---- quiet runs: the shadow compares a run against the native READY instant -----------------

def test_a_broken_run_of_at_least_51_samples_is_reported_with_its_extent():
    window = StopWindow()
    feed(window, 80)
    assert window.runs == []
    # a moving sample ends the run; the run had samples 0..79
    window.observe(sim_ns=BASE_SIM + 80 * 2_000_000, receive_mono_ns=BASE_MONO + 90_000_000,
                   feedback_velocity=0.5, reference_velocity=0.0, reference_position=0.25,
                   now_mono_ns=BASE_MONO + 90_000_000)
    assert window.runs == [dict(first_sim_ns=BASE_SIM, last_sim_ns=BASE_SIM + 79 * 2_000_000, n=80,
                                reference_position=0.25)]


def test_short_runs_are_not_reported():
    window = StopWindow()
    feed(window, 50)
    window.void('GOAL_SENT')
    assert window.runs == []


def test_a_run_survives_the_age_slide_and_a_void_closes_it():
    window = StopWindow()
    feed(window, 120, mono_step=5_000_000)  # too slow to complete, but one unbroken quiet run
    assert window.completed is None and window.runs == []
    assert window.open_run() == dict(first_sim_ns=BASE_SIM, last_sim_ns=BASE_SIM + 119 * 2_000_000, n=120,
                                     reference_position=0.25)
    window.void('GOAL_SENT')
    assert window.runs == [dict(first_sim_ns=BASE_SIM, last_sim_ns=BASE_SIM + 119 * 2_000_000, n=120,
                                reference_position=0.25)]
    assert window.open_run() is None


def test_a_reference_change_closes_the_run_and_the_new_sample_opens_the_next():
    window = StopWindow()
    feed(window, 60, ref=0.1)
    window.observe(sim_ns=BASE_SIM + 60 * 2_000_000, receive_mono_ns=BASE_MONO + 61_000_000,
                   feedback_velocity=0.0, reference_velocity=0.0, reference_position=0.2,
                   now_mono_ns=BASE_MONO + 61_000_000)
    assert [run['n'] for run in window.runs] == [60]
    assert window.open_run() is None  # a single sample is not a reportable open run


def test_flush_run_closes_the_open_run_without_losing_the_window_latch():
    window = StopWindow()
    first = feed(window, 51)
    feed(window, 10, start=51)
    window.flush_run()
    assert [run['n'] for run in window.runs] == [61] and window.completed == first
