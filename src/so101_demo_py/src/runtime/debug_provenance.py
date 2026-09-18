"""DEBUG-only installed-artifact manifest.

The manifest is a *diagnostic observation* of what was installed. It is never a
runtime prerequisite: no runtime path reads it, hashes it or compares its commit, so a
missing, corrupt, stale or foreign manifest cannot change execution availability or
authority. A separate explicitly requested reader inspects it and prints diagnostics.

Determinism policy
------------------
* Entries are install-relative POSIX paths plus the actual file-byte SHA-256; no
  absolute prefix, timestamp, or self-hash appears, so the same bytes produce the same
  manifest anywhere the tree is relocated.
* Coverage: every regular file under the prefix except the manifest itself,
  ``__pycache__``/bytecode, ``*.pyc``/``*.pyo``, logs and caches, and the colcon
  setup/dsv shims that are regenerated per install.
* Symlinks are recorded with ``symlink_target`` and hashed only when the target stays
  inside the prefix (``EXTERNAL`` targets record ``sha256: null``); traversal never
  follows a link out of the prefix.
* The source commit and dirty state are nullable observations taken from the build
  source tree when Git is available; a no-Git build records ``null`` honestly.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_KIND = "DEBUG_INSTALL_PROVENANCE"
MANIFEST_NAME = "debug-provenance-manifest.json"

_EXCLUDED_DIRECTORIES = frozenset({"__pycache__", ".cache", "log", "logs"})
_EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".log")
_EXCLUDED_NAMES = frozenset({
    "COLCON_IGNORE", "package.dsv", ".colcon_install_layout", "setup.sh", "setup.bash",
    "setup.zsh", "setup.ps1", "local_setup.sh", "local_setup.bash", "local_setup.zsh",
    "local_setup.ps1",
})
# The prefix-relative location of the manifest written by the final installation stage.
MANIFEST_RELATIVE_PATH = f"share/so101_demo_py/{MANIFEST_NAME}"


@dataclass(frozen=True, slots=True)
class DebugArtifact:
    path: str
    sha256: str | None
    symlink_target: str | None = None

    def as_document(self) -> dict[str, object]:
        document: dict[str, object] = {"path": self.path, "sha256": self.sha256}
        if self.symlink_target is not None:
            document["symlink_target"] = self.symlink_target
        return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(prefix: Path, path: Path) -> bool:
    relative = path.relative_to(prefix)
    if relative.as_posix() == MANIFEST_RELATIVE_PATH or path.name == MANIFEST_NAME:
        return True
    if any(part in _EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
        return True
    if path.name in _EXCLUDED_NAMES or path.name.startswith("_local_setup_util_"):
        return True
    return path.name.endswith(_EXCLUDED_SUFFIXES)


def collect_debug_artifacts(
    prefix: Path, *, prefix_root: Path | None = None
) -> tuple[DebugArtifact, ...]:
    """Walk the installed prefix deterministically; never leave the prefix boundary."""

    prefix = Path(prefix).resolve(strict=True)
    if not prefix.is_dir():
        raise ValueError("DEBUG_MANIFEST_PREFIX_INVALID")
    del prefix_root
    artifacts: list[DebugArtifact] = []
    for current, directories, files in os.walk(prefix, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if not _excluded(prefix, Path(current) / name)
        )
        for name in sorted(files):
            path = Path(current) / name
            if _excluded(prefix, path):
                continue
            relative = path.relative_to(prefix).as_posix()
            if path.is_symlink():
                target = os.readlink(path)
                resolved = (path.parent / target).resolve()
                inside = resolved.is_relative_to(prefix) and resolved.is_file()
                artifacts.append(DebugArtifact(
                    path=relative,
                    sha256=_sha256(resolved) if inside else None,
                    symlink_target=target if inside else "EXTERNAL",
                ))
                continue
            if not path.is_file():
                continue
            artifacts.append(DebugArtifact(path=relative, sha256=_sha256(path)))
    return tuple(artifacts)


def _observed_commit(source_root: Path | None) -> tuple[str | None, bool | None]:
    """Build/install-only Git observation (the runtime never reaches this)."""

    from .provenance import (
        observed_source_commit_from_git, observed_source_dirty_from_git)

    commit = observed_source_commit_from_git(source_root)
    return commit, observed_source_dirty_from_git(source_root)


def build_debug_manifest(
    prefix: Path, *, source_root: Path | None = None,
    manifest_path: Path | None = None,
) -> Mapping[str, object]:
    """Build the deterministic DEBUG manifest document (no timestamp, no self-hash)."""

    prefix = Path(prefix).resolve(strict=True)
    target = (prefix / MANIFEST_RELATIVE_PATH) if manifest_path is None else Path(manifest_path)
    try:
        relative_target = target.resolve().relative_to(prefix).as_posix()
    except ValueError as error:
        raise ValueError("DEBUG_MANIFEST_PATH_OUTSIDE_PREFIX") from error
    if relative_target != MANIFEST_RELATIVE_PATH:
        raise ValueError("DEBUG_MANIFEST_PATH_INVALID")
    commit, dirty = _observed_commit(source_root)
    artifacts = collect_debug_artifacts(prefix, prefix_root=prefix)
    return MappingProxyType({
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "authority": "DEBUG_ONLY_NOT_RUNTIME_AUTHORITY",
        "package": "so101_demo_py",
        "source_commit": commit,
        "source_dirty": dirty,
        "policy": {
            "path_base": "install_relative_posix",
            "excluded_directories": sorted(_EXCLUDED_DIRECTORIES),
            "excluded_suffixes": list(_EXCLUDED_SUFFIXES),
            "excluded_names": sorted(_EXCLUDED_NAMES),
            "symlinks": "recorded_and_hashed_only_inside_prefix",
            "self": MANIFEST_RELATIVE_PATH,
        },
        "artifacts": [artifact.as_document() for artifact in artifacts],
    })


def write_debug_manifest(
    prefix: Path, *, source_root: Path | None = None,
    manifest_path: Path | None = None,
) -> Path:
    """Emit the manifest after installation mutations; deterministic bytes."""

    prefix = Path(prefix).resolve(strict=True)
    target = (prefix / MANIFEST_RELATIVE_PATH) if manifest_path is None else Path(manifest_path)
    document = build_debug_manifest(
        prefix, source_root=source_root, manifest_path=target)
    payload = (
        json.dumps(dict(document), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    temporary.write_bytes(payload)
    os.replace(temporary, target)
    return target


def read_debug_manifest(prefix: Path) -> Mapping[str, object] | None:
    """Explicitly requested DEBUG reader; never called by a runtime decision path."""

    target = Path(prefix) / MANIFEST_RELATIVE_PATH
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or document.get("kind") != MANIFEST_KIND:
        return None
    return document


def coverage_summary(artifacts: Sequence[DebugArtifact]) -> dict[str, object]:
    """Small deterministic diagnostic summary for the explicit debug reader."""

    kinds = {"modules": 0, "executables": 0, "share": 0, "other": 0}
    for artifact in artifacts:
        if artifact.path.startswith("lib/python") and artifact.path.endswith(".py"):
            kinds["modules"] += 1
        elif artifact.path.startswith("lib/so101_demo_py/"):
            kinds["executables"] += 1
        elif artifact.path.startswith("share/"):
            kinds["share"] += 1
        else:
            kinds["other"] += 1
    return {"count": len(artifacts), **kinds}
