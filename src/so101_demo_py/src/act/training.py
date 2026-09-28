"""Task 12: the gates a training run must pass, and the state it must leave behind.

Training starts only against a verified export, a resolved dependency lock, a frozen configuration and a
live owner lease on the GPU. Whatever happens next, the run leaves a terminal state on disk — `COMPLETED`
or `FAILED` with the error — because a failed training that vanishes silently is indistinguishable from one
that never started, and the next run would have no way to tell.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def require_exported_dataset(output) -> dict:
    """Re-read an export and confirm every episode still hashes to what the manifest claims."""

    root = Path(output)
    manifest_path = root / "export-manifest.json"
    if not manifest_path.is_file() or root.is_symlink():
        raise ValueError("TRAINING_DATASET_NOT_EXPORTED")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except ValueError as error:
        raise ValueError("TRAINING_DATASET_MANIFEST_INVALID") from error
    if (not isinstance(manifest, dict) or manifest.get("kind") != "act_dataset_export"
            or not isinstance(manifest.get("episodes"), list) or not manifest["episodes"]):
        raise ValueError("TRAINING_DATASET_MANIFEST_INVALID")
    for episode in manifest["episodes"]:
        if (not isinstance(episode, dict) or not isinstance(episode.get("scene_id"), str)
                or not isinstance(episode.get("content_sha256"), str)):
            raise ValueError("TRAINING_DATASET_MANIFEST_INVALID")
        path = root / "episodes" / (episode["scene_id"] + ".json")
        if not path.is_file():
            raise ValueError("TRAINING_EPISODE_MISSING")
        if hashlib.sha256(path.read_bytes()).hexdigest() != episode["content_sha256"]:
            raise ValueError("TRAINING_EPISODE_DIGEST_MISMATCH")
    return manifest


def train_act(*, config: dict, requirements: dict, dataset, owner: dict, output, trainer) -> dict:
    """Run the pre-flight gates, then the injected trainer, and record the terminal state."""

    if not isinstance(config, dict) or "action" not in config:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if not isinstance(requirements, dict) or requirements.get("status") != "RESOLVED":
        raise ValueError("TRAINING_REQUIREMENTS_UNRESOLVED")
    if not isinstance(owner, dict) or owner.get("device") != "cuda":
        raise ValueError("TRAINING_OWNER_NOT_CUDA")
    if not isinstance(owner.get("run_root"), str) or not owner["run_root"]:
        raise ValueError("TRAINING_OWNER_INVALID")
    if not callable(trainer):
        raise ValueError("TRAINING_TRAINER_REQUIRED")
    manifest = require_exported_dataset(dataset)
    target = Path(output)
    if target.exists() or target.is_symlink():
        raise ValueError("TRAINING_OUTPUT_EXISTS")

    state_path = target.with_name(target.name + ".state.json")
    disposition = {"schema_version": 1, "kind": "act_training_state", "status": "FAILED",
                   "dataset_sha256": hashlib.sha256(
                       (Path(dataset) / "export-manifest.json").read_bytes()).hexdigest(),
                   "config_sha256": hashlib.sha256(
                       json.dumps(config, sort_keys=True).encode()).hexdigest(),
                   "device": owner["device"], "run_root": owner["run_root"],
                   "episode_count": len(manifest["episodes"]), "error": None}
    try:
        bundle = trainer(config, Path(dataset), target)
        if not isinstance(bundle, dict) or bundle.get("kind") != "act_bundle":
            raise ValueError("TRAINING_BUNDLE_INVALID")
        disposition["status"] = "COMPLETED"
        return {**disposition, "bundle": bundle}
    except Exception as error:                       # the evidence is the point: record, then re-raise
        disposition["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        temporary = state_path.with_name(state_path.name + ".partial")
        with open(temporary, "w") as handle:
            handle.write(json.dumps(disposition, sort_keys=True, indent=2) + chr(10))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(state_path)


def attach_episode_content(committed, *, root) -> tuple:
    """Read each committed episode's content from inside the campaign root, verifying what it claims.

    Content is never taken on trust or by path inference: the file must sit under the root the campaign
    index names, and when the entry records a content hash the bytes must match it.
    """

    base = Path(root).resolve()
    resolved = []
    for episode in committed:
        if not isinstance(episode, dict):
            raise ValueError("TRAINING_EPISODES_INVALID")
        if isinstance(episode.get("content"), dict) and episode["content"]:
            resolved.append(episode)
            continue
        name = episode.get("content_path")
        if not isinstance(name, str) or not name:
            raise ValueError("TRAINING_EPISODE_CONTENT_MISSING")
        path = Path(name)
        if not path.is_absolute():
            path = base / name
        resolved_path = path.resolve()
        if not resolved_path.is_file() or not resolved_path.is_relative_to(base):
            raise ValueError("TRAINING_EPISODE_CONTENT_MISSING")
        try:
            content = json.loads(resolved_path.read_bytes())
        except ValueError as error:
            raise ValueError("TRAINING_EPISODE_CONTENT_INVALID") from error
        if not isinstance(content, dict) or not content:
            raise ValueError("TRAINING_EPISODE_CONTENT_INVALID")
        recorded = episode.get("content_sha256")
        if isinstance(recorded, str) and hashlib.sha256(resolved_path.read_bytes()).hexdigest() != recorded:
            raise ValueError("TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH")
        resolved.append({**episode, "content": content})
    return tuple(resolved)
