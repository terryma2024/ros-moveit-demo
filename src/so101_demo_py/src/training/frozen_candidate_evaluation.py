"""Frozen-candidate verification and one-time synthetic-test evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from PIL import Image
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import CollectionMode
from so101_demo.perception_benchmark.calibration import GroundedSamBenchmarkThresholds
from so101_demo.perception_benchmark.codec import encode_mask_rle, read_mask
from so101_demo.perception_benchmark.contracts import DecisionOutput, MaskRef
from so101_demo.perception_benchmark.dataset import rasterize_polygon
from so101_demo.perception_benchmark.matching import mask_iou
from so101_demo.training.grounding_dino_dataset import (
    _boxes_match,
    _label_polygons,
    _manifest,
    _sample_paths,
    _truth_instances,
    _validate_manifest_members,
    _validate_sample_shape,
)
from so101_demo.training.grounding_dino_finetune import box_iou

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SCHEMA = "so101-grounded-sam-frozen-candidate/v1"
_PIPELINE = "grounding-dino-tiny+sam2.1-hiera-tiny"
_PROMPT_PROFILE = {"cup": "cup."}
_RAW_THRESHOLDS = {
    "box_threshold": "0.01",
    "maximum_candidates": 300,
    "sam_quality_threshold": "0.00",
    "selector": "off",
    "text_threshold": "0.01",
}
_PRODUCTION_THRESHOLDS = {
    "box_threshold": "0.25",
    "duplicate_iou_threshold": "0.85",
    "maximum_candidates": 16,
    "maximum_mask_area_ratio": "0.50",
    "minimum_mask_pixels": 64,
    "sam_quality_threshold": "0.90",
    "selector_minimum_confidence": "0.25",
    "text_threshold": "0.25",
}
_SELECTOR = {
    "eligible_cardinality": "exactly_one",
    "implementation": "so101_demo.application.object_pose.TargetSelector",
    "multiple_results": "TARGET_AMBIGUOUS",
    "query_class": "cup",
    "zero_result": "TARGET_NOT_FOUND",
}
_SAM_CONTRACT = {
    "prompt_source": "current_frame_dino_box_only",
    "state": "stateless_per_frame",
    "weights": "frozen",
}


class FrozenCandidateError(RuntimeError):
    """Stable fail-closed error for a frozen candidate or test run."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class FrozenCandidateLock:
    path: Path
    file_sha256: str
    lock_sha256: str
    document: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "document", MappingProxyType(dict(self.document)))


@dataclass(frozen=True, slots=True)
class FrozenSyntheticTest:
    samples: tuple[Mapping[str, Any], ...]
    scenario_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "samples", tuple(self.samples))
        object.__setattr__(self, "scenario_counts", MappingProxyType(dict(self.scenario_counts)))


def verify_frozen_candidate_lock(path: Path, expected_file_sha256: str) -> FrozenCandidateLock:
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_file():
        raise FrozenCandidateError("LOCK_UNREADABLE", str(candidate))
    if not isinstance(expected_file_sha256, str) or _SHA256.fullmatch(expected_file_sha256) is None:
        raise FrozenCandidateError("LOCK_FILE_SHA256_INVALID", str(expected_file_sha256))
    payload = candidate.read_bytes()
    file_sha256 = hashlib.sha256(payload).hexdigest()
    if file_sha256 != expected_file_sha256:
        raise FrozenCandidateError("LOCK_FILE_SHA256_MISMATCH", str(candidate))
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FrozenCandidateError("LOCK_DOCUMENT_INVALID", str(candidate)) from error
    if not isinstance(document, dict) or payload != _canonical(document):
        raise FrozenCandidateError("LOCK_NOT_CANONICAL", str(candidate))
    if set(document) != {
        "code",
        "lock_sha256",
        "model_bundle",
        "pipeline_id",
        "prompt_profile",
        "sam_runtime_contract",
        "schema_version",
        "selector",
        "synthetic_test_seal",
        "threshold_provenance",
        "thresholds",
    }:
        raise FrozenCandidateError("LOCK_DOCUMENT_INVALID", "top-level fields")
    stored_lock_sha = _require_sha(document.get("lock_sha256"), "LOCK_DIGEST_INVALID")
    unhashed = dict(document)
    unhashed.pop("lock_sha256")
    if hashlib.sha256(_canonical(unhashed)).hexdigest() != stored_lock_sha:
        raise FrozenCandidateError("LOCK_DIGEST_MISMATCH", str(candidate))
    if stat.S_IMODE(candidate.stat().st_mode) & 0o222:
        raise FrozenCandidateError("LOCK_MUTABLE", str(candidate))
    if (
        document.get("schema_version") != _SCHEMA
        or document.get("pipeline_id") != _PIPELINE
        or document.get("prompt_profile") != _PROMPT_PROFILE
        or document.get("sam_runtime_contract") != _SAM_CONTRACT
        or document.get("selector") != _SELECTOR
    ):
        raise FrozenCandidateError("LOCK_CONTRACT_INVALID", str(candidate))
    thresholds = _mapping(document.get("thresholds"), "LOCK_THRESHOLDS_INVALID")
    if (
        thresholds.get("raw_collection") != _RAW_THRESHOLDS
        or thresholds.get("production") != _PRODUCTION_THRESHOLDS
        or thresholds.get("production_candidate_mask_iou_threshold") != "0.98"
        or set(thresholds)
        != {
            "raw_collection",
            "production",
            "production_candidate_mask_iou_threshold",
        }
    ):
        raise FrozenCandidateError("LOCK_THRESHOLDS_INVALID", str(candidate))
    code = _mapping(document.get("code"), "LOCK_CODE_INVALID")
    if set(code) != {"creation_commit", "gated_implementation_commit"} or any(
        not isinstance(code.get(name), str) or _COMMIT.fullmatch(code[name]) is None
        for name in code
    ):
        raise FrozenCandidateError("LOCK_CODE_INVALID", str(candidate))
    provenance = _mapping(document.get("threshold_provenance"), "LOCK_PROVENANCE_INVALID")
    if (
        set(provenance)
        != {
            "coco100_tuning",
            "dino_box_text",
            "frozen_sam_geometry_filters",
            "sealed_test_tuning",
            "source_threshold_lock_sha256",
        }
        or provenance.get("dino_box_text") != "synthetic_val_epoch_7_checkpoint_manifest"
        or provenance.get("frozen_sam_geometry_filters") != "unchanged_formal_grounded_sam_lock"
        or provenance.get("sealed_test_tuning") is not False
        or provenance.get("coco100_tuning") is not False
    ):
        raise FrozenCandidateError("LOCK_PROVENANCE_INVALID", str(candidate))
    _require_sha(
        provenance.get("source_threshold_lock_sha256"),
        "LOCK_PROVENANCE_INVALID",
    )
    bundle_document = _mapping(document.get("model_bundle"), "LOCK_MODEL_BUNDLE_INVALID")
    expected_bundle_fields = {
        "detector_checkpoint_manifest_sha256",
        "detector_model_sha256",
        "manifest_sha256",
        "root",
        "sam_model_id",
        "sam_revision",
        "sam_source_bundle_manifest_sha256",
        "sam_transformers_model_sha256",
    }
    if set(bundle_document) != expected_bundle_fields:
        raise FrozenCandidateError("LOCK_MODEL_BUNDLE_INVALID", "fields")
    for name in (
        "detector_checkpoint_manifest_sha256",
        "detector_model_sha256",
        "manifest_sha256",
        "sam_source_bundle_manifest_sha256",
        "sam_transformers_model_sha256",
    ):
        _require_sha(bundle_document.get(name), "LOCK_MODEL_BUNDLE_INVALID")
    if (
        bundle_document.get("sam_model_id") != "facebook/sam2.1-hiera-tiny"
        or bundle_document.get("sam_revision") != "de431c4043854a71d8101e17995dfe596bf101a5"
    ):
        raise FrozenCandidateError("LOCK_MODEL_BUNDLE_INVALID", "SAM identity")
    root_value = bundle_document.get("root")
    if not isinstance(root_value, str) or not Path(root_value).is_absolute():
        raise FrozenCandidateError("LOCK_MODEL_BUNDLE_INVALID", "root")
    bundle_root = Path(root_value)
    try:
        bundle = verify_model_bundle(bundle_root, str(bundle_document["manifest_sha256"]))
    except Exception as error:
        raise FrozenCandidateError("LOCK_MODEL_BUNDLE_INVALID", str(error)) from error
    if (
        Path(bundle.root) != bundle_root
        or bundle.target_class_id != "cup"
        or bundle.prompt != "cup."
        or _sha256_file(bundle_root / "grounding-dino-tiny/model.safetensors")
        != bundle_document["detector_model_sha256"]
        or _sha256_file(bundle_root / "sam2.1-hiera-tiny/model.safetensors")
        != bundle_document["sam_transformers_model_sha256"]
    ):
        raise FrozenCandidateError("LOCK_MODEL_BUNDLE_INVALID", "external hashes")
    seal = _mapping(document.get("synthetic_test_seal"), "LOCK_TEST_SEAL_INVALID")
    if set(seal) != {
        "converted_sealed_members_sha256",
        "sample_count",
        "scenario_quotas",
        "seed_range",
        "source_archive_sha256",
        "source_manifest_sha256",
    }:
        raise FrozenCandidateError("LOCK_TEST_SEAL_INVALID", "fields")
    for name in (
        "converted_sealed_members_sha256",
        "source_archive_sha256",
        "source_manifest_sha256",
    ):
        _require_sha(seal.get(name), "LOCK_TEST_SEAL_INVALID")
    sample_count = seal.get("sample_count")
    quotas = seal.get("scenario_quotas")
    seed_range = seal.get("seed_range")
    if (
        type(sample_count) is not int
        or sample_count <= 0
        or not isinstance(quotas, dict)
        or not quotas
        or any(
            not isinstance(name, str) or type(count) is not int or count <= 0
            for name, count in quotas.items()
        )
        or sum(quotas.values()) != sample_count
        or not isinstance(seed_range, list)
        or len(seed_range) != 2
        or any(type(value) is not int for value in seed_range)
        or seed_range[1] - seed_range[0] + 1 != sample_count
    ):
        raise FrozenCandidateError("LOCK_TEST_SEAL_INVALID", "counts")
    return FrozenCandidateLock(
        path=candidate,
        file_sha256=file_sha256,
        lock_sha256=stored_lock_sha,
        document=document,
    )


def load_locked_synthetic_test(
    *,
    lock: FrozenCandidateLock,
    source_root: Path,
    sealed_members_path: Path,
) -> FrozenSyntheticTest:
    if not isinstance(lock, FrozenCandidateLock):
        raise FrozenCandidateError("LOCK_CAPABILITY_INVALID", "wrong type")
    root = Path(source_root)
    sealed_path = Path(sealed_members_path)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
        or not sealed_path.is_absolute()
        or sealed_path.is_symlink()
        or not sealed_path.is_file()
    ):
        raise FrozenCandidateError("TEST_SOURCE_INVALID", str(root))
    if (
        stat.S_IMODE(root.stat().st_mode) & 0o222
        or stat.S_IMODE(sealed_path.stat().st_mode) & 0o222
    ):
        raise FrozenCandidateError("TEST_SOURCE_MUTABLE", str(root))
    root = root.resolve()
    seal_contract = lock.document["synthetic_test_seal"]
    expected_seal_sha = seal_contract["converted_sealed_members_sha256"]
    seal_payload = sealed_path.read_bytes()
    if hashlib.sha256(seal_payload).hexdigest() != expected_seal_sha:
        raise FrozenCandidateError("SEALED_INVENTORY_SHA256_MISMATCH", str(sealed_path))
    try:
        sealed = json.loads(seal_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FrozenCandidateError("SEALED_INVENTORY_INVALID", str(sealed_path)) from error
    if not isinstance(sealed, dict) or seal_payload != _canonical(sealed):
        raise FrozenCandidateError("SEALED_INVENTORY_INVALID", "not canonical")
    expected_seal_fields = {
        "converter_commit",
        "sample_count",
        "samples",
        "schema_version",
        "sealed",
        "source_archive_sha256",
        "source_manifest_sha256",
        "split",
    }
    if (
        set(sealed) != expected_seal_fields
        or sealed.get("schema_version") != 1
        or sealed.get("sealed") is not True
        or sealed.get("split") != "test"
        or sealed.get("source_archive_sha256") != seal_contract["source_archive_sha256"]
        or sealed.get("source_manifest_sha256") != seal_contract["source_manifest_sha256"]
        or sealed.get("sample_count") != seal_contract["sample_count"]
        or not isinstance(sealed.get("samples"), list)
        or len(sealed["samples"]) != seal_contract["sample_count"]
    ):
        raise FrozenCandidateError("SEALED_INVENTORY_INVALID", "identity")
    manifest_path = root / "dataset-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise FrozenCandidateError("SOURCE_MANIFEST_SHA256_MISMATCH", str(manifest_path))
    if stat.S_IMODE(manifest_path.stat().st_mode) & 0o222:
        raise FrozenCandidateError("TEST_SOURCE_MUTABLE", str(manifest_path))
    if _sha256_file(manifest_path) != seal_contract["source_manifest_sha256"]:
        raise FrozenCandidateError("SOURCE_MANIFEST_SHA256_MISMATCH", str(manifest_path))

    sealed_by_image: dict[str, Mapping[str, Any]] = {}
    member_payloads: dict[str, bytes] = {}
    member_directories = {"image": "images", "label": "labels", "truth": "truth"}
    for item in sealed["samples"]:
        if not isinstance(item, dict) or set(item) != {
            "image_relpath",
            "image_sha256",
            "label_relpath",
            "label_sha256",
            "truth_relpath",
            "truth_sha256",
        }:
            raise FrozenCandidateError("SEALED_INVENTORY_INVALID", "sample fields")
        for kind in ("image", "label", "truth"):
            relative = _test_relative_path(item.get(f"{kind}_relpath"), kind)
            path = root.joinpath(*relative.parts)
            if (
                path.is_symlink()
                or not path.is_file()
                or path.resolve().parent != (root / member_directories[kind] / "test")
            ):
                raise FrozenCandidateError("SEALED_MEMBER_INVALID", relative.as_posix())
            if stat.S_IMODE(path.stat().st_mode) & 0o222:
                raise FrozenCandidateError("TEST_SOURCE_MUTABLE", relative.as_posix())
            payload = path.read_bytes()
            expected_sha = _require_sha(item.get(f"{kind}_sha256"), "SEALED_INVENTORY_INVALID")
            if hashlib.sha256(payload).hexdigest() != expected_sha:
                raise FrozenCandidateError("SEALED_MEMBER_SHA256_MISMATCH", relative.as_posix())
            member_payloads[relative.as_posix()] = payload
        image_relative = str(item["image_relpath"])
        if image_relative in sealed_by_image:
            raise FrozenCandidateError("SEALED_INVENTORY_INVALID", "duplicate image")
        sealed_by_image[image_relative] = item

    try:
        manifest, _ = _manifest(root)
        manifest_samples = [
            _validate_sample_shape(item, index) for index, item in enumerate(manifest["samples"])
        ]
        _validate_manifest_members(manifest, manifest_samples)
    except Exception as error:
        raise FrozenCandidateError("SOURCE_MANIFEST_INVALID", str(error)) from error
    test_samples = [item for item in manifest_samples if item["split"] == "test"]
    if (
        len(test_samples) != seal_contract["sample_count"]
        or Counter(item["scenario"] for item in test_samples)
        != Counter(seal_contract["scenario_quotas"])
        or sorted(item["seed"] for item in test_samples)
        != list(range(*_inclusive_range(seal_contract["seed_range"])))
    ):
        raise FrozenCandidateError("TEST_MANIFEST_CONTRACT_INVALID", "counts or seeds")

    width = manifest["image_width"]
    height = manifest["image_height"]
    output_samples: list[Mapping[str, Any]] = []
    for sample in sorted(test_samples, key=lambda item: item["seed"]):
        paths = _sample_paths(sample)
        image_relative = paths["image"].as_posix()
        sealed_item = sealed_by_image.get(image_relative)
        if sealed_item is None or any(
            sealed_item[f"{kind}_relpath"] != paths[kind].as_posix()
            for kind in ("image", "label", "truth")
        ):
            raise FrozenCandidateError("TEST_MANIFEST_CONTRACT_INVALID", image_relative)
        label_payload = member_payloads[paths["label"].as_posix()]
        truth_payload = member_payloads[paths["truth"].as_posix()]
        try:
            polygons = _label_polygons(label_payload, member=paths["label"].as_posix())
            truths = _truth_instances(
                truth_payload,
                member=paths["truth"].as_posix(),
                sample=sample,
                image_width=width,
                image_height=height,
                schema_version=manifest["schema_version"],
                scene_geometry=manifest.get("scene_geometry"),
            )
        except Exception as error:
            raise FrozenCandidateError("TEST_ANNOTATION_INVALID", str(error)) from error
        if len(polygons) != len(truths):
            raise FrozenCandidateError("TEST_ANNOTATION_INVALID", "instance count")
        boxes: list[Mapping[str, Any]] = []
        for polygon, truth in zip(polygons, truths, strict=True):
            from so101_demo.training.grounding_dino_dataset import polygon_to_box

            box = polygon_to_box(polygon, width, height)
            if not _boxes_match(box, truth["box"]):
                raise FrozenCandidateError("TEST_ANNOTATION_INVALID", "box mismatch")
            mask = rasterize_polygon(tuple(polygon), width, height)
            mask.setflags(write=False)
            boxes.append(
                MappingProxyType(
                    {
                        "absolute_xyxy": box.absolute_xyxy,
                        "normalized_xyxy": box.normalized_xyxy,
                        "visible_pixel_count": truth["visible_pixel_count"],
                        "occlusion": truth["occlusion"],
                        "mask": mask,
                    }
                )
            )
        output_samples.append(
            MappingProxyType(
                {
                    "seed": sample["seed"],
                    "scenario": sample["scenario"],
                    "configured_cup_count": sample["configured_cup_count"],
                    "visible_instance_count": sample["visible_instance_count"],
                    "image_path": root.joinpath(*paths["image"].parts),
                    "image_sha256": sealed_item["image_sha256"],
                    "boxes": tuple(boxes),
                }
            )
        )
    return FrozenSyntheticTest(
        samples=tuple(output_samples),
        scenario_counts=Counter(item["scenario"] for item in test_samples),
    )


def map_production_candidates(
    *,
    raw_candidates: Sequence[Any],
    production_candidates: Sequence[Any],
    raw_mask_loader: Callable[[Any], np.ndarray],
    minimum_mask_iou: float,
) -> Mapping[str, str]:
    if (
        isinstance(minimum_mask_iou, bool)
        or not isinstance(minimum_mask_iou, (int, float))
        or not math.isfinite(float(minimum_mask_iou))
        or not 0.0 < float(minimum_mask_iou) <= 1.0
    ):
        raise ValueError("minimum_mask_iou must be in (0, 1]")
    available = {candidate.candidate_id: candidate for candidate in raw_candidates}
    if len(available) != len(tuple(raw_candidates)):
        raise FrozenCandidateError("PRODUCTION_CANDIDATE_MAPPING_INVALID", "raw IDs")
    result: dict[str, str] = {}
    for observed in production_candidates:
        matches: list[Any] = []
        for raw in available.values():
            if (
                observed.class_id != raw.label
                or tuple(observed.bbox_xyxy) != tuple(raw.bbox_xyxy)
                or observed.confidence != raw.ranking_score
                or raw.grounding_box_score != observed.confidence
                or raw.sam_quality is None
                or observed.segmentation_quality is None
            ):
                continue
            raw_mask = np.asarray(raw_mask_loader(raw.mask), dtype=bool)
            if raw_mask.shape != observed.mask.shape:
                continue
            if mask_iou(raw_mask, np.asarray(observed.mask, dtype=bool)) >= float(minimum_mask_iou):
                matches.append(raw)
        if len(matches) != 1 or observed.instance_id in result:
            raise FrozenCandidateError("PRODUCTION_CANDIDATE_MAPPING_INVALID", observed.instance_id)
        raw = matches[0]
        available.pop(raw.candidate_id)
        result[observed.instance_id] = raw.candidate_id
    return MappingProxyType(result)


def initialize_evaluation_output(
    *,
    output_root: Path,
    lock: FrozenCandidateLock,
    run_id: str,
    source_commit: str,
) -> str:
    root = Path(output_root)
    if not isinstance(lock, FrozenCandidateLock):
        raise FrozenCandidateError("LOCK_CAPABILITY_INVALID", "wrong type")
    if not root.is_absolute() or root.is_symlink():
        raise FrozenCandidateError("OUTPUT_ROOT_INVALID", str(root))
    if os.path.lexists(root):
        raise FrozenCandidateError("OUTPUT_ROOT_ALREADY_EXISTS", str(root))
    if not root.parent.is_dir() or root.parent.is_symlink():
        raise FrozenCandidateError("OUTPUT_PARENT_INVALID", str(root.parent))
    if not isinstance(run_id, str) or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", run_id) is None:
        raise FrozenCandidateError("RUN_ID_INVALID", str(run_id))
    if not isinstance(source_commit, str) or _COMMIT.fullmatch(source_commit) is None:
        raise FrozenCandidateError("SOURCE_COMMIT_INVALID", str(source_commit))
    os.mkdir(root, 0o700)
    os.mkdir(root / "records", 0o700)
    os.mkdir(root / "production-masks", 0o700)
    started_at = datetime.now(timezone.utc).isoformat()
    access = {
        "schema_version": "so101-grounded-sam-synthetic-test-access/v1",
        "run_id": run_id,
        "source_commit": source_commit,
        "output_root": str(root),
        "candidate_lock_path": str(lock.path),
        "candidate_lock_file_sha256": lock.file_sha256,
        "candidate_lock_sha256": lock.lock_sha256,
        "sealed_member_inventory_sha256": lock.document["synthetic_test_seal"][
            "converted_sealed_members_sha256"
        ],
        "granted_at": started_at,
    }
    access["event_sha256"] = hashlib.sha256(_canonical(access)).hexdigest()
    _write_exclusive_json(root / "access-event.json", access)
    _write_exclusive_json(
        root / "manifest.json",
        {
            "schema_version": "so101-grounded-sam-synthetic-test-run/v1",
            "status": "RUNNING",
            "run_id": run_id,
            "source_commit": source_commit,
            "candidate_lock_file_sha256": lock.file_sha256,
            "candidate_lock_sha256": lock.lock_sha256,
            "access_event_sha256": access["event_sha256"],
            "expected_sample_count": lock.document["synthetic_test_seal"]["sample_count"],
            "record_count": 0,
            "started_at": started_at,
            "ended_at": None,
            "report_sha256": None,
            "safety_passed": None,
        },
    )
    _fsync_directory(root)
    return str(access["event_sha256"])


def mark_evaluation_invalid(output_root: Path, error: Exception) -> Mapping[str, Any]:
    root = Path(output_root)
    manifest_path = root / "manifest.json"
    manifest = _read_canonical_mapping(manifest_path, "RUN_MANIFEST_INVALID")
    if manifest.get("status") != "RUNNING":
        raise FrozenCandidateError("RUN_MANIFEST_INVALID", "run is already terminal")
    code = error.code if isinstance(error, FrozenCandidateError) else type(error).__name__
    failure = {
        "schema_version": "so101-grounded-sam-synthetic-test-failure/v1",
        "code": code,
        "detail": error.detail if isinstance(error, FrozenCandidateError) else str(error),
        "error_type": type(error).__name__,
        "record_count": len(tuple((root / "records").glob("*.json"))),
    }
    failure_sha = _write_exclusive_json(root / "failure.json", failure)
    manifest["status"] = "INVALID"
    manifest["record_count"] = failure["record_count"]
    manifest["ended_at"] = datetime.now(timezone.utc).isoformat()
    manifest["failure_sha256"] = failure_sha
    manifest["safety_passed"] = False
    _replace_json(manifest_path, manifest)
    _fsync_directory(root)
    return MappingProxyType(failure)


def evaluate_frozen_synthetic_test(
    *,
    dataset: FrozenSyntheticTest,
    lock: FrozenCandidateLock,
    output_root: Path,
    raw_adapter: Any,
    production_observer: Callable[[Any], Any],
    source_commit: str,
    run_id: str,
    raw_mask_loader: Callable[[Any], np.ndarray] | None = None,
) -> Mapping[str, Any]:
    root = Path(output_root)
    if not isinstance(dataset, FrozenSyntheticTest) or not isinstance(lock, FrozenCandidateLock):
        raise FrozenCandidateError("EVALUATION_INPUT_INVALID", "typed inputs")
    manifest_path = root / "manifest.json"
    manifest = _read_canonical_mapping(manifest_path, "RUN_MANIFEST_INVALID")
    expected_manifest = {
        "status": "RUNNING",
        "run_id": run_id,
        "source_commit": source_commit,
        "candidate_lock_file_sha256": lock.file_sha256,
        "candidate_lock_sha256": lock.lock_sha256,
        "expected_sample_count": len(dataset.samples),
    }
    if any(manifest.get(name) != value for name, value in expected_manifest.items()):
        raise FrozenCandidateError("RUN_MANIFEST_INVALID", "identity")
    if dict(dataset.scenario_counts) != dict(
        lock.document["synthetic_test_seal"]["scenario_quotas"]
    ):
        raise FrozenCandidateError("TEST_DATASET_IDENTITY_MISMATCH", "scenario counts")
    production_values = lock.document["thresholds"]["production"]
    calibrated_thresholds = GroundedSamBenchmarkThresholds(
        Decimal(production_values["box_threshold"]),
        Decimal(production_values["text_threshold"]),
        Decimal(production_values["sam_quality_threshold"]),
        Decimal(production_values["selector_minimum_confidence"]),
        Decimal(production_values["duplicate_iou_threshold"]),
        production_values["minimum_mask_pixels"],
        Decimal(production_values["maximum_mask_area_ratio"]),
    )
    mapping_iou = float(lock.document["thresholds"]["production_candidate_mask_iou_threshold"])
    load_raw_mask = raw_mask_loader or (lambda ref: read_mask(ref, root))
    counters: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    scenario_totals: dict[str, Counter[str]] = {
        scenario: Counter() for scenario in dataset.scenario_counts
    }
    area_totals: dict[str, Counter[str]] = {
        bucket: Counter() for bucket in ("small", "medium", "large")
    }
    strata_totals: dict[str, Counter[str]] = {
        name: Counter() for name in ("small_far", "partial_occlusion", "single_cup", "multi_cup")
    }
    occlusion_totals: Counter[str] = Counter()
    occlusion_visible_fractions: list[float] = []
    mask_ious: list[float] = []
    record_hashes: list[str] = []
    image_hits = 0
    for index, sample in enumerate(dataset.samples):
        observation = None
        sample_errors: list[str] = []
        production_documents: list[Mapping[str, Any]] = []
        matched_pairs: list[tuple[int, int]] = []
        truths = tuple(sample["boxes"])
        try:
            image_path = Path(sample["image_path"])
            if _sha256_file(image_path) != sample["image_sha256"]:
                raise FrozenCandidateError("IMAGE_SHA256_MISMATCH", str(image_path))
            with Image.open(image_path) as opened:
                rgb = np.asarray(opened.convert("RGB"), dtype=np.uint8)
            frame = DetectionFrame(
                rgb8=rgb,
                source_stamp_ns=int(sample["seed"]),
                source_frame_id="synthetic_test_camera",
            )
            raw_result = raw_adapter.collect(frame, CollectionMode.LOW_FLOOR)
            expected_limits = {
                "box_threshold": 0.01,
                "text_threshold": 0.01,
                "sam_quality_floor": 0.0,
                "min_mask_pixels": 64,
                "max_mask_area_ratio": 0.5,
            }
            if (
                raw_result.model_id != _PIPELINE
                or raw_result.runtime_device != "cuda"
                or raw_result.dtype != "float32"
                or raw_result.collection_mode != CollectionMode.LOW_FLOOR
                or raw_result.fallback_used is not False
                or raw_result.irreversible_limits != expected_limits
                or len(raw_result.raw_candidates)
                > lock.document["thresholds"]["raw_collection"]["maximum_candidates"]
                or any(candidate.label != "cup" for candidate in raw_result.raw_candidates)
            ):
                counters["fallback_count"] += 1
                raise FrozenCandidateError("RUNTIME_CONTRACT_INVALID", "raw result")
            raw_masks = {
                candidate.mask.relative_path: load_raw_mask(candidate.mask)
                for candidate in raw_result.raw_candidates
            }
            counters["raw_candidates"] += len(raw_result.raw_candidates)
            observation = production_observer(frame)
            decisions[str(observation.decision.value)] += 1
            if observation.decision is DecisionOutput.ERROR:
                counters["inference_errors"] += 1
                sample_errors.append(str(observation.error_type or "PRODUCTION_ERROR"))
            batch = observation.batch
            production_candidates = () if batch is None else tuple(batch.candidates)
            if batch is not None and (
                batch.model_id != _PIPELINE
                or batch.runtime_device != "cuda"
                or batch.weights_sha256 != lock.document["model_bundle"]["manifest_sha256"]
                or (batch.image_width, batch.image_height)
                != (frame.image_width, frame.image_height)
                or len(production_candidates) > production_values["maximum_candidates"]
                or any(
                    candidate.source_stamp_ns != frame.source_stamp_ns
                    or candidate.source_frame_id != frame.source_frame_id
                    or candidate.class_id != "cup"
                    or (candidate.image_width, candidate.image_height)
                    != (frame.image_width, frame.image_height)
                    for candidate in production_candidates
                )
            ):
                counters["fallback_count"] += 1
                raise FrozenCandidateError("RUNTIME_CONTRACT_INVALID", "production batch")
            try:
                mapped = map_production_candidates(
                    raw_candidates=raw_result.raw_candidates,
                    production_candidates=production_candidates,
                    raw_mask_loader=lambda ref: raw_masks[ref.relative_path],
                    minimum_mask_iou=mapping_iou,
                )
            except FrozenCandidateError as error:
                counters["mapping_errors"] += 1
                sample_errors.append(error.code)
                mapped = {}
            calibrated = calibrated_thresholds.filter_candidates(tuple(raw_result.raw_candidates))
            if set(mapped.values()) != {candidate.candidate_id for candidate in calibrated}:
                counters["calibrated_production_parity_errors"] += 1
                sample_errors.append("CALIBRATED_PRODUCTION_PARITY_INVALID")
            expected_decision = (
                DecisionOutput.NOT_FOUND
                if len(calibrated) == 0
                else DecisionOutput.UNIQUE
                if len(calibrated) == 1
                else DecisionOutput.AMBIGUOUS
            )
            if observation.decision is not DecisionOutput.ERROR and (
                observation.decision is not expected_decision
            ):
                counters["calibrated_production_parity_errors"] += 1
                sample_errors.append("CALIBRATED_DECISION_PARITY_INVALID")
            if sample["scenario"] == "no_cup" and observation.decision is DecisionOutput.UNIQUE:
                counters["no_cup_unique_count"] += 1
            for candidate in production_candidates:
                relative = (
                    Path("production-masks")
                    / f"{index:06d}"
                    / f"{candidate.instance_id}.coco-rle.json"
                )
                if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", candidate.instance_id):
                    raise FrozenCandidateError("PRODUCTION_MASK_INVALID", candidate.instance_id)
                target = root / relative
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                mask_sha = hashlib.sha256(
                    np.asarray(candidate.mask, dtype=np.uint8).tobytes(order="C")
                ).hexdigest()
                try:
                    artifact_sha = _write_exclusive_json(target, encode_mask_rle(candidate.mask))
                    persisted = read_mask(
                        MaskRef(
                            relative_path=relative.as_posix(),
                            sha256=mask_sha,
                            pixel_count=int(candidate.mask.sum()),
                            image_width=frame.image_width,
                            image_height=frame.image_height,
                        ),
                        root,
                    )
                    if not np.array_equal(persisted, candidate.mask):
                        raise FrozenCandidateError("PRODUCTION_MASK_INVALID", candidate.instance_id)
                except Exception:
                    counters["missing_production_masks"] += 1
                    raise
                production_documents.append(
                    {
                        "instance_id": candidate.instance_id,
                        "raw_candidate_id": mapped.get(candidate.instance_id),
                        "class_id": candidate.class_id,
                        "confidence": candidate.confidence,
                        "segmentation_quality": candidate.segmentation_quality,
                        "bbox_xyxy": list(candidate.bbox_xyxy),
                        "mask_relative_path": relative.as_posix(),
                        "mask_artifact_sha256": artifact_sha,
                        "mask_sha256": mask_sha,
                        "mask_pixel_count": int(candidate.mask.sum()),
                    }
                )
            counters["production_candidates"] += len(production_candidates)
            matched_pairs = _greedy_box_matches(production_candidates, truths)
        except Exception as error:
            if not sample_errors:
                counters["inference_errors"] += 1
                sample_errors.append(
                    error.code if isinstance(error, FrozenCandidateError) else type(error).__name__
                )
            production_candidates = ()
            matched_pairs = []

        tp = len(matched_pairs)
        fp = len(production_candidates) - tp
        fn = len(truths) - tp
        counters.update({"tp": tp, "fp": fp, "fn": fn})
        if tp:
            image_hits += 1
        scenario_counter = scenario_totals[str(sample["scenario"])]
        scenario_counter.update({"tp": tp, "fp": fp, "fn": fn, "images": 1})
        active_strata = []
        if sample["scenario"] == "small_far_cup":
            active_strata.append("small_far")
        if sample["scenario"] == "partially_occluded_cup":
            active_strata.append("partial_occlusion")
        if sample["configured_cup_count"] == 1:
            active_strata.append("single_cup")
        elif sample["configured_cup_count"] > 1:
            active_strata.append("multi_cup")
        for name in active_strata:
            strata_totals[name].update({"tp": tp, "fp": fp, "fn": fn, "images": 1})
        matched_truths = {truth_index for _, truth_index in matched_pairs}
        for truth_index, truth in enumerate(truths):
            bucket = _area_bucket(truth["absolute_xyxy"])
            area_totals[bucket]["truth"] += 1
            if truth_index in matched_truths:
                area_totals[bucket]["matched"] += 1
            occlusion = truth["occlusion"]
            if occlusion is not None and occlusion["state"] == "partial":
                occlusion_totals["truth"] += 1
                occlusion_visible_fractions.append(float(occlusion["visible_fraction"]))
                if truth_index in matched_truths:
                    occlusion_totals["matched"] += 1
        for production_index, truth_index in matched_pairs:
            value = mask_iou(
                np.asarray(production_candidates[production_index].mask, dtype=bool),
                np.asarray(truths[truth_index]["mask"], dtype=bool),
            )
            mask_ious.append(value)
        record = {
            "schema_version": "so101-grounded-sam-synthetic-test-record/v1",
            "formal_sample_index": index,
            "seed": sample["seed"],
            "scenario": sample["scenario"],
            "image_sha256": sample["image_sha256"],
            "truth_count": len(truths),
            "production_decision": (
                observation.decision.value if observation is not None else "ERROR"
            ),
            "production_candidates": production_documents,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "errors": sample_errors,
        }
        record_path = root / "records" / f"{index:06d}.json"
        record_hashes.append(_write_exclusive_json(record_path, record))
        if (index + 1) % 10 == 0 or index + 1 == len(dataset.samples):
            print(
                f"EVAL_PROGRESS completed={index + 1} total={len(dataset.samples)} "
                f"errors={counters['inference_errors']} mapping={counters['mapping_errors']}",
                flush=True,
            )
    safety_gates = {
        "sample_count": len(dataset.samples),
        "missing_samples": len(dataset.samples) - len(record_hashes),
        "runtime_device": "cuda",
        "dtype": "float32",
        "fallback_count": counters["fallback_count"],
        "inference_errors": counters["inference_errors"],
        "mapping_errors": counters["mapping_errors"],
        "calibrated_production_parity_errors": counters["calibrated_production_parity_errors"],
        "missing_production_masks": counters["missing_production_masks"],
        "no_cup_unique_count": counters["no_cup_unique_count"],
    }
    safety_passed = (
        safety_gates["missing_samples"] == 0
        and safety_gates["fallback_count"] == 0
        and safety_gates["inference_errors"] == 0
        and safety_gates["mapping_errors"] == 0
        and safety_gates["calibrated_production_parity_errors"] == 0
        and safety_gates["missing_production_masks"] == 0
        and safety_gates["no_cup_unique_count"] == 0
    )
    precision = _ratio(counters["tp"], counters["tp"] + counters["fp"])
    recall = _ratio(counters["tp"], counters["tp"] + counters["fn"])
    f1 = _ratio(2 * precision * recall, precision + recall)
    report: dict[str, Any] = {
        "schema_version": "so101-grounded-sam-synthetic-test-report/v1",
        "run_id": run_id,
        "source_commit": source_commit,
        "candidate_lock_file_sha256": lock.file_sha256,
        "candidate_lock_sha256": lock.lock_sha256,
        "safety_passed": safety_passed,
        "safety_gates": safety_gates,
        "totals": {"fn": counters["fn"], "fp": counters["fp"], "tp": counters["tp"]},
        "candidate_counts": {
            "production": counters["production_candidates"],
            "raw": counters["raw_candidates"],
        },
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "image_hits": image_hits,
        "decision_counts": dict(sorted(decisions.items())),
        "mean_matched_mask_iou": (None if not mask_ious else sum(mask_ious) / len(mask_ious)),
        "scenario_metrics": {
            name: dict(sorted(values.items())) for name, values in sorted(scenario_totals.items())
        },
        "strata_metrics": {
            name: dict(sorted(values.items())) for name, values in sorted(strata_totals.items())
        },
        "occlusion_recall": {
            "matched": occlusion_totals["matched"],
            "truth": occlusion_totals["truth"],
            "recall": _ratio(occlusion_totals["matched"], occlusion_totals["truth"]),
        },
        "mean_partial_visible_fraction": (
            None
            if not occlusion_visible_fractions
            else sum(occlusion_visible_fractions) / len(occlusion_visible_fractions)
        ),
        "area_recall": {
            name: {
                "matched": values["matched"],
                "truth": values["truth"],
                "recall": _ratio(values["matched"], values["truth"]),
            }
            for name, values in area_totals.items()
        },
        "record_inventory_sha256": hashlib.sha256(
            _canonical({"record_sha256s": record_hashes})
        ).hexdigest(),
    }
    report_sha = _write_exclusive_json(root / "report.json", report)
    manifest["status"] = "VALID" if safety_passed else "FAILED_SAFETY"
    manifest["record_count"] = len(record_hashes)
    manifest["ended_at"] = datetime.now(timezone.utc).isoformat()
    manifest["report_sha256"] = report_sha
    manifest["safety_passed"] = safety_passed
    _replace_json(manifest_path, manifest)
    _fsync_directory(root)
    return MappingProxyType(report)


def _canonical(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_exclusive_json(path: Path, document: Mapping[str, Any]) -> str:
    payload = _canonical(document)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise FrozenCandidateError("OUTPUT_COLLISION", str(target)) from error
    _fsync_directory(target.parent)
    return hashlib.sha256(payload).hexdigest()


def _replace_json(path: Path, document: Mapping[str, Any]) -> None:
    target = Path(path)
    temporary = target.with_name(f".{target.name}.next")
    if os.path.lexists(temporary):
        raise FrozenCandidateError("OUTPUT_COLLISION", str(temporary))
    payload = _canonical(document)
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    _fsync_directory(target.parent)


def _read_canonical_mapping(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = Path(path).read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FrozenCandidateError(code, str(path)) from error
    if not isinstance(document, dict) or payload != _canonical(document):
        raise FrozenCandidateError(code, str(path))
    return document


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _greedy_box_matches(
    candidates: Sequence[Any], truths: Sequence[Mapping[str, Any]]
) -> list[tuple[int, int]]:
    unmatched = set(range(len(truths)))
    matches: list[tuple[int, int]] = []
    order = sorted(
        range(len(candidates)),
        key=lambda index: (-float(candidates[index].confidence), index),
    )
    for candidate_index in order:
        eligible = [
            (
                box_iou(
                    tuple(candidates[candidate_index].bbox_xyxy),
                    tuple(truths[truth_index]["absolute_xyxy"]),
                ),
                truth_index,
            )
            for truth_index in unmatched
        ]
        if not eligible:
            continue
        overlap, truth_index = max(eligible, key=lambda item: (item[0], -item[1]))
        if overlap >= 0.5:
            unmatched.remove(truth_index)
            matches.append((candidate_index, truth_index))
    return matches


def _area_bucket(box: Sequence[float]) -> str:
    area = (float(box[2]) - float(box[0])) * (float(box[3]) - float(box[1]))
    return "small" if area < 32**2 else "medium" if area < 96**2 else "large"


def _ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0.0 else float(numerator / denominator)


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FrozenCandidateError(code, str(value))
    return value


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise FrozenCandidateError(code, "not a mapping")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise FrozenCandidateError("EXTERNAL_FILE_UNREADABLE", str(path)) from error
    return digest.hexdigest()


def _test_relative_path(value: object, kind: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise FrozenCandidateError("SEALED_INVENTORY_INVALID", f"{kind} path")
    relative = PurePosixPath(value)
    expected_prefix = {"image": "images", "label": "labels", "truth": "truth"}[kind]
    if (
        relative.is_absolute()
        or "\\" in value
        or len(relative.parts) != 3
        or relative.parts[:2] != (expected_prefix, "test")
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise FrozenCandidateError("SEALED_MEMBER_INVALID", value)
    return relative


def _inclusive_range(value: object) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise FrozenCandidateError("LOCK_TEST_SEAL_INVALID", "seed range")
    return int(value[0]), int(value[1]) + 1
