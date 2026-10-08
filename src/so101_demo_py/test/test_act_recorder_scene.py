"""source alignment associations derived by the Recorder from the Teacher's own scene operations (Phase A4b).

The Teacher publishes each real Apply/GetPlanningScene call as a `scene_operation` event. These tests build such events
from real ROS messages and the frozen-model fixture of the source alignment suite, send them through the real stream encoding, and check
that the Recorder's associations verify with the QC readback (`verify_scene_association`), record pose deltas instead of
requiring equality where nothing wrote the pose, and are INVALID for every defect named in the design: a missing
operation, a sequence gap, a CDR digest mismatch, an over-size payload, a timing join outside the 100 ms window, a foreign
session or a scene whose membership is wrong. Nothing here writes a planning scene.
"""

import copy
import json
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act import recorder_scene, scene_operation
from so101_demo.act.recorder_scene import (AssociationJob, SceneAssociationError, SceneAssociations,
                                           SceneOperationTracker, build_association, select_source)
from so101_demo.act.scene_association import (association_anchor, claim_scene_records, validate_scene_association,
                                              verify_scene_association)
from so101_demo.act.scene_operation import (MAX_CDR_BYTES, SceneOperationError, scene_operation_payload,
                                            scene_operation_record)
from so101_demo.act.teacher_event_stream import StreamIdentity, TeacherEventStream, decode_event
from test_act_scene_association import association, frozen_scene  # noqa: F401  (pytest fixture)
from test_act_scene_attachment_association import _restamp_clocks, alignment_geometry_attached_scene

IDENTITY = {"session_id": "alignment-session", "reset_epoch": 1}
STREAM_IDENTITY = StreamIdentity("alignment-session", 1, "alignment-attempt")


def full_read_request():
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene

    request = GetPlanningScene.Request()
    request.components.components = (PlanningSceneComponents.WORLD_OBJECT_NAMES
                                     | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                                     | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
                                     | PlanningSceneComponents.OBJECT_COLORS)
    return request


class Context:
    """One physics source and every scene the Teacher's operations can leave, built before any clock is stamped."""

    def __init__(self, frozen_scene):
        from so101_demo.act.scene_association import _world, source_attachment_geometry, source_geometry
        from so101_demo.core.simulation.types import ReceivedSimulationEvidence
        from so101_demo.core.task_geometry import load_task_geometry

        document, raw = association(frozen_scene)
        self.root, self.inputs, self.model = frozen_scene
        self.world = _world(document["source"]["physics"])
        self.scene_state = copy.deepcopy(document["source"]["scene_state"])
        self.raw = copy.deepcopy(raw[0])
        self.received = ReceivedSimulationEvidence(self.world, 0.0)
        self.base = load_task_geometry(self.root / "assets/common/geometry-manifest.yaml")
        self.expected_world = source_geometry(self.base, self.world)
        import mujoco
        data = mujoco.MjData(self.model)
        data.qpos[:], data.qvel[:] = self.scene_state["qpos"], self.scene_state["qvel"]
        mujoco.mj_forward(self.model, data)
        self.attachment = source_attachment_geometry(self.expected_world, self.model, data)
        self.sim_ns = round(self.world.simulation_time_s * 1e9)
        self.offset_ns = 0
        self.clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=self.sim_ns + self.offset_ns))
        self.receipt_s = 0.0

    def stamp(self):
        """Restamp the source clocks to now (the source alignment timing join is 100 ms); the calls must follow immediately."""
        self.receipt_s = _restamp_clocks(self.scene_state, self.raw, received=(self.received,))

    # ---- scenes ----
    def world_scene(self, shift_m=0.0):
        from so101_demo.application.dynamic_scene_sync import geometry_with_cup_pose
        from so101_demo.control.planning_scene.task_scene import make_task_scene
        from so101_demo.core.task_geometry import Pose7

        geometry = self.expected_world
        if shift_m:
            values = list(self.expected_world.object("plastic_cup").pose.values)
            values[0] += shift_m
            geometry = geometry_with_cup_pose(self.expected_world, Pose7.parse(values, "fixture.shifted"))
        scene = make_task_scene(geometry)
        scene.is_diff = False
        scene.robot_state.attached_collision_objects = []
        return scene

    def attached_scene(self, shift_m=0.0):
        from so101_demo.control.planning_scene.task_scene import make_task_scene

        attachment = copy.deepcopy(self.attachment)
        attachment["local_cup"]["pose"]["values"][0] += shift_m
        scene = make_task_scene(self.expected_world)
        scene.is_diff = False
        scene.world.collision_objects = [item for item in scene.world.collision_objects if item.id != "plastic_cup"]
        scene.robot_state.attached_collision_objects = copy.deepcopy(
            alignment_geometry_attached_scene(attachment).robot_state.attached_collision_objects)
        return scene

    def detach_request(self):
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene
        from moveit_msgs.srv import ApplyPlanningScene
        from so101_demo.control.planning_scene.task_scene import _collision_object

        remove = AttachedCollisionObject()
        remove.object.id = "plastic_cup"
        remove.object.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [remove]
        scene.world.collision_objects = [_collision_object(self.expected_world.object("plastic_cup"),
                                                           self.expected_world.frame_id)]
        return ApplyPlanningScene.Request(scene=scene)

    def source_hint(self):
        return {"simulation_step": self.world.simulation_step, "publisher_sequence": self.world.publisher_sequence,
                "simulation_time_s": self.world.simulation_time_s}


def over_dds(message):
    """What a service response looks like once it crossed DDS: serialized and deserialized (float32 fields rounded)."""
    from rclpy.serialization import deserialize_message, serialize_message

    return deserialize_message(serialize_message(message), type(message))


class Teacher:
    """Makes real call records and publishes them as the Teacher does, through the real stream encoding."""

    def __init__(self, ctx):
        self.ctx, self.records, self.texts = ctx, [], []
        self.published = []
        self.stream = TeacherEventStream(STREAM_IDENTITY, clock_ns=lambda: ctx.sim_ns + ctx.offset_ns,
                                         publish=self.published.append, start=False)

    def call(self, request, response, *, phase, service, state=None, source=None, tamper=None):
        from so101_demo.control.planning_scene.task_scene import record_scene_service_call

        hook = scene_operation.make_scene_operation_hook(self.stream, state=lambda: state, source=lambda: source)
        response = over_dds(response)
        record_scene_service_call(request=request, phase=phase, service=service, invoke=lambda: response,
                                  records=self.records, ros_clock=self.ctx.clock, on_record=hook)
        self.stream.pump()
        payload = decode_event(self.published[-1])["payload"]
        if tamper is not None:
            tamper(payload)
        return payload

    def setup(self, shift_m=0.003, **kwargs):
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
        from so101_demo.control.planning_scene.task_scene import make_task_scene

        applied = self.call(ApplyPlanningScene.Request(scene=make_task_scene(self.ctx.expected_world)),
                            ApplyPlanningScene.Response(success=True), phase="APPLY",
                            service="/apply_planning_scene", state="SETUP")
        read = self.call(full_read_request(), GetPlanningScene.Response(scene=self.ctx.world_scene(shift_m)),
                         phase="READ_BACK", service="/get_planning_scene", state="SETUP", **kwargs)
        return applied, read

    def attach(self, shift_m=0.004, scene=None, **kwargs):
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
        from so101_demo.control.planning_scene.task_scene import make_plain_attach_scene

        applied = self.call(ApplyPlanningScene.Request(scene=make_plain_attach_scene()),
                            ApplyPlanningScene.Response(success=True), phase="DYNAMIC_ATTACH",
                            service="/apply_planning_scene", state="ATTACH_MOVEIT")
        read = self.call(full_read_request(), GetPlanningScene.Response(
            scene=self.ctx.attached_scene(shift_m) if scene is None else scene),
            phase="DYNAMIC_SCENE_READBACK", service="/get_planning_scene", state="ATTACH_MOVEIT", **kwargs)
        return applied, read

    def detach(self, state="DETACH_MOVEIT", scene=None, **kwargs):
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

        applied = self.call(self.ctx.detach_request(), ApplyPlanningScene.Response(success=True),
                            phase="DYNAMIC_DETACH_SYNC", service="/apply_planning_scene", state=state,
                            source=self.ctx.source_hint())
        read = self.call(full_read_request(), GetPlanningScene.Response(
            scene=self.ctx.world_scene() if scene is None else scene),
            phase="DYNAMIC_SCENE_READBACK", service="/get_planning_scene", state=state, **kwargs)
        return applied, read


@pytest.fixture
def ctx(frozen_scene):
    return Context(frozen_scene)


def jobs_of(tracker, payloads):
    jobs = []
    for payload in payloads:
        jobs.extend(tracker.ingest(payload))
    return jobs


def associate(ctx, job):
    hint = job.source_hint or {}
    selection = select_source(
        world_records=[ctx.received], scene_frames=[(ctx.scene_state, ctx.receipt_s)],
        raw_lookup=lambda step: {"sample": ctx.raw} if step == ctx.world.simulation_step else None,
        identity=IDENTITY, model_sha256=ctx.scene_state["model_sha256"],
        anchor=job.apply if job.apply is not None else job.query, publisher_sequence=hint.get("publisher_sequence"))
    return build_association(job, selection, base_geometry=ctx.base, model=ctx.model, execution_root=ctx.root)


def verified(ctx, document, raw):
    return verify_scene_association(document, inputs=ctx.inputs, identity=IDENTITY, raw_steps=[raw["sample"]])


# ---- the Teacher's scene operations as events ---------------------------------------------------------------

def test_a_scene_operation_event_carries_cdr_digests_clocks_outcome_and_rebuilds_the_exact_record(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    applied, read = teacher.attach()
    assert set(applied) == {"operation", "state", "call_id", "phase", "service", "schema_version", "request_cdr_base64",
                            "request_cdr_sha256", "response_cdr_base64", "response_cdr_sha256", "oversize",
                            "request_ros_clock", "response_ros_clock", "request_monotonic_ns",
                            "response_monotonic_ns", "success", "error", "source"}
    assert applied["operation"] == "attach" and applied["success"] is True and applied["oversize"] is False
    assert read["operation"] == "readback" and read["service"] == "/get_planning_scene"
    for payload, record in zip((applied, read), teacher.records):
        rebuilt, request, response = scene_operation_record(payload)
        assert json.dumps(rebuilt, sort_keys=True) == json.dumps(record, sort_keys=True)
        assert rebuilt["request_ros_clock"]["sim_time_ns"] == ctx.sim_ns
    assert decode_event(teacher.published[0])["type"] == "scene_operation"


def test_operation_kinds_follow_the_teachers_scene_states(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    assert teacher.detach(state="DETACH_MOVEIT")[0]["operation"] == "detach"
    assert teacher.detach(state="SYNC_WORLD_OBJECT")[0]["operation"] == "sync_world_object"
    assert teacher.setup()[0]["operation"] == "apply" and teacher.setup()[1]["operation"] == "readback"
    assert scene_operation.operation_kind("DYNAMIC_ACM_APPLY", "DESCEND") == "acm_apply"
    assert scene_operation.operation_kind("DYNAMIC_ACM_READBACK", None) == "acm_readback"


def test_a_failed_teacher_call_is_published_with_its_error_and_never_raises(ctx):
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.control.planning_scene.task_scene import make_plain_attach_scene, record_scene_service_call

    ctx.stamp()
    teacher = Teacher(ctx)
    hook = scene_operation.make_scene_operation_hook(teacher.stream, state=lambda: "ATTACH_MOVEIT")

    def refuse():
        raise RuntimeError("DYNAMIC_ATTACH_TIMEOUT")

    with pytest.raises(RuntimeError, match="DYNAMIC_ATTACH_TIMEOUT"):
        record_scene_service_call(request=ApplyPlanningScene.Request(scene=make_plain_attach_scene()),
                                  phase="DYNAMIC_ATTACH", service="/apply_planning_scene", invoke=refuse,
                                  records=teacher.records, ros_clock=ctx.clock, on_record=hook)
    teacher.stream.pump()
    payload = decode_event(teacher.published[-1])["payload"]
    assert payload["success"] is False and payload["error"] == "DYNAMIC_ATTACH_TIMEOUT"
    assert payload["response_cdr_base64"] is None and payload["response_cdr_sha256"] is None


def test_the_publication_hook_never_changes_the_call_even_when_the_hook_or_the_stream_raises(ctx):
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.control.planning_scene.task_scene import make_plain_attach_scene, record_scene_service_call

    ctx.stamp()
    records = []

    def exploding(record, request, response):
        raise RuntimeError("HOOK_BROKE")

    class BrokenStream:
        def offer(self, *args):
            raise RuntimeError("STREAM_BROKE")

    for hook in (exploding, scene_operation.make_scene_operation_hook(BrokenStream())):
        response = record_scene_service_call(
            request=ApplyPlanningScene.Request(scene=make_plain_attach_scene()), phase="DYNAMIC_ATTACH",
            service="/apply_planning_scene", invoke=lambda: ApplyPlanningScene.Response(success=True),
            records=records, ros_clock=ctx.clock, on_record=hook)
        assert response.success is True
    assert len(records) == 2


def test_an_oversize_cdr_travels_as_a_digest_marked_oversize_and_makes_the_recorder_refuse_it(ctx, monkeypatch):
    ctx.stamp()
    monkeypatch.setattr(scene_operation, "MAX_CDR_BYTES", 64)
    teacher = Teacher(ctx)
    applied, read = teacher.attach()
    assert applied["oversize"] is True and read["oversize"] is True
    assert applied["request_cdr_base64"] is None and len(applied["request_cdr_sha256"]) == 64
    assert read["response_cdr_base64"] is None and len(read["response_cdr_sha256"]) == 64
    with pytest.raises(SceneOperationError, match="SCENE_OPERATION_OVERSIZE"):
        scene_operation_record(applied)
    with pytest.raises(SceneOperationError, match="SCENE_OPERATION_OVERSIZE"):
        SceneOperationTracker().ingest(applied)
    assert MAX_CDR_BYTES == 262144 and scene_operation.MAX_CDR_BYTES == 64


@pytest.mark.parametrize("tamper,code", [
    (lambda p: p.update(response_cdr_sha256="0" * 64), "SCENE_OPERATION_CDR_DIGEST_MISMATCH"),
    (lambda p: p.update(request_cdr_sha256="f" * 64), "SCENE_OPERATION_CDR_DIGEST_MISMATCH"),
    (lambda p: p.update(response_cdr_base64="AAAA"), "SCENE_OPERATION_CDR_DIGEST_MISMATCH"),
    (lambda p: p.update(request_cdr_base64="***"), "SCENE_OPERATION_REQUEST_BASE64_INVALID"),
    (lambda p: p.update(extra=1), "SCENE_OPERATION_MALFORMED"),
    (lambda p: p.update(service="/other"), "SCENE_OPERATION_MALFORMED"),
])
def test_a_tampered_or_malformed_scene_operation_is_refused_with_a_stable_code(ctx, tamper, code):
    ctx.stamp()
    teacher = Teacher(ctx)
    teacher.attach()
    payload = decode_event(teacher.published[-1])["payload"]
    tamper(payload)
    with pytest.raises(SceneOperationError, match=code):
        scene_operation_record(payload)
    with pytest.raises(SceneOperationError, match=code):
        SceneOperationTracker().ingest(payload)


# ---- tracker: which associations the Teacher's operations owe ------------------------------------------------

def test_the_tracker_owes_one_association_per_geometry_changing_apply_and_the_setup_world_sync(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    tracker = SceneOperationTracker()
    jobs = jobs_of(tracker, teacher.setup())
    # the Teacher's SETUP writes the task scene: a world_sync alignment is owed (the initial one is the Recorder's own, CP-3425)
    assert [job.operation for job in jobs] == ["world_sync"] and jobs[0].apply is not None
    jobs = jobs_of(tracker, teacher.attach()) + jobs_of(tracker, teacher.detach()) + jobs_of(
        tracker, teacher.detach(state="SYNC_WORLD_OBJECT"))
    assert [job.operation for job in jobs] == ["attach", "detach", "detach"]
    assert jobs[1].source_hint == ctx.source_hint() and jobs[0].source_hint is None
    assert tracker.owed_apply_sim_times() == []


def test_an_apply_without_its_readback_stays_owed_and_a_later_row_must_wait(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    tracker = SceneOperationTracker()
    applied, _ = teacher.attach()
    assert jobs_of(tracker, [applied]) == []
    assert tracker.owed_apply_sim_times() == [ctx.sim_ns]
    associations = SceneAssociations()
    document, raw = (lambda job: associate(ctx, job))(jobs_of(SceneOperationTracker(), teacher.setup())[0])
    associations.admit({"association": document, "raw_steps": [raw["sample"]]})
    at_s = ctx.sim_ns / 1e9 + 0.05
    assert associations.at(at_s) is not None
    assert associations.at(at_s, tracker) is None, "an owed association holds the rows back instead of guessing"
    assert associations.at(ctx.sim_ns / 1e9 - 1.0, tracker) is None


def test_an_association_that_is_built_but_not_yet_admitted_also_holds_the_rows_back(ctx):
    associations = SceneAssociations()
    associations.pend("a1", 5_000_000_000)
    assert associations.at(5.1) is None
    associations.settle("a1")
    assert associations.at(5.1) is None  # nothing admitted yet either


def test_a_failed_teacher_apply_owes_no_association_and_acm_calls_are_ignored(ctx):
    from moveit_msgs.srv import ApplyPlanningScene

    ctx.stamp()
    teacher = Teacher(ctx)
    tracker = SceneOperationTracker()
    refused = teacher.call(ApplyPlanningScene.Request(), ApplyPlanningScene.Response(success=False),
                           phase="DYNAMIC_ATTACH", service="/apply_planning_scene", state="ATTACH_MOVEIT")
    assert refused["success"] is False and jobs_of(tracker, [refused]) == [] and len(tracker.failed) == 1
    acm = teacher.call(ApplyPlanningScene.Request(), ApplyPlanningScene.Response(success=True),
                       phase="DYNAMIC_ACM_APPLY", service="/apply_planning_scene", state="DESCEND")
    assert jobs_of(tracker, [acm]) == [] and tracker.owed_apply_sim_times() == []


# ---- associations VALID from a fixture stream -------------------------------------------------------------

def test_the_setup_world_sync_is_valid_records_the_pose_delta_and_never_refuses_on_pose(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.setup(shift_m=0.003))
    document, raw = associate(ctx, job)
    assert verified(ctx, document, raw).success
    assert document["operation"] == "world_sync" and document["apply"] is not None and document["schema_version"] == 1
    audit = document["receipt"]["verification"]["evidence"]["cup_world_pose_audit"]
    assert audit["refuses"] is False and audit["translation_delta_m"] == pytest.approx(0.003, abs=1e-9)
    assert document["receipt"]["verification"]["evidence"]["mismatches"] == []
    assert association_anchor(document) is document["apply"]["record"]
    validate_scene_association(document)
    claim_scene_records(document, {})


def test_a_large_setup_pose_delta_is_recorded_not_refused_and_equal_poses_record_zero(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.setup(shift_m=0.05))
    document, raw = associate(ctx, job)
    assert verified(ctx, document, raw).success
    assert document["receipt"]["verification"]["evidence"]["cup_world_pose_audit"]["translation_delta_m"] == \
        pytest.approx(0.05, abs=1e-9)
    ctx.stamp()
    exact, = jobs_of(SceneOperationTracker(), Teacher(ctx).setup(shift_m=0.0))
    document, raw = associate(ctx, exact)
    assert document["receipt"]["verification"]["evidence"]["cup_world_pose_audit"]["translation_delta_m"] == 0.0


def test_initial_membership_geometry_and_frame_stay_strict(ctx):
    from moveit_msgs.srv import GetPlanningScene

    def initial_job(scene):
        ctx.stamp()
        teacher = Teacher(ctx)
        applied, _ = teacher.setup()
        read = teacher.call(full_read_request(), GetPlanningScene.Response(scene=scene), phase="READ_BACK",
                            service="/get_planning_scene", state="SETUP")
        job, = jobs_of(SceneOperationTracker(), [applied, read])
        return job

    missing_table = ctx.world_scene()
    missing_table.world.collision_objects = [item for item in missing_table.world.collision_objects
                                             if item.id != "table"]
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_GEOMETRY_MISMATCH: world_membership"):
        associate(ctx, initial_job(missing_table))
    bad_frame = ctx.world_scene()
    bad_frame.world.collision_objects[2].header.frame_id = "gripper"
    with pytest.raises(SceneAssociationError, match="plastic_cup.frame"):
        associate(ctx, initial_job(bad_frame))
    wrong_size = ctx.world_scene()
    wrong_size.world.collision_objects[0].primitives[0].dimensions[0] += 0.05
    with pytest.raises(SceneAssociationError, match="primitive"):
        associate(ctx, initial_job(wrong_size))


def test_the_attach_association_is_valid_with_membership_strict_and_the_local_pose_delta_recorded(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.attach(shift_m=0.004))
    document, raw = associate(ctx, job)
    assert verified(ctx, document, raw).success
    assert document["operation"] == "attach" and document["schema_version"] == 1
    audit = document["receipt"]["verification"]["evidence"]["cup_local_pose_audit"]
    assert audit["refuses"] is False and audit["translation_delta_m"] == pytest.approx(0.004, abs=1e-9)
    assert document["apply"]["record"]["phase"] == "DYNAMIC_ATTACH"
    assert document["apply"]["record"] == teacher.records[0], "the Teacher's own apply record, not a Recorder call"


def test_an_attach_readback_without_the_cup_attached_is_invalid(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.attach(scene=ctx.world_scene()))
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_GEOMETRY_MISMATCH: .*attachment"):
        associate(ctx, job)


@pytest.mark.parametrize("state", ["DETACH_MOVEIT", "SYNC_WORLD_OBJECT"])
def test_the_detach_and_sync_associations_are_valid_with_strict_geometry_from_the_teachers_own_source(ctx, state):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.detach(state=state))
    document, raw = associate(ctx, job)
    assert verified(ctx, document, raw).success
    assert document["operation"] == "detach" and document["apply"]["record"] == teacher.records[0]


def test_a_detach_readback_with_the_cup_elsewhere_is_invalid_because_the_teacher_applied_source_geometry(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.detach(scene=ctx.world_scene(shift_m=0.01)))
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_GEOMETRY_MISMATCH: plastic_cup.pose"):
        associate(ctx, job)


# ---- INVALID: timing join, causality, identity ----------------------------------------------------------------

def test_a_timing_join_outside_the_100_ms_window_finds_no_source_and_a_named_detach_source_refuses_by_name(ctx):
    ctx.stamp()
    ctx.offset_ns = 150_000_000       # the Teacher's call happened 150 ms of simulation time after the source
    teacher = Teacher(ctx)
    attach, = jobs_of(SceneOperationTracker(), teacher.attach())
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE"):
        associate(ctx, attach)
    detach, = jobs_of(SceneOperationTracker(), teacher.detach())
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_SOURCE_OUTSIDE_TIMING_WINDOW"):
        associate(ctx, detach)


def test_a_source_received_after_the_call_is_not_causal_for_it(ctx):
    ctx.stamp()
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.attach())
    object.__setattr__(ctx.received, "received_monotonic_s", time.monotonic() + 1.0)
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE"):
        associate(ctx, job)


def test_the_monotonic_clock_window_is_also_a_hundred_milliseconds(ctx):
    ctx.stamp()
    ctx.scene_state["clock_interval_begin_monotonic_ns"] -= 200_000_000
    ctx.scene_state["clock_interval_end_monotonic_ns"] -= 200_000_000
    ctx.raw["clock_interval_begin_monotonic_ns"] -= 200_000_000
    ctx.raw["clock_interval_end_monotonic_ns"] -= 200_000_000
    teacher = Teacher(ctx)
    job, = jobs_of(SceneOperationTracker(), teacher.attach())
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE"):
        associate(ctx, job)


def test_a_foreign_session_or_epoch_source_is_refused_never_joined(ctx):
    ctx.stamp()
    job, = jobs_of(SceneOperationTracker(), Teacher(ctx).attach())
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_SOURCE_SCOPE_INVALID"):
        select_source(world_records=[ctx.received], scene_frames=[(ctx.scene_state, ctx.receipt_s)],
                      raw_lookup=lambda step: {"sample": ctx.raw}, identity={"session_id": "other", "reset_epoch": 1},
                      model_sha256=ctx.scene_state["model_sha256"], anchor=job.apply)


def test_a_source_whose_native_sample_or_scene_frame_disagrees_is_refused_not_skipped(ctx):
    ctx.stamp()
    job, = jobs_of(SceneOperationTracker(), Teacher(ctx).attach())
    changed = copy.deepcopy(ctx.raw)
    changed["model_qpos"][0] += 0.1
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_SOURCE_NATIVE_MISMATCH"):
        select_source(world_records=[ctx.received], scene_frames=[(ctx.scene_state, ctx.receipt_s)],
                      raw_lookup=lambda step: {"sample": changed}, identity=IDENTITY,
                      model_sha256=ctx.scene_state["model_sha256"], anchor=job.apply)
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_SOURCE_AMBIGUOUS"):
        select_source(world_records=[ctx.received], scene_frames=[(ctx.scene_state, ctx.receipt_s)] * 2,
                      raw_lookup=lambda step: {"sample": ctx.raw}, identity=IDENTITY,
                      model_sha256=ctx.scene_state["model_sha256"], anchor=job.apply)


def own_initial_job(ctx, scene=None):
    """The Recorder's OWN read of the scene before the Teacher's SETUP: a full read, no apply, no Teacher event (CP-3425)."""
    from moveit_msgs.srv import GetPlanningScene

    payload = Teacher(ctx).call(full_read_request(), GetPlanningScene.Response(
        scene=ctx.world_scene(0.003) if scene is None else scene), phase="RECORDER_ROW_SCENE",
        service="/get_planning_scene", state=None)
    record, _request, _response = scene_operation_record(payload)
    return AssociationJob("initial", None, record, None, time.monotonic())


def test_the_initial_alignment_is_the_recorders_own_pre_setup_read_and_asserts_only_that_nothing_is_attached(ctx):
    ctx.stamp()
    document, raw = associate(ctx, own_initial_job(ctx))
    assert verified(ctx, document, raw).success
    assert document["operation"] == "initial" and document["apply"] is None and document["schema_version"] == 3
    evidence = document["receipt"]["verification"]["evidence"]
    assert evidence["mismatches"] == [] and evidence["attached_ids"] == []
    assert document["expected"]["geometry"] == {"attached": []}
    assert association_anchor(document) is document["query"]["record"]
    validate_scene_association(document)
    # the world objects the scene happens to hold are recorded, never required (the worker guarantees only the attachments)
    assert "table" in evidence["world_ids"]
    empty = ctx.world_scene(0.003)
    empty.world.collision_objects = []
    empty.object_colors = []
    ctx.stamp()
    document, raw = associate(ctx, own_initial_job(ctx, empty))
    assert verified(ctx, document, raw).success and document["receipt"]["verification"]["evidence"]["world_ids"] == []


def test_a_residual_attached_body_before_the_setup_is_invalid_and_never_passes_silently(ctx):
    """The worker's initial gate (`parallel_ros_runtime` POINT_INITIAL_GATE, ROBOT_STATE_ATTACHED_OBJECTS) guarantees no
    attached object; MoveIt's `Attached body 'plastic_cup' not found` in the logs is its answer to the SETUP's REMOVE of a cup
    that is NOT attached. A cup that IS still attached is a defect of the start state: the alignment refuses it."""
    ctx.stamp()
    residual = ctx.attached_scene(0.0)
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_GEOMETRY_MISMATCH: attached_not_empty"):
        associate(ctx, own_initial_job(ctx, residual))


def test_the_initial_alignment_schema_is_exactly_version_3_without_an_apply(ctx):
    ctx.stamp()
    document, raw = associate(ctx, own_initial_job(ctx))
    altered = copy.deepcopy(document)
    for key in ("request_ros_clock", "response_ros_clock"):
        altered["query"]["record"][key]["sim_time_ns"] += 200_000_000
    with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_SOURCE_CLOCK_MAPPING_INVALID"):
        verified(ctx, altered, raw)
    altered = copy.deepcopy(document)
    altered["apply"] = copy.deepcopy(document["query"])
    with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_SCHEMA_INVALID"):
        validate_scene_association(altered)
    for version in (1, 2):
        altered = copy.deepcopy(document)
        altered["schema_version"] = version
        with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_SCHEMA_INVALID"):
            validate_scene_association(altered)


def test_a_setup_world_sync_fails_the_qc_readback_when_its_clocks_are_moved(ctx):
    ctx.stamp()
    job, = jobs_of(SceneOperationTracker(), Teacher(ctx).setup())
    document, raw = associate(ctx, job)
    altered = copy.deepcopy(document)
    for key in ("request_ros_clock", "response_ros_clock"):
        altered["apply"]["record"][key]["sim_time_ns"] += 200_000_000
    with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_"):
        verified(ctx, altered, raw)


# ---- the Recorder's sources run the whole chain with the real QC verification -------------------------------------

def sources_fixture(ctx, monkeypatch):
    """RosRecorderSources over fakes that stand for the Recorder's own recorded sources; real verification runs."""
    from dataclasses import asdict

    import rclpy
    from so101_demo.ros import episode_recorder_sources as module
    from so101_demo.act.episode_recorder_process import FaultInjector
    from so101_demo.parallel_batch.contracts import LeaseIdentity
    from test_act_episode_recorder_sources import RecordingNode

    monkeypatch.setattr(rclpy, "spin_once", lambda *args, **kwargs: None)
    lease = LeaseIdentity(batch_id="b", coordinator_epoch=1, worker_id="w00", worker_generation=1, point_id="p",
                          attempt_id="alignment-attempt", lease_generation=1, lease_issued_monotonic_s=1.0,
                          lease_deadline_monotonic_s=time.monotonic() + 600.)
    identity = {"session_id": "alignment-session", "attempt_id": "alignment-attempt", "reset_epoch": 1, "release_epoch": 0,
                "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic", "lease": asdict(lease)}
    appended = []
    audit = SimpleNamespace(inputs=ctx.inputs, append_scene_association=appended.append,
                            append_collection_boundary=lambda *a: None, identity=identity)
    capture = SimpleNamespace(started=False, audit=audit, on_acquisition=lambda frame, pixels: None,
                              window={"collection_end_s": 1.0})
    episode = SimpleNamespace(identity=identity, capture=capture,
                              frozen_inputs_manifest=ctx.root.parent / "inputs-manifest.json",
                              execution_inputs={"scene_path": "scene.xml"}, bind_physical_provider=lambda p: None)
    binding = SimpleNamespace(
        observer=SimpleNamespace(original_frames_with_receipts=lambda: [(ctx.scene_state, ctx.receipt_s)]),
        physics_adapter=SimpleNamespace(
            original_durable_steps=lambda min_physics_step=None: [ctx.raw],
            source_at=lambda at, **kw: {"sample": ctx.raw, "received_monotonic_ns": 1, "chunk_sequence": 1},
            receipt_diagnostics=lambda: {"chunk_count": 1}),
        model=ctx.model, model_identity={"model_sha256": ctx.scene_state["model_sha256"]}, observation_adapter=None,
        hazards=[], drain_sources=lambda: 0, close=lambda: None)
    world = SimpleNamespace(retained_with_receipts=lambda: (ctx.received,), callback_count=1)
    latched = []
    engine = SimpleNamespace(on_event_text=lambda text: None, latch=lambda reason, **f: latched.append(reason),
                             invalid=latched, policy={"finish_budget_s": 1.0}, end_obs=None)
    scene_calls = []

    class Client:
        def wait_for_service(self, timeout_sec=None):
            return True

        def call_async(self, request):
            from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
            assert type(request) is GetPlanningScene.Request, "the Recorder may only read the scene"
            scene_calls.append(request)
            response = over_dds(GetPlanningScene.Response(scene=ctx.world_scene(0.003)))
            return SimpleNamespace(done=lambda: True, result=lambda: response)

    node = RecordingNode()
    node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=ctx.sim_ns + ctx.offset_ns))
    sources = module.RosRecorderSources(
        node, episode, SimpleNamespace(session_id="alignment-session", expected_reset_epoch=1), faults=FaultInjector(),
        bind=lambda *a, **k: binding, world_observer_factory=lambda n, s: world,
        reference_port_factory=lambda n, **k: SimpleNamespace(read=lambda when: {}, close=lambda: None),
        scene_client_factory=lambda n: Client())
    sources.prepare(engine)
    return sources, engine, latched, appended, scene_calls, node


def event_of(payload, seq=1):
    published = []
    stream = TeacherEventStream(STREAM_IDENTITY, clock_ns=lambda: 1, publish=published.append, start=False)
    for _ in range(seq - 1):
        stream.offer("phase_finish", {})
    stream.offer("scene_operation", payload)
    stream.pump()
    return decode_event(published[-1])


def settle(sources, engine, *, rounds=200):
    for _ in range(rounds):
        sources.pump(engine)
        if not sources._admissions and not sources._jobs:
            return
        time.sleep(0.01)
    raise AssertionError("the associations never settled")


def test_the_recorders_sources_turn_the_teachers_setup_and_attach_events_into_admitted_verified_associations(
        ctx, monkeypatch):
    ctx.stamp()
    sources, engine, latched, appended, _, node = sources_fixture(ctx, monkeypatch)
    assert sources._execution_root() == ctx.root
    # the initial alignment is the Recorder's own read before the Teacher's SETUP: no Teacher event is involved (CP-3425)
    ctx.stamp()
    sources._query_scene()
    settle(sources, engine)
    assert latched == [] and [item["operation"] for item in appended] == ["initial"]
    assert sources._initial_built is True and len(sources.associations.history) == 1
    ctx.stamp()   # the SETUP happens later: a fresh source precedes it within the 100 ms join
    teacher = Teacher(ctx)
    for payload in teacher.setup():
        sources.on_teacher_event(engine, event_of(payload))
    settle(sources, engine)
    assert latched == [] and [item["operation"] for item in appended] == ["initial", "world_sync"]
    ctx.stamp()   # the attach happens later: a fresh source precedes it within the 100 ms join
    teacher = Teacher(ctx)
    for payload in teacher.attach():
        sources.on_teacher_event(engine, event_of(payload, seq=3))
    settle(sources, engine)
    assert latched == [] and [item["operation"] for item in appended] == ["initial", "world_sync", "attach"]
    assert [item["association"]["operation"] for item in sources.associations.history] == ["initial", "world_sync", "attach"]
    assert sources.final_issues(engine) == []
    assert not [call for call in node.calls if call[0] == "FORBIDDEN"]


def test_rows_wait_while_an_association_is_owed_and_are_ready_once_it_is_admitted_with_the_real_provider(
        ctx, monkeypatch):
    from so101_demo.act.joints import ACT_JOINTS

    ctx.stamp()
    sources, engine, latched, appended, scene_calls, _ = sources_fixture(ctx, monkeypatch)
    teacher = Teacher(ctx)
    at_s = ctx.sim_ns / 1e9
    sources._controller_history.append({"source_stamp_ns": ctx.sim_ns, "generation": 1,
                                        "positions": {name: 0.0 for name in ACT_JOINTS},
                                        "received_monotonic_s": time.monotonic(), "original_message": {}})
    provider = sources._provider
    assert provider.ready(at_s) is False, "no association yet: nothing to join"
    ctx.stamp()
    teacher = Teacher(ctx)
    applied, read = teacher.setup()
    sources.on_teacher_event(engine, event_of(applied))
    sources.on_teacher_event(engine, event_of(read, seq=2))
    sources._service_associations(engine)
    assert provider.ready(at_s) is False, "built but not yet admitted"
    settle(sources, engine)
    sources._query_scene()
    # CP-3403: the pumps that settled the association already read the scene (reads start at the built initial association)
    assert len(scene_calls) >= 1 and provider.ready(at_s) is True
    ctx.stamp()
    teacher = Teacher(ctx)
    attach_applied, attach_read = teacher.attach()
    sources.on_teacher_event(engine, event_of(attach_applied, seq=3))
    assert sources._association_at(ctx.sim_ns / 1e9 + 0.01) is None, "an owed attach association holds later rows back"
    sources.on_teacher_event(engine, event_of(attach_read, seq=4))
    settle(sources, engine)
    assert latched == []


def test_a_missing_readback_event_is_named_by_the_final_check_and_a_gap_never_hides_it(ctx, monkeypatch):
    ctx.stamp()
    sources, engine, latched, _, _, _ = sources_fixture(ctx, monkeypatch)
    teacher = Teacher(ctx)
    attach_applied, attach_read = teacher.attach()
    sources.on_teacher_event(engine, event_of(attach_applied))
    assert sources.final_issues(engine) == ["RECORDER_SOURCE_ALIGNMENT_READBACK_MISSING: attach"]


def test_a_cdr_digest_mismatch_raises_to_the_engine_which_marks_the_data_invalid(ctx, monkeypatch):
    ctx.stamp()
    sources, engine, _, _, _, _ = sources_fixture(ctx, monkeypatch)
    teacher = Teacher(ctx)
    payload = teacher.attach()[0]
    payload["response_cdr_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="SCENE_OPERATION_CDR_DIGEST_MISMATCH"):
        sources.on_teacher_event(engine, event_of(payload))


def test_the_engine_turns_a_digest_mismatch_and_a_sequence_gap_of_scene_events_into_invalid_verdicts(ctx, monkeypatch,
                                                                                                    tmp_path):
    from so101_demo.act.episode_recorder_process import RecorderEngine, load_recorder_policy
    from test_act_episode_recorder import POLICY_FILE, make_episode

    for case in ("digest", "gap"):
        ctx.stamp()
        teacher = Teacher(ctx)
        texts = []
        stream = TeacherEventStream(StreamIdentity("session-1", 2, "attempt-1"), clock_ns=lambda: 1,
                                    publish=texts.append, start=False)
        applied, read = teacher.attach()
        if case == "digest":
            applied["request_cdr_sha256"] = "0" * 64
        stream.offer("scene_operation", applied)
        stream.offer("scene_operation", read)
        stream.pump()
        if case == "gap":
            del texts[0]

        class Sources(SimpleNamespace):
            pass

        seen = []
        from so101_demo.act.episode_recorder_process import RecorderSources

        class Recording(RecorderSources):
            def pump(self, engine):
                pass

            def try_start(self, engine):
                return None

            def on_teacher_event(self, engine, event):
                seen.append(scene_operation_record(event["payload"]) if event["type"] == "scene_operation" else None)

        working = tmp_path / case
        working.mkdir()
        engine = RecorderEngine(episode=make_episode(working), sources=Recording(),
                                policy=dict(load_recorder_policy(POLICY_FILE), poll_s=0.0),
                                identity=StreamIdentity("session-1", 2, "attempt-1"),
                                ready_file=working / "ready.json", result_file=working / "result.json")
        engine.episode.start(1.0)
        for text in texts:
            engine.on_event_text(text)
        engine.step()
        reasons = [item["reason"] for item in engine.invalid]
        if case == "digest":
            assert any("SCENE_OPERATION_CDR_DIGEST_MISMATCH" in reason for reason in reasons), reasons
        else:
            assert any("TEACHER_EVENT_SEQUENCE_GAP" in reason for reason in reasons), reasons


def test_an_association_whose_source_has_not_arrived_is_retried_then_invalid(ctx, monkeypatch):
    ctx.stamp()
    sources, engine, latched, appended, _, _ = sources_fixture(ctx, monkeypatch)
    sources.world.retained_with_receipts = lambda: ()
    ctx.stamp()
    teacher = Teacher(ctx)
    for payload in teacher.setup():
        sources.on_teacher_event(engine, event_of(payload))
    sources._service_associations(engine)
    assert len(sources._jobs) == 1 and appended == [], "a source that may still arrive is waited for, bounded"
    sources.world.retained_with_receipts = lambda: (ctx.received,)
    settle(sources, engine)
    assert [item["operation"] for item in appended] == ["world_sync"]
    sources2, engine2, *_ = sources_fixture(ctx, monkeypatch)
    sources2.world.retained_with_receipts = lambda: ()
    sources2.ALIGNMENT_RETRY_S = 0.0
    for payload in Teacher(ctx).setup():
        sources2.on_teacher_event(engine2, event_of(payload))
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE"):
        sources2._service_associations(engine2)


def test_the_capture_start_waits_for_the_initial_association_to_be_built(ctx, monkeypatch):
    ctx.stamp()
    sources, engine, *_ = sources_fixture(ctx, monkeypatch)
    assert sources.try_start(engine) is None
    assert sources.listening(engine) is True


def test_admission_runs_the_real_verification_off_the_loop_and_a_failing_one_surfaces_as_an_exception(ctx, monkeypatch):
    ctx.stamp()
    sources, engine, latched, appended, _, _ = sources_fixture(ctx, monkeypatch)
    release = threading.Event()
    original = sources._provider.admit_scene_association

    def slow(bound):
        release.wait(5)
        altered = copy.deepcopy(bound)
        altered["association"]["receipt"]["sha256"] = "0" * 64
        return original(altered)

    sources._provider.admit_scene_association = slow
    ctx.stamp()
    for payload in Teacher(ctx).setup():
        sources.on_teacher_event(engine, event_of(payload))
    began = time.monotonic()
    sources._service_associations(engine)
    assert time.monotonic() - began < 2.0, "the loop never waits for the verification"
    assert len(sources._admissions) == 1 and sources.associations.history == []
    release.set()
    with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_"):
        for _ in range(500):
            sources._service_associations(engine)
            time.sleep(0.01)


def test_c2_an_unavailable_source_names_what_the_recorder_had_so_the_cause_is_retained(ctx):
    ctx.stamp()
    ctx.offset_ns = 150_000_000
    job, = jobs_of(SceneOperationTracker(), Teacher(ctx).attach())
    with pytest.raises(SceneAssociationError) as caught:
        associate(ctx, job)
    text = str(caught.value)
    assert text.startswith("RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE")
    for key in ("worlds=1", "too_old=1", "no_scene_frame=0", "no_raw_step=0", "newest_world_step="):
        assert key in text


def test_c3_a_failed_association_retains_the_inputs_the_join_saw(ctx, monkeypatch, tmp_path):
    ctx.stamp()
    sources, engine, *_ = sources_fixture(ctx, monkeypatch)
    sources.episode.capture.recorder = SimpleNamespace(root=tmp_path)
    sources.binding.physics_adapter.retained_step_range = lambda: (ctx.raw["physics_step"] + 10, ctx.raw["physics_step"] + 20)
    sources.world.retained_with_receipts = lambda: (ctx.received,)
    sources.ALIGNMENT_RETRY_S = 0.0
    ctx.stamp()
    ctx.offset_ns = 150_000_000       # outside the 100 ms window: the join fails
    for payload in Teacher(ctx).setup():
        sources.on_teacher_event(engine, event_of(payload))
    with pytest.raises(SceneAssociationError, match="RECORDER_SOURCE_ALIGNMENT_UNAVAILABLE"):
        sources._service_associations(engine)
    document = json.loads((tmp_path / "source-alignment-failure.json").read_text())
    assert document["operation"] == "world_sync"
    assert document["world_records"]["count"] == 1 and document["scene_frames"]["count"] == 1
    assert document["raw_steps"] == {"min": ctx.raw["physics_step"] + 10, "max": ctx.raw["physics_step"] + 20}
    assert document["overlap"]["world_scene_and_raw_steps"] == 0      # the raw range does not cover the world step
    assert document["rejections"]["too_old"] == 1 and document["anchor"]["sim_time_ns"] > 0


def test_c3_a_retry_that_succeeds_leaves_no_failure_file(ctx, monkeypatch, tmp_path):
    ctx.stamp()
    sources, engine, *_ = sources_fixture(ctx, monkeypatch)
    sources.episode.capture.recorder = SimpleNamespace(root=tmp_path)
    ctx.stamp()
    for payload in Teacher(ctx).setup():
        sources.on_teacher_event(engine, event_of(payload))
    settle(sources, engine)
    assert not (tmp_path / "source-alignment-failure.json").exists()
