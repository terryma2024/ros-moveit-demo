"""Original stopped capture boundaries; these controls do not execute CUDA."""
from collections import deque
from types import SimpleNamespace
import threading
import json

import pytest
from sensor_msgs.msg import Image, CameraInfo
from rosgraph_msgs.msg import Clock

from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture

try:
    from so101_demo.adapters.act.head_stopped_capture import stopped_window_boundary
except ImportError:
    def stopped_window_boundary(receipts,*,now_ns):
        from so101_demo.act.head_feedback import nanoseconds
        gaps=sorted(right-left for left,right in zip(receipts,receipts[1:]))
        midpoint=nanoseconds(receipts[-1])+nanoseconds(gaps[len(gaps)//2]/2)
        if midpoint<=now_ns:raise ValueError('HEAD_STOPPED_WINDOW_DECLARATION_LATE')
        return midpoint


@pytest.fixture
def capture():
    port=SimpleNamespace(_lock=threading.RLock(),_head_samples=deque(),
        _head_feedback=dict(source_ns=1_000_000_000,wall_s=10.,valid=True,
                            positions=(0.,),velocities=(0.,)))
    class Node:
        def create_subscription(self,kind,topic,callback,qos):return (kind,topic,callback,qos)
        def get_clock(self):
            assert not port._lock._is_owned()
            return SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1_010_000_000))
    return StoppedHeadCapture(Node(),port,frame_id='head_camera_frame',monotonic=lambda:10.001)


def image(source=1_000_000_000):
    msg=Image();msg.header.stamp.sec=source//1_000_000_000
    msg.header.stamp.nanosec=source%1_000_000_000;msg.header.frame_id='head_camera_frame'
    msg.width=640;msg.height=480;msg.encoding='rgb8';msg.step=1920;msg.data=bytes(640*480*3)
    return msg


def info(source=1_000_000_000):
    msg=CameraInfo();msg.header.stamp.sec=source//1_000_000_000
    msg.header.stamp.nanosec=source%1_000_000_000;msg.header.frame_id='head_camera_frame'
    msg.width=640;msg.height=480;msg.k=[415.,0.,320.,0.,415.,240.,0.,0.,1.]
    return msg


def test_camera_and_joint_snapshot_precedes_decision_clock(capture):
    capture._image(image());capture._info(info())
    snapshot=capture.snapshot()
    assert snapshot['camera']==capture.camera_messages[-1]
    assert snapshot['joint']['wall_s']==10.
    assert snapshot['clocks']['sim_ns']==1_010_000_000
    capture.port._head_feedback['wall_s']=11.
    assert snapshot['joint']['wall_s']==10.
    assert all(entry[1]!='/joint_states' for entry in capture.subscriptions)


@pytest.mark.parametrize('damage',['frame','size','encoding','step','bytes','source'])
def test_invalid_payload_is_retained_and_consumes_capture(capture,damage):
    msg=image()
    if damage=='frame':msg.header.frame_id='foreign_camera'
    elif damage=='size':msg.width=639
    elif damage=='encoding':msg.encoding='bgr8'
    elif damage=='step':msg.step=1919
    elif damage=='bytes':msg.data=b'bad'
    else:msg.header.stamp.sec=0
    capture._image(msg)
    assert capture.camera_messages[-1]['valid'] is False
    with pytest.raises(ValueError):capture.snapshot()


def test_capacity_one_drop_remains_an_original_failure(capture):
    capture._image(image());capture._image(image(1_100_000_000))
    assert len(capture.camera_messages)==2
    assert capture.events[-1]['event']=='IMAGE_DROPPED'
    with pytest.raises(ValueError,match='DROPPED'):capture.check()


def test_duplicate_source_never_refreshes_original_receipt(capture):
    capture._image(image());first=capture.camera_messages[-1].copy()
    capture.take_image();capture._image(image())
    assert capture.camera_messages[0]==first
    assert capture.camera_messages[-1]['valid'] is False
    with pytest.raises(ValueError):capture.check()


def test_clock_original_callback_time_is_not_decision_time(capture):
    msg=Clock();msg.clock.sec=1
    capture._clock(msg)
    assert capture.clock_messages[-1]['source_ns']==1_000_000_000
    assert capture.clock_messages[-1]['wall_s']==10.001
    capture._clock(msg)
    assert capture.clock_messages[-1]['valid'] is False


def test_invalid_camera_info_is_retained(capture):
    msg=info();msg.k[0]=float('nan')
    capture._info(msg)
    assert capture.info_messages[-1]['valid'] is False
    with pytest.raises(ValueError):capture.check()


def test_valid_ros_info_keeps_builtin_boolean_for_lossless_json(capture):
    capture._info(info())
    assert type(capture.info_messages[-1]['valid']) is bool
    assert json.loads(json.dumps(capture.info_messages[-1]))['valid'] is True


def test_pending_original_waits_for_exact_tf_before_admission(capture):
    capture._image(image());capture._info(info())
    capture.port._head_samples.append(capture.port._head_feedback.copy())
    original=capture._pending
    class Buffer:
        def can_transform(self,*args):return False
        def lookup_transform(self,*args):raise AssertionError('SDK_LOOKUP_BEFORE_TF_READY')
    class Detector:
        def detect(self,*args,**kwargs):raise AssertionError('CUDA_BEFORE_TF_READY')
    assert capture.infer(Detector(),Buffer(),session_id='test',attempt_id='test',stop_velocity_rad_s=.05) is None
    assert capture._pending is original
    assert capture._pending[0]['wall_s']==10.001


def declare(capture):
    capture.begin_capture()
    getattr(capture,'declare_window',lambda **kw:None)(start_ns=11_000_000_000,end_ns=31_000_000_000)


def test_export_after_predeclared_end_does_not_admit_or_drop_new_presence(capture):
    declare(capture)
    capture.monotonic=lambda:31.001
    capture._image(image());capture._image(image(1_100_000_000))
    capture.check()
    assert capture.take_image() is None
    assert [row['event'] for row in capture.events]==['IMAGE_UNADMITTED_PRESENCE']*2
    assert len(capture.camera_messages)==2


def test_post_end_presence_cannot_hide_unconsumed_in_window_exposure(capture):
    declare(capture)
    capture.monotonic=lambda:30.999;capture._image(image())
    capture.monotonic=lambda:31.001;capture._image(image(1_100_000_000))
    assert capture._pending[0]['source_ns']==1_000_000_000
    with pytest.raises(ValueError,match='UNCONSUMED'):
        getattr(capture,'finish_window',lambda:None)()


def test_camera_info_and_clock_forward_original_metadata_after_cache_release(capture):
    records=[]
    def sink(kind,record):
        assert not capture.port._lock._is_owned()
        records.append((kind,record.copy()))
        if kind=='INFO':record['k'][0]=-1.
    getattr(capture,'bind_original_sink',lambda sink:None)(sink)
    capture._image(image());capture._info(info())
    msg=Clock();msg.clock.sec=1;capture._clock(msg)
    assert [kind for kind,_ in records]==['IMAGE','INFO','CLOCK']
    assert all(record['wall_s']==10.001 and record['source_ns']==1_000_000_000 for _,record in records)
    assert capture.info_messages[-1]['k'][0]==415.


def test_original_sink_failure_consumes_capture_before_return(capture):
    def sink(kind,record):raise RuntimeError('writer unavailable')
    getattr(capture,'bind_original_sink',lambda sink:None)(sink)
    capture._info(info())
    with pytest.raises(ValueError,match='ORIGINAL_SINK_FAILED'):capture.check()


def test_failure_before_capture_boundary_cannot_be_cleared(capture):
    capture._image(image(0))
    with pytest.raises(ValueError):capture.begin_capture()


def test_declared_window_and_original_sink_cannot_be_rebound(capture):
    declare(capture)
    with pytest.raises(PermissionError):capture.declare_window(start_ns=12_000_000_000,end_ns=32_000_000_000)
    capture.bind_original_sink(lambda *a:None)
    with pytest.raises(PermissionError):capture.bind_original_sink(lambda *a:None)


def test_in_window_drop_and_post_window_invalidity_still_fail(capture):
    declare(capture);capture.monotonic=lambda:30.
    capture._image(image());capture._image(image(1_100_000_000))
    capture.monotonic=lambda:32.;capture._image(image(1_200_000_000))
    with pytest.raises(ValueError,match='DROPPED'):capture.finish_window()


def test_finished_window_cannot_replay_exposure_or_reopen(capture):
    declare(capture);capture.monotonic=lambda:32.;capture.finish_window()
    capture._image(image())
    assert capture.infer(None,None,session_id='test',attempt_id='test',stop_velocity_rad_s=.05) is None
    with pytest.raises(PermissionError):capture.finish_window()
    invalid=image(1_100_000_000);invalid.header.frame_id='foreign';capture._image(invalid)
    with pytest.raises(ValueError,match='INVALID'):capture.check()


def test_late_original_waits_for_next_exposure_before_window_is_declared():
    receipts=[10.,10.1,10.2]
    assert stopped_window_boundary(receipts,now_ns=10_270_000_000) is None
    receipts.append(10.3)
    assert stopped_window_boundary(receipts,now_ns=10_310_000_000)==10_350_000_000


def test_equal_midpoint_is_not_a_future_window_and_cannot_start_in_past():
    assert stopped_window_boundary([10.,10.1,10.2],now_ns=10_250_000_000) is None
