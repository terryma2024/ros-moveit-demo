#!/usr/bin/env python3
"""Fail-closed probe for the pinned MuJoCo ROS 2 binary provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


PINNED_COMMIT = "35ba8174b62d9560093614f981a3d4b978a96036"
APT_PREFIX = "/opt/ros/jazzy"
PACKAGES = {
    "mujoco_vendor": "ros-jazzy-mujoco-vendor",
    "mujoco_ros2_control": "ros-jazzy-mujoco-ros2-control",
    "mujoco_ros2_control_msgs": "ros-jazzy-mujoco-ros2-control-msgs",
    "mujoco_ros2_control_plugins": "ros-jazzy-mujoco-ros2-control-plugins",
}
INTERFACES = {
    "mujoco_ros2_control_msgs/srv/ResetWorld": "string keyframe\n---\nbool success\nstring message",
    "mujoco_ros2_control_msgs/srv/SetPause": "bool paused\n---\nbool success\nstring message",
    "mujoco_ros2_control_msgs/srv/StepSimulation": "uint32 steps\n---\nbool success\nstring message",
}


def validate_lock(lock: object) -> list[str]:
    if not isinstance(lock, dict):
        return ["lock must be a mapping"]
    errors: list[str] = []
    expected = {"schema_version": 1, "provider": "apt", "release": "0.0.3", "prefix": APT_PREFIX}
    for key, value in expected.items():
        if lock.get(key) != value:
            errors.append(f"{key} must be {value}")
    fallback = lock.get("fallback")
    if not isinstance(fallback, dict):
        errors.append("fallback must be a mapping")
    else:
        for key, value in {"tag": "0.0.3", "commit": PINNED_COMMIT, "prefix": "/data/work/ws_mujoco_ros2_control_003/install"}.items():
            if fallback.get(key) != value:
                errors.append(f"fallback {key} must be {value}")
    files = lock.get("required_files")
    if not isinstance(files, dict) or not files:
        errors.append("required_files must contain sha256 pins")
    elif any(not isinstance(value, str) or len(value) != 64 for value in files.values()):
        errors.append("required_files values must be sha256")
    return errors


def run(command: list[str], environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, check=True, text=True, capture_output=True, env=environment)
    return result.stdout.strip()


def ros_environment() -> dict[str, str]:
    environment = dict(os.environ)
    paths = [item for item in environment.get("PYTHONPATH", "").split(os.pathsep) if item]
    for prefix in environment.get("AMENT_PREFIX_PATH", APT_PREFIX).split(os.pathsep):
        candidate = f"{prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        if candidate not in paths:
            paths.append(candidate)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    return environment


def probe(lock: dict) -> dict[str, object]:
    errors = validate_lock(lock)
    prefixes: dict[str, str] = {}
    versions: dict[str, str] = {}
    definitions: dict[str, str] = {}
    hashes: dict[str, str] = {}
    environment = ros_environment()
    for package, debian_package in PACKAGES.items():
        prefixes[package] = run(["ros2", "pkg", "prefix", package], environment)
        versions[package] = run(["dpkg-query", "-W", "-f=${Version}", debian_package])
        if prefixes[package] != APT_PREFIX:
            errors.append(f"{package} prefix must be {APT_PREFIX}")
    if not versions.get("mujoco_ros2_control", "").startswith("0.0.3-"):
        errors.append("mujoco_ros2_control apt version must start with 0.0.3-")
    for interface, expected in INTERFACES.items():
        definition = run(["ros2", "interface", "show", interface], environment).strip()
        definitions[interface] = definition
        hashes[interface] = hashlib.sha256(definition.encode()).hexdigest()
        if definition != expected:
            errors.append(f"{interface} definition mismatch")
    for filename, expected_hash in lock.get("required_files", {}).items():
        observed = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        if observed != expected_hash:
            errors.append(f"required file hash mismatch: {filename}")
    return {"provider": lock.get("provider"), "release": lock.get("release"), "prefixes": prefixes, "package_versions": versions, "interface_sha256": hashes, "validation_errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = probe(yaml.safe_load(args.lock.read_text(encoding="utf-8")))
        code = 0 if not document["validation_errors"] else 1
    except Exception as error:
        document = {"validation_errors": [f"probe failed: {type(error).__name__}: {error}"]}
        code = 1
    print(json.dumps(document, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
