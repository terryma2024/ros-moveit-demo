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
        # carry the content locator through: a resolved episode that forgets where its content lives
        # forces the exporter to guess, and guessing is what this module exists to prevent
        resolved.append({"scene_id": episode["scene_id"],
                         "split": episode.get("split"),
                         "journal_sha256": entry["journal_sha256"],
                         "verifier_sha256": entry["verifier_sha256"],
                         **{key: entry[key] for key in ("content_path", "content_sha256")
                            if isinstance(entry.get(key), str)}})
    return tuple(resolved)


BUNDLE_KEYS = frozenset({"schema_version", "kind", "model_source", "dataset_sha256", "config_sha256",
                         "policy_path", "policy_sha256", "normalization"})


def _bundle_digest(value, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(code)
    return value


def load_bundle(path) -> dict:
    """Load a bundle document and confirm the policy it names is the policy it carries.

    A bundle is the only thing a runner is allowed to trust, so the document has to be closed, its policy
    has to live inside the bundle directory, and its digest has to match the bytes on disk. The
    normalisation provenance is checked too: statistics computed from anything but the train split would
    silently invalidate every later evaluation.
    """

    import hashlib

    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError("BUNDLE_MISSING")
    try:
        document = json.loads(target.read_bytes())
    except ValueError as error:
        raise ValueError("BUNDLE_INVALID") from error
    if (not isinstance(document, dict) or set(document) != BUNDLE_KEYS
            or document["schema_version"] != 1 or document["kind"] != "act_bundle"):
        raise ValueError("BUNDLE_INVALID")
    model_source = document["model_source"]
    if (not isinstance(model_source, dict) or set(model_source) != {"name", "sha256"}
            or not isinstance(model_source["name"], str) or not model_source["name"]):
        raise ValueError("BUNDLE_INVALID")
    _bundle_digest(model_source["sha256"], "BUNDLE_INVALID")
    _bundle_digest(document["dataset_sha256"], "BUNDLE_INVALID")
    _bundle_digest(document["config_sha256"], "BUNDLE_INVALID")
    normalization = document["normalization"]
    if not isinstance(normalization, dict) or normalization.get("split") != "train":
        raise ValueError("BUNDLE_NORMALIZATION_NOT_TRAIN_ONLY")
    policy_name = document["policy_path"]
    if (not isinstance(policy_name, str) or not policy_name or policy_name.startswith("/")
            or ".." in Path(policy_name).parts):
        raise ValueError("BUNDLE_POLICY_PATH_INVALID")
    policy = target.parent / policy_name
    if not policy.is_file() or policy.is_symlink():
        raise ValueError("BUNDLE_POLICY_MISSING")
    if hashlib.sha256(policy.read_bytes()).hexdigest() != document["policy_sha256"]:
        raise ValueError("BUNDLE_POLICY_DIGEST_MISMATCH")
    return document


def require_policy_interface(model) -> object:
    """A policy must offer `infer(observation) -> tuple[tuple[float, ...], ...]` and `reset()`."""

    if not callable(getattr(model, "infer", None)) or not callable(getattr(model, "reset", None)):
        raise ValueError("POLICY_INTERFACE_INVALID")
    return model


def load_policy(bundle_path, *, loader) -> object:
    """Load the policy a bundle names through an injected loader — never by import path."""

    bundle = load_bundle(bundle_path)
    if not callable(loader):
        raise ValueError("POLICY_LOADER_REQUIRED")
    return require_policy_interface(loader(bundle))


EXPORT_KEYS = frozenset({"schema_version", "kind", "episodes", "scene_count",
                         "source_manifest_sha256", "campaign_index_sha256"})
_STALE_DATASET_IDS = ("0917a",)
_COLLECTION_SPLITS = ("train", "validation", "offline_test")
_NEWLINE = bytes((10,))


def export_dataset(committed, output, *, source_manifest_sha256: str,
                   campaign_index_sha256: str) -> dict:
    """Write the immutable export: one document per committed episode plus a digest manifest.

    The export is written once. An existing output directory is a refusal rather than a place to append,
    because a dataset that grows underneath a training run invalidates every metric computed from it. The
    episode order is the order the caller resolved -- the frozen manifest order -- and each episode's bytes
    are hashed into the manifest so a later edit is detectable.
    """

    import hashlib
    import os

    _bundle_digest(source_manifest_sha256, "EXPORT_SOURCE_DIGEST_INVALID")
    _bundle_digest(campaign_index_sha256, "EXPORT_INDEX_DIGEST_INVALID")
    if not isinstance(committed, (list, tuple)):
        raise ValueError("EXPORT_EPISODES_INVALID")
    episodes = list(committed)
    if not episodes:
        raise ValueError("EXPORT_EMPTY")
    target = Path(output)
    if target.exists() or target.is_symlink():
        raise ValueError("EXPORT_OUTPUT_EXISTS")

    records, seen = [], set()
    for episode in episodes:
        if not isinstance(episode, dict) or not isinstance(episode.get("scene_id"), str):
            raise ValueError("EXPORT_EPISODES_INVALID")
        scene_id = episode["scene_id"]
        if scene_id in seen:
            raise ValueError("EXPORT_DUPLICATE_SCENE")
        seen.add(scene_id)
        split = episode.get("split")
        if split is not None and split not in _COLLECTION_SPLITS:
            raise ValueError("EXPORT_SPLIT_FORBIDDEN")
        if any(stale in scene_id or stale in str(episode.get("dataset_id", ""))
               for stale in _STALE_DATASET_IDS):
            raise ValueError("EXPORT_STALE_DATASET_ID")
        if episode.get("status", "PASSED") != "PASSED":
            raise ValueError("EXPORT_EPISODE_NOT_PASSED")
        content = episode.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("EXPORT_EPISODE_CONTENT_MISSING")
        payload = json.dumps(content, sort_keys=True, indent=2).encode() + _NEWLINE
        records.append({"scene_id": scene_id, "split": split,
                        "content_sha256": hashlib.sha256(payload).hexdigest(),
                        "payload": payload})

    target.mkdir(parents=True)
    episodes_dir = target / "episodes"
    episodes_dir.mkdir()
    for record in records:
        path = episodes_dir / (record["scene_id"] + ".json")
        temporary = path.with_name(path.name + ".partial")
        with open(temporary, "wb") as handle:
            handle.write(record["payload"])
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    document = {"schema_version": 1, "kind": "act_dataset_export", "scene_count": len(records),
                "source_manifest_sha256": source_manifest_sha256,
                "campaign_index_sha256": campaign_index_sha256,
                "episodes": [{"scene_id": record["scene_id"], "split": record["split"],
                              "content_sha256": record["content_sha256"]} for record in records]}
    manifest_path = target / "export-manifest.json"
    manifest_path.write_text(json.dumps(document, sort_keys=True, indent=2) + chr(10))
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {**document, "manifest_path": str(manifest_path), "export_sha256": digest}
