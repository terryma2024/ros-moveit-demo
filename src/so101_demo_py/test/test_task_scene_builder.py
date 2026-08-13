from pathlib import Path

PACKAGE = Path(__file__).parents[1]


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
