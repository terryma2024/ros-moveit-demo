"""The gates a training run must pass, and the state it must leave behind.

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


def _file_digest(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require_exported_dataset(output) -> dict:
    """Re-read an export and confirm every episode and every frame still hashes to what the manifest claims."""

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
                or not isinstance(episode.get("content_sha256"), str)
                or not isinstance(episode.get("frames"), dict) or not episode["frames"]):
            raise ValueError("TRAINING_DATASET_MANIFEST_INVALID")
        path = root / "episodes" / (episode["scene_id"] + ".json")
        if not path.is_file():
            raise ValueError("TRAINING_EPISODE_MISSING")
        if hashlib.sha256(path.read_bytes()).hexdigest() != episode["content_sha256"]:
            raise ValueError("TRAINING_EPISODE_DIGEST_MISMATCH")
        prefix = f"episodes/{episode['scene_id']}/frames/"
        for relative, digest in episode["frames"].items():
            if (not isinstance(relative, str) or not relative.startswith(prefix) or ".." in Path(relative).parts
                    or not isinstance(digest, str) or len(digest) != 64):
                raise ValueError("TRAINING_DATASET_MANIFEST_INVALID")
            frame = root / relative
            if not frame.is_file() or frame.is_symlink():
                raise ValueError("TRAINING_EPISODE_FRAME_MISSING")
            if _file_digest(frame) != digest:
                raise ValueError("TRAINING_EPISODE_FRAME_DIGEST_MISMATCH")
    return manifest


#: the directory a trainer receives: the export manifest (its digest is the dataset provenance) and the whitelisted samples only
TRAINING_VIEW_SUFFIX = ".training-view"
TRAINING_SAMPLES_FILE = "training-samples.json"


def materialize_training_view(dataset, view, samples) -> Path:
    """Write the training view: a copy of the export manifest and the whitelisted samples, atomically, once."""

    view = Path(view)
    view.mkdir(parents=True)
    (view / "export-manifest.json").write_bytes((Path(dataset) / "export-manifest.json").read_bytes())
    # the view holds no episodes and no frames: the trainer resolves frame paths against the dataset root named here and
    # re-verifies their digests (the view's copy of the export manifest is byte-identical to the dataset's)
    payload = (json.dumps({"kind": "act_training_samples", "schema_version": 1, "dataset_root": str(Path(dataset).resolve()),
                           "samples": samples}, sort_keys=True,
                          indent=2, allow_nan=False) + chr(10)).encode()
    temporary = view / (TRAINING_SAMPLES_FILE + ".partial")
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(view / TRAINING_SAMPLES_FILE)
    return view


def load_training_samples(output, *, manifest=None) -> list:
    """The training samples of a verified export, read through the whitelist (observation and action only).

    The export is re-verified (every episode hashes to its manifest entry), and each episode is read again through
    `bundle.training_content`: a file edited together with its digest still cannot put an audit, contact, force or collision field
    in front of the trainer. A sample is `{scene_id, split, rows}`; a flat content has no rows."""

    from .bundle import training_content

    if manifest is None:
        manifest = require_exported_dataset(output)
    root = Path(output)
    samples = []
    for episode in manifest["episodes"]:
        content = training_content(json.loads((root / "episodes" / (episode["scene_id"] + ".json")).read_bytes()))
        rows = content.get("rows")
        if rows is None:
            rows = ([{"observation": content["observation"], "action": content["action"]}]
                    if "observation" in content and "action" in content else [])
        samples.append({"scene_id": episode["scene_id"], "split": episode.get("split"), "rows": rows})
    return samples


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
    # The trainer is given a training VIEW, never the export: the digests are re-checked and every episode is re-read through the
    # whitelist (observation and action only), so no audit, contact, force or collision field can reach it.
    view = target.with_name(target.name + TRAINING_VIEW_SUFFIX)
    if view.exists() or view.is_symlink():
        raise ValueError("TRAINING_OUTPUT_EXISTS")
    samples = load_training_samples(dataset, manifest=manifest)

    state_path = target.with_name(target.name + ".state.json")
    disposition = {"schema_version": 1, "kind": "act_training_state", "status": "FAILED",
                   "dataset_sha256": hashlib.sha256(
                       (Path(dataset) / "export-manifest.json").read_bytes()).hexdigest(),
                   "config_sha256": hashlib.sha256(
                       json.dumps(config, sort_keys=True).encode()).hexdigest(),
                   "device": owner["device"], "run_root": owner["run_root"],
                   "episode_count": len(manifest["episodes"]), "error": None}
    try:
        materialize_training_view(dataset, view, samples)
        bundle = trainer(config, view, target)
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


def attach_episode_content(committed, *, root, workers=None) -> tuple:
    """Read each committed episode's content, verifying what it claims. The content hash is always verified.

    The source is the sealed recorder rows of the committed episode (`bundle.sealed_episode_content`: the seal is the one the
    coordinator commit bound and `records.jsonl` hashes to the seal `files` map). An entry that names a ``content_path`` is read from
    inside the campaign root and must carry a ``content_sha256`` that its bytes match; an entry that carries inline ``content`` must
    carry a ``content_sha256`` equal to the canonical JSON digest of that content. Nothing is taken on trust or by path inference.

    ``workers`` > 1 first verifies, across a process pool, the commits of the episodes that read sealed rows; the loop below is the
    serial path in every case, so the digest checks run every time and the first refusal in order is the one raised.
    """

    from .bundle import _prime_verification_memo, resolve_workers, sealed_episode_content

    workers = resolve_workers(workers)
    if workers > 1:
        _prime_verification_memo(
            [episode for episode in committed if isinstance(episode, dict) and isinstance(episode.get("collection_evidence"), dict)
             and not (isinstance(episode.get("content"), dict) and episode["content"])
             and not (isinstance(episode.get("content_path"), str) and episode["content_path"])], workers)
    base = Path(root).resolve()
    resolved = []
    for episode in committed:
        if not isinstance(episode, dict):
            raise ValueError("TRAINING_EPISODES_INVALID")
        recorded = episode.get("content_sha256")
        if isinstance(episode.get("content"), dict) and episode["content"]:
            if not isinstance(recorded, str):
                raise ValueError("TRAINING_EPISODE_CONTENT_DIGEST_MISSING")
            canonical = json.dumps(episode["content"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            if hashlib.sha256(canonical).hexdigest() != recorded:
                raise ValueError("TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH")
            resolved.append(episode)
            continue
        name = episode.get("content_path")
        if not isinstance(name, str) or not name:
            if isinstance(episode.get("collection_evidence"), dict):
                resolved.append({**episode, "content": sealed_episode_content(episode)})
                continue
            raise ValueError("TRAINING_EPISODE_CONTENT_MISSING")
        path = Path(name)
        if not path.is_absolute():
            path = base / name
        resolved_path = path.resolve()
        if not resolved_path.is_file() or not resolved_path.is_relative_to(base):
            raise ValueError("TRAINING_EPISODE_CONTENT_MISSING")
        raw = resolved_path.read_bytes()
        if not isinstance(recorded, str):
            raise ValueError("TRAINING_EPISODE_CONTENT_DIGEST_MISSING")
        if hashlib.sha256(raw).hexdigest() != recorded:
            raise ValueError("TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH")
        try:
            content = json.loads(raw)
        except ValueError as error:
            raise ValueError("TRAINING_EPISODE_CONTENT_INVALID") from error
        if not isinstance(content, dict) or not content:
            raise ValueError("TRAINING_EPISODE_CONTENT_INVALID")
        resolved.append({**episode, "content": content})
    return tuple(resolved)
