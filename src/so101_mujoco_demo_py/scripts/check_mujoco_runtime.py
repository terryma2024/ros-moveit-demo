#!/usr/bin/env python3
"""Fail-closed provenance probe for the qualified mujoco_ros2_control fork."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

OFFICIAL_COMMIT = "35ba8174b62d9560093614f981a3d4b978a96036"
FORK_URL = "git@gitee.com:zjumty/mujoco_ros2_control.git"
FORK_TAG = "so101-0.0.3-r1"
APT_PREFIX = "/opt/ros/jazzy"
PACKAGES = (
    "mujoco_vendor",
    "mujoco_ros2_control",
    "mujoco_ros2_control_msgs",
    "mujoco_ros2_control_plugins",
)
INTERFACES = (
    "mujoco_ros2_control_msgs/msg/ViewerCamera",
    "mujoco_ros2_control_msgs/srv/SetViewerCamera",
    "mujoco_ros2_control_msgs/srv/GetViewerCamera",
    "mujoco_ros2_control_msgs/srv/ResetWorld",
    "mujoco_ros2_control_msgs/srv/SetPause",
    "mujoco_ros2_control_msgs/srv/StepSimulation",
)
EXPECTED_PATHS = {
    "workspace_env": "SO101_WORKSPACE_DIR",
    "workspace_default": "repo_parent",
    "fork_workspace": "ws_mujoco_ros2_control_fork",
    "fork_install": "ws_mujoco_ros2_control_fork/install",
    "project_install": "install",
}


def resolved_prefixes(lock: dict, project_root: Path) -> tuple[Path, Path]:
    paths = lock["paths"]
    workspace = (
        Path(os.environ.get(paths["workspace_env"], project_root.parent)).expanduser().resolve()
    )
    return workspace / paths["fork_install"], project_root / paths["project_install"]


def validate_lock(lock: object) -> list[str]:
    if not isinstance(lock, dict):
        return ["lock must be a mapping"]
    errors: list[str] = []
    for key, value in {
        "schema_version": 3,
        "provider": "gitee_fork_submodule",
        "release": "0.0.3",
        "submodule_path": "third_party/mujoco_ros2_control",
    }.items():
        if lock.get(key) != value:
            errors.append(f"{key} must be {value}")

    fork = lock.get("fork")
    if not isinstance(fork, dict):
        errors.append("fork must be a mapping")
    else:
        for key, value in {"url": FORK_URL, "tag": FORK_TAG}.items():
            if fork.get(key) != value:
                errors.append(f"fork {key} must be {value}")
        commit = fork.get("commit")
        if not isinstance(commit, str) or len(commit) != 40:
            errors.append("fork commit must be a full SHA-1")

    upstream = lock.get("upstream")
    expected_upstream = {
        "url": "https://github.com/ros-controls/mujoco_ros2_control.git",
        "tag": "0.0.3",
        "commit": OFFICIAL_COMMIT,
    }
    if upstream != expected_upstream:
        errors.append("upstream must pin official 0.0.3")

    if lock.get("paths") != EXPECTED_PATHS:
        errors.append("paths must define the relocatable workspace policy")
    if lock.get("source_order") != ["ros_underlay", "fork_overlay", "project_overlay"]:
        errors.append("source_order must place the fork between ROS and project overlays")
    if "package_prefixes" in lock or "project_package_prefixes" in lock:
        errors.append("absolute package prefix mappings are forbidden")

    interface_hashes = lock.get("interface_sha256")
    if not isinstance(interface_hashes, dict) or set(interface_hashes) != set(INTERFACES):
        errors.append("interface_sha256 must pin all reset and viewer camera interfaces")
    elif any(not isinstance(value, str) or len(value) != 64 for value in interface_hashes.values()):
        errors.append("interface_sha256 values must be SHA-256")
    files = lock.get("required_files")
    if not isinstance(files, dict) or not files:
        errors.append("required_files must contain SHA-256 pins")
    elif any(not isinstance(value, str) or len(value) != 64 for value in files.values()):
        errors.append("required_files values must be SHA-256")
    return errors


def run(command: list[str], environment: dict[str, str] | None = None) -> str:
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        env=environment,
    ).stdout.strip()


def ros_environment() -> dict[str, str]:
    environment = dict(os.environ)
    paths = [item for item in environment.get("PYTHONPATH", "").split(os.pathsep) if item]
    for prefix in environment.get("AMENT_PREFIX_PATH", APT_PREFIX).split(os.pathsep):
        candidate = (
            f"{prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        )
        if candidate not in paths:
            paths.append(candidate)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    return environment


def probe(lock: dict, project_root: Path) -> dict[str, object]:
    errors = validate_lock(lock)
    try:
        fork_prefix, _ = resolved_prefixes(lock, project_root)
    except Exception as error:
        errors.append(f"path resolution failed: {type(error).__name__}: {error}")
        fork_prefix = Path("/__invalid_fork_prefix__")
    environment = ros_environment()
    prefixes: dict[str, str] = {}
    interface_hashes: dict[str, str] = {}
    installed_hashes: dict[str, str] = {}
    source: dict[str, object] = {}

    checkout = project_root / str(lock.get("submodule_path", ""))
    try:
        source = {
            "origin": run(["git", "-C", str(checkout), "remote", "get-url", "origin"]),
            "commit": run(["git", "-C", str(checkout), "rev-parse", "HEAD"]),
            "status": run(
                ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"]
            ),
            "tag_commit": run(["git", "-C", str(checkout), "rev-list", "-n", "1", FORK_TAG]),
        }
        if source["origin"] != lock.get("fork", {}).get("url"):
            errors.append("fork origin mismatch")
        if source["commit"] != lock.get("fork", {}).get("commit"):
            errors.append("fork commit mismatch")
        if source["tag_commit"] != source["commit"]:
            errors.append("fork release tag mismatch")
        if source["status"]:
            errors.append("fork source is dirty")
        ancestry = subprocess.run(
            ["git", "-C", str(checkout), "merge-base", "--is-ancestor", OFFICIAL_COMMIT, "HEAD"],
            check=False,
        )
        if ancestry.returncode != 0:
            errors.append("official base ancestry mismatch")
    except Exception as error:
        errors.append(f"source probe failed: {type(error).__name__}: {error}")

    for package in PACKAGES:
        try:
            prefixes[package] = run(["ros2", "pkg", "prefix", package], environment)
            expected = APT_PREFIX if package == "mujoco_vendor" else str(fork_prefix)
            if prefixes[package] != expected:
                errors.append(f"{package} prefix must be {expected}")
        except Exception as error:
            errors.append(f"{package} prefix probe failed: {type(error).__name__}: {error}")

    for interface in INTERFACES:
        try:
            definition = run(["ros2", "interface", "show", interface], environment)
            observed_hash = hashlib.sha256(definition.encode()).hexdigest()
            interface_hashes[interface] = observed_hash
            if observed_hash != lock.get("interface_sha256", {}).get(interface):
                errors.append(f"{interface} hash mismatch")
        except Exception as error:
            errors.append(f"{interface} probe failed: {type(error).__name__}: {error}")

    for filename, expected_hash in lock.get("required_files", {}).items():
        installed_path = fork_prefix / filename
        try:
            observed_hash = hashlib.sha256(installed_path.read_bytes()).hexdigest()
            installed_hashes[filename] = observed_hash
            if observed_hash != expected_hash:
                errors.append(f"required file hash mismatch: {filename}")
        except Exception as error:
            errors.append(
                f"required file probe failed: {installed_path}: {type(error).__name__}: {error}"
            )
    return {
        "provider": lock.get("provider"),
        "release": lock.get("release"),
        "source": source,
        "prefixes": prefixes,
        "interface_sha256": interface_hashes,
        "required_files": installed_hashes,
        "validation_errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    try:
        lock = yaml.safe_load(args.lock.read_text(encoding="utf-8"))
        document = probe(lock, args.lock.resolve().parents[3])
        code = 0 if not document["validation_errors"] else 1
    except Exception as error:
        document = {"validation_errors": [f"probe failed: {type(error).__name__}: {error}"]}
        code = 1
    print(json.dumps(document, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
