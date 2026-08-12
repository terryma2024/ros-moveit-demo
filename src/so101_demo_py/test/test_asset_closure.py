import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

LEGACY_NAMES = ("so101_mujoco_demo_py", "so101_gazebo_demo_py")
TEXT_SUFFIXES = {".xml", ".sdf", ".xacro", ".urdf", ".yaml", ".json", ".md"}


def _share(request) -> Path:
    installed = request.config.getoption("--installed-share")
    return installed or Path(__file__).parents[1]


def test_assets_have_backend_entrypoints_and_resolve_locally(request) -> None:
    share = _share(request)
    required = (
        "assets/mujoco/scene.xml",
        "assets/mujoco/so101.xml",
        "assets/gazebo/world.sdf",
        "assets/gazebo/so101_prepared.sdf",
        "assets/gazebo/urdf/so101.urdf.xacro",
    )
    assert all((share / relative).is_file() for relative in required)


def test_installed_assets_do_not_reference_legacy_packages(request) -> None:
    share = _share(request)
    violations = []
    for path in (share / "assets").rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            if any(name in text for name in LEGACY_NAMES):
                violations.append(str(path.relative_to(share)))
    assert violations == []


def test_mujoco_and_gazebo_collision_trees_are_nonempty_and_distinct(request) -> None:
    share = _share(request)
    mujoco = {path.name for path in (share / "assets/mujoco/collision").rglob("*.stl")}
    gazebo = {
        str(path.relative_to(share / "assets/gazebo/collision"))
        for path in (share / "assets/gazebo/collision").rglob("*.stl")
    }
    assert len(mujoco) >= 27
    assert len(gazebo) > len(mujoco)
    assert mujoco != gazebo


def test_mujoco_references_common_visuals_and_backend_collision_assets(request) -> None:
    share = _share(request)
    assets = share / "assets"
    manifest = yaml.safe_load(
        (assets / "common/geometry-manifest.yaml").read_bytes()
    )
    visual_names = set(manifest["common_visuals"])
    collision_names = {
        path.name for path in (assets / "mujoco/collision").glob("*.stl")
    }

    mjcf = ET.parse(assets / "mujoco/so101.xml")
    mjcf_files = {
        mesh.attrib["file"] for mesh in mjcf.findall(".//mesh[@file]")
    }
    assert mjcf_files == {
        *(f"../common/visual/{name}" for name in visual_names),
        *(f"collision/{name}" for name in collision_names),
    }

    scene = ET.parse(assets / "mujoco/scene.xml")
    assert {
        mesh.attrib["file"] for mesh in scene.findall(".//mesh[@file]")
    } == {"../common/task_objects/target_landing_tolerance_ring.obj"}

    urdf = ET.parse(assets / "mujoco/so101.urdf")
    urdf_files = {
        mesh.attrib["filename"] for mesh in urdf.findall(".//mesh[@filename]")
    }
    assert urdf_files == {
        *(
            f"package://so101_demo_py/assets/common/visual/{name}"
            for name in visual_names
        ),
        *(
            f"package://so101_demo_py/assets/mujoco/collision/{name}"
            for name in collision_names
        ),
    }
    assert not (assets / "mujoco/assets").exists()
