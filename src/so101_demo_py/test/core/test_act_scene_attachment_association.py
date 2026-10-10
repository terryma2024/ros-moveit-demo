"""Full frozen-source attached cup records; controlled ROS, never live qualification.

A4c: the in-child source alignment association code (the causal source selector with its waits and refusal facts, the attach/detach
association publication, the data-state fence) is gone from the Teacher. The independent Recorder derives each
association from the Teacher's `scene_operation` events; that derivation (source selection, freshness, hazards, the
native-source match, detach and attach verification) is tested in `test_act_recorder_scene` and
`test_act_episode_recorder_sources`. What stays here is the readback-side geometry the QC re-verifies, and the Teacher's
own attach request."""

import copy
import time
from types import SimpleNamespace

import pytest

from test_act_scene_association import association, frozen_scene


def alignment_geometry_attached_scene(geometry):
    """A readback-shaped scene with the cup attached to the gripper at its full source-derived local geometry.

    This is what MoveIt reports once the cup is attached at the physical pose; it is test data for the readback side
    only. (No production request carries it any more: the Teacher always sends the plain attach request.)
    """
    from moveit_msgs.msg import AttachedCollisionObject, PlanningScene
    from so101_demo.core.task_geometry import Pose7, TaskGeometryObject, GeometryPrimitive
    from so101_demo.control.planning_scene.task_scene import _collision_object
    value = geometry["local_cup"]
    cup = TaskGeometryObject(object_id=value["object_id"], pose=Pose7.parse(value["pose"]["values"], "alignment.local"),
        color_rgba=tuple(value["color_rgba"]), primitives=tuple(GeometryPrimitive(
            name=item["name"], kind=item["kind"], dimensions=tuple(item["dimensions"]),
            pose=Pose7.parse(item["pose"]["values"], "alignment.primitive")) for item in value["primitives"]))
    scene = PlanningScene()
    scene.is_diff = scene.robot_state.is_diff = True
    scene.robot_state.attached_collision_objects = [AttachedCollisionObject(
        link_name=geometry["link_name"], touch_links=list(geometry["touch_links"]),
        object=_collision_object(cup, geometry["frame_id"]))]
    return scene


def attachment(frozen_scene):
    import mujoco
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.act.scene_association import (
        _world, make_scene_association, source_geometry, source_attachment_geometry,
    )
    from so101_demo.core.task_geometry import load_task_geometry, Pose7
    from so101_demo.control.planning_scene.task_scene import (
        make_plain_attach_scene, make_task_scene, verify_task_scene, record_scene_service_call)
    document, raw = association(frozen_scene)
    root, inputs, model = frozen_scene
    world = _world(document["source"]["physics"])
    scene_state = copy.deepcopy(document["source"]["scene_state"])
    data = mujoco.MjData(model)
    data.qpos[:], data.qvel[:] = scene_state["qpos"], scene_state["qvel"]
    mujoco.mj_forward(model, data)
    geometry = source_geometry(load_task_geometry(root / "assets/common/geometry-manifest.yaml"), world)
    expected = source_attachment_geometry(geometry, model, data)
    # The Teacher's request is always the plain attach; the readback shows the cup attached at the physical pose.
    request_scene = make_plain_attach_scene()
    observed = make_task_scene(geometry)
    observed.is_diff = False
    observed.world.collision_objects = [item for item in observed.world.collision_objects if item.id != "plastic_cup"]
    observed.robot_state.attached_collision_objects = copy.deepcopy(
        alignment_geometry_attached_scene(expected).robot_state.attached_collision_objects)
    local_pose = Pose7.parse(expected["local_cup"]["pose"]["values"], "fixture.local")
    # The source alignment attach association (A4b) records the cup's local pose delta instead of requiring equality: the Teacher's plain
    # attach applies no cup geometry, so MoveIt keeps its own pose for the cup.
    verification = verify_task_scene(observed, geometry, expected_cup_attachment="gripper",
                                    expected_cup_local_pose=local_pose, expected_touch_links=("gripper", "jaw"),
                                    cup_local_pose_audit_only=True)
    assert verification.success
    # Finish import/message preparation before the unchanged .1s actual-call source window.
    from rosidl_runtime_py.convert import message_to_ordereddict
    message_to_ordereddict(ApplyPlanningScene.Request(scene=request_scene))
    begin, end, receipt = time.monotonic_ns(), time.monotonic_ns(), time.monotonic_ns()
    scene_state.update(clock_interval_begin_monotonic_ns=begin, clock_interval_end_monotonic_ns=end)
    raw[0].update(clock_interval_begin_monotonic_ns=begin - 2, clock_interval_end_monotonic_ns=begin - 1)
    clock = SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=round(world.simulation_time_s * 1e9)))
    calls = []
    record_scene_service_call(request=ApplyPlanningScene.Request(scene=request_scene), phase="ATTACH",
        service="/apply_planning_scene", invoke=lambda: ApplyPlanningScene.Response(success=True), records=calls, ros_clock=clock)
    query = GetPlanningScene.Request()
    query.components.components = (PlanningSceneComponents.WORLD_OBJECT_NAMES | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
        | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.OBJECT_COLORS)
    record_scene_service_call(request=query, phase="READ_BACK", service="/get_planning_scene",
        invoke=lambda: GetPlanningScene.Response(scene=observed), records=calls, ros_clock=clock)
    return make_scene_association(execution_root=root, source=world, scene_state=scene_state,
        received_monotonic_ns=receipt, scene_received_monotonic_ns=receipt, geometry=expected,
        apply_call=calls[0], query_call=calls[1], verification=verification, operation="attach"), raw


def _restamp_clocks(scene, raw_sample, received=()):
    """Stamp the source clocks at the current monotonic time and return the scene receipt time.

    The selector's real-clock freshness checks allow 0.1 s, so fixtures restamp when the selector drains the
    sources instead of depending on fixture-build latency under host load. Order is preserved: raw end <
    scene begin <= evidence receipt <= scene receipt.
    """
    begin = time.monotonic_ns()
    scene.update(clock_interval_begin_monotonic_ns=begin, clock_interval_end_monotonic_ns=begin)
    raw_sample.update(clock_interval_begin_monotonic_ns=begin - 2, clock_interval_end_monotonic_ns=begin - 1)
    for item in received:
        object.__setattr__(item, "received_monotonic_s", time.monotonic())
    return time.monotonic()


def test_full_attached_geometry_reconstructs_gripper_local_pose_from_frozen_native_fk(frozen_scene):
    import mujoco
    import numpy as np
    from so101_demo.act.scene_association import verify_scene_association
    document, raw = attachment(frozen_scene)
    assert verify_scene_association(document, inputs=frozen_scene[1],
                                   identity={"session_id": "alignment-session", "reset_epoch": 1}, raw_steps=raw).success
    model = frozen_scene[2]
    data = mujoco.MjData(model)
    data.qpos[:], data.qvel[:] = raw[0]["model_qpos"], raw[0]["model_qvel"]
    mujoco.mj_forward(model, data)
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "gripper")
    local = document["expected"]["geometry"]["local_cup"]["pose"]["values"]
    reconstructed = data.xpos[body] + data.xmat[body].reshape(3, 3) @ np.array(local[:3])
    assert reconstructed == pytest.approx(document["source"]["physics"]["object_state"]["position_world"])
    from scipy.spatial.transform import Rotation
    actual_orientation = document["source"]["physics"]["object_state"]["orientation_xyzw"]
    assert data.xmat[body].reshape(3, 3) @ Rotation.from_quat(local[3:]).as_matrix() == pytest.approx(
        Rotation.from_quat(actual_orientation).as_matrix(), abs=1e-9)
    assert document["receipt"]["geometry"]["attached"][0]["object"]["frame_id"] == "gripper"
    assert len(document["receipt"]["geometry"]["attached"][0]["object"]["primitives"]) == 13


@pytest.mark.parametrize("change", ["pose", "frame", "dimension", "touch_links", "colors", "extra_acm", "source_fk"])
def test_valid_ros_attached_mutations_cannot_pass_rehashed_alignment(frozen_scene, change):
    from so101_demo.act.scene_association import verify_scene_association, digest
    document, raw = attachment(frozen_scene)
    if change == "extra_acm":
        document["apply"]["record"]["request"]["scene"]["allowed_collision_matrix"]["default_entry_names"] = ["plastic_cup"]
        document["apply"]["record"]["request"]["scene"]["allowed_collision_matrix"]["default_entry_values"] = [True]
    elif change == "source_fk":
        document["expected"]["geometry"]["local_cup"]["pose"]["values"][0] += .01
        document["expected"]["sha256"] = digest(document["expected"]["geometry"])
        document["apply"]["expected_sha256"] = document["expected"]["sha256"]
    else:
        scene = document["query"]["record"]["response"]["scene"]
        attached = scene["robot_state"]["attached_collision_objects"][0]
        if change == "pose":
            attached["object"]["pose"]["position"]["x"] += .01
        elif change == "frame":
            attached["object"]["header"]["frame_id"] = "world"
        elif change == "dimension":
            attached["object"]["primitives"][0]["dimensions"][0] += .01
        elif change == "touch_links":
            attached["touch_links"] = ["gripper", "jaw", "table"]
        else:
            scene["object_colors"][0]["color"]["g"] += .01
    with pytest.raises(ValueError):
        verify_scene_association(document, inputs=frozen_scene[1],
                                identity={"session_id": "alignment-session", "reset_epoch": 1}, raw_steps=raw)


def test_attach_association_accepts_only_the_plain_request_form(frozen_scene):
    """The recorded apply request must be the Teacher's one plain attach, never a geometry-carrying form."""
    from moveit_msgs.srv import ApplyPlanningScene
    from rosidl_runtime_py.convert import message_to_ordereddict
    from so101_demo.act.scene_association import verify_scene_association
    identity = {"session_id": "alignment-session", "reset_epoch": 1}
    document, raw = attachment(frozen_scene)
    plain = document["apply"]["record"]["request"]["scene"]["robot_state"]["attached_collision_objects"][0]
    assert plain["object"]["primitives"] == [] and plain["link_name"] == "gripper"
    assert verify_scene_association(document, inputs=frozen_scene[1], identity=identity, raw_steps=raw).success
    geometry_form = ApplyPlanningScene.Request(scene=alignment_geometry_attached_scene(document["expected"]["geometry"]))
    document["apply"]["record"]["request"] = dict(message_to_ordereddict(geometry_form))
    with pytest.raises(ValueError, match="SOURCE_ALIGNMENT_APPLY_REQUEST_INVALID"):
        verify_scene_association(document, inputs=frozen_scene[1], identity=identity, raw_steps=raw)


def _teacher_attach(*, apply_success=True, attached=("plastic_cup",)):
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    value = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    requests, recorded = [], []
    before, after = object(), object()
    snapshots = iter((before, after))
    value._snapshot = lambda: next(snapshots)
    value._apply_scene = object()
    value._touch_collision_allowed = False
    value._scene_membership = lambda: (list(attached), {"plastic_cup": 13})
    value._record = lambda *args, **kwargs: recorded.append((args, kwargs))

    def call(client, request, timeout, phase, before_dispatch=None):
        requests.append((client, request, phase))
        return ApplyPlanningScene.Response(success=apply_success)

    value._call = call
    return value, requests, recorded, (before, after)


def test_the_teacher_attach_sends_the_plain_request_and_reads_the_attachment_back():
    from moveit_msgs.srv import ApplyPlanningScene
    from so101_demo.control.planning_scene.task_scene import make_plain_attach_scene
    from so101_demo.core.domain import State
    value, requests, recorded, (before, after) = _teacher_attach()
    value._attach(State.ATTACH_MOVEIT)
    assert [(request, phase) for _, request, phase in requests] == [
        (ApplyPlanningScene.Request(scene=make_plain_attach_scene()), "DYNAMIC_ATTACH")]
    attached = requests[0][1].scene.robot_state.attached_collision_objects[0]
    assert attached.object.id == "plastic_cup" and attached.link_name == "gripper" and not attached.object.primitives
    assert requests[0][1].scene.world.collision_objects == []
    assert value._attached is True
    assert recorded and recorded[0][0][:3] == (State.ATTACH_MOVEIT, before, after)


@pytest.mark.parametrize("fault, code", [("apply_refused", "DYNAMIC_ATTACH_FAILED"),
                                          ("not_attached", "DYNAMIC_ATTACH_READBACK_MISMATCH")])
def test_the_teacher_attach_refusals_are_the_teachers_own_failures(fault, code):
    from so101_demo.core.domain import State
    value, requests, recorded, _ = _teacher_attach(apply_success=fault != "apply_refused",
                                                    attached=() if fault == "not_attached" else ("plastic_cup",))
    with pytest.raises(RuntimeError, match=code):
        value._attach(State.ATTACH_MOVEIT)
    assert not getattr(value, "_attached", False) and recorded == []


def test_the_teacher_attach_has_no_association_machinery_to_depend_on():
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution
    for name in ("_causal_scene_source", "_try_causal_scene_source", "_check_scene_source_freshness",
                 "_plan_attach_association", "_attach_association", "_detach_association", "_publish_scene_association",
                 "_scene_transaction", "_refresh_collection_scene"):
        assert not hasattr(RosDynamicMujocoExecution, name), name
