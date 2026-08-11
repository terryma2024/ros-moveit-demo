import pytest
from moveit_msgs.msg import CollisionObject
from shape_msgs.msg import SolidPrimitive

from so101_mujoco_demo_py.scene_setup import (
    EXPECTED_PRIMITIVE_COUNTS,
    REQUIRED_WORLD_OBJECTS,
    make_task_scene,
    scene_contains_required_objects,
    scene_matches_task_geometry,
    task_scene_readback,
)


def test_scene_setup_reproduces_task_world_geometry_and_colors() -> None:
    scene = make_task_scene()
    objects = {item.id: item for item in scene.world.collision_objects}
    colors = {item.id: item.color for item in scene.object_colors}

    assert set(objects) == REQUIRED_WORLD_OBJECTS
    assert set(colors) == REQUIRED_WORLD_OBJECTS
    assert objects["table"].primitives[0].type == SolidPrimitive.BOX
    assert objects["table"].primitives[0].dimensions == pytest.approx([0.50, 0.60, 0.04])
    table_pose = objects["table"].primitive_poses[0]
    assert [table_pose.position.x, table_pose.position.y, table_pose.position.z] == (
        pytest.approx([0.0, -0.20, 0.10])
    )
    assert objects["pedestal"].primitives[0].dimensions == pytest.approx([0.18, 0.18, 0.10])
    pedestal_pose = objects["pedestal"].primitive_poses[0]
    assert [
        pedestal_pose.position.x,
        pedestal_pose.position.y,
        pedestal_pose.position.z,
    ] == pytest.approx([0.0, 0.0, 0.17])


def test_scene_setup_removes_stale_attached_cup_before_restoring_world_cup() -> None:
    scene = make_task_scene()

    assert scene.robot_state.is_diff
    assert len(scene.robot_state.attached_collision_objects) == 1
    removal = scene.robot_state.attached_collision_objects[0]
    assert removal.object.id == "plastic_cup"
    assert removal.object.operation == CollisionObject.REMOVE


def test_cup_is_the_open_compound_geometry_not_a_solid_proxy() -> None:
    cup = next(
        item for item in make_task_scene().world.collision_objects if item.id == "plastic_cup"
    )
    assert len(cup.primitives) == 13
    assert all(item.type == SolidPrimitive.BOX for item in cup.primitives[:12])
    assert all(
        item.dimensions == pytest.approx([0.020705524, 0.002, 0.088])
        for item in cup.primitives[:12]
    )
    assert cup.primitives[-1].type == SolidPrimitive.CYLINDER
    assert cup.primitives[-1].dimensions == pytest.approx([0.002, 0.040])
    assert scene_contains_required_objects(["table", "pedestal", "plastic_cup"])
    assert not scene_contains_required_objects(["table", "plastic_cup"])


def test_runtime_readback_contract_requires_geometry_and_colors() -> None:
    scene = make_task_scene()

    primitive_counts, color_ids = task_scene_readback(scene)

    assert primitive_counts == EXPECTED_PRIMITIVE_COUNTS
    assert color_ids == REQUIRED_WORLD_OBJECTS
    assert scene_matches_task_geometry(scene)

    scene.world.collision_objects[-1].primitives.pop()
    assert not scene_matches_task_geometry(scene)
