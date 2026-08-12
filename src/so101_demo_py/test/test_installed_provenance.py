"""Acceptance checks that must run from the clean fusion-final overlay."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from so101_demo.runtime.provenance import installed_bundle

EXPECTED_EXECUTABLES = {"gazebo_execute", "pick_place", "run_qualification", "scene_setup"}
EXPECTED_LAUNCHERS = {
    "so101_gazebo.launch.py",
    "so101_gazebo_pick_place.launch.py",
    "so101_mujoco.launch.py",
    "so101_mujoco_pick_place.launch.py",
}


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_manifest_matches_final_installed_prefix_and_source() -> None:
    prefix = Path(get_package_prefix("so101_demo_py")).resolve()
    assert prefix.parent.name == "fusion-final"
    manifest = installed_bundle().manifest["inputs"]
    assert manifest["package_prefix"] == str(prefix)
    assert manifest["source_commit"] == os.environ.get("SO101_SOURCE_COMMIT", _git_head())
    dependency = manifest["mujoco_ros2_control"]
    assert dependency["prefix"] != "/opt/ros/jazzy"
    assert dependency["executable"]["sha256"]


def test_final_install_contains_runtime_contract() -> None:
    prefix = Path(get_package_prefix("so101_demo_py")).resolve()
    share = Path(get_package_share_directory("so101_demo_py")).resolve()
    assert {path.name for path in (prefix / "lib/so101_demo_py").iterdir()} >= EXPECTED_EXECUTABLES
    assert {path.name for path in (share / "launch").glob("*.launch.py")} == EXPECTED_LAUNCHERS
    assert (share / "assets/mujoco/scene.xml").is_file()
    assert (share / "assets/gazebo/world.sdf").is_file()
    assert (share / "config/policies/light_cup_wall_pick/v1/mujoco.yaml").is_file()
    assert (share / "config/policies/light_cup_wall_pick/v1/gazebo.yaml").is_file()
    assert (share / "config/policies/light_cup_wall_pick/v1/real_stub.yaml").is_file()


def test_pytest_collection_is_nonzero() -> None:
    completed = subprocess.run(
        ["python3", "-m", "pytest", "--collect-only", "-q", "src/so101_demo_py/test"],
        check=True,
        capture_output=True,
        text=True,
    )
    terminal = completed.stdout.strip().splitlines()[-1]
    assert terminal.endswith("tests collected in 0.00s") or "tests collected" in terminal
    assert not terminal.startswith("no tests collected")
