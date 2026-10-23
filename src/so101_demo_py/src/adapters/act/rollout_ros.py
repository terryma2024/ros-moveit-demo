"""The ROS side of the native rollout executor (design 2026-10-18-so101-act-native-rollout-design.md, task 5).

Everything the episode state machine (`act/rollout_episode.py`) calls on its session is built here:

* `ObservationAssembler` - the observation tick. A new image set of the CONFIGURED cameras (the camera names come from the policy
  bundle, never from this module) joined with the causal joint state gives one observation: `{sim_time_s, state, <camera>...}`.
  The state is the six arm joints, followed by the neck sin and cos when the bundle's state width is 8.
* `JointLimitPermit` - the permit port of the execution adapter. It checks the ACT joint limits and nothing else: no path
  proof, no clearance or contact check (the policy is the planner).
* `ControllerReference` - the adapter's reference port: where the controller will be at the goal's start time.
* `ThreadInferenceTransport` - the transport `ActInferenceProcess` sends over: one worker thread owns the model call, so the
  control loop never waits on it.
* `WorldCupObserver` - the cup pose and speed of the world evidence stream, in the Teacher's observation document.
* `RolloutSession` - the object the state machine drives, over the pieces above, with the command ports
  (`ActExecutionAdapter` over two `RosControllerPort`s) wired by `build_ros_session`.

The assembler, permit, reference, transport, world observer and session import no ROS and are tested with fakes. `build_ros_session`
takes a ROS `binding` (the real one wraps rclpy) so its wiring is tested without a graph too.
"""

from __future__ import annotations

from collections import deque
import hashlib
import math
import queue
import threading
import time

import numpy as np

from so101_demo.act.contracts import ContractError, finite
from so101_demo.act.execution import ActExecutionAdapter, bounded_positions, prefix_sha256
from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS
from so101_demo.act.synchronizer import causal_sample, source_age_ok_ns, time_ns

NECK_JOINT = "neck_yaw_joint"
STATE_WITH_NECK = 8
STATE_ARM_ONLY = 6
#: The depth of the camera rings (a frame is about 0.9 MB) and of the joint-state ring (500 Hz, two floats each).
CAMERA_RING = 32
JOINT_RING = 2048


def _pixels_sha256(pixels) -> str:
    return hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest()


class ObservationAssembler:
    """New image sets of the configured cameras, joined with the causal joint state.

    `poll()` returns an observation only when EVERY configured camera has a frame newer than the one last emitted, the newest
    frames are within `max_skew_s` of each other, and none is older than `max_age_s` against the latest joint-state stamp. It never
    returns the same frame twice and never a frame at or below the reset boundary (`source_floor_s`): a reset-era message that is
    still queued cannot start an episode.
    """

    def __init__(self, *, cameras, state_dim, max_age_s, max_skew_s, image_shape=(480, 640, 3),
                 monotonic=time.monotonic) -> None:
        cameras = tuple(cameras)
        if (not cameras or len(set(cameras)) != len(cameras) or any(not isinstance(name, str) or not name for name in cameras)
                or state_dim not in (STATE_WITH_NECK, STATE_ARM_ONLY) or isinstance(state_dim, bool)):
            raise ValueError("ROLLOUT_OBSERVATION_CONFIG_INVALID")
        shape = tuple(image_shape)
        if len(shape) != 3 or shape[2] != 3 or any(type(item) is not int or item < 1 for item in shape):
            raise ValueError("ROLLOUT_OBSERVATION_CONFIG_INVALID")
        self.cameras, self.state_dim, self.image_shape = cameras, state_dim, shape
        self.max_age_s, self.max_skew_s = finite(max_age_s, nonnegative=True), finite(max_skew_s, nonnegative=True)
        self.monotonic = monotonic
        self._lock = threading.RLock()
        self._frames = {name: deque(maxlen=CAMERA_RING) for name in cameras}
        self._joints = deque(maxlen=JOINT_RING)
        self._emitted = dict.fromkeys(cameras)
        self._floor_ns = None
        self.session_id = None
        self.rejected = deque(maxlen=64)
        self.rejected_count = 0

    @property
    def joint_names(self) -> tuple:
        return ARM_JOINTS + ((NECK_JOINT,) if self.state_dim == STATE_WITH_NECK else ())

    def reset(self, session_id: str, *, source_floor_s: float) -> None:
        with self._lock:
            for ring in (*self._frames.values(), self._joints):
                ring.clear()
            self._emitted = dict.fromkeys(self.cameras)
            self._floor_ns = time_ns(finite(source_floor_s, nonnegative=True))
            self.session_id = session_id

    def _reject(self, reason: str) -> bool:
        self.rejected.append(reason)
        self.rejected_count += 1
        return False

    def note_rejected(self, reason: str) -> None:
        """Count a message the ROS callback itself refused (wrong encoding or shape, unreadable joint names)."""

        with self._lock:
            self._reject(reason)

    def push_image(self, camera, stamp_s, pixels, *, received_wall_s=None) -> bool:
        """Offer one decoded frame; a refused frame is counted and returns False (a ROS callback must not raise)."""

        received = self.monotonic() if received_wall_s is None else received_wall_s
        with self._lock:
            ring = self._frames.get(camera)
            if ring is None or self._floor_ns is None:
                return self._reject("INPUT_SESSION_INVALID")
            try:
                stamp_ns = time_ns(stamp_s)
            except ContractError:
                return self._reject("INPUT_TIMESTAMP_INVALID")
            if stamp_ns <= self._floor_ns:
                return self._reject("INPUT_RESET_STALE")
            if ring and stamp_ns <= time_ns(ring[-1][0]):
                return self._reject("INPUT_TIMESTAMP_INVALID")
            if not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8 or pixels.shape != self.image_shape:
                return self._reject("INPUT_RGB_INVALID")
            ring.append((float(stamp_s), pixels.copy(), received))
            return True

    def push_joints(self, stamp_s, positions: dict, *, received_wall_s=None) -> bool:
        """Offer one joint state (`positions` maps joint name to radians); the neck is read only for a state width of 8."""

        received = self.monotonic() if received_wall_s is None else received_wall_s
        with self._lock:
            if self._floor_ns is None:
                return self._reject("INPUT_SESSION_INVALID")
            try:
                stamp_ns = time_ns(stamp_s)
                values = tuple(finite(positions[name]) for name in self.joint_names)
            except (ContractError, KeyError, TypeError):
                return self._reject("JOINT_MAPPING_INVALID")
            if stamp_ns <= self._floor_ns:
                return self._reject("INPUT_RESET_STALE")
            if self._joints and stamp_ns <= time_ns(self._joints[-1][0]):
                return self._reject("INPUT_TIMESTAMP_INVALID")
            self._joints.append((float(stamp_s), values, received))
            return True

    def sim_time(self):
        """The simulation clock as the executor sees it: the stamp of the newest accepted joint state (None before the first)."""

        with self._lock:
            return self._joints[-1][0] if self._joints else None

    def latest_arm(self):
        with self._lock:
            return self._joints[-1][1][:6] if self._joints else None

    def poll(self):
        """(observation, audit) for a new image set, or None."""

        with self._lock:
            if not self._joints or any(not ring for ring in self._frames.values()):
                return None
            newest = {name: ring[-1] for name, ring in self._frames.items()}
            if any(self._emitted[name] is not None and time_ns(frame[0]) <= time_ns(self._emitted[name])
                   for name, frame in newest.items()):
                return None
            stamps = {name: frame[0] for name, frame in newest.items()}
            now_ns = time_ns(self._joints[-1][0])
            ages = [now_ns - time_ns(stamp) for stamp in stamps.values()]
            if max(map(time_ns, stamps.values())) - min(map(time_ns, stamps.values())) > time_ns(self.max_skew_s):
                return None
            if not all(source_age_ok_ns(now_ns, time_ns(stamp), time_ns(self.max_age_s)) for stamp in stamps.values()):
                return None
            at_s = max(stamps.values())
            try:
                joint_stamp, values, joint_received = causal_sample(
                    [(stamp, (stamp, vector, received)) for stamp, vector, received in self._joints], at_s, self.max_age_s)
            except ValueError:
                return None
            state = list(values[:6])
            if self.state_dim == STATE_WITH_NECK:
                state += [math.sin(values[6]), math.cos(values[6])]
            observation = {"sim_time_s": at_s, "state": state}
            audit = {"stamps": dict(stamps), "joint_stamp_s": joint_stamp, "image_ages_ns": ages,
                     "received_wall_s": {name: frame[2] for name, frame in newest.items()},
                     "joint_received_wall_s": joint_received,
                     "pixel_sha256": {name: _pixels_sha256(frame[1]) for name, frame in newest.items()},
                     "neck_yaw_rad": values[6] if self.state_dim == STATE_WITH_NECK else None}
            for name, frame in newest.items():
                observation[name] = frame[1]
                self._emitted[name] = frame[0]
            return observation, audit


class JointLimitPermit:
    """The permit port of the execution adapter: the ACT joint limits and the revoke latch, nothing else."""

    def __init__(self) -> None:
        self.revoked = None

    def issue(self, prefix: dict) -> dict:
        return {"prefix_sha256": prefix_sha256(prefix)}

    def require(self, permit, prefix: dict):
        if self.revoked is not None:
            raise PermissionError("PERMIT_REVOKED")
        if not isinstance(permit, dict) or permit.get("prefix_sha256") != prefix_sha256(prefix):
            raise PermissionError("PERMIT_INVALID")
        for row in prefix["positions"]:
            bounded_positions(row)
        return None

    def revoke(self, reason: str) -> None:
        self.revoked = reason


class ControllerReference:
    """The reference port: the controller's position at a future simulation time.

    With a goal in flight it is that goal's trajectory (linear between its knots, held after the last one); before any goal it is
    the latest measured arm and gripper position. The returned six values are the first knot of the next goal, so the arm starts
    the new segment from where it will be.
    """

    def __init__(self, *, measured, last_goals) -> None:
        self.measured, self.last_goals = measured, last_goals

    @staticmethod
    def _at(goal: dict, time_s: float) -> tuple:
        rel = time_s - goal["header_stamp_s"]
        offsets, rows = goal["time_from_start_s"], goal["positions"]
        if rel <= offsets[0]:
            return tuple(rows[0])
        for index in range(1, len(offsets)):
            if rel <= offsets[index]:
                span = offsets[index] - offsets[index - 1]
                weight = (rel - offsets[index - 1]) / span
                return tuple(a + weight * (b - a) for a, b in zip(rows[index - 1], rows[index], strict=True))
        return tuple(rows[-1])

    def __call__(self, start_s: float) -> tuple:
        goals = self.last_goals()
        if goals is None:
            held = self.measured()
            if held is None:
                raise RuntimeError("CONTROLLER_REFERENCE_UNAVAILABLE")
            return tuple(float(value) for value in held)
        arm, gripper = goals
        return self._at(arm, start_s) + self._at(gripper, start_s)


class ThreadInferenceTransport:
    """`ActInferenceProcess` transport over one worker thread that owns the model call.

    `send` hands the request to the worker and returns; `receive` returns the finished reply of the latest request (with its age
    since the send) or None. A reply that belongs to an abandoned earlier request is dropped by sequence, so a slow inference can
    never be applied to a later observation. A failing model call becomes a reply without actions, which the boundary refuses.
    """

    def __init__(self, infer, *, monotonic=time.monotonic, span_sink=None) -> None:
        if not callable(infer):
            raise ValueError("INFERENCE_TRANSPORT_INVALID")
        self._infer, self.monotonic = infer, monotonic
        self._span_sink = span_sink                 # diagnostics only: span_sink("call", start, end) per model call
        self._requests = queue.Queue()
        self._lock = threading.Lock()
        self._latest = None
        self._reply = None
        self._busy = False
        self._closed = False
        self._thread = threading.Thread(target=self._work, name="act-rollout-inference", daemon=True)
        self._thread.start()

    def _work(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            with self._lock:
                if request["sequence"] != self._latest:
                    continue                    # superseded before it started
                self._busy = True
            call_start = self.monotonic()
            try:
                reply = {"sequence": request["sequence"], "actions": self._infer(request["observation"])}
            except Exception as error:          # noqa: BLE001 - reported as an invalid reply, never raised in the worker
                reply = {"sequence": request["sequence"], "error": (str(error) or type(error).__name__)[:300]}
            if self._span_sink is not None:
                try:
                    self._span_sink("call", call_start, self.monotonic())
                except Exception:               # noqa: BLE001 - diagnostics never change a reply
                    pass
            with self._lock:
                self._busy = False
                if request["sequence"] == self._latest:
                    self._reply = (reply, request["sent_s"])

    def send(self, request: dict) -> None:
        if self._closed:
            raise ValueError("INFERENCE_PROCESS_CLOSED")
        job = {"sequence": request["sequence"], "observation": request["observation"], "sent_s": self.monotonic()}
        with self._lock:
            self._latest, self._reply = request["sequence"], None
        self._requests.put(job)

    def receive(self):
        with self._lock:
            if self._reply is None:
                return None
            reply, sent_s = self._reply
            self._reply = None
        return dict(reply, age_s=max(0.0, self.monotonic() - sent_s))

    def idle(self) -> bool:
        with self._lock:
            return not self._busy and self._requests.empty()

    def quiesce(self, timeout_s: float, sleep=time.sleep) -> bool:
        """Wait (bounded) for the model call in progress to return, so that a policy reset never overlaps it."""

        deadline = self.monotonic() + timeout_s
        with self._lock:
            self._latest, self._reply = None, None
        while not self.idle():
            if self.monotonic() >= deadline:
                return False
            sleep(0.002)
        return True

    def close(self):
        self._closed = True
        self._requests.put(None)
        self._thread.join(timeout=5.0)
        return not self._thread.is_alive()


class WorldCupObserver:
    """The cup pose of the world evidence stream, as the Teacher's observation document (None when none is fresh)."""

    def __init__(self, observer) -> None:
        if not callable(getattr(observer, "snapshot_with_receipt", None)):
            raise ValueError("ROLLOUT_WORLD_OBSERVER_INVALID")
        self.observer = observer
        self.last_error = None

    def cup_pose(self):
        try:
            evidence = self.observer.snapshot_with_receipt().evidence
        except Exception as error:      # noqa: BLE001 - a stale or missing sample is "no pose", the machine decides what that means
            self.last_error = (str(error) or type(error).__name__)[:200]
            return None
        state = evidence.object_state
        x, y, z, w = state.orientation_xyzw
        return {"position": list(state.position_world), "orientation": {"x": x, "y": y, "z": z, "w": w},
                "simulation_time_s": evidence.simulation_time_s, "frame_id": evidence.frame_id,
                "object_id": state.body, "session_id": evidence.simulation_session_id,
                "reset_epoch": evidence.reset_epoch, "publisher_sequence": evidence.publisher_sequence,
                "simulation_step": evidence.simulation_step,
                "linear_speed_m_s": math.sqrt(sum(item * item for item in state.linear_velocity_world))}


class RolloutSession:
    """What the episode state machine drives: observe, command, stop, look at the world, close.

    Refusals that must NOT disturb the controllers are made here, before the adapter is called: the adapter stops the arm when a
    submission fails after a goal exists, but a late prefix or an out-of-limit row is only a skipped command (design D2).
    """

    def __init__(self, *, assembler, adapter, permit, world, spin, close, submit_lead_s, drain_timeout_s=1.0,
                 monotonic=time.monotonic) -> None:
        self.assembler, self.adapter, self.permit, self.world = assembler, adapter, permit, world
        self._spin, self._close, self.submit_lead_s = spin, close, submit_lead_s
        self.drain_timeout_s, self.monotonic = drain_timeout_s, monotonic
        self.closed = False

    def begin(self, session_id: str, attempt_id: str) -> None:
        self.adapter.begin_attempt(session_id, attempt_id)

    def ready(self) -> bool:
        """Whether the first joint state of this session has arrived (the simulation clock is readable)."""

        return self.assembler.sim_time() is not None

    def sim_time(self):
        value = self.assembler.sim_time()
        if value is None:
            raise RuntimeError("ROLLOUT_SIM_CLOCK_UNAVAILABLE")
        return value

    def spin(self) -> None:
        self._spin()

    def observe(self):
        return self.assembler.poll()

    def submit_prefix(self, prefix: dict) -> str:
        for row in prefix["positions"]:
            bounded_positions(row)
        if self.sim_time() + self.submit_lead_s >= prefix["target_times_s"][0] - 1e-6:
            raise ValueError("PREFIX_LATE")
        return self.adapter.submit(prefix, self.permit.issue(prefix))

    def goal_pair(self):
        """Diagnostics only: the `goal_pair` record of the most recent submission (None when it sent nothing)."""

        return getattr(self.adapter, "last_pair", None)

    def goal_response_summary(self):
        """Diagnostics only: acceptance latency statistics of this attempt's goal pairs."""

        return self.adapter.goal_response_summary()

    def goal_pairs(self):
        """Diagnostics only: the goal pairs of this attempt (call after `goal_response_summary`, which refreshes them)."""

        return list(getattr(self.adapter, "pair_log", ()))

    def drain_goals(self) -> bool:
        """Wait (bounded, wall time) until every goal already sent has its outcome; True when none is left unfinished.

        A rollout goal lasts one action step (0.1 s) and the horizon falls on an observation tick, so the last goal finishes at
        the very moment the horizon is reached. A cancel that reaches the controller in that instant leaves the goal CANCELING
        for good (the controller's success is refused in that state): it never gets a result and the stop can never be proven.
        Nothing is sent after the horizon, so the goals are simply let finish before the stop."""

        deadline = self.monotonic() + self.drain_timeout_s
        while True:
            unfinished = sum(getattr(getattr(self.adapter, name, None), "unfinished_goals", lambda: 0)()
                             for name in ("arm", "gripper"))
            if unfinished == 0:
                return True
            if self.monotonic() >= deadline:
                return False
            self._spin()

    def stop(self, reason: str) -> str:
        if reason == "ROLLOUT_HORIZON":
            self.drain_goals()
        return self.adapter.stop(reason)

    def stop_confirmed(self) -> bool:
        return self.adapter.poll_stop() == "STOPPED"

    def stop_diagnostics(self) -> dict:
        """Why a stop is not confirmed: per controller port the feedback age, the largest measured speed and the goals with no
        terminal result (the three things `RosControllerPort.stopped` demands). Read-only; a port that cannot be read says so."""

        report = {}
        for name in ("arm", "gripper"):
            port = getattr(self.adapter, name, None)
            try:
                with port._lock:
                    velocity = port._velocity
                    received = port._received
                    goals = list(port._goals.values())
                    age = None if received is None else round(port.monotonic() - received, 4)
                    open_goals = [{"accepted": record["accepted"], "status": None if record["result"] is None
                                   else record["result"].status, "cancel_requested": record["cancel_requested"],
                                   "cancel_ack": record.get("cancel_ack"), "error": record.get("error"),
                                   "has_handle": record.get("handle") is not None}
                                  for record in goals if record["accepted"] is None
                                  or (record["accepted"] is True and (record["result"] is None
                                                                      or record["result"].status not in (4, 5, 6)))]
                    report[name] = {"feedback_age_s": age, "max_abs_velocity_rad_s": None if velocity is None
                                    else round(max(abs(value) for value in velocity), 6),
                                    "stop_velocity_rad_s": port.stop_velocity, "max_age_s": port.max_age,
                                    "goals": len(goals), "open_goals": open_goals[:5], "open_goal_count": len(open_goals)}
            except Exception as error:      # noqa: BLE001 - diagnostics must never turn a stop problem into a crash
                report[name] = {"unreadable": (str(error) or type(error).__name__)[:120]}
        return report

    def cup_pose(self):
        return self.world.cup_pose()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._close()


def _last_goals(adapter):
    for entry in reversed(adapter.audit):
        goals = entry.get("goals") if isinstance(entry, dict) else None
        if goals is not None:
            return goals
    return None


def build_ros_session(*, binding, config: dict, cameras, state_dim: int, image_shape, session_id: str, source_floor_s: float,
                      timing: dict, rgb_sync: dict, world_observer_factory):
    """Create the executor's nodes (AFTER the initial gate) and return the `RolloutSession`.

    `binding` is the ROS seam: `create_node(name)`, `message_types` (`Image`, `JointState`, `FollowJointTrajectory`), the QoS
    profiles, `action_client(node, type, name)`, `start_spinning(node)` (a background executor; returns a stop callable) and
    `destroy_node(node)`. `config` is the rollout config; `timing` holds the controller timing from the config and the frozen
    inputs; `rgb_sync` the frozen RGB `max_age_s` and `max_skew_s`. `world_observer_factory(node, session_id)` builds the world
    evidence observer on the same node.
    """

    from so101_demo.act.rollout_config import camera_topics_for
    from so101_demo.adapters.act.ros_execution import RosControllerPort

    topics = camera_topics_for(config, cameras)
    assembler = ObservationAssembler(cameras=cameras, state_dim=state_dim, max_age_s=rgb_sync["max_age_s"],
                                     max_skew_s=rgb_sync["max_skew_s"], image_shape=image_shape)
    assembler.reset(session_id, source_floor_s=source_floor_s)
    node = binding.create_node("act_rollout_executor")
    stop_spinning = None
    clients = []
    try:
        height, width, _channels = assembler.image_shape

        def on_image(camera, message):
            try:
                if (message.encoding, message.width, message.height, message.step) != ("rgb8", width, height, width * 3) \
                        or len(message.data) != height * width * 3:
                    assembler.note_rejected("INPUT_RGB_INVALID")
                    return
                stamp = int(message.header.stamp.sec) + int(message.header.stamp.nanosec) / 1e9
                pixels = np.frombuffer(bytes(message.data), dtype=np.uint8).reshape((height, width, 3))
                assembler.push_image(camera, stamp, pixels)
            except Exception as error:      # noqa: BLE001 - a callback never raises into the executor
                assembler.note_rejected("IMAGE_CALLBACK_FAILED: " + str(error)[:100])

        def on_joints(message):
            try:
                stamp = int(message.header.stamp.sec) + int(message.header.stamp.nanosec) / 1e9
                if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
                    assembler.note_rejected("JOINT_MAPPING_INVALID")
                    return
                assembler.push_joints(stamp, dict(zip(message.name, message.position, strict=True)))
            except Exception as error:      # noqa: BLE001
                assembler.note_rejected("JOINT_CALLBACK_FAILED: " + str(error)[:100])

        for camera, topic in topics.items():
            node.create_subscription(binding.message_types["Image"], topic,
                                     lambda message, camera=camera: on_image(camera, message), binding.image_qos)
        node.create_subscription(binding.message_types["JointState"], config["joint_state_topic"], on_joints,
                                 binding.sensor_qos)
        follow = binding.message_types["FollowJointTrajectory"]
        # an action client outlives `destroy_node` and keeps the node in the ROS graph until it is destroyed itself
        arm_client = binding.action_client(node, follow, config["controller_actions"]["arm"])
        clients.append(arm_client)
        gripper_client = binding.action_client(node, follow, config["controller_actions"]["gripper"])
        clients.append(gripper_client)
        arm = RosControllerPort(node, arm_client, ARM_JOINTS[:5], stop_velocity_rad_s=timing["stop_velocity_rad_s"],
                                max_age_s=timing["max_age_s"])
        gripper = RosControllerPort(node, gripper_client, ARM_JOINTS[5:], stop_velocity_rad_s=timing["stop_velocity_rad_s"],
                                    max_age_s=timing["max_age_s"])
        permit = JointLimitPermit()
        holder = {}
        adapter = ActExecutionAdapter(
            arm, gripper, permit_port=permit, sim_clock=lambda: holder["session"].sim_time(),
            progress=lambda: holder["session"].spin(), submit_lead_s=timing["submit_lead_s"],
            accept_timeout_s=timing["accept_timeout_s"], stop_timeout_s=timing["stop_timeout_s"],
            reference_port=ControllerReference(measured=assembler.latest_arm,
                                               last_goals=lambda: _last_goals(adapter)))
        world = WorldCupObserver(world_observer_factory(node, session_id))
        stop_spinning = binding.start_spinning(node)

        def close():
            failures = []
            for step in (stop_spinning, *(lambda client=client: binding.destroy_action_client(client) for client in clients),
                         lambda: binding.destroy_node(node)):
                try:
                    step()
                except Exception as error:      # noqa: BLE001 - every step runs; the first failure is raised after
                    failures.append(error)
            if failures:
                raise failures[0]

        session = RolloutSession(assembler=assembler, adapter=adapter, permit=permit, world=world,
                                 spin=lambda: time.sleep(0.001), close=close, submit_lead_s=timing["submit_lead_s"],
                                 drain_timeout_s=timing["stop_timeout_s"])
        holder["session"] = session
        return session
    except BaseException:
        if stop_spinning is not None:
            stop_spinning()
        for client in clients:
            binding.destroy_action_client(client)
        binding.destroy_node(node)
        raise


class RclpyBinding:
    """The real ROS seam: rclpy, imported on first use; one background executor thread per node."""

    def __init__(self) -> None:
        import rclpy
        from control_msgs.action import FollowJointTrajectory
        from rclpy.action import ActionClient
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
        from sensor_msgs.msg import Image, JointState

        self._rclpy, self._action_client, self._executor_type = rclpy, ActionClient, SingleThreadedExecutor
        self.message_types = {"Image": Image, "JointState": JointState, "FollowJointTrajectory": FollowJointTrajectory}
        self.image_qos = QoSProfile(depth=CAMERA_RING, reliability=ReliabilityPolicy.RELIABLE)
        self.sensor_qos = qos_profile_sensor_data
        # A private context: other components of the rollout process (the scene reset) initialise and shut down the DEFAULT
        # context themselves, and `rclpy.init()` on an initialised default context raises `Context.init() must only be called once`.
        from so101_demo.ros.process_init import global_init_options

        self._context = rclpy.context.Context()
        rclpy.init(context=self._context, **global_init_options())

    def create_node(self, name: str):
        return self._rclpy.create_node(name, context=self._context)

    def shutdown(self) -> None:
        if self._context.ok():
            self._context.shutdown()

    def action_client(self, node, action_type, name: str):
        return self._action_client(node, action_type, name)

    def start_spinning(self, node):
        executor = self._executor_type(context=self._context)
        executor.add_node(node)
        thread = threading.Thread(target=executor.spin, name="act-rollout-spin", daemon=True)
        thread.start()

        def stop():
            executor.shutdown()
            thread.join(timeout=5.0)
            if thread.is_alive():
                raise RuntimeError("ROLLOUT_SPIN_THREAD_STILL_RUNNING")
        return stop

    def destroy_action_client(self, client) -> None:
        client.destroy()

    def destroy_node(self, node) -> None:
        node.destroy_node()
