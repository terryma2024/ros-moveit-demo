#!/usr/bin/env python3
"""Stable backend integration contract for the MuJoCo/Gazebo convergence."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

APPROVED_URL = "git@gitee.com:zjumty/mujoco_ros2_control.git"
IMPLEMENTATION = Path("src/so101_mujoco_demo_py")
GAZEBO_PACKAGE = "so101_gazebo_demo_py"
BEHAVIOR_SOURCE_COMMIT = "8d7913e7f552a40ee627d65be8b873ac16748bc9"
BACKUP_BRANCH = "codex/so101-mujoco-ros2-pre-isolation-20260810"
BACKUP_COMMIT = "3add34f8390b78a1f4a13ff49aefb2dc87638245"


class ContractError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ContractError(message)


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def resolve_implementation_path(path: Path, logical: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except RuntimeError as error:
        fail(f"implementation symlink cycle: {logical}: {error}")
    except OSError as error:
        fail(f"cannot resolve implementation path {logical}: {error}")


def symlink_files(root: Path, repository: Path):
    def walk(logical: Path, physical: Path, active: frozenset[Path] = frozenset()):
        resolved = resolve_implementation_path(physical, logical)
        try:
            resolved.relative_to(repository)
        except ValueError:
            fail(f"implementation symlink escapes repository: {logical}")
        git = repository / ".git"
        if resolved == git or git in resolved.parents:
            fail(f"implementation symlink enters Git metadata: {logical}")
        if resolved in active:
            fail(f"implementation symlink cycle: {logical}")
        current = active | {resolved}
        for entry in sorted(os.scandir(resolved), key=lambda item: item.name):
            child = logical / entry.name
            if IMPLEMENTATION / "test" == child or IMPLEMENTATION / "test" in child.parents:
                continue
            path = Path(entry.path)
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                target = resolve_implementation_path(path, child)
                try:
                    target.relative_to(repository)
                except ValueError:
                    fail(f"implementation symlink escapes repository: {child}")
                git = repository / ".git"
                if target == git or git in target.parents:
                    fail(f"implementation symlink enters Git metadata: {child}")
                if target.is_dir():
                    yield from walk(child, target, current)
                elif target.is_file():
                    yield child, target, True
                else:
                    fail(f"unsupported implementation symlink target: {child}")
            elif stat.S_ISDIR(mode):
                yield from walk(child, path, current)
            elif stat.S_ISREG(mode):
                yield child, path, False
            else:
                fail(f"unsupported implementation filesystem entry: {child}")

    yield from walk(IMPLEMENTATION, repository / IMPLEMENTATION)


def declared_dependencies(root: Path) -> set[str]:
    deps: set[str] = set()
    package_xml = root / "package.xml"
    if package_xml.is_file():
        try:
            tree = ET.parse(package_xml)
        except ET.ParseError as error:
            fail(f"invalid package.xml: {error}")
        for node in tree.getroot():
            if node.tag.endswith("depend") and node.text:
                deps.add(node.text.strip())
    setup = root / "setup.py"
    if setup.is_file():
        try:
            tree = ast.parse(setup.read_text(encoding="utf-8"), filename=str(setup))
        except (OSError, SyntaxError) as error:
            fail(f"invalid setup.py: {error}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == GAZEBO_PACKAGE:
                    deps.add(node.value)
    return deps


def git_source_sha256(repository: Path, commit: str, source_path: str) -> str | None:
    result = subprocess.run(
        ("git", "show", f"{commit}:{source_path}"),
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def validate_provenance(root: Path) -> None:
    path = root / "docs/provenance.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid provenance JSON: {error}")
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        fail("invalid provenance structure or schema version")
    behavior = document.get("behavior_source")
    backup = document.get("rejected_backup")
    if not isinstance(behavior, dict) or behavior.get("commit") != BEHAVIOR_SOURCE_COMMIT:
        fail("invalid provenance behavior source commit")
    source_paths = behavior.get("paths")
    if (
        not isinstance(source_paths, list)
        or not source_paths
        or not all(isinstance(source_path, str) for source_path in source_paths)
    ):
        fail("invalid provenance behavior source paths")
    if (
        not isinstance(backup, dict)
        or backup.get("branch") != BACKUP_BRANCH
        or backup.get("commit") != BACKUP_COMMIT
    ):
        fail("invalid provenance rejected backup")
    fields = {"source_commit", "source_path", "destination_path", "source_sha256", "adaptation"}
    adaptations = document.get("adaptations")
    if not isinstance(adaptations, list) or not adaptations:
        fail("invalid provenance adaptations")
    adaptation_sources = []
    for index, item in enumerate(adaptations):
        if not isinstance(item, dict) or set(item) != fields:
            fail(f"invalid provenance adaptation fields at index {index}")
        if (
            item["source_commit"] != BEHAVIOR_SOURCE_COMMIT
            or item["source_path"] not in source_paths
        ):
            fail(f"invalid provenance adaptation source at index {index}")
        if not isinstance(item["destination_path"], str) or not item["destination_path"].startswith(
            "src/so101_mujoco_demo_py/"
        ):
            fail(f"invalid provenance adaptation destination at index {index}")
        source_hash = git_source_sha256(root.parents[1], item["source_commit"], item["source_path"])
        if source_hash is None or source_hash != item["source_sha256"]:
            fail(f"invalid provenance adaptation source hash at index {index}")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", str(item["source_sha256"]))
            or not isinstance(item["adaptation"], str)
            or not item["adaptation"].strip()
        ):
            fail(f"invalid provenance adaptation hash/text at index {index}")
        adaptation_sources.append(item["source_path"])
    if set(adaptation_sources) != set(source_paths):
        fail("provenance behavior paths and adaptation sources differ")
    updates = document.get("visual_reference_updates", [])
    if not isinstance(updates, list):
        fail("invalid provenance visual reference updates")
    for index, item in enumerate(updates):
        if not isinstance(item, dict) or set(item) != fields:
            fail(f"invalid provenance visual reference fields at index {index}")
        if not re.fullmatch(r"[0-9a-f]{40}", str(item["source_commit"])):
            fail(f"invalid provenance visual reference commit at index {index}")
        if not isinstance(item["source_path"], str) or not isinstance(
            item["destination_path"], str
        ):
            fail(f"invalid provenance visual reference paths at index {index}")
        source_hash = git_source_sha256(root.parents[1], item["source_commit"], item["source_path"])
        if source_hash is None or source_hash != item["source_sha256"]:
            fail(f"invalid provenance visual reference source hash at index {index}")
        if (
            not item["destination_path"].startswith("src/so101_mujoco_demo_py/")
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["source_sha256"]))
            or not isinstance(item["adaptation"], str)
            or not item["adaptation"].strip()
        ):
            fail(f"invalid provenance visual reference payload at index {index}")


def main() -> int:
    repository = Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    ).resolve()
    os.chdir(repository)
    url = run(
        "git",
        "config",
        "-f",
        ".gitmodules",
        "--get",
        "submodule.third_party/mujoco_ros2_control.url",
        cwd=repository,
    )
    if url.returncode or url.stdout.strip() != APPROVED_URL:
        fail("control submodule URL is not approved")
    entry = run(
        "git", "ls-files", "--stage", "--", "third_party/mujoco_ros2_control", cwd=repository
    )
    if entry.returncode or not entry.stdout.startswith("160000 "):
        fail("control dependency is not recorded as a gitlink")
    scan = list(symlink_files(IMPLEMENTATION, repository))
    dependencies = declared_dependencies(IMPLEMENTATION)
    expected_provenance = IMPLEMENTATION / "docs/provenance.json"
    for logical, physical, is_symlink in scan:
        if logical.suffix == ".pyc" or "__pycache__" in logical.parts:
            continue
        payload = physical.read_bytes()
        if logical == expected_provenance:
            if is_symlink:
                fail("provenance JSON must be a regular file")
            validate_provenance(IMPLEMENTATION)
            continue
        if logical.name == "provenance.json":
            fail(f"unexpected provenance JSON: {logical}")
        is_dependency_bearing_source = logical.suffix.lower() in {
            ".json",
            ".py",
            ".xml",
            ".yaml",
            ".yml",
        }
        if (
            is_dependency_bearing_source
            and GAZEBO_PACKAGE.encode() in payload.lower()
            and GAZEBO_PACKAGE not in dependencies
        ):
            fail(f"undeclared Gazebo backend dependency: {logical}")
        if logical.suffix == ".py":
            try:
                ast.parse(payload.decode("utf-8"), filename=str(logical))
            except (UnicodeDecodeError, SyntaxError) as error:
                fail(f"implementation source is not parseable: {logical}: {error}")
    print("backend integration contract passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"backend integration contract failed: {error}", file=sys.stderr)
        raise SystemExit(1)
