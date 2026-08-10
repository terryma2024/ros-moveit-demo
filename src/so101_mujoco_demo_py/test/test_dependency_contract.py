from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

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


def test_lock_pins_exact_reset_qualified_provider() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    assert lock["schema_version"] == 2
    assert lock["provider"] == "patched_source"
    assert lock["release"] == "0.0.3"
    assert lock["prefix"] == "/data/work/ws_mujoco_ros2_control_003/install"
    assert lock["upstream"] == {
        "url": "https://github.com/ros-controls/mujoco_ros2_control",
        "tag": "0.0.3",
        "commit": PINNED_COMMIT,
    }
    assert len(lock["required_files"]) == 4


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
        (("upstream", "commit"), "deadbeef"),
    ):
        changed = {**valid, "upstream": dict(valid["upstream"])}
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
    assert report["provider"] == "patched_source"
    assert report["release"] == "0.0.3"
    assert report["prefixes"] == {
        "mujoco_vendor": "/opt/ros/jazzy",
        "mujoco_ros2_control": "/data/work/ws_mujoco_ros2_control_003/install",
        "mujoco_ros2_control_msgs": "/data/work/ws_mujoco_ros2_control_003/install",
        "mujoco_ros2_control_plugins": "/data/work/ws_mujoco_ros2_control_003/install",
    }
    assert set(report["interface_sha256"]) == {
        "mujoco_ros2_control_msgs/srv/ResetWorld",
        "mujoco_ros2_control_msgs/srv/SetPause",
        "mujoco_ros2_control_msgs/srv/StepSimulation",
    }
    assert report["validation_errors"] == []
