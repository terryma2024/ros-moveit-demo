"""Mechanical inventory behind the code-style guards.

The refactor removes version numbers (``v1``, ``V2``) and process names (``task8``, ``w2``, ``b1b``) from
file names, identifiers and wire strings. This module finds every such name, so a guard test can compare
the hits with a reviewed allowlist, and so the rename map can be generated instead of written by hand.

Three scans, each AST- or manifest-scoped so that geometry identifiers (``x1``, ``q6``, ``dq1``) and other
locals are never read as hits:

``versioned``
    A whole snake_case or CamelCase segment ``v<digits>``, in a file or directory name or in a module-level
    ``def`` / ``class`` / constant name, and in ``console_scripts`` names.
``process``
    A whole segment naming a work step (``task8``, ``t8``, ``w2``, ``n1``, ``hs40``, ``cp12``, ``exp3``,
    ``p3``, ``b1b``, ``d4``, ``rec12b``, ``r11``) in the same places.
``wire``
    String values in package source and configuration that carry a process name on the wire:
    ``TASK<n>_`` error codes, ``SO101_TASK<n>`` environment variables, ``task<n>-`` / ``task<n>_`` identifiers,
    ``MPS_W<n>_`` profile values, ``hs<n>-`` case ids, a whole-string worker label (``"w1"``, ``"W8"``), and
    kind-like literals with an embedded ``[-_]v<n>`` segment. Docstrings are not wire values and are not scanned.

``python src/so101_demo_py/test/support/style_inventory.py`` prints the per-guard counts.
"""

from __future__ import annotations

import ast
import functools
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from paths import REPOSITORY


# The four Python packages the refactor covers, and the directory that holds each one's importable source.
PACKAGES = {
    "so101_demo_py": "src",
    "so101_teleop": "so101_teleop",
    "so101_quik": "so101_quik",
    "so101_mujoco_support": "src",
}
TEST_TREES = ("test", "benchmark_test")
# Directories whose file names are part of the inventory, next to the source root and the test trees.
NAME_TREES = ("config", "launch", "scripts", "docker", "assets", "cmake", "include", "msg")
CONFIG_TREE = "config"
EXCLUDED_PARTS = {"build", "install", "log", "__pycache__", "node_modules", ".git", ".pytest_cache", "third_party"}

SCAN_VERSIONED = "versioned"
SCAN_PROCESS = "process"
SCAN_WIRE = "wire"

_VERSION_SEGMENT = re.compile(r"v\d+", re.IGNORECASE)
_PROCESS_SEGMENT = re.compile(
    r"task\d+|t8|w\d|n1|hs\d+|cp\d+|exp\d+|p\d|b\d+b?|d\d|rec\d+b?|r\d+b?", re.IGNORECASE
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WIRE_PATTERNS = (
    re.compile(r"TASK\d+_"),
    re.compile(r"SO101_TASK\d+"),
    re.compile(r"task\d+[-_]"),
    re.compile(r"MPS_W\d_"),
    re.compile(r"(?<![A-Za-z0-9])hs\d+-"),
    # an error code or verdict that names a worker count by its work step (W8_QUALIFICATION_..., N1_CAMPAIGN_PASS, ..._N1)
    re.compile(r"(?<![A-Za-z0-9])(?:W\d|N1)_[A-Z]"),
    re.compile(r"[A-Z]_(?:W\d|N1)(?![A-Za-z0-9])"),
)
# A kind-like literal is one token with no space or slash. It carries a version when a ``v<digits>`` segment sits
# between separators anywhere in it (``so101-run-result-v1``, ``recorder_queue_v1``, ``paired_camera_truth_v2_original``).
_KIND_LIKE = re.compile(r"[A-Za-z][\w.\-]*")
_EMBEDDED_VERSION = re.compile(r"(?:^|[-_])[vV]\d+(?=[-_.]|$)")
# A worker or work-step label used as a whole string (``"w1"``, ``"W8"``) is a process name, not a counter.
_WORKER_LABEL = re.compile(r"[Ww]\d")


def segments(name: str) -> list[str]:
    """Split a file stem or identifier into snake_case, kebab-case and CamelCase segments."""

    out: list[str] = []
    for chunk in re.split(r"[^0-9A-Za-z]+", name):
        if chunk:
            out.extend(part for part in _CAMEL_BOUNDARY.split(chunk) if part)
    return out


def versioned_segments(name: str) -> list[str]:
    return [segment for segment in segments(name) if _VERSION_SEGMENT.fullmatch(segment)]


def process_segments(name: str) -> list[str]:
    return [segment for segment in segments(name) if _PROCESS_SEGMENT.fullmatch(segment)]


_SCANNERS = {SCAN_VERSIONED: versioned_segments, SCAN_PROCESS: process_segments}


@dataclass(frozen=True, order=True)
class Hit:
    """One inventory hit. ``key`` is its stable identity in the allowlists."""

    scan: str
    path: str  # repository-relative, POSIX
    kind: str  # file | dir | def | class | const | script | str
    name: str

    @property
    def key(self) -> str:
        return f"{self.scan}|{self.path}|{self.kind}|{self.name}"


def _tracked(repository: Path) -> list[str]:
    """Repository-relative paths of tracked and not-ignored files, or a directory walk without git."""

    try:
        out = subprocess.run(
            ["git", "-C", str(repository), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            check=True,
        ).stdout
        return sorted(p for p in out.decode().split("\0") if p and (repository / p).is_file())
    except (OSError, subprocess.CalledProcessError):
        found: list[str] = []
        for base, dirs, files in os.walk(repository / "src"):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_PARTS]
            found.extend(str((Path(base) / f).relative_to(repository)) for f in files)
        return sorted(found)


def _package_of(path: str) -> tuple[str, str] | None:
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "src" or parts[1] not in PACKAGES:
        return None
    if EXCLUDED_PARTS.intersection(parts):
        return None
    return parts[1], "/".join(parts[2:])


def _in_tree(rest: str, tree: str) -> bool:
    return rest == tree or rest.startswith(tree + "/")


@functools.lru_cache(maxsize=4)
def _package_files(repository: Path) -> tuple[tuple[str, str, str], ...]:
    """``(repository-relative path, package, path-inside-package)`` for every inventoried file."""

    files: list[tuple[str, str, str]] = []
    for path in _tracked(repository):
        located = _package_of(path)
        if located is None:
            continue
        package, rest = located
        roots = (PACKAGES[package], *TEST_TREES, *NAME_TREES)
        if any(_in_tree(rest, tree) for tree in roots) or "/" not in rest:
            files.append((path, package, rest))
    return tuple(files)


def package_files(repository: Path = REPOSITORY) -> list[tuple[str, str, str]]:
    """The inventoried files, computed once per process."""

    return list(_package_files(repository))


def _name_hits(scan: str, files: list[tuple[str, str, str]]) -> list[Hit]:
    matcher = _SCANNERS[scan]
    hits: list[Hit] = []
    seen_dirs: set[str] = set()
    for path, _package, rest in files:
        parts = rest.split("/")
        for index, part in enumerate(parts[:-1]):
            directory = "/".join(["src", path.split("/")[1], *parts[: index + 1]])
            if directory not in seen_dirs:
                seen_dirs.add(directory)
                if matcher(part):
                    hits.append(Hit(scan, directory, "dir", part))
        stem = parts[-1]
        stem_no_ext = stem.rsplit(".", 1)[0] if "." in stem else stem
        if matcher(stem_no_ext):
            hits.append(Hit(scan, path, "file", stem))
    return hits


def _module_level_names(tree: ast.Module) -> list[tuple[str, str]]:
    """``(kind, name)`` for module-level def, class and constant names, including those under module-level
    ``if`` / ``try`` / ``with`` blocks but never inside a function or class body."""

    found: list[tuple[str, str]] = []

    def targets(node: ast.expr) -> list[str]:
        if isinstance(node, ast.Name):
            return [node.id]
        if isinstance(node, (ast.Tuple, ast.List)):
            return [name for element in node.elts for name in targets(element)]
        if isinstance(node, ast.Starred):
            return targets(node.value)
        return []

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append(("def", node.name))
            elif isinstance(node, ast.ClassDef):
                found.append(("class", node.name))
            elif isinstance(node, ast.Assign):
                found.extend(("const", name) for target in node.targets for name in targets(target))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                found.extend(("const", name) for name in targets(node.target))
            elif isinstance(node, ast.If):
                visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body)
                for handler in node.handlers:
                    visit(handler.body)
                visit(node.orelse)
                visit(node.finalbody)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                visit(node.body)

    visit(tree.body)
    return found


@functools.lru_cache(maxsize=4096)
def _parse(repository: Path, path: str) -> ast.Module | None:
    try:
        return ast.parse((repository / path).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _symbol_hits(scan: str, files: list[tuple[str, str, str]], repository: Path) -> list[Hit]:
    matcher = _SCANNERS[scan]
    hits: list[Hit] = []
    for path, _package, rest in files:
        if not path.endswith(".py"):
            continue
        tree = _parse(repository, path)
        if tree is None:
            continue
        seen: set[tuple[str, str]] = set()
        for kind, name in _module_level_names(tree):
            if (kind, name) not in seen and matcher(name):
                seen.add((kind, name))
                hits.append(Hit(scan, path, kind, name))
    return hits


def _console_script_hits(scan: str, repository: Path) -> list[Hit]:
    matcher = _SCANNERS[scan]
    hits: list[Hit] = []
    for package in PACKAGES:
        setup = repository / "src" / package / "setup.py"
        if not setup.is_file():
            continue
        tree = _parse(repository, f"src/{package}/setup.py")
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "=" in node.value:
                script = node.value.split("=", 1)[0].strip()
                if re.fullmatch(r"[A-Za-z0-9_.\-]+", script) and "." not in script and ":" not in node.value.split("=", 1)[0]:
                    if matcher(script) and _is_console_script(tree, node):
                        hits.append(Hit(scan, f"src/{package}/setup.py", "script", script))
    return hits


def _is_console_script(tree: ast.Module, target: ast.Constant) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "console_scripts" and isinstance(value, (ast.List, ast.Tuple)):
                    if any(element is target for element in value.elts):
                        return True
    return False


def _docstring_nodes(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def is_wire_string(value: str) -> bool:
    if any(pattern.search(value) for pattern in _WIRE_PATTERNS) or _WORKER_LABEL.fullmatch(value):
        return True
    return bool(_KIND_LIKE.fullmatch(value) and _EMBEDDED_VERSION.search(value))


def _wire_name(value: str) -> str:
    flat = " ".join(value.split())
    return flat if len(flat) <= 160 else flat[:157] + "..."


def _config_strings(repository: Path, path: str) -> list[str]:
    text = (repository / path).read_text(encoding="utf-8", errors="replace")
    values: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            values.append(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    try:
        if path.endswith(".json"):
            walk(json.loads(text))
        elif path.endswith((".yaml", ".yml")):
            import yaml

            for document in yaml.safe_load_all(text):
                walk(document)
        else:
            return []
    except Exception:  # noqa: BLE001 - an unparsable config falls back to its raw tokens
        values.extend(re.findall(r"[\w.\-]+", text))
    return values


def _wire_hits(files: list[tuple[str, str, str]], repository: Path) -> list[Hit]:
    hits: dict[str, Hit] = {}
    for path, package, rest in files:
        if path.endswith(".py") and _in_tree(rest, PACKAGES[package]):
            tree = _parse(repository, path)
            if tree is None:
                continue
            docstrings = _docstring_nodes(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    if is_wire_string(node.value):
                        hit = Hit(SCAN_WIRE, path, "str", _wire_name(node.value))
                        hits[hit.key] = hit
        elif _in_tree(rest, CONFIG_TREE) and path.endswith((".json", ".yaml", ".yml")):
            for value in _config_strings(repository, path):
                if is_wire_string(value):
                    hit = Hit(SCAN_WIRE, path, "str", _wire_name(value))
                    hits[hit.key] = hit
    return list(hits.values())


def scan(which: str, repository: Path = REPOSITORY) -> list[Hit]:
    """Every hit of one scan, sorted and de-duplicated (computed once per process)."""

    return list(_scan(which, repository))


@functools.lru_cache(maxsize=8)
def _scan(which: str, repository: Path) -> tuple[Hit, ...]:
    files = package_files(repository)
    if which == SCAN_WIRE:
        found = _wire_hits(files, repository)
    else:
        found = _name_hits(which, files) + _symbol_hits(which, files, repository) + _console_script_hits(which, repository)
    return tuple(sorted(set(found)))


ALLOWLIST_COLUMNS = ("scan", "path", "kind", "name", "classification", "target", "confidence", "reason")
ALLOWLIST_CLASSIFICATIONS = (
    "family",
    "profile",
    "single-version-rename",
    "process-rename",
    "shim-delete",
    "wire-rename",
    "permanent",
)
ALLOWLIST_CONFIDENCES = ("design", "mechanical", "strip", "uncertain", "decided")


@dataclass(frozen=True)
class AllowEntry:
    """One reviewed allowlist line: a hit that may exist until its phase removes it."""

    key: str
    classification: str
    target: str
    confidence: str
    reason: str


def load_allowlist(path: Path) -> tuple[dict[str, AllowEntry], list[str]]:
    """Read the tab-separated allowlist. Returns ``(entries by key, problems)``.

    Lines starting with ``#`` and blank lines are ignored. A problem is reported for a malformed line, an
    unknown classification or confidence, an empty reason or target, and a duplicate key.
    """

    entries: dict[str, AllowEntry] = {}
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != len(ALLOWLIST_COLUMNS):
            problems.append(f"line {number}: expected {len(ALLOWLIST_COLUMNS)} tab-separated fields, found {len(fields)}")
            continue
        scan_name, hit_path, kind, name, classification, target, confidence, reason = fields
        key = f"{scan_name}|{hit_path}|{kind}|{name}"
        if classification not in ALLOWLIST_CLASSIFICATIONS:
            problems.append(f"line {number}: unknown classification {classification!r}")
        if confidence not in ALLOWLIST_CONFIDENCES:
            problems.append(f"line {number}: unknown confidence {confidence!r}")
        if not reason.strip() or not target.strip():
            problems.append(f"line {number}: an entry needs a reason and a target")
        if key in entries:
            problems.append(f"line {number}: duplicate entry {key}")
        entries[key] = AllowEntry(key, classification, target, confidence, reason)
    return entries, problems


def compare_with_allowlist(which: str, allowlist: Path, repository: Path = REPOSITORY) -> tuple[list[Hit], list[str], list[str]]:
    """``(hits missing from the allowlist, allowlist keys no hit uses, allowlist problems)`` for one scan."""

    entries, problems = load_allowlist(allowlist)
    hits = scan(which, repository)
    live = {hit.key for hit in hits}
    missing = [hit for hit in hits if hit.key not in entries]
    unused = sorted(key for key in entries if key.startswith(which + "|") and key not in live)
    return missing, unused, problems


def duplicate_basenames(package_dir: Path) -> dict[str, list[str]]:
    """Python file names that occur more than once under ``<package>/test`` and ``<package>/benchmark_test``.

    ``conftest.py`` and ``__init__.py`` may repeat. Paths are relative to ``package_dir`` and sorted.
    """

    seen: dict[str, list[str]] = {}
    for tree in TEST_TREES:
        for base, dirs, files in os.walk(package_dir / tree):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_PARTS]
            for file in files:
                if file.endswith(".py") and file not in {"__init__.py", "conftest.py"}:
                    seen.setdefault(file, []).append(str((Path(base) / file).relative_to(package_dir)))
    return {name: sorted(paths) for name, paths in sorted(seen.items()) if len(paths) > 1}


if __name__ == "__main__":
    for which in (SCAN_VERSIONED, SCAN_PROCESS, SCAN_WIRE):
        hits = scan(which)
        by_kind: dict[str, int] = {}
        for hit in hits:
            by_kind[hit.kind] = by_kind.get(hit.kind, 0) + 1
        print(which, len(hits), by_kind)
