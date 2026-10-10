"""The general MuJoCo plugin file must enable the scene-state publisher.

SimulationEvidencePlugin creates /so101/simulation/scene_state only when
``robot_contact_roots`` is a non-empty list and ``robot_contact_buffer_capacity``
is positive (simulation_evidence_plugin.cpp). The general release preflight
consumes those frames, so the file the general launch loads has to declare both.
"""
from xml.etree import ElementTree

import yaml
from paths import PACKAGE_ROOT


def _parameters(relative: str) -> dict:
    return yaml.safe_load((PACKAGE_ROOT / relative).read_bytes())["/**"]["ros__parameters"]


def test_general_plugin_file_declares_the_scene_publisher_guard() -> None:
    parameters = _parameters("config/mujoco/mujoco_plugins.yaml")
    roots = parameters.get("robot_contact_roots")
    assert isinstance(roots, list) and roots
    assert all(isinstance(root, str) and root for root in roots)
    capacity = parameters.get("robot_contact_buffer_capacity")
    assert isinstance(capacity, int) and capacity > 0


def test_general_plugin_roots_match_the_other_profile_and_exist_in_the_model() -> None:
    general = _parameters("config/mujoco/mujoco_plugins.yaml")
    other = _parameters("config/mujoco/act/mujoco_plugins.yaml")
    assert general.get("robot_contact_roots") == other["robot_contact_roots"]
    assert general.get("robot_contact_buffer_capacity") == other["robot_contact_buffer_capacity"]
    bodies = {
        element.attrib.get("name")
        for element in ElementTree.parse(PACKAGE_ROOT / "assets/mujoco/so101.xml").iter("body")
    }
    assert set(general["robot_contact_roots"]) <= bodies
