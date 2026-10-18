"""The Recorder's data sources, served from a bag replay (P2, cleanup step 2).

`OfflineRosSources` is the one sources object of the offline processor. It binds the same data-side objects the live Recorder used and
keeps every rule, gate and check of it:

* the source binder `data_source_binding.bind_data_sources` builds the scene_state observer and adapter, the raw physics adapter and
  the RGB/joint observation adapter around the processor's own episode;
* the world evidence observer is `MujocoWorldObserver`;
* the boundary and retention logic (verified reset, dispatch receipts, sequence end, initial and final boundaries, world sources) is
  `ros/recorder_data_side.RecorderDataSide`;
* the controller reference at `t+0.1 s` comes from the controller state topics through `ControllerReferenceObserver` and the
  same record shape the command broker returns (`collection_reference`).

What a replay does differently from a live node:

* messages arrive through `ReplayNode.deliver_due`, at their recorded receipt instants (there is no receiver thread);
* the planning-scene reads the live Recorder made over `/get_planning_scene` are the record-only process's reads, replayed from
  `/so101/raw/planning_scene_reads` at the instant each finished (the shape is the Teacher's `scene_operation` payload);
* the alignment verification runs inline (a thread would only add wall-clock races to a deterministic replay);
* there is no scene poller: the reads are visible when their message has been delivered.

The planning-scene audit of every training row. The Recorder never writes the MoveIt scene: it derives the source alignment
associations (`initial`, `attach`, `detach`) from the Teacher's own `scene_operation` events (`act/recorder_scene.py`).
"""

from __future__ import annotations

import copy
import json
import threading
import time
from collections import deque
from pathlib import Path

from ...act.collection_reference import build_collection_reference
from ...act.nonfinite import json_safe
from ...act.recorder_scene import (
    AssociationJob,
    SceneAssociationError,
    SceneAssociations,
    SceneOperationTracker,
    build_association,
    select_source,
)
from ...act.scene_operation import SceneOperationError
from ...act.synchronizer import source_age_ok_ns
from ...ros.recorder_data_side import RecorderDataSide
from .raw_recorder import SCENE_READS_TOPIC
from so101_demo.act.rig_profile import DEFAULT_RIG
from .replay import InlineExecutor, ReplayNode

_SEED_ACTIVATION_RESERVE_S = 0.05
_CONTROLLER_KINDS = ("arm", "gripper", "neck")

# controller_state is published at the controller update rate (500 Hz) with the update's sim stamp. The reader keeps
# KEEP_LAST 1000 (2 s of frames) so a slow callback cannot lose a frame, and the buffer holds at least 2 s by stamp.
STATE_QOS_DEPTH = 1000
STATE_WINDOW_S = 2.0
STATE_FRAME_CAPACITY = 2048   # at least STATE_WINDOW_S at 500 Hz (1000 frames), with margin


def controller_state_qos():
    from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

    return QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=STATE_QOS_DEPTH,
                      reliability=QoSReliabilityPolicy.RELIABLE)


class ControllerReferencePort:
    """Read-only controller reference at an instant, from the controller state topics (no lease, no RPC).

    The subscription is RELIABLE with KEEP_LAST 1000. A reader that is slower than the publisher can then never block
    the controller's realtime publisher (a KEEP_LAST writer drops, it does not wait), and the frames it does take are
    in order. Age is measured from the frame's own stamp against the node's simulation clock: the buffer holds at least
    2 s, whatever the wall-clock jitter of the callbacks.
    """

    def __init__(self, node, *, session_id, reset_epoch, window_s=STATE_WINDOW_S, monotonic=time.monotonic,
                 observer=None):
        from control_msgs.msg import JointTrajectoryControllerState

        from ...adapters.act.controller_reference_observer import ControllerReferenceObserver

        if window_s < STATE_WINDOW_S:
            raise ValueError("REFERENCE_WINDOW_TOO_SHORT")
        self.node, self.monotonic, self.window_s = node, monotonic, window_s
        self.observer = observer or ControllerReferenceObserver(max_frames=STATE_FRAME_CAPACITY)
        self.identity = (session_id, reset_epoch)
        self.floor_ns = node.get_clock().now().nanoseconds
        self.observer.reset(session_id, reset_epoch, source_floor_ns=self.floor_ns)
        self.subscriptions = [
            node.create_subscription(JointTrajectoryControllerState, f"/{kind}_controller/controller_state",
                                     lambda message, kind=kind: self.observer.accept(
                                         kind, message, received_monotonic_s=self.monotonic()),
                                     controller_state_qos())
            for kind in _CONTROLLER_KINDS]

    def recent(self, kind):
        return self.observer.recent_by_stamp(
            kind, now_sim_ns=self.node.get_clock().now().nanoseconds, window_ns=round(self.window_s * 1e9))

    def continuity_report(self):
        return self.observer.gap_report()

    def received_through_s(self):
        """The newest instant that BOTH required controllers have published and the Recorder has received (a frame at or
        after an instant proves the frame at that instant arrived, controller_state being ordered per topic), or None."""
        stamps = [self.observer.latest_stamp_ns(kind) for kind in ("arm", "gripper")]
        if any(stamp is None for stamp in stamps):
            return None
        return min(stamps) / 1e9

    def matching(self, kind, target_ns):
        return self.observer.matching_by_stamp(
            kind, now_sim_ns=self.node.get_clock().now().nanoseconds, window_ns=round(self.window_s * 1e9),
            target_ns=target_ns, tolerance_ns=1000)

    def read(self, requested_sim_time_s):
        try:
            return dict(build_collection_reference(requested_sim_time_s, self.recent, matching=self.matching),
                        accepted=True)
        except ValueError as error:
            raise RuntimeError("REFERENCE_HISTORY_UNAVAILABLE") from error

    def close(self):
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)


class OfflineRosSources:
    #: the rig whose cameras the capture needs (rig v1 unless the constructor is given another)
    rig = DEFAULT_RIG
    #: how long an association waits for its source to appear in the histories before it is INVALID
    ALIGNMENT_RETRY_S = 1.0
    #: virtual time one waiting pass of the data side costs (about one loop pass of the live Recorder)
    PROGRESS_STEP_S = 0.002

    def __init__(self, node: ReplayNode, episode, options, *, bind=None, world_observer_factory=None,
                 reference_port_factory=None, physical_provider=None, policy=None, final_normal_stop_seq=None,
                 rig=DEFAULT_RIG) -> None:
        self.node, self.episode, self.options = node, episode, options
        #: the rig whose cameras the offline capture must receive (rig v1 unless the processor names another)
        self.rig = rig
        #: the frozen Recorder policy (episode_recorder): its receiver-lag bound goes to the physics adapter
        self._policy = {} if policy is None else dict(policy)
        #: how long a source may wait for its raw chunk: the receiver-lag policy (the adapter fails the data beyond it)
        self._chunk_wait_s = float(self._policy.get("physics_receiver_lag_max_s", 0.1))
        if "physics_receiver_lag_max_s" in self._policy:
            self.ALIGNMENT_RETRY_S = max(self.ALIGNMENT_RETRY_S, self._chunk_wait_s)
        #: the Teacher publishes a `normal_stop` for every confirmed stop; the bag shows which one is the last
        self._final_normal_stop_seq = final_normal_stop_seq
        self._final_boundary_done = False
        self._scene_reads_pending: list = []
        self._scene_subscription = None
        self._planning_lock = threading.Lock()
        self._controller_lock = threading.Lock()
        self._bind, self._world_factory = bind, world_observer_factory
        self._reference_factory, self._physical_provider = reference_port_factory, physical_provider
        self._stream = self.binding = self.world = self.reference_port = self.host = None
        self._joint_subscription = None
        self._counts = {**{camera: 0 for camera in rig.camera_names}, "joint_states": 0}
        self._hazards_seen = 0
        self._lag_window_pending = False
        self._finish_started = False
        self._summary_written = False
        self.tracker = SceneOperationTracker()
        self.associations = SceneAssociations()
        self._jobs: list = []
        self._admissions: list = []
        self._initial_built = False
        self._start_gate: dict = {}   # why try_start did not start the capture, by cause
        self._executor = None
        self._base_geometry = None
        self._planning_calls = deque(maxlen=64)
        self._controller_history = deque(maxlen=512)
        self._joint_generation = 0

    # ---- construction ---------------------------------------------------------------------------------------------

    def prepare(self, engine) -> None:
        from std_msgs.msg import String

        from ...adapters.act.ros_teacher_event_stream import RosTeacherEventSubscription

        episode, options, node = self.episode, self.options, self.node
        session_id, reset_epoch = options.session_id, options.expected_reset_epoch
        # the Teacher events first: the engine sees seq 1
        self._stream = RosTeacherEventSubscription(node, engine.on_event_text)
        self.binding = self._bind_sources(engine)
        self.world = (self._world_factory or self._default_world_factory)(node, session_id)
        self.reference_port = (self._reference_factory or self._default_reference_factory)(
            node, session_id=session_id, reset_epoch=reset_epoch)
        self._subscribe_joint_states()
        self._count_acquisitions()
        self._lag_window_pending = False
        if getattr(node, "start_at_stamp_ns", None) is not None:
            suspend = getattr(getattr(self.binding, "physics_adapter", None), "suspend_lag_check", None)
            if suspend is not None:
                # the bag begins before the window: the simulation is paused there (live, the adapter only exists from the start)
                suspend()
                self._lag_window_pending = True
        self.host = RecorderDataSide(
            node=node, session_id=session_id, reset_epoch=reset_epoch, episode=episode, binding=self.binding,
            world_observer=self.world, execution_root=self._execution_root(), progress=lambda: self.pump(engine),
            normal_stop_proof=lambda: {}, invalid_latched=lambda: bool(getattr(engine, "replay_failed", engine.invalid)),
            drain_collection=lambda: self.collect(engine),   # the final boundary drains the original camera tail
            native_source_wait_s=self._chunk_wait_s)
        # the alignment verification runs on the caller's thread
        self._executor = InlineExecutor()
        provider = self._physical_provider or self._build_provider()
        self._provider = provider
        episode.bind_physical_provider(provider)
        # The data side waits in loops that call `progress` (the first world after the stop, the camera tail). Live, each pass costs
        # real time and the loop ends at its deadline; on a virtual clock a pass that costs nothing would never reach the deadline.
        self.host._progress_callable = lambda: (self.node.clock.advance(self.PROGRESS_STEP_S), self.pump(engine))[1]
        self._scene_subscription = self.node.create_subscription(String, SCENE_READS_TOPIC, self._on_scene_read, 1000)

    def _execution_root(self) -> Path:
        inputs = self.episode.capture.audit.inputs
        return Path(self.episode.frozen_inputs_manifest).parent / inputs["execution_snapshot"]["path"]


    def _bind_sources(self, engine):
        from ...ros import data_source_binding

        binder = self._bind or data_source_binding.bind_data_sources
        snapshot = self.episode.execution_inputs
        model_path = self._execution_root() / snapshot["scene_path"]
        return binder(self.node, session_id=self.options.session_id, reset_epoch=self.options.expected_reset_epoch,
                      model_path=model_path, max_age_s=.1, expected_model=snapshot, episode_recorder=self.episode,
                      physics_lag_max_s=self._policy.get("physics_receiver_lag_max_s"))

    def _default_world_factory(self, node, session_id):
        from ...backends.mujoco.observer import MujocoWorldObserver

        # A gap is reported here and judged where the data is: the retained records must be gap-free
        return MujocoWorldObserver(node, session_id, max_age_s=0.5, subscription_depth=256, history_capacity=2048,
                                   on_sequence_gap=self._world_gap_is_judged_on_the_records)

    @staticmethod
    def _world_gap_is_judged_on_the_records(previous, current) -> None:
        """A sequence gap is not a sticky hazard of the observer: the retained records are checked for gaps where they are read."""

    def _default_reference_factory(self, node, *, session_id, reset_epoch):
        return ControllerReferencePort(node, session_id=session_id, reset_epoch=reset_epoch)

    def _subscribe_joint_states(self) -> None:
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import JointState

        self._joint_subscription = self.node.create_subscription(JointState, "/joint_states", self._on_joint_state,
                                                                  qos_profile_sensor_data)

    def _on_joint_state(self, message) -> None:
        """Count the message and keep the original measured state the rows join (same record the Teacher child kept)."""
        self._counts["joint_states"] += 1
        try:
            from ...act.joints import ACT_JOINTS

            if len(message.name) != len(message.position):
                return
            positions = {name: float(value) for name, value in zip(message.name, message.position, strict=True)}
            stamp = getattr(getattr(message, "header", None), "stamp", None)
            if not all(name in positions for name in ACT_JOINTS) or stamp is None:
                return
            from rosidl_runtime_py.convert import message_to_ordereddict

            record = {
                "source_stamp_ns": int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec),
                "positions": copy.deepcopy(positions), "received_monotonic_s": time.monotonic(),
                # NaN/inf (the broadcaster's missing effort interface) are tagged, not dropped: canonical JSON is strict
                "original_message": json_safe(message_to_ordereddict(message))}
            with self._controller_lock:
                self._joint_generation += 1
                record["generation"] = self._joint_generation
                self._controller_history.append(record)
        except Exception:
            pass   # an unusable joint message is simply not a row source; its absence surfaces as an unready row

    def _controller_source_at(self, at_s):
        at_ns = round(at_s * 1e9)
        with self._controller_lock:
            found = next((record for record in reversed(self._controller_history)
                          if 0 <= at_ns - record["source_stamp_ns"] <= 100_000_000), None)
        return None if found is None else copy.deepcopy(found)

    def _lifecycle_source_at(self, at_s):
        record = self._lifecycle
        return copy.deepcopy({key: record[key] for key in ("phase", "release_epoch", "release_time_s")}) \
            if record["sim_time_ns"] <= round(at_s * 1e9) else None

    def _count_acquisitions(self) -> None:
        """Count RGB frames as the capture takes them, so a missing camera is named at the end."""
        capture = self.episode.capture
        original = capture.on_acquisition

        def counted(frame, pixels):
            result = original(frame, pixels)
            self._counts[frame.camera] = self._counts.get(frame.camera, 0) + 1
            return result

        capture.on_acquisition = counted

    # ---- physical audit provider and the Teacher-derived scene associations --------------------------------------

    def _build_provider(self):
        from ...act.live_physical_audit import LivePhysicalAuditProvider

        self._lifecycle = {"sim_time_ns": self.node.get_clock().now().nanoseconds, "phase": "PREPARE",
                           "release_epoch": self.episode.identity["release_epoch"], "release_time_s": None}
        audit = self.episode.capture.audit
        return LivePhysicalAuditProvider(
            identity=self.episode.identity, inputs=audit.inputs, scene_association_source=self._association_at,
            physics_source=self.binding.physics_adapter.source_at, planning_source=self._planning_source_at,
            controller_source=self._controller_source_at, lifecycle_source=self._lifecycle_source_at,
            physics_awaiting=self._physics_awaiting, planning_next_source=self._planning_next_source_at,
            concurrent_apply_source=self._concurrent_apply_for)

    def _physics_awaiting(self, at_s):
        """The newest physics sample received is older than this grid instant: its chunk is in flight."""
        newest = self.binding.physics_adapter.latest_sample_time_s()
        return newest is not None and newest < at_s

    def _unbuilt_job_sim_times(self):
        """Sim times of the anchors of the association jobs issued and not built yet."""
        times = []
        for job in self._jobs:
            anchor = job.query if job.apply is None else job.apply
            clock = anchor.get("response_ros_clock")
            if clock is not None:
                times.append(clock["sim_time_ns"])
        return times

    def _association_at(self, at_s):
        return self.associations.at(at_s, self.tracker, self._unbuilt_job_sim_times())

    #: how long after a read the replay waits for the Teacher event of an apply that may have been concurrent with it (an apply
    #: takes 20 ms and its event follows within a few ms; this stays under the 100 ms age rule so that a true mismatch is still reported as such)
    APPLY_SETTLE_NS = 50_000_000

    def _concurrent_apply_for(self, read):
        """(admitted association documents whose apply overlapped `read`, True when an overlapping apply has no admitted
        association yet): a read concurrent with an apply may show the scene before or after it."""
        from ...act.scene_association import association_anchor, read_follows_apply_before_readback, read_overlaps_apply

        # the Teacher's own applies, in the tracker (the planning calls hold the Recorder's reads only)
        overlapping = {call["call_id"] for call in list(self.tracker.records)
                       if call["service"] == "/apply_planning_scene" and call.get("request_ros_clock") is not None
                       and call.get("response_ros_clock") is not None
                       and isinstance(call.get("response"), dict) and call["response"].get("success") is True
                       and read_overlaps_apply(read, call)}
        documents = [bound["association"] for bound in self.associations.history
                     if association_anchor(bound["association"])["call_id"] in overlapping]
        known = {association_anchor(document)["call_id"] for document in documents}
        # An apply that finished before the read but whose own read-back began after it: its association is not governing yet while
        # the scene already is its result. Offered with the overlapping ones; the rule accepts only exactly that geometry.
        documents += [bound["association"] for bound in self.associations.history
                      if association_anchor(bound["association"])["call_id"] not in overlapping
                      and read_follows_apply_before_readback(read, bound["association"])]
        # An apply concurrent with this read is only known once its Teacher event has been replayed (the event is published when
        # the apply returns, after the read did): until the replay has moved a settle time past the read, no overlap is not yet proof.
        unseen = time.monotonic_ns() < read["response_ros_clock"]["end_monotonic_ns"] + self.APPLY_SETTLE_NS
        # An apply that already finished before the read began, whose association is not admitted yet (built or being built during
        # a live recording): the scene may already be its result while the previous association still governs, so the row waits.
        admitted = {association_anchor(bound["association"])["call_id"] for bound in self.associations.history}
        unbuilt = {call["call_id"] for call in list(self.tracker.records)
                   if call["service"] == "/apply_planning_scene" and call.get("response_ros_clock") is not None
                   and isinstance(call.get("response"), dict) and call["response"].get("success") is True
                   and call["response_ros_clock"]["end_monotonic_ns"] <= read["request_ros_clock"]["begin_monotonic_ns"]
                   and call["call_id"] not in admitted}
        return documents, bool(overlapping - known) or bool(unbuilt) or (not overlapping and unseen)

    def _planning_source_at(self, at_s):
        """The Recorder's own read-only scene query that joins the grid instant, after the governing association.

        Normally the newest read at or before the instant and at most 100 ms old (the single age rule). When there is none
        because the scene service stalled (a hole in the reads), the newest read at or before the instant is returned if it is
        BRACKETED: see `_bracket_at`.
        """
        bound = self._association_at(at_s)
        if bound is None:
            return None
        found = self._planning_reads(at_s, bound)
        if found["fresh"] is not None:
            return copy.deepcopy(found["fresh"])
        bracket = self._bracket_at(at_s, bound, found)
        if bracket is None:
            bracket = self._apply_bracket_at(at_s, bound, found)
        return None if bracket is None else copy.deepcopy(bracket[0])

    def _planning_next_source_at(self, at_s):
        """The read after the instant, only for a read the bracket admits (older than the age rule)."""
        bound = self._association_at(at_s)
        if bound is None:
            return None
        found = self._planning_reads(at_s, bound)
        if found["fresh"] is not None:
            return None
        bracket = self._bracket_at(at_s, bound, found)
        if bracket is None:
            bracket = self._apply_bracket_at(at_s, bound, found)
        return None if bracket is None else copy.deepcopy(bracket[1])

    def _planning_reads(self, at_s, bound):
        """The full reads usable after the governing association: {"fresh": newest at or before the instant within 100 ms,
        "before": newest at or before the instant, "after": first after the instant}."""
        from moveit_msgs.msg import PlanningSceneComponents

        from ...act.scene_association import association_anchor

        required = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                    | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
        anchor = association_anchor(bound["association"])
        at_ns = round(at_s * 1e9)
        with self._planning_lock:
            calls = list(self._planning_calls)
        usable = [call for call in calls
                  if (call["service"] == "/get_planning_scene" and call.get("response") is not None
                      and call.get("response_ros_clock") is not None
                      and call["request"]["components"]["components"] & required == required
                      and call["request_ros_clock"]["begin_monotonic_ns"] >= anchor["response_ros_clock"]["end_monotonic_ns"])]
        found = {"fresh": None, "before": None, "after": None}
        for call in reversed(usable):
            stamp = call["response_ros_clock"]["sim_time_ns"]
            if stamp <= at_ns:
                found["before"] = call
                if source_age_ok_ns(at_ns, stamp):
                    found["fresh"] = call
                break
        for call in usable:
            if call["response_ros_clock"]["sim_time_ns"] > at_ns:
                found["after"] = call
                break
        return found

    def _bracket_at(self, at_s, bound, found):
        """(read before, read after) when the scene is PROVEN unchanged across the hole, else None.

        Proof: both reads carry the same normalized scene geometry (the content the association compares), and no Teacher
        `/apply_planning_scene` call overlaps the interval between them (its request begins before the later read's response
        ends and its response ends after the earlier read's request began). Anything else leaves the 100 ms rule in force.
        """
        before, after = found["before"], found["after"]
        if before is None or after is None:
            return None
        from moveit_msgs.srv import GetPlanningScene

        from ...act.scene_association import canonical, decode_ros
        from ...control.planning_scene.task_scene import normalized_scene_geometry

        geometry = [canonical(normalized_scene_geometry(decode_ros(GetPlanningScene.Response, call["response"]).scene))
                    for call in (before, after)]
        if geometry[0] != geometry[1] or geometry[0] != canonical(bound["association"]["receipt"]["geometry"]):
            return None
        for call in self.tracker.records:
            if call["service"] != "/apply_planning_scene":
                continue
            if (call["request_monotonic_ns"] <= after["response_ros_clock"]["end_monotonic_ns"]
                    and (call["response_monotonic_ns"] or 0) >= before["request_ros_clock"]["begin_monotonic_ns"]):
                return None
        return before, after

    def _apply_bracket_at(self, at_s, bound, found):
        """(the Teacher's apply, the first read after it) for a row between the two, else None.

        The row has no read at or before it that follows the governing association (a read must begin after the apply's response),
        so the scene source is the apply that made the scene what the association describes. Proof: the apply succeeded; the first
        read after the row, causal after the same apply, carries the association's geometry; no other apply (successful or not) lies
        between the apply's response and that read. With any read at or before the row the read rules decide.
        """
        from moveit_msgs.srv import GetPlanningScene

        from ...act.scene_association import association_anchor, canonical, decode_ros
        from ...control.planning_scene.task_scene import normalized_scene_geometry

        document = bound["association"]
        after = found["after"]
        if document["apply"] is None or found["before"] is not None or after is None:
            return None
        anchor = association_anchor(document)
        response = anchor.get("response")
        if anchor.get("error") is not None or not isinstance(response, dict) or response.get("success") is not True:
            return None
        geometry = canonical(normalized_scene_geometry(decode_ros(GetPlanningScene.Response, after["response"]).scene))
        if geometry != canonical(document["receipt"]["geometry"]):
            return None
        for call in self.tracker.records:
            if call["service"] != "/apply_planning_scene" or call["call_id"] == anchor["call_id"]:
                continue
            if (call["request_monotonic_ns"] <= after["response_ros_clock"]["end_monotonic_ns"]
                    and (call["response_monotonic_ns"] or 0) >= anchor["response_monotonic_ns"]):
                return None
        return anchor, after

    # ---- planning scene reads (replayed from the bag) ---------------------------------------------------------------

    def _on_scene_read(self, message) -> None:
        self._scene_reads_pending.append(message.data)

    def _refresh_scene(self) -> None:
        """Make the reads that have been delivered visible to the row audit, in recorded order."""
        from ...act.scene_operation import scene_operation_record

        pending, self._scene_reads_pending = self._scene_reads_pending, []
        for text in pending:
            line = json.loads(text)
            record, _request, _response = scene_operation_record(line["payload"])
            with self._planning_lock:
                self._planning_calls.append(record)

    def _raw_lookup(self, step):
        adapter = self.binding.physics_adapter
        first = getattr(adapter, "first_original_durable_step", None)
        if first is not None:
            sample = first(step)   # one bounded copy, not the whole retained tail
            samples = [] if sample is None else [sample]
        else:
            samples = adapter.original_durable_steps(min_physics_step=step)[:1]
        for sample in samples:
            if sample["physics_step"] == step:
                return {"sample": sample}
        return None

    def _service_associations(self, engine) -> None:
        """Admit finished verifications, then build the associations the Teacher's operations owe (non-blocking)."""
        for item in list(self._admissions):
            future, bound, key = item
            if not future.done():
                continue
            self._admissions.remove(item)
            self.associations.settle(key)
            error = future.exception()
            if error is not None:
                raise error
            self.associations.admit(bound)
        self._offer_initial_alignment()
        if not self._jobs:
            return
        jobs, self._jobs = self._jobs, []
        failure = None
        for index, job in enumerate(jobs):
            if failure is not None:
                continue
            try:
                self._build_job(job)
            except SceneAssociationError as error:
                # a source the Teacher named, or the latest one, may still be arriving: its raw physics sample comes with its
                # 100 ms chunk, up to 100 ms after the world record (L2 rRQGirke: detach, job age 0.07 s, raw newest 44600 < 44604)
                if (str(error).startswith(("RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE", "RECORDER_SOURCE_ALIGNMENT_TEACHER_EVENT_UNAVAILABLE"))
                        and time.monotonic() - job.created_monotonic_s < self.ALIGNMENT_RETRY_S):
                    self._jobs.append(job)   # its source may still be arriving in the Recorder's own histories
                else:
                    failure = error
                    self._retain_alignment_inputs(job, error)
            except Exception as error:
                failure = error
        if failure is not None:
            raise failure

    def _offer_initial_alignment(self) -> None:
        """The initial alignment is the Recorder's OWN: its latest full read of the scene, before the Teacher's SETUP, against a
        physics source. It asserts the empty scene and depends on no Teacher event. A source that has not arrived
        yet is retried with the next, newer read; any other refusal (a scene that is not empty) is the data's verdict."""
        if self._initial_built or getattr(self, "_initial_offered", False):
            return
        from moveit_msgs.msg import PlanningSceneComponents

        required = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                    | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
        with self._planning_lock:
            calls = list(self._planning_calls)
        for call in reversed(calls):
            if (call["service"] == "/get_planning_scene" and call.get("response") is not None
                    and call.get("response_ros_clock") is not None and call.get("request_ros_clock") is not None
                    and call["request"]["components"]["components"] & required == required):
                break
        else:
            return
        if call["call_id"] == getattr(self, "_initial_last_call", None):
            return
        self._initial_last_call = call["call_id"]
        job = AssociationJob("initial", None, copy.deepcopy(call), None, time.monotonic())
        try:
            self._build_job(job)
        except SceneAssociationError as error:
            if str(error).startswith(("RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE", "RECORDER_SOURCE_ALIGNMENT_TEACHER_EVENT_UNAVAILABLE")):
                self._gate("initial_alignment_source_unavailable")
                return
            self._initial_offered = True
            self._retain_alignment_inputs(job, error)
            raise

    def _retain_alignment_inputs(self, job, error) -> None:
        """Keep what the source join saw (steps and stamps, no samples) next to the Recorder's result; never raises."""

        try:
            import json

            from ...act.recorder_scene import describe_alignment_inputs

            root = Path(self.episode.capture.recorder.root)
            anchor = job.apply if job.apply is not None else job.query
            adapter = self.binding.physics_adapter
            raw_range = adapter.retained_step_range() if hasattr(adapter, "retained_step_range") else None
            document = describe_alignment_inputs(
                world_records=self.world.retained_with_receipts(),
                scene_frames=self.binding.observer.original_frames_with_receipts(), raw_range=raw_range,
                anchor=anchor, error=error, now_monotonic_ns=time.monotonic_ns())
            document["operation"] = job.operation
            document["job_age_s"] = time.monotonic() - job.created_monotonic_s
            tmp = root / "source-alignment-failure.json.tmp"
            tmp.write_text(json.dumps(document, sort_keys=True, default=str))
            tmp.replace(root / "source-alignment-failure.json")
        except Exception:
            pass

    def _build_job(self, job) -> None:
        from ...act.scene_association import association_anchor
        from ...core.task_geometry import load_task_geometry

        if self._base_geometry is None:
            self._base_geometry = load_task_geometry(self._execution_root() / "assets/common/geometry-manifest.yaml")
        anchor = job.apply if job.apply is not None else job.query
        hint = job.source_hint or {}
        selection = select_source(
            world_records=self.world.retained_with_receipts(),
            scene_frames=self.binding.observer.original_frames_with_receipts(), raw_lookup=self._raw_lookup,
            identity=self.episode.identity, model_sha256=self.binding.model_identity["model_sha256"], anchor=anchor,
            publisher_sequence=hint.get("publisher_sequence"))
        document, raw = build_association(job, selection, base_geometry=self._base_geometry, model=self.binding.model,
                                          execution_root=self._execution_root())
        self.episode.capture.audit.append_scene_association(document)
        bound = {"association": document, "raw_steps": [copy.deepcopy(raw["sample"])]}
        key = document["association_id"]
        self.associations.pend(key, association_anchor(document)["response_ros_clock"]["sim_time_ns"])
        self._admissions.append((self._executor.submit(self._provider.admit_scene_association, bound), bound, key))
        if job.operation == "initial":
            self._initial_built = True


    def final_issues(self, engine) -> list:
        issues = []
        if self.tracker._open:
            issues.append("RECORDER_SOURCE_ALIGNMENT_READBACK_MISSING: " + ",".join(kind for kind, _, _ in self.tracker._open))
        if self._jobs:
            issues.append("RECORDER_SOURCE_ALIGNMENT_NOT_BUILT: " + ",".join(job.operation for job in self._jobs))
        if self._admissions:
            issues.append("RECORDER_SOURCE_ALIGNMENT_ADMISSION_UNFINISHED")
        return issues

    # ---- one pass ---------------------------------------------------------------------------------------------------

    def pump(self, engine) -> None:
        self.node.deliver_due()
        if self._lag_window_pending and getattr(self.node, "window_open", True):
            self._lag_window_pending = False
            self.binding.physics_adapter.resume_lag_check()
        self._refresh_scene()
        errors = self.node.take_callback_errors()
        if errors:
            # what a raising callback raises from a pump: a reason the data is invalid, the loop goes on
            raise RuntimeError("RECORDER_CALLBACK_FAILED: " + " | ".join(errors[:3]))
        binding = self.binding
        records = getattr(binding, "hazards", ())
        if len(records) > self._hazards_seen:
            fresh = [dict(item) for item in list(records)[self._hazards_seen:]]
            self._hazards_seen += len(fresh)
            for item in fresh:
                engine.latch(str(item.get("reason", "DATA_SOURCE_HAZARD")))
        self._drain_stages(engine)

    def _drain_stages(self, engine) -> None:
        """Run every drain stage on every pass: a failure in one never stops the others.

        L2 cefacd37: one world/scene join failure was raised from the pump before the associations were serviced, so the world
        cursor stood still (22 s later its record was evicted: "retention prefix lost") and the Teacher's attach and detach
        associations were never built. Each stage now reports its own failure; the first is raised after all stages ran and the
        others are latched directly, so the diagnostics stay truthful.
        """
        binding = self.binding
        errors = []

        def stage(name, operation):
            try:
                operation()
            except Exception as error:   # noqa: BLE001
                errors.append((name, error))

        stage("drain_physics", binding.drain_sources)
        if self.host._world_record_cursor is not None:
            stage("drain_world", self.host._drain_world_sources)
            if errors and errors[-1][0] == "drain_world":
                self._skip_failed_world_record()
            if self.episode.capture.started:
                stage("initial_boundary", self.host._step_data_initial_boundary)
        stage("associations", lambda: self._service_associations(engine))
        for name, error in errors[1:]:
            engine.latch(str(error) or type(error).__name__)
        if errors:
            raise errors[0][1]

    def _skip_failed_world_record(self) -> None:
        """After a world/scene join failure the data is already INVALID: step the cursor past what was retained so the same
        record is not raised again every pass until the history evicts it (observation only; never raises)."""
        try:
            retained = self.world.retained_with_receipts()
            if retained:
                self.host._world_record_cursor = max(self.host._world_record_cursor,
                                                     retained[-1].evidence.publisher_sequence)
        except Exception:   # noqa: BLE001
            pass

    def _gate(self, cause, **facts) -> None:
        """Count one pass of the capture-start gate by outcome; the first and the last time are kept (observation only)."""
        now = time.monotonic_ns()
        gate = self.__dict__.setdefault("_start_gate", {})   # tests build the sources without the constructor
        entry = gate.setdefault(cause, {"passes": 0, "first_monotonic_ns": now, "facts": {}})
        entry["passes"] += 1
        entry["last_monotonic_ns"] = now
        if facts:
            entry["facts"] = facts

    def _epoch_boundary(self, history):
        """The verified reset: the Recorder's own FIRST retained evidence of this session and epoch that still has its
        physics step, with the evidence producer's clock (the sample's sim time, the producer's monotonic interval of the step),
        not a receipt time. None while no retained world record has its raw step."""
        identity = self.episode.identity
        for received in history:
            world = received.evidence
            if (world.simulation_session_id, world.reset_epoch) != (identity["session_id"], identity["reset_epoch"]):
                continue
            raw = self._raw_lookup(world.simulation_step)
            if raw is None:
                continue
            sample = raw["sample"]
            return {
                "kind": "ACT_VERIFIED_RESET_BOUNDARY", "schema_version": 3, "session_id": identity["session_id"],
                "attempt_id": identity["attempt_id"], "reset_epoch": identity["reset_epoch"],
                "source_clock": {"sim_time_ns": round(world.simulation_time_s * 1e9),
                                 "begin_monotonic_ns": sample["clock_interval_begin_monotonic_ns"],
                                 "end_monotonic_ns": sample["clock_interval_end_monotonic_ns"]},
                "physical_source": {
                    "session_id": identity["session_id"], "reset_epoch": identity["reset_epoch"],
                    "simulation_step": world.simulation_step, "publisher_sequence": world.publisher_sequence,
                    "simulation_time_s": world.simulation_time_s, "received_wall_s": received.received_monotonic_s}}
        return None

    def start_gate_summary(self, engine) -> dict:
        return {cause: entry["passes"] for cause, entry in getattr(self, "_start_gate", {}).items()}

    def try_start(self, engine):
        """Start the capture once an RGB seed pair is available; return the start time (sim seconds) or None."""

        from ...act.native_endpoints import validate_source_clock

        if not self._initial_built:
            self._gate("initial_association_not_built")
            return None   # the capture starts once the initial association (from the Teacher's setup scene) is built
        adapter = self.binding.observation_adapter
        if adapter is None:
            raise RuntimeError("RECORDER_OBSERVATION_ADAPTER_MISSING")
        # The seed pair is the newest pre-capture pair. The world evidence the capture is retained from is the newest world
        # record AT OR BEFORE the pair's stamp (its predecessor), taken from the retained history, never the newest world record
        # of the moment: a camera frame is older than the newest world record by its own latency, so "stamp >= newest world"
        # held only in a few-millisecond window (a live run expired the seed on 12605 passes).
        with adapter._lock:
            if adapter.hazard is not None or adapter._closed:
                raise PermissionError("RECORDER_CAPTURE_START_SOURCE_LOST")
            pair = dict(adapter._pre_capture_frames)
        if set(pair) != set(self.rig.camera_names):
            self._gate("seed_unavailable")
            return None
        seed_s = max(frame.stamp_s for frame, _ in pair.values())
        oldest_s = min(frame.stamp_s for frame, _ in pair.values())   # both cameras must lie at or after the world floor
        try:
            history = self.world.retained_with_receipts()
        except Exception:
            history = ()
        latest = None
        for received in reversed(history):
            if received.evidence.simulation_time_s <= oldest_s:
                latest = received.evidence
                break
        if latest is None:
            self._gate("world_snapshot_missing" if not history else "world_history_starts_after_seed", seed_sim_s=oldest_s)
            return None   # no world evidence yet (or none old enough): not ready, nothing to refuse
        floor = latest.simulation_time_s
        episode = self.episode
        with adapter._lock:
            if adapter.hazard is not None or adapter._closed:
                raise PermissionError("RECORDER_CAPTURE_START_SOURCE_LOST")
            refusal = adapter.seed_pair_refusal(floor, reserve_s=_SEED_ACTIVATION_RESERVE_S)
            if refusal in ("INPUT_COLLECTION_SEED_UNAVAILABLE", "INPUT_COLLECTION_SEED_EXPIRED"):
                self._gate("seed_" + refusal.rsplit("_", 1)[-1].lower(), world_sim_s=floor, seed_sim_s=seed_s)
                return None
        provider = getattr(self, "_provider", None)
        if provider is not None and hasattr(provider, "ready"):
            # The first row is minted at the seed pair's own stamp, and every row source must be causal at that instant. The
            # native physics sample for it arrives with its 100 ms chunk, AFTER the frame: that source is in flight, not
            # missing, and the capture waits for it (`awaiting_arrival`, bounded by the receiver-lag policy). Any other
            # source that is not causal keeps the gate closed.
            if not provider.ready(seed_s):
                cause = getattr(provider, "unready_cause", None)
                cause = None if cause is None else cause(seed_s)
                awaiting = getattr(provider, "awaiting_arrival", None)
                if not (cause == "physics" and awaiting is not None and awaiting(seed_s)):
                    self._gate("provider_not_ready", seed_sim_s=seed_s, world_sim_s=floor, source=cause)
                    return None
                self._gate("physics_in_flight", seed_sim_s=seed_s, world_sim_s=floor)
        boundary = self._epoch_boundary(history)
        if boundary is None:
            self._gate("epoch_evidence_unavailable")
            return None
        started = []

        def activate(start_s):
            self.host.retain_epoch_boundary(episode, boundary)
            begin = time.monotonic_ns()
            stamp = self.node.get_clock().now().nanoseconds
            episode.start(start_s)
            clock = validate_source_clock(dict(sim_time_ns=stamp, begin_monotonic_ns=begin,
                                               end_monotonic_ns=time.monotonic_ns()))
            self.host._collection_capture_start_clock = clock
            episode.capture.audit.append_collection_boundary("capture_start", clock)
            started.append(start_s)

        adapter.activate_capture(min_stamp_s=floor, activate=activate)
        if len(started) != 1:
            raise PermissionError("EPISODE_CAUSAL_START_NOT_ONCE")
        self._gate("started", sim_s=started[0])
        # World sources are retained from the predecessor of the seed stamp, contiguously.
        self.host._world_record_cursor = latest.publisher_sequence - 1
        return started[0]


    def collect(self, engine) -> None:
        capture = self.episode.capture
        if not capture.active:
            return
        capture.drain()
        now_s = self.node.get_clock().now().nanoseconds / 1e9
        # Ask only for instants whose frame has arrived: the sim clock reaches an instant before the frame stamped at it
        # has been delivered on its own topic, and a reference that has not arrived yet is waited for, not refused.
        received = getattr(self.reference_port, "received_through_s", None)
        if received is not None:
            through = received()
            now_s = None if through is None else min(now_s, through)
        for when in (() if now_s is None else capture.reference_requests(now_s)):
            capture.on_reference(self.reference_port.read(when))
        capture.drain()

    # ---- Teacher events -----------------------------------------------------------------------------------------

    def on_teacher_event(self, engine, event) -> None:
        kind = event["type"]
        if kind == "scene_operation":
            try:
                self._jobs.extend(self.tracker.ingest(event["payload"]))
            except SceneOperationError as error:
                raise RuntimeError(str(error)) from error
            return
        if self.host is None:
            return
        if (kind == "normal_stop" and self._final_normal_stop_seq is not None
                and event["seq"] != self._final_normal_stop_seq):
            self.host._data_skip_normal_stop_boundary = True    # audited, not the boundary
        self.host._consume_teacher_event(self.episode, event)
        if (kind == "normal_stop" and event["seq"] == self._final_normal_stop_seq and not self._final_boundary_done
                and self.host._retained_normal_stop() is not None):
            # The final boundary is the first world record after the stop, at most 100 ms of simulation time later. The Teacher
            # takes its end observation and publishes `terminal` 0.5 s after its final stop (pilot bag), so searching for the
            # boundary only after `terminal` (the tail) can never meet that bound. The search starts when the stop is known.
            self._final_boundary_done = True
            self._end_lag_check()
            self.host._finish_native_collection(time.monotonic() + engine.policy["finish_budget_s"])

    # ---- end of the recording -------------------------------------------------------------------------------------

    def _end_lag_check(self) -> None:
        """The recording is over: the simulation may stop publishing, a growing receiver lag is no longer a defect."""
        end_lag = getattr(self.binding.physics_adapter, "end_lag_check", None)
        if end_lag is not None:
            end_lag()

    def tail_ready(self, engine) -> bool:
        """Fix the final boundaries once (bounded), then wait until the cameras reach the Teacher's end observation."""

        if not self._finish_started:
            self._finish_started = True
            if not self._final_boundary_done:
                self._end_lag_check()
                self.host._finish_native_collection(time.monotonic() + engine.policy["finish_budget_s"])
            # the event summary and the reference continuity are sealed once, after the last Teacher event (the terminal)
            self._seal_event_and_reference_facts(engine)
        if self._jobs or self._admissions:
            return False   # the associations the last Teacher scene operations owe are still being admitted
        end = engine.end_obs
        if end is None:
            return True   # the reference check names the missing end observation
        collection_end = self.episode.capture.window["collection_end_s"]
        if collection_end is None or collection_end < end["simulation_time_s"]:
            return False
        # The reference check needs the raw physics sample of the end observation's step. A raw chunk is 100 ms and its grid is not the
        # cameras': the camera grid can reach the observation while the chunk that holds it (published up to 100 ms after its last step)
        # is still to come (pilot 8d9ed9d3: end step 56421 in chunk 56401-56450, retained 56400).
        step = end.get("simulation_step")
        adapter = None if self.binding is None else self.binding.physics_adapter
        reader = getattr(adapter, "retained_step_range", None)
        if reader is None or type(step) is not int:
            return True
        retained = reader()
        return retained is not None and retained[1] >= step

    def _seal_event_and_reference_facts(self, engine) -> None:
        """The Recorder's own counts, written once before the audit seals: every accepted V2 event (so QC can prove the
        sequence whole) and the per-controller `controller_state` gap report (so QC can prove the labels continuous)."""
        if self._summary_written:
            return
        audit = self.episode.capture.audit
        audit.append_teacher_event_summary(engine.event_summary())
        audit.append_reference_continuity(self.reference_port.continuity_report())
        self._summary_written = True

    def end_time_s(self, engine) -> float:
        clock = getattr(self.host, "_collection_normal_end_clock", None)
        if clock is not None:
            return clock["sim_time_ns"] / 1e9
        return self.episode.capture.window["collection_end_s"]

    def physics_steps(self, engine) -> list:
        """Every raw physics sample of the episode, for the Teacher-reference check before the seal.

        The adapter's own history is the last 4096 samples (8.2 s): on a 100 s episode the Teacher's start step is no longer in it.
        The audit holds every chunk the capture retained; the adapter is the fallback when the audit cannot be read.
        """
        try:
            from ...act.episode_qc import _raw_physics_samples, read_verified_rows

            samples = _raw_physics_samples(read_verified_rows(Path(self.episode.capture.recorder.root) / "audit", "events.jsonl"))
            if samples:
                return samples
        except (OSError, ValueError, AttributeError, KeyError, TypeError):
            pass
        return self.binding.physics_adapter.original_durable_steps()

    def source_counts(self, engine) -> dict:
        counts = dict(self._counts)
        binding = self.binding
        adapter = binding.physics_adapter
        counts["physics"] = 0 if adapter is None else adapter.receipt_diagnostics()["chunk_count"]
        counts["scene_state"] = len(binding.observer.original_frames_with_receipts())
        counts["world"] = self.world.callback_count
        return counts

    def close(self) -> None:
        errors = []
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
        for operation in (
                *(() if self._stream is None else (self._stream.close,)),
                *(() if self.reference_port is None else (self.reference_port.close,)),
                *(() if self._joint_subscription is None else
                  (lambda: self.node.destroy_subscription(self._joint_subscription),)),
                *(() if self._scene_subscription is None else
                  (lambda: self.node.destroy_subscription(self._scene_subscription),)),
                *(() if self.binding is None else (self.binding.close,))):
            try:
                operation()
            except Exception as error:
                errors.append(error)
        if errors:
            raise errors[0]
