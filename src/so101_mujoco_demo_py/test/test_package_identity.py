from __future__ import annotations

import ast
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "so101_mujoco_demo_py"


def package_xml() -> ET.Element:
    return ET.parse(PACKAGE_ROOT / "package.xml").getroot()


def setup_call() -> ast.Call:
    tree = ast.parse((PACKAGE_ROOT / "setup.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setup"
    ]
    assert len(calls) == 1
    return calls[0]


def keyword(call: ast.Call, name: str) -> ast.AST:
    return next(item.value for item in call.keywords if item.arg == name)


def setup_arguments() -> dict[str, object]:
    captured: dict[str, object] = {}

    def capture_setup(**kwargs: object) -> None:
        captured.update(kwargs)

    with patch("setuptools.setup", capture_setup):
        runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")
    return captured


def test_package_name_and_build_type_are_independent() -> None:
    root = package_xml()
    assert root.findtext("name") == PACKAGE_NAME
    assert root.findtext("export/build_type") == "ament_python"
    assert setup_arguments()["name"] == PACKAGE_NAME


def test_resource_marker_and_python_namespace_exist() -> None:
    assert (PACKAGE_ROOT / "resource" / PACKAGE_NAME).is_file()
    assert (PACKAGE_ROOT / PACKAGE_NAME / "__init__.py").is_file()
    assert (PACKAGE_ROOT / PACKAGE_NAME / "cli.py").is_file()


def test_setup_installs_resource_marker_and_package_manifest() -> None:
    data_files = dict(setup_arguments()["data_files"])
    assert data_files["share/ament_index/resource_index/packages"] == [f"resource/{PACKAGE_NAME}"]
    assert data_files[f"share/{PACKAGE_NAME}"] == ["package.xml"]


def test_console_entry_point_preserves_ros_facing_executable_name() -> None:
    entry_points = ast.literal_eval(keyword(setup_call(), "entry_points"))
    assert entry_points == {
        "console_scripts": [
            "analyze_contact_calibration = so101_mujoco_demo_py.contact_calibration:main",
            "camera_preset = so101_mujoco_demo_py.camera_preset_cli:main",
            "collect_contact_calibration = so101_mujoco_demo_py.contact_calibration_collector:main",
            "pick_place_state_machine = so101_mujoco_demo_py.cli:main",
            "headless_execution = so101_mujoco_demo_py.headless_execution:main",
            "scene_setup = so101_mujoco_demo_py.scene_setup:main",
            "staged_approach = so101_mujoco_demo_py.staged_approach:main",
            "teleop_reset = so101_mujoco_demo_py.teleop_reset:main",
            "teleop_workflow = so101_mujoco_demo_py.teleop_workflow:main",
        ]
    }


def test_metadata_and_imports_have_no_gazebo_dependency() -> None:
    metadata = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PACKAGE_ROOT / "package.xml",
            PACKAGE_ROOT / "setup.py",
            PACKAGE_ROOT / PACKAGE_NAME / "__init__.py",
            PACKAGE_ROOT / PACKAGE_NAME / "cli.py",
        )
    ).lower()
    for forbidden in ("gazebo", "gz_", "ros_gz", "so101_gazebo_demo_py"):
        assert forbidden not in metadata
