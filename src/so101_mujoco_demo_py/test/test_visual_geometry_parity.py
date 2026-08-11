from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
URDF = PACKAGE_ROOT / "urdf/so101.urdf"
ROBOT_MJCF = PACKAGE_ROOT / "mjcf/so101.xml"
SCENE_MJCF = PACKAGE_ROOT / "mjcf/scene.xml"
PLUGINS = PACKAGE_ROOT / "config/mujoco_plugins.yaml"


def _numbers(value: str | None, size: int) -> tuple[float, ...]:
    values = tuple(float(item) for item in (value or " ".join("0" for _ in range(size))).split())
    assert len(values) == size
    return values


def _rounded(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(value, 8) for value in values)


def _rpy_quaternion(rpy: tuple[float, float, float]) -> tuple[float, ...]:
    """Return wxyz for the URDF-fixed Rz(yaw) * Ry(pitch) * Rx(roll)."""
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        cy * cp * cr + sy * sp * sr,
        cy * cp * sr - sy * sp * cr,
        sy * cp * sr + cy * sp * cr,
        sy * cp * cr - cy * sp * sr,
    )


def _canonical_quaternion(values: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    normalized = tuple(value / norm for value in values)
    if next((value for value in normalized if abs(value) > 1.0e-12), 1.0) < 0.0:
        normalized = tuple(-value for value in normalized)
    return _rounded(normalized)


def _urdf_instances(link: ET.Element, role: str) -> Counter[tuple[object, ...]]:
    instances: Counter[tuple[object, ...]] = Counter()
    for instance in link.findall(f"./{role}"):
        origin = instance.find("./origin")
        mesh = instance.find("./geometry/mesh")
        assert origin is not None and mesh is not None
        filename = Path(mesh.attrib["filename"]).name
        material = instance.find("./material")
        instances[
            (
                filename,
                _rounded(_numbers(origin.get("xyz"), 3)),
                _canonical_quaternion(_rpy_quaternion(_numbers(origin.get("rpy"), 3))),
                material.get("name") if material is not None else None,
            )
        ] += 1
    return instances


def _mjcf_instances(
    body: ET.Element, role: str, assets: dict[str, str]
) -> Counter[tuple[object, ...]]:
    instances: Counter[tuple[object, ...]] = Counter()
    for geom in body.findall(f"./geom[@class='robot_{role}']"):
        mesh_name = geom.get("mesh")
        assert mesh_name in assets
        assert geom.get("euler") is None, (
            f"{geom.get('name')} must not rely on MJCF Euler semantics"
        )
        assert geom.get("quat") is not None, f"{geom.get('name')} must use an explicit quaternion"
        instances[
            (
                Path(assets[mesh_name]).name,
                _rounded(_numbers(geom.get("pos"), 3)),
                _canonical_quaternion(_numbers(geom.get("quat"), 4)),
                geom.get("material") if role == "visual" else None,
            )
        ] += 1
    return instances


def test_each_robot_body_matches_frozen_urdf_visual_and_collision_instances() -> None:
    urdf = ET.parse(URDF).getroot()
    mjcf = ET.parse(ROBOT_MJCF).getroot()
    assets = {mesh.attrib["name"]: mesh.attrib["file"] for mesh in mjcf.findall("./asset/mesh")}
    materials = {
        material.attrib["name"]: _rounded(_numbers(material.get("rgba"), 4))
        for material in mjcf.findall("./asset/material")
    }
    urdf_materials = {
        material.attrib["name"]: _rounded(_numbers(material.find("./color").get("rgba"), 4))
        for material in urdf.findall("./material")
    }

    for link in urdf.findall("./link"):
        if link.get("name") in {"world", "so101_tcp"}:
            continue
        body = mjcf.find(f".//body[@name='{link.get('name')}']")
        assert body is not None, f"missing MJCF body {link.get('name')}"
        assert _mjcf_instances(body, "visual", assets) == _urdf_instances(link, "visual")
        assert _mjcf_instances(body, "collision", assets) == _urdf_instances(link, "collision")

    assert materials == urdf_materials


def test_every_robot_body_joint_transform_matches_urdf_rotation_matrix() -> None:
    urdf = ET.parse(URDF).getroot()
    mjcf = ET.parse(ROBOT_MJCF).getroot()
    for joint in urdf.findall("./joint"):
        child = joint.find("./child")
        origin = joint.find("./origin")
        assert child is not None and origin is not None
        child_name = child.get("link")
        if child_name == "so101_tcp":
            continue
        body = mjcf.find(f".//body[@name='{child_name}']")
        assert body is not None, f"missing MJCF body {child_name}"
        assert _numbers(body.get("pos"), 3) == pytest.approx(
            _numbers(origin.get("xyz"), 3), abs=1.0e-8
        )
        actual = _canonical_quaternion(
            _numbers(body.get("quat"), 4) if body.get("quat") is not None else (1.0, 0.0, 0.0, 0.0)
        )
        expected = _canonical_quaternion(_rpy_quaternion(_numbers(origin.get("rpy"), 3)))
        assert actual == pytest.approx(expected, abs=1.0e-8), child_name


def test_robot_mesh_assets_exist_and_visual_collision_filters_are_separate() -> None:
    root = ET.parse(ROBOT_MJCF).getroot()
    mesh_assets = root.findall("./asset/mesh")
    assert mesh_assets
    for mesh in mesh_assets:
        assert (ROBOT_MJCF.parent / mesh.attrib["file"]).is_file(), mesh.attrib["file"]

    visual_default = root.find("./default/default[@class='robot_visual']/geom")
    collision_default = root.find("./default/default[@class='robot_collision']/geom")
    assert visual_default is not None
    assert visual_default.get("type") == "mesh"
    assert visual_default.get("group") == "0"
    assert visual_default.get("contype") == "0"
    assert visual_default.get("conaffinity") == "0"
    assert collision_default is not None
    assert collision_default.get("type") == "mesh"
    assert collision_default.get("group") == "3"
    assert int(collision_default.get("contype", "0")) != 0
    assert int(collision_default.get("conaffinity", "0")) != 0


def test_fingertip_contact_sets_cover_every_authoritative_gripper_and_jaw_collision() -> None:
    urdf = ET.parse(URDF).getroot()
    parameters = yaml.safe_load(PLUGINS.read_text(encoding="utf-8"))["/**"]["ros__parameters"]

    expected_left = {
        collision.attrib["name"] for collision in urdf.findall("./link[@name='gripper']/collision")
    }
    expected_right = {
        collision.attrib["name"] for collision in urdf.findall("./link[@name='jaw']/collision")
    }
    assert len(expected_left) == 14
    assert len(expected_right) == 14
    assert set(parameters["left_fingertip_geoms"]) == expected_left
    assert set(parameters["right_fingertip_geoms"]) == expected_right
    assert not (
        {"fixed_fingertip_collision", "moving_fingertip_collision"}
        & (expected_left | expected_right)
    )


def test_mujoco_fingertip_material_preserves_gazebo_axial_grip_friction() -> None:
    root = ET.parse(ROBOT_MJCF).getroot()
    fingertip_collisions = [
        geom
        for geom in root.findall("./worldbody//geom")
        if "fingertip_pad_collision_" in geom.get("name", "")
    ]
    assert len(fingertip_collisions) == 13
    assert {_numbers(geom.get("friction"), 3) for geom in fingertip_collisions} == {
        (3.0, 0.01, 0.001)
    }


def test_mujoco_fingertip_material_preserves_gazebo_contact_solver_contract() -> None:
    root = ET.parse(ROBOT_MJCF).getroot()
    fingertip_collisions = [
        geom
        for geom in root.findall("./worldbody//geom")
        if "fingertip_pad_collision_" in geom.get("name", "")
    ]
    assert len(fingertip_collisions) == 13

    # MuJoCo's negative direct format is (-stiffness, -damping).  Keep this
    # explicit on each TPU pad so it cannot silently fall back to the default
    # soft contact when the robot MJCF is included by another scene.
    assert {_numbers(geom.get("solref"), 2) for geom in fingertip_collisions} == {
        (-1_000_000.0, -100.0)
    }


def test_mujoco_scene_enables_noslip_post_solver_for_physical_grasp() -> None:
    root = ET.parse(SCENE_MJCF).getroot()
    option = root.find("./option")
    assert option is not None

    # The default is zero, which disables MuJoCo's post-solver suppression of
    # friction-dimension drift.  The physical grasp path requires an explicit,
    # bounded iteration budget so a slowly lifted cup does not creep through
    # otherwise valid bilateral fingertip contacts.
    assert int(option.get("noslip_iterations", "0")) == 10


WALL_NAMES = (
    "wall_near",
    "wall_01",
    "wall_02",
    "wall_03",
    "wall_04",
    "wall_05",
    "wall_opposite",
    "wall_07",
    "wall_08",
    "wall_09",
    "wall_10",
    "wall_11",
)
WALL_POSES = (
    (0.0, 0.039, 0.001, 0.0),
    (0.0195, 0.033775, 0.001, -0.523598776),
    (0.033775, 0.0195, 0.001, -1.047197551),
    (0.039, 0.0, 0.001, -1.570796327),
    (0.033775, -0.0195, 0.001, -2.094395102),
    (0.0195, -0.033775, 0.001, -2.617993878),
    (0.0, -0.039, 0.001, math.pi),
    (-0.0195, -0.033775, 0.001, 2.617993878),
    (-0.033775, -0.0195, 0.001, 2.094395102),
    (-0.039, 0.0, 0.001, 1.570796327),
    (-0.033775, 0.0195, 0.001, 1.047197551),
    (-0.0195, 0.033775, 0.001, 0.523598776),
)


def _cup_parts(cup: ET.Element, role: str) -> dict[str, ET.Element]:
    suffix = f"_{role}"
    return {
        geom.attrib["name"].removesuffix(suffix): geom
        for geom in cup.findall(f"./geom[@class='cup_{role}']")
    }


@pytest.mark.parametrize(
    ("body_name", "expected_pos", "expected_full_size"),
    (
        ("base_pedestal", (0.0, 0.0, 0.17), (0.18, 0.18, 0.10)),
        ("table", (0.0, -0.20, 0.10), (0.50, 0.60, 0.04)),
    ),
)
def test_static_gazebo_scene_geometry_has_paired_visual_and_collision(
    body_name: str,
    expected_pos: tuple[float, float, float],
    expected_full_size: tuple[float, float, float],
) -> None:
    root = ET.parse(SCENE_MJCF).getroot()
    body = root.find(f"./worldbody/body[@name='{body_name}']")
    assert body is not None
    assert _numbers(body.get("pos"), 3) == pytest.approx(expected_pos)

    visual = body.find(f"./geom[@name='{body_name}_visual']")
    collision = body.find(f"./geom[@name='{body_name}_collision']")
    assert visual is not None
    assert collision is not None
    expected_half_size = tuple(value / 2.0 for value in expected_full_size)
    for geom in (visual, collision):
        assert geom.get("type") == "box"
        assert _numbers(geom.get("size"), 3) == pytest.approx(expected_half_size)
        assert _numbers(geom.get("pos", "0 0 0"), 3) == pytest.approx((0.0, 0.0, 0.0))
    assert visual.get("contype") == "0"
    assert visual.get("conaffinity") == "0"
    assert int(collision.get("contype", "0")) != 0
    assert int(collision.get("conaffinity", "0")) != 0


def test_plastic_cup_is_open_gazebo_parity_compound_with_paired_parts() -> None:
    root = ET.parse(SCENE_MJCF).getroot()
    cup = root.find(".//body[@name='plastic_cup']")
    assert cup is not None
    inertial = cup.find("./inertial")
    assert inertial is not None
    assert float(inertial.attrib["mass"]) == pytest.approx(0.020)
    assert _numbers(inertial.get("diaginertia"), 3) == pytest.approx(
        (0.0000295, 0.0000295, 0.0000320)
    )
    assert _numbers(cup.get("pos"), 3) == pytest.approx((0.02, -0.28, 0.165))

    visual_default = root.find("./default/default[@class='cup_visual']/geom")
    collision_default = root.find("./default/default[@class='cup_collision']/geom")
    assert visual_default is not None
    assert visual_default.get("group") == "0"
    assert visual_default.get("contype") == "0"
    assert visual_default.get("conaffinity") == "0"
    assert visual_default.get("material") == "cup_orange"
    assert collision_default is not None
    assert int(collision_default.get("contype", "0")) != 0
    assert int(collision_default.get("conaffinity", "0")) != 0
    assert _numbers(collision_default.get("friction"), 3) == pytest.approx((1.2, 0.01, 0.001))

    visuals = _cup_parts(cup, "visual")
    collisions = _cup_parts(cup, "collision")
    assert set(visuals) == set(collisions) == {*WALL_NAMES, "bottom"}
    for name, (x, y, z, yaw) in zip(WALL_NAMES, WALL_POSES, strict=True):
        for parts in (visuals, collisions):
            geom = parts[name]
            assert geom.get("type") == "box"
            assert _numbers(geom.get("size"), 3) == pytest.approx(
                (0.020705524 / 2.0, 0.002 / 2.0, 0.088 / 2.0)
            )
            assert _numbers(geom.get("pos"), 3) == pytest.approx((x, y, z))
            assert _numbers(geom.get("euler"), 3) == pytest.approx((0.0, 0.0, yaw))

    for parts in (visuals, collisions):
        bottom = parts["bottom"]
        assert bottom.get("type") == "cylinder"
        assert _numbers(bottom.get("size"), 2) == pytest.approx((0.040, 0.002 / 2.0))
        assert _numbers(bottom.get("pos"), 3) == pytest.approx((0.0, 0.0, -0.044))

    assert len(visuals) == len(collisions) == 13
    assert not any("top" in name or "lid" in name for name in visuals | collisions)

    task_start = root.find("./keyframe/key[@name='task_start']")
    assert task_start is not None
    qpos = _numbers(task_start.get("qpos"), 13)
    assert qpos[6:9] == pytest.approx((0.02, -0.28, 0.165))
