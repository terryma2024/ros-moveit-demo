from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config/dependency-lock.yaml"
PROBE = ROOT / "scripts/check_mujoco_runtime.py"
PINNED_COMMIT = "35ba8174b62d9560093614f981a3d4b978a96036"


def load_probe():
    spec = importlib.util.spec_from_file_location("mujoco_runtime_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_pins_exact_apt_release_and_source_fallback() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    assert lock == {
        "schema_version": 1,
        "provider": "apt",
        "release": "0.0.3",
        "prefix": "/opt/ros/jazzy",
        "fallback": {
            "tag": "0.0.3",
            "commit": PINNED_COMMIT,
            "prefix": "/data/work/ws_mujoco_ros2_control_003/install",
        },
        "required_files": {
            "/opt/ros/jazzy/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp": "0eb99bec603f187ad43a57149a846d86c3866fe13f9e59828a17741d3b1bd181",
            "/opt/ros/jazzy/share/mujoco_ros2_control_plugins/cmake/export_mujoco_ros2_control_pluginsExport.cmake": "f8a748c2845ecb535895a2df81c633fbf17aa61df244c7495df833ea1aa9587d",
            "/opt/ros/jazzy/share/mujoco_ros2_control_msgs/srv/ResetWorld.srv": "daa0e9fc5cc21a4c6f6a04d7e77f9010c762d97ba0756f62b38da49b3f37f644",
            "/opt/ros/jazzy/share/mujoco_ros2_control/package.xml": "e9cfedd0d7a8bb3795a4e9287ca9ebcd9c9cc4dc74beaa42be906a49f54ef826",
        },
    }


@pytest.mark.parametrize("floating", ["main", "master", "latest", "HEAD"])
def test_lock_forbids_floating_git_references(floating: str) -> None:
    assert floating not in LOCK.read_text(encoding="utf-8").split()


def test_validator_rejects_wrong_release_prefix_or_commit() -> None:
    probe = load_probe()
    valid = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    assert probe.validate_lock(valid) == []
    for path, value in (
        (("release",), "0.0.4"),
        (("prefix",), "/tmp/wrong"),
        (("fallback", "commit"), "deadbeef"),
    ):
        changed = {**valid, "fallback": dict(valid["fallback"])}
        if len(path) == 1:
            changed[path[0]] = value
        else:
            changed[path[0]][path[1]] = value
        assert probe.validate_lock(changed)


def test_live_probe_reports_exact_packages_interfaces_and_hashes() -> None:
    result = subprocess.run(
        ["python3", str(PROBE), "--lock", str(LOCK)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["provider"] == "apt"
    assert report["release"] == "0.0.3"
    assert report["prefixes"] == {
        name: "/opt/ros/jazzy"
        for name in (
            "mujoco_vendor",
            "mujoco_ros2_control",
            "mujoco_ros2_control_msgs",
            "mujoco_ros2_control_plugins",
        )
    }
    assert set(report["interface_sha256"]) == {
        "mujoco_ros2_control_msgs/srv/ResetWorld",
        "mujoco_ros2_control_msgs/srv/SetPause",
        "mujoco_ros2_control_msgs/srv/StepSimulation",
    }
    assert report["validation_errors"] == []
