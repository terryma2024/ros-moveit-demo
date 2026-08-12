import hashlib
from pathlib import Path

import yaml


def _share() -> Path:
    return Path(__file__).parents[1]


def test_backends_share_visual_source_and_keep_collision_separate() -> None:
    manifest = yaml.safe_load(
        (_share() / "assets/common/geometry-manifest.yaml").read_bytes()
    )
    assert manifest["backends"]["mujoco"]["visual_source"] == "assets/common/visual"
    assert manifest["backends"]["gazebo"]["visual_source"] == "assets/common/visual"
    assert manifest["backends"]["mujoco"]["collision_source"] == (
        "assets/mujoco/collision"
    )
    assert manifest["backends"]["gazebo"]["collision_source"] == (
        "assets/gazebo/collision"
    )
    assert manifest["stable_names"] == {
        "tcp": "so101_tcp",
        "task_object": "light_plastic_cup",
    }


def test_manifest_hashes_every_common_visual() -> None:
    share = _share()
    manifest = yaml.safe_load(
        (share / "assets/common/geometry-manifest.yaml").read_bytes()
    )
    entries = manifest["common_visuals"]
    files = sorted((share / "assets/common/visual").glob("*"))
    assert sorted(entries) == [path.name for path in files if path.is_file()]
    for path in files:
        if path.is_file():
            assert entries[path.name]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
            assert entries[path.name]["format"] == path.suffix.removeprefix(".")


def test_task_object_dimensions_scale_and_initial_pose_are_explicit() -> None:
    manifest = yaml.safe_load(
        (_share() / "assets/common/geometry-manifest.yaml").read_bytes()
    )
    cup = manifest["task_objects"]["light_plastic_cup"]
    assert cup["dimensions_m"] == {"outer_radius": 0.04, "height": 0.09}
    assert cup["scale"] == [1.0, 1.0, 1.0]
    assert cup["initial_pose_xyz_m"] == [0.02, -0.28, 0.165]


def test_qualified_mujoco_model_and_scene_bytes_remain_pinned() -> None:
    assets = _share() / "assets/mujoco"
    assert hashlib.sha256((assets / "so101.xml").read_bytes()).hexdigest() == (
        "f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca"
    )
    assert hashlib.sha256((assets / "scene.xml").read_bytes()).hexdigest() == (
        "b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0"
    )
    assert hashlib.sha256((assets / "so101.urdf").read_bytes()).hexdigest() == (
        "0912ddd5521424c4a928f44026f666f2f9faa28931e215a390740263765e79d5"
    )
