"""Generate a dataset."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path
from typing import Any, Mapping

from so101_demo.adapters.perception.mujoco_dataset.config import (
    DatasetConfig,
    _dataset_splits,
    scenario_plan,
    split_seed_plan,
)
from so101_demo.adapters.perception.mujoco_dataset.render import (
    DatasetRenderer,
    _exclusive_text,
    _label_text,
    _mask_sha256,
    _resolved_scenario_quotas,
    _scene_geometry_document,
    _truth_instance_document,
    build_labeled_sample,
)
from so101_demo.adapters.perception.mujoco_dataset.renderer import MuJoCoDatasetRenderer
from so101_demo.adapters.perception.mujoco_dataset.verify import (
    _head_profile_context,
    _sample_camera_document,
)
from so101_demo.adapters.perception.mujoco_scene_geometry import (
    TaskSceneGeometry,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256
from so101_demo.runtime.point_cloud_preview import write_png_rgb8
from so101_demo.runtime.task_artifacts import atomic_json


def generate_dataset(
    config: DatasetConfig,
    output_root: Path,
    *,
    renderer: DatasetRenderer | None = None,
    geometry_seal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"output root already exists: {root}")
    head_context = _head_profile_context(config, geometry_seal)
    root.mkdir(parents=True, mode=0o700)
    owned_renderer = renderer is None
    active_renderer = renderer or MuJoCoDatasetRenderer(config)
    seeds = split_seed_plan(config.split_counts, config.seed_starts)
    schedules = scenario_plan(config)
    samples: list[dict[str, Any]] = []
    artifacts: list[str] = []
    class_instance_total = 0
    try:
        for split in config.split_counts:
            for seed, scenario in zip(seeds[split], schedules[split], strict=True):
                render = active_renderer.render(seed, scenario)
                extra_truth: dict[str, Any] = {}
                if config.require_nonpenetrating_scene:
                    receipt = render.geometry_receipt
                    if not isinstance(receipt, TaskSceneGeometry) or not receipt.accepted:
                        raise ValueError("required accepted geometry receipt is missing or invalid")
                    receipt.validate_scope(scenario.cup_count)
                    extra_truth["scene_geometry"] = {
                        "policy": "task-visual-nonpenetration-v1",
                        "accepted": True,
                        **asdict(receipt),
                    }
                sample = build_labeled_sample(
                    render,
                    seed=seed,
                    scenario=scenario,
                )
                scene_group_id = None
                camera_document: dict[str, Any] | None = None
                raw_mask_sha256 = None
                if head_context is not None:
                    scene_group_id = f"scene-{seed:09d}"
                    camera_document = _sample_camera_document(
                        config, head_context, render, scene_group_id
                    )
                    raw_mask_sha256 = canonical_sha256(
                        [_mask_sha256(instance.mask) for instance in sample.instances]
                    )
                stem = f"{seed:09d}"
                image_relative = Path("images") / split / f"{stem}.png"
                label_relative = Path("labels") / split / f"{stem}.txt"
                truth_relative = Path("truth") / split / f"{stem}.json"
                image_path = root / image_relative
                image_path.parent.mkdir(parents=True, exist_ok=True)
                write_png_rgb8(sample.rgb8, image_path)
                _exclusive_text(root / label_relative, _label_text(sample))
                truth_document: dict[str, Any] = {
                    "seed": seed,
                    "split": split,
                    "scenario": scenario.value,
                    "configured_cup_count": scenario.cup_count,
                    "visible_instance_count": len(sample.instances),
                    "instances": [_truth_instance_document(item) for item in sample.instances],
                    **extra_truth,
                }
                if scene_group_id is not None:
                    truth_document["scene_group_id"] = scene_group_id
                    truth_document["camera"] = camera_document
                    truth_document["raw_mask_sha256"] = raw_mask_sha256
                atomic_json(root / truth_relative, truth_document)
                relative_paths = (image_relative, label_relative, truth_relative)
                artifacts.extend(path.as_posix() for path in relative_paths)
                class_instance_total += len(sample.instances)
                sample_record: dict[str, Any] = {
                    "seed": seed,
                    "split": split,
                    "scenario": scenario.value,
                    "configured_cup_count": scenario.cup_count,
                    "visible_instance_count": len(sample.instances),
                    "image": image_relative.as_posix(),
                    "label": label_relative.as_posix(),
                    "truth": truth_relative.as_posix(),
                }
                if head_context is not None:
                    for key, relative in (
                        ("image", image_relative),
                        ("label", label_relative),
                        ("truth", truth_relative),
                    ):
                        contents = (root / relative).read_bytes()
                        sample_record[f"{key}_sha256"] = hashlib.sha256(contents).hexdigest()
                        sample_record[f"{key}_bytes"] = len(contents)
                if scene_group_id is not None:
                    sample_record["scene_group_id"] = scene_group_id
                    sample_record["camera"] = camera_document
                    sample_record["raw_mask_sha256"] = raw_mask_sha256
                samples.append(sample_record)
        dataset_yaml = "path: .\n"
        for split in config.split_counts:
            dataset_yaml += f"{split}: images/{split}\n"
        dataset_yaml += "names:\n  0: plastic_cup\n"
        _exclusive_text(root / "dataset.yaml", dataset_yaml)
        artifacts.append("dataset.yaml")
        manifest: dict[str, Any] = {
            "schema_version": config.schema_version,
            "generator_commit": config.generator_commit,
            "mjcf_sha256": hashlib.sha256(config.mjcf_path.read_bytes()).hexdigest(),
            "camera_name": config.camera_name,
            "image_width": config.image_width,
            "image_height": config.image_height,
            "sample_count": len(samples),
            "split_counts": {
                split: config.split_counts[split] for split in sorted(config.split_counts)
            },
            "seed_starts": {
                split: config.seed_starts[split] for split in sorted(config.seed_starts)
            },
            "seed_ranges": {split: [values[0], values[-1]] for split, values in seeds.items()},
            "scenario_quotas": _resolved_scenario_quotas(schedules),
            "scene_geometry": _scene_geometry_document(config.geometry),
            "truth_contract": {
                "mask_order": "row_major",
                "mask_rle": "alternating_zero_one_counts_starting_with_zero",
                "mask_sha256": "sha256_uint8_row_major_bytes",
                "partial_occlusion_reference": "visible_union_paired_segmentation_with_declared_occluder_hidden",
                "canonical_amodal": "visible_bitwise_union_paired_reference",
            },
            "class_instance_totals": {"plastic_cup": class_instance_total},
            "samples": samples,
            "artifacts": sorted(artifacts),
        }
        if config.require_nonpenetrating_scene:
            manifest["scene_geometry_policy"] = "task-visual-nonpenetration-v1"
        if config.dataset_contract is not None:
            manifest["dataset_contract"] = config.dataset_contract
            manifest["member_splits"] = list(_dataset_splits(config.dataset_contract))
        manifest["promotable"] = config.promotable
        if head_context is not None:
            manifest["geometry_seal_sha256"] = head_context["seal_sha256"]
            manifest["camera_identity"] = {
                "frame_id": config.camera_name,
                "width": config.image_width,
                "height": config.image_height,
                "focal_px": head_context["focal_px"],
                "distortion_model": "plumb_bob",
            }
            manifest["neck_yaw_rad"] = list(config.neck_yaw_rad or ())
            group_ids = [item["scene_group_id"] for item in samples]
            if len(set(group_ids)) != len(group_ids):
                raise ValueError(
                    "HEAD_DATASET_SCENE_GROUP_DUPLICATE: a scene_group_id appears twice in one dataset"
                )
            manifest["scene_group_ids"] = group_ids
        atomic_json(root / "dataset-manifest.json", manifest)
        return manifest
    finally:
        if owned_renderer:
            active_renderer.close()
