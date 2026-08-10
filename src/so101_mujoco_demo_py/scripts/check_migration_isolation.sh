#!/usr/bin/env bash
set -euo pipefail

readonly expected_branch="codex/so101-mujoco-ros2"
readonly main_base_commit="d300e7a41fb274d6d7e120699b7040666ea61904"
readonly task_base_commit="45c6efc701b133c45875e86b0053cfc37dab7f4f"
readonly protected_tree="src/so101_gazebo_"'demo_py'
readonly ledger="docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md"

fail() {
  printf 'migration isolation check failed: %s\n' "$1" >&2
  exit 1
}

repository_root=$(git rev-parse --show-toplevel 2>/dev/null) ||
  fail "not inside a Git worktree"
cd "$repository_root"

current_branch=$(git branch --show-current)
if [[ "$current_branch" != "$expected_branch" ]]; then
  fail "unexpected branch '$current_branch' (expected '$expected_branch')"
fi

git cat-file -e "${main_base_commit}^{commit}" 2>/dev/null ||
  fail "pinned main base commit is unavailable"
git cat-file -e "${task_base_commit}^{commit}" 2>/dev/null ||
  fail "pinned task base commit is unavailable"
git merge-base --is-ancestor "$main_base_commit" "$task_base_commit" ||
  fail "pinned main base is not an ancestor of the task base"
git merge-base --is-ancestor "$task_base_commit" HEAD ||
  fail "pinned task base is not an ancestor of HEAD"

if ! git diff --quiet "$main_base_commit" -- "$protected_tree"; then
  fail "protected Gazebo tree differs from $main_base_commit"
fi

protected_status=$(git status --short -- "$protected_tree")
if [[ -n "$protected_status" ]]; then
  fail "protected Gazebo tree has worktree changes"
fi

if ! python3 - "$repository_root" "$protected_tree" "$ledger" <<'PY'
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


class IsolationError(RuntimeError):
    pass


repository_root = Path(sys.argv[1]).resolve()
protected_tree = Path(sys.argv[2])
ledger_path = repository_root / sys.argv[3]
implementation_root = repository_root / "src/so101_mujoco_demo_py"
provenance_path = implementation_root / "docs/provenance.json"
legacy_namespace = ("so101_gazebo_" + "demo_py").lower()
behavior_source_commit = "8d7913e7f552a40ee627d65be8b873ac16748bc9"
backup_branch = "codex/so101-mujoco-ros2-pre-" + "isolation-20260810"
backup_commit = "3add34f8390b78a1f4a13f" + "f49aefb2dc87638245"


def fail(message: str) -> None:
    raise IsolationError(message)


def read_front_matter(document: Path) -> dict[str, str]:
    try:
        lines = document.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read ledger: {error}")
    if not lines or lines[0] != "---":
        fail("ledger has no YAML front matter")
    try:
        closing_marker = lines.index("---", 1)
    except ValueError:
        fail("ledger front matter is not closed")
    values: dict[str, str] = {}
    for line in lines[1:closing_marker]:
        match = re.fullmatch(r"([a-z0-9_]+):\s*(.*)", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def git_tracked_paths() -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", str(protected_tree)],
            cwd=repository_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"cannot enumerate tracked protected files: {error}")
    return {
        entry.decode("utf-8")
        for entry in result.stdout.split(b"\0")
        if entry
    }


def protected_nontracked_manifest_sha256() -> str:
    tracked = git_tracked_paths()
    protected_root = repository_root / protected_tree
    records: list[str] = []
    try:
        walker = os.walk(protected_root, followlinks=False)
        for current_root, directory_names, file_names in walker:
            current = Path(current_root)
            symlink_directories = [
                name for name in directory_names if (current / name).is_symlink()
            ]
            directory_names[:] = [
                name for name in directory_names if name not in symlink_directories
            ]
            for name in sorted(file_names + symlink_directories):
                candidate = current / name
                relative = candidate.relative_to(repository_root).as_posix()
                if relative in tracked:
                    continue
                metadata = candidate.lstat()
                mode = stat.S_IMODE(metadata.st_mode)
                if stat.S_ISLNK(metadata.st_mode):
                    kind = "L"
                    payload = os.readlink(candidate).encode()
                elif stat.S_ISREG(metadata.st_mode):
                    kind = "F"
                    payload = candidate.read_bytes()
                else:
                    fail(f"unsupported protected filesystem entry: {relative}")
                payload_sha256 = hashlib.sha256(payload).hexdigest()
                records.append(
                    f"{kind}\t{mode:04o}\t{payload_sha256}\t{relative}\n"
                )
    except OSError as error:
        fail(f"cannot fingerprint protected filesystem: {error}")
    return hashlib.sha256("".join(sorted(records)).encode()).hexdigest()


def is_within_repository(candidate: Path) -> bool:
    try:
        candidate.relative_to(repository_root)
    except ValueError:
        return False
    return True


def implementation_files(
    logical_directory: Path,
    physical_directory: Path,
    active_directories: frozenset[Path] = frozenset(),
):
    resolved_directory = physical_directory.resolve(strict=True)
    if not is_within_repository(resolved_directory):
        fail(f"implementation symlink escapes repository: {logical_directory}")
    if repository_root / ".git" == resolved_directory or repository_root / ".git" in resolved_directory.parents:
        fail(f"implementation symlink enters Git metadata: {logical_directory}")
    if resolved_directory in active_directories:
        fail(f"implementation symlink cycle: {logical_directory}")
    next_active = active_directories | {resolved_directory}
    try:
        entries = sorted(os.scandir(resolved_directory), key=lambda entry: entry.name)
    except OSError as error:
        fail(f"cannot enumerate implementation directory {logical_directory}: {error}")

    for entry in entries:
        logical_path = logical_directory / entry.name
        if logical_path == implementation_root / "test" or implementation_root / "test" in logical_path.parents:
            continue
        physical_path = Path(entry.path)
        try:
            metadata = physical_path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                target = physical_path.resolve(strict=True)
                if not is_within_repository(target):
                    fail(f"implementation symlink escapes repository: {logical_path}")
                target_metadata = target.stat()
                if stat.S_ISDIR(target_metadata.st_mode):
                    yield from implementation_files(logical_path, target, next_active)
                elif stat.S_ISREG(target_metadata.st_mode):
                    yield logical_path, target, True
                else:
                    fail(f"unsupported implementation symlink target: {logical_path}")
            elif stat.S_ISDIR(metadata.st_mode):
                yield from implementation_files(logical_path, physical_path, next_active)
            elif stat.S_ISREG(metadata.st_mode):
                yield logical_path, physical_path, False
            else:
                fail(f"unsupported implementation filesystem entry: {logical_path}")
        except OSError as error:
            fail(f"cannot inspect implementation path {logical_path}: {error}")


def constant_string(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = constant_string(node.left, constants)
        right = constant_string(node.right, constants)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        pieces: list[str] = []
        for value in node.values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                return None
            pieces.append(value.value)
        return "".join(pieces)
    return None


def scan_python(logical_path: Path, payload: bytes) -> None:
    display_path = logical_path.relative_to(repository_root)
    try:
        source = payload.decode("utf-8")
        tree = ast.parse(source, filename=str(display_path))
    except (UnicodeDecodeError, SyntaxError) as error:
        fail(f"cannot parse Python source {display_path}: {error}")

    constants: dict[str, str] = {}
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            value_node = statement.value
            if value_node is None:
                continue
            value = constant_string(value_node, constants)
            if value is None:
                continue
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value

    for node in ast.walk(tree):
        candidate = constant_string(node, constants)
        if candidate is not None and legacy_namespace in candidate.lower():
            fail(f"legacy Gazebo Python dependency: {display_path}")
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        if any(legacy_namespace in module.lower() for module in modules):
            fail(f"legacy Gazebo Python dependency: {display_path}")


def json_string_positions(value, path=()):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from json_string_positions(nested, path + (key,))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from json_string_positions(nested, path + (index,))
    elif isinstance(value, str):
        yield path, value


def validate_provenance(payload: bytes) -> None:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"invalid provenance JSON: {error}")
    if not isinstance(document, dict):
        fail("invalid provenance structure: top level must be an object")
    if document.get("schema_version") != 1:
        fail("invalid provenance schema version")

    behavior_source = document.get("behavior_source")
    rejected_backup = document.get("rejected_backup")
    if not isinstance(behavior_source, dict):
        fail("invalid provenance structure: behavior_source must be an object")
    if behavior_source.get("commit") != behavior_source_commit:
        fail("invalid provenance behavior source commit")
    source_paths = behavior_source.get("paths")
    if not isinstance(source_paths, list) or not source_paths or not all(
        isinstance(source_path, str) for source_path in source_paths
    ):
        fail("invalid provenance behavior source paths")
    if not isinstance(rejected_backup, dict):
        fail("invalid provenance structure: rejected_backup must be an object")
    if rejected_backup.get("branch") != backup_branch:
        fail("invalid provenance rejected backup branch")
    if rejected_backup.get("commit") != backup_commit:
        fail("invalid provenance rejected backup commit")

    adaptations = document.get("adaptations")
    expected_adaptation_fields = {
        "source_commit",
        "source_path",
        "destination_path",
        "source_sha256",
        "adaptation",
    }
    if not isinstance(adaptations, list) or not adaptations:
        fail("invalid provenance adaptations")
    adaptation_source_paths: list[str] = []
    for index, adaptation in enumerate(adaptations):
        if not isinstance(adaptation, dict) or set(adaptation) != expected_adaptation_fields:
            fail(f"invalid provenance adaptation fields at index {index}")
        if adaptation["source_commit"] != behavior_source_commit:
            fail(f"invalid provenance adaptation source commit at index {index}")
        source_path = adaptation["source_path"]
        if source_path not in source_paths:
            fail(f"undeclared provenance adaptation source at index {index}")
        destination_path = adaptation["destination_path"]
        if not isinstance(destination_path, str) or not destination_path.startswith(
            "src/so101_mujoco_demo_py/"
        ):
            fail(f"invalid provenance adaptation destination at index {index}")
        if not re.fullmatch(r"[0-9a-f]{64}", adaptation["source_sha256"]):
            fail(f"invalid provenance adaptation source hash at index {index}")
        if not isinstance(adaptation["adaptation"], str) or not adaptation["adaptation"].strip():
            fail(f"invalid provenance adaptation text at index {index}")
        adaptation_source_paths.append(source_path)
    if set(adaptation_source_paths) != set(source_paths):
        fail("provenance behavior paths and adaptation sources differ")

    for path, value in json_string_positions(document):
        lowered = value.lower()
        legacy_allowed = (
            (
                len(path) == 3
                and path[0] == "behavior_source"
                and path[1] == "paths"
                and isinstance(path[2], int)
            )
            or (
                len(path) == 3
                and path[0] == "adaptations"
                and isinstance(path[1], int)
                and path[2] == "source_path"
                and value in source_paths
            )
        )
        backup_allowed = path in {
            ("rejected_backup", "branch"),
            ("rejected_backup", "commit"),
        }
        if legacy_namespace in lowered and not legacy_allowed:
            fail(f"legacy namespace in invalid provenance position: {path}")
        if (backup_branch.lower() in lowered or backup_commit in lowered) and not backup_allowed:
            fail(f"backup reference in invalid provenance position: {path}")


def scan_implementation() -> None:
    try:
        files = implementation_files(implementation_root, implementation_root)
        for logical_path, physical_path, is_symlink in files:
            display_path = logical_path.relative_to(repository_root)
            try:
                payload = physical_path.read_bytes()
            except OSError as error:
                fail(f"cannot read implementation file {display_path}: {error}")

            if logical_path == provenance_path:
                if is_symlink:
                    fail("provenance JSON must be a regular file")
                validate_provenance(payload)
                continue
            if logical_path.name == "provenance.json":
                fail(f"provenance exemption is only allowed at {provenance_path.relative_to(repository_root)}")

            lowered_payload = payload.lower()
            if legacy_namespace.encode() in lowered_payload:
                fail(f"legacy Gazebo Python dependency: {display_path}")
            if backup_branch.lower().encode() in lowered_payload or backup_commit.encode() in lowered_payload:
                fail(f"rejected backup reference: {display_path}")
            if logical_path.suffix == ".py":
                scan_python(logical_path, payload)
    except IsolationError:
        raise
    except Exception as error:
        fail(f"unexpected implementation scanner error: {error}")


try:
    front_matter = read_front_matter(ledger_path)
    expected_manifest = front_matter.get("protected_nontracked_baseline_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest):
        fail("ledger has no valid protected nontracked baseline digest")
    actual_manifest = protected_nontracked_manifest_sha256()
    if actual_manifest != expected_manifest:
        fail(
            "protected nontracked filesystem differs from baseline "
            f"(actual {actual_manifest}, expected {expected_manifest})"
        )
    scan_implementation()
except IsolationError as error:
    print(f"migration isolation scanner failed: {error}", file=sys.stderr)
    sys.exit(1)
PY
then
  fail "implementation scan failed"
fi

printf 'migration isolation check passed\n'
