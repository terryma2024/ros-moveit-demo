"""Fail-closed contracts for reproducible Grounding DINO fine-tuning."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

import yaml

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SCENARIOS = frozenset(
    {
        "no_cup",
        "one_cup_distractors",
        "two_cups",
        "cup_near_bottle",
        "small_far_cup",
        "partially_occluded_cup",
    }
)
_DOMAIN_ROLES = frozenset(
    {"near_synthetic", "real_train", "real_val", "generic", "hard_negative"}
)


class TrainingDataError(RuntimeError):
    """Raised when a frozen train or validation input fails verification."""


class CheckpointError(RuntimeError):
    """Raised when a checkpoint is incomplete or has changed."""


def _data_error(code: str, detail: str) -> TrainingDataError:
    return TrainingDataError(f"{code}: {detail}")


def _checkpoint_error(code: str, detail: str) -> CheckpointError:
    return CheckpointError(f"{code}: {detail}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def exclusive_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(document))
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True, slots=True)
class BoxTruth:
    absolute_xyxy: tuple[float, float, float, float]
    normalized_xyxy: tuple[float, float, float, float]
    class_name: str
    text: str
    visible_pixel_count: int
    occlusion: Mapping[str, Any] | None


@dataclass(frozen=True, slots=True)
class TrainingSample:
    seed: int
    scenario: str
    configured_cup_count: int
    image_path: Path
    image_sha256: str
    boxes: tuple[BoxTruth, ...]
    domain_role: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedSplit:
    name: str
    inventory_path: Path
    inventory_sha256: str
    image_root: Path
    image_width: int
    image_height: int
    samples: tuple[TrainingSample, ...]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    epoch: int
    box_threshold: float
    text_threshold: float
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    small_target_recall: float
    multi_cup_recall: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VerifiedCheckpoint:
    root: Path
    completed_epoch: int
    manifest: Mapping[str, Any]
    manifest_sha256: str


def _regular_file(path: Path, *, code: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise _data_error(code, f"not a regular file: {candidate}")
    return candidate.resolve()


def _four_floats(value: object, *, field: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise _data_error("BOX_INVALID", f"{field} must contain four values")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as error:
        raise _data_error("BOX_INVALID", f"{field} contains a non-number") from error
    if any(not math.isfinite(item) for item in result):
        raise _data_error("BOX_INVALID", f"{field} contains a non-finite value")
    return result  # type: ignore[return-value]


def _box_truth(document: object, *, width: int, height: int) -> BoxTruth:
    if not isinstance(document, dict):
        raise _data_error("BOX_INVALID", "box entry must be a mapping")
    absolute = _four_floats(document.get("absolute_xyxy"), field="absolute_xyxy")
    normalized = _four_floats(document.get("normalized_xyxy"), field="normalized_xyxy")
    if not (0.0 <= absolute[0] < absolute[2] <= width):
        raise _data_error("BOX_INVALID", "absolute x coordinates are invalid")
    if not (0.0 <= absolute[1] < absolute[3] <= height):
        raise _data_error("BOX_INVALID", "absolute y coordinates are invalid")
    if not all(0.0 <= value <= 1.0 for value in normalized):
        raise _data_error("BOX_INVALID", "normalized coordinates are outside [0, 1]")
    expected = (
        absolute[0] / width,
        absolute[1] / height,
        absolute[2] / width,
        absolute[3] / height,
    )
    if any(abs(left - right) > 1e-6 for left, right in zip(normalized, expected, strict=True)):
        raise _data_error("BOX_INVALID", "absolute and normalized coordinates disagree")
    if document.get("class_name") != "cup" or document.get("text") != "cup.":
        raise _data_error("CLASS_OR_PROMPT_INVALID", "box must be generic cup with prompt cup.")
    pixels = document.get("visible_pixel_count")
    if type(pixels) is not int or pixels <= 0:
        raise _data_error("BOX_INVALID", "visible_pixel_count must be positive")
    occlusion = document.get("occlusion")
    if occlusion is not None and not isinstance(occlusion, dict):
        raise _data_error("BOX_INVALID", "occlusion must be null or a mapping")
    return BoxTruth(
        absolute_xyxy=absolute,
        normalized_xyxy=normalized,
        class_name="cup",
        text="cup.",
        visible_pixel_count=pixels,
        occlusion=None if occlusion is None else MappingProxyType(dict(occlusion)),
    )


def load_verified_split(
    *,
    inventory_path: Path,
    image_root: Path,
    expected_inventory_sha256: str,
    expected_split: str,
    expected_sample_count: int,
    expected_source_archive_sha256: str,
    expected_source_manifest_sha256: str,
    expected_generator_commit: str,
    expected_converter_commit: str,
) -> VerifiedSplit:
    """Load one train/val inventory without exposing any sealed-test path."""

    if expected_split not in {"train", "val"}:
        raise _data_error("SPLIT_INVALID", "only train and val may be loaded")
    inventory = _regular_file(inventory_path, code="INVENTORY_INVALID")
    if not _SHA256.fullmatch(expected_inventory_sha256):
        raise _data_error("INVENTORY_SHA256_INVALID", expected_inventory_sha256)
    actual_inventory_sha = sha256_file(inventory)
    if actual_inventory_sha != expected_inventory_sha256:
        raise _data_error("INVENTORY_SHA256_MISMATCH", str(inventory))
    root = Path(image_root)
    if root.is_symlink() or not root.is_dir():
        raise _data_error("IMAGE_ROOT_INVALID", str(root))
    root = root.resolve()
    try:
        document = json.loads(inventory.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _data_error("INVENTORY_INVALID", str(inventory)) from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise _data_error("INVENTORY_INVALID", "unsupported schema")
    expected_identities = {
        "split": expected_split,
        "class_name": "cup",
        "prompt": "cup.",
        "source_archive_sha256": expected_source_archive_sha256,
        "source_manifest_sha256": expected_source_manifest_sha256,
        "source_generator_commit": expected_generator_commit,
        "converter_commit": expected_converter_commit,
    }
    if any(document.get(key) != value for key, value in expected_identities.items()):
        raise _data_error("INVENTORY_IDENTITY_MISMATCH", expected_split)
    if not _COMMIT.fullmatch(expected_generator_commit) or not _COMMIT.fullmatch(
        expected_converter_commit
    ):
        raise _data_error("INVENTORY_IDENTITY_INVALID", "commit")
    width = document.get("image_width")
    height = document.get("image_height")
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise _data_error("INVENTORY_INVALID", "image dimensions")
    raw_samples = document.get("samples")
    if (
        type(document.get("sample_count")) is not int
        or document["sample_count"] != expected_sample_count
        or not isinstance(raw_samples, list)
        or len(raw_samples) != expected_sample_count
    ):
        raise _data_error("SAMPLE_COUNT_MISMATCH", expected_split)
    samples: list[TrainingSample] = []
    seen_seeds: set[int] = set()
    for raw in raw_samples:
        if not isinstance(raw, dict):
            raise _data_error("SAMPLE_INVALID", expected_split)
        seed = raw.get("seed")
        scenario = raw.get("scenario")
        if type(seed) is not int or seed in seen_seeds:
            raise _data_error("SAMPLE_INVALID", "seed")
        if scenario not in _SCENARIOS:
            raise _data_error("SAMPLE_INVALID", "scenario")
        seen_seeds.add(seed)
        relative = raw.get("image_relpath")
        if not isinstance(relative, str):
            raise _data_error("IMAGE_PATH_INVALID", "missing image_relpath")
        parts = PurePosixPath(relative).parts
        if len(parts) != 3 or parts[:2] != ("images", expected_split):
            raise _data_error("IMAGE_PATH_INVALID", relative)
        candidate = root / parts[2]
        if candidate.is_symlink() or not candidate.is_file():
            raise _data_error("IMAGE_PATH_INVALID", relative)
        resolved_image = candidate.resolve()
        if resolved_image.parent != root:
            raise _data_error("IMAGE_PATH_INVALID", relative)
        image_sha = raw.get("image_sha256")
        if not isinstance(image_sha, str) or not _SHA256.fullmatch(image_sha):
            raise _data_error("IMAGE_SHA256_INVALID", relative)
        if sha256_file(resolved_image) != image_sha:
            raise _data_error("IMAGE_SHA256_MISMATCH", relative)
        raw_boxes = raw.get("boxes")
        if not isinstance(raw_boxes, list):
            raise _data_error("BOX_INVALID", relative)
        boxes = tuple(_box_truth(item, width=width, height=height) for item in raw_boxes)
        configured = raw.get("configured_cup_count")
        visible = raw.get("visible_instance_count")
        if type(configured) is not int or configured < 0 or visible != len(boxes):
            raise _data_error("SAMPLE_INVALID", "instance counts")
        domain_role = raw.get("domain_role")
        if domain_role is not None and domain_role not in _DOMAIN_ROLES:
            raise _data_error("SAMPLE_INVALID", "domain_role")
        samples.append(
            TrainingSample(
                seed=seed,
                scenario=scenario,
                configured_cup_count=configured,
                image_path=resolved_image,
                image_sha256=image_sha,
                boxes=boxes,
                domain_role=domain_role,
            )
        )
    return VerifiedSplit(
        name=expected_split,
        inventory_path=inventory,
        inventory_sha256=actual_inventory_sha,
        image_root=root,
        image_width=width,
        image_height=height,
        samples=tuple(samples),
    )


def build_coco_annotation(sample: Any, *, image_id: int) -> dict[str, Any]:
    annotations: list[dict[str, Any]] = []
    for box in sample.boxes:
        left, top, right, bottom = box.absolute_xyxy
        width = right - left
        height = bottom - top
        annotations.append(
            {
                "bbox": [left, top, width, height],
                "area": width * height,
                "category_id": 0,
                "iscrowd": 0,
            }
        )
    return {"image_id": image_id, "annotations": annotations}


def select_smoke_subset(split: VerifiedSplit) -> VerifiedSplit:
    selected: list[TrainingSample] = []
    for scenario in (
        "no_cup",
        "one_cup_distractors",
        "two_cups",
        "cup_near_bottle",
        "small_far_cup",
        "partially_occluded_cup",
    ):
        try:
            selected.append(next(sample for sample in split.samples if sample.scenario == scenario))
        except StopIteration as error:
            raise _data_error("SMOKE_SUBSET_INCOMPLETE", scenario) from error
    return VerifiedSplit(
        name=split.name,
        inventory_path=split.inventory_path,
        inventory_sha256=split.inventory_sha256,
        image_root=split.image_root,
        image_width=split.image_width,
        image_height=split.image_height,
        samples=tuple(selected),
    )


def _threshold_rank(result: ValidationResult) -> tuple[float, ...]:
    return (
        result.f1,
        result.recall,
        result.small_target_recall,
        result.multi_cup_recall,
        -float(result.fp),
        result.box_threshold,
        result.text_threshold,
    )


def _checkpoint_rank(result: ValidationResult) -> tuple[float, ...]:
    return (
        result.f1,
        result.recall,
        result.small_target_recall,
        result.multi_cup_recall,
        -float(result.fp),
        -float(result.epoch),
    )


def select_best_threshold(results: list[ValidationResult]) -> ValidationResult:
    if not results:
        raise ValueError("threshold results must not be empty")
    return max(results, key=_threshold_rank)


def select_best_checkpoint(results: list[ValidationResult]) -> ValidationResult:
    if not results:
        raise ValueError("checkpoint results must not be empty")
    return max(results, key=_checkpoint_rank)


def box_iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0.0 else intersection / union


def match_predictions(
    *,
    predicted_boxes: list[tuple[float, float, float, float]],
    predicted_scores: list[float],
    truth_boxes: tuple[BoxTruth, ...],
    iou_threshold: float,
) -> tuple[int, int, int, set[int]]:
    order = sorted(range(len(predicted_boxes)), key=lambda index: (-predicted_scores[index], index))
    unmatched = set(range(len(truth_boxes)))
    matched: set[int] = set()
    false_positives = 0
    for prediction_index in order:
        eligible = [
            (box_iou(predicted_boxes[prediction_index], truth_boxes[index].absolute_xyxy), index)
            for index in unmatched
        ]
        if not eligible:
            false_positives += 1
            continue
        best_iou, best_index = max(eligible, key=lambda item: (item[0], -item[1]))
        if best_iou < iou_threshold:
            false_positives += 1
            continue
        unmatched.remove(best_index)
        matched.add(best_index)
    return len(matched), false_positives, len(unmatched), matched


def require_cuda(torch_module: Any) -> str:
    if not torch_module.cuda.is_available() or torch_module.cuda.device_count() != 1:
        raise RuntimeError("CPU_FALLBACK_FORBIDDEN: exactly one CUDA device is required")
    return "cuda:0"


def checkpoint_file_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.name == "checkpoint-manifest.json":
            continue
        if path.is_symlink() or not path.is_file():
            if path.is_dir():
                continue
            raise _checkpoint_error("CHECKPOINT_MEMBER_INVALID", str(path))
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return entries


def verify_complete_checkpoint(
    root: Path, *, expected_identity: Mapping[str, str]
) -> VerifiedCheckpoint:
    checkpoint = Path(root)
    if checkpoint.is_symlink() or not checkpoint.is_dir():
        raise _checkpoint_error("CHECKPOINT_INVALID", str(checkpoint))
    checkpoint = checkpoint.resolve()
    manifest_path = checkpoint / "checkpoint-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise _checkpoint_error("CHECKPOINT_INCOMPLETE", str(checkpoint))
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _checkpoint_error("CHECKPOINT_MANIFEST_INVALID", str(checkpoint)) from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise _checkpoint_error("CHECKPOINT_MANIFEST_INVALID", "schema")
    if document.get("complete") is not True:
        raise _checkpoint_error("CHECKPOINT_INCOMPLETE", str(checkpoint))
    epoch = document.get("completed_epoch")
    if type(epoch) is not int or epoch <= 0:
        raise _checkpoint_error("CHECKPOINT_MANIFEST_INVALID", "completed_epoch")
    if document.get("identity") != dict(expected_identity):
        raise _checkpoint_error("CHECKPOINT_IDENTITY_MISMATCH", str(checkpoint))
    declared = document.get("files")
    if not isinstance(declared, list) or not declared:
        raise _checkpoint_error("CHECKPOINT_MANIFEST_INVALID", "files")
    actual = checkpoint_file_entries(checkpoint)
    if actual != declared:
        raise _checkpoint_error("CHECKPOINT_FILE_MISMATCH", str(checkpoint))
    return VerifiedCheckpoint(
        root=checkpoint,
        completed_epoch=epoch,
        manifest=MappingProxyType(document),
        manifest_sha256=sha256_file(manifest_path),
    )


def load_contract(path: Path) -> tuple[dict[str, Any], str]:
    contract_path = _regular_file(path, code="CONTRACT_INVALID")
    try:
        payload = contract_path.read_text(encoding="utf-8")
        document = (
            json.loads(payload)
            if contract_path.suffix.lower() == ".json"
            else yaml.safe_load(payload)
        )
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise _data_error("CONTRACT_INVALID", str(contract_path)) from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise _data_error("CONTRACT_INVALID", "schema")
    for key in ("model", "data", "training", "smoke", "validation"):
        if not isinstance(document.get(key), dict):
            raise _data_error("CONTRACT_INVALID", key)
    if document["data"].get("class_name") != "cup" or document["data"].get("prompt") != "cup.":
        raise _data_error("CONTRACT_INVALID", "generic cup prompt")
    return document, sha256_file(contract_path)
