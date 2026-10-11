"""Calibration constants, validation samples and the locked split datasets."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from so101_demo.adapters.perception.mujoco_dataset.render import decode_binary_mask_rle
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import MaskRef, RawCandidate
from so101_demo.perception_benchmark.dataset.truth import rasterize_polygon
from so101_demo.training.grounding_dino_dataset.contracts import (
    BoundingBox,
    GroundingDinoDatasetError,
    binary_mask_to_box,
    polygon_to_box,
)
from so101_demo.training.grounding_dino_dataset.validation import _boxes_match, _label_polygons

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


_RAW_RECORD_SCHEMA = "so101-grounded-sam-val-raw-record/v1"


_RAW_RUN_SCHEMA = "so101-grounded-sam-val-raw-run/v1"


_FROZEN_GRID = (
    Decimal("0.50"),
    Decimal("0.60"),
    Decimal("0.70"),
    Decimal("0.75"),
    Decimal("0.80"),
    Decimal("0.85"),
    Decimal("0.90"),
)


_LOW_QUALITY_GRID = tuple(Decimal(f"{value / 10:.2f}") for value in range(6))


_RAW_LIMITS = {
    "box_threshold": 0.01,
    "max_mask_area_ratio": 0.5,
    "min_mask_pixels": 64,
    "sam_quality_floor": 0.0,
    "text_threshold": 0.01,
}


_CANDIDATE_FIELDS = {
    "bbox_xyxy",
    "candidate_id",
    "class_confidence",
    "grounding_box_score",
    "grounding_text_score",
    "label",
    "mask",
    "ranking_score",
    "ranking_score_source",
    "sam_quality",
}


_MASK_FIELDS = {
    "image_height",
    "image_width",
    "pixel_count",
    "relative_path",
    "sha256",
}


class ValCalibrationError(RuntimeError):
    """Stable fail-closed error for val evidence and calibration."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ValSample:
    formal_sample_index: int
    seed: int
    scenario: str
    configured_cup_count: int
    image_path: Path
    image_sha256: str
    truths: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if (
            type(self.formal_sample_index) is not int
            or self.formal_sample_index < 0
            or type(self.seed) is not int
            or not isinstance(self.scenario, str)
            or not self.scenario
            or type(self.configured_cup_count) is not int
            or self.configured_cup_count < 0
            or not isinstance(self.image_sha256, str)
            or _SHA256.fullmatch(self.image_sha256) is None
        ):
            raise ValueError("val sample identity is invalid")
        object.__setattr__(self, "image_path", Path(self.image_path))
        object.__setattr__(
            self,
            "truths",
            tuple(MappingProxyType(dict(truth)) for truth in self.truths),
        )


@dataclass(frozen=True, slots=True)
class ValDataset:
    inventory_sha256: str
    source_manifest_sha256: str
    samples: tuple[ValSample, ...]
    scenario_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        for value in (self.inventory_sha256, self.source_manifest_sha256):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ValueError("val dataset SHA256 is invalid")
        samples = tuple(self.samples)
        if not all(isinstance(sample, ValSample) for sample in samples):
            raise ValueError("val dataset samples are invalid")
        if [sample.formal_sample_index for sample in samples] != list(range(len(samples))):
            raise ValueError("val dataset sample order is invalid")
        counts = dict(self.scenario_counts)
        if Counter(sample.scenario for sample in samples) != Counter(counts):
            raise ValueError("val dataset scenario counts are invalid")
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "scenario_counts", MappingProxyType(counts))


def candidate_to_document(candidate: RawCandidate) -> dict[str, Any]:
    """Serialize every field needed for stable raw/production identity."""

    if not isinstance(candidate, RawCandidate):
        raise TypeError("candidate must be a RawCandidate")
    return {
        "bbox_xyxy": list(candidate.bbox_xyxy),
        "candidate_id": candidate.candidate_id,
        "class_confidence": candidate.class_confidence,
        "grounding_box_score": candidate.grounding_box_score,
        "grounding_text_score": candidate.grounding_text_score,
        "label": candidate.label,
        "mask": {
            "image_height": candidate.mask.image_height,
            "image_width": candidate.mask.image_width,
            "pixel_count": candidate.mask.pixel_count,
            "relative_path": candidate.mask.relative_path,
            "sha256": candidate.mask.sha256,
        },
        "ranking_score": candidate.ranking_score,
        "ranking_score_source": candidate.ranking_score_source,
        "sam_quality": candidate.sam_quality,
    }


def candidate_from_document(document: object) -> RawCandidate:
    """Reconstruct one raw candidate only from the complete strict schema."""

    if not isinstance(document, Mapping) or set(document) != _CANDIDATE_FIELDS:
        raise ValCalibrationError("RAW_CANDIDATE_INVALID", "fields")
    mask = document.get("mask")
    bbox = document.get("bbox_xyxy")
    if (
        not isinstance(mask, Mapping)
        or set(mask) != _MASK_FIELDS
        or not isinstance(bbox, list)
        or len(bbox) != 4
    ):
        raise ValCalibrationError("RAW_CANDIDATE_INVALID", "mask or bbox")
    try:
        return RawCandidate(
            candidate_id=document["candidate_id"],
            label=document["label"],
            bbox_xyxy=tuple(bbox),
            mask=MaskRef(
                relative_path=mask["relative_path"],
                sha256=mask["sha256"],
                pixel_count=mask["pixel_count"],
                image_width=mask["image_width"],
                image_height=mask["image_height"],
            ),
            ranking_score=document["ranking_score"],
            ranking_score_source=document["ranking_score_source"],
            class_confidence=document["class_confidence"],
            grounding_box_score=document["grounding_box_score"],
            grounding_text_score=document["grounding_text_score"],
            sam_quality=document["sam_quality"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValCalibrationError("RAW_CANDIDATE_INVALID", "values") from error


def _read_canonical(path: Path, code: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        payload = Path(path).read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValCalibrationError(code, str(path)) from error
    if not isinstance(document, Mapping) or canonical_json_bytes(document) != payload:
        raise ValCalibrationError(code, str(path))
    return document, payload


def _require_immutable_regular_file(path: Path, code: str) -> bytes:
    target = Path(path)
    try:
        metadata = target.lstat()
        payload = target.read_bytes()
        after = target.lstat()
    except OSError as error:
        raise ValCalibrationError(code, str(target)) from error
    if (
        target.is_symlink()
        or not target.is_file()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o222
        or (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise ValCalibrationError(code, str(target))
    return payload


def _safe_split_member(root: Path, value: object, kind: str, seed: int, split: str) -> Path:
    if not isinstance(value, str) or "\\" in value:
        raise ValCalibrationError("VAL_MEMBER_PATH_INVALID", str(value))
    relative = PurePosixPath(value)
    expected = PurePosixPath(kind, split, f"{seed}.{ {'images': 'png', 'labels': 'txt', 'truth': 'json'}[kind] }")
    if relative != expected:
        raise ValCalibrationError("VAL_MEMBER_PATH_INVALID", value)
    target = root.joinpath(*relative.parts)
    if target.resolve(strict=False).parent != (root / kind / split).resolve(strict=False):
        raise ValCalibrationError("VAL_MEMBER_PATH_INVALID", value)
    return target


def _visible_mask_from_truth(
    instance: object,
    *,
    width: int,
    height: int,
    expected_pixel_count: object,
) -> tuple[np.ndarray, BoundingBox] | None:
    if not isinstance(instance, Mapping):
        raise ValCalibrationError("VAL_ANNOTATION_INVALID", "truth instance")
    fields = {
        "mask_shape_hw",
        "visible_mask_rle_counts",
        "visible_mask_sha256",
    }
    present = fields.intersection(instance)
    if not present:
        return None
    if present != fields:
        raise ValCalibrationError("VAL_VISIBLE_MASK_INVALID", "incomplete fields")
    try:
        mask = decode_binary_mask_rle(
            instance["visible_mask_rle_counts"], instance["mask_shape_hw"]
        )
    except (KeyError, ValueError) as error:
        raise ValCalibrationError("VAL_VISIBLE_MASK_INVALID", "RLE") from error
    actual_hash = hashlib.sha256(mask.astype(np.uint8).tobytes(order="C")).hexdigest()
    if (
        mask.shape != (height, width)
        or type(expected_pixel_count) is not int
        or int(mask.sum()) != expected_pixel_count
        or instance.get("visible_pixel_count") != expected_pixel_count
        or instance.get("visible_mask_sha256") != actual_hash
    ):
        raise ValCalibrationError("VAL_VISIBLE_MASK_INVALID", "identity")
    try:
        box = binary_mask_to_box(mask, width, height)
    except GroundingDinoDatasetError as error:
        raise ValCalibrationError("VAL_VISIBLE_MASK_INVALID", "box") from error
    mask.setflags(write=False)
    return mask, box


def _trainer_box_matches(
    visible_box: BoundingBox,
    inventory_box: BoundingBox,
    *,
    width: int,
    height: int,
) -> bool:
    if not all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
        for a, b in zip(
            visible_box.absolute_xyxy,
            inventory_box.absolute_xyxy,
            strict=True,
        )
    ):
        return False
    left, top, right, bottom = visible_box.absolute_xyxy
    trainer_normalized = (left / width, top / height, right / width, bottom / height)
    return all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
        for a, b in zip(
            trainer_normalized,
            inventory_box.normalized_xyxy,
            strict=True,
        )
    )


def load_locked_val_dataset(
    *,
    inventory_path: Path,
    expected_inventory_sha256: str,
    source_root: Path,
    expected_source_manifest_sha256: str,
) -> ValDataset:
    """Verify and load only the externally hash-bound r3 validation members."""

    return _load_locked_split_dataset(
        inventory_path=inventory_path,
        expected_inventory_sha256=expected_inventory_sha256,
        source_root=source_root,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        split="val",
    )


def load_locked_train_dataset(
    *,
    inventory_path: Path,
    expected_inventory_sha256: str,
    source_root: Path,
    expected_source_manifest_sha256: str,
) -> ValDataset:
    """Load train members only, requiring exact visible RLE for optimizer truth."""

    return _load_locked_split_dataset(
        inventory_path=inventory_path,
        expected_inventory_sha256=expected_inventory_sha256,
        source_root=source_root,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        split="train",
    )


def _load_locked_split_dataset(
    *,
    inventory_path: Path,
    expected_inventory_sha256: str,
    source_root: Path,
    expected_source_manifest_sha256: str,
    split: str,
) -> ValDataset:
    if split not in {"train", "val"}:
        raise ValCalibrationError("SPLIT_INVALID")

    inventory_file = Path(inventory_path)
    root = Path(source_root)
    if (
        not inventory_file.is_absolute()
        or not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) & 0o222
        or _SHA256.fullmatch(expected_inventory_sha256) is None
        or _SHA256.fullmatch(expected_source_manifest_sha256) is None
    ):
        raise ValCalibrationError("VAL_DATASET_IDENTITY_INVALID")
    inventory_payload = _require_immutable_regular_file(
        inventory_file, "VAL_INVENTORY_INVALID"
    )
    if hashlib.sha256(inventory_payload).hexdigest() != expected_inventory_sha256:
        raise ValCalibrationError("VAL_INVENTORY_SHA256_MISMATCH")
    try:
        inventory = json.loads(inventory_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValCalibrationError("VAL_INVENTORY_INVALID") from error
    expected_fields = {
        "class_name",
        "converter_commit",
        "image_height",
        "image_width",
        "prompt",
        "sample_count",
        "samples",
        "schema_version",
        "source_archive_sha256",
        "source_generator_commit",
        "source_manifest_sha256",
        "source_mjcf_sha256",
        "split",
    }
    if (
        not isinstance(inventory, Mapping)
        or canonical_json_bytes(inventory) != inventory_payload
        or set(inventory) != expected_fields
        or inventory.get("schema_version") != 1
        or inventory.get("split") != split
        or inventory.get("class_name") != "cup"
        or inventory.get("prompt") != "cup."
        or inventory.get("source_manifest_sha256") != expected_source_manifest_sha256
        or not isinstance(inventory.get("samples"), list)
        or inventory.get("sample_count") != len(inventory["samples"])
        or type(inventory.get("image_width")) is not int
        or type(inventory.get("image_height")) is not int
    ):
        raise ValCalibrationError("VAL_INVENTORY_INVALID")
    manifest_payload = _require_immutable_regular_file(
        root / "dataset-manifest.json", "SOURCE_MANIFEST_INVALID"
    )
    if hashlib.sha256(manifest_payload).hexdigest() != expected_source_manifest_sha256:
        raise ValCalibrationError("SOURCE_MANIFEST_SHA256_MISMATCH")
    width = int(inventory["image_width"])
    height = int(inventory["image_height"])
    samples: list[ValSample] = []
    member_fields = {
        "boxes",
        "configured_cup_count",
        "image_relpath",
        "image_sha256",
        "label_relpath",
        "label_sha256",
        "scenario",
        "seed",
        "truth_relpath",
        "truth_sha256",
        "visible_instance_count",
    }
    for index, item in enumerate(inventory["samples"]):
        if (
            not isinstance(item, Mapping)
            or set(item) != member_fields
            or type(item.get("seed")) is not int
            or not isinstance(item.get("scenario"), str)
            or not isinstance(item.get("boxes"), list)
        ):
            raise ValCalibrationError("VAL_SAMPLE_INVALID", str(index))
        seed = int(item["seed"])
        payloads: dict[str, bytes] = {}
        for kind, field in (("images", "image"), ("labels", "label"), ("truth", "truth")):
            path = _safe_split_member(root, item[f"{field}_relpath"], kind, seed, split)
            payload = _require_immutable_regular_file(path, "VAL_MEMBER_INVALID")
            expected_sha = item.get(f"{field}_sha256")
            if (
                not isinstance(expected_sha, str)
                or _SHA256.fullmatch(expected_sha) is None
                or hashlib.sha256(payload).hexdigest() != expected_sha
            ):
                raise ValCalibrationError("VAL_MEMBER_SHA256_MISMATCH", str(path))
            payloads[field] = payload
        try:
            truth_document = json.loads(payloads["truth"])
            polygons = _label_polygons(
                payloads["label"], member=str(item["label_relpath"])
            )
        except Exception as error:
            raise ValCalibrationError("VAL_ANNOTATION_INVALID", str(index)) from error
        if (
            not isinstance(truth_document, Mapping)
            or truth_document.get("split") != split
            or truth_document.get("seed") != seed
            or truth_document.get("scenario") != item["scenario"]
            or len(polygons) != len(item["boxes"])
            or item.get("visible_instance_count") != len(polygons)
            or not isinstance(truth_document.get("instances"), list)
            or len(truth_document["instances"]) != len(polygons)
        ):
            raise ValCalibrationError("VAL_ANNOTATION_INVALID", str(index))
        truths: list[Mapping[str, Any]] = []
        for polygon, box_document, truth_instance in zip(
            polygons,
            item["boxes"],
            truth_document["instances"],
            strict=True,
        ):
            if (
                not isinstance(box_document, Mapping)
                or box_document.get("class_name") != "cup"
                or box_document.get("text") != "cup."
            ):
                raise ValCalibrationError("VAL_ANNOTATION_INVALID", str(index))
            converted = polygon_to_box(polygon, width, height)
            try:
                expected_box = type(converted)(
                    normalized_xyxy=tuple(box_document["normalized_xyxy"]),
                    absolute_xyxy=tuple(box_document["absolute_xyxy"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValCalibrationError("VAL_ANNOTATION_INVALID", str(index)) from error
            visible = _visible_mask_from_truth(
                truth_instance,
                width=width,
                height=height,
                expected_pixel_count=box_document.get("visible_pixel_count"),
            )
            canonical_box = converted
            if visible is None:
                if not _boxes_match(converted, expected_box):
                    raise ValCalibrationError("VAL_ANNOTATION_INVALID", str(index))
                if split == "train":
                    raise ValCalibrationError("TRAIN_VISIBLE_MASK_REQUIRED", str(index))
                mask = rasterize_polygon(tuple(polygon), width, height)
                mask.setflags(write=False)
            else:
                mask, canonical_box = visible
                if not _boxes_match(converted, canonical_box) or not (
                    _boxes_match(canonical_box, expected_box)
                    or _trainer_box_matches(
                        canonical_box,
                        expected_box,
                        width=width,
                        height=height,
                    )
                ):
                    raise ValCalibrationError("VAL_VISIBLE_MASK_INVALID", "box identity")
            truths.append(
                {
                    "absolute_xyxy": canonical_box.absolute_xyxy,
                    "visible_pixel_count": box_document.get("visible_pixel_count"),
                    "occlusion": box_document.get("occlusion"),
                    "mask": mask,
                }
            )
        samples.append(
            ValSample(
                formal_sample_index=index,
                seed=seed,
                scenario=str(item["scenario"]),
                configured_cup_count=int(item["configured_cup_count"]),
                image_path=_safe_split_member(root, item["image_relpath"], "images", seed, split),
                image_sha256=str(item["image_sha256"]),
                truths=tuple(truths),
            )
        )
    return ValDataset(
        inventory_sha256=expected_inventory_sha256,
        source_manifest_sha256=expected_source_manifest_sha256,
        samples=tuple(samples),
        scenario_counts=Counter(sample.scenario for sample in samples),
    )
