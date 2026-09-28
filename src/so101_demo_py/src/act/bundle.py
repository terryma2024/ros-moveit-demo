"""Task 12: decide which episodes a training bundle may contain.

Two rules carry the weight here. Normalisation statistics may be computed from the train split only, so
`training_rows` is the only sanctioned way to select rows for them. And an episode directory is not an
episode: it counts only when the coordinator committed it and a verifier receipt agrees with the journal
hash, so a seal that nobody committed — or two receipts that disagree — never reaches a dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

_EPISODE_KEYS = ("scene_id", "journal_sha256", "verifier_sha256")


def training_rows(rows) -> list:
    """The rows normalisation may use: the train split, and nothing else."""

    if not isinstance(rows, (list, tuple)):
        raise ValueError("TRAINING_ROWS_INVALID")
    selected = []
    for row in rows:
        if not isinstance(row, dict) or "split" not in row:
            raise ValueError("TRAINING_ROWS_INVALID")
        if row["split"] == "train":
            selected.append(row)
    return selected


def _index(path) -> dict:
    target = Path(path)
    if not target.is_file():
        return {}                      # nothing was committed, so nothing may be exported
    try:
        document = json.loads(target.read_bytes())
    except ValueError as error:
        raise ValueError("CAMPAIGN_INDEX_INVALID") from error
    if not isinstance(document, dict):
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    committed = document.get("committed_episodes", [])
    if not isinstance(committed, list):
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    return {entry["scene_id"]: entry for entry in committed
            if isinstance(entry, dict) and isinstance(entry.get("scene_id"), str)}


def resolve_committed_episodes(*, manifest: dict, campaign_index) -> tuple:
    """Episodes the coordinator committed, with a verifier receipt that agrees with the journal."""

    if not isinstance(manifest, dict) or not isinstance(manifest.get("episodes"), list):
        raise ValueError("MANIFEST_INVALID")
    committed = _index(campaign_index)
    resolved = []
    for episode in manifest["episodes"]:
        if not isinstance(episode, dict) or not isinstance(episode.get("scene_id"), str):
            raise ValueError("MANIFEST_INVALID")
        if episode.get("status") != "PASSED":
            continue                                   # a business failure is retained, not exported
        entry = committed.get(episode["scene_id"])
        if entry is None:
            continue                                   # a directory without a coordinator commit
        if any(not isinstance(entry.get(key), str) or len(entry[key]) != 64
               for key in _EPISODE_KEYS[1:]):
            raise ValueError("EPISODE_RECEIPT_INVALID")
        if entry.get("journal_sha256") != entry.get("verifier_sha256"):
            raise ValueError("EPISODE_RECEIPT_CONFLICT")
        resolved.append({"scene_id": episode["scene_id"],
                         "journal_sha256": entry["journal_sha256"],
                         "verifier_sha256": entry["verifier_sha256"]})
    return tuple(resolved)
