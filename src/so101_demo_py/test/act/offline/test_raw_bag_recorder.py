"""The record-only process records every message of the topics it was given into a closed MCAP bag, reports RECORDING
only once its recording node subscribes, and reads the bag back at stop."""
import threading
import time
import os
import json
import sys
from pathlib import Path

import pytest

rclpy = pytest.importorskip("rclpy")
rosbag2_py = pytest.importorskip("rosbag2_py")
from std_msgs.msg import String

from so101_demo.act.offline.bag_io import bag_info, read_messages
from so101_demo.act.offline.raw_recorder import RawRecorder, TOPICS, CORE_TOPICS, EVENTS_TOPIC


@pytest.fixture(autouse=True)
def raw_context_lifecycle(isolated_ros_domain):
    rclpy.try_shutdown()
    yield
    rclpy.try_shutdown()


def test_the_topic_list_covers_every_source_the_recorder_subscribes_to():
    for topic in ("/clock", "/head_camera/color", "/head_camera/camera_info", "/wrist_camera/color", "/wrist_camera/camera_info",
                  "/so101/simulation/evidence", "/so101/simulation/physics_step_chunks", "/so101/simulation/robot_contacts",
                  "/so101/simulation/scene_state", "/joint_states", "/arm_controller/controller_state",
                  "/gripper_controller/controller_state", "/neck_controller/controller_state", "/so101/teacher/events"):
        assert topic in TOPICS
    assert EVENTS_TOPIC not in CORE_TOPICS, "the Teacher's events topic has no publisher before the Teacher starts"
    assert set(CORE_TOPICS) <= set(TOPICS)


def test_the_bag_records_everything_published_after_recording_and_closes_with_its_counts(tmp_path, isolated_ros_domain):
    if not rclpy.ok():
        rclpy.init()
    node = rclpy.create_node("rec13_pub")
    names = ("/rec13/a", "/rec13/b")
    publishers = {name: node.create_publisher(String, name, 100) for name in names}
    recorder = RawRecorder(tmp_path / "raw" / "bag", topics=names, core_topics=names, scene_reads=None)
    stop = threading.Event()
    published = {name: 0 for name in names}

    def publish():
        while not stop.is_set():
            for name, publisher in publishers.items():
                publisher.publish(String(data=f"{name}-{published[name]}"))
                published[name] += 1
            time.sleep(0.005)

    thread = threading.Thread(target=publish, daemon=True)
    thread.start()
    try:
        recorder.start()
        ok, state = recorder.wait_recording(20.0)
        assert ok, state
        marker = {name: published[name] for name in names}
        time.sleep(0.5)
    finally:
        stop.set()
        thread.join()
        time.sleep(0.05)
        stats = recorder.stop()
        node.destroy_node()
    assert stats["closed"] and stats["failure"] is None and stats["missing_core_topics"] == [], stats
    # C5: the recorder runs with debug logging (the per-topic loss lines exist only there) and reports the per-topic breakdown, an
    # empty one when nothing was lost
    assert stats["transport_lost"] == 0 and stats["transport_lost_by_topic"] == {} and stats["transport_lost_events"] == [], stats
    log_text = (tmp_path / "raw" / "bag-record.log").read_text(errors="replace")
    assert "[DEBUG]" in log_text
    # experiment 583: a process-wide DEBUG level printed two rcl lines per taken message (42 MB per episode) from the thread
    # that takes the messages; only the recorder's own logger is at DEBUG
    assert "Subscription taking serialized message" not in log_text and log_text.count("\n") < 2000, log_text.count("\n")
    assert stats["anchor_start"]["system_ns"] > 0 and stats["anchor_end"]["monotonic_ns"] > stats["anchor_start"]["monotonic_ns"]
    for name in names:
        count = stats["bag"]["topics"][name]["count"]
        assert count >= published[name] - marker[name] > 20, (name, count, marker, published)
    messages = list(read_messages(tmp_path / "raw" / "bag"))
    assert len(messages) == stats["bag"]["message_count"]
    stamps = [item[2] for item in messages]
    assert stamps == sorted(stamps), "bag order is time order"
    # rosbag2 stamps with the SYSTEM clock: the stamps fall between the two anchors
    assert stats["anchor_start"]["system_ns"] - 1_000_000_000 <= stamps[0] <= stats["anchor_end"]["system_ns"]


def test_an_instance_without_a_namespace_records_with_the_stock_recorder_and_writes_no_topic_map(
        tmp_path, monkeypatch, isolated_ros_domain):
    """The instance marker alone decides the bag root; the recorder is `ros2 bag record` on the logical names."""
    monkeypatch.delenv("SO101_ACT_CONTAINER_NAMESPACE", raising=False)
    monkeypatch.delenv("ROS_NAMESPACE", raising=False)
    root = tmp_path / "w00" / "g1"
    root.mkdir(parents=True)
    monkeypatch.setenv("SO101_ACT_INSTANCE_ROOT", str(root))
    from so101_demo.act.offline.raw_recorder import _bag_root_evidence
    rclpy.init()
    node = rclpy.create_node("instance_recorder_source")
    names = ("/rec14/a", "/rec14/b")
    publishers = {name: node.create_publisher(String, name, 100) for name in names}
    recorder = RawRecorder(root / "attempts" / "scene" / "raw" / "bag", topics=names, core_topics=names)
    stop = threading.Event()

    def publish():
        while not stop.is_set():
            for name, publisher in publishers.items():
                publisher.publish(String(data=name))
            time.sleep(0.005)

    thread = threading.Thread(target=publish, daemon=True)
    thread.start()
    try:
        recorder.start()
        argv = recorder._recorder.args
        assert argv[:3] == [sys.executable, "-m", "so101_demo.act.offline.bag_record_entry"] and "--log-level" not in argv
        assert not any("__ns" in str(item) or "act_scoped_bag_record" in str(item) for item in argv)
        okay, state = recorder.wait_recording(20.0)
        assert okay, state
        assert recorder._probe.get_namespace() == "/"
        time.sleep(0.3)
    finally:
        stop.set()
        thread.join()
        time.sleep(0.05)
        stats = recorder.stop()
        node.destroy_node()
    assert stats["closed"] and not stats["failure"] and stats["missing_core_topics"] == [], stats
    assert set(stats["bag"]["topics"]) == set(names)
    assert recorder.topic_map == {name: name for name in names}
    assert _bag_root_evidence(recorder)["bag_root"]["location"] == "owned_root"
    assert not (recorder.bag_dir.parent / (recorder.bag_dir.name + "-topic-map.json")).exists()


@pytest.mark.skipif(sys.platform=='darwin',reason='container-only native recorder')
def test_native_scoped_recorder_keeps_logical_readback_and_original_namespace(tmp_path,monkeypatch,isolated_ros_domain):
    from ament_index_python.packages import get_package_prefix
    from so101_demo.runtime.container_campaign.ros_namespace import container_ros_init_options
    # A fresh source/SDK installation may be selected by this test harness.
    # Production always resolves the installed support package, with no override.
    prefix=Path(os.environ.get('SO101_TEST_SCOPED_RECORDER_PREFIX') or get_package_prefix('so101_mujoco_support'))
    binary=prefix/'lib/so101_mujoco_support/act_scoped_bag_record'
    assert binary.is_file() and os.access(binary,os.X_OK), 'fresh native recorder installation required'
    original=get_package_prefix
    monkeypatch.setattr('ament_index_python.packages.get_package_prefix',
        lambda name:str(prefix) if name=='so101_mujoco_support' else original(name))
    root=tmp_path/'w00/g1';root.mkdir(parents=True)
    namespace='/act/recorder_test/w00'
    # Controlled external native readiness identity; all Recorder/ROS/MCAP I/O is real.
    (root/'runtime-ready.json').write_text(json.dumps(dict(schema_version=1,kind='ACT_SHARD_RUNTIME_READY',
        generation=1,ros_namespace=namespace)))
    monkeypatch.setenv('SO101_ACT_CONTAINER_NAMESPACE',namespace)
    monkeypatch.setenv('ROS_NAMESPACE',namespace)
    monkeypatch.setenv('SO101_ACT_CONTAINER_OWNED_ROOT',str(root))
    rclpy.init(**container_ros_init_options())
    node=rclpy.create_node('scoped_recorder_source')
    names=('/head_camera/color','/so101/teacher/events')
    publishers={name:node.create_publisher(String,name,100) for name in names}
    recorder=RawRecorder(root/'attempts/scene/attempt/working/raw/bag',topics=names,core_topics=names)
    stop=threading.Event()
    def publish():
        while not stop.is_set():
            for name,publisher in publishers.items():publisher.publish(String(data=name))
            time.sleep(.005)
    thread=threading.Thread(target=publish,daemon=True);thread.start()
    try:
        recorder.start()
        okay,state=recorder.wait_recording(10.)
        assert okay,state
        assert recorder._probe.get_namespace()==namespace
        for name in names:
            matches=[info for info in recorder._probe.get_subscriptions_info_by_topic(namespace+name)
                     if info.node_name==recorder.node_name]
            assert len(matches)==1 and matches[0].node_namespace==namespace
        time.sleep(.2)
    finally:
        stop.set();thread.join();time.sleep(.05)
        stats=recorder.stop()
        node.destroy_node()
    from so101_demo.act.offline.raw_recorder import _atomic_json
    _atomic_json(recorder.bag_dir.parent/'record-stats.json',stats)
    assert stats['closed'] and not stats['failure'] and stats['bag_process_rc']==0,stats
    assert stats['transport_lost']==0 and stats['transport_lost_by_topic']=={},stats
    assert set(stats['bag']['topics'])==set(names)
    assert stats['missing_core_topics']==[]
    assert all(stats['bag']['topics'][name]['count']>20 for name in names)
    assert set(row[0] for row in read_messages(recorder.bag_dir))==set(names)
    assert (recorder.bag_dir.parent/'bag-topic-map.json').is_file()


def test_a_core_topic_without_a_publisher_is_not_recording_and_the_wait_is_bounded(tmp_path, isolated_ros_domain):
    recorder = RawRecorder(tmp_path / "bag", topics=("/rec13/none",), core_topics=("/rec13/none",), scene_reads=None)
    began = time.monotonic()
    try:
        recorder.start()
        ok, state = recorder.wait_recording(1.0)
    finally:
        recorder.stop()
    assert ok is False and time.monotonic() - began < 6.0 and state["/rec13/none"]["publishers"] == 0


def test_an_existing_bag_is_never_reused(tmp_path):
    (tmp_path / "bag").mkdir()
    with pytest.raises(FileExistsError, match="RAW_BAG_EXISTS"):
        RawRecorder(tmp_path / "bag", topics=("/x",), core_topics=("/x",)).start()


def test_the_500_hz_controller_states_are_recorded_through_deep_reliable_queues():
    """Pilot 8d9ed9d3: the bag node lost 987 messages on the transport layer (the controller states, about 600 holes each
    in the window; four touched a label instant and made the episode INVALID). A 440 ms stall of the recorder is 220
    ticks of a 500 Hz topic, so its queue must be far deeper than the publisher's own."""
    from so101_demo.act.offline.raw_recorder import DEEP_RELIABLE, build_options

    controllers = ("/arm_controller/controller_state", "/gripper_controller/controller_state",
                   "/neck_controller/controller_state", "/clock")
    assert all(DEEP_RELIABLE.get(topic, 0) >= 10000 for topic in controllers), DEEP_RELIABLE
    _, options = build_options(__import__("pathlib").Path("/nonexistent/bag"), topics=controllers)
    assert set(options.topic_qos_profile_overrides) == set(controllers)
