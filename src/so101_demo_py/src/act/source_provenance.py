"""Closed Task 8 source provenance: what the runtime actually loads, and from where.

The registry below is the only source of runtime roles. A caller cannot trim it, add to it or
reorder it: verification re-derives the same closed set and rejects anything else.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

SCHEMA_VERSION = 1
KIND = "task8_live_source_provenance"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")

#: (logical_name, artifact_kind, repository-relative source, install-relative install path)
#: kind semantics: verbatim_install copies bytes unchanged; compiled records a build receipt;
#: external_runtime records the loaded path, its hash and a version string.
_ROLE_SPECS = (
    ("command_broker", "verbatim_install",
     "src/so101_demo_py/src/adapters/act/command_broker.py",
     "so101_demo_py/lib/python3.12/site-packages/so101_demo/adapters/act/command_broker.py"),
    ("task8_runner", "verbatim_install",
     "src/so101_demo_py/src/act/task8.py",
     "so101_demo_py/lib/python3.12/site-packages/so101_demo/act/task8.py"),
    ("teleop_child", "verbatim_install",
     "src/so101_teleop/so101_teleop/unified/ros_child.py",
     "so101_teleop/lib/python3.12/site-packages/so101_teleop/unified/ros_child.py"),
    ("teleop_case_owner", "verbatim_install",
     "src/so101_teleop/so101_teleop/unified/bridge.py",
     "so101_teleop/lib/python3.12/site-packages/so101_teleop/unified/bridge.py"),
    ("controller_config", "verbatim_install",
     "src/so101_demo_py/config/mujoco/ros2_controllers.yaml",
     "so101_demo_py/share/so101_demo_py/config/mujoco/ros2_controllers.yaml"),
    ("simulation_evidence_plugin", "compiled",
     "src/so101_mujoco_support/src/simulation_evidence_plugin.cpp",
     "so101_mujoco_support/lib/libso101_simulation_evidence_plugin.so"),
    ("broker_owned_controller_plugin", "compiled",
     "src/so101_mujoco_support/src/broker_owned_trajectory_controller.cpp",
     "so101_mujoco_support/lib/libso101_broker_owned_trajectory_controller.so"),
    ("mujoco_ros2_control_plugin", "compiled",
     "src/so101_mujoco_support/src/simulation_evidence_plugin.cpp",
     "so101_mujoco_support/lib/libmujoco_ros2_control.so"),
    ("ros_runtime", "external_runtime", None, None),
    ("model_weights", "external_runtime", None, None),
)

#: external runtimes are named by their real load site, never by a source-tree stand-in
_EXTERNAL_RUNTIMES = {
    "ros_runtime": ("/opt/ros/jazzy/bin/ros2", "jazzy"),
    "model_weights": ("/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt", "yolo11n-seg"),
}

_TOP_LEVEL = ("schema_version", "kind", "repository_head", "submodules", "calibration_identity",
              "runtime_roles")
_ROLE_FIELDS = {
    "verbatim_install": {"logical_name", "artifact_kind", "source_path", "source_sha256",
                         "installed_path", "installed_sha256"},
    "compiled": {"logical_name", "artifact_kind", "source_path", "installed_path",
                 "installed_sha256", "build_receipt_path", "build_receipt_sha256"},
    "external_runtime": {"logical_name", "artifact_kind", "loaded_path", "loaded_sha256",
                         "version"},
}
_RECEIPT_FIELDS = ("sources", "headers", "cmake_arguments", "compiler", "linker",
                   "dependency_sha256", "output_sha256")


def runtime_role_specs() -> tuple[tuple[str, str, str | None, str | None], ...]:
    """The closed registry, so tests and callers can enumerate it without editing it."""

    return _ROLE_SPECS


def _digest(path: Path) -> str:
    stream = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(stream, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _regular(path: Path, code: str) -> None:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(code) from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(code)


def _head(source_root: Path) -> str:
    result = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    head = result.stdout.strip()
    if result.returncode != 0 or _COMMIT.fullmatch(head) is None:
        raise ValueError("SOURCE_PROVENANCE_HEAD_UNKNOWN")
    return head


def _submodules(source_root: Path) -> dict:
    result = subprocess.run(["git", "-C", str(source_root), "submodule", "status"],
                            capture_output=True, text=True, check=False)
    submodules = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and _COMMIT.fullmatch(parts[0].lstrip("+-")):
            submodules[parts[1]] = parts[0].lstrip("+-")
    return dict(sorted(submodules.items()))


def build_source_provenance(source_root: Path, install_overlay: Path, *,
                            calibration_identity=None) -> dict:
    """Describe every registered runtime role as it exists in this tree and overlay."""

    source_root, install_overlay = Path(source_root), Path(install_overlay)
    if calibration_identity is None:
        from .calibration import installed_calibration_identity
        calibration_identity = installed_calibration_identity(source_root)
    source_commit, config_sha256 = calibration_identity
    if _COMMIT.fullmatch(source_commit) is None or _SHA.fullmatch(config_sha256) is None:
        raise ValueError("SOURCE_PROVENANCE_CALIBRATION_IDENTITY_INVALID")
    roles = []
    for logical_name, artifact_kind, source_rel, install_rel in _ROLE_SPECS:
        if artifact_kind == "verbatim_install":
            source_path = source_root / source_rel
            installed_path = install_overlay / install_rel
            _regular(source_path, "SOURCE_PROVENANCE_SOURCE_MISSING")
            _regular(installed_path, "SOURCE_PROVENANCE_INSTALL_MISSING")
            roles.append({
                "logical_name": logical_name, "artifact_kind": artifact_kind,
                "source_path": source_rel, "source_sha256": _digest(source_path),
                "installed_path": str(installed_path), "installed_sha256": _digest(installed_path),
            })
        elif artifact_kind == "compiled":
            installed_path = install_overlay / install_rel
            receipt_path = Path(str(installed_path) + ".build-receipt.json")
            _regular(installed_path, "SOURCE_PROVENANCE_INSTALL_MISSING")
            _regular(receipt_path, "SOURCE_PROVENANCE_RECEIPT_MISSING")
            roles.append({
                "logical_name": logical_name, "artifact_kind": artifact_kind,
                "source_path": source_rel, "installed_path": str(installed_path),
                "installed_sha256": _digest(installed_path),
                "build_receipt_path": str(receipt_path),
                "build_receipt_sha256": _digest(receipt_path),
            })
        else:
            loaded_path, version = _EXTERNAL_RUNTIMES[logical_name]
            path = Path(loaded_path)
            _regular(path, "SOURCE_PROVENANCE_EXTERNAL_MISSING")
            roles.append({
                "logical_name": logical_name, "artifact_kind": artifact_kind,
                "loaded_path": loaded_path, "loaded_sha256": _digest(path), "version": version,
            })
    document = {
        "schema_version": SCHEMA_VERSION, "kind": KIND, "repository_head": _head(source_root),
        "submodules": _submodules(source_root),
        "calibration_identity": {"source_commit": source_commit,
                                 "config_sha256": config_sha256},
        "runtime_roles": sorted(roles, key=lambda role: role["logical_name"]),
    }
    return verify_source_provenance(document, source_root=source_root,
                                    install_overlay=install_overlay)


def canonical_bytes(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def write_source_provenance(document: dict, output: Path) -> Path:
    """Atomically publish a provenance file; an existing target is never overwritten."""

    output = Path(output)
    payload = canonical_bytes(document)
    descriptor = os.open(str(output) + ".partial", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(str(output) + ".partial", output)
    except FileExistsError as error:
        os.unlink(str(output) + ".partial")
        raise ValueError("SOURCE_PROVENANCE_OUTPUT_EXISTS") from error
    os.unlink(str(output) + ".partial")
    return output


def verify_source_provenance(document: dict, *, source_root: Path, install_overlay: Path) -> dict:
    """Re-derive every registered role and reject any drift, in a canonical document."""

    if type(document) is not dict or tuple(sorted(document)) != tuple(sorted(_TOP_LEVEL)):
        raise ValueError("SOURCE_PROVENANCE_SCHEMA_INVALID")
    if document["schema_version"] != SCHEMA_VERSION or document["kind"] != KIND:
        raise ValueError("SOURCE_PROVENANCE_SCHEMA_INVALID")
    if canonical_bytes(document) != canonical_bytes(json.loads(canonical_bytes(document))):
        raise ValueError("SOURCE_PROVENANCE_NOT_CANONICAL")
    source_root, install_overlay = Path(source_root), Path(install_overlay)
    roles = document["runtime_roles"]
    if type(roles) is not list:
        raise ValueError("SOURCE_PROVENANCE_SCHEMA_INVALID")
    if any(type(role) is not dict or type(role.get("logical_name")) is not str
           or not role["logical_name"] for role in roles):
        raise ValueError("SOURCE_PROVENANCE_ROLE_INVALID")
    names = [role["logical_name"] for role in roles]
    expected = [spec[0] for spec in _ROLE_SPECS]
    if sorted(names) != sorted(expected) or len(names) != len(expected):
        raise ValueError("SOURCE_PROVENANCE_ROLE_SET_INVALID")
    for role in roles:
        kind = role.get("artifact_kind")
        if kind not in _ROLE_FIELDS or set(role) != _ROLE_FIELDS[kind]:
            raise ValueError("SOURCE_PROVENANCE_ROLE_INVALID")
        if kind == "verbatim_install":
            source_path = source_root / role["source_path"]
            _regular(source_path, "SOURCE_PROVENANCE_SOURCE_MISSING")
            if _digest(source_path) != role["source_sha256"]:
                raise ValueError("SOURCE_PROVENANCE_DIRTY")
            installed_path = Path(role["installed_path"])
            _regular(installed_path, "SOURCE_PROVENANCE_INSTALL_MISSING")
            if _digest(installed_path) != role["installed_sha256"]:
                raise ValueError("SOURCE_PROVENANCE_INSTALL_DIRTY")
            if role["source_sha256"] != role["installed_sha256"]:
                raise ValueError("SOURCE_PROVENANCE_NOT_VERBATIM")
        elif kind == "compiled":
            installed_path = Path(role["installed_path"])
            _regular(installed_path, "SOURCE_PROVENANCE_INSTALL_MISSING")
            if _digest(installed_path) != role["installed_sha256"]:
                raise ValueError("SOURCE_PROVENANCE_INSTALL_DIRTY")
            receipt_path = Path(role["build_receipt_path"])
            _regular(receipt_path, "SOURCE_PROVENANCE_RECEIPT_MISSING")
            if _digest(receipt_path) != role["build_receipt_sha256"]:
                raise ValueError("SOURCE_PROVENANCE_RECEIPT_DIRTY")
            receipt = json.loads(receipt_path.read_bytes())
            if (type(receipt) is not dict or set(receipt) != set(_RECEIPT_FIELDS)
                    or not receipt["sources"] or not receipt["headers"]
                    or not receipt["cmake_arguments"] or not receipt["compiler"]
                    or not receipt["linker"]
                    or receipt["output_sha256"] != role["installed_sha256"]):
                raise ValueError("SOURCE_PROVENANCE_RECEIPT_INVALID")
            dependencies = receipt["dependency_sha256"]
            if not isinstance(dependencies, dict) or not dependencies:
                raise ValueError("SOURCE_PROVENANCE_RECEIPT_INVALID")
            for relative, digest in dependencies.items():
                if _SHA.fullmatch(str(digest)) is None or type(relative) is not str:
                    raise ValueError("SOURCE_PROVENANCE_RECEIPT_INVALID")
                candidate = source_root / relative
                _regular(candidate, "SOURCE_PROVENANCE_RECEIPT_INPUT_MISSING")
                if _digest(candidate) != digest:
                    raise ValueError("SOURCE_PROVENANCE_RECEIPT_INPUT_DIRTY")
        else:
            path = Path(role["loaded_path"])
            _regular(path, "SOURCE_PROVENANCE_EXTERNAL_MISSING")
            if _digest(path) != role["loaded_sha256"]:
                raise ValueError("SOURCE_PROVENANCE_EXTERNAL_DIRTY")
            if type(role["version"]) is not str or not role["version"]:
                raise ValueError("SOURCE_PROVENANCE_ROLE_INVALID")
    expected_submodules = _submodules(source_root)
    if document["submodules"] != expected_submodules:
        raise ValueError("SOURCE_PROVENANCE_SUBMODULE_DRIFT")
    if document["repository_head"] != _head(source_root):
        raise ValueError("SOURCE_PROVENANCE_HEAD_DRIFT")
    return document
