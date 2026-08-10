from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from so101_mujoco_demo_py.model_parity import compile_mjcf

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MJCF = PACKAGE_ROOT / "mjcf/so101.xml"


def test_committed_mjcf_compiles_with_installed_mujoco() -> None:
    compile_mjcf(MJCF)


def test_mjcf_has_stable_robot_evidence_and_control_names() -> None:
    root = ET.parse(MJCF).getroot()
    assert [joint.get("name") for joint in root.findall("./worldbody//joint")] == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
    ]
    body_names = {body.get("name") for body in root.findall(".//body")}
    assert {"base", "shoulder", "upper_arm", "lower_arm", "wrist", "gripper", "jaw"} <= body_names
    assert root.find('.//site[@name="so101_tcp"]') is not None
    assert root.find('.//geom[@name="fixed_fingertip_collision"]') is not None
    assert root.find('.//geom[@name="moving_fingertip_collision"]') is not None
    assert [actuator.get("name") for actuator in root.findall("./actuator/position")] == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
    ]
    assert root.find('./keyframe/key[@name="home"]') is not None


def test_robot_mjcf_contains_no_physics_shortcuts() -> None:
    root = ET.parse(MJCF).getroot()
    assert root.find(".//equality") is None
    assert root.find(".//adhesion") is None
    assert root.find('.//body[@mocap="true"]') is None
