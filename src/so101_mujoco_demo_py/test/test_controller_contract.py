from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = PACKAGE_ROOT / "config/ros2_controllers.yaml"
PLUGINS = PACKAGE_ROOT / "config/mujoco_plugins.yaml"
URDF = PACKAGE_ROOT / "urdf/so101.urdf"


def test_controller_names_and_six_position_interfaces_match_moveit_contract() -> None:
    document = yaml.safe_load(CONTROLLERS.read_text(encoding="utf-8"))
    manager = document["controller_manager"]["ros__parameters"]
    assert manager["update_rate"] == 500
    assert manager["joint_state_broadcaster"]["type"] == (
        "joint_state_broadcaster/JointStateBroadcaster"
    )
    assert manager["arm_controller"]["type"] == (
        "joint_trajectory_controller/JointTrajectoryController"
    )
    assert manager["gripper_controller"]["type"] == (
        "joint_trajectory_controller/JointTrajectoryController"
    )
    assert document["arm_controller"]["ros__parameters"]["joints"] == ["1", "2", "3", "4", "5"]
    assert document["gripper_controller"]["ros__parameters"]["joints"] == ["6"]
    for controller in ("arm_controller", "gripper_controller"):
        parameters = document[controller]["ros__parameters"]
        assert parameters["command_interfaces"] == ["position"]
        assert parameters["state_interfaces"] == ["position", "velocity"]
        assert parameters["open_loop_control"] is False


def test_atomic_plugin_configuration_uses_stable_scene_names() -> None:
    document = yaml.safe_load(PLUGINS.read_text(encoding="utf-8"))
    parameters = document["/**"]["ros__parameters"]
    plugin = parameters["mujoco_plugins"]["simulation_evidence"]
    assert plugin["type"] == "so101_mujoco_support/SimulationEvidencePlugin"
    assert parameters["object_body"] == "cup"
    assert parameters["left_fingertip_geom"] == "fixed_fingertip_collision"
    assert parameters["right_fingertip_geom"] == "moving_fingertip_collision"
    assert parameters["other_contact_geoms"] == ["table_collision"]
    assert parameters["topic"] == "/so101/simulation/evidence"


def test_urdf_uses_a_launch_resolved_package_local_scene_token() -> None:
    root = ET.parse(URDF).getroot()
    hardware = root.find("./ros2_control/hardware")
    assert hardware is not None
    parameters = {entry.attrib["name"]: entry.text for entry in hardware.findall("param")}
    assert parameters["mujoco_model"] == "@SO101_MUJOCO_SCENE@"
    assert parameters["headless"] == "@SO101_MUJOCO_HEADLESS@"
    joints = root.findall("./ros2_control/joint")
    assert [joint.attrib["name"] for joint in joints] == ["1", "2", "3", "4", "5", "6"]
    assert all(joint.find("./command_interface[@name='position']") is not None for joint in joints)
