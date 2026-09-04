"""Fresh-reload validation for immutable Grounding DINO checkpoints."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from so101_demo.perception_benchmark.codec import atomic_write_json
from so101_demo.training.grounding_dino_finetune import (
    BoxTruth,
    ValidationResult,
    load_contract,
    load_verified_split,
    match_predictions,
    require_cuda,
    select_best_threshold,
    verify_complete_checkpoint,
)
from so101_demo.training.grounding_dino_runtime import (
    _checkpoint_identity,
    _validate_contract,
)

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CheckpointRevalidationError(RuntimeError):
    """Stable fail-closed error for saved-checkpoint revalidation."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(slots=True)
class _MetricCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    small_tp: int = 0
    small_total: int = 0
    multi_tp: int = 0
    multi_total: int = 0


def _selected_rank(report: Mapping[str, Any]) -> tuple[float, ...]:
    try:
        selected = report["selected"]
        epoch = report["epoch"]
        if not isinstance(selected, Mapping) or type(epoch) is not int or epoch <= 0:
            raise TypeError
        if selected.get("epoch") != epoch:
            raise TypeError
        return (
            float(selected["f1"]),
            float(selected["recall"]),
            float(selected["small_target_recall"]),
            float(selected["multi_cup_recall"]),
            -float(selected["fp"]),
            float(selected["box_threshold"]),
            float(selected["text_threshold"]),
            -float(epoch),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CheckpointRevalidationError("REPORT_INVALID") from error


def select_deployable_checkpoint(
    reports: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Select an epoch by the preregistered deployment ranking."""

    candidates = tuple(reports)
    if not candidates:
        raise CheckpointRevalidationError("REPORTS_EMPTY")
    epochs = [report.get("epoch") for report in candidates]
    if len(set(epochs)) != len(epochs):
        raise CheckpointRevalidationError("DUPLICATE_EPOCH")
    return max(candidates, key=_selected_rank)


def _valid_selected(selected: Mapping[str, Any]) -> int:
    required = {
        "epoch",
        "box_threshold",
        "text_threshold",
        "tp",
        "fp",
        "fn",
        "precision",
        "recall",
        "f1",
        "small_target_recall",
        "multi_cup_recall",
    }
    if set(selected) != required or type(selected.get("epoch")) is not int:
        raise CheckpointRevalidationError("SELECTED_RESULT_INVALID")
    epoch = int(selected["epoch"])
    if epoch <= 0:
        raise CheckpointRevalidationError("SELECTED_RESULT_INVALID")
    for field in ("tp", "fp", "fn"):
        if type(selected[field]) is not int or selected[field] < 0:
            raise CheckpointRevalidationError("SELECTED_RESULT_INVALID", field)
    for field in required - {"epoch", "tp", "fp", "fn"}:
        if isinstance(selected[field], bool) or not isinstance(selected[field], (int, float)):
            raise CheckpointRevalidationError("SELECTED_RESULT_INVALID", field)
    return epoch


def write_checkpoint_revalidation(
    *,
    output_root: Path,
    source_commit: str,
    checkpoint_root: Path,
    checkpoint_manifest_sha256: str,
    val_inventory_sha256: str,
    selected: Mapping[str, Any],
    grid_results: Sequence[Mapping[str, Any]],
    runtime: Mapping[str, Any],
    score_range: Mapping[str, Any],
    denominator: Mapping[str, Any] | None = None,
    elapsed_ms: int | None = None,
    environment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one complete, exclusive, hash-bound revalidation result."""

    root = Path(output_root)
    if root.exists():
        raise CheckpointRevalidationError("OUTPUT_ROOT_ALREADY_EXISTS", str(root))
    if not root.is_absolute() or not root.parent.is_dir():
        raise CheckpointRevalidationError("OUTPUT_ROOT_INVALID", str(root))
    if _COMMIT.fullmatch(source_commit) is None:
        raise CheckpointRevalidationError("SOURCE_COMMIT_INVALID")
    if any(
        _SHA256.fullmatch(value) is None
        for value in (checkpoint_manifest_sha256, val_inventory_sha256)
    ):
        raise CheckpointRevalidationError("PROVENANCE_SHA256_INVALID")
    epoch = _valid_selected(selected)
    grid = [dict(point) for point in grid_results]
    if len(grid) != 100 or any(point.get("epoch") != epoch for point in grid):
        raise CheckpointRevalidationError("GRID_RESULT_INVALID")
    if dict(runtime) != {
        "device": "cuda:0",
        "dtype": "float32",
        "cpu_fallback": False,
    }:
        raise CheckpointRevalidationError("RUNTIME_INVALID")
    if (
        type(score_range.get("count")) is not int
        or score_range["count"] < 0
        or set(score_range) - {"floor", "minimum", "maximum", "count"}
    ):
        raise CheckpointRevalidationError("SCORE_RANGE_INVALID")
    report = {
        "schema_version": 1,
        "status": "VALID",
        "epoch": epoch,
        "source_commit": source_commit,
        "checkpoint_root": str(Path(checkpoint_root).resolve()),
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "val_inventory_sha256": val_inventory_sha256,
        "prompt": "cup.",
        "class_name": "cup",
        "sam_loaded": False,
        "synthetic_test_access": "none",
        "coco100_access": "none",
        "runtime": dict(runtime),
        "environment": dict(environment or {}),
        "elapsed_ms": elapsed_ms,
        "denominator": dict(denominator or {}),
        "score_range": dict(score_range),
        "selected": dict(selected),
        "grid_results": grid,
    }
    root.mkdir(mode=0o700, exist_ok=False)
    report_sha256 = atomic_write_json(root / "report.json", report)
    manifest = {
        "schema_version": 1,
        "status": "VALID",
        "epoch": epoch,
        "report_sha256": report_sha256,
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
        "val_inventory_sha256": val_inventory_sha256,
        "source_commit": source_commit,
    }
    atomic_write_json(root / "manifest.json", manifest)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return report


def _normalized_label(value: object) -> str:
    return str(value).strip().lower().rstrip(".")


def _small_indices(truths: tuple[BoxTruth, ...], small_area: float) -> set[int]:
    return {
        index
        for index, truth in enumerate(truths)
        if (truth.absolute_xyxy[2] - truth.absolute_xyxy[0])
        * (truth.absolute_xyxy[3] - truth.absolute_xyxy[1])
        < small_area
    }


def _evaluate_grid(
    *,
    model: Any,
    processor: Any,
    samples: Sequence[Any],
    prompt: str,
    epoch: int,
    device: str,
    box_thresholds: list[float],
    text_thresholds: list[float],
    iou_threshold: float,
    small_area: float,
    multi_scenario: str,
) -> tuple[list[ValidationResult], dict[str, Any], int]:
    import torch
    from PIL import Image

    counts = {(box, text): _MetricCounts() for box in box_thresholds for text in text_thresholds}
    scores_at_floor: list[float] = []
    processed_samples = 0
    model.eval()
    with torch.inference_mode():
        for sample in samples:
            with Image.open(sample.image_path) as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                encoded = processor(images=rgb, text=prompt, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in encoded.items()}
            outputs = model(**inputs)
            for text_index, text_threshold in enumerate(text_thresholds):
                processed = processor.post_process_grounded_object_detection(
                    outputs,
                    input_ids=inputs["input_ids"],
                    threshold=min(box_thresholds),
                    text_threshold=text_threshold,
                    target_sizes=[(height, width)],
                )[0]
                raw_boxes = processed["boxes"].detach().cpu().tolist()
                raw_scores = processed["scores"].detach().cpu().tolist()
                raw_labels = processed["text_labels"]
                cup_predictions = [
                    (tuple(float(value) for value in box), float(score))
                    for box, score, label in zip(raw_boxes, raw_scores, raw_labels, strict=True)
                    if _normalized_label(label) == "cup"
                ]
                if text_index == 0:
                    scores_at_floor.extend(score for _, score in cup_predictions)
                for box_threshold in box_thresholds:
                    filtered = [item for item in cup_predictions if item[1] >= box_threshold]
                    tp, fp, fn, matched = match_predictions(
                        predicted_boxes=[item[0] for item in filtered],
                        predicted_scores=[item[1] for item in filtered],
                        truth_boxes=sample.boxes,
                        iou_threshold=iou_threshold,
                    )
                    current = counts[(box_threshold, text_threshold)]
                    current.tp += tp
                    current.fp += fp
                    current.fn += fn
                    small = _small_indices(sample.boxes, small_area)
                    current.small_total += len(small)
                    current.small_tp += len(matched.intersection(small))
                    if sample.scenario == multi_scenario:
                        current.multi_total += len(sample.boxes)
                        current.multi_tp += len(matched)
            processed_samples += 1
    results: list[ValidationResult] = []
    for (box_threshold, text_threshold), current in counts.items():
        precision = current.tp / (current.tp + current.fp) if current.tp + current.fp else 0.0
        recall = current.tp / (current.tp + current.fn) if current.tp + current.fn else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
        results.append(
            ValidationResult(
                epoch=epoch,
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                tp=current.tp,
                fp=current.fp,
                fn=current.fn,
                precision=precision,
                recall=recall,
                f1=f1,
                small_target_recall=(
                    current.small_tp / current.small_total if current.small_total else 0.0
                ),
                multi_cup_recall=(
                    current.multi_tp / current.multi_total if current.multi_total else 0.0
                ),
            )
        )
    score_range = {
        "floor": min(box_thresholds),
        "minimum": min(scores_at_floor) if scores_at_floor else None,
        "maximum": max(scores_at_floor) if scores_at_floor else None,
        "count": len(scores_at_floor),
    }
    return results, score_range, processed_samples


def evaluate_saved_checkpoint(
    *,
    contract_path: Path,
    checkpoint_root: Path,
    val_inventory: Path,
    val_images: Path,
    output_root: Path,
    source_commit: str,
) -> dict[str, Any]:
    """Verify, fresh-load, and evaluate one saved checkpoint on frozen val."""

    started = time.monotonic()
    if Path(output_root).exists():
        raise CheckpointRevalidationError("OUTPUT_ROOT_ALREADY_EXISTS", str(output_root))
    contract, contract_sha256 = load_contract(contract_path)
    _validate_contract(contract)
    try:
        checkpoint_manifest = json.loads(
            (Path(checkpoint_root) / "checkpoint-manifest.json").read_text(encoding="utf-8")
        )
        training_commit = checkpoint_manifest["identity"]["training_commit"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise CheckpointRevalidationError("CHECKPOINT_MANIFEST_INVALID") from error
    if not isinstance(training_commit, str) or _COMMIT.fullmatch(training_commit) is None:
        raise CheckpointRevalidationError("CHECKPOINT_IDENTITY_INVALID")
    identity = _checkpoint_identity(
        contract_sha256=contract_sha256,
        document=contract,
        training_commit=training_commit,
    )
    verified = verify_complete_checkpoint(checkpoint_root, expected_identity=identity)
    data = contract["data"]
    split = load_verified_split(
        inventory_path=val_inventory,
        image_root=val_images,
        expected_inventory_sha256=data["val_inventory_sha256"],
        expected_split="val",
        expected_sample_count=data["val_sample_count"],
        expected_source_archive_sha256=data["source_archive_sha256"],
        expected_source_manifest_sha256=data["source_manifest_sha256"],
        expected_generator_commit=data["generator_commit"],
        expected_converter_commit=data["converter_commit"],
    )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    import transformers
    from transformers import AutoProcessor, GroundingDinoForObjectDetection

    device = require_cuda(torch)
    processor = AutoProcessor.from_pretrained(verified.root, local_files_only=True)
    model = GroundingDinoForObjectDetection.from_pretrained(
        verified.root, local_files_only=True, use_safetensors=True
    ).to(device)
    model.float()
    floating_dtypes = {
        str(parameter.dtype) for parameter in model.parameters() if parameter.is_floating_point()
    }
    if floating_dtypes != {"torch.float32"}:
        raise CheckpointRevalidationError(
            "MODEL_DTYPE_INVALID", ",".join(sorted(floating_dtypes))
        )
    validation = contract["validation"]
    box_thresholds = [float(value) for value in validation["box_threshold_grid"]]
    text_thresholds = [float(value) for value in validation["text_threshold_grid"]]
    results, score_range, processed_samples = _evaluate_grid(
        model=model,
        processor=processor,
        samples=split.samples,
        prompt=data["prompt"],
        epoch=verified.completed_epoch,
        device=device,
        box_thresholds=box_thresholds,
        text_thresholds=text_thresholds,
        iou_threshold=float(validation["box_iou_threshold"]),
        small_area=float(validation["small_area_max_exclusive_px2"]),
        multi_scenario=validation["multi_cup_scenario"],
    )
    if processed_samples != len(split.samples) or len(results) != 100:
        raise CheckpointRevalidationError("INCOMPLETE_DENOMINATOR")
    selected = select_best_threshold(results)
    denominator = {
        "sample_count": len(split.samples),
        "processed_sample_count": processed_samples,
        "truth_count": sum(len(sample.boxes) for sample in split.samples),
        "scenario_counts": dict(sorted(Counter(sample.scenario for sample in split.samples).items())),
    }
    environment = {
        "python": sys.version,
        "python_executable": sys.executable,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_uuid": str(torch.cuda.get_device_properties(0).uuid),
    }
    elapsed_ms = int((time.monotonic() - started) * 1000)
    report = write_checkpoint_revalidation(
        output_root=output_root,
        source_commit=source_commit,
        checkpoint_root=verified.root,
        checkpoint_manifest_sha256=verified.manifest_sha256,
        val_inventory_sha256=split.inventory_sha256,
        selected=selected.as_dict(),
        grid_results=[result.as_dict() for result in results],
        runtime={"device": device, "dtype": "float32", "cpu_fallback": False},
        score_range=score_range,
        denominator=denominator,
        elapsed_ms=elapsed_ms,
        environment=environment,
    )
    return report
