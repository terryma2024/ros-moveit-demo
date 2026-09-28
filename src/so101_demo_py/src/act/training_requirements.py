"""Task 12: the pinned training dependencies.

A training run may only start against a **resolved** lock: every package pinned by version and source SHA,
with the resolver provenance recorded. Until the selected LeRobot / PyTorch release has actually been
resolved inside a training interpreter, this stays `UNRESOLVED` and every attempt to require it fails
closed — an unpinned environment is exactly what makes a trained artefact unreproducible.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_LOCK_KEYS = frozenset({"schema_version", "kind", "status", "resolver", "packages"})
_RESOLVER_KEYS = frozenset({"python", "resolved_at", "index_sha256"})
_PACKAGE_KEYS = frozenset({"name", "version", "sha256"})
_STATUSES = ("UNRESOLVED", "RESOLVED")


def load_training_requirements(path) -> dict:
    """Load the closed lock document, whatever state it is in."""

    target = Path(path)
    if not target.is_file():
        raise ValueError("TRAINING_REQUIREMENTS_MISSING")
    try:
        document = yaml.safe_load(target.read_bytes())
    except yaml.YAMLError as error:
        raise ValueError("TRAINING_REQUIREMENTS_INVALID") from error
    if (not isinstance(document, dict) or set(document) != _LOCK_KEYS
            or document["schema_version"] != 1 or document["kind"] != "act_training_requirements"
            or document["status"] not in _STATUSES):
        raise ValueError("TRAINING_REQUIREMENTS_INVALID")
    packages = document["packages"]
    if not isinstance(packages, list):
        raise ValueError("TRAINING_REQUIREMENTS_INVALID")
    if document["status"] == "UNRESOLVED":
        if document["resolver"] is not None or packages:
            # claiming to be unresolved while carrying resolved content would hide which is authoritative
            raise ValueError("TRAINING_REQUIREMENTS_INVALID")
        return document
    resolver = document["resolver"]
    if not isinstance(resolver, dict) or set(resolver) != _RESOLVER_KEYS:
        raise ValueError("TRAINING_REQUIREMENTS_INVALID")
    if not isinstance(resolver["python"], str) or not resolver["python"]:
        raise ValueError("TRAINING_REQUIREMENTS_INVALID")
    if not isinstance(resolver["resolved_at"], str) or not resolver["resolved_at"]:
        raise ValueError("TRAINING_REQUIREMENTS_INVALID")
    if not isinstance(resolver["index_sha256"], str) or len(resolver["index_sha256"]) != 64:
        raise ValueError("TRAINING_REQUIREMENTS_INVALID")
    if not packages:
        raise ValueError("TRAINING_REQUIREMENTS_EMPTY")
    seen = set()
    for package in packages:
        if not isinstance(package, dict) or set(package) != _PACKAGE_KEYS:
            raise ValueError("TRAINING_REQUIREMENTS_INVALID")
        if not isinstance(package["name"], str) or not package["name"]:
            raise ValueError("TRAINING_REQUIREMENTS_INVALID")
        if not isinstance(package["version"], str) or not package["version"]:
            raise ValueError("TRAINING_REQUIREMENTS_UNPINNED")
        if not isinstance(package["sha256"], str) or len(package["sha256"]) != 64:
            # a version without its source hash is not a pin
            raise ValueError("TRAINING_REQUIREMENTS_UNPINNED")
        if package["name"] in seen:
            raise ValueError("TRAINING_REQUIREMENTS_INVALID")
        seen.add(package["name"])
    return document


def require_resolved_requirements(path) -> dict:
    """The lock a training run must present before it may start."""

    document = load_training_requirements(path)
    if document["status"] != "RESOLVED":
        raise ValueError("TRAINING_REQUIREMENTS_UNRESOLVED")
    return document
