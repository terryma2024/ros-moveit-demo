"""Explicit collection mode and the closed collection-scope record.

The non-head diagnostic-episode milestone runs the same acquisition chain as formal collection but with
one substitution: the target is preselected instead of chosen by Head Search. That substitution
changes exactly one thing — which startup prerequisites apply. It must never clear a non-Head
safety gate, and the formal mode must keep requiring a real Head qualification, so the applicability
rule lives here as a small closed function rather than as a flag the caller can forget.

`collection-scope.json` is the immutable record of that choice. It is closed, digested and bound to
the frozen inputs so the diagnostic identity survives into the audit, seal, QC, result and export
boundaries instead of living only in a command line.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re

SCOPE_KIND = "ACT_COLLECTION_SCOPE"
SCOPE_SCHEMA_VERSION = 1
SCOPE_FIELDS = frozenset({"kind", "schema_version", "mode", "scene_id", "seed", "inputs_sha256"})
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class CollectionMode(str, Enum):
    FORMAL = "formal"
    DIAGNOSTIC = "preselected_target_diagnostic"


def _resolved_mode(mode) -> CollectionMode:
    try:
        return CollectionMode(mode)
    except (TypeError, ValueError) as error:
        raise ValueError("COLLECTION_MODE_UNKNOWN") from error


def require_scope(mode, *, head_ready: bool, nonhead_ready: bool,
                  worker_count: int, resume: bool) -> CollectionMode:
    """Resolve the collection mode and refuse every inapplicable prerequisite combination.

    `nonhead_ready` is the common safety admission (robot, contact, controller, reset, collision,
    holding, release, sampling, identity, activation). It is required in both modes: the diagnostic
    mode removes the Head Search prerequisite only, never a non-Head one. The diagnostic mode is
    additionally fixed to one Worker and forbids resume, because it is a single frozen episode.
    """

    resolved = _resolved_mode(mode)
    if not nonhead_ready:
        raise ValueError("NONHEAD_SAFETY_NOT_READY")
    if resolved is CollectionMode.FORMAL and not head_ready:
        raise ValueError("HEAD_QUALIFICATION_REQUIRED")
    if resolved is CollectionMode.DIAGNOSTIC:
        if type(worker_count) is not int or worker_count != 1 or resume is not False:
            raise ValueError("DIAGNOSTIC_SCOPE_INVALID")
    return resolved


def build_collection_scope(mode, *, scene_id: str, seed: int, inputs_sha256: str) -> dict:
    """Build the closed scope document, refusing anything it could not later verify."""

    resolved = _resolved_mode(mode)
    if not isinstance(scene_id, str) or not scene_id or scene_id != scene_id.strip():
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if type(seed) is not int or seed < 0:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if not isinstance(inputs_sha256, str) or _HEX64.fullmatch(inputs_sha256) is None:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    return {"kind": SCOPE_KIND, "schema_version": SCOPE_SCHEMA_VERSION, "mode": resolved.value,
            "scene_id": scene_id, "seed": seed, "inputs_sha256": inputs_sha256}


def _canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def require_valid_scope(document, *, expected_inputs_sha256: str | None = None,
                        expected_mode: CollectionMode | str | None = None) -> dict:
    """Validate a scope document read back from disk; fail closed on any tampering."""

    if not isinstance(document, dict) or set(document) != SCOPE_FIELDS:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if document["kind"] != SCOPE_KIND or document["schema_version"] != SCOPE_SCHEMA_VERSION:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if document["mode"] not in (CollectionMode.FORMAL.value, CollectionMode.DIAGNOSTIC.value):
        raise ValueError("COLLECTION_SCOPE_INVALID")
    scene_id, seed = document["scene_id"], document["seed"]
    if not isinstance(scene_id, str) or not scene_id or scene_id != scene_id.strip():
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if type(seed) is not int or seed < 0:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if not isinstance(document["inputs_sha256"], str) or _HEX64.fullmatch(document["inputs_sha256"]) is None:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if expected_inputs_sha256 is not None and document["inputs_sha256"] != expected_inputs_sha256:
        raise ValueError("COLLECTION_SCOPE_INVALID")
    if expected_mode is not None and document["mode"] != _resolved_mode(expected_mode).value:
        # a copied directory with one edited word is not the identity this run was admitted under
        raise ValueError("COLLECTION_SCOPE_INVALID")
    return dict(document)


def write_collection_scope(scope: dict, output: Path) -> str:
    """Write the scope once, atomically and durably; a second write is refused, not merged."""

    document = require_valid_scope(scope)
    payload = _canonical(document)
    target = Path(output)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except FileExistsError as error:
        raise ValueError("COLLECTION_SCOPE_ALREADY_WRITTEN") from error
    except OSError as error:
        raise ValueError("COLLECTION_SCOPE_UNWRITABLE") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise ValueError("COLLECTION_SCOPE_UNWRITABLE") from error
    return hashlib.sha256(payload).hexdigest()


def read_collection_scope(path: Path, *, expected_inputs_sha256: str | None = None,
                          expected_mode: CollectionMode | str | None = None) -> dict:
    """Read back and validate a scope document without trusting its writer."""

    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise ValueError("COLLECTION_SCOPE_INVALID") from error
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("COLLECTION_SCOPE_INVALID") from error
    return require_valid_scope(document, expected_inputs_sha256=expected_inputs_sha256,
                               expected_mode=expected_mode)
