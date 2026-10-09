"""The record-only process of the offline pilot (CP-3428).

It writes every source an episode needs, losslessly, and does nothing else: no alignment, no association, no QC, no verdict. It
never commands, cancels, pauses or resets anything and the Teacher does not know it exists.

* the bag: rosbag2 with MCAP storage, one bag per attempt, `raw/bag`. rosbag2 stamps every message with the receive time of the
  recording node on the SYSTEM clock; `clock-anchor` pairs of (system, monotonic) taken at RECORDING and at stop let the offline
  processor map that receipt onto the monotonic clock the Recorder's rules use.
* `raw/scene-reads.jsonl`: the planning-scene reads the Recorder makes for its rows (`/get_planning_scene`, full read, about 20 Hz),
  as `scene_operation`-shaped payloads (request and response CDR with their sim and monotonic clocks). Service introspection of
  move_group would need code changes in move_group, so the Teacher's own `scene_operation` events plus these reads stand in for it.
* `raw/record-stats.json` at stop: per-topic counts of the closed bag, the reads, both anchors, and what was missing.

States of the ready file: RECORDING once the bag's recording node has subscribed to every core topic that has a publisher.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

READY_SCHEMA = "SO101_RAW_RECORDER_READY_V1"
STATS_SCHEMA = "SO101_RAW_RECORD_STATS_V1"
NODE_NAME = "so101_raw_recorder"
EVENTS_TOPIC = "/so101/teacher/events"
SCENE_READS_TOPIC = "/so101/raw/planning_scene_reads"
CAMERA_TOPICS = ("/head_camera/color", "/head_camera/camera_info", "/wrist_camera/color", "/wrist_camera/camera_info")
SIMULATION_TOPICS = ("/so101/simulation/evidence", "/so101/simulation/physics_step_chunks",
                     "/so101/simulation/robot_contacts", "/so101/simulation/scene_state", "/so101/simulation/joints",
                     "/so101/simulation/physics_hazard")
CONTROL_TOPICS = ("/joint_states", "/arm_controller/controller_state", "/gripper_controller/controller_state",
                  "/neck_controller/controller_state")
#: Everything the Recorder subscribes to (cameras, world, scene state, chunks, joint states, controller states, the Teacher's
#: events, the simulation clock) and the topics around them the pilot may need.
TOPICS = ("/clock", *CAMERA_TOPICS, *SIMULATION_TOPICS, *CONTROL_TOPICS, EVENTS_TOPIC, SCENE_READS_TOPIC)
#: Topics that must have a publisher and be subscribed before the Teacher may start (the events topic has none until it does).
CORE_TOPICS = ("/clock", "/head_camera/color", "/wrist_camera/color", "/so101/simulation/evidence",
               "/so101/simulation/physics_step_chunks", "/so101/simulation/scene_state", "/joint_states",
               "/arm_controller/controller_state", "/gripper_controller/controller_state",
               "/neck_controller/controller_state", "/head_camera/camera_info", "/wrist_camera/camera_info",
               "/so101/simulation/robot_contacts", SCENE_READS_TOPIC)
#: Deep reliable queues for the high-rate topics (500 steps/s of chunks, 500 Hz controller states): the recorder must not be the
#: slow subscriber. The world topic is left to rosbag2's own adaptation to the publisher (transient-local, 256 deep).
DEEP_RELIABLE = {"/so101/simulation/physics_step_chunks": 1000, "/so101/simulation/robot_contacts": 10000,
                 "/arm_controller/controller_state": 20000, "/gripper_controller/controller_state": 20000,
                 "/neck_controller/controller_state": 20000, "/clock": 20000}


#: `debug` is what makes rosbag2 print the per-topic loss lines (there is no per-topic status at `info`).
RECORDER_LOG_LEVEL = "debug"
_TRANSPORT_LOST = re.compile(r"Number of messages lost on the transport layer:\s*(\d+)")


_TOPIC_LOST = re.compile(r"Messages lost on transport layer for topic '([^']+)'\. Total lost:\s*(\d+)")
_TOPIC_LOST_EVENT = re.compile(r"\[(\d+)\.(\d{1,9})\]\s.*?Messages lost on transport layer for topic '([^']+)'\. Total lost:\s*(\d+)")


def transport_lost_events_from_log(text: str) -> list:
    """One entry per per-topic loss line of the recorder's debug log: {"topic", "total" (cumulative), "log_time_ns"}.

    `log_time_ns` is the system-clock time rosbag2 stamped the line with (the same clock as the bag's message stamps). A line is
    written when the loss is reported, never before the loss, so a line logged before an instant proves the loss was earlier."""
    events = []
    for match in _TOPIC_LOST_EVENT.finditer(text):
        seconds, fraction, topic, total = match.groups()
        events.append({"topic": topic, "total": int(total), "log_time_ns": int(seconds) * 10**9 + int(fraction.ljust(9, "0"))})
    return events




def transport_lost_by_topic_from_log(text: str) -> dict:
    """{topic: messages lost} from the DEBUG lines `ros2 bag record --log-level debug` prints per lost-message event.

    Each line carries the subscription's cumulative total, so the last (largest) value of a topic is its loss. A log without such
    lines gives {} (a recorder that ran without debug logging, or lost nothing): the caller then knows only the aggregate."""
    by_topic: dict = {}
    for match in _TOPIC_LOST.finditer(text):
        by_topic[match.group(1)] = max(by_topic.get(match.group(1), 0), int(match.group(2)))
    return dict(sorted(by_topic.items()))


def transport_lost_from_log(text: str) -> int:
    """The messages `ros2 bag record` reports it lost on the transport layer, summed over the log (it prints the total at stop)."""
    return sum(int(match.group(1)) for match in _TRANSPORT_LOST.finditer(text))


def _atomic_json(path: Path, document: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.pending")
    with open(staging, "wb") as stream:
        stream.write((json.dumps(document, sort_keys=True, default=str, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path)


def clock_anchor() -> dict:
    """One instant on both clocks, read back to back."""
    mono_a, system, mono_b = time.monotonic_ns(), time.time_ns(), time.monotonic_ns()
    return {"system_ns": system, "monotonic_ns": (mono_a + mono_b) // 2, "uncertainty_ns": mono_b - mono_a}


def build_options(bag_dir: Path, topics=TOPICS, node_name=NODE_NAME):
    import rosbag2_py
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

    storage = rosbag2_py.StorageOptions(uri=str(bag_dir), storage_id="mcap", max_cache_size=256 * 1024 * 1024)
    options = rosbag2_py.RecordOptions()
    options.topics = list(topics)
    options.rmw_serialization_format = "cdr"
    options.include_unpublished_topics = True
    options.disable_keyboard_controls = True
    options.topic_polling_interval = __import__("datetime").timedelta(milliseconds=100)
    options.topic_qos_profile_overrides = {
        topic: QoSProfile(depth=depth, history=HistoryPolicy.KEEP_LAST, reliability=ReliabilityPolicy.RELIABLE)
        for topic, depth in DEEP_RELIABLE.items() if topic in topics}
    return storage, options


class SceneReadSidecar:
    """`/get_planning_scene` full reads at about 20 Hz, written as they finish (lossless, line by line)."""

    PERIOD_S = 0.05

    def __init__(self, node, path: Path, *, clock=time.monotonic) -> None:
        from std_msgs.msg import String

        self._node, self._path, self._clock = node, Path(path), clock
        self._publisher = node.create_publisher(String, SCENE_READS_TOPIC, 1000)
        self._stop = threading.Event()
        self._thread = None
        self.count = 0
        self.errors = 0
        #: CP-3489: reads are written to the sidecar file from the first one, but only published on the topic once the bag recorder has
        #: matched its subscription (a read published earlier is not in the bag, which the bag/sidecar count would show as a loss)
        self._publish_ready = threading.Event()
        self.published = 0
        self._fsync_wanted = threading.Event()
        self._fsync_thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="so101-raw-scene-reads", daemon=True)
        self._thread.start()

    def enable_publishing(self) -> None:
        """The bag recorder subscribes to the topic: reads from now on are also published."""
        self._publish_ready.set()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(3.0)

    def _fsync_loop(self, descriptor: int) -> None:
        """Makes the sidecar durable off the read loop: an `fsync` on a busy filesystem takes up to hundreds of milliseconds, and the
        read loop (about 20 Hz, and the Recorder's causal join needs every read) must not wait for it (CP-3489)."""
        while True:
            self._fsync_wanted.wait()
            self._fsync_wanted.clear()
            try:
                os.fsync(descriptor)
            except OSError:
                pass
            if self._stop.is_set():
                return

    def _loop(self):
        from collections import deque

        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene
        from std_msgs.msg import String

        from ...control.planning_scene.task_scene import record_scene_service_call
        from ..scene_operation import scene_operation_payload

        client = self._node.create_client(GetPlanningScene, "/get_planning_scene")
        request = GetPlanningScene.Request()
        request.components.components = (PlanningSceneComponents.WORLD_OBJECT_NAMES
                                         | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                                         | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
                                         | PlanningSceneComponents.OBJECT_COLORS)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "ab") as stream:
            self._fsync_thread = threading.Thread(target=self._fsync_loop, args=(stream.fileno(),),
                                                  name="so101-raw-scene-reads-fsync", daemon=True)
            self._fsync_thread.start()

            def write(record, call_request, response):
                payload = scene_operation_payload(record, call_request, response, state="RAW_READ")
                line = json.dumps({"recorded_monotonic_ns": time.monotonic_ns(), "recorded_system_ns": time.time_ns(),
                                   "payload": payload}, sort_keys=True, allow_nan=False)
                stream.write(line.encode() + b"\n")
                if self._publish_ready.is_set():
                    self._publisher.publish(String(data=line))
                    self.published += 1
                self.count += 1
                if self.count % 20 == 0:
                    stream.flush()
                    self._fsync_wanted.set()        # the durable write happens on its own thread

            def invoke():
                if not client.wait_for_service(timeout_sec=1.0):
                    raise RuntimeError("RAW_SCENE_SERVICE_UNAVAILABLE")
                future = client.call_async(request)
                deadline = time.monotonic() + 1.0
                while not future.done() and time.monotonic() < deadline:
                    time.sleep(0.001)
                if not future.done():
                    raise RuntimeError("RAW_SCENE_QUERY_TIMEOUT")
                return future.result()

            while not self._stop.is_set():
                began = time.monotonic()
                try:
                    record_scene_service_call(request=request, phase="RAW_SCENE_READ", service="/get_planning_scene",
                                              invoke=invoke, records=deque(maxlen=1), ros_clock=self._node.get_clock(),
                                              on_record=write)
                except Exception:   # a refused or timed-out read is a gap the offline processor will see
                    self.errors += 1
                self._stop.wait(max(0.0, self.PERIOD_S - (time.monotonic() - began)))
            stream.flush()
            self._fsync_wanted.set()
            self._fsync_thread.join(5.0)
            os.fsync(stream.fileno())


class RawRecorder:
    def __init__(self, bag_dir, *, topics=TOPICS, core_topics=CORE_TOPICS, node_name=NODE_NAME, scene_reads=None,
                 domain_node=None) -> None:
        self.bag_dir, self.topics, self.core_topics, self.node_name = Path(bag_dir), tuple(topics), tuple(core_topics), node_name
        self.scene_reads_path = None if scene_reads is None else Path(scene_reads)
        self._recorder = None
        self._thread = None
        self._probe = None
        self._executor = None
        self._sidecar = None
        self.failure = None
        self.anchor_start = self.anchor_end = None
        self._received = {}
        self._subscriptions = {}
        self._log = None
        self._spin_thread = None
        self._recording_ready = False
        self._matched_counts = {}

    def start(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.parameter import Parameter

        if self.bag_dir.exists():
            raise FileExistsError(f"RAW_BAG_EXISTS: {self.bag_dir}")
        self.bag_dir.parent.mkdir(parents=True, exist_ok=True)
        if not rclpy.ok():
            rclpy.init(signal_handler_options=rclpy.signals.SignalHandlerOptions.NO)
        self._probe = rclpy.create_node(self.node_name + "_probe",
                                        parameter_overrides=[Parameter("use_sim_time", Parameter.Type.BOOL, True)])
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._probe)
        self._spin_thread = threading.Thread(target=self._executor.spin, name="so101-raw-probe-spin", daemon=True)
        self._spin_thread.start()
        executable = shutil.which("ros2")
        if executable is None or not os.access(executable, os.X_OK):
            raise RuntimeError("RAW_ROS2_EXECUTABLE_UNAVAILABLE")
        import yaml

        qos_path = self.bag_dir.parent / (self.bag_dir.name + "-qos.yaml")
        overrides = {topic: {"history": "keep_last", "depth": depth, "reliability": "reliable", "durability": "volatile"}
                     for topic, depth in DEEP_RELIABLE.items() if topic in self.topics}
        qos_path.write_text(yaml.safe_dump(overrides))
        self._log = open(self.bag_dir.parent / (self.bag_dir.name + "-record.log"), "xb")
        self._recorder = subprocess.Popen([executable, "bag", "record", "-s", "mcap", "-o", str(self.bag_dir),
                                          "--node-name", self.node_name, "--disable-keyboard-controls",
                                          "--log-level", RECORDER_LOG_LEVEL,
                                          "--max-cache-size", str(256 * 1024 * 1024),
                                          "--qos-profile-overrides-path", str(qos_path), *self.topics],
                                         stdout=self._log, stderr=subprocess.STDOUT, start_new_session=True,
                                         env=dict(os.environ, ROS_DOMAIN_ID=str(self._probe.context.get_domain_id())))
        if self.scene_reads_path is not None:
            self._sidecar = SceneReadSidecar(self._probe, self.scene_reads_path)
            self._sidecar.start()

    def subscription_state(self) -> dict:
        """{topic: {"publishers": n, "recording": bool}} from the graph: is the bag's node among the subscribers?"""
        state = {}
        for topic in self.topics:
            infos = self._probe.get_publishers_info_by_topic(topic)
            publishers = len(infos)
            if infos and topic not in self._subscriptions:
                from rosidl_runtime_py.utilities import get_message
                from rclpy.qos import QoSProfile

                offered = infos[0].qos_profile
                profile = QoSProfile(depth=1000, reliability=offered.reliability, durability=offered.durability)

                def received(_message, name=topic):
                    self._received[name] = self._received.get(name, 0) + 1

                self._subscriptions[topic] = self._probe.create_subscription(get_message(infos[0].topic_type), topic,
                                                                            received, profile, raw=True)
            recording = any(info.node_name == self.node_name for info in self._probe.get_subscriptions_info_by_topic(topic))
            if recording and topic == SCENE_READS_TOPIC and self._sidecar is not None:
                self._sidecar.enable_publishing()       # the bag has matched: reads are published from now on (CP-3489)
            count = self._received.get(topic, 0)
            if recording and topic not in self._matched_counts:
                self._matched_counts[topic] = count
            state[topic] = {"publishers": publishers, "recording": recording, "received": count,
                            "received_after_match": count - self._matched_counts.get(topic, count)}
        return state

    def wait_recording(self, timeout_s: float, sleep=time.sleep, clock=time.monotonic):
        """(ok, state): every core topic has a publisher and the bag's node subscribes to every topic that has one."""
        deadline = clock() + timeout_s
        while True:
            state = self.subscription_state()
            if self._recorder is not None and self._recorder.poll() is not None:
                self.failure = f"RAW_BAG_PROCESS_EXITED: {self._recorder.returncode}"
            core_ok = all(state[topic]["publishers"] > 0 and state[topic]["recording"]
                          and state[topic]["received_after_match"] > 0 for topic in self.core_topics)
            others_ok = all(item["recording"] for topic, item in state.items() if item["publishers"] > 0)
            if core_ok and others_ok and self.failure is None:
                self.anchor_start = clock_anchor()
                self._recording_ready = True
                return True, state
            if clock() >= deadline or self.failure is not None:
                return False, state
            sleep(0.05)

    def stop(self) -> dict:
        """Stop recording, close the bag and read it back. Never raises."""
        stats = {"schema": STATS_SCHEMA, "failure": self.failure}
        try:
            if self._sidecar is not None:
                self._sidecar.stop()
            if self._recorder is not None:
                deadline = time.monotonic() + 5.0
                while (not self.bag_dir.exists() and self._recorder.poll() is None and time.monotonic() < deadline):
                    time.sleep(0.02)
                if self._recorder.poll() is None:
                    os.killpg(self._recorder.pid, signal.SIGINT)
                try:
                    stats["bag_process_rc"] = self._recorder.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    os.killpg(self._recorder.pid, signal.SIGKILL)
                    self._recorder.wait()
                    self.failure = "RAW_BAG_CLOSE_TIMEOUT"
            self._recorder = None
            if self._log is not None:
                self._log.close()
                self._log = None
            try:
                log_path = self.bag_dir.parent / (self.bag_dir.name + "-record.log")
                log_text = log_path.read_text(errors="replace")
                stats["transport_lost"] = transport_lost_from_log(log_text)
                stats["transport_lost_by_topic"] = transport_lost_by_topic_from_log(log_text)
                stats["transport_lost_events"] = transport_lost_events_from_log(log_text)
            except OSError:
                stats["transport_lost"] = None
            self.anchor_end = clock_anchor()
            if self._executor is not None:
                self._executor.shutdown()
            if self._spin_thread is not None:
                self._spin_thread.join(3.0)
            if self._probe is not None:
                self._probe.destroy_node()
        except BaseException as error:   # noqa: BLE001
            stats["stop_error"] = repr(error)
        stats.update(self.verify_closed())
        stats["failure"] = self.failure
        stats["recording_ready"] = self._recording_ready
        stats["anchor_start"], stats["anchor_end"] = self.anchor_start, self.anchor_end
        if self._sidecar is not None:
            stats["scene_reads"] = {"count": self._sidecar.count, "errors": self._sidecar.errors,
                                    "published": self._sidecar.published}
        return stats

    def verify_closed(self) -> dict:
        from .bag_io import bag_info

        try:
            info = bag_info(self.bag_dir)
        except Exception as error:   # noqa: BLE001
            return {"closed": False, "bag_error": repr(error)[:300]}
        missing = [topic for topic in self.core_topics if info["topics"].get(topic, {}).get("count", 0) == 0]
        return {"closed": True, "bag": info, "missing_core_topics": missing}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="so101_raw_recorder")
    parser.add_argument("--bag-dir", type=Path, required=True)
    parser.add_argument("--scene-reads", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--stats-file", type=Path, required=True)
    parser.add_argument("--ready-timeout-s", type=float, default=30.0)
    options = parser.parse_args(argv)
    recorder = RawRecorder(options.bag_dir, scene_reads=options.scene_reads)
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    try:
        recorder.start()
        ok, state = recorder.wait_recording(options.ready_timeout_s)
        _atomic_json(options.ready_file, {"schema": READY_SCHEMA, "state": "RECORDING" if ok else "NOT_RECORDING",
                                          "pid": os.getpid(), "anchor": recorder.anchor_start, "topics": state})
    except BaseException as error:   # noqa: BLE001
        _atomic_json(options.ready_file, {"schema": READY_SCHEMA, "state": "FAILED", "error": repr(error)[:300]})
        _atomic_json(options.stats_file, recorder.stop())
        return 3
    stop.wait()
    stats = recorder.stop()
    _atomic_json(options.stats_file, stats)
    return 0 if (stats.get("closed") and not stats.get("failure") and stats.get("recording_ready")
                 and not stats.get("missing_core_topics") and not stats.get("stop_error")) else 3


if __name__ == "__main__":
    raise SystemExit(main())
