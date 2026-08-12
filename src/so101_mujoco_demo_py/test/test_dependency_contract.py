from __future__ import annotations

import copy
import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
LOCK = PACKAGE_ROOT / "config/dependency-lock.yaml"
PROBE = PACKAGE_ROOT / "scripts/check_mujoco_runtime.py"
RESET_PROBE = PACKAGE_ROOT / "scripts/check_reset_qualified_runtime.py"
SUBMODULE = PROJECT_ROOT / "third_party/mujoco_ros2_control"
OFFICIAL_COMMIT = "35ba8174b62d9560093614f981a3d4b978a96036"
FORK_URL = "git@gitee.com:zjumty/mujoco_ros2_control.git"
FORK_TAG = "so101-0.0.3-r6"
WORKSPACE_ENV = "SO101_WORKSPACE_DIR"
FORK_WORKSPACE = "ws_mujoco_ros2_control_fork"
CAMERA_INTERFACES = {
    "mujoco_ros2_control_msgs/msg/ViewerCamera",
    "mujoco_ros2_control_msgs/srv/SetViewerCamera",
    "mujoco_ros2_control_msgs/srv/GetViewerCamera",
}
RESET_INTERFACES = {
    "mujoco_ros2_control_msgs/srv/ResetWorld",
    "mujoco_ros2_control_msgs/srv/SetPause",
    "mujoco_ros2_control_msgs/srv/StepSimulation",
}


def load_probe():
    spec = importlib.util.spec_from_file_location("mujoco_runtime_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_reset_probe():
    spec = importlib.util.spec_from_file_location("reset_runtime_probe", RESET_PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_lock() -> dict:
    return yaml.safe_load(LOCK.read_text(encoding="utf-8"))


def test_reset_checker_accepts_an_explicit_fresh_project_install(tmp_path: Path) -> None:
    probe = load_reset_probe()
    lock = load_lock()
    project_install = tmp_path / "acceptance" / "install"

    fork_prefix, resolved_project_install = probe.resolved_prefixes(
        lock,
        PROJECT_ROOT,
        project_install,
    )

    assert fork_prefix == PROJECT_ROOT.parent / FORK_WORKSPACE / "install"
    assert resolved_project_install == project_install.resolve()


def test_lock_pins_exact_qualified_fork() -> None:
    lock = load_lock()
    submodule_head = subprocess.run(
        ["git", "-C", str(SUBMODULE), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    assert lock["schema_version"] == 3
    assert lock["provider"] == "gitee_fork_submodule"
    assert lock["release"] == "0.0.3"
    assert lock["fork"] == {
        "url": FORK_URL,
        "tag": FORK_TAG,
        "commit": submodule_head,
        "policy_behavior_commit": "f42b7b3d77288c2fee750fe53b0258e0a3d18194",
    }
    assert (
        subprocess.run(
            [
                "git",
                "-C",
                str(SUBMODULE),
                "merge-base",
                "--is-ancestor",
                lock["fork"]["policy_behavior_commit"],
                submodule_head,
            ],
            check=False,
        ).returncode
        == 0
    )
    assert lock["upstream"] == {
        "url": "https://github.com/ros-controls/mujoco_ros2_control.git",
        "tag": "0.0.3",
        "commit": OFFICIAL_COMMIT,
    }
    assert lock["submodule_path"] == "third_party/mujoco_ros2_control"
    assert lock["paths"] == {
        "workspace_env": WORKSPACE_ENV,
        "workspace_default": "repo_parent",
        "fork_workspace": FORK_WORKSPACE,
        "fork_install": f"{FORK_WORKSPACE}/install",
        "project_install": "install",
    }
    assert "patch" not in lock
    assert "/data/work/" not in LOCK.read_text(encoding="utf-8")


def test_lock_declares_source_order_prefixes_and_all_interfaces() -> None:
    lock = load_lock()
    assert lock["source_order"] == [
        "ros_underlay",
        "fork_overlay",
        "project_overlay",
    ]
    assert "package_prefixes" not in lock
    assert "project_package_prefixes" not in lock
    assert set(lock["interface_sha256"]) == CAMERA_INTERFACES | RESET_INTERFACES
    assert all(len(value) == 64 for value in lock["interface_sha256"].values())
    assert lock["required_files"]
    assert all(len(value) == 64 for value in lock["required_files"].values())


@pytest.mark.parametrize("floating", ["main", "master", "latest", "HEAD"])
def test_lock_forbids_floating_git_references(floating: str) -> None:
    assert floating not in LOCK.read_text(encoding="utf-8").split()


def test_validator_rejects_wrong_fork_release_path_policy_or_commit() -> None:
    probe = load_probe()
    valid = load_lock()
    assert probe.validate_lock(valid) == []
    for path, value in (
        (("release",), "0.0.4"),
        (("paths", "workspace_env"), "WRONG_WORKSPACE"),
        (("fork", "commit"), "deadbeef"),
        (("upstream", "commit"), "deadbeef"),
    ):
        changed = copy.deepcopy(valid)
        if len(path) == 1:
            changed[path[0]] = value
        else:
            changed[path[0]][path[1]] = value
        assert probe.validate_lock(changed)
