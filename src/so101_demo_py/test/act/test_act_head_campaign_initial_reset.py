"""Paused native reset originals must precede controller activation.

Real ROS CDR and the bounded writer exercise this preparation boundary;
these tests do not claim an actual native stack or render equivalence.
"""
import copy
import json
import threading
import time

import pytest

from test_act_head_campaign_truth_collector import _collector, _envelope, _frame, _module, _writer
from test_act_head_execution_reset import setup_scene


def _reset():
    return dict(paused=True,simulation_step=0,reset_epoch=7,
        simulation_session_id='native-session',model_sha256='a'*64,
        simulation_time_s=1.,qpos=[0.],qvel=[0.])


def _originals(recorder, *, omit=None, damage=None):
    frame=_frame()
    if omit!='paired':
        recorder.record_frame(_envelope(frame),received_utc_ns=10,received_monotonic_ns=20)
    rgb=copy.deepcopy(frame.rgb);info=copy.deepcopy(frame.camera_info)
    if damage=='rgb':rgb.data=b'xyz'
    elif damage=='info':info.k[0]=1.
    if omit!='rgb':
        recorder.record_production('rgb',rgb,received_utc_ns=11,received_monotonic_ns=21)
    if omit!='info':
        recorder.record_production('info',info,received_utc_ns=12,received_monotonic_ns=22)
    # ROS inputs may be reused by callers. Readiness must use frozen originals.
    rgb.data=b'def';info.k[0]=9.;frame.rgb.data=b'ghi'


def test_initial_frame_requires_literal_rgb_info_and_same_actual_paused_reset(tmp_path):
    writer=_writer(tmp_path);recorder=_collector(_module(),writer)
    try:
        _originals(recorder)
        proof=recorder.wait_initial_reset_frame(_reset(),deadline=time.monotonic()+.2)
        assert proof['ready'] is True and proof['source_ns']==1_000_000_000
        assert proof['frame_sequence']==1 and proof['reset_original']==_reset()
        assert proof['paired_original']['received_utc_ns']==10
        assert proof['production_rgb']['received_utc_ns']==11
        assert proof['production_info']['received_utc_ns']==12
        with pytest.raises((ValueError,PermissionError)):
            recorder.wait_initial_reset_frame(_reset(),deadline=time.monotonic()+.2)
    finally:writer.finish({'execution':'TEST_ONLY'})
    rows=[json.loads(row) for row in (tmp_path/'run/events.jsonl').read_text().splitlines()]
    assert len([row for row in rows if row['kind']=='TRUTH_INITIAL_RESET_FRAME'])==1


@pytest.mark.parametrize('omit',['paired','rgb','info'])
def test_missing_initial_original_expires_the_same_preparation_deadline(tmp_path,omit):
    writer=_writer(tmp_path);recorder=_collector(_module(),writer)
    try:
        _originals(recorder,omit=omit)
        started=time.monotonic()
        with pytest.raises(TimeoutError):
            recorder.wait_initial_reset_frame(_reset(),deadline=started+.02)
        assert time.monotonic()-started<.15
    finally:writer.finish({'execution':'TEST_ONLY'})


@pytest.mark.parametrize('damage',['rgb','info','source'])
def test_mismatched_initial_original_is_retained_and_cannot_activate(tmp_path,damage):
    writer=_writer(tmp_path);recorder=_collector(_module(),writer)
    try:
        _originals(recorder,damage=damage)
        reset=_reset()
        if damage=='source':reset['simulation_time_s']=1.1
        with pytest.raises(ValueError):
            recorder.wait_initial_reset_frame(reset,deadline=time.monotonic()+.2)
        assert recorder.failure
    finally:writer.finish({'execution':'TEST_ONLY'})


def test_initial_wait_accepts_late_real_info_without_holding_the_recorder_lock(tmp_path):
    writer=_writer(tmp_path);recorder=_collector(_module(),writer)
    _originals(recorder,omit='info')
    entered=threading.Event();result=[];errors=[]
    def wait():
        entered.set()
        try:result.append(recorder.wait_initial_reset_frame(_reset(),deadline=time.monotonic()+1.))
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=wait)
    try:
        thread.start();assert entered.wait(1)
        recorder.record_production('info',_frame().camera_info,
            received_utc_ns=12,received_monotonic_ns=22)
        thread.join(1.);assert not thread.is_alive() and not errors
        assert result[0]['ready']
    finally:
        thread.join(1.);writer.finish({'execution':'TEST_ONLY'})


def test_blocked_initial_saver_cannot_extend_the_preparation_deadline(tmp_path):
    writer=_writer(tmp_path);recorder=_collector(_module(),writer)
    entered=threading.Event();release=threading.Event()
    def block():
        with recorder._lock:
            entered.set();release.wait(2.)
    thread=threading.Thread(target=block)
    try:
        thread.start();assert entered.wait(1)
        started=time.monotonic()
        with pytest.raises(TimeoutError):
            recorder.wait_initial_reset_frame(_reset(),deadline=started+.02)
        assert time.monotonic()-started<.15
    finally:
        release.set();thread.join(1.);assert not thread.is_alive()
        writer.finish({'execution':'TEST_ONLY'})


def test_late_final_watermark_cannot_promote_an_expired_initial_frame(tmp_path):
    from mujoco_ros2_control_msgs.msg import CameraTruthFrame
    writer=_writer(tmp_path);recorder=_collector(_module(),writer)
    try:
        _originals(recorder,omit='info')
        with pytest.raises(TimeoutError):
            recorder.wait_initial_reset_frame(_reset(),deadline=time.monotonic()+.02)
        recorder.record_frame(_envelope(CameraTruthFrame(schema_version=1,record_type=1,
            capture_identity='capture',camera_name='head_camera',model_sha256='a'*64,
            render_config_sha256='b'*64,generated_count=1,enqueued_count=1,published_count=1,
            last_enqueued_sequence=1,last_published_sequence=1,frame_sequence=1)),
            received_utc_ns=13,received_monotonic_ns=23)
        assert recorder.receipt()['final_received'] is True
        assert recorder.receipt()['complete'] is False
    finally:writer.finish({'execution':'TEST_ONLY'})


@pytest.mark.parametrize('refuse',[False,True])
def test_verified_reset_hook_runs_before_resume_and_preserves_the_existing_deadline(tmp_path,refuse):
    scene,_,_,_,events=setup_scene(tmp_path)
    started=time.monotonic();calls=[]
    def ready(frame,*,deadline):
        calls.append((frame,deadline))
        assert frame['paused'] is True and frame['simulation_step']==0
        assert frame['reset_epoch']==3
        # reset() takes its deadline when it starts, however late the scheduler lets that happen after `started`: never shorter than
        # the timeout counted from `started`, never longer than the timeout counted from this call
        assert started+.1<=deadline<=time.monotonic()+.1
        assert not any(row[0]=='switch' and row[1] for row in events)
        return {'ready':not refuse}
    scene.on_verified_reset=ready
    try:
        if refuse:
            with pytest.raises(PermissionError,match='INITIAL_FRAME'):
                scene.reset(timeout_s=.1)
            assert not any(row[0]=='switch' and row[1] for row in events)
            assert [row for row in events if row[0]=='pause'][-1]==('pause',True)
        else:
            scene.reset(timeout_s=.1)
            assert any(row[0]=='switch' and row[1] for row in events)
        assert len(calls)==1
    finally:scene.close()
