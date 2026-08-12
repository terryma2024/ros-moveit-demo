#!/usr/bin/env python3
"""Verify fork source identity and installed reset/viewer-camera runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROS_UNDERLAY = Path("/opt/ros/jazzy")
FORK_PACKAGES = (
    "mujoco_ros2_control",
    "mujoco_ros2_control_msgs",
    "mujoco_ros2_control_plugins",
)
PROJECT_PACKAGES = ("so101_mujoco_support", "so101_mujoco_demo_py")


def resolved_prefixes(
    lock: dict,
    project_root: Path,
    project_install_override: Path | None = None,
) -> tuple[Path, Path]:
    paths = lock["paths"]
    workspace = (
        Path(os.environ.get(paths["workspace_env"], project_root.parent)).expanduser().resolve()
    )
    project_install = (
        project_install_override.expanduser().resolve()
        if project_install_override is not None
        else project_root / paths["project_install"]
    )
    return workspace / paths["fork_install"], project_install


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def fail(message: str) -> None:
    raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument(
        "--project-install",
        type=Path,
        help="explicit project install root for a fresh isolated acceptance build",
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    lock = yaml.safe_load(args.lock.read_text(encoding="utf-8"))
    project_root = args.lock.resolve().parents[3]
    fork_prefix, project_install = resolved_prefixes(
        lock,
        project_root,
        args.project_install,
    )
    source = project_root / lock["submodule_path"]
    fork = lock["fork"]
    upstream = lock["upstream"]

    observed: dict[str, object] = {
        "fork_url": command("git", "-C", str(source), "remote", "get-url", "origin"),
        "fork_commit": command("git", "-C", str(source), "rev-parse", "HEAD"),
        "fork_tag_commit": command("git", "-C", str(source), "rev-list", "-n", "1", fork["tag"]),
        "fork_status": command(
            "git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"
        ),
        "package_prefixes": {},
        "required_files": {},
    }
    if observed["fork_url"] != fork["url"]:
        fail("fork URL mismatch")
    if observed["fork_commit"] != fork["commit"]:
        fail("fork commit mismatch")
    if observed["fork_tag_commit"] != fork["commit"]:
        fail("fork release tag mismatch")
    if observed["fork_status"]:
        fail("fork checkout is dirty")
    ancestry = subprocess.run(
        ["git", "-C", str(source), "merge-base", "--is-ancestor", upstream["commit"], "HEAD"],
        check=False,
    )
    if ancestry.returncode != 0:
        fail("official base ancestry mismatch")

    prefixes = [
        entry for entry in os.environ.get("AMENT_PREFIX_PATH", "").split(os.pathsep) if entry
    ]
    if str(fork_prefix) not in prefixes or str(ROS_UNDERLAY) not in prefixes:
        fail("fork overlay and ROS underlay must both be sourced")
    if prefixes.index(str(fork_prefix)) >= prefixes.index(str(ROS_UNDERLAY)):
        fail("fork overlay does not precede its ROS underlay")

    observed_prefixes: dict[str, str] = {}
    expected_prefixes = {"mujoco_vendor": str(ROS_UNDERLAY)}
    expected_prefixes.update({package: str(fork_prefix) for package in FORK_PACKAGES})
    for package, expected in expected_prefixes.items():
        actual = command("ros2", "pkg", "prefix", package)
        observed_prefixes[package] = actual
        if actual != expected:
            fail(f"package prefix mismatch for {package}: {actual}")
    observed["package_prefixes"] = observed_prefixes

    project_prefixes: dict[str, str] = {}
    for package in PROJECT_PACKAGES:
        expected = str(project_install / package)
        actual = command("ros2", "pkg", "prefix", package)
        project_prefixes[package] = actual
        if actual != expected:
            fail(f"project package prefix mismatch for {package}: {actual}")
    observed["project_package_prefixes"] = project_prefixes

    plugin_header = fork_prefix / (
        "include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp"
    )
    plugin_source = plugin_header.read_text(encoding="utf-8")
    for hook in (
        "virtual void on_reset() {}",
        "virtual void on_pause(bool paused)",
        "virtual void on_state_snapshot(const mjModel* model, const mjData* data, bool paused)",
    ):
        if hook not in plugin_source:
            fail(f"installed plugin base is missing hook: {hook}")
    viewer_header = fork_prefix / "include/mujoco_ros2_control/viewer_camera.hpp"
    if "validate_and_apply_viewer_camera" not in viewer_header.read_text(encoding="utf-8"):
        fail("installed viewer camera API is missing")

    required_files = lock.get("required_files", {})
    if not required_files:
        fail("lock has no installed runtime hashes")
    observed_files: dict[str, str] = {}
    for raw_path, expected_hash in required_files.items():
        actual_hash = sha256(fork_prefix / raw_path)
        observed_files[raw_path] = actual_hash
        if actual_hash != expected_hash:
            fail(f"installed file hash mismatch: {raw_path}")
    observed["required_files"] = observed_files
    print(json.dumps(observed, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        sys.exit(1)
