"""Verify a sealed head-camera dataset: counts, scenarios, camera identity, files and leakage.

The generator writes a manifest; this program is what decides whether that manifest describes a
dataset the model work may consume. It reads the manifest back against the files on disk, against
the accepted production-camera seal, and - when the task-camera manifest is supplied - against that
other camera domain's seeds and scene groups, because a world state shared between the two domains
would let a test image be reported as a held-out result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _seed_partitions(manifest: Mapping[str, Any], *, name: str) -> dict[str, set[int]]:
    """Every sample's seed, grouped by split, with a malformed sample refused by name."""

    partitions: dict[str, set[int]] = {}
    for index, sample in enumerate(manifest.get("samples") or ()):
        if not isinstance(sample, Mapping):
            raise ValueError(
                f"HEAD_DATASET_{name}_PARTITION_INVALID: sample {index} is not a mapping"
            )
        split = sample.get("split")
        seed = sample.get("seed")
        if not isinstance(split, str) or not split:
            raise ValueError(
                f"HEAD_DATASET_{name}_PARTITION_INVALID: sample {index} declares no split"
            )
        if type(seed) is not int or seed < 0:
            raise ValueError(
                f"HEAD_DATASET_{name}_PARTITION_INVALID: sample {index} declares no integer seed"
            )
        partitions.setdefault(split, set()).add(seed)
    return partitions


def _scene_group_partitions(manifest: Mapping[str, Any], *, name: str) -> dict[str, str] | None:
    """The manifest's world identities, or None when it carries none at all."""

    samples = list(manifest.get("samples") or ())
    if not samples:
        return None
    declared = [sample.get("scene_group_id") for sample in samples if isinstance(sample, Mapping)]
    if not any(group is not None for group in declared):
        return None
    groups: dict[str, str] = {}
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            raise ValueError(
                f"HEAD_DATASET_{name}_PARTITION_INVALID: sample {index} is not a mapping"
            )
        group = sample.get("scene_group_id")
        split = sample.get("split")
        if not isinstance(group, str) or not group or not isinstance(split, str) or not split:
            raise ValueError(
                f"HEAD_DATASET_{name}_PARTITION_INVALID: sample {index} carries an incomplete world "
                "identity"
            )
        previous = groups.get(group)
        if previous is not None and previous != split:
            raise ValueError(
                f"SCENE_GROUP_SPLIT_LEAK: {group} is {previous} and {split} inside the {name.lower()} "
                "manifest itself, so its partition cannot be compared with the other camera domain"
            )
        groups[group] = split
    return groups


def cross_domain_report(
    head_manifest: Mapping[str, Any], task_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Refuse any world state the two camera domains share, whatever its split is called.

    The seeds are the world states, so an overlap is a leak even when the two manifests name the
    splits differently; the world identities are compared as well whenever both manifests declare
    them, because a group assigned to different splits in the two domains is the same leak.
    """

    head_seeds = _seed_partitions(head_manifest, name="HEAD")
    task_seeds = _seed_partitions(task_manifest, name="TASK")
    head_all = set().union(*head_seeds.values()) if head_seeds else set()
    task_all = set().union(*task_seeds.values()) if task_seeds else set()
    shared = sorted(head_all & task_all)
    if shared:
        raise ValueError(
            "HEAD_DATASET_SEED_LEAK: the head and task camera domains share world-state seeds "
            f"{shared[:8]}{'...' if len(shared) > 8 else ''}"
        )
    head_groups = _scene_group_partitions(head_manifest, name="HEAD")
    task_groups = _scene_group_partitions(task_manifest, name="TASK")
    if head_groups is None or task_groups is None:
        return {
            "cross_domain": "SEED_DISJOINT_ONLY",
            "note": "one of the two manifests carries no scene_group_id, so only the world-state seeds "
            "could be compared",
        }
    from so101_demo.act.head_search_training import validate_scene_group_partition

    merged = validate_scene_group_partition(head=head_groups, task=task_groups)
    return {
        "cross_domain": "SEED_AND_SCENE_GROUP_DISJOINT",
        "scene_group_count": len(merged),
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_head_search_dataset",
        description="Verify a sealed head-camera YOLO-Seg dataset manifest",
    )
    parser.add_argument("--head", required=True, type=_absolute_path)
    parser.add_argument("--task", type=_absolute_path)
    parser.add_argument("--geometry-seal", required=True, type=_absolute_path)
    parser.add_argument("--expected-train", required=True, type=_positive_integer)
    parser.add_argument("--expected-val", required=True, type=_positive_integer)
    parser.add_argument("--expected-test", required=True, type=_positive_integer)
    parser.add_argument("--require-non-promotable", action="store_true")
    parsed = parser.parse_args(arguments)

    from so101_demo.adapters.perception.mujoco_dataset.verify import verify_head_search_manifest

    try:
        manifest = json.loads(parsed.head.read_text(encoding="utf-8"))
        geometry_seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
        report = verify_head_search_manifest(
            manifest,
            dataset_root=parsed.head.parent,
            geometry_seal=geometry_seal,
            expected_train=parsed.expected_train,
            expected_val=parsed.expected_val,
            expected_test=parsed.expected_test,
            require_non_promotable=parsed.require_non_promotable,
        )
        if parsed.task is not None:
            task_manifest = json.loads(parsed.task.read_text(encoding="utf-8"))
            report.update(cross_domain_report(manifest, task_manifest))
        report["manifest"] = str(parsed.head)
        report["geometry_seal"] = str(parsed.geometry_seal)
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "failure": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
