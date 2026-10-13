"""A formal episode audit shaped like a real Teacher episode, written through the real `EpisodeAuditWriter`. Not a test module.

Everything the decoupled Recorder retains is produced here by its real producer where one exists: the Teacher events come out of
`TeacherEventStream` (envelopes, sequence numbers, scene operations that take a number and are never retained), the normal-stop
boundary is derived from the `normal_stop` event by `normal_stop_boundary_from_event`, the world sources by
`world_source_record`, the scene alignments by `make_scene_association` over real `record_scene_service_call` records and
verified with the real scene verifiers, the queue account by the real `LosslessRecorderQueue`. The audit therefore passes the
writer's own admission and the readback's full re-verification; only the coverage predicate decides what is left.

The timeline is short (native steps of 2 ms) but has the real structure: the eighteen Teacher states, the attach inside
ATTACH_MOVEIT, the MoveIt detach before the gripper opens and a second one in SYNC_WORLD_OBJECT.

`TeacherEpisode(...)` takes the faults a test needs as plain arguments; `write(root)` returns the writer and the window to seal with.
"""

from __future__ import annotations

import copy
import dataclasses
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from act_episode_audit_support import ZERO, _lease
from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
from so101_demo.act.joints import ARM_JOINTS

SESSION, EPOCH, ATTEMPT = "alignment-session", 1, "attempt-1"
STEP_S = 0.002
#: the eighteen states a completed Teacher run goes through, spelled out here so the fixture does not borrow the audit's copy
STATES = (
    "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND", "CLOSE_GRIPPER", "WAIT_GRASP_STABLE", "MICRO_LIFT",
    "WAIT_MICRO_LIFT_STABLE", "VERIFY_PHYSICAL_GRASP", "ATTACH_MOVEIT", "LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE",
    "DETACH_MOVEIT", "OPEN_GRIPPER", "WAIT_RELEASE_SETTLE", "VALIDATE_FINAL_PLACEMENT", "SYNC_WORLD_OBJECT", "RETREAT")
_GOAL_STATES = {"PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND", "CLOSE_GRIPPER", "MICRO_LIFT", "LIFT",
                "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE", "OPEN_GRIPPER", "RETREAT"}
POLICY = {"sample_rate_hz": 10, "queue_capacity_samples": 16, "queue_high_watermark_samples": 12,
          "queue_recovery_watermark_samples": 8, "queue_high_watermark_hold_s": .2, "lossless": True}
BOUNDARY_STAGES = ("verified_reset", "capture_start", "initial_capture", "normal_stop", "final_capture")
ALIGNMENT_OPERATIONS = ("initial", "world_sync", "attach", "detach", "detach_sync")

#: first phase begins at 0.110 s; phase k begins at 0.110 + 0.006 k and finishes 4 ms later
FIRST_PHASE_NS = 110_000_000
PHASE_PERIOD_NS = 6_000_000
PHASE_LENGTH_NS = 4_000_000
STOP_NS = 220_000_000
END_OBSERVATION_NS = 240_000_000
RESET_COMPLETE_NS = 100_000_000
#: the native step an alignment is sourced from
ALIGNMENT_STEPS = {"initial": 20, "world_sync": 52, "attach": 80, "detach": 92, "detach_sync": 104}
LAST_STEP = 130
STOP_STEP = 109
END_STEP = 120


def _ns() -> int:
    return time.monotonic_ns()


def phase_bounds(index: int) -> tuple[int, int]:
    begin = FIRST_PHASE_NS + PHASE_PERIOD_NS * index
    return begin, begin + PHASE_LENGTH_NS


class _Sink:
    """The queue's recorder: it only has to accept the one bound row."""

    def append(self, *job):
        return None


class _Base:
    """The model, the cup's world state and the scene geometry every alignment and world source here is derived from."""

    def __init__(self, frozen_scene):
        import mujoco
        from so101_demo.act.scene_association import source_geometry
        from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
        from so101_demo.core.task_geometry import load_task_geometry
        from so101_mujoco_support.msg import PhysicsStepEvidence
        from rosidl_runtime_py.convert import message_to_ordereddict

        self.root, self.inputs, self.model = frozen_scene
        data = mujoco.MjData(self.model)
        mujoco.mj_resetDataKeyframe(self.model, data, mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_KEY, "task_start"))
        body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
        address = self.model.jnt_qposadr[self.model.body_jntadr[body]]
        data.qpos[address + 2] = .5
        mujoco.mj_step(self.model, data)
        w, x, y, z = data.qpos[address + 3:address + 7]
        position = tuple(map(float, data.qpos[address:address + 3]))
        independent = mujoco.MjData(self.model)
        mujoco.mj_copyData(independent, self.model, data)
        mujoco.mj_forward(self.model, independent)
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(self.model, independent, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
        self.state = ObjectState(body, "plastic_cup", position, (float(x), float(y), float(z), float(w)),
                                 tuple(map(float, velocity[3:])), tuple(map(float, velocity[:3])))
        self.world = SimulationEvidence(float(data.time), "world", 7, 1, EPOCH, SESSION, False, self.state,
                                        False, 0., 0., False, (), (), ())
        self.qpos, self.qvel = list(map(float, data.qpos)), list(map(float, data.qvel))
        self.geometry = source_geometry(load_task_geometry(self.root / "assets/common/geometry-manifest.yaml"), self.world)
        self.model_sha256 = self.inputs["execution_snapshot"]["model_identity"]["model_sha256"]
        sample = PhysicsStepEvidence(physics_step=1, model_qpos=self.qpos, model_qvel=self.qvel, reset_epoch=EPOCH,
                                     simulation_session_id=SESSION, simulation_time_s=float(data.time),
                                     clock_interval_begin_monotonic_ns=1, clock_interval_end_monotonic_ns=1)
        sample.object_pose_world.position.x, sample.object_pose_world.position.y, sample.object_pose_world.position.z = position
        sample.object_pose_world.orientation.w = float(w)
        (sample.object_pose_world.orientation.x, sample.object_pose_world.orientation.y,
         sample.object_pose_world.orientation.z) = float(x), float(y), float(z)
        (sample.object_twist_world.linear.x, sample.object_twist_world.linear.y,
         sample.object_twist_world.linear.z) = self.state.linear_velocity_world
        (sample.object_twist_world.angular.x, sample.object_twist_world.angular.y,
         sample.object_twist_world.angular.z) = self.state.angular_velocity_world
        self.sample = dict(message_to_ordereddict(sample))
        self.data = data

    def world_at(self, step):
        return dataclasses.replace(self.world, simulation_time_s=step * STEP_S, simulation_step=step,
                                   publisher_sequence=1000 + step)

    def scene_state_at(self, step, begin, end):
        return {"simulation_session_id": SESSION, "reset_epoch": EPOCH, "simulation_step": step,
                "simulation_time_s": step * STEP_S, "model_sha256": self.model_sha256, "qpos": list(self.qpos),
                "qvel": list(self.qvel), "paused": False, "clock_interval_begin_monotonic_ns": begin,
                "clock_interval_end_monotonic_ns": end}

    def raw_sample(self, step, interval_ns):
        sample = copy.deepcopy(self.sample)
        sample.update(physics_step=step, simulation_time_s=step * STEP_S,
                      clock_interval_begin_monotonic_ns=interval_ns, clock_interval_end_monotonic_ns=interval_ns)
        return sample


def _alignment(base: _Base, operation: str, step: int, samples: dict) -> dict:
    """One real scene association of `operation`, sourced from native step `step` (the raw sample must have been made before)."""

    from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene, PlanningSceneComponents
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.act.scene_association import (
        make_scene_association, source_attachment_geometry, source_geometry, source_model_data)
    from so101_demo.control.planning_scene.task_scene import (
        PRE_SETUP_EXPECTATION, _collision_object, make_plain_attach_scene, make_task_scene, record_scene_service_call,
        verify_pre_setup_scene, verify_task_scene)
    from so101_demo.core.task_geometry import Pose7

    world = base.world_at(step)
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=round(step * STEP_S * 1e9)))
    geometry = source_geometry(base.geometry, world)
    components = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                  | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
    calls = []
    apply_phase = {"world_sync": "APPLY", "attach": "DYNAMIC_ATTACH", "detach": "DYNAMIC_DETACH_SYNC",
                   "detach_sync": "DYNAMIC_DETACH_SYNC"}.get(operation)
    if operation == "initial":
        scene = make_task_scene(geometry)
        scene.is_diff = False
        scene.robot_state.attached_collision_objects = []
        verification = verify_pre_setup_scene(scene)
        expected_record = PRE_SETUP_EXPECTATION
        apply_request = None
    elif operation == "world_sync":
        scene = make_task_scene(geometry)
        scene.is_diff = False
        scene.robot_state.attached_collision_objects = []
        verification = verify_task_scene(scene, geometry, cup_world_pose_audit_only=True)
        expected_record = geometry
        apply_request = ApplyPlanningScene.Request(scene=make_task_scene(geometry))
    elif operation == "attach":
        scene = make_task_scene(geometry)
        scene.is_diff = False
        cup = geometry.object("plastic_cup")
        scene.world.collision_objects = [item for item in scene.world.collision_objects if item.id != "plastic_cup"]
        attached = AttachedCollisionObject()
        attached.link_name = "gripper"
        attached.object = _collision_object(cup, "gripper")
        attached.touch_links = ["gripper", "jaw"]
        scene.robot_state.attached_collision_objects = [attached]
        mj_data = source_model_data(base.model, world, base.scene_state_at(step, 1, 1))
        expected_record = source_attachment_geometry(geometry, base.model, mj_data)
        verification = verify_task_scene(scene, geometry, expected_cup_attachment="gripper",
            expected_cup_local_pose=Pose7.parse(expected_record["local_cup"]["pose"]["values"], "fixture.local"),
            expected_touch_links=("gripper", "jaw"), cup_local_pose_audit_only=True)
        apply_request = ApplyPlanningScene.Request(scene=make_plain_attach_scene())
    else:
        scene = make_task_scene(geometry)
        scene.is_diff = False
        scene.robot_state.attached_collision_objects = []
        verification = verify_task_scene(scene, geometry)
        expected_record = geometry
        removal = AttachedCollisionObject()
        removal.object.id = "plastic_cup"
        removal.object.operation = CollisionObject.REMOVE
        request = PlanningScene()
        request.is_diff = True
        request.robot_state.is_diff = True
        request.robot_state.attached_collision_objects = [removal]
        request.world.collision_objects = [_collision_object(geometry.object("plastic_cup"), geometry.frame_id)]
        apply_request = ApplyPlanningScene.Request(scene=request)
    assert verification.success, verification.evidence
    # the native sample, then the scene state and the calls, all taken now: the verifier bounds the gap between them
    if step not in samples:
        samples[step] = base.raw_sample(step, _ns())
    begin, end = _ns(), _ns()
    scene_state = base.scene_state_at(step, begin, end)
    received = _ns()
    if apply_request is not None:
        record_scene_service_call(request=apply_request, phase=apply_phase, service="/apply_planning_scene",
            invoke=lambda: ApplyPlanningScene.Response(success=True), records=calls, ros_clock=clock)
    query = GetPlanningScene.Request()
    query.components.components = components
    record_scene_service_call(request=query, phase="RAW_SCENE_READ" if operation == "initial" else "READ_BACK",
        service="/get_planning_scene", invoke=lambda: GetPlanningScene.Response(scene=scene), records=calls, ros_clock=clock)
    document = make_scene_association(execution_root=base.root, source=world, scene_state=scene_state,
        received_monotonic_ns=received, scene_received_monotonic_ns=received, geometry=expected_record,
        apply_call=None if apply_request is None else calls[0], query_call=calls[-1], verification=verification,
        operation="detach" if operation == "detach_sync" else operation)
    return document


class TeacherEpisode:
    """The facts of one Teacher episode, with the faults a test asks for.

    Arguments name what to leave out or change:
    * `states` / `final_status` / `terminal`: the phases that ran, how the last one finished and what the terminal claims;
    * `omit_events`: Teacher event types the Teacher never emitted;
    * `omit_boundaries`, `omit_alignments`, `omit_continuity`, `queue` ("ok", "none", "twice", "short");
    * `alignment_steps`: moves an alignment to another native step; `raw_first_step` / `raw_last_step`: the retained native range;
    * `reference`: "raw" (a complete raw group) or "projected" (a bare projection).
    """

    def __init__(self, frozen_scene, *, states=STATES, final_status="SUCCEEDED", terminal="COMPLETED",
                 omit_events=(), omit_boundaries=(), omit_alignments=(), omit_continuity=False, queue="ok",
                 alignment_steps=None, raw_first_step=1, raw_last_step=LAST_STEP, reference="raw", omit_summary=False,
                 summary_gap=False):
        self.base = _Base(frozen_scene)
        self.states, self.final_status, self.terminal = tuple(states), final_status, terminal
        self.omit_events, self.omit_boundaries = set(omit_events), set(omit_boundaries)
        self.omit_alignments, self.omit_continuity, self.queue = set(omit_alignments), omit_continuity, queue
        self.steps = dict(ALIGNMENT_STEPS, **(alignment_steps or {}))
        self.raw_first_step, self.raw_last_step, self.reference = raw_first_step, raw_last_step, reference
        self.summary = None
        self.omit_summary, self.summary_gap = omit_summary, summary_gap

    # -- the Teacher's events, through the real producer -----------------------------------------------------------

    def _teacher_documents(self):
        from so101_demo.act.teacher_event_stream import StreamIdentity, TeacherEventStream, decode_event

        published, now = [], [0]
        stream = TeacherEventStream(StreamIdentity(SESSION, EPOCH, ATTEMPT), clock_ns=lambda: now[0],
                                    publish=published.append, start=False)

        def emit(kind, sim_ns, payload):
            now[0] = sim_ns
            stream.offer(kind, payload)
            stream.pump()

        def observation(step):
            return {"frame_id": "world", "object_id": "plastic_cup", "orientation": {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0},
                    "position": [0.02, -0.28, 0.165], "publisher_sequence": 1000 + step, "reset_epoch": EPOCH,
                    "session_id": SESSION, "simulation_step": step, "simulation_time_s": step * STEP_S}

        scene_operations = 0
        for sim_ns in (50_000_000, 60_000_000):
            emit("scene_operation", sim_ns, {"phase": "APPLY"})
            scene_operations += 1
        if "reset_complete" not in self.omit_events:
            reset_step = RESET_COMPLETE_NS // 2_000_000 - 1
            emit("reset_complete", RESET_COMPLETE_NS, {
                "session_id": SESSION, "reset_epoch": EPOCH, "simulation_time_s": reset_step * STEP_S,
                "simulation_step": reset_step, "publisher_sequence": 1000 + reset_step, "received_monotonic_ns": _ns()})
        if "teacher_start_observation" not in self.omit_events:
            emit("teacher_start_observation", RESET_COMPLETE_NS, {"observation": observation(50)})
        for index, state in enumerate(self.states):
            begin, finish = phase_bounds(index)
            last = index == len(self.states) - 1
            emit("phase_begin", begin, {"state": state, "sim_time_ns": begin, "monotonic_ns": _ns(),
                                        "goal_sent": state in _GOAL_STATES, "goal_kind": "arm" if state in _GOAL_STATES else None})
            status = self.final_status if last else "SUCCEEDED"
            emit("phase_finish", finish, {"state": state, "sim_time_ns": finish, "monotonic_ns": _ns(), "status": status,
                                          "code": None if status == "SUCCEEDED" else "TEACHER_FIXTURE_FAILURE"})
        if "normal_stop" not in self.omit_events:
            stop_begin = _ns()
            emit("normal_stop", STOP_NS, {"proof": {
                "epoch": {"reset_epoch": EPOCH, "session_id": SESSION},
                "joint_positions": {name: 0.1 for name in "123456"}, "joint_velocities": {name: 0.0 for name in "123456"},
                "kind": "TEACHER_NORMAL_STOP", "publisher_sequence": 1000 + STOP_STEP, "received_wall_s": (stop_begin - 2) / 1e9,
                "scope": {"attempt_id": ATTEMPT, "reset_epoch": EPOCH, "session_id": SESSION},
                "sim_stamp_s": STOP_STEP * STEP_S, "simulation_step": STOP_STEP,
                "source_clock": {"begin_monotonic_ns": stop_begin, "end_monotonic_ns": stop_begin,
                                 "sim_time_ns": STOP_NS},
                "stop_confirmed_wall_s": (stop_begin - 1) / 1e9, "trajectory_result": "SUCCEEDED"}})
        if "teacher_end_observation" not in self.omit_events:
            emit("teacher_end_observation", END_OBSERVATION_NS, {"observation": observation(END_STEP), "problem": None})
        if "terminal" not in self.omit_events:
            done = self.terminal == "COMPLETED"
            emit("terminal", END_OBSERVATION_NS, {
                "status": "DONE" if done else "ERROR", "teacher_execution_status": self.terminal,
                "teacher_task_result": "PASS" if done else "FAIL", "failure": None if done else "TEACHER_FIXTURE_FAILURE"})
        documents = [decode_event(text) for text in published]
        types = {}
        for document in documents:
            types[document["type"]] = types.get(document["type"], 0) + 1
        self.summary = {"schema": "SO101_TEACHER_EVENT", "accepted": len(documents), "last_seq": documents[-1]["seq"],
                        "types": types}
        return [document for document in documents if document["type"] != "scene_operation"]

    # -- the writer ------------------------------------------------------------------------------------------------

    def write(self, root: Path):
        from so101_demo.act.lossless_recorder import LosslessRecorderQueue
        from so101_demo.act.native_endpoints import world_source_record
        from so101_demo.act.teacher_collection import normal_stop_boundary_from_event
        from so101_demo.core.simulation.types import ReceivedSimulationEvidence

        base = self.base
        lease = _lease(lease_issued_monotonic_s=_ns() / 1e9 - 10.0, lease_deadline_monotonic_s=_ns() / 1e9 + 1000.0)
        identity = {"session_id": SESSION, "attempt_id": ATTEMPT, "reset_epoch": EPOCH, "release_epoch": 0,
                    "scene_id": "default", "seed": 0, "mode": "formal", "lease": lease}
        scope = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "formal", "scene_id": "default", "seed": 0,
                 "inputs_sha256": base.inputs["inputs_sha256"]}
        documents = self._teacher_documents()
        Path(root).parent.mkdir(parents=True, exist_ok=True)
        writer = EpisodeAuditWriter(root, scope, identity, base.inputs)
        max_samples = base.inputs["execution_snapshot"]["physics_chunks"]["max_samples"]

        # the native steps, in order, with the alignments made at their step
        wanted = {operation: step for operation, step in self.steps.items() if operation not in self.omit_alignments}
        alignments = {}
        samples, world_sources = {}, {}
        for step in range(1, LAST_STEP + 1):
            if step not in wanted.values():
                samples[step] = base.raw_sample(step, _ns())
            for operation, aligned in wanted.items():
                if aligned == step:
                    alignments[operation] = _alignment(base, operation, step, samples)
            if step >= 50 and step % 5 == 0 and step <= 115:
                scene_clock = _ns()
                received = _ns()
                world_sources[step] = world_source_record(
                    ReceivedSimulationEvidence(base.world_at(step), received / 1e9),
                    (base.scene_state_at(step, scene_clock, scene_clock), received / 1e9), execution_root=base.root)
        # one sequence of world sources: consecutive publisher sequences, as the validator requires
        ordered = sorted(world_sources)
        for index, step in enumerate(ordered):
            world_sources[step]["physics"]["publisher_sequence"] = 2000 + index

        minter = AcquisitionMinter()
        frames = {}
        for camera in ("head", "wrist"):
            for stamp in (0.1, 0.2, 0.3):
                frame = minter.mint(camera, session_id=SESSION, reset_epoch=EPOCH, stamp_s=stamp,
                                    received_monotonic_ns=int(stamp * 1e9) + 1, pixels=ZERO)
                writer.append_acquisition(frame)
                frames[(camera, stamp)] = frame
        reference = {"reference_time_s": 0.2, "source": "CONTROLLER_REFERENCE", "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
                     "accepted": True}
        if self.reference == "raw":
            reference.update(joint_names=list(ARM_JOINTS), sim_stamp_ns=200_000_000,
                             received_monotonic_ns=200_000_001, velocities=[0.0] * 6)
        writer.append_source("references", reference)

        for start in range(self.raw_first_step, self.raw_last_step + 1, max_samples):
            chunk_steps = [step for step in range(start, min(start + max_samples, self.raw_last_step + 1))]
            writer.append_raw_physics({"schema_version": 1, "received_monotonic_ns": _ns(), "chunk": {
                "chunk_sequence": (start - self.raw_first_step) // max_samples + 1, "simulation_session_id": SESSION,
                "reset_epoch": EPOCH, "first_physics_step": chunk_steps[0], "last_physics_step": chunk_steps[-1],
                "first_simulation_time_s": chunk_steps[0] * STEP_S, "last_simulation_time_s": chunk_steps[-1] * STEP_S,
                "failed_publish_attempts": 0, "handoff_monotonic_ns": 0, "publish_monotonic_ns": 0,
                "publish_deferrals_total": 0, "evidence_loss": False, "samples": [samples[step] for step in chunk_steps]}})
        for step in ordered:
            writer.append_world_source(world_sources[step])

        def boundary_clock(sim_ns):
            now = _ns()
            return {"sim_time_ns": sim_ns, "begin_monotonic_ns": now, "end_monotonic_ns": now}

        boundaries = {}
        reset_clock = boundary_clock(20_000_000)
        boundaries["verified_reset"] = {
            "attempt_id": ATTEMPT, "kind": "ACT_VERIFIED_RESET_BOUNDARY", "reset_epoch": EPOCH, "schema_version": 3,
            "session_id": SESSION, "source_clock": reset_clock,
            "physical_source": {"publisher_sequence": 1010, "received_wall_s": reset_clock["end_monotonic_ns"] / 1e9 + 0.001,
                                "reset_epoch": EPOCH, "session_id": SESSION, "simulation_step": 10, "simulation_time_s": 0.02}}
        boundaries["capture_start"] = boundary_clock(80_000_000)
        first_world, last_world = world_sources.get(50), world_sources.get(115)
        if first_world is not None:
            boundaries["initial_capture"] = {"source_clock": boundary_clock(102_000_000),
                                             "world_source": first_world}
        if last_world is not None:
            boundaries["final_capture"] = {"source_clock": boundary_clock(232_000_000), "world_source": last_world}

        def put(stage):
            if stage in self.omit_boundaries or stage not in boundaries:
                return
            writer.append_collection_boundary(stage, boundaries[stage])

        for stage in ("verified_reset", "capture_start", "initial_capture"):
            put(stage)

        # the Teacher's events and the alignments in simulation-time order, as the Recorder retains them
        timeline = [(document["sim_time_ns"], 1, index, "event", document) for index, document in enumerate(documents)]
        for operation, document in alignments.items():
            timeline.append((round(document["source"]["physics"]["simulation_time_s"] * 1e9), 0, 0, "alignment", document))
        for _time, _rank, _index, kind, document in sorted(timeline, key=lambda item: item[:3]):
            if kind == "alignment":
                writer.append_scene_association(document)
                continue
            writer.append_teacher_event(document)
            if document["type"] == "normal_stop":
                boundaries["normal_stop"] = normal_stop_boundary_from_event(document)
                put("normal_stop")
        put("final_capture")
        if not self.omit_summary:
            writer.append_teacher_event_summary(dict(self.summary, accepted=self.summary["accepted"] + int(self.summary_gap)))
        if not self.omit_continuity:
            writer.append_reference_continuity({
                "schema_version": 2, "period_ns": 2_000_000, "session_id": SESSION, "reset_epoch": EPOCH,
                "kinds": {kind: {"frames": 100, "gaps": 0, "steps": []} for kind in ("arm", "gripper", "neck")}})
        queue = LosslessRecorderQueue(_Sink(), policy=POLICY)
        accepted = {"ok": 1, "none": 0, "twice": 1, "many": 2}[self.queue]
        for _ in range(accepted):
            queue.append({}, (), {})
        queue.flush()
        queue.close()
        if self.queue != "none":
            snapshot = queue.snapshot()
            writer.append_recorder_queue(snapshot, sim_time_s=0.3)
            if self.queue == "twice":
                writer.append_recorder_queue(snapshot, sim_time_s=0.3)
        writer.bind_row(0, 0.1, frames[("head", 0.1)].acquisition_id, frames[("wrist", 0.1)].acquisition_id, 1)
        window = {"source_schedule": {"head": [0.1, 0.2, 0.3], "wrist": [0.1, 0.2, 0.3]},
                  "streams_required": ["head", "wrist"], "cadence_s": 0.1, "permitted_gaps_s": [],
                  "collection_start_s": 0.1, "collection_end_s": 0.3, "first_command_s": FIRST_PHASE_NS / 1e9,
                  "physics_end_s": STOP_NS / 1e9, "label_cutoff_s": 0.1, "outcome": "complete"}
        return writer, window
