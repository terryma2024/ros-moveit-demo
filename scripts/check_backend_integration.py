#!/usr/bin/env python3
"""Repository contract for the canonical SO-101 Python simulation package."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

APPROVED_URL = "git@gitee.com:zjumty/mujoco_ros2_control.git"
CANONICAL_PACKAGE = "so101_demo_py"
IMPLEMENTATION = Path("src") / CANONICAL_PACKAGE
LOCK_PATH = IMPLEMENTATION / "config/mujoco/dependency-lock.yaml"
POLICY_SHA256 = "aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356"
REMOVED_PACKAGES = tuple(f"so101_{backend}_demo_py" for backend in ("mujoco", "gazebo"))
PROCESS_DOCUMENT_ROOTS = tuple(
    Path(path)
    for path in (
        "docs/experiments",
        "docs/plans",
        "docs/provenance",
        "docs/superpowers/plans",
        "docs/superpowers/specs",
    )
)
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".tsx",
    ".ts",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_canonical_package(repository: Path) -> None:
    root = repository / IMPLEMENTATION
    package_xml = ET.parse(root / "package.xml").getroot()
    require(package_xml.findtext("name") == CANONICAL_PACKAGE, "package.xml name drift")
    require((root / f"resource/{CANONICAL_PACKAGE}").is_file(), "ament resource missing")
    setup = (root / "setup.py").read_text(encoding="utf-8")
    require('python_package = "so101_demo"' in setup, "Python namespace drift")
    require("package_dir={python_package: \"src\"}" in setup, "src layout drift")


def validate_dependency_lock(repository: Path) -> None:
    lock = yaml.safe_load((repository / LOCK_PATH).read_text(encoding="utf-8"))
    require(lock.get("schema_version") == 3, "dependency lock schema drift")
    require(lock.get("provider") == "gitee_fork_submodule", "dependency provider drift")
    require(lock["fork"]["url"] == APPROVED_URL, "fork URL is not approved")
    require(lock["fork"]["tag"] == "so101-0.0.3-r10", "fork release tag drift")
    submodule_path = lock["submodule_path"]
    configured_url = git(
        repository,
        "config",
        "-f",
        ".gitmodules",
        "--get",
        f"submodule.{submodule_path}.url",
    )
    require(configured_url == APPROVED_URL, "submodule URL is not approved")
    entry = git(repository, "ls-files", "--stage", "--", submodule_path).split()
    require(len(entry) >= 2 and entry[0] == "160000", "control dependency is not a gitlink")
    require(entry[1] == lock["fork"]["commit"], "gitlink and dependency lock differ")


def validate_policy(repository: Path) -> None:
    policy_root = repository / IMPLEMENTATION / "config/policies/light_cup_wall_pick/v1"
    mujoco = policy_root / "mujoco.yaml"
    gazebo = policy_root / "gazebo.yaml"
    require(sha256(mujoco) == POLICY_SHA256, "qualified MuJoCo policy bytes changed")
    require(mujoco.read_bytes() == gazebo.read_bytes(), "simulator v1 policy variants differ")
    provenance = json.loads(
        (repository / IMPLEMENTATION / "docs/provenance.json").read_text(encoding="utf-8")
    )
    require(provenance.get("qualification_status") == "QUALIFIED", "qualification drift")
    require(provenance.get("policy", {}).get("sha256") == POLICY_SHA256, "provenance policy drift")


def is_process_document(path: Path) -> bool:
    return any(path == root or root in path.parents for root in PROCESS_DOCUMENT_ROOTS)


def validate_removed_packages(repository: Path) -> None:
    for package in REMOVED_PACKAGES:
        require(not (repository / "src" / package).exists(), f"removed package still exists: {package}")

    tracked = git(repository, "ls-files", "-z").encode("utf-8").split(b"\0")
    offenders: list[str] = []
    for encoded in tracked:
        if not encoded:
            continue
        relative = Path(encoded.decode("utf-8"))
        if is_process_document(relative) or relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = (repository / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(package in text for package in REMOVED_PACKAGES):
            offenders.append(str(relative))
    require(not offenders, "active removed-package references: " + ", ".join(offenders))


def main() -> int:
    repository = Path(
        subprocess.check_output(("git", "rev-parse", "--show-toplevel"), text=True).strip()
    ).resolve()
    validate_canonical_package(repository)
    validate_dependency_lock(repository)
    validate_policy(repository)
    validate_removed_packages(repository)
    print("backend integration contract passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, KeyError, OSError, ValueError, ET.ParseError) as error:
        print(f"backend integration contract failed: {error}", file=sys.stderr)
        raise SystemExit(1)
