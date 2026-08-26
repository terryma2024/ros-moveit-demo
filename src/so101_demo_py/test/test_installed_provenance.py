"""Acceptance checks that must run from a clean isolated project overlay."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from so101_demo.runtime.provenance import installed_bundle

EXPECTED_EXECUTABLES = {
    "camera_preset",
    "dynamic_cup_pick_place",
    "fixed_cup_pick_place",
    "gazebo_execute",
    "gazebo_ready",
    "rgbd_cup_pose",
    "run_qualification",
    "scene_setup",
    "so101_mujoco_perception_pick_place",
    "teleop_reset",
    "teleop_workflow",
}
EXPECTED_LAUNCHERS = {
    "so101_gazebo.launch.py",
    "so101_gazebo_pick_place.launch.py",
    "so101_mujoco.launch.py",
    "so101_mujoco_perception_pick_place.launch.py",
    "so101_mujoco_pick_place.launch.py",
}


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_manifest_matches_selected_installed_prefix_and_source() -> None:
    prefix = Path(get_package_prefix("so101_demo_py")).resolve()
    expected = os.environ.get("SO101_DEMO_EXPECTED_PREFIX")
    if expected is not None:
        assert prefix == Path(expected).resolve()
    assert prefix.name == "so101_demo_py"
    assert Path(get_package_share_directory("so101_demo_py")).resolve() == (
        prefix / "share/so101_demo_py"
    )
    manifest = installed_bundle().manifest["inputs"]
    assert manifest["package_prefix"] == str(prefix)
    assert manifest["source_commit"] == os.environ.get("SO101_SOURCE_COMMIT", _git_head())
    dependency = manifest["mujoco_ros2_control"]
    assert dependency["prefix"] != "/opt/ros/jazzy"
    assert dependency["executable"]["sha256"]


def test_final_install_contains_runtime_contract() -> None:
    prefix = Path(get_package_prefix("so101_demo_py")).resolve()
    share = Path(get_package_share_directory("so101_demo_py")).resolve()
    installed_executables = {path.name for path in (prefix / "lib/so101_demo_py").iterdir()}
    assert installed_executables >= EXPECTED_EXECUTABLES
    assert "pick_place" not in installed_executables
    assert {path.name for path in (share / "launch").glob("*.launch.py")} == EXPECTED_LAUNCHERS
    assert (share / "assets/mujoco/scene.xml").is_file()
    assert (share / "assets/gazebo/world.sdf").is_file()
    assert (share / "config/policies/light_cup_wall_pick/v1/mujoco.yaml").is_file()
    assert (share / "config/policies/light_cup_wall_pick/v1/gazebo.yaml").is_file()
    assert (share / "config/policies/light_cup_wall_pick/v1/real_stub.yaml").is_file()
    assert (share / "config/policies/dynamic_cup_pick/v1/gazebo.yaml").is_file()
    assert (share / "config/policies/dynamic_cup_pick/v1/manifest.yaml").is_file()


def test_mujoco_support_plugin_comes_from_the_candidate_project_overlay() -> None:
    demo_prefix = Path(get_package_prefix("so101_demo_py")).resolve()
    support_prefix = Path(get_package_prefix("so101_mujoco_support")).resolve()
    expected_support_prefix = demo_prefix.parent / "so101_mujoco_support"
    library_suffix = ".dylib" if platform.system() == "Darwin" else ".so"

    assert support_prefix == expected_support_prefix
    assert (
        support_prefix
        / "share/so101_mujoco_support/so101_mujoco_plugins.xml"
    ).is_file()
    assert (
        support_prefix / f"lib/libso101_simulation_evidence_plugin{library_suffix}"
    ).is_file()


def test_pytest_collection_is_nonzero() -> None:
    test_root = Path(__file__).resolve().parent
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_root)],
        check=True,
        capture_output=True,
        text=True,
    )
    terminal = completed.stdout.strip().splitlines()[-1]
    assert terminal.endswith("tests collected in 0.00s") or "tests collected" in terminal
    assert not terminal.startswith("no tests collected")
