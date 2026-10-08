"""A small synthetic MCAP of one Teacher attempt, written with the real message types, and sources that read it back (P2 tests).

Sim time is the bag's spine. Producer monotonic = MONO0 + sim; the bag stamps (system clock) = monotonic + SYS_OFFSET + the
topic's delivery lag, so the anchors in `record-stats.json` are exact and every message has a known receipt instant.

The scenario is the one `test_act_episode_recorder.SyntheticSources` plays (10 Hz ticks at 1.0 ... 1.5 s, the Teacher's events at
the same instants) with every source now a topic of the bag: images, `/joint_states`, controller states on the 2 ms grid, physics
chunks, world evidence, the event stream, `/clock`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from so101_demo.act.offline.bag_io import BagWriter
from so101_demo.act.offline.raw_recorder import CORE_TOPICS, EVENTS_TOPIC, SCENE_READS_TOPIC
from so101_demo.act.teacher_event_stream import StreamIdentity, TeacherEventStream
from test_act_episode_recorder import END_STEP, START_STEP, STAMPS, SourcesDefaults, observation

MONO0 = 2_000_000_000_000
SYS_OFFSET = 1_700_000_000_000_000_000
SESSION, EPOCH, ATTEMPT = "session-1", 2, "attempt-1"
BAG_START_S, BAG_END_S = 0.9, 1.75
CHUNK_STAMPS = (*STAMPS, 1.6, 1.7)
LAG_NS = {"clock": 200_000, "state": 500_000, "image": 5_000_000, "joint": 6_000_000, "chunk": 3_000_000,
          "world": 500_000, "event": 6_000_000, "other": 1_000_000}
from so101_demo.act.joints import ARM_JOINTS
GRIPPER, NECK = tuple(ARM_JOINTS[5:]), ("neck_yaw_joint",)
STATE_PERIOD_NS = 2_000_000


def mono_of(sim_s: float) -> int:
    return MONO0 + round(sim_s * 1e9)


def system_of(mono_ns: int) -> int:
    return mono_ns + SYS_OFFSET


def arm_reference(t_s: float):
    """The controller's published reference at sim time t: distinct per joint and per instant, so a label can be checked."""
    return [round(0.1 * (index + 1) + 0.5 * t_s, 9) for index in range(5)], [round(0.6 + 0.5 * t_s, 9)]


def _stamp(message_stamp, sim_ns):
    message_stamp.sec, message_stamp.nanosec = divmod(int(sim_ns), 1_000_000_000)


def _chunk(sequence, first, count):
    from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk

    samples = []
    for offset in range(count):
        step = first + offset
        begin = mono_of(step * 0.002)
        sample = PhysicsStepEvidence(
            simulation_session_id=SESSION, reset_epoch=EPOCH, physics_step=step, simulation_time_s=step * 0.002,
            clock_interval_begin_monotonic_ns=begin, clock_interval_end_monotonic_ns=begin + 1_800_000,
            model_qpos=[.1, .2], model_qvel=[.3], has_contact=False, maximum_normal_force_n=0., total_normal_force_n=0.,
            global_max_single_contact_force_n=0.)
        sample.object_pose_world.orientation.w = 1.
        samples.append(sample)
    return PhysicsStepEvidenceChunk(
        chunk_sequence=sequence, simulation_session_id=SESSION, reset_epoch=EPOCH, first_physics_step=first,
        last_physics_step=first + count - 1, first_simulation_time_s=samples[0].simulation_time_s,
        last_simulation_time_s=samples[-1].simulation_time_s, samples=samples)


def scripted_events():
    """[(sim_s, text)] for the Teacher's seven events, from the real stream so the envelope is the real one."""
    times = [1.0, 1.0, 1.05, 1.1, 1.3, 1.4, 1.5]
    clock = iter(round(t * 1e9) for t in times)
    published = []
    stream = TeacherEventStream(StreamIdentity(SESSION, EPOCH, ATTEMPT), clock_ns=lambda: next(clock),
                                publish=published.append, start=False)
    plan = [
        ("reset_complete", {"session_id": SESSION, "reset_epoch": EPOCH, "simulation_time_s": 1.0,
                            "simulation_step": START_STEP, "publisher_sequence": START_STEP}),
        ("teacher_start_observation", {"observation": observation(START_STEP)}),
        ("phase_begin", {"state": "PREPARE_OPEN_GRIPPER", "sim_time_ns": 1_050_000_000, "monotonic_ns": 1,
                         "goal_sent": True, "goal_kind": "gripper"}),
        ("phase_finish", {"state": "PREPARE_OPEN_GRIPPER", "sim_time_ns": 1_100_000_000, "monotonic_ns": 2,
                          "status": "SUCCEEDED", "code": None}),
        ("normal_stop", {"proof": {"stop_confirmed_wall_s": 1.0}}),
        ("teacher_end_observation", {"observation": observation(END_STEP), "problem": None}),
        ("terminal", {"status": "DONE", "teacher_execution_status": "COMPLETED", "teacher_task_result": "PASS",
                      "failure": None}),
    ]
    for kind, payload in plan:
        stream.offer(kind, payload)
        stream.pump()
    return list(zip(times, published))


def messages(*, paused_worlds=()):
    """[(topic, type name, receipt system ns, message)] of the whole scenario."""
    from builtin_interfaces.msg import Time
    from control_msgs.msg import JointTrajectoryControllerState
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import CameraInfo, Image, JointState
    from so101_mujoco_support.msg import RobotContactEvidence, SceneStateEvidence, SimulationEvidence
    from std_msgs.msg import String

    out = []

    def add(topic, type_name, sim_s, lag, message):
        out.append((topic, type_name, system_of(mono_of(sim_s)) + LAG_NS[lag], message))

    steps = round((BAG_END_S - BAG_START_S) / 0.002)
    for index in range(steps + 1):
        sim_ns = round(BAG_START_S * 1e9) + index * STATE_PERIOD_NS
        sim_s = sim_ns / 1e9
        add("/clock", "rosgraph_msgs/msg/Clock", sim_s, "clock", Clock(clock=Time(sec=sim_ns // 10**9, nanosec=sim_ns % 10**9)))
        arm, gripper = arm_reference(sim_s)
        for kind, names, positions in (("arm", tuple(ARM_JOINTS[:5]), arm),
                                       ("gripper", GRIPPER, gripper), ("neck", NECK, [0.0])):
            message = JointTrajectoryControllerState()
            _stamp(message.header.stamp, sim_ns)
            message.joint_names = list(names)
            message.reference.positions = list(positions)
            message.reference.velocities = [0.0] * len(positions)
            add(f"/{kind}_controller/controller_state", "control_msgs/msg/JointTrajectoryControllerState", sim_s, "state",
                message)
    world_index = 0
    sim_ns = round(BAG_START_S * 1e9)
    while sim_ns <= round(BAG_END_S * 1e9):
        world_index += 1
        message = SimulationEvidence()
        _stamp(message.header.stamp, sim_ns)
        message.header.frame_id = "world"
        message.publisher_sequence, message.simulation_step, message.reset_epoch = world_index, sim_ns // 2_000_000, EPOCH
        message.simulation_session_id = SESSION
        message.paused = (world_index - 1) in paused_worlds
        message.object_pose_world.orientation.w = 1.0
        add("/so101/simulation/evidence", "so101_mujoco_support/msg/SimulationEvidence", sim_ns / 1e9, "world", message)
        # the scene state is published in the same call as the world record: same step, same stamp (phase C rule)
        scene = SceneStateEvidence(simulation_session_id=SESSION, reset_epoch=EPOCH, simulation_step=sim_ns // 2_000_000)
        _stamp(scene.header.stamp, sim_ns)
        add("/so101/simulation/scene_state", "so101_mujoco_support/msg/SceneStateEvidence", sim_ns / 1e9, "world", scene)
        sim_ns += 12_000_000
    joint_ns = round(BAG_START_S * 1e9)
    while joint_ns <= round(BAG_END_S * 1e9):
        joints = JointState()
        _stamp(joints.header.stamp, joint_ns)
        joints.name = ["a", "b", "c", "d", "e", "f"]
        joints.position = [0.0] * 6
        add("/joint_states", "sensor_msgs/msg/JointState", joint_ns / 1e9, "joint", joints)
        joint_ns += 10_000_000
    for sequence, stamp in enumerate(CHUNK_STAMPS, start=1):
        last = round(stamp / 0.002)
        add("/so101/simulation/physics_step_chunks", "so101_mujoco_support/msg/PhysicsStepEvidenceChunk", stamp, "chunk",
            _chunk(sequence, last - 49, 50))
    for stamp in STAMPS:
        for camera in ("head", "wrist"):
            image = Image(height=480, width=640, encoding="rgb8", step=1920, data=np.zeros(480 * 640 * 3, np.uint8).tobytes())
            _stamp(image.header.stamp, round(stamp * 1e9))
            image.header.frame_id = f"{camera}_camera"
            add(f"/{camera}_camera/color", "sensor_msgs/msg/Image", stamp, "image", image)
    for stamp in STAMPS:
        for camera in ("head", "wrist"):
            info = CameraInfo(height=480, width=640)
            _stamp(info.header.stamp, round(stamp * 1e9))
            add(f"/{camera}_camera/camera_info", "sensor_msgs/msg/CameraInfo", stamp, "image", info)
    add("/so101/simulation/robot_contacts", "so101_mujoco_support/msg/RobotContactEvidence", 0.95, "other",
        RobotContactEvidence(simulation_session_id=SESSION, reset_epoch=EPOCH, physics_step=475))
    mono = mono_of(0.95)
    add(SCENE_READS_TOPIC, "std_msgs/msg/String", 0.95, "other",
        String(data=json.dumps({"recorded_monotonic_ns": mono, "recorded_system_ns": system_of(mono), "payload": {}})))
    for sim_s, text in scripted_events():
        add(EVENTS_TOPIC, "std_msgs/msg/String", sim_s, "event", String(data=text))
    return out


def build_bag(root: Path, *, omit_topics=(), drop=(), paused_worlds=(), transport_lost=0, transport_lost_by_topic=None,
                transport_lost_events=None) -> Path:
    """Write `root/bag` (MCAP) and `root/record-stats.json`; returns the bag directory.

    `omit_topics`: topics left out entirely. `drop`: (topic, index) messages left out (index counts per topic from 0).
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    plan = messages(paused_worlds=paused_worlds)
    plan.sort(key=lambda item: item[2])
    bag = root / "bag"
    writer = BagWriter(bag)
    seen: dict = {}
    for topic, type_name, system_ns, message in plan:
        index = seen.get(topic, 0)
        seen[topic] = index + 1
        if topic in omit_topics or (topic, index) in set(drop):
            continue
        writer.create(topic, type_name)
        writer.write(topic, message, system_ns)
    writer.close()
    start, end = mono_of(BAG_START_S - 0.05), mono_of(BAG_END_S + 0.05)
    stats = {"anchor_start": {"system_ns": system_of(start), "monotonic_ns": start, "uncertainty_ns": 1000},
         "anchor_end": {"system_ns": system_of(end), "monotonic_ns": end, "uncertainty_ns": 1000},
         "transport_lost": transport_lost, "scene_reads": {"count": 1, "errors": 0}}
    if transport_lost_by_topic is not None:
        stats["transport_lost_by_topic"] = transport_lost_by_topic
    if transport_lost_events is not None:
        stats["transport_lost_events"] = transport_lost_events
    (root / "record-stats.json").write_text(json.dumps(stats))
    return bag


class BagSyntheticSources(SourcesDefaults):
    """`SyntheticSources`' job over the replay node: the capture is fed from the topics the bag delivers.

    Real parts: the physics adapter (continuity), `ControllerReferencePort` (the t+0.1 label from `controller_state`), the
    episode and its lossless writer, the engine. Stand-ins (as in `SyntheticSources`): the capture start and the row pushes.
    """

    def __init__(self, node, episode, options, policy):
        self.node, self.episode = node, episode
        self.inbox = []
        self.counts = {"head": 0, "wrist": 0, "physics": 0, "scene_state": 1, "world": 0, "joint_states": 0}
        self.adapter = self.port = None
        self.events_seen = []
        self.last_image_stamp = 0.0
        self.delivered_events = 0

    def prepare(self, engine):
        from sensor_msgs.msg import Image, JointState
        from so101_demo.adapters.act.ros_episode_physics import RosEpisodePhysicsAdapter
        from so101_demo.adapters.act.ros_teacher_event_stream import RosTeacherEventSubscription
        from so101_demo.act.offline.sources import ControllerReferencePort
        from so101_mujoco_support.msg import SimulationEvidence

        self._events = RosTeacherEventSubscription(self.node, engine.on_event_text)
        self.adapter = RosEpisodePhysicsAdapter(self.node, session_id=SESSION, reset_epoch=EPOCH, nq=2, nv=1,
                                                audit=engine.episode.capture.audit, history_capacity=4096)
        self.port = ControllerReferencePort(self.node, session_id=SESSION, reset_epoch=EPOCH)
        for camera in ("head", "wrist"):
            self.node.create_subscription(Image, f"/{camera}_camera/color",
                                          lambda message, camera=camera: self.inbox.append(("image", camera, message)), 10)
        self.node.create_subscription(JointState, "/joint_states", lambda message: self.inbox.append(("joint", None, message)), 10)
        self.node.create_subscription(SimulationEvidence, "/so101/simulation/evidence", self._world, 10)

    def _world(self, _message):
        self.counts["world"] += 1

    def try_start(self, engine):
        stamps = {camera: [m.header.stamp.sec + m.header.stamp.nanosec / 1e9 for kind, c, m in self.inbox
                           if kind == "image" and c == camera] for camera in ("head", "wrist")}
        if not stamps["head"] or not stamps["wrist"]:
            return None
        start = min(stamps["head"][0], stamps["wrist"][0])
        engine.episode.start(start)
        return start

    def pump(self, engine):
        self.node.deliver_due()
        errors = self.node.take_callback_errors()
        if errors:
            raise RuntimeError("RECORDER_CALLBACK_FAILED: " + " | ".join(errors[:3]))
        self.adapter.drain()
        self.counts["physics"] = self.adapter.receipt_diagnostics()["chunk_count"]
        if not engine.episode.capture.started:
            return
        inbox, self.inbox = self.inbox, []
        for kind, camera, message in inbox:
            stamp = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
            if kind == "image":
                pixels = np.frombuffer(message.data, np.uint8).reshape(480, 640, 3)
                engine.episode.push(camera, stamp_s=stamp, pixels=pixels)
                self.counts[camera] += 1
                self.last_image_stamp = max(self.last_image_stamp, stamp)
            elif any(abs(stamp - tick) < 1e-9 for tick in STAMPS):     # the capture takes the joint states of its own ticks
                engine.episode.push_numeric(stamp_s=stamp, arm=list(message.position), neck=0.0)
                self.counts["joint_states"] += 1

    def collect(self, engine):
        capture = engine.episode.capture
        through = self.port.received_through_s()
        now_s = self.node.get_clock().now().nanoseconds / 1e9
        if through is not None:
            for when in capture.reference_requests(min(now_s, through)):
                capture.on_reference(self.port.read(when))
        capture.drain()

    def on_teacher_event(self, engine, event):
        import time

        self.events_seen.append(event["type"])
        capture = engine.episode.capture
        if event["type"] == "phase_begin" and event["payload"].get("goal_sent") is True:
            capture.on_event({"kind": "first_command", "sim_time_s": 1.05})
        elif event["type"] == "normal_stop":
            now = time.monotonic_ns()
            capture.on_normal_motion_end(dict(sim_time_ns=1_300_000_000, begin_monotonic_ns=now - 1, end_monotonic_ns=now))

    def tail_ready(self, engine):
        return self.last_image_stamp >= STAMPS[-1]

    def end_time_s(self, engine):
        return 1.3

    def physics_steps(self, engine):
        return self.adapter.original_durable_steps()

    def source_counts(self, engine):
        return dict(self.counts)

    def close(self):
        if self.adapter is not None:
            self.adapter.close()
