"""Frozen-source source alignment reconstruction with full generated ROS values, never live acceptance."""

import copy
import time
from types import SimpleNamespace

import pytest
from paths import REPOSITORY


@pytest.fixture(scope="module")
def frozen_scene(tmp_path_factory):
    import mujoco
    from so101_demo.act.execution_snapshot import freeze_execution_snapshot
    from so101_demo.act.diagnostic_episode_inputs import execution_snapshot_binding, INPUT_ROLES
    from so101_demo.act.scene_association import digest
    root = tmp_path_factory.mktemp("alignment-frozen") / "execution"
    source = REPOSITORY
    snapshot = freeze_execution_snapshot(source, root)
    roles = {name: {"identity": {}} for name in INPUT_ROLES}
    roles["scene_model"]["identity"] = {key: snapshot[key] for key in ("model_sha256", "mujoco_version")}
    inputs = {"roles": roles, "execution_snapshot": execution_snapshot_binding(snapshot, root)}
    inputs["inputs_sha256"] = digest({**roles, "execution_snapshot": inputs["execution_snapshot"]})
    model = mujoco.MjModel.from_xml_path(str(root / snapshot["scene_path"]))
    return root, inputs, model


def association(frozen_scene):
    import mujoco
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.act.scene_association import make_scene_association, source_geometry
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    from so101_demo.core.task_geometry import load_task_geometry
    from so101_demo.control.planning_scene.task_scene import make_task_scene, verify_task_scene, record_scene_service_call

    root, inputs, model = frozen_scene
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "task_start"))
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
    joint = model.body_jntadr[body]
    address = model.jnt_qposadr[joint]
    data.qpos[address + 2] = .5
    mujoco.mj_step(model, data)
    w, x, y, z = data.qpos[address + 3:address + 7]
    position = tuple(map(float, data.qpos[address:address + 3]))
    import numpy as np
    independent = mujoco.MjData(model)
    mujoco.mj_copyData(independent, model, data)
    mujoco.mj_forward(model, independent)
    velocity = np.zeros(6)
    mujoco.mj_objectVelocity(model, independent, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
    state = ObjectState(body, "plastic_cup", position, (float(x), float(y), float(z), float(w)),
                        tuple(map(float, velocity[3:])), tuple(map(float, velocity[:3])))
    world = SimulationEvidence(float(data.time), "world", 7, 1, 1, "alignment-session", False,
        state, False, 0., 0., False, (), (), ())
    begin = time.monotonic_ns()
    end = time.monotonic_ns()
    receipt = time.monotonic_ns()
    scene_state = {"simulation_session_id": "alignment-session", "reset_epoch": 1, "simulation_step": 1,
        "simulation_time_s": float(data.time), "model_sha256": inputs["execution_snapshot"]["model_identity"]["model_sha256"],
        "qpos": list(map(float, data.qpos)), "qvel": list(map(float, data.qvel)), "paused": False,
        "clock_interval_begin_monotonic_ns": begin, "clock_interval_end_monotonic_ns": end}
    geometry = source_geometry(load_task_geometry(root / "assets/common/geometry-manifest.yaml"), world)
    scene = make_task_scene(geometry)
    scene.is_diff = False
    scene.robot_state.attached_collision_objects = []
    expected_scene = make_task_scene(geometry)
    calls = []
    from rosidl_runtime_py.convert import message_to_ordereddict
    message_to_ordereddict(ApplyPlanningScene.Request(scene=expected_scene))
    begin, end, receipt = time.monotonic_ns(), time.monotonic_ns(), time.monotonic_ns()
    scene_state["clock_interval_begin_monotonic_ns"] = begin
    scene_state["clock_interval_end_monotonic_ns"] = end
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=round(data.time * 1e9)))
    record_scene_service_call(request=ApplyPlanningScene.Request(scene=expected_scene), phase="APPLY",
        service="/apply_planning_scene", invoke=lambda: ApplyPlanningScene.Response(success=True), records=calls, ros_clock=clock)
    query = GetPlanningScene.Request()
    query.components.components = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
        | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
    record_scene_service_call(request=query, phase="READ_BACK", service="/get_planning_scene",
        invoke=lambda: GetPlanningScene.Response(scene=scene), records=calls, ros_clock=clock)
    verification = verify_task_scene(scene, geometry, cup_world_pose_audit_only=True)
    assert verification.success
    document = make_scene_association(execution_root=root, source=world, scene_state=scene_state,
        received_monotonic_ns=receipt, scene_received_monotonic_ns=receipt, geometry=geometry,
        apply_call=calls[0], query_call=calls[1], verification=verification, operation="world_sync")
    from so101_mujoco_support.msg import PhysicsStepEvidence
    from rosidl_runtime_py.convert import message_to_ordereddict
    sample = PhysicsStepEvidence(physics_step=1, model_qpos=scene_state["qpos"], model_qvel=scene_state["qvel"],
        reset_epoch=1, simulation_session_id="alignment-session", simulation_time_s=float(data.time),
        clock_interval_begin_monotonic_ns=begin - 2, clock_interval_end_monotonic_ns=begin - 1)
    sample.object_pose_world.position.x, sample.object_pose_world.position.y, sample.object_pose_world.position.z = position
    sample.object_pose_world.orientation.w = float(w)
    sample.object_pose_world.orientation.x, sample.object_pose_world.orientation.y, sample.object_pose_world.orientation.z = float(x), float(y), float(z)
    sample.object_twist_world.linear.x, sample.object_twist_world.linear.y, sample.object_twist_world.linear.z = state.linear_velocity_world
    sample.object_twist_world.angular.x, sample.object_twist_world.angular.y, sample.object_twist_world.angular.z = state.angular_velocity_world
    raw = [dict(message_to_ordereddict(sample))]
    return document, raw


def test_alignment_resolves_full_actual_ros_contents_and_frozen_model(frozen_scene):
    from so101_demo.act.scene_association import verify_scene_association
    document, raw = association(frozen_scene)
    root, inputs, model = frozen_scene
    assert verify_scene_association(document, inputs=inputs,
        identity={"session_id": "alignment-session", "reset_epoch": 1}, raw_steps=raw).success
    assert len(document["receipt"]["geometry"]["world"]) == 3
    assert document["source"]["physics"]["publisher_sequence"] == 7
    assert document["apply"]["record"]["request"]["scene"]["world"]["collision_objects"][2]["operation"] == "\x00"


@pytest.mark.parametrize("mutation", ["extra_acm", "replayed_calls", "conflicting_record"])
def test_actual_audit_writer_and_resigned_reader_resolve_alignment_to_retained_native_steps(frozen_scene, tmp_path, mutation):
    import hashlib
    import json
    import shutil
    from so101_demo.act.collection_scope import build_collection_scope
    from so101_demo.act.episode_audit.verification import verify_audit_manifest
    from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
    from so101_demo.act.lossless_recorder import LosslessRecorderQueue
    from so101_demo.act.scene_association import canonical
    from test_act_lossless_recorder_queue import POLICY
    document, raw = association(frozen_scene)
    identity = {"session_id": "alignment-session", "attempt_id": "alignment-attempt", "reset_epoch": 1,
                "release_epoch": 0, "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}
    scope = build_collection_scope("preselected_target_diagnostic", scene_id="default", seed=0,
                                   inputs_sha256=frozen_scene[1]["inputs_sha256"])
    writer = EpisodeAuditWriter(tmp_path / "audit-episode", scope, identity, frozen_scene[1])
    try:
        writer.append_raw_physics({"schema_version": 1, "received_monotonic_ns": time.monotonic_ns(),
            "chunk": {"chunk_sequence": 1, "simulation_session_id": "alignment-session", "reset_epoch": 1,
                "first_physics_step": 1, "last_physics_step": 1,
                "first_simulation_time_s": raw[0]["simulation_time_s"], "last_simulation_time_s": raw[0]["simulation_time_s"],
                "failed_publish_attempts": 0, "handoff_monotonic_ns": 0, "publish_monotonic_ns": 0,
                "publish_deferrals_total": 0, "evidence_loss": False, "samples": raw}})
        writer.append_scene_association(document)
        if mutation != "extra_acm":
            repeated = copy.deepcopy(document)
            repeated["association_id"] += "-replay"
            if mutation == "replayed_calls":
                repeated["source"]["record_id"] += "-replay"
                repeated["expected"]["record_id"] += "-replay"
                repeated["receipt"]["receipt_id"] += "-replay"
                repeated["apply"]["source_id"] = repeated["source"]["record_id"]
                repeated["apply"]["expected_id"] = repeated["expected"]["record_id"]
            else:
                repeated["source"]["received_monotonic_ns"] += 1
            with pytest.raises(ValueError, match="AUDIT_SOURCE_ALIGNMENT_INVALID"):
                writer.append_scene_association(repeated)
        queue = LosslessRecorderQueue(object(), policy=POLICY)
        queue.close()
        writer.append_recorder_queue(queue.snapshot(), sim_time_s=raw[0]["simulation_time_s"])
        path = writer.seal({"start_s": .002, "end_s": .002, "label_cutoff_s": .002})
    finally:
        for stream in writer._streams.values():
            stream.close()
    assert verify_audit_manifest(path)["identity"] == identity
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    copied = tmp_path / "isolated-resigned-audit"
    shutil.copytree(path.parent, copied)
    events = [json.loads(line) for line in (copied / "events.jsonl").read_text().splitlines()]
    alignment_event = next(event for event in events if event["kind"] == "source_alignment")
    if mutation == "extra_acm":
        alignment_event["payload"]["association"]["apply"]["record"]["request"]["scene"]["allowed_collision_matrix"]["default_entry_names"] = ["plastic_cup"]
        alignment_event["payload"]["association"]["apply"]["record"]["request"]["scene"]["allowed_collision_matrix"]["default_entry_values"] = [True]
        rejection = "SOURCE_ALIGNMENT_APPLY_REQUEST_INVALID"
    else:
        replay = copy.deepcopy(alignment_event)
        replay["payload"]["association"] = repeated
        replay["sequence"] = events[-1]["sequence"] + 1
        replay["monotonic_ns"] = events[-1]["monotonic_ns"] + 1
        events.append(replay)
        rejection = "AUDIT_SOURCE_ALIGNMENT_INVALID"
    payload = b"".join(canonical(event) + b"\n" for event in events)
    (copied / "events.jsonl").write_bytes(payload)
    manifest = json.loads((copied / "audit-manifest.json").read_bytes())
    manifest["files"]["events.jsonl"].update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    (copied / "audit-manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match=rejection):
        verify_audit_manifest(copied / "audit-manifest.json")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
    assert verify_audit_manifest(path)["identity"] == identity


def test_actual_dynamic_detach_applies_the_selected_source_geometry_and_records_its_transaction(frozen_scene):
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.act.scene_association import _world, source_geometry
    from so101_demo.core.domain import State
    from so101_demo.core.simulation.types import ReceivedSimulationEvidence
    from so101_demo.core.task_geometry import load_task_geometry
    from so101_demo.control.planning_scene.task_scene import make_task_scene, record_scene_service_call
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    document, raw = association(frozen_scene)
    world = _world(document["source"]["physics"])
    adapter = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    adapter._task_geometry = load_task_geometry(frozen_scene[0] / "assets/common/geometry-manifest.yaml")
    adapter._execution_snapshot_root = frozen_scene[0]
    adapter._session_id, adapter._expected_reset_epoch = world.simulation_session_id, world.reset_epoch
    adapter._document, adapter._scene_service_calls = {}, []
    adapter._touch_collision_allowed = False
    adapter._snapshot = lambda: world
    adapter._supported_release_preflight = lambda: world
    adapter._selected_release_source = ReceivedSimulationEvidence(world, document["source"]["received_monotonic_ns"] * 1e-9)
    adapter._selected_release_source_scene = (document["source"]["scene_state"], document["source"]["scene_received_monotonic_ns"] * 1e-9)
    adapter._monotonic = time.monotonic
    adapter._release_runtime_policy = {"safety_release": {"support_distance_max_m": .002}}
    adapter._execution_policy = {"state_max_age_s": .5}
    adapter._write = lambda: None
    adapter._record = lambda *args, **kwargs: None
    adapter._apply_scene, adapter._get_scene = object(), object()
    response_scene = make_task_scene(source_geometry(adapter._task_geometry, world))
    response_scene.robot_state.attached_collision_objects = []
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=round(world.simulation_time_s * 1e9)))
    adapter._node = SimpleNamespace(get_clock=lambda: clock)
    adapter._scene_source_binding = SimpleNamespace(model=frozen_scene[2],
        model_identity={"model_sha256": document["source"]["scene_state"]["model_sha256"]},
        physics_adapter=SimpleNamespace(source_at=lambda at, **kwargs: {"sample": raw[0]}))
    def call(client, request, timeout, phase, before_dispatch=None):
        if before_dispatch is not None:
            before_dispatch()
        return record_scene_service_call(request=request, phase=phase,
            service="/apply_planning_scene" if client is adapter._apply_scene else "/get_planning_scene",
            invoke=lambda: ApplyPlanningScene.Response(success=True) if client is adapter._apply_scene
                else GetPlanningScene.Response(scene=response_scene), records=adapter._scene_service_calls, ros_clock=clock)
    adapter._call = call
    adapter._detach_or_sync(State.DETACH_MOVEIT)
    # The Teacher's own transaction names the exact source the apply was derived from and the two calls it made; the
    # association itself is the Recorder's (derived from the `scene_operation` events of these two calls).
    transaction = adapter._document["scene_transactions"][0]
    from so101_demo.act.scene_association import canonical
    assert transaction["phase"] == State.DETACH_MOVEIT.value
    assert canonical(transaction["source_physics"]) == canonical(document["source"]["physics"])
    assert [item["service"] for item in adapter._scene_service_calls] == ["/apply_planning_scene", "/get_planning_scene"]
    assert transaction["apply_call_id"] == adapter._scene_service_calls[0]["call_id"]
    assert transaction["query_call_id"] == adapter._scene_service_calls[1]["call_id"]
    assert not hasattr(adapter, "episode_recorder") and not hasattr(adapter, "_active_scene_association")


@pytest.mark.parametrize("mutation", ["missing_native", "none_native", "native_qpos", "query_id", "duplicate_id",
    "apply_refused", "request_geometry", "observed_geometry", "component_mask", "clock", "source_pose",
    "rehashed_frozen_geometry", "old_record", "unknown", "raw_pose", "raw_clock", "raw_contacts", "world_twist", "apply_acm", "old_native_generation", "model_binding",
    "raw_scene_overlap", "response_clock_overlap", "numeric_contact_flag", "boolean_distance", "boolean_force"])
def test_alignment_semantic_negatives_restore_original_positive(frozen_scene, mutation):
    from so101_demo.act.scene_association import canonical, digest, verify_scene_association
    document, raw = association(frozen_scene)
    original = canonical(document)
    altered = copy.deepcopy(document)
    raw_copy = copy.deepcopy(raw)
    inputs_copy = copy.deepcopy(frozen_scene[1])
    if mutation == "missing_native":
        raw_copy = []
    elif mutation == "none_native":
        raw_copy = None
    elif mutation == "native_qpos":
        raw_copy[0]["model_qpos"][0] += .1
    elif mutation == "raw_pose":
        raw_copy[0]["object_pose_world"]["position"]["x"] += .1
    elif mutation == "raw_clock":
        raw_copy[0]["clock_interval_end_monotonic_ns"] = altered["apply"]["record"]["response_monotonic_ns"] + 1
    elif mutation == "raw_scene_overlap":
        raw_copy[0]["clock_interval_end_monotonic_ns"] = altered["source"]["scene_state"]["clock_interval_begin_monotonic_ns"] + 1
    elif mutation == "response_clock_overlap":
        altered["apply"]["record"]["response_ros_clock"]["end_monotonic_ns"] = altered["query"]["record"]["request_ros_clock"]["begin_monotonic_ns"] + 1
    elif mutation in ("numeric_contact_flag", "boolean_distance", "boolean_force"):
        field = {"numeric_contact_flag": "has_contact", "boolean_distance": "minimum_signed_distance_m",
                 "boolean_force": "maximum_normal_force_n"}[mutation]
        altered["source"]["physics"][field] = 0 if mutation == "numeric_contact_flag" else False
        altered["source"]["physics_sha256"] = digest(altered["source"]["physics"])
    elif mutation == "old_native_generation":
        raw_copy[0]["clock_interval_begin_monotonic_ns"] -= 200000000
    elif mutation == "model_binding":
        inputs_copy["execution_snapshot"]["model_identity"]["model_sha256"] = "b" * 64
        inputs_copy["roles"]["scene_model"]["identity"]["model_sha256"] = "b" * 64
        altered["source"]["scene_state"]["model_sha256"] = "b" * 64
        inputs_copy["inputs_sha256"] = digest({**inputs_copy["roles"], "execution_snapshot": inputs_copy["execution_snapshot"]})
    elif mutation == "raw_contacts":
        raw_copy[0]["has_contact"] = True
    elif mutation == "world_twist":
        altered["source"]["physics"]["object_state"]["linear_velocity_world"][0] += .1
        altered["source"]["physics_sha256"] = digest(altered["source"]["physics"])
    elif mutation == "apply_acm":
        altered["apply"]["record"]["request"]["scene"]["allowed_collision_matrix"]["default_entry_names"] = ["plastic_cup"]
        altered["apply"]["record"]["request"]["scene"]["allowed_collision_matrix"]["default_entry_values"] = [True]
    elif mutation == "query_id":
        altered["receipt"]["query_id"] = "foreign-query"
    elif mutation == "duplicate_id":
        altered["association_id"] = altered["source"]["record_id"]
    elif mutation == "apply_refused":
        altered["apply"]["record"]["response"]["success"] = False
    elif mutation == "request_geometry":
        altered["apply"]["record"]["request"]["scene"]["world"]["collision_objects"][2]["primitives"][0]["dimensions"][0] += .1
    elif mutation == "observed_geometry":
        altered["query"]["record"]["response"]["scene"]["world"]["collision_objects"][2]["primitives"][0]["dimensions"][0] += .1
    elif mutation == "component_mask":
        altered["query"]["record"]["request"]["components"]["components"] = 0
    elif mutation == "clock":
        altered["apply"]["record"]["request_ros_clock"]["sim_time_ns"] += 200000000
        altered["apply"]["record"]["response_ros_clock"]["sim_time_ns"] += 200000000
        altered["query"]["record"]["request_ros_clock"]["sim_time_ns"] += 200000000
        altered["query"]["record"]["response_ros_clock"]["sim_time_ns"] += 200000000
    elif mutation == "source_pose":
        altered["source"]["physics"]["object_state"]["position_world"][0] += .1
        altered["source"]["physics_sha256"] = digest(altered["source"]["physics"])
    elif mutation == "rehashed_frozen_geometry":
        altered["expected"]["geometry"]["objects"][2]["primitives"][0]["dimensions"][0] += .1
        altered["expected"]["sha256"] = digest(altered["expected"]["geometry"])
        altered["apply"]["expected_sha256"] = altered["expected"]["sha256"]
        altered["apply"]["record"]["request"]["scene"]["world"]["collision_objects"][2]["primitives"][0]["dimensions"][0] += .1
        altered["query"]["record"]["response"]["scene"]["world"]["collision_objects"][2]["primitives"][0]["dimensions"][0] += .1
        cup = next(item for item in altered["receipt"]["geometry"]["world"] if item["id"] == "plastic_cup")
        cup["primitives"][0]["dimensions"][0] += .1
        altered["receipt"]["sha256"] = digest(altered["receipt"]["geometry"])
        altered["receipt"]["verification"]["evidence"]["observed_geometry"] = copy.deepcopy(altered["receipt"]["geometry"])
    elif mutation == "old_record":
        altered["apply"]["record"]["schema_version"] = 1
    else:
        altered["unapproved"] = True
    with pytest.raises((ValueError, AssertionError)):
        verify_scene_association(altered, inputs=inputs_copy,
            identity={"session_id": "alignment-session", "reset_epoch": 1}, raw_steps=raw_copy)
    assert canonical(document) == original
    assert verify_scene_association(document, inputs=frozen_scene[1],
        identity={"session_id": "alignment-session", "reset_epoch": 1}, raw_steps=raw).success
