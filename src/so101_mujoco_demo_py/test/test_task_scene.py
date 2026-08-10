from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from so101_mujoco_demo_py.model_parity import compile_mjcf

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENE = PACKAGE_ROOT / "mjcf/scene.xml"
CONFIG = PACKAGE_ROOT / "config/task_scene.yaml"
CHECKER = PACKAGE_ROOT / "scripts/check_task_scene.py"
PROVENANCE = PACKAGE_ROOT / "docs/provenance.json"


def test_task_scene_compiles_with_named_rigid_world_and_keyframes() -> None:
    compile_mjcf(SCENE)
    root = ET.parse(SCENE).getroot()
    assert root.find(".//body[@name='table']") is not None
    cup = root.find(".//body[@name='cup']")
    assert cup is not None
    cup_joint = cup.find("./joint[@name='cup_free_joint']")
    assert cup_joint is not None
    assert cup_joint.attrib["type"] == "free"
    assert float(cup_joint.attrib["damping"]) == 1.0
    assert root.find(".//geom[@name='table_collision']") is not None
    assert root.find(".//geom[@name='cup_collision']") is not None
    include = root.find("./include[@file='so101.xml']")
    assert include is not None
    robot_root = ET.parse(SCENE.parent / include.attrib["file"]).getroot()
    assert robot_root.find(".//key[@name='home']") is not None
    assert root.find(".//key[@name='task_start']") is not None


def test_task_inputs_are_explicitly_uncalibrated() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["schema_version"] == 1
    assert config["calibration_status"] == "UNCALIBRATED"
    assert config["source"] == "MuJoCo initial inputs; not migrated Gazebo/Bullet values"
    assert config["simulation_seconds"] == 10.0
    assert config["finite_state_required"] is True
    assert config["stationary_table_required"] is True
    assert config["stationary_cup_after_settle_required"] is True
    assert config["initial_inputs"]["cup_free_joint_damping"] == 1.0


def test_task_scene_provenance_marks_native_inputs_uncalibrated() -> None:
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    artifacts = {entry["path"]: entry for entry in provenance["independent_artifacts"]}
    assert artifacts["mjcf/scene.xml"] == {
        "path": "mjcf/scene.xml",
        "origin": "independent MuJoCo task scene",
        "calibration_status": "UNCALIBRATED",
    }
    assert artifacts["config/task_scene.yaml"] == {
        "path": "config/task_scene.yaml",
        "origin": "independent MuJoCo task inputs",
        "calibration_status": "UNCALIBRATED",
    }


def test_headless_scene_is_finite_and_stationary_for_ten_seconds() -> None:
    result = subprocess.run(
        ["python3", str(CHECKER), "--config", str(CONFIG)],
        cwd=PACKAGE_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["finite_state"] is True
    assert report["simulation_seconds"] >= 10.0
    assert report["table_dofs"] == 0
    assert report["cup_translation_after_settle_m"] <= 1.0e-5
    assert report["final_two_second_translation_envelope_m"] <= 1.0e-5
    assert report["final_two_second_net_speed_m_per_s"] <= 1.0e-5
