"""Qualified MuJoCo compatibility surface for the shared task-scene contract."""

from collections.abc import Sequence
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from so101_demo.control.planning_scene.task_scene import (
    make_task_scene as _make_task_scene,
)
from so101_demo.control.planning_scene.task_scene import (
    verify_task_scene,
)
from so101_demo.core.task_geometry import load_task_geometry

REQUIRED_WORLD_OBJECTS = frozenset({"table", "pedestal", "plastic_cup"})
EXPECTED_PRIMITIVE_COUNTS = {"table": 1, "pedestal": 1, "plastic_cup": 13}


def _geometry():
    share = Path(get_package_share_directory("so101_demo_py"))
    return load_task_geometry(share / "assets/common/geometry-manifest.yaml")


def task_collision_objects() -> list:
    return list(_make_task_scene(_geometry()).world.collision_objects)


def task_object_colors() -> list:
    return list(_make_task_scene(_geometry()).object_colors)


def make_task_scene():
    return _make_task_scene(_geometry())


def scene_contains_required_objects(object_ids: Sequence[str]) -> bool:
    return REQUIRED_WORLD_OBJECTS <= set(object_ids)


def task_scene_readback(scene) -> tuple[dict[str, int], set[str]]:
    primitive_counts = {
        collision_object.id: len(collision_object.primitives)
        for collision_object in scene.world.collision_objects
    }
    color_ids = {object_color.id for object_color in scene.object_colors}
    return primitive_counts, color_ids


def scene_matches_task_geometry(scene) -> bool:
    return verify_task_scene(scene, _geometry()).success


def main() -> int:
    from so101_demo.cli.scene_setup import main as shared_main

    return shared_main(["--backend", "mujoco"])
