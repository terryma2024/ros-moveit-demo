import xml.etree.ElementTree as ET
import math
from pathlib import Path

import yaml


PACKAGE = Path(__file__).parents[1]


def test_light_cup_uses_20g_baseline_friction_profile() -> None:
    object_config = yaml.safe_load(
        (PACKAGE / "config/task_objects/light_plastic_cup.yaml").read_text()
    )
    assert object_config["model"]["mass_kg"] == 0.020
    pads = object_config["fingertip_pads"]
    assert pads["friction_coefficient"] == 1.2
    assert pads["contact_material"]["axial_friction_coefficient"] == 3.0
    assert pads["contact_material"]["transverse_friction_coefficient"] == 1.2

    world = ET.parse(PACKAGE / "worlds/so101_pick_place.sdf").getroot()
    cup = world.find(".//model[@name='plastic_cup']/link")
    assert cup is not None
    assert float(cup.findtext("inertial/mass")) == 0.020
    assert float(cup.findtext("inertial/inertia/ixx")) == 0.0000295
    assert float(cup.findtext("inertial/inertia/iyy")) == 0.0000295
    assert float(cup.findtext("inertial/inertia/izz")) == 0.000032
    walls = [
        collision for collision in cup.findall("collision")
        if collision.get("name", "").startswith("wall")
    ]
    assert len(walls) == 12
    for wall in walls:
        assert float(wall.findtext("surface/friction/ode/mu")) == 1.2
        assert float(wall.findtext("surface/friction/ode/mu2")) == 1.2
        assert float(wall.findtext("surface/friction/bullet/friction")) == 1.2
        assert float(wall.findtext("surface/friction/bullet/friction2")) == 1.2

    prepared = ET.parse(PACKAGE / "models/so101_prepared.sdf").getroot()
    pad_collisions = [
        collision for collision in prepared.findall(".//collision")
        if collision.find("surface/friction/ode/fdir1") is not None
    ]
    assert len(pad_collisions) == 15
    for collision in pad_collisions:
        assert float(collision.findtext("surface/friction/ode/mu")) == 3.0
        assert float(collision.findtext("surface/friction/ode/mu2")) == 1.2
        assert float(collision.findtext("surface/friction/bullet/friction")) == 3.0
        assert float(collision.findtext("surface/friction/bullet/friction2")) == 1.2


def test_table_target_ring_contains_cup_radius_plus_ten_mm_center_tolerance() -> None:
    object_config = yaml.safe_load(
        (PACKAGE / "config/task_objects/light_plastic_cup.yaml").read_text()
    )
    place_xyz = object_config["scene"]["place_pose_xyz_xyzw"][:3]
    radius = object_config["model"]["outer_radius_m"]
    center_tolerance = 0.010
    expected_inner_radius = radius + center_tolerance
    expected_line_width = 0.005

    world = ET.parse(PACKAGE / "worlds/so101_pick_place.sdf").getroot()
    table = world.find(".//model[@name='table']")
    assert table is not None
    table_pose = tuple(float(value) for value in table.findtext("pose").split())
    link = table.find("link[@name='table_top']")
    assert link is not None
    marker = link.find("visual[@name='target_landing_tolerance_ring']")
    assert marker is not None
    assert link.find("collision[@name='target_landing_tolerance_ring']") is None
    marker_pose = tuple(float(value) for value in marker.findtext("pose").split())
    assert math.isclose(table_pose[0] + marker_pose[0], place_xyz[0], abs_tol=1e-9)
    assert math.isclose(table_pose[1] + marker_pose[1], place_xyz[1], abs_tol=1e-9)
    table_surface_z = table_pose[2] + 0.04 / 2.0
    assert 0.0 < table_pose[2] + marker_pose[2] - table_surface_z <= 0.0002
    assert marker.findtext("material/ambient") == "1 0 0 1"
    assert marker.findtext("material/diffuse") == "1 0 0 1"

    uri = marker.findtext("geometry/mesh/uri")
    assert uri == "model://so101_gazebo_demo_py/meshes/target_landing_tolerance_ring.stl"
    mesh = PACKAGE / "meshes/target_landing_tolerance_ring.stl"
    vertices = [
        tuple(float(value) for value in line.split()[1:])
        for line in mesh.read_text().splitlines()
        if line.lstrip().startswith("vertex ")
    ]
    assert len(vertices) >= 64
    assert all(math.isclose(vertex[2], 0.0, abs_tol=1e-12) for vertex in vertices)
    radii = [math.hypot(vertex[0], vertex[1]) for vertex in vertices]
    assert math.isclose(min(radii), expected_inner_radius, abs_tol=1e-9)
    assert math.isclose(max(radii) - min(radii), expected_line_width, abs_tol=1e-9)
