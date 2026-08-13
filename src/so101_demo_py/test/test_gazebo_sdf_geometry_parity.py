import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1]


def _numbers(text: str | None) -> tuple[float, ...]:
    assert text is not None
    return tuple(float(value) for value in text.split())


def _pose_xyz_xyzw(text: str | None) -> tuple[float, ...]:
    x, y, z, roll, pitch, yaw = _numbers(text or "0 0 0 0 0 0")
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        x,
        y,
        z,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _dimensions(collision: ET.Element) -> tuple[str, tuple[float, ...]]:
    box = collision.find("geometry/box/size")
    if box is not None:
        return "box", _numbers(box.text)
    cylinder = collision.find("geometry/cylinder")
    assert cylinder is not None
    return "cylinder", (
        float(cylinder.findtext("length", "nan")),
        float(cylinder.findtext("radius", "nan")),
    )


@pytest.mark.parametrize("object_id", ["table", "pedestal", "plastic_cup"])
def test_gazebo_sdf_matches_canonical_task_geometry(object_id: str) -> None:
    from so101_demo.core.task_geometry import load_task_geometry

    contract = load_task_geometry(PACKAGE / "assets/common/geometry-manifest.yaml")
    expected = contract.object(object_id)
    world = ET.parse(PACKAGE / "assets/gazebo/world.sdf").getroot().find("world")
    assert world is not None
    model = world.find(f"model[@name='{object_id}']")
    assert model is not None

    assert _pose_xyz_xyzw(model.findtext("pose")) == pytest.approx(
        expected.pose.values, rel=0.0, abs=1e-9
    )
    collisions = {value.attrib["name"]: value for value in model.findall("link/collision")}
    visuals = {value.attrib["name"]: value for value in model.findall("link/visual")}
    assert tuple(collisions) == tuple(primitive.name for primitive in expected.primitives)

    for primitive in expected.primitives:
        collision = collisions[primitive.name]
        kind, dimensions = _dimensions(collision)
        assert kind == primitive.kind
        assert dimensions == pytest.approx(primitive.dimensions)
        assert _pose_xyz_xyzw(collision.findtext("pose")) == pytest.approx(
            primitive.pose.values, rel=0.0, abs=1e-9
        )
        visual = visuals.get(primitive.name)
        if visual is None and len(expected.primitives) == 1:
            visual = visuals["visual"]
        assert _numbers(visual.findtext("material/diffuse")) == pytest.approx(
            expected.color_rgba
        )
