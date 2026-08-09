import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


PACKAGE = Path(__file__).parents[1]


def test_light_cup_uses_10g_high_friction_profile() -> None:
    object_config = yaml.safe_load(
        (PACKAGE / "config/task_objects/light_plastic_cup.yaml").read_text()
    )
    assert object_config["model"]["mass_kg"] == 0.010
    pads = object_config["fingertip_pads"]
    assert pads["friction_coefficient"] == 2.0
    assert pads["contact_material"]["axial_friction_coefficient"] == 3.0
    assert pads["contact_material"]["transverse_friction_coefficient"] == 2.0

    world = ET.parse(PACKAGE / "worlds/so101_pick_place.sdf").getroot()
    cup = world.find(".//model[@name='plastic_cup']/link")
    assert cup is not None
    assert float(cup.findtext("inertial/mass")) == 0.010
    assert float(cup.findtext("inertial/inertia/ixx")) == 0.00001475
    assert float(cup.findtext("inertial/inertia/iyy")) == 0.00001475
    assert float(cup.findtext("inertial/inertia/izz")) == 0.000016
    walls = [
        collision for collision in cup.findall("collision")
        if collision.get("name", "").startswith("wall")
    ]
    assert len(walls) == 12
    for wall in walls:
        assert float(wall.findtext("surface/friction/ode/mu")) == 2.0
        assert float(wall.findtext("surface/friction/ode/mu2")) == 2.0
        assert float(wall.findtext("surface/friction/bullet/friction")) == 2.0
        assert float(wall.findtext("surface/friction/bullet/friction2")) == 2.0

    prepared = ET.parse(PACKAGE / "models/so101_prepared.sdf").getroot()
    pad_collisions = [
        collision for collision in prepared.findall(".//collision")
        if collision.find("surface/friction/ode/fdir1") is not None
    ]
    assert len(pad_collisions) == 15
    for collision in pad_collisions:
        assert float(collision.findtext("surface/friction/ode/mu")) == 3.0
        assert float(collision.findtext("surface/friction/ode/mu2")) == 2.0
        assert float(collision.findtext("surface/friction/bullet/friction")) == 3.0
        assert float(collision.findtext("surface/friction/bullet/friction2")) == 2.0
