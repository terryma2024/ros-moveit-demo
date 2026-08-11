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


def test_mjcf_uses_reviewed_servo_dynamics_without_changing_geometry_or_ranges() -> None:
    root = ET.parse(MJCF).getroot()
    joint_default = root.find("./default/joint")
    assert joint_default is not None
    assert joint_default.attrib == {
        "damping": "0.60",
        "frictionloss": "0.052",
        "armature": "0.028",
    }

    joints = root.findall("./worldbody//joint")
    assert [(joint.get("name"), joint.get("range")) for joint in joints] == [
        ("1", "-1.91986 1.91986"),
        ("2", "-1.74533 1.74533"),
        ("3", "-1.74533 1.5708"),
        ("4", "-1.65806 1.65806"),
        ("5", "-2.79253 2.79253"),
        ("6", "-0.059600220867817 1.74533"),
    ]

    actuators = root.findall("./actuator/position")
    assert [
        (
            actuator.get("name"),
            actuator.get("joint"),
            actuator.get("kp"),
            actuator.get("kv"),
            actuator.get("forcerange"),
            actuator.get("ctrlrange"),
        )
        for actuator in actuators
    ] == [
        ("1", "1", "998.22", "2.731", "-3.35 3.35", "-1.91986 1.91986"),
        ("2", "2", "998.22", "2.731", "-3.35 3.35", "-1.74533 1.74533"),
        ("3", "3", "998.22", "2.731", "-3.35 3.35", "-1.74533 1.5708"),
        ("4", "4", "998.22", "2.731", "-3.35 3.35", "-1.65806 1.65806"),
        ("5", "5", "998.22", "2.731", "-3.35 3.35", "-2.79253 2.79253"),
        (
            "6",
            "6",
            "998.22",
            "2.731",
            "-3.35 3.35",
            "-0.059600220867817 1.74533",
        ),
    ]

    assert [geom.attrib for geom in root.findall("./worldbody//geom")] == [
        {
            "name": "base_collision",
            "class": "robot_collision",
            "type": "box",
            "pos": "0.0208 0.0180 0.055",
            "size": "0.055 0.065 0.055",
        },
        {
            "name": "shoulder_collision",
            "class": "robot_collision",
            "type": "capsule",
            "fromto": "0 0 0 -0.0303992 -0.0182778 -0.0542",
            "size": "0.032",
        },
        {
            "name": "upper_arm_collision",
            "class": "robot_collision",
            "type": "capsule",
            "fromto": "0 0 0 -0.11257 -0.028 0",
            "size": "0.024",
        },
        {
            "name": "lower_arm_collision",
            "class": "robot_collision",
            "type": "capsule",
            "fromto": "0 0 0 -0.1349 0.0052 0",
            "size": "0.023",
        },
        {
            "name": "wrist_collision",
            "class": "robot_collision",
            "type": "capsule",
            "fromto": "0 0 0 0 -0.0611 0.0181",
            "size": "0.025",
        },
        {
            "name": "gripper_collision",
            "class": "robot_collision",
            "type": "box",
            "pos": "0.0077 0.0001 -0.0234",
            "size": "0.026 0.022 0.032",
        },
        {
            "name": "fixed_fingertip_collision",
            "class": "robot_collision",
            "type": "box",
            "pos": "0 -0.043 0.0189",
            "size": "0.012 0.028 0.010",
        },
        {
            "name": "moving_fingertip_collision",
            "class": "robot_collision",
            "type": "box",
            "pos": "0 -0.030 0.0189",
            "size": "0.012 0.026 0.010",
        },
    ]


def test_robot_mjcf_contains_no_physics_shortcuts() -> None:
    root = ET.parse(MJCF).getroot()
    assert root.find(".//equality") is None
    assert root.find(".//adhesion") is None
    assert root.find('.//body[@mocap="true"]') is None
