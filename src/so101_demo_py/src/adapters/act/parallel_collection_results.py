"""Task 11A results: append-once scene records, verified by digest.

A scene result is published exactly once. Re-publishing the identical document is idempotent — a wave
that is re-entered after a crash must be able to finish without rewriting history — while a *different*
document for a scene that already has a result is refused, because that would silently replace a sealed
outcome. Verification re-reads the bytes rather than trusting the recorded digest.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_RESULT_KEYS = frozenset({"scene_id", "status", "qc", "done", "interventions",
                          "coordinator_committed", "reset_epoch"})


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ActCollectionResultStore:
    """Publishes one digest-verified JSON document per scene under `root/results`."""

    def __init__(self, root) -> None:
        self.root = Path(root)
        if not self.root.is_absolute() or not self.root.is_dir() or self.root.is_symlink():
            raise ValueError("RESULT_ROOT_INVALID")
        self.directory = self.root / "results"

    def _target(self, scene_id: str) -> Path:
        if not isinstance(scene_id, str) or not scene_id or "/" in scene_id or ".." in scene_id:
            raise ValueError("RESULT_SCENE_ID_INVALID")
        return self.directory / f"{scene_id}.json"

    def publish(self, record: dict) -> dict:
        if not isinstance(record, dict) or not _RESULT_KEYS <= set(record):
            raise ValueError("RESULT_INVALID")
        if record.get("status") not in ("PASSED", "FAILED"):
            raise ValueError("RESULT_INVALID")
        target = self._target(record["scene_id"])
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record, sort_keys=True, indent=2).encode() + b"\n"
        if target.exists():
            existing = target.read_bytes()
            if existing == payload:
                return {"path": str(target), "sha256": _digest(existing)}   # idempotent re-entry
            raise ValueError("SCENE_TERMINAL_STATE_IMMUTABLE")
        temporary = target.with_name(target.name + ".partial")
        with open(temporary, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
        return {"path": str(target), "sha256": _digest(payload)}

    def read(self, scene_id: str) -> dict:
        target = self._target(scene_id)
        if not target.is_file():
            raise ValueError("RESULT_MISSING")
        try:
            return json.loads(target.read_bytes())
        except ValueError as error:
            raise ValueError("RESULT_INVALID") from error


    def has_result(self, scene_id: str) -> bool:
        """True when this scene already has a sealed result, so it must not be collected again."""

        try:
            self.read(scene_id)
        except ValueError:
            return False
        return True

class ActCollectionResultVerifier:
    """Confirms a published result still matches the bytes it claims."""

    def __init__(self, store: ActCollectionResultStore) -> None:
        self.store = store

    def verify(self, entry: dict) -> dict:
        if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("sha256"), str) or len(entry["sha256"]) != 64):
            raise ValueError("RESULT_ENTRY_INVALID")
        path = Path(entry["path"])
        if not path.is_file():
            raise ValueError("RESULT_MISSING")
        actual = _digest(path.read_bytes())
        if actual != entry["sha256"]:
            raise ValueError("RESULT_DIGEST_MISMATCH")
        return json.loads(path.read_bytes())

    def has_result(self, scene_id: str) -> bool:
        """True when this scene already has a sealed result, so it must not be collected again."""

        try:
            self.read(scene_id)
        except ValueError:
            return False
        return True
