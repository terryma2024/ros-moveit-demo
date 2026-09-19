"""ACT samples remain causal, bounded and scoped to the reset session."""

import numpy as np
import pytest

from so101_demo.act.synchronizer import RgbObservationSynchronizer, causal_sample


def test_causal_sampling_rejects_future_and_stale_values():
    assert causal_sample([(1., "past"), (1.1, "future")], 1.05, .1) == "past"
    for values in ([(1.1, "future")], [(0.8, "stale")], []):
        with pytest.raises(ValueError):
            causal_sample(values, 1.05, .1)


def filled(session="epoch1", head=1., wrist=1.):
    sync = RgbObservationSynchronizer(max_age_s=.15, max_skew_s=.02, capacity=8)
    sync.reset(session)
    for stream, stamp, value in (("head", head, np.zeros((480, 640, 3), np.uint8)),
                                ("wrist", wrist, np.zeros((480, 640, 3), np.uint8)),
                                ("arm", 1., (0.,)*6), ("neck", 1., .3)):
        sync.push(stream, session, stamp, value)
    return sync


def test_sample_keeps_stationary_pixels_and_measured_state():
    sync = filled()
    sample = sync.sample("epoch1", "attempt1", 1.05)
    assert sample["sim_time_s"] == 1.05
    assert sample["state"][:6] == (0.,)*6
    assert np.allclose(sample["state"][6:], (np.sin(.3), np.cos(.3)))
    assert sample["head"].shape == (480, 640, 3)


def test_reset_invalidates_every_stream_and_old_sessions():
    sync = filled()
    sync.reset("epoch2")
    with pytest.raises(ValueError): sync.sample("epoch2", "attempt2", 1.05)
    with pytest.raises(ValueError): sync.push("arm", "epoch1", 2., (0.,)*6)
    with pytest.raises(ValueError): sync.sample("epoch1", "attempt1", 1.05)


def test_duplicate_backward_skew_and_future_fail_closed():
    sync = filled()
    for stamp in (1., .9):
        with pytest.raises(ValueError): sync.push("arm", "epoch1", stamp, (0.,)*6)
    with pytest.raises(ValueError): filled(wrist=1.04).sample("epoch1", "attempt1", 1.05)
    with pytest.raises(ValueError): filled(head=1.1).sample("epoch1", "attempt1", 1.05)
    with pytest.raises(ValueError): sync.push("depth", "epoch1", 2., object())


def test_ring_and_copy_ownership_are_bounded():
    sync = filled()
    pixels=np.zeros((480,640,3),np.uint8)
    sync.push("head", "epoch1", 1.1, pixels)
    pixels[:] = 255
    assert sync.buffers["head"][-1][1].max() == 0
    for index in range(20): sync.push("arm", "epoch1", 2.+index*.1, (0.,)*6)
    assert len(sync.buffers["arm"]) == 8


def test_ros_adapter_uses_real_stamps_and_excludes_queued_pre_reset_messages():
    from sensor_msgs.msg import Image, JointState
    from so101_demo.act.joints import ACT_JOINTS
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter
    class Node:
        def create_subscription(self, kind, topic, callback, qos): return topic
    sync = RgbObservationSynchronizer(max_age_s=.15, max_skew_s=.02)
    adapter = RosObservationAdapter(Node(), sync)
    assert adapter.subscriptions == ["/head_camera/color", "/wrist_camera/color", "/joint_states"]
    adapter.reset("epoch1", source_floor_s=1.)
    image = Image(width=640,height=480,step=1920,encoding="rgb8",data=bytes(640*480*3))
    image.header.stamp.sec=1; image.header.stamp.nanosec=100000000
    for stream in ("head", "wrist"): adapter._image(stream,image)
    joints=JointState(name=list(reversed(ACT_JOINTS)),position=[.3]+[0.]*6)
    joints.header.stamp=image.header.stamp; adapter._joints(joints)
    assert sync.sample("epoch1","attempt1",1.1)["state"][-2:] == pytest.approx((np.sin(.3),np.cos(.3)))
    adapter.reset("epoch2",source_floor_s=1.2)
    for stream in ("head", "wrist"): adapter._image(stream,image)
    adapter._joints(joints)
    assert all(len(buffer)==0 for buffer in sync.buffers.values())
    assert adapter.rejected[-1]=="INPUT_RESET_STALE"


def test_lossless_rgb_readers_request_reliable_bounded_history():
    from rclpy.qos import ReliabilityPolicy
    from sensor_msgs.msg import Image,JointState
    from so101_demo.adapters.act.ros_observation import RosObservationAdapter
    subscriptions=[]
    class Node:
        def create_subscription(self,kind,topic,callback,qos):subscriptions.append((kind,topic,qos));return None
    RosObservationAdapter(Node(),RgbObservationSynchronizer(max_age_s=.15,max_skew_s=.12))
    assert len(subscriptions)==3
    for kind,topic,qos in subscriptions:
        if kind is Image:assert qos.reliability==ReliabilityPolicy.RELIABLE and qos.depth==32
        else:assert kind is JointState and qos.reliability==ReliabilityPolicy.BEST_EFFORT


def test_search_rgb_and_calibration_info_share_reliable_transport():
    from rclpy.qos import ReliabilityPolicy
    from sensor_msgs.msg import Image,CameraInfo
    from so101_demo.adapters.act.ros_search import RosSearchAdapter
    subscriptions=[]
    class Node:
        def create_subscription(self,kind,topic,callback,qos):subscriptions.append((kind,qos));return None
    RosSearchAdapter(Node(),None,None,None,tf_buffer=object())
    for kind,qos in subscriptions:
        if kind in (Image,CameraInfo):assert qos.reliability==ReliabilityPolicy.RELIABLE and qos.depth==32
