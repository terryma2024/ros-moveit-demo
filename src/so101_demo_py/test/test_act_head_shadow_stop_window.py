"""The shadow stop window beside the broker stack: it writes its own log and never changes a run."""

import time

import pytest

from so101_demo.act.head_neck_limits import STOP_WINDOW_DEADLINE_S, STOP_WINDOW_STEP_NS
from so101_demo.act.head_stop_window_shadow import compare_end, compare_startup, read_jsonl
from so101_demo.adapters.act.head_shadow_stop_window import (
    ENVIRONMENT_VARIABLE, ShadowStopWindow, shadow_from_environment)
from test_act_head_stop_window_subscriber import BASE_SIM, Rig, wait_for


@pytest.fixture
def rig(isolated_ros_domain):
    value = Rig()
    try:
        yield value
    finally:
        value.close()


def make(rig, tmp_path, run_id='run-1'):
    shadow = ShadowStopWindow(context=rig.context, directory=tmp_path, run_id=run_id)
    shadow.start()
    deadline = time.monotonic() + 5.
    while rig.publisher.get_subscription_count() < 1:
        assert time.monotonic() < deadline
        time.sleep(.01)
    return shadow


def kinds(path):
    return [row['kind'] for row in read_jsonl(path)]


def test_a_run_writes_started_startup_goal_end_phase_end_window_and_final(rig, tmp_path):
    shadow = make(rig, tmp_path)
    try:
        rig.publish(0, 51)
        assert wait_for(lambda: 'SHADOW_WINDOW' in kinds(shadow.path))
        shadow.note_first_goal()
        rig.publish(51, 20, fb=0.2)  # the neck moves
        raw_stop = BASE_SIM + 100 * STOP_WINDOW_STEP_NS
        shadow.on_raw_stop_confirmed(raw_stop)
        rig.publish(71, 60)  # indices 71..130: 71..100 are at or below the stamp, 101..130 count: only 30
        rig.publish(131, 30)
        final = shadow.finish(timeout_s=5.)
    finally:
        shadow.finish(timeout_s=.1)
    rows = read_jsonl(shadow.path)
    assert [row['kind'] for row in rows] == [
        'SHADOW_STARTED', 'SHADOW_WINDOW', 'SHADOW_FIRST_GOAL', 'SHADOW_END_PHASE', 'SHADOW_WINDOW',
        'SHADOW_FINAL']
    assert rows[0]['qos_depth'] == 64 and rows[0]['run_id'] == 'run-1'
    startup, end = rows[1], rows[4]
    assert startup['phase'] == 'startup' and startup['window']['first_sim_ns'] == BASE_SIM
    assert end['phase'] == 'end' and end['window']['first_sim_ns'] == raw_stop + STOP_WINDOW_STEP_NS
    assert rows[3]['raw_stop_sim_ns'] == raw_stop
    assert final['startup_window'] == startup['window'] and final['end_window'] == end['window']
    assert rows[5]['stop_receipt']['thread_alive'] is False
    # the log is consumable by the comparison
    events = [dict(kind='PREARM_STATUS', record=dict(status='READY', proof=dict(
        last_sim_time_ns=startup['window']['last_sim_ns']))),
        dict(kind='NATIVE_CLOSE', record=dict(ack=True, error=None, receipt=dict(status='ARMED_CLOSED'))),
        dict(kind='CANCEL_STOP', record=dict(raw_stop_confirmed=True, cancel_error=None, result_error=None,
                                            raw_stop_confirmed_sim_ns=raw_stop))]
    assert compare_startup(events, rows)['equal'] is True
    assert compare_end(events, rows)['equal'] is True


def test_finish_without_an_end_phase_does_not_wait_and_writes_final(rig, tmp_path):
    shadow = make(rig, tmp_path)
    started = time.monotonic()
    final = shadow.finish(timeout_s=5.)
    assert time.monotonic() - started < 1.5
    assert final['startup_window'] is None and final['end_window'] is None
    assert kinds(shadow.path) == ['SHADOW_STARTED', 'SHADOW_FINAL']
    assert shadow.finish(timeout_s=.1) == final  # idempotent


def test_finish_gives_up_on_a_missing_end_window_after_the_timeout(rig, tmp_path):
    shadow = make(rig, tmp_path)
    shadow.on_raw_stop_confirmed(BASE_SIM)
    started = time.monotonic()
    final = shadow.finish(timeout_s=.4)
    assert .35 <= time.monotonic() - started < 2.
    assert final['end_window'] is None
    assert kinds(shadow.path) == ['SHADOW_STARTED', 'SHADOW_END_PHASE', 'SHADOW_FINAL']


def test_a_goal_before_the_startup_window_completes_voids_it(rig, tmp_path):
    shadow = make(rig, tmp_path)
    try:
        rig.publish(0, 30)
        assert wait_for(lambda: shadow.snapshot()['pending'] == 30)
        shadow.note_first_goal()
        assert shadow.snapshot()['voids'] == ['FIRST_GOAL']
        rig.publish(30, 20)
        time.sleep(.3)
        assert 'SHADOW_WINDOW' not in kinds(shadow.path)
    finally:
        shadow.finish(timeout_s=.1)


def test_the_log_is_created_exclusively(rig, tmp_path):
    shadow = make(rig, tmp_path)
    try:
        other = ShadowStopWindow(context=rig.context, directory=tmp_path, run_id='run-1')
        with pytest.raises(FileExistsError):
            other.start()
    finally:
        shadow.finish(timeout_s=.1)


@pytest.mark.parametrize('run_id', ['', 'a/b', '..', 'x' * 200])
def test_run_ids_that_could_escape_the_directory_are_refused(rig, tmp_path, run_id):
    with pytest.raises(ValueError, match='SHADOW_RUN_ID_INVALID'):
        ShadowStopWindow(context=rig.context, directory=tmp_path, run_id=run_id)


def test_the_environment_switch(rig, tmp_path):
    assert shadow_from_environment(context=rig.context, run_id='r', environ={}) is None
    shadow = shadow_from_environment(context=rig.context, run_id='r', environ={ENVIRONMENT_VARIABLE: str(tmp_path)})
    assert isinstance(shadow, ShadowStopWindow) and shadow.path.parent == tmp_path
    for bad in ('relative/dir', str(tmp_path / 'missing'), ''):
        with pytest.raises(ValueError, match='SHADOW_DIRECTORY_INVALID'):
            shadow_from_environment(context=rig.context, run_id='r', environ={ENVIRONMENT_VARIABLE: bad})
