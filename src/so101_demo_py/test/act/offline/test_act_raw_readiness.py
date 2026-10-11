import json
import os
import signal
import subprocess
import sys
import threading
import time

import rclpy
import pytest
from moveit_msgs.srv import GetPlanningScene
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String

from so101_demo.act.offline.raw_recorder import RawRecorder, SceneReadSidecar


@pytest.fixture(autouse=True)
def raw_context_lifecycle(isolated_ros_domain):
    rclpy.try_shutdown()
    yield
    rclpy.try_shutdown()


def test_a_subscription_without_a_received_message_is_not_recording(tmp_path, isolated_ros_domain):
    if not rclpy.ok():
        rclpy.init()
    node = rclpy.create_node("raw_silent_publisher")
    publisher = node.create_publisher(String, "/raw_test/silent", 10)
    recorder = RawRecorder(tmp_path / "bag", topics=("/raw_test/silent",), core_topics=("/raw_test/silent",))
    try:
        recorder.start()
        ready, state = recorder.wait_recording(0.7)
        assert not ready, state
        publisher.publish(String(data="first"))
        ready, state = recorder.wait_recording(5.0)
        assert ready and state["/raw_test/silent"]["received"] >= 1, state
    finally:
        recorder.stop()
        node.destroy_node()


def test_scene_reads_retain_cdr_and_publish_the_recorded_topic(tmp_path, isolated_ros_domain):
    if not rclpy.ok():
        rclpy.init()
    node = rclpy.create_node("raw_scene_service_test")
    service = node.create_service(GetPlanningScene, "/get_planning_scene", lambda request, response: response)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    recorder = RawRecorder(tmp_path / "bag", topics=("/so101/raw/planning_scene_reads",),
                           core_topics=("/so101/raw/planning_scene_reads",), scene_reads=tmp_path / "scene-reads.jsonl")
    try:
        recorder.start()
        ready, state = recorder.wait_recording(8.0)
        assert ready, state
    finally:
        stats = recorder.stop()
        executor.shutdown()
        thread.join(3.0)
        node.destroy_service(service)
        node.destroy_node()
    assert stats["closed"] and stats["scene_reads"]["count"] > 0, stats
    assert stats["bag"]["topics"]["/so101/raw/planning_scene_reads"]["count"] > 0
    reads = [json.loads(line) for line in (tmp_path / "scene-reads.jsonl").read_text().splitlines()]
    assert reads and reads[0]["payload"]["request_cdr_base64"] and reads[0]["payload"]["response_cdr_base64"]


def test_cli_stop_closes_the_bag_and_writes_stats(tmp_path, isolated_ros_domain):
    process = subprocess.Popen([sys.executable, "-m", "so101_demo.act.offline.raw_recorder",
                                "--bag-dir", str(tmp_path / "bag"), "--scene-reads", str(tmp_path / "scene.jsonl"),
                                "--ready-file", str(tmp_path / "ready.json"), "--stats-file", str(tmp_path / "stats.json"),
                                "--ready-timeout-s", "0.2"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=dict(os.environ))
    try:
        deadline = time.monotonic() + 15.0
        while not (tmp_path / "ready.json").exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "ready.json").exists()
        process.send_signal(signal.SIGTERM)
        output, errors = process.communicate(timeout=15.0)
        assert (tmp_path / "stats.json").exists(), (output, errors)
        stats = json.loads((tmp_path / "stats.json").read_bytes())
        assert stats["closed"], stats
        assert process.returncode == 3, (output, errors)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


# ---- the sidecar never waits for fsync, and publishes only once the bag has matched -------------------------------------

def _scene_service(name):
    node = rclpy.create_node(name)
    service = node.create_service(GetPlanningScene, "/get_planning_scene", lambda request, response: response)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()

    def close():
        executor.shutdown()
        thread.join(3.0)
        node.destroy_service(service)
        node.destroy_node()

    return node, close


def test_the_sidecar_writes_every_read_but_publishes_none_until_the_bag_has_matched(tmp_path, isolated_ros_domain):
    if not rclpy.ok():
        rclpy.init()
    node, close = _scene_service("raw_gate_service")
    sidecar = SceneReadSidecar(node, tmp_path / "scene-reads.jsonl")
    seen = []
    listener = node.create_subscription(String, "/so101/raw/planning_scene_reads", lambda message: seen.append(message), 100)
    try:
        sidecar.start()
        deadline = time.monotonic() + 8.0
        while sidecar.count < 5 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sidecar.count >= 5 and sidecar.published == 0 and seen == [], (sidecar.count, sidecar.published, len(seen))
        before = sidecar.count
        sidecar.enable_publishing()
        deadline = time.monotonic() + 8.0
        while sidecar.published < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sidecar.published >= 3 and len(seen) >= 1
    finally:
        sidecar.stop()
        node.destroy_subscription(listener)
        close()
    lines = (tmp_path / "scene-reads.jsonl").read_text().splitlines()
    assert len(lines) == sidecar.count and sidecar.count > before, "the reads before the gate opened are in the file"


def test_a_slow_fsync_never_stalls_the_read_loop(tmp_path, isolated_ros_domain, monkeypatch):
    """The first live round lost 340 ms reads to one fsync on a busy filesystem: the durable write is on its own thread."""
    from so101_demo.act.offline import raw_recorder

    real = os.fsync
    calls = []

    def slow(descriptor):
        calls.append(time.monotonic())
        time.sleep(0.4)
        return real(descriptor)

    monkeypatch.setattr(raw_recorder.os, "fsync", slow)
    if not rclpy.ok():
        rclpy.init()
    node, close = _scene_service("raw_fsync_service")
    sidecar = SceneReadSidecar(node, tmp_path / "scene-reads.jsonl")
    try:
        sidecar.start()
        deadline = time.monotonic() + 15.0
        while sidecar.count < 70 and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        sidecar.stop()
        close()
    assert sidecar.count >= 70 and len(calls) >= 2, (sidecar.count, len(calls))
    stamps = [json.loads(line)["recorded_monotonic_ns"] / 1e6
              for line in (tmp_path / "scene-reads.jsonl").read_text().splitlines()]
    # skip the first reads (the service is still being discovered): after that every gap is the 50 ms period, not 400 ms
    gaps = [b - a for a, b in zip(stamps[5:], stamps[6:])]
    assert max(gaps) < 200.0, sorted(gaps)[-5:]


def test_the_camera_topics_have_deep_reliable_queues_in_the_bag_overrides(tmp_path, isolated_ros_domain):
    """Camera_info depth 100, images depth 50, written into the bag's QoS overrides like the other deep topics."""
    import yaml
    from so101_demo.act.offline.raw_recorder import DEEP_RELIABLE

    assert {"/head_camera/camera_info": 100, "/wrist_camera/camera_info": 100,
            "/head_camera/color": 50, "/wrist_camera/color": 50}.items() <= DEEP_RELIABLE.items()
    if not rclpy.ok():
        rclpy.init()
    topics = tuple(DEEP_RELIABLE)
    recorder = RawRecorder(tmp_path / "bag", topics=topics, core_topics=("/clock",), scene_reads=None)
    try:
        recorder.start()
    finally:
        recorder.stop()
    overrides = yaml.safe_load((tmp_path / "bag-qos.yaml").read_text())
    for topic in ("/head_camera/camera_info", "/wrist_camera/camera_info", "/head_camera/color", "/wrist_camera/color"):
        assert overrides[topic] == {"history": "keep_last", "depth": DEEP_RELIABLE[topic], "reliability": "reliable",
                                    "durability": "volatile"}
