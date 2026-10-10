import pytest
from types import SimpleNamespace
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT


def _geometry():
    from so101_demo.core.task_geometry import load_task_geometry

    return load_task_geometry(PACKAGE / "assets/common/geometry-manifest.yaml")


def _readback_scene():
    from so101_demo.control.planning_scene.task_scene import make_task_scene

    scene = make_task_scene(_geometry())
    scene.robot_state.attached_collision_objects = []
    return scene


def test_builder_consumes_manifest_with_object_and_local_primitive_poses() -> None:
    scene = _readback_scene()
    objects = {value.id: value for value in scene.world.collision_objects}

    assert tuple(objects) == ("table", "pedestal", "plastic_cup")
    assert {name: len(value.primitives) for name, value in objects.items()} == {
        "table": 1,
        "pedestal": 1,
        "plastic_cup": 13,
    }
    cup = objects["plastic_cup"]
    assert (cup.pose.position.x, cup.pose.position.y, cup.pose.position.z) == (
        0.02,
        -0.28,
        0.165,
    )
    assert (cup.primitive_poses[0].position.x, cup.primitive_poses[0].position.y) == (
        0.0,
        0.039,
    )
    assert list(cup.primitives[-1].dimensions) == [0.002, 0.04]
    assert {value.id for value in scene.object_colors} == set(objects)


def test_scene_verifier_proves_full_contract() -> None:
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    verification = verify_task_scene(_readback_scene(), _geometry())

    assert verification.success
    assert verification.failure_code is None
    assert verification.evidence["primitive_counts"] == {
        "table": 1,
        "pedestal": 1,
        "plastic_cup": 13,
    }
    assert verification.evidence["attached_ids"] == []


def test_scene_verifier_rejects_unrelated_color_membership():
    from moveit_msgs.msg import ObjectColor
    from so101_demo.control.planning_scene.task_scene import verify_task_scene
    scene = _readback_scene()
    scene.object_colors.append(ObjectColor(id="foreign"))
    result = verify_task_scene(scene, _geometry())
    assert not result.success
    assert "color_membership" in result.evidence["mismatches"]


def test_scene_verifier_accepts_explicit_source_derived_local_attachment_pose():
    from dataclasses import replace
    from moveit_msgs.msg import AttachedCollisionObject
    from so101_demo.control.planning_scene.task_scene import _collision_object, verify_task_scene
    from so101_demo.core.task_geometry import Pose7
    geometry = _geometry()
    local_pose = Pose7.parse([.01, .02, .03, 0., 0., 0., 1.], "fixture.local")
    cup = replace(geometry.object("plastic_cup"), pose=local_pose)
    scene = _readback_scene()
    scene.world.collision_objects = [obj for obj in scene.world.collision_objects if obj.id != "plastic_cup"]
    attached = AttachedCollisionObject(link_name="gripper", touch_links=["gripper", "jaw"],
                                      object=_collision_object(cup, "gripper"))
    scene.robot_state.attached_collision_objects = [attached]
    result = verify_task_scene(scene, geometry, expected_cup_attachment="gripper",
                               expected_cup_local_pose=local_pose, expected_touch_links=("gripper", "jaw"))
    assert result.success
    attached.object.pose.position.x += .01
    assert not verify_task_scene(scene, geometry, expected_cup_attachment="gripper",
                                 expected_cup_local_pose=local_pose, expected_touch_links=("gripper", "jaw")).success


def test_scene_verification_retains_actual_full_geometry_for_independent_readback():
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    scene = _readback_scene()
    verification = verify_task_scene(scene, _geometry())
    observed = verification.evidence["observed_geometry"]
    assert observed["attached"] == []
    cup = next(item for item in observed["world"] if item["id"] == "plastic_cup")
    assert cup["frame_id"] == "world"
    assert cup["pose"] == list(_geometry().object("plastic_cup").pose.values)
    assert len(cup["primitives"]) == len(cup["primitive_poses"]) == 13
    assert cup["primitives"][-1] == {"type": 3, "dimensions": [0.002, 0.04]}
    assert next(item for item in observed["colors"] if item["id"] == "plastic_cup")["rgba"] == list(
        _geometry().object("plastic_cup").color_rgba)
    scene.world.collision_objects[2].primitives[-1].dimensions[0] += 0.01
    refused = verify_task_scene(scene, _geometry())
    assert not refused.success
    changed = next(item for item in refused.evidence["observed_geometry"]["world"]
                   if item["id"] == "plastic_cup")
    assert changed["primitives"][-1]["dimensions"][0] == 0.012


def test_scene_verifier_rejects_duplicate_actual_ids_instead_of_erasing_them():
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    scene = _readback_scene()
    scene.world.collision_objects.append(scene.world.collision_objects[2])
    verification = verify_task_scene(scene, _geometry())
    assert not verification.success
    assert "world_duplicate_ids" in verification.evidence["mismatches"]


def test_scene_port_retains_actual_service_call_request_response_and_clock_bounds(monkeypatch):
    import rclpy
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from so101_demo.control.planning_scene.task_scene import RosTaskScenePort, make_task_scene

    monkeypatch.setattr(rclpy, "spin_until_future_complete", lambda *args, **kwargs: None)

    class Client:
        def __init__(self, response):
            self.response = response
            self.requests = []

        def call_async(self, request):
            self.requests.append(request)
            return SimpleNamespace(done=lambda: True, result=lambda: self.response)

    port = object.__new__(RosTaskScenePort)
    port._node = object()
    port._backend = "mujoco"
    port._timeout_s = 0.1
    port._service_calls = []
    port._apply_client = Client(ApplyPlanningScene.Response(success=True))
    port._get_client = Client(GetPlanningScene.Response(scene=_readback_scene()))
    request = ApplyPlanningScene.Request(scene=make_task_scene(_geometry()))
    assert port._call(port._apply_client, request, "APPLY").success
    query = GetPlanningScene.Request()
    query.components.components = 123
    assert port._call(port._get_client, query, "READ_BACK").scene.world.collision_objects
    records = port.service_call_records()
    assert len(records) == 2
    apply, readback = records
    assert apply["call_id"] != readback["call_id"]
    assert apply["service"] == "/apply_planning_scene"
    assert apply["request"]["scene"]["world"]["collision_objects"][2]["id"] == "plastic_cup"
    assert apply["response"] == {"success": True}
    assert readback["service"] == "/get_planning_scene"
    assert readback["request"]["components"]["components"] == 123
    assert len(readback["response"]["scene"]["world"]["collision_objects"][2]["primitives"]) == 13
    assert 0 < apply["request_monotonic_ns"] <= apply["response_monotonic_ns"] <= readback["request_monotonic_ns"]
    assert readback["request_monotonic_ns"] <= readback["response_monotonic_ns"]
    assert "sim_time_s" not in apply and "scene_revision" not in readback
    records[0]["response"]["success"] = False
    assert port.service_call_records()[0]["response"]["success"] is True


def test_scene_verifier_accepts_equivalent_quaternion_sign_from_moveit() -> None:
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    scene = _readback_scene()
    pose = scene.world.collision_objects[2].primitive_poses[4]
    pose.orientation.x *= -1.0
    pose.orientation.y *= -1.0
    pose.orientation.z *= -1.0
    pose.orientation.w *= -1.0

    verification = verify_task_scene(scene, _geometry())

    assert verification.success
    assert verification.evidence["mismatches"] == []


def test_scene_verifier_rejects_pose_count_color_and_attachment_mismatches() -> None:
    from moveit_msgs.msg import AttachedCollisionObject
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    mutations = []

    pose = _readback_scene()
    pose.world.collision_objects[2].pose.position.x += 0.01
    mutations.append(pose)

    count = _readback_scene()
    count.world.collision_objects[2].primitives.pop()
    count.world.collision_objects[2].primitive_poses.pop()
    mutations.append(count)

    color = _readback_scene()
    color.object_colors[2].color.r = 0.0
    mutations.append(color)

    attached = _readback_scene()
    value = AttachedCollisionObject()
    value.object.id = "plastic_cup"
    attached.robot_state.attached_collision_objects = [value]
    mutations.append(attached)

    for scene in mutations:
        verification = verify_task_scene(scene, _geometry())
        assert not verification.success
        assert verification.failure_code == "SCENE_READBACK_MISMATCH"


def test_scene_verifier_can_require_the_cup_attachment_state() -> None:
    from moveit_msgs.msg import AttachedCollisionObject
    from so101_demo.control.planning_scene.task_scene import verify_task_scene

    scene = _readback_scene()
    cup = scene.world.collision_objects.pop()
    attached = AttachedCollisionObject()
    attached.object = cup
    attached.link_name = "gripper"
    scene.robot_state.attached_collision_objects = [attached]

    verification = verify_task_scene(
        scene,
        _geometry(),
        expected_cup_attachment="gripper",
    )

    assert verification.success
    assert verification.evidence["attached_ids"] == ["plastic_cup"]


def _plain_attached_scene(*, shift=(0., 0., 0.), link="gripper", touch=("gripper", "jaw"), frame=None):
    """What MoveIt reports after the Teacher's plain attach: the cup on the gripper at MoveIt's own local pose."""
    from dataclasses import replace
    from moveit_msgs.msg import AttachedCollisionObject
    from so101_demo.control.planning_scene.task_scene import _collision_object
    from so101_demo.core.task_geometry import Pose7
    geometry = _geometry()
    moveit_pose = Pose7.parse([.01 + shift[0], .02 + shift[1], .03 + shift[2], 0., 0., 0., 1.], "fixture.moveit")
    cup = replace(geometry.object("plastic_cup"), pose=moveit_pose)
    scene = _readback_scene()
    scene.world.collision_objects = [obj for obj in scene.world.collision_objects if obj.id != "plastic_cup"]
    attached = AttachedCollisionObject(link_name=link, touch_links=list(touch),
                                      object=_collision_object(cup, frame or link))
    scene.robot_state.attached_collision_objects = [attached]
    return scene, attached, geometry


def _audit_call(scene, geometry, **overrides):
    from so101_demo.control.planning_scene.task_scene import verify_task_scene
    from so101_demo.core.task_geometry import Pose7
    parameters = dict(expected_cup_attachment="gripper",
                      expected_cup_local_pose=Pose7.parse([.01, .02, .03, 0., 0., 0., 1.], "fixture.source_local"),
                      expected_touch_links=("gripper", "jaw"), cup_local_pose_audit_only=True)
    parameters.update(overrides)
    return verify_task_scene(scene, geometry, **parameters)


def test_audit_only_cup_local_pose_difference_passes_and_records_the_delta():
    import math
    scene, attached, geometry = _plain_attached_scene(shift=(.03, .04, 0.))
    # A pure translation difference of 0.05 m plus a 90 degree yaw: neither may refuse in audit-only mode.
    attached.object.pose.orientation.z = math.sqrt(.5)
    attached.object.pose.orientation.w = math.sqrt(.5)
    result = _audit_call(scene, geometry)
    assert result.success and result.evidence["mismatches"] == []
    audit = result.evidence["cup_local_pose_audit"]
    assert audit["translation_delta_m"] == pytest.approx(.05)
    assert audit["rotation_delta_rad"] == pytest.approx(math.pi / 2)
    assert audit["expected_pose"] == [.01, .02, .03, 0., 0., 0., 1.]
    assert audit["observed_pose"][:3] == pytest.approx([.04, .06, .03])
    assert audit["refuses"] is False


def test_audit_only_without_a_source_local_pose_records_the_reason_and_does_not_refuse():
    scene, attached, geometry = _plain_attached_scene()
    result = _audit_call(scene, geometry, expected_cup_local_pose=None)
    assert result.success
    audit = result.evidence["cup_local_pose_audit"]
    assert audit["translation_delta_m"] is None and audit["reason"] == "SOURCE_LOCAL_POSE_NOT_PROVIDED"


@pytest.mark.parametrize("fault", ["wrong_link", "missing_touch_links", "wrong_touch_links", "wrong_frame",
                                   "wrong_dimensions", "wrong_primitive_type", "missing_primitive",
                                   "still_in_world", "wrong_color", "world_object_moved"])
def test_audit_only_attached_proof_still_refuses_every_non_pose_fault(fault):
    from moveit_msgs.msg import CollisionObject
    scene, attached, geometry = _plain_attached_scene(
        link="jaw" if fault == "wrong_link" else "gripper",
        frame="world" if fault == "wrong_frame" else None)
    if fault == "missing_touch_links":
        attached.touch_links = []
    if fault == "wrong_touch_links":
        attached.touch_links = ["gripper"]
    if fault == "wrong_dimensions":
        attached.object.primitives[-1].dimensions[0] += .01
    if fault == "wrong_primitive_type":
        attached.object.primitives[0].type = 1 if attached.object.primitives[0].type == 3 else 3
    if fault == "missing_primitive":
        attached.object.primitives.pop()
        attached.object.primitive_poses.pop()
    if fault == "still_in_world":
        scene.world.collision_objects.append(CollisionObject(id="plastic_cup"))
    if fault == "wrong_color":
        next(item for item in scene.object_colors if item.id == "plastic_cup").color.r += .5
    if fault == "world_object_moved":
        next(item for item in scene.world.collision_objects if item.id == "table").pose.position.x += .01
    result = _audit_call(scene, geometry)
    assert not result.success, result.evidence["mismatches"]
    assert not any(item == "plastic_cup.pose" for item in result.evidence["mismatches"])


def test_audit_only_option_requires_an_attachment_and_default_stays_strict():
    from so101_demo.control.planning_scene.task_scene import verify_task_scene
    scene, attached, geometry = _plain_attached_scene(shift=(.03, 0., 0.))
    with pytest.raises(ValueError):
        verify_task_scene(scene, geometry, cup_local_pose_audit_only=True)
    strict = _audit_call(scene, geometry, cup_local_pose_audit_only=False)
    assert not strict.success and strict.evidence["mismatches"] == ["plastic_cup.pose"]
    assert "cup_local_pose_audit" not in strict.evidence
