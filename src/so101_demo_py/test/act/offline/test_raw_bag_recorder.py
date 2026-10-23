"""The record-only process records every message of the topics it was given into a closed MCAP bag, reports RECORDING
only once its recording node subscribes, and reads the bag back at stop."""
import threading
import time
import os
import sys

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
    # lossless zstd chunk compression is configured and observed in the closed bag's own chunks, and recorded in the stats
    assert stats["bag_compression"]["compression"] == "Zstd" and stats["bag_compression"]["observed_chunk_compression"] == ["zstd"], stats
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


def test_an_instance_records_with_the_stock_recorder_and_writes_no_topic_map(
        tmp_path, monkeypatch, isolated_ros_domain):
    """The instance marker alone decides the bag root; the recorder is `ros2 bag record` on the logical names."""
    monkeypatch.delenv("ROS_NAMESPACE", raising=False)
    root = tmp_path / "w00" / "g1"
    root.mkdir(parents=True)
    (root / "output").mkdir()
    monkeypatch.setenv("SO101_ACT_INSTANCE_ROOT", str(root))
    monkeypatch.setenv("SO101_ACT_INSTANCE_OUTPUT", str(root / "output"))     # a native layout: the output is the owned root's own
    from so101_demo.act.offline.raw_recorder import _bag_root_evidence
    rclpy.init()
    node = rclpy.create_node("instance_recorder_source")
    names = ("/rec14/a", "/rec14/b")
    publishers = {name: node.create_publisher(String, name, 100) for name in names}
    recorder = RawRecorder(root / "output" / "tasks" / "task-1" / "raw" / "bag", topics=names, core_topics=names)
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
        assert not any("__ns" in str(item) for item in argv)
        okay, state = recorder.wait_recording(20.0)
        assert okay, state
        assert recorder.bag_root["location"] == "task_output" and recorder.bag_root["output_identity"]["same"] is True
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
    assert _bag_root_evidence(recorder)["bag_root"]["location"] == "task_output"
    assert not (recorder.bag_dir.parent / (recorder.bag_dir.name + "-topic-map.json")).exists()


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
