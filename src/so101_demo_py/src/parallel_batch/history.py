"""Pure historical reading of retained parallel-validation documents.

This module is deliberately tiny and dependency-free: it decodes bytes from an earlier
generation so the operator can still inspect old runs, and it must never import the active
budget/measurement implementation, never start a probe and never perform a product action.
Reading a historical record cannot authorize execution; :func:`describe` says so explicitly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

#: Versions that may be read for history. Version 3 is the active generation; reading it
#: here is still read-only and grants nothing.
SUPPORTED_HISTORY_VERSIONS = (1, 2, 3)

HISTORY_KINDS = {
    1: "LEGACY_V1",
    2: "CERTIFIED_V2",
    3: "ACTIVE_V3",
}


class HistoryError(ValueError):
    """A retained document could not be read as history."""


class ReadOnlyHistory(dict):
    """A mapping that is still a dict but refuses every mutation.

    Historical records are evidence: a caller that tries to "fix up" one has a bug, and it
    fails here instead of silently editing an audit artifact.
    """

    def _refuse(self, *args, **kwargs):
        raise TypeError("history records are read-only")

    __setitem__ = _refuse
    __delitem__ = _refuse
    clear = _refuse
    pop = _refuse
    popitem = _refuse
    setdefault = _refuse
    update = _refuse
    __ior__ = _refuse


def _decode(path: Path) -> tuple[bytes, object]:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise HistoryError(f"HISTORY_READ_FAILED: {path}") from error
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise HistoryError(f"HISTORY_DECODE_FAILED: {path}") from error
    return raw, document


def describe(document: object, *, raw_sha256: str, byte_count: int) -> dict:
    """Closed description of a retained document; read-only by construction."""

    if not isinstance(document, Mapping):
        raise HistoryError("HISTORY_MAPPING")
    version = document.get("schema_version")
    if version not in SUPPORTED_HISTORY_VERSIONS:
        raise HistoryError(f"HISTORY_SCHEMA_VERSION: {version!r}")
    return ReadOnlyHistory({
        "schema_version": version,
        "kind": HISTORY_KINDS[version],
        "raw_sha256": raw_sha256,
        "bytes": byte_count,
        "readonly": True,
        "authorizes_execution": False,
        "payload": MappingProxyType(dict(document)),
    })


def load_history(path: Path) -> dict:
    """Read a retained document for display/audit. Never converts it into an active request."""

    raw, document = _decode(Path(path))
    return describe(document, raw_sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))


def load_jsonl_history(path: Path) -> list[dict]:
    """Read a retained JSON-lines record (samples, checkpoints) without interpreting it."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise HistoryError(f"HISTORY_READ_FAILED: {path}") from error
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise HistoryError(f"HISTORY_JSONL_INVALID: {path}:{number}") from error
    return entries


def history_versions() -> tuple[int, ...]:
    return SUPPORTED_HISTORY_VERSIONS
