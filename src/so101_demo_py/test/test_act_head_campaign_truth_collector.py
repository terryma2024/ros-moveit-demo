"""Real ROS messages are saved by the existing bounded file-v1 writer."""
import importlib
import json

import pytest


def _module():
    return importlib.import_module('so101_demo.adapters.act.head_campaign_truth_collector')


def _frame():
    from mujoco_ros2_control_msgs.msg import CameraTruthFrame
    from sensor_msgs.msg import Image, CameraInfo
    from std_msgs.msg import Header
    from builtin_interfaces.msg import Time
    header = Header(stamp=Time(sec=1), frame_id='head_camera_frame')
    return CameraTruthFrame(schema_version=1, capture_identity='capture', frame_sequence=1,
        camera_name='head_camera', model_sha256='a'*64, render_config_sha256='b'*64,
        render_phase='frozen_mjv_scene_after_original_rgb',
        rgb=Image(header=header,width=1,height=1,encoding='rgb8',step=3,data=b'abc'),
        camera_info=CameraInfo(header=header,width=1,height=1),
        instances=Image(header=header,width=1,height=1,encoding='32SC2',step=8,data=b'\xff'*8),
        generated_count=1,enqueued_count=1,last_enqueued_sequence=1)


def _envelope(frame):
    """The native message wraps every original frame in the reference envelope (no initial reference: kind 0)."""
    from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
    return CameraTruthFrameV2(schema_version=2, original=frame, reference_kind=0)


def _writer(tmp_path):
    from so101_demo.act.head_run_evidence import HeadRunEvidence
    return HeadRunEvidence.create(tmp_path/'run',{'run':{'run_id':'test'}})


def _collector(module,writer):
    return module.FrameOriginalRecorder(writer=writer,capture_identity='capture',
        camera_name='head_camera',model_sha256='a'*64,render_config_sha256='b'*64)


def test_collector_keeps_exact_cdr_and_original_receive_times(tmp_path):
    module = _module()
    from rclpy.serialization import deserialize_message
    from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
    writer = _writer(tmp_path)
    try:
        collector = _collector(module,writer)
        frame = _frame()
        collector.record_frame(_envelope(frame),received_utc_ns=10,received_monotonic_ns=20)
        collector.record_production('rgb',frame.rgb,received_utc_ns=11,received_monotonic_ns=21)
        collector.record_production('info',frame.camera_info,received_utc_ns=12,received_monotonic_ns=22)
        assert collector.frame_watermark == 1
        assert collector.failure is None
    finally:
        writer.finish({'execution':'TEST_ONLY'})
    events = [json.loads(row) for row in (tmp_path/'run/events.jsonl').read_text().splitlines()]
    event = next(row for row in events if row['kind']=='TRUTH_CAMERA_PAIRED')
    assert event['record']['received_utc_ns']==10
    assert event['record']['received_monotonic_ns']==20
    assert event['record']['source_ns']==1000000000
    ref = event['record']['cdr_ref']
    assert deserialize_message((tmp_path/'run'/ref['path']).read_bytes(),CameraTruthFrameV2)==_envelope(frame)
    assert len([row for row in events if row['kind']=='TRUTH_CAMERA_PRODUCTION'])==2


@pytest.mark.parametrize('fault',['repeated','backward','identity','loss'])
def test_fault_is_sticky_and_bad_original_is_still_saved(tmp_path,fault):
    module = _module()
    writer = _writer(tmp_path)
    try:
        collector = _collector(module,writer)
        frame = _frame()
        collector.record_frame(_envelope(frame),received_utc_ns=10,received_monotonic_ns=20)
        import copy
        second = copy.deepcopy(frame)
        second.frame_sequence=2
        second.rgb.header.stamp.sec=2
        second.camera_info.header.stamp.sec=2
        second.instances.header.stamp.sec=2
        if fault=='repeated':second.frame_sequence=1
        if fault=='backward':second.rgb.header.stamp.sec=0
        if fault=='identity':second.capture_identity='old'
        if fault=='loss':second.loss_latched=True
        with pytest.raises(ValueError):
            collector.record_frame(_envelope(second),received_utc_ns=11,received_monotonic_ns=21)
        first=collector.failure
        assert first
        assert collector.frame_watermark==1
        with pytest.raises(ValueError):
            collector.record_frame(_envelope(second),received_utc_ns=12,received_monotonic_ns=22)
        assert collector.failure==first
    finally:
        writer.finish({'execution':'TEST_ONLY'})
    rows=[json.loads(x) for x in (tmp_path/'run/events.jsonl').read_text().splitlines()]
    assert len([r for r in rows if r['kind']=='TRUTH_CAMERA_PAIRED'])==3


def test_final_watermark_detects_last_missing_frame_without_next_gap(tmp_path):
    module = _module()
    writer = _writer(tmp_path)
    try:
        collector = _collector(module,writer)
        frame = _frame()
        collector.record_frame(_envelope(frame),received_utc_ns=10,received_monotonic_ns=20)
        final = type(frame)(schema_version=1,record_type=1,capture_identity='capture',
            camera_name='head_camera',model_sha256='a'*64,render_config_sha256='b'*64,
            generated_count=2,enqueued_count=2,published_count=2,last_enqueued_sequence=2,
            last_published_sequence=2,frame_sequence=2)
        with pytest.raises(ValueError):
            collector.record_frame(_envelope(final),received_utc_ns=11,received_monotonic_ns=21)
        assert collector.failure
    finally:
        writer.finish({'execution':'TEST_ONLY'})


def test_real_writer_capacity_fault_latches_truth_incomplete(tmp_path):
    from so101_demo.act.head_run_evidence import HeadRunEvidence
    faults=[]
    writer=HeadRunEvidence.create(tmp_path/'run', {'run':{'run_id':'test'}},
        capacities={'max_artifact_bytes':1}, fault_callback=lambda reason: faults.append(reason))
    recorder=_collector(_module(),writer)
    try:
        with pytest.raises(BufferError):
            recorder.record_frame(_envelope(_frame()),received_utc_ns=10,received_monotonic_ns=20)
        assert recorder.receipt()['failure']=='HEAD_TRUTH_ORIGINAL_SAVE_FAILED'
        assert recorder.receipt()['complete'] is False
        assert [str(fault) for fault in faults]==['HEAD_RUN_EVIDENCE_CAPACITY']
    finally:
        with pytest.raises(RuntimeError,match='HEAD_RUN_EVIDENCE_FAULTED'):
            writer.finish({'execution':'TEST_ONLY'})
    assert not (tmp_path/'run/seal.json').exists()


def test_owned_ros_subscriptions_receive_real_native_topic_types_and_retire(tmp_path):
    module = _module()
    import os
    import time
    import uuid
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
    from sensor_msgs.msg import Image, CameraInfo
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
    context = Context()
    worker = os.environ.get('PYTEST_XDIST_WORKER','gw0')
    domain = 212 + (int(worker[2:]) if worker.startswith('gw') else 0)
    rclpy.init(context=context,domain_id=domain)
    token='truth_'+uuid.uuid4().hex
    node=Node(token,context=context)
    executor=SingleThreadedExecutor(context=context)
    executor.add_node(node)
    base='/'+token
    writer=_writer(tmp_path)
    collector=None
    try:
        recorder=_collector(module,writer)
        physics_received=[]
        record_physics=recorder.record_physics
        def receive_physics(message, **times):
            result=record_physics(message, **times)
            physics_received.append(message)
            return result
        recorder.record_physics=receive_physics
        collector=module.HeadCampaignTruthCollector(node=node,recorder=recorder,
            truth_topic=base+'/paired',rgb_topic=base+'/rgb',info_topic=base+'/info')
        qos=QoSProfile(depth=10,reliability=ReliabilityPolicy.BEST_EFFORT)
        pubs=[node.create_publisher(cls,topic,qos) for cls,topic in (
            (CameraTruthFrameV2,base+'/paired'),(Image,base+'/rgb'),(CameraInfo,base+'/info'),
            (PhysicsStepEvidenceChunk,'/so101/simulation/physics_step_chunks'))]
        deadline=time.monotonic()+2
        while not all(p.get_subscription_count()==1 for p in pubs) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.01)
        assert [p.get_subscription_count() for p in pubs]==[1,1,1,1]
        frame=_frame()
        pubs[0].publish(_envelope(frame))
        pubs[1].publish(frame.rgb)
        pubs[2].publish(frame.camera_info)
        pubs[3].publish(PhysicsStepEvidenceChunk(chunk_sequence=1,
            simulation_session_id='native-session',reset_epoch=7))
        deadline=time.monotonic()+2
        while not (recorder.frame_watermark==1 and
                   recorder.production_watermarks=={'rgb':1000000000,'info':1000000000} and
                   physics_received) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.01)
        assert recorder.frame_watermark==1
        assert recorder.production_watermarks=={'rgb':1000000000,'info':1000000000}
        assert len(physics_received)==1
        assert collector.close()['closed'] is True
        assert collector.close()['closed'] is True
        deadline=time.monotonic()+2
        while any(p.get_subscription_count() for p in pubs) and time.monotonic()<deadline:
            executor.spin_once(timeout_sec=.01)
        assert [p.get_subscription_count() for p in pubs]==[0,0,0,0]
    finally:
        if collector is not None:collector.close()
        executor.shutdown()
        node.destroy_node()
        context.shutdown()
        writer.finish({'execution':'TEST_ONLY'})
    rows=[json.loads(x) for x in (tmp_path/'run/events.jsonl').read_text().splitlines()]
    assert any(row['kind']=='TRUTH_PHYSICS_CHUNK' for row in rows)
    assert all(row['record']['received_utc_ns']>0 for row in rows)


def test_callback_retirement_is_bounded_and_cannot_hide_a_live_saver(tmp_path):
    import threading
    import time
    module=_module()
    writer=_writer(tmp_path)
    recorder=_collector(module,writer)
    started=threading.Event();release=threading.Event()
    original=recorder.record_frame
    def blocked(message,**times):
        with recorder._lock:
            started.set()
            assert release.wait(2)
            return original(message,**times)
    recorder.record_frame=blocked
    class Node:
        def __init__(self):self.callbacks=[];self.retired=[]
        def create_subscription(self,cls,topic,callback,qos):self.callbacks.append(callback);return callback
        def destroy_subscription(self,subscription):self.retired.append(subscription);return True
    node=Node()
    collector=module.HeadCampaignTruthCollector(node=node,recorder=recorder,truth_topic='/private_truth')
    thread=threading.Thread(target=lambda:node.callbacks[0](_frame()))
    try:
        thread.start();assert started.wait(1)
        before=time.monotonic()
        result=collector.close()
        assert time.monotonic()-before<.15
        assert result['closed'] is False
        assert not node.retired
        assert thread.is_alive()
        release.set();thread.join(1);assert not thread.is_alive()
        assert collector.close()['closed'] is True
        old=recorder.frame_watermark
        node.callbacks[0](_frame())
        assert recorder.frame_watermark==old
    finally:
        release.set();thread.join(1)
        collector.close()
        writer.finish({'execution':'TEST_ONLY'})


@pytest.mark.parametrize('damage',['encoding','step','payload','info_size','published_count','mapping'])
def test_malformed_native_frame_is_preserved_and_immediately_invalidates_truth(tmp_path,damage):
    writer=_writer(tmp_path);recorder=_collector(_module(),writer);frame=_frame()
    if damage=='encoding':frame.instances.encoding='rgb8'
    elif damage=='step':frame.instances.step=7
    elif damage=='payload':frame.instances.data=b'\xff'
    elif damage=='info_size':frame.camera_info.width=2
    elif damage=='published_count':frame.published_count=1
    else:frame.segmentation_ids=[0,0];frame.object_ids=[1,2];frame.object_types=[5,5]
    try:
        with pytest.raises(ValueError):
            recorder.record_frame(_envelope(frame),received_utc_ns=10,received_monotonic_ns=20)
        assert recorder.receipt()['failure'] and recorder.frame_watermark==0
    finally:writer.finish({'execution':'TEST_ONLY'})
    rows=[json.loads(row) for row in (tmp_path/'run/events.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['kind']=='TRUTH_CAMERA_PAIRED'
