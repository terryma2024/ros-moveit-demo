"""The dataset profile, file writers and the dataset conversion."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import os
from pathlib import Path
from typing import Any

from so101_demo.training.grounding_dino_dataset.contracts import (
    _COMMIT,
    _LEGACY_SPLITS,
    _SHA256,
    _TEST_DATASET_CONTRACT,
    _TEST_SPLITS,
    _TRAIN_VAL_DATASET_CONTRACT,
    _TRAIN_VAL_SPLITS,
    _fail,
    polygon_to_box,
)
from so101_demo.training.grounding_dino_dataset.validation import (
    _box_document,
    _boxes_match,
    _canonical_json,
    _dataset_contract,
    _label_polygons,
    _manifest,
    _read_bytes,
    _sample_paths,
    _sha256_bytes,
    _truth_instances,
    _validate_manifest_members,
    _validate_official_test_version,
    _validate_official_train_val_version,
    _validate_sample_shape,
    _validate_train_val_source_tree,
)


def _profile(
    samples: list[dict[str, Any]],
    inventories: Mapping[str, list[dict[str, Any]]],
    *,
    schema_version: int,
    include_test_seal: bool = True,
) -> dict[str, Any]:
    profile: dict[str, Any] = {"schema_version": 1}
    samples_by_split = {
        split: [sample for sample in samples if sample["split"] == split]
        for split in inventories
    }
    for split in inventories:
        split_samples = samples_by_split[split]
        records = inventories[split]
        area_counts: Counter[str] = Counter()
        instance_count = 0
        occlusion_counts: Counter[str] = Counter()
        for record in records:
            for box in record["boxes"]:
                left, top, right, bottom = box["absolute_xyxy"]
                area = (right - left) * (bottom - top)
                bucket = "small" if area < 32**2 else "medium" if area < 96**2 else "large"
                area_counts[bucket] += 1
                instance_count += 1
                occlusion = box.get("occlusion")
                if occlusion is None:
                    occlusion_counts["unmeasured"] += 1
                else:
                    occlusion_counts[f"measured_{occlusion['state']}"] += 1
        configured_count = sum(sample["configured_cup_count"] for sample in split_samples)
        visible_count = sum(sample["visible_instance_count"] for sample in split_samples)
        profile[split] = {
            "area_bucket_counts": {
                bucket: area_counts[bucket] for bucket in ("small", "medium", "large")
            },
            "background": "unknown",
            "configured_instance_count": configured_count,
            "fully_hidden_instance_count": configured_count - visible_count,
            "image_count": len(split_samples),
            "instance_count": instance_count,
            "lighting": "unknown",
            "partial_occlusion": (
                "unknown"
                if schema_version == 1
                else {
                    "measured_none": occlusion_counts["measured_none"],
                    "measured_partial": occlusion_counts["measured_partial"],
                    "unmeasured": occlusion_counts["unmeasured"],
                }
            ),
            "scenario_counts": dict(
                sorted(Counter(sample["scenario"] for sample in split_samples).items())
            ),
            "visible_cup_count_per_image": dict(
                sorted(
                    Counter(
                        str(sample["visible_instance_count"]) for sample in split_samples
                    ).items()
                )
            ),
        }
    if include_test_seal:
        profile["test"] = {
            "sample_count": sum(sample["split"] == "test" for sample in samples),
            "sealed": True,
        }
    return profile


def _write_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def convert_dataset(
    source_root: Path,
    output_root: Path,
    *,
    source_archive_sha256: str,
    converter_commit: str,
) -> dict[str, str]:
    """Validate and convert train/val while retaining a cryptographic test seal."""

    source_root = Path(source_root)
    output_root = Path(output_root)
    if not source_root.is_absolute() or not output_root.is_absolute():
        raise _fail("PATH_NOT_ABSOLUTE", "source and output roots must be absolute")
    if output_root.exists() or output_root.is_symlink():
        raise _fail("OUTPUT_ROOT_ALREADY_EXISTS", str(output_root))
    if source_root.is_symlink():
        raise _fail("SOURCE_PATH_INVALID", "source root must not be a symlink")
    try:
        source_root = source_root.resolve(strict=True)
    except OSError as error:
        raise _fail("SOURCE_ROOT_INVALID", str(error)) from error
    if not source_root.is_dir():
        raise _fail("SOURCE_ROOT_INVALID", "source root is not a directory")
    if _SHA256.fullmatch(source_archive_sha256) is None:
        raise _fail("PROVENANCE_INVALID", "source archive SHA256 is invalid")
    if _COMMIT.fullmatch(converter_commit) is None:
        raise _fail("PROVENANCE_INVALID", "converter commit is invalid")

    manifest, manifest_payload = _manifest(source_root)
    dataset_contract = manifest.get("dataset_contract")
    splits = (
        _TRAIN_VAL_SPLITS
        if dataset_contract == _TRAIN_VAL_DATASET_CONTRACT
        else _TEST_SPLITS
        if dataset_contract == _TEST_DATASET_CONTRACT
        else _LEGACY_SPLITS
    )
    if splits == _TRAIN_VAL_SPLITS:
        _validate_official_train_val_version(manifest)
    elif splits == _TEST_SPLITS:
        _validate_official_test_version(manifest)
    _dataset_contract(source_root, splits)
    samples = [
        _validate_sample_shape(sample, index, splits)
        for index, sample in enumerate(manifest["samples"])
    ]
    _validate_manifest_members(manifest, samples, splits)
    if splits != _LEGACY_SPLITS:
        _validate_train_val_source_tree(source_root, manifest, samples)
    width = manifest["image_width"]
    height = manifest["image_height"]
    source_manifest_sha256 = _sha256_bytes(manifest_payload)
    common = {
        "class_name": "cup",
        "converter_commit": converter_commit,
        "image_height": height,
        "image_width": width,
        "prompt": "cup.",
        "schema_version": 1,
        "source_archive_sha256": source_archive_sha256,
        "source_generator_commit": manifest["generator_commit"],
        "source_manifest_sha256": source_manifest_sha256,
        "source_mjcf_sha256": manifest["mjcf_sha256"],
    }
    inventories: dict[str, list[dict[str, Any]]] = {
        split: [] for split in splits if split != "test"
    }
    sealed_samples: list[dict[str, Any]] = []
    for sample in sorted(
        manifest["samples"], key=lambda item: (splits.index(item["split"]), item["seed"])
    ):
        paths = _sample_paths(sample)
        payloads = {name: _read_bytes(source_root, path) for name, path in paths.items()}
        hashes = {f"{name}_sha256": _sha256_bytes(payload) for name, payload in payloads.items()}
        base_record = {
            "image_relpath": paths["image"].as_posix(),
            "label_relpath": paths["label"].as_posix(),
            "truth_relpath": paths["truth"].as_posix(),
            **hashes,
        }
        split = sample["split"]
        if split == "test":
            if splits == _TEST_SPLITS:
                polygons = _label_polygons(payloads["label"], member=paths["label"].as_posix())
                truth_instances = _truth_instances(
                    payloads["truth"],
                    member=paths["truth"].as_posix(),
                    sample=sample,
                    image_width=width,
                    image_height=height,
                    schema_version=manifest["schema_version"],
                    scene_geometry=manifest.get("scene_geometry"),
                    require_complete_visible_truth=True,
                    require_geometry_receipt=True,
                )
                if len(polygons) != len(truth_instances):
                    raise _fail(
                        "TRUTH_MISMATCH",
                        f"{paths['label']}: label/truth instance count differs",
                    )
                for polygon, truth_instance in zip(polygons, truth_instances, strict=True):
                    if not _boxes_match(
                        polygon_to_box(polygon, width, height), truth_instance["box"]
                    ):
                        raise _fail(
                            "TRUTH_MISMATCH",
                            f"{paths['label']}: label/truth box differs",
                        )
            sealed_samples.append(base_record)
            continue

        polygons = _label_polygons(payloads["label"], member=paths["label"].as_posix())
        truth_instances = _truth_instances(
            payloads["truth"],
            member=paths["truth"].as_posix(),
            sample=sample,
            image_width=width,
            image_height=height,
            schema_version=manifest["schema_version"],
            scene_geometry=manifest.get("scene_geometry"),
            require_complete_visible_truth=splits != _LEGACY_SPLITS,
            require_geometry_receipt=splits != _LEGACY_SPLITS,
        )
        if len(polygons) != len(truth_instances):
            raise _fail("TRUTH_MISMATCH", f"{paths['label']}: label/truth instance count differs")
        boxes: list[dict[str, Any]] = []
        for polygon, truth_instance in zip(polygons, truth_instances, strict=True):
            label_box = polygon_to_box(polygon, width, height)
            if not _boxes_match(label_box, truth_instance["box"]):
                raise _fail("TRUTH_MISMATCH", f"{paths['label']}: label/truth box differs")
            box_document = _box_document(
                truth_instance["box"], image_width=width, image_height=height
            )
            box_document["visible_pixel_count"] = truth_instance["visible_pixel_count"]
            if manifest["schema_version"] == 2:
                box_document["occlusion"] = truth_instance["occlusion"]
            boxes.append(box_document)
        inventories[split].append(
            {
                **base_record,
                "boxes": boxes,
                "configured_cup_count": sample["configured_cup_count"],
                "scenario": sample["scenario"],
                "seed": sample["seed"],
                "visible_instance_count": sample["visible_instance_count"],
            }
        )

    documents: dict[str, dict[str, Any]] = {}
    for split in inventories:
        documents[f"{split}/inventory.json"] = {
            **common,
            "sample_count": len(inventories[split]),
            "samples": inventories[split],
            "split": split,
        }
    if "test" in splits:
        documents["test-sealed-members.json"] = {
            "converter_commit": converter_commit,
            "sample_count": len(sealed_samples),
            "samples": sealed_samples,
            "schema_version": 1,
            "sealed": True,
            "source_archive_sha256": source_archive_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "split": "test",
        }
    documents["dataset-profile.json"] = _profile(
        samples,
        inventories,
        schema_version=manifest["schema_version"],
        include_test_seal="test" in splits,
    )
    payloads = {relative: _canonical_json(document) for relative, document in documents.items()}
    output_root.mkdir(parents=True, exist_ok=False)
    for relative in sorted(payloads):
        _write_file(output_root / relative, payloads[relative])
    for directory in sorted(
        {output_root, *(path.parent for path in output_root.rglob("*"))},
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if directory.is_dir():
            _fsync_directory(directory)
    return {
        relative.replace("/", "_").replace(".json", "_sha256"): _sha256_bytes(payload)
        for relative, payload in sorted(payloads.items())
    }
