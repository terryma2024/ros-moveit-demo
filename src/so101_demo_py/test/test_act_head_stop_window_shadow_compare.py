"""Shadow stop window vs the native verdicts (design section 3 'Shadow comparison')."""

import json

import pytest

from so101_demo.act.head_neck_limits import STOP_WINDOW_DEADLINE_S, STOP_WINDOW_STARTUP_SLACK_NS
from so101_demo.act.head_stop_window_shadow import (
    compare_end, compare_run, compare_startup, read_jsonl)

NATIVE_LAST = 4_470_000_000
RAW_STOP = 9_000_000_000
DEADLINE_NS = round(STOP_WINDOW_DEADLINE_S * 1e9)


def prearm(status='READY', last=NATIVE_LAST):
    return dict(kind='PREARM_STATUS', record=dict(status=status, proof=dict(
        last_sim_time_ns=last, first_sim_time_ns=last - 100_000_000, sample_count=64)))


def native_close(ack=True, error=None, status='ARMED_CLOSED'):
    return dict(kind='NATIVE_CLOSE', record=dict(ack=ack, error=error, receipt=None if not ack else dict(
        status=status, ack_validated=True)))


def cancel_stop(confirmed=True, sim=RAW_STOP, cancel_error=None, result_error=None):
    return dict(kind='CANCEL_STOP', record=dict(raw_stop_confirmed=confirmed, cancel_error=cancel_error,
                                                result_error=result_error, observation_count=2,
                                                raw_stop_confirmed_sim_ns=sim if confirmed else None))


def window(first, phase='startup'):
    return dict(kind='SHADOW_WINDOW', phase=phase, window=dict(
        n=51, first_sim_ns=first, last_sim_ns=first + 100_000_000, max_abs_feedback_velocity=0.0001,
        max_abs_reference_velocity=0.0, reference_position=0.1, max_age_ns=50_000_000))


# ---- startup ------------------------------------------------------------------------------

def test_startup_passes_when_the_shadow_completes_within_102ms_of_the_native_ready_stamp():
    shadow = [window(NATIVE_LAST - 100_000_000)]
    verdict = compare_startup([prearm()], shadow)
    assert verdict['native'] == 'PASS' and verdict['shadow'] == 'PASS' and verdict['equal'] is True
    assert verdict['native_ready_sim_ns'] == NATIVE_LAST
    assert verdict['margin_ns'] == STOP_WINDOW_STARTUP_SLACK_NS
    assert verdict['shadow_last_sim_ns'] == NATIVE_LAST


def test_startup_bound_is_inclusive_at_102ms_and_late_by_2ms_is_a_disagreement():
    at_bound = [window(NATIVE_LAST + STOP_WINDOW_STARTUP_SLACK_NS - 100_000_000)]
    assert compare_startup([prearm()], at_bound)['equal'] is True
    late = [window(NATIVE_LAST + STOP_WINDOW_STARTUP_SLACK_NS - 100_000_000 + 2_000_000)]
    verdict = compare_startup([prearm()], late)
    assert verdict['native'] == 'PASS' and verdict['shadow'] == 'FAIL' and verdict['equal'] is False
    assert verdict['shadow_reason'] == 'LATE'
    assert verdict['margin_ns'] == -2_000_000


def test_startup_native_pass_with_no_shadow_window_is_a_disagreement():
    verdict = compare_startup([prearm()], [])
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('PASS', 'FAIL', False)
    assert verdict['shadow_reason'] == 'NO_WINDOW'


def test_startup_fail_fail_agrees():
    verdict = compare_startup([prearm('NOT_READY'), prearm('NOT_READY')], [])
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('FAIL', 'FAIL', True)
    assert verdict['native_ready_sim_ns'] is None


def test_startup_native_fail_but_shadow_pass_is_a_disagreement():
    verdict = compare_startup([prearm('NOT_READY')], [window(4_000_000_000)])
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('FAIL', 'PASS', False)


def test_a_startup_window_that_completed_after_the_first_goal_is_not_a_startup_window():
    shadow = [dict(kind='SHADOW_FIRST_GOAL', mono_ns=10), window(NATIVE_LAST - 100_000_000)]
    shadow[1]['mono_ns'] = 11
    verdict = compare_startup([prearm()], shadow)
    assert verdict['shadow'] == 'FAIL' and verdict['shadow_reason'] == 'AFTER_FIRST_GOAL'


def test_the_first_startup_window_wins_when_several_are_recorded():
    shadow = [window(NATIVE_LAST - 100_000_000), window(NATIVE_LAST + 500_000_000)]
    assert compare_startup([prearm()], shadow)['equal'] is True


# ---- end ------------------------------------------------------------------------------------

def test_end_passes_when_a_window_of_later_samples_completes_within_the_deadline():
    shadow = [dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=RAW_STOP),
              window(RAW_STOP + 2_000_000, 'end')]
    verdict = compare_end([native_close(), cancel_stop()], shadow)
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('PASS', 'PASS', True)
    assert verdict['raw_stop_sim_ns'] == RAW_STOP
    assert verdict['margin_ns'] == DEADLINE_NS - 102_000_000


def test_end_window_must_use_only_samples_after_the_raw_stop_stamp():
    shadow = [dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=RAW_STOP), window(RAW_STOP, 'end')]
    verdict = compare_end([native_close(), cancel_stop()], shadow)
    assert verdict['shadow'] == 'FAIL' and verdict['shadow_reason'] == 'NOT_AFTER_RAW_STOP'


def test_end_window_after_the_deadline_is_a_failure_and_a_disagreement():
    late = RAW_STOP + DEADLINE_NS - 100_000_000 + 2_000_000
    shadow = [dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=RAW_STOP), window(late, 'end')]
    verdict = compare_end([native_close(), cancel_stop()], shadow)
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('PASS', 'FAIL', False)
    assert verdict['shadow_reason'] == 'LATE'


def test_end_deadline_edge_is_inclusive():
    edge = RAW_STOP + DEADLINE_NS - 100_000_000
    shadow = [dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=RAW_STOP), window(edge, 'end')]
    assert compare_end([native_close(), cancel_stop()], shadow)['equal'] is True


@pytest.mark.parametrize('events', [
    [native_close(ack=False, error='RuntimeError'), cancel_stop()],
    [native_close(), cancel_stop(confirmed=False)],
    [native_close(), cancel_stop(cancel_error='TimeoutError')],
    [cancel_stop()],
    [native_close()],
])
def test_end_native_fail_with_no_shadow_end_phase_is_fail_fail(events):
    verdict = compare_end(events, [])
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('FAIL', 'FAIL', True)


def test_end_native_pass_without_a_shadow_end_phase_is_a_disagreement():
    verdict = compare_end([native_close(), cancel_stop()], [])
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('PASS', 'FAIL', False)
    assert verdict['shadow_reason'] == 'NO_END_PHASE'


def test_end_shadow_stamp_and_native_stamp_must_be_the_same_raw_stop():
    shadow = [dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=RAW_STOP + 2), window(RAW_STOP + 4_000_000, 'end')]
    verdict = compare_end([native_close(), cancel_stop()], shadow)
    assert verdict['shadow'] == 'FAIL' and verdict['shadow_reason'] == 'RAW_STOP_STAMP_MISMATCH'


# ---- run ------------------------------------------------------------------------------------

def test_run_verdict_is_equal_only_when_both_phases_are():
    events = [prearm(), native_close(), cancel_stop()]
    good = [window(NATIVE_LAST - 100_000_000), dict(kind='SHADOW_END_PHASE', raw_stop_sim_ns=RAW_STOP),
            window(RAW_STOP + 2_000_000, 'end')]
    assert compare_run(events, good)['equal'] is True
    assert compare_run(events, good[:2])['equal'] is False
    assert compare_run(events, good[:2])['startup']['equal'] is True
    assert compare_run(events, good[:2])['end']['equal'] is False


def test_read_jsonl_skips_blank_lines_and_refuses_garbage(tmp_path):
    path = tmp_path / 'x.jsonl'
    path.write_text(json.dumps(dict(kind='A')) + '\n\n' + json.dumps(dict(kind='B')) + '\n')
    assert [row['kind'] for row in read_jsonl(path)] == ['A', 'B']
    path.write_text('{"kind": "A"}\nnot json\n')
    with pytest.raises(ValueError, match='SHADOW_JSONL_INVALID'):
        read_jsonl(path)


# ---- startup against quiet runs: the shadow must cover the native READY instant -----------------

def run_row(first, last, phase='startup'):
    return dict(kind='SHADOW_QUIET_RUN', phase=phase, first_sim_ns=first, last_sim_ns=last,
                n=(last - first) // 2_000_000 + 1, reference_position=0.1)


def test_a_long_quiet_run_that_began_long_before_native_ready_and_covers_it_passes():
    shadow = [run_row(632_000_000, NATIVE_LAST + 3_000_000_000)]
    verdict = compare_startup([prearm()], shadow)
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('PASS', 'PASS', True)
    assert verdict['shadow_complete_sim_ns'] == 632_000_000 + 100_000_000
    assert verdict['margin_ns'] == NATIVE_LAST + STOP_WINDOW_STARTUP_SLACK_NS - 732_000_000


def test_a_quiet_run_that_ended_before_native_ready_is_not_evidence_for_it():
    shadow = [run_row(632_000_000, NATIVE_LAST - 2_000_000)]
    verdict = compare_startup([prearm()], shadow)
    assert (verdict['native'], verdict['shadow'], verdict['equal']) == ('PASS', 'FAIL', False)
    assert verdict['shadow_reason'] == 'RUN_ENDED_BEFORE_NATIVE_READY'


def test_a_run_that_starts_more_than_102ms_after_native_ready_is_late():
    start = NATIVE_LAST + STOP_WINDOW_STARTUP_SLACK_NS - 100_000_000 + 2_000_000
    verdict = compare_startup([prearm()], [run_row(start, start + 500_000_000)])
    assert verdict['shadow'] == 'FAIL' and verdict['shadow_reason'] == 'LATE'
    at_bound = start - 2_000_000
    assert compare_startup([prearm()], [run_row(at_bound, at_bound + 500_000_000)])['equal'] is True


def test_runs_win_over_a_window_row_and_only_startup_runs_count():
    shadow = [window(NATIVE_LAST - 100_000_000), run_row(0, NATIVE_LAST - 2_000_000),
              run_row(NATIVE_LAST - 500_000_000, NATIVE_LAST + 500_000_000, phase='end')]
    verdict = compare_startup([prearm()], shadow)
    assert verdict['shadow'] == 'FAIL' and verdict['shadow_reason'] == 'RUN_ENDED_BEFORE_NATIVE_READY'


def test_native_fail_with_a_startup_run_is_a_disagreement_and_without_it_agrees():
    assert compare_startup([prearm('NOT_READY')], [run_row(0, 1_000_000_000)])['equal'] is False
    assert compare_startup([prearm('NOT_READY')], [])['equal'] is True
