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
