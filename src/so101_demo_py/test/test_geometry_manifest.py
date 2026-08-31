import hashlib
from pathlib import Path

import pytest
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


def test_task_scene_is_the_exact_typed_geometry_contract() -> None:
    from so101_demo.core.task_geometry import load_task_geometry

    scene = load_task_geometry(_share() / "assets/common/geometry-manifest.yaml")

    assert scene.frame_id == "world"
    assert scene.object_ids == ("table", "pedestal", "plastic_cup")
    assert scene.primitive_counts == {"table": 1, "pedestal": 1, "plastic_cup": 13}

    table = scene.object("table")
    assert table.pose.values == (0.0, -0.2, 0.1, 0.0, 0.0, 0.0, 1.0)
    assert table.color_rgba == (0.36, 0.24, 0.14, 1.0)
    assert table.primitives[0].kind == "box"
    assert table.primitives[0].dimensions == (0.5, 0.6, 0.04)

    pedestal = scene.object("pedestal")
    assert pedestal.pose.values == (0.0, 0.0, 0.17, 0.0, 0.0, 0.0, 1.0)
    assert pedestal.color_rgba == (0.3, 0.3, 0.32, 1.0)
    assert pedestal.primitives[0].dimensions == (0.18, 0.18, 0.1)

    cup = scene.object("plastic_cup")
    assert cup.pose.values == (0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)
    assert cup.color_rgba == (1.0, 0.55, 0.12, 1.0)
    assert [primitive.kind for primitive in cup.primitives].count("box") == 12
    assert [primitive.kind for primitive in cup.primitives].count("cylinder") == 1
    assert cup.primitives[0].name == "wall_near"
    assert cup.primitives[0].dimensions == (0.020705524, 0.002, 0.088)
    assert cup.primitives[-1].name == "bottom"
    assert cup.primitives[-1].dimensions == (0.002, 0.04)
    assert cup.primitives[-1].pose.values == (
        0.0,
        0.0,
        -0.044,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def test_task_scene_loader_rejects_unknown_fields_and_wrong_counts(tmp_path: Path) -> None:
    from so101_demo.core.task_geometry import GeometryContractError, load_task_geometry

    manifest = yaml.safe_load(
        (_share() / "assets/common/geometry-manifest.yaml").read_bytes()
    )
    manifest["task_scene"]["unexpected"] = True
    invalid = tmp_path / "unknown.yaml"
    invalid.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(GeometryContractError, match="SCENE_MANIFEST_INVALID"):
        load_task_geometry(invalid)

    manifest = yaml.safe_load(
        (_share() / "assets/common/geometry-manifest.yaml").read_bytes()
    )
    manifest["task_scene"]["objects"]["plastic_cup"]["primitives"].pop()
    invalid = tmp_path / "wrong-count.yaml"
    invalid.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(GeometryContractError, match="SCENE_MANIFEST_INVALID"):
        load_task_geometry(invalid)


def test_qualified_mujoco_model_and_scene_bytes_remain_pinned() -> None:
    assets = _share() / "assets/mujoco"
    assert hashlib.sha256((assets / "so101.xml").read_bytes()).hexdigest() == (
        "f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca"
    )
    assert hashlib.sha256((assets / "scene.xml").read_bytes()).hexdigest() == (
        "fec97df90ada01bed12e09110986caac52881312360c5549763dcb2a02d99d9c"
    )
    assert hashlib.sha256((assets / "so101.urdf").read_bytes()).hexdigest() == (
        "73ab5bdd26451778c094a837817c65748b1e8bacd48672e313c941d8ca85f0b2"
    )
