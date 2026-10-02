"""Original stopped capture boundaries; these controls do not execute CUDA."""
from collections import deque
from types import SimpleNamespace
import threading

import pytest
from sensor_msgs.msg import Image, CameraInfo
from rosgraph_msgs.msg import Clock

from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture


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
