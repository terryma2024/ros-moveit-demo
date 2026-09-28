"""Task 12A: read-only evaluation of a frozen bundle on the Offline Test split.

Padded frames are not evidence. A tail padded to complete an action chunk must never contribute to a
joint metric, and a metric must never quietly shrink its denominator to make a bad row disappear — the
mask decides which frames count, and a frame that is malformed is refused rather than skipped.
"""

from __future__ import annotations

import math
from pathlib import Path

_JOINTS = 6


def _row(row, label: str) -> list:
    if not isinstance(row, (list, tuple)) or len(row) != _JOINTS:
        raise ValueError("MASK_SHAPE_INVALID")
    values = []
    for value in row:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label}_INVALID")
        values.append(float(value))
    return values


def masked_joint_mae(predicted: list, target: list, valid: list) -> list:
    """Per-joint mean absolute error over the frames the mask keeps."""

    if len(predicted) != len(target) or len(valid) != len(target):
        raise ValueError("MASK_SHAPE_INVALID")
    for keep in valid:
        if type(keep) is not bool:
            raise ValueError("MASK_SHAPE_INVALID")
    indices = [index for index, keep in enumerate(valid) if keep]
    if not indices:
        raise ValueError("NO_VALID_TARGETS")
    predictions = [_row(predicted[index], "PREDICTED") for index in indices]
    targets = [_row(target[index], "TARGET") for index in indices]
    return [sum(abs(predictions[position][joint] - targets[position][joint])
                for position in range(len(indices))) / len(indices)
            for joint in range(_JOINTS)]


def masked_joint_rmse(predicted: list, target: list, valid: list) -> list:
    """Per-joint root mean squared error over the same frames, with the same refusals."""

    if len(predicted) != len(target) or len(valid) != len(target):
        raise ValueError("MASK_SHAPE_INVALID")
    for keep in valid:
        if type(keep) is not bool:
            raise ValueError("MASK_SHAPE_INVALID")
    indices = [index for index, keep in enumerate(valid) if keep]
    if not indices:
        raise ValueError("NO_VALID_TARGETS")
    predictions = [_row(predicted[index], "PREDICTED") for index in indices]
    targets = [_row(target[index], "TARGET") for index in indices]
    return [math.sqrt(sum((predictions[position][joint] - targets[position][joint]) ** 2
                          for position in range(len(indices))) / len(indices))
            for joint in range(_JOINTS)]


FREEZE_FIELDS = ("bundle_sha256", "dataset_manifest_sha256", "campaign_index_sha256",
                 "split_manifest_sha256", "calibration_sha256", "runtime_config_sha256")
MIN_OFFLINE_TEST_EPISODES = 10


def _sha256(value, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(code)
    return value


def load_freeze(freeze_path) -> dict:
    """The frozen six digests, each re-read from the file its sibling paths document records."""

    import hashlib
    import json

    target = Path(freeze_path)
    if not target.is_file():
        raise ValueError("FREEZE_MISSING")
    try:
        freeze = json.loads(target.read_bytes())
    except ValueError as error:
        raise ValueError("FREEZE_INVALID") from error
    if not isinstance(freeze, dict) or set(freeze) != set(FREEZE_FIELDS):
        raise ValueError("FREEZE_INVALID")
    for field in FREEZE_FIELDS:
        _sha256(freeze[field], "FREEZE_INVALID")
    paths_path = target.parent / "freeze-paths.json"
    if not paths_path.is_file():
        raise ValueError("FREEZE_PATHS_MISSING")
    paths = json.loads(paths_path.read_bytes())
    if not isinstance(paths, dict) or set(paths) != set(FREEZE_FIELDS):
        raise ValueError("FREEZE_PATHS_INVALID")
    for field in FREEZE_FIELDS:
        recorded = Path(paths[field])
        if not recorded.is_absolute():
            raise ValueError("FREEZE_PATHS_INVALID")
        if not recorded.is_file():
            raise ValueError("FREEZE_FILE_MISSING")
        if hashlib.sha256(recorded.read_bytes()).hexdigest() != freeze[field]:
            raise ValueError("FREEZE_DIGEST_MISMATCH")
    return freeze


def evaluate_offline(manifest_path, bundle_path, freeze_path, output, *, policy_loader) -> dict:
    """Read-only evaluation of a frozen bundle on the Offline Test split.

    Nothing here may write to the dataset, update statistics, select a checkpoint or backpropagate: the
    only output is the metrics document. A freeze that does not verify stops the run before any inference.
    """

    import hashlib
    import json

    from so101_demo.act.bundle import load_bundle, load_policy

    freeze = load_freeze(freeze_path)
    if hashlib.sha256(Path(bundle_path).read_bytes()).hexdigest() != freeze["bundle_sha256"]:
        raise ValueError("FREEZE_BUNDLE_MISMATCH")
    bundle = load_bundle(bundle_path)
    manifest_file = Path(manifest_path)
    if hashlib.sha256(manifest_file.read_bytes()).hexdigest() != freeze["dataset_manifest_sha256"]:
        raise ValueError("FREEZE_MANIFEST_MISMATCH")
    manifest = json.loads(manifest_file.read_bytes())
    episodes = [episode for episode in manifest.get("episodes", [])
                if isinstance(episode, dict) and episode.get("split") == "offline_test"
                and episode.get("status") == "PASSED"]
    if len(episodes) < MIN_OFFLINE_TEST_EPISODES:
        raise ValueError("OFFLINE_TEST_EPISODES_INSUFFICIENT")
    if any(episode.get("cross_split_chunk") for episode in episodes):
        raise ValueError("CROSS_SPLIT_CHUNK_FORBIDDEN")
    normalization_before = json.dumps(bundle.get("normalization"), sort_keys=True)

    model = load_policy(bundle_path, loader=policy_loader)
    per_episode, horizon_totals, horizon_counts, valid_targets = [], {}, {}, 0
    for episode in episodes:
        model.reset()                                  # a fresh model state per episode
        frames = episode.get("frames")
        if not isinstance(frames, list) or not frames:
            raise ValueError("EPISODE_FRAMES_INVALID")
        predicted, target, valid = [], [], []
        for frame in frames:
            action = model.infer(frame["observation"])
            predicted.append(list(action[0]))
            target.append(list(frame["action"]))
            keep = frame.get("valid", True)
            valid.append(keep)
            if keep:
                valid_targets += 1
                horizon_totals[len(predicted)] = horizon_totals.get(len(predicted), 0.0) + \
                    sum(abs(value) for value in predicted[-1])
                horizon_counts[len(predicted)] = horizon_counts.get(len(predicted), 0) + 1
        per_episode.append({"episode_id": episode.get("episode_id"),
                            "mae": masked_joint_mae(predicted, target, valid),
                            "rmse": masked_joint_rmse(predicted, target, valid),
                            "valid_targets": sum(1 for keep in valid if keep)})
    if json.dumps(bundle.get("normalization"), sort_keys=True) != normalization_before:
        raise ValueError("EVALUATION_MUTATED_STATISTICS")
    overall = [sum(episode["mae"][joint] for episode in per_episode) / len(per_episode)
               for joint in range(_JOINTS)]           # every episode weighs the same
    document = {"schema_version": 1, "kind": "act_offline_evaluation",
                "episode_count": len(per_episode), "valid_targets": valid_targets,
                "per_episode": per_episode, "mean_mae_rad": overall,
                "byte_weighted": False,
                "freeze": {field: freeze[field] for field in FREEZE_FIELDS},
                "bundle_sha256": freeze["bundle_sha256"]}
    target_path = Path(output)
    if target_path.exists() or target_path.is_symlink():
        raise ValueError("EVALUATION_OUTPUT_EXISTS")
    temporary = target_path.with_name(target_path.name + ".partial")
    temporary.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n")
    temporary.replace(target_path)
    return document
