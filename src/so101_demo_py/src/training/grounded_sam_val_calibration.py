"""Train/val-only Grounded-SAM raw evidence and threshold calibration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from PIL import Image
from so101_demo.adapters.perception.mujoco_dataset import decode_binary_mask_rle
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import CollectionMode
from so101_demo.perception_benchmark.calibration import GroundedSamBenchmarkThresholds
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    read_mask,
)
from so101_demo.perception_benchmark.contracts import MaskRef, RawCandidate
from so101_demo.perception_benchmark.dataset import rasterize_polygon
from so101_demo.training.grounding_dino_dataset import (
    BoundingBox,
    GroundingDinoDatasetError,
    _boxes_match,
    _label_polygons,
    binary_mask_to_box,
    polygon_to_box,
)
from so101_demo.training.grounding_dino_finetune import box_iou

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
            if not _boxes_match(converted, expected_box):
                raise ValCalibrationError("VAL_ANNOTATION_INVALID", str(index))
            visible = _visible_mask_from_truth(
                truth_instance,
                width=width,
                height=height,
                expected_pixel_count=box_document.get("visible_pixel_count"),
            )
            canonical_box = converted
            if visible is None:
                if split == "train":
                    raise ValCalibrationError("TRAIN_VISIBLE_MASK_REQUIRED", str(index))
                mask = rasterize_polygon(tuple(polygon), width, height)
                mask.setflags(write=False)
            else:
                mask, canonical_box = visible
                if not _boxes_match(canonical_box, expected_box):
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


def _create_output_root(path: Path) -> Path:
    root = Path(path)
    if not root.is_absolute() or root.is_symlink() or not root.parent.is_dir():
        raise ValCalibrationError("OUTPUT_ROOT_INVALID", str(root))
    if os.path.lexists(root):
        raise ValCalibrationError("OUTPUT_ROOT_ALREADY_EXISTS", str(root))
    try:
        os.mkdir(root, 0o700)
    except OSError as error:
        raise ValCalibrationError("OUTPUT_ROOT_CREATE_FAILED", str(root)) from error
    return root


def write_calibration_evidence(
    *,
    output_root: Path,
    dataset: ValDataset,
    raw_run_root: Path,
    raw_manifest_sha256: str,
    source_commit: str,
    selected: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Persist one exclusive deterministic val calibration result."""

    if (
        _SHA256.fullmatch(raw_manifest_sha256) is None
        or _COMMIT.fullmatch(source_commit) is None
        or not Path(raw_run_root).is_absolute()
    ):
        raise ValCalibrationError("CALIBRATION_PROVENANCE_INVALID")
    root = _create_output_root(output_root)
    report = {
        "schema_version": "so101-grounded-sam-val-calibration-report/v1",
        "source_commit": source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "raw_run_root": str(Path(raw_run_root)),
        "raw_manifest_sha256": raw_manifest_sha256,
        "selected_sam_quality": selected["sam_quality"],
        "selected": dict(selected),
        "grid_points": [dict(point) for point in points],
    }
    try:
        report_sha = atomic_write_json(root / "report.json", report)
        atomic_write_json(
            root / "manifest.json",
            {
                "schema_version": "so101-grounded-sam-val-calibration-run/v1",
                "status": "VALID",
                "source_commit": source_commit,
                "val_inventory_sha256": dataset.inventory_sha256,
                "raw_manifest_sha256": raw_manifest_sha256,
                "report_sha256": report_sha,
            },
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_WRITE_FAILED") from error
    return MappingProxyType(report)


def _write_exclusive_json(path: Path, document: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(document)
    target = Path(path)
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ValCalibrationError("OUTPUT_COLLISION", str(target)) from error
    return hashlib.sha256(payload).hexdigest()


def _record_inventory_sha(record_hashes: Sequence[str]) -> str:
    return hashlib.sha256(
        canonical_json_bytes({"record_sha256s": list(record_hashes)})
    ).hexdigest()


def _replace_manifest(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.next")
    if os.path.lexists(temporary):
        raise ValCalibrationError("OUTPUT_COLLISION", str(temporary))
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ValCalibrationError("MANIFEST_WRITE_FAILED", str(path)) from error


def collect_val_raw(
    *,
    dataset: ValDataset,
    adapter: Any | None = None,
    adapter_factory: Callable[[Path], Any] | None = None,
    output_root: Path,
    run_id: str,
    source_commit: str,
    model_manifest_sha256: str,
) -> Mapping[str, Any]:
    """Run one complete CUDA low-floor collection and persist all metadata."""

    if (
        not isinstance(dataset, ValDataset)
        or not isinstance(run_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", run_id) is None
        or _COMMIT.fullmatch(source_commit) is None
        or _SHA256.fullmatch(model_manifest_sha256) is None
        or ((adapter is None) == (adapter_factory is None))
    ):
        raise ValCalibrationError("RAW_RUN_IDENTITY_INVALID")
    root = _create_output_root(output_root)
    records_root = root / "records"
    records_root.mkdir(mode=0o700)
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": _RAW_RUN_SCHEMA,
        "status": "RUNNING",
        "run_id": run_id,
        "source_commit": source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "model_manifest_sha256": model_manifest_sha256,
        "expected_sample_count": len(dataset.samples),
        "record_count": 0,
        "record_inventory_sha256": _record_inventory_sha(()),
        "inference_error_count": 0,
    }
    _write_exclusive_json(manifest_path, manifest)
    record_hashes: list[str] = []
    try:
        active_adapter = adapter if adapter is not None else adapter_factory(root)
        if (
            getattr(active_adapter, "model_id", None)
            != "grounding-dino-tiny+sam2.1-hiera-tiny"
            or getattr(active_adapter, "runtime_device", None) != "cuda"
        ):
            raise ValCalibrationError("RAW_RUN_IDENTITY_INVALID")
        for sample in dataset.samples:
            try:
                image_payload = sample.image_path.read_bytes()
                if hashlib.sha256(image_payload).hexdigest() != sample.image_sha256:
                    raise ValCalibrationError("VAL_IMAGE_SHA256_MISMATCH", str(sample.seed))
                with Image.open(sample.image_path) as opened:
                    rgb = np.asarray(opened.convert("RGB"), dtype=np.uint8)
                frame = DetectionFrame(
                    rgb8=rgb,
                    source_stamp_ns=sample.seed,
                    source_frame_id="synthetic_val_camera",
                )
                result = active_adapter.collect(frame, CollectionMode.LOW_FLOOR)
                candidates = tuple(result.raw_candidates)
                if (
                    result.model_id != "grounding-dino-tiny+sam2.1-hiera-tiny"
                    or result.runtime_device != "cuda"
                    or result.dtype != "float32"
                    or CollectionMode(result.collection_mode) is not CollectionMode.LOW_FLOOR
                    or result.fallback_used is not False
                    or dict(result.irreversible_limits) != _RAW_LIMITS
                    or len(candidates) > 300
                    or any(candidate.label != "cup" for candidate in candidates)
                ):
                    raise ValCalibrationError("RAW_RUNTIME_CONTRACT_INVALID", str(sample.seed))
                for candidate in candidates:
                    read_mask(candidate.mask, root)
                record = {
                    "schema_version": _RAW_RECORD_SCHEMA,
                    "formal_sample_index": sample.formal_sample_index,
                    "seed": sample.seed,
                    "scenario": sample.scenario,
                    "image_sha256": sample.image_sha256,
                    "raw_candidates": [candidate_to_document(item) for item in candidates],
                    "runtime": {
                        "device": "cuda",
                        "dtype": "float32",
                        "fallback_used": False,
                    },
                    "irreversible_limits": dict(_RAW_LIMITS),
                }
                record_hashes.append(
                    _write_exclusive_json(
                        records_root / f"{sample.formal_sample_index:06d}.json",
                        record,
                    )
                )
                manifest["record_count"] = len(record_hashes)
                manifest["record_inventory_sha256"] = _record_inventory_sha(record_hashes)
                _replace_manifest(manifest_path, manifest)
                if len(record_hashes) % 10 == 0 or len(record_hashes) == len(dataset.samples):
                    print(
                        f"VAL_RAW_PROGRESS completed={len(record_hashes)} "
                        f"total={len(dataset.samples)}",
                        flush=True,
                    )
            except Exception as error:
                manifest["status"] = "INVALID"
                manifest["inference_error_count"] = 1
                manifest["record_count"] = len(record_hashes)
                manifest["record_inventory_sha256"] = _record_inventory_sha(record_hashes)
                _replace_manifest(manifest_path, manifest)
                if isinstance(error, ValCalibrationError):
                    raise
                raise ValCalibrationError(
                    "RAW_INFERENCE_FAILED", type(error).__name__
                ) from error
        manifest["status"] = "VALID"
        _replace_manifest(manifest_path, manifest)
        return MappingProxyType(dict(manifest))
    except Exception:
        if manifest["status"] == "RUNNING":
            manifest["status"] = "INVALID"
            manifest["inference_error_count"] = 1
            manifest["record_count"] = len(record_hashes)
            manifest["record_inventory_sha256"] = _record_inventory_sha(record_hashes)
            _replace_manifest(manifest_path, manifest)
        raise


def load_verified_raw_records(
    root: Path,
    *,
    dataset: ValDataset,
    expected_model_manifest_sha256: str,
    expected_source_commit: str,
) -> tuple[tuple[RawCandidate, ...], ...]:
    """Load a terminal val raw run and verify every record and mask."""

    evidence_root = Path(root)
    if (
        not evidence_root.is_absolute()
        or evidence_root.is_symlink()
        or not evidence_root.is_dir()
        or _SHA256.fullmatch(expected_model_manifest_sha256) is None
        or _COMMIT.fullmatch(expected_source_commit) is None
    ):
        raise ValCalibrationError("RAW_RUN_IDENTITY_INVALID")
    manifest, _ = _read_canonical(evidence_root / "manifest.json", "RAW_MANIFEST_INVALID")
    expected_manifest = {
        "schema_version": _RAW_RUN_SCHEMA,
        "status": "VALID",
        "run_id": manifest.get("run_id"),
        "source_commit": expected_source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "model_manifest_sha256": expected_model_manifest_sha256,
        "expected_sample_count": len(dataset.samples),
        "record_count": len(dataset.samples),
        "record_inventory_sha256": manifest.get("record_inventory_sha256"),
        "inference_error_count": 0,
    }
    if dict(manifest) != expected_manifest or not isinstance(manifest.get("run_id"), str):
        raise ValCalibrationError("RAW_MANIFEST_INVALID", "identity")
    record_hashes: list[str] = []
    output: list[tuple[RawCandidate, ...]] = []
    records_root = evidence_root / "records"
    paths = tuple(sorted(records_root.glob("*.json")))
    if len(paths) != len(dataset.samples):
        raise ValCalibrationError("RAW_DENOMINATOR_INVALID")
    for sample, path in zip(dataset.samples, paths, strict=True):
        if path.name != f"{sample.formal_sample_index:06d}.json":
            raise ValCalibrationError("RAW_RECORD_ORDER_INVALID")
        record, payload = _read_canonical(path, "RAW_RECORD_INVALID")
        if (
            set(record)
            != {
                "formal_sample_index",
                "image_sha256",
                "irreversible_limits",
                "raw_candidates",
                "runtime",
                "scenario",
                "schema_version",
                "seed",
            }
            or record.get("schema_version") != _RAW_RECORD_SCHEMA
            or record.get("formal_sample_index") != sample.formal_sample_index
            or record.get("seed") != sample.seed
            or record.get("scenario") != sample.scenario
            or record.get("image_sha256") != sample.image_sha256
            or record.get("runtime")
            != {"device": "cuda", "dtype": "float32", "fallback_used": False}
            or record.get("irreversible_limits") != _RAW_LIMITS
            or not isinstance(record.get("raw_candidates"), list)
        ):
            raise ValCalibrationError("RAW_RECORD_INVALID", path.name)
        candidates = tuple(
            candidate_from_document(item) for item in record["raw_candidates"]
        )
        if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
            raise ValCalibrationError("RAW_CANDIDATE_INVALID", "duplicate IDs")
        try:
            for candidate in candidates:
                read_mask(candidate.mask, evidence_root)
        except (OSError, ValueError) as error:
            raise ValCalibrationError("RAW_MASK_INVALID", path.name) from error
        record_hashes.append(hashlib.sha256(payload).hexdigest())
        output.append(candidates)
    inventory_sha = hashlib.sha256(
        canonical_json_bytes({"record_sha256s": record_hashes})
    ).hexdigest()
    if inventory_sha != manifest["record_inventory_sha256"]:
        raise ValCalibrationError("RAW_RECORD_INVENTORY_INVALID")
    return tuple(output)


def verify_val_truth_rebind(
    *,
    raw_dataset: ValDataset,
    truth_dataset: ValDataset,
) -> Mapping[str, Any]:
    """Bind verified raw records to corrected truth only for identical val images."""

    if (
        not isinstance(raw_dataset, ValDataset)
        or not isinstance(truth_dataset, ValDataset)
        or len(raw_dataset.samples) != len(truth_dataset.samples)
    ):
        raise ValCalibrationError("RAW_TRUTH_REBIND_INVALID", "denominator")
    identities = []
    for raw_sample, truth_sample in zip(
        raw_dataset.samples,
        truth_dataset.samples,
        strict=True,
    ):
        raw_identity = (
            raw_sample.formal_sample_index,
            raw_sample.seed,
            raw_sample.scenario,
            raw_sample.configured_cup_count,
            raw_sample.image_sha256,
        )
        truth_identity = (
            truth_sample.formal_sample_index,
            truth_sample.seed,
            truth_sample.scenario,
            truth_sample.configured_cup_count,
            truth_sample.image_sha256,
        )
        if raw_identity != truth_identity:
            raise ValCalibrationError(
                "RAW_TRUTH_REBIND_INVALID",
                str(raw_sample.formal_sample_index),
            )
        identities.append(
            {
                "configured_cup_count": raw_sample.configured_cup_count,
                "formal_sample_index": raw_sample.formal_sample_index,
                "image_sha256": raw_sample.image_sha256,
                "scenario": raw_sample.scenario,
                "seed": raw_sample.seed,
            }
        )
    receipt = {
        "raw_source_manifest_sha256": raw_dataset.source_manifest_sha256,
        "raw_val_inventory_sha256": raw_dataset.inventory_sha256,
        "sample_count": len(identities),
        "sample_identity_sha256": hashlib.sha256(
            canonical_json_bytes({"samples": identities})
        ).hexdigest(),
        "truth_source_manifest_sha256": truth_dataset.source_manifest_sha256,
        "truth_val_inventory_sha256": truth_dataset.inventory_sha256,
    }
    return MappingProxyType(receipt)


def _greedy_matches(
    candidates: Sequence[RawCandidate], truths: Sequence[Mapping[str, Any]]
) -> tuple[tuple[int, int], ...]:
    unmatched = set(range(len(truths)))
    matches: list[tuple[int, int]] = []
    for candidate_index in sorted(
        range(len(candidates)),
        key=lambda index: (-candidates[index].ranking_score, candidates[index].candidate_id),
    ):
        eligible = [
            (
                box_iou(
                    candidates[candidate_index].bbox_xyxy,
                    tuple(truths[truth_index]["absolute_xyxy"]),
                ),
                truth_index,
            )
            for truth_index in unmatched
        ]
        if eligible:
            overlap, truth_index = max(eligible, key=lambda item: (item[0], -item[1]))
            if overlap >= 0.5:
                unmatched.remove(truth_index)
                matches.append((candidate_index, truth_index))
    return tuple(matches)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if denominator == 0 else float(numerator / denominator)


def _threshold_point(
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    quality: Decimal,
) -> dict[str, Any]:
    thresholds = GroundedSamBenchmarkThresholds(
        Decimal("0.25"),
        Decimal("0.25"),
        quality,
        Decimal("0.25"),
        Decimal("0.85"),
        64,
        Decimal("0.50"),
    )
    totals: Counter[str] = Counter()
    scenarios: dict[str, Counter[str]] = {
        name: Counter() for name in dataset.scenario_counts
    }
    decisions: Counter[str] = Counter()
    no_cup_unique_count = 0
    for sample, raw in zip(dataset.samples, raw_candidates_by_sample, strict=True):
        candidates = thresholds.filter_candidates(raw)[:16]
        matches = _greedy_matches(candidates, sample.truths)
        tp = len(matches)
        fp = len(candidates) - tp
        fn = len(sample.truths) - tp
        totals.update(tp=tp, fp=fp, fn=fn)
        scenarios[sample.scenario].update(tp=tp, fp=fp, fn=fn, images=1)
        decision = "NOT_FOUND" if not candidates else "UNIQUE" if len(candidates) == 1 else "AMBIGUOUS"
        decisions[decision] += 1
        if sample.scenario == "no_cup" and decision == "UNIQUE":
            no_cup_unique_count += 1
    precision = _ratio(totals["tp"], totals["tp"] + totals["fp"])
    recall = _ratio(totals["tp"], totals["tp"] + totals["fn"])
    f1 = _ratio(2.0 * precision * recall, precision + recall)
    scenario_metrics = {
        name: dict(sorted(values.items())) for name, values in sorted(scenarios.items())
    }

    def scenario_recall(name: str) -> float:
        values = scenarios.get(name, Counter())
        return _ratio(values["tp"], values["tp"] + values["fn"])

    return {
        "sam_quality": format(quality, ".2f"),
        "totals": {"fn": totals["fn"], "fp": totals["fp"], "tp": totals["tp"]},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "small_far_recall": scenario_recall("small_far_cup"),
        "multi_cup_recall": scenario_recall("two_cups"),
        "decision_counts": dict(sorted(decisions.items())),
        "scenario_metrics": scenario_metrics,
        "safety_gates": {"no_cup_unique_count": no_cup_unique_count},
    }


def select_sam_quality_threshold(
    *,
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    quality_grid: Sequence[str] = tuple(format(value, ".2f") for value in _FROZEN_GRID),
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    """Evaluate and select the preregistered val-only SAM threshold grid."""

    if len(raw_candidates_by_sample) != len(dataset.samples):
        raise ValCalibrationError("RAW_DENOMINATOR_INVALID")
    try:
        normalized = tuple(Decimal(value) for value in quality_grid)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID") from error
    if normalized != _FROZEN_GRID and normalized not in {
        (Decimal("0.70"), Decimal("0.75"), Decimal("0.80")),
    }:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID")
    points = tuple(
        MappingProxyType(_threshold_point(dataset, raw_candidates_by_sample, quality))
        for quality in normalized
    )

    def selection_key(point: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            -float(point["f1"]),
            -float(point["recall"]),
            -float(point["small_far_recall"]),
            -float(point["multi_cup_recall"]),
            int(point["safety_gates"]["no_cup_unique_count"]),
            -Decimal(str(point["sam_quality"])),
            int(point["totals"]["fp"]),
        )

    selected = min(points, key=selection_key)
    return selected, points


def _mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    left_mask = np.asarray(left, dtype=bool)
    right_mask = np.asarray(right, dtype=bool)
    if left_mask.shape != right_mask.shape or left_mask.ndim != 2:
        raise ValCalibrationError("MASK_TRUTH_SHAPE_INVALID")
    union = int(np.logical_or(left_mask, right_mask).sum())
    return 0.0 if union == 0 else float(np.logical_and(left_mask, right_mask).sum() / union)


def _mask_aware_threshold_point(
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    raw_evidence_root: Path,
    quality: Decimal,
) -> dict[str, Any]:
    thresholds = GroundedSamBenchmarkThresholds(
        Decimal("0.25"),
        Decimal("0.25"),
        quality,
        Decimal("0.25"),
        Decimal("0.85"),
        64,
        Decimal("0.50"),
    )
    totals: Counter[str] = Counter()
    scenarios: dict[str, Counter[str]] = {
        name: Counter() for name in dataset.scenario_counts
    }
    decisions: Counter[str] = Counter()
    mask_ious: list[float] = []
    no_cup_unique_count = 0
    for sample, raw in zip(dataset.samples, raw_candidates_by_sample, strict=True):
        candidates = thresholds.filter_candidates(raw)[:16]
        matches = _greedy_matches(candidates, sample.truths)
        passing = 0
        for candidate_index, truth_index in matches:
            truth_mask = sample.truths[truth_index].get("mask")
            if not isinstance(truth_mask, np.ndarray):
                raise ValCalibrationError("VAL_TRUTH_MASK_INVALID", str(sample.seed))
            overlap = _mask_iou(
                read_mask(candidates[candidate_index].mask, raw_evidence_root),
                truth_mask,
            )
            mask_ious.append(overlap)
            if overlap >= 0.80:
                passing += 1
        tp = passing
        fp = len(candidates) - passing
        fn = len(sample.truths) - passing
        totals.update(
            tp=tp,
            fp=fp,
            fn=fn,
            bbox_matches=len(matches),
            mask_pass=passing,
            mask_fail=len(matches) - passing,
        )
        scenarios[sample.scenario].update(tp=tp, fp=fp, fn=fn, images=1)
        decision = "NOT_FOUND" if not candidates else "UNIQUE" if len(candidates) == 1 else "AMBIGUOUS"
        decisions[decision] += 1
        if sample.scenario == "no_cup" and decision == "UNIQUE":
            no_cup_unique_count += 1
    precision = _ratio(totals["tp"], totals["tp"] + totals["fp"])
    recall = _ratio(totals["tp"], totals["tp"] + totals["fn"])
    f1 = _ratio(2.0 * precision * recall, precision + recall)

    def scenario_recall(name: str) -> float:
        values = scenarios.get(name, Counter())
        return _ratio(values["tp"], values["tp"] + values["fn"])

    return {
        "sam_quality": format(quality, ".2f"),
        "totals": {"fn": totals["fn"], "fp": totals["fp"], "tp": totals["tp"]},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "small_far_recall": scenario_recall("small_far_cup"),
        "multi_cup_recall": scenario_recall("two_cups"),
        "decision_counts": dict(sorted(decisions.items())),
        "scenario_metrics": {
            name: dict(sorted(values.items())) for name, values in sorted(scenarios.items())
        },
        "safety_gates": {"no_cup_unique_count": no_cup_unique_count},
        "mask_metrics": {
            "bbox_match_count": totals["bbox_matches"],
            "pass_count": totals["mask_pass"],
            "fail_count": totals["mask_fail"],
            "truth_iou_threshold": 0.80,
            "minimum_iou": min(mask_ious) if mask_ious else None,
            "median_iou": float(np.median(mask_ious)) if mask_ious else None,
            "maximum_iou": max(mask_ious) if mask_ious else None,
        },
    }


def select_mask_aware_sam_quality_threshold(
    *,
    dataset: ValDataset,
    raw_candidates_by_sample: Sequence[tuple[RawCandidate, ...]],
    raw_evidence_root: Path,
    quality_grid: Sequence[str] = tuple(format(value, ".2f") for value in _LOW_QUALITY_GRID),
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    """Select the preregistered low SAM-quality grid with truth-mask safety."""

    root = Path(raw_evidence_root)
    if (
        len(raw_candidates_by_sample) != len(dataset.samples)
        or not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
    ):
        raise ValCalibrationError("MASK_AWARE_INPUT_INVALID")
    try:
        normalized = tuple(Decimal(value) for value in quality_grid)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID") from error
    if normalized not in {
        _LOW_QUALITY_GRID,
        (Decimal("0.00"), Decimal("0.10"), Decimal("0.20")),
    }:
        raise ValCalibrationError("CALIBRATION_GRID_INVALID")
    points = tuple(
        MappingProxyType(
            _mask_aware_threshold_point(dataset, raw_candidates_by_sample, root, quality)
        )
        for quality in normalized
    )

    def selection_key(point: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            -float(point["f1"]),
            -float(point["recall"]),
            -float(point["small_far_recall"]),
            -float(point["multi_cup_recall"]),
            int(point["safety_gates"]["no_cup_unique_count"]),
            -Decimal(str(point["sam_quality"])),
            int(point["totals"]["fp"]),
        )

    return min(points, key=selection_key), points


def write_mask_aware_calibration_evidence(
    *,
    output_root: Path,
    dataset: ValDataset,
    raw_run_root: Path,
    raw_manifest_sha256: str,
    source_commit: str,
    selected: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Persist an exclusive mask-aware low-grid calibration result."""

    if (
        _SHA256.fullmatch(raw_manifest_sha256) is None
        or _COMMIT.fullmatch(source_commit) is None
        or not Path(raw_run_root).is_absolute()
        or len(points) != len(_LOW_QUALITY_GRID)
    ):
        raise ValCalibrationError("CALIBRATION_PROVENANCE_INVALID")
    root = _create_output_root(output_root)
    report = {
        "schema_version": "so101-grounded-sam-val-mask-aware-calibration-report/v1",
        "source_commit": source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "raw_run_root": str(Path(raw_run_root)),
        "raw_manifest_sha256": raw_manifest_sha256,
        "frozen_thresholds": {
            "box": "0.25",
            "text": "0.25",
            "truth_box_iou": "0.50",
            "truth_mask_iou": "0.80",
            "sam_quality_grid": [format(value, ".2f") for value in _LOW_QUALITY_GRID],
        },
        "selected_sam_quality": selected["sam_quality"],
        "selected": dict(selected),
        "grid_points": [dict(point) for point in points],
        "inference_rerun": False,
        "synthetic_test_access": "none",
        "coco100_access": "none",
    }
    try:
        report_sha = atomic_write_json(root / "report.json", report)
        atomic_write_json(
            root / "manifest.json",
            {
                "schema_version": "so101-grounded-sam-val-mask-aware-calibration-run/v1",
                "status": "VALID",
                "source_commit": source_commit,
                "val_inventory_sha256": dataset.inventory_sha256,
                "raw_manifest_sha256": raw_manifest_sha256,
                "report_sha256": report_sha,
            },
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_WRITE_FAILED") from error
    return MappingProxyType(report)


__all__ = (
    "ValCalibrationError",
    "ValDataset",
    "ValSample",
    "candidate_from_document",
    "candidate_to_document",
    "collect_val_raw",
    "load_locked_val_dataset",
    "load_verified_raw_records",
    "select_mask_aware_sam_quality_threshold",
    "select_sam_quality_threshold",
    "verify_val_truth_rebind",
    "write_mask_aware_calibration_evidence",
    "write_calibration_evidence",
)
