#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def fail(message: str) -> None:
    raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    lock = yaml.safe_load(args.lock.read_text(encoding="utf-8"))
    package_root = args.lock.resolve().parents[1]
    source = Path(lock["source_checkout"])
    patch = package_root / lock["patch"]["path"]

    observed: dict[str, object] = {
        "upstream_url": command("git", "-C", str(source), "remote", "get-url", "origin"),
        "upstream_commit": command("git", "-C", str(source), "rev-parse", "HEAD"),
        "upstream_tags": command(
            "git", "-C", str(source), "tag", "--points-at", "HEAD"
        ).splitlines(),
        "applied_patch_sha256": hashlib.sha256(
            subprocess.run(
                ["git", "-C", str(source), "diff", "HEAD", "--binary", "--unified=0"],
                check=True,
                capture_output=True,
            ).stdout
        ).hexdigest(),
        "patch_sha256": sha256(patch),
        "package_prefixes": {},
        "required_files": {},
    }
    expected_upstream = lock["upstream"]
    if observed["upstream_url"] != expected_upstream["url"]:
        fail("upstream URL mismatch")
    if observed["upstream_commit"] != expected_upstream["commit"]:
        fail("upstream commit mismatch")
    if expected_upstream["tag"] not in observed["upstream_tags"]:
        fail("stable tag is not attached to pinned commit")
    if observed["patch_sha256"] != lock["patch"]["sha256"]:
        fail("patch SHA-256 mismatch")
    if observed["applied_patch_sha256"] != lock["patch"]["sha256"]:
        fail("dependency checkout does not contain exactly the approved patch")

    prefixes = os.environ.get("AMENT_PREFIX_PATH", "").split(os.pathsep)
    expected_order = [
        "/opt/ros/jazzy",
        lock["prefix"],
    ]
    positions = [prefixes.index(item) for item in expected_order if item in prefixes]
    if len(positions) != 2 or positions[1] >= positions[0]:
        fail("dependency overlay does not precede its ROS underlay in AMENT_PREFIX_PATH")

    observed_prefixes: dict[str, str] = {}
    for package, expected in lock["package_prefixes"].items():
        actual = command("ros2", "pkg", "prefix", package)
        observed_prefixes[package] = actual
        if actual != expected:
            fail(f"package prefix mismatch for {package}: {actual}")
    observed["package_prefixes"] = observed_prefixes
    project_prefixes: dict[str, str] = {}
    for package, expected in lock["project_package_prefixes"].items():
        actual = command("ros2", "pkg", "prefix", package)
        project_prefixes[package] = actual
        if actual != expected:
            fail(f"project package prefix mismatch for {package}: {actual}")
    observed["project_package_prefixes"] = project_prefixes

    header = (
        Path(lock["prefix"])
        / "include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp"
    )
    header_source = header.read_text(encoding="utf-8")
    if "virtual void on_reset() {}" not in header_source:
        fail("installed plugin base does not contain the qualified reset hook")
    if "virtual void on_pause(bool paused)" not in header_source:
        fail("installed plugin base does not contain the authoritative pause hook")
    if (
        "virtual void on_state_snapshot(const mjModel* model, const mjData* data, bool paused)"
        not in header_source
    ):
        fail("installed plugin base does not contain the authoritative state snapshot hook")

    required_files = lock.get("required_files", {})
    if not required_files:
        fail("lock has no installed header/runtime hashes")
    observed_files: dict[str, str] = {}
    for raw_path, expected_hash in required_files.items():
        path = Path(raw_path)
        actual_hash = sha256(path)
        observed_files[raw_path] = actual_hash
        if actual_hash != expected_hash:
            fail(f"installed file hash mismatch: {raw_path}")
    observed["required_files"] = observed_files
    print(json.dumps(observed, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail closed with one diagnostic
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        sys.exit(1)
