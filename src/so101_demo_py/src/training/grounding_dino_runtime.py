"""CUDA-only Grounding DINO training runtime for the frozen cup dataset."""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .grounding_dino_finetune import (
    TrainingSample,
    ValidationResult,
    build_coco_annotation,
    checkpoint_file_entries,
    exclusive_json,
    load_contract,
    load_verified_split,
    match_predictions,
    require_cuda,
    select_best_checkpoint,
    select_best_threshold,
    select_smoke_subset,
    sha256_file,
    verify_complete_checkpoint,
)


@dataclass(slots=True)
class _MetricCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    small_tp: int = 0
    small_total: int = 0
    multi_tp: int = 0
    multi_total: int = 0


def _validate_sha_mapping(root: Path, expected: dict[str, str]) -> None:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError(f"BASE_MODEL_INVALID: {root}")
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != set(expected):
        raise RuntimeError("BASE_MODEL_FILE_SET_MISMATCH")
    for relative, expected_sha in expected.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_sha:
            raise RuntimeError(f"BASE_MODEL_SHA256_MISMATCH: {relative}")


def _validate_contract(document: dict[str, Any]) -> None:
    model = document["model"]
    data = document["data"]
    training = document["training"]
    smoke = document["smoke"]
    validation = document["validation"]
    if model.get("model_id") != "IDEA-Research/grounding-dino-tiny":
        raise RuntimeError("CONTRACT_MODEL_INVALID")
    if model.get("revision") != "a2bb814dd30d776dcf7e30523b00659f4f141c71":
        raise RuntimeError("CONTRACT_REVISION_INVALID")
    if not isinstance(model.get("files"), dict) or "model.safetensors" not in model["files"]:
        raise RuntimeError("CONTRACT_MODEL_FILES_INVALID")
    if data.get("class_name") != "cup" or data.get("prompt") != "cup.":
        raise RuntimeError("CONTRACT_PROMPT_INVALID")
    expected_training = {
        "optimizer": "AdamW",
        "scheduler": "linear_decay",
        "train_precision": "bfloat16_autocast",
        "validation_precision": "float32",
        "checkpoint_precision": "float32",
        "augmentations": "none",
    }
    if any(training.get(key) != value for key, value in expected_training.items()):
        raise RuntimeError("CONTRACT_TRAINING_INVALID")
    positive_integers = (
        "seed",
        "epochs",
        "batch_size",
        "gradient_accumulation_steps",
        "data_workers",
        "checkpoint_frequency_epochs",
    )
    if any(type(training.get(key)) is not int or training[key] <= 0 for key in positive_integers):
        raise RuntimeError("CONTRACT_TRAINING_INVALID")
    if training["checkpoint_frequency_epochs"] != 1:
        raise RuntimeError("CONTRACT_CHECKPOINT_FREQUENCY_INVALID")
    if smoke.get("expected_train_samples") != 6 or smoke.get("expected_val_samples") != 6:
        raise RuntimeError("CONTRACT_SMOKE_INVALID")
    expected_threshold_rank = [
        "f1",
        "recall",
        "small_target_recall",
        "multi_cup_recall",
        "negative_fp",
        "box_threshold",
        "text_threshold",
    ]
    expected_checkpoint_rank = [
        "f1",
        "recall",
        "small_target_recall",
        "multi_cup_recall",
        "negative_fp",
        "negative_epoch",
    ]
    if validation.get("threshold_rank_descending") != expected_threshold_rank:
        raise RuntimeError("CONTRACT_THRESHOLD_RANK_INVALID")
    if validation.get("checkpoint_rank_descending") != expected_checkpoint_rank:
        raise RuntimeError("CONTRACT_CHECKPOINT_RANK_INVALID")


def _checkpoint_identity(
    *, contract_sha256: str, document: dict[str, Any], training_commit: str
) -> dict[str, str]:
    return {
        "contract_sha256": contract_sha256,
        "base_model_sha256": document["model"]["files"]["model.safetensors"],
        "train_inventory_sha256": document["data"]["train_inventory_sha256"],
        "val_inventory_sha256": document["data"]["val_inventory_sha256"],
        "training_commit": training_commit,
    }


def _atomic_torch_save(torch: Any, path: Path, document: dict[str, Any]) -> None:
    with path.open("xb") as stream:
        torch.save(document, stream)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class _ProcessedDataset:
    def __init__(self, samples: tuple[TrainingSample, ...], processor: Any, prompt: str) -> None:
        self._samples = samples
        self._processor = processor
        self._prompt = prompt

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, index: int) -> dict[str, Any]:
        from PIL import Image

        sample = self._samples[index]
        with Image.open(sample.image_path) as image:
            rgb = image.convert("RGB")
            encoded = self._processor(
                images=rgb,
                text=self._prompt,
                annotations=build_coco_annotation(sample, image_id=sample.seed),
                return_tensors="pt",
            )
        labels = encoded.pop("labels")
        if not isinstance(labels, list) or len(labels) != 1:
            raise RuntimeError("PROCESSOR_LABEL_CONTRACT_INVALID")
        result = {
            key: value.squeeze(0) if hasattr(value, "shape") and value.shape[0] == 1 else value
            for key, value in encoded.items()
        }
        result["labels"] = labels[0]
        return result


def _collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
    import torch

    labels = [item.pop("labels") for item in batch]
    keys = set(batch[0])
    if any(set(item) != keys for item in batch):
        raise RuntimeError("PROCESSOR_BATCH_CONTRACT_INVALID")
    result = {key: torch.stack([item[key] for item in batch]) for key in sorted(keys)}
    result["labels"] = labels
    return result


def _move_batch(batch: dict[str, Any], device: str) -> dict[str, Any]:
    labels = batch.pop("labels")
    moved = {key: value.to(device) for key, value in batch.items()}
    moved["labels"] = [
        {key: value.to(device) if hasattr(value, "to") else value for key, value in label.items()}
        for label in labels
    ]
    return moved


def _linear_factor(step: int, *, total_steps: int, warmup_steps: int) -> float:
    if step < warmup_steps:
        return float(step + 1) / max(1, warmup_steps)
    remaining = total_steps - step
    return max(0.0, float(remaining) / max(1, total_steps - warmup_steps))


def _training_loader(
    *,
    torch: Any,
    samples: tuple[TrainingSample, ...],
    processor: Any,
    prompt: str,
    batch_size: int,
    workers: int,
    seed: int,
) -> Any:
    generator = torch.Generator()
    generator.manual_seed(seed)
    return torch.utils.data.DataLoader(
        _ProcessedDataset(samples, processor, prompt),
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
        num_workers=workers,
        persistent_workers=workers > 0,
        collate_fn=_collate,
        pin_memory=True,
        drop_last=False,
    )


def _normalized_label(value: object) -> str:
    return str(value).strip().lower().rstrip(".")


def _evaluate(
    *,
    model: Any,
    processor: Any,
    samples: tuple[TrainingSample, ...],
    prompt: str,
    epoch: int,
    device: str,
    box_thresholds: list[float],
    text_thresholds: list[float],
    iou_threshold: float,
    small_area: float,
    multi_scenario: str,
) -> list[ValidationResult]:
    import torch
    from PIL import Image

    counts = {(box, text): _MetricCounts() for box in box_thresholds for text in text_thresholds}
    model.eval()
    with torch.inference_mode():
        for sample in samples:
            with Image.open(sample.image_path) as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                encoded = processor(images=rgb, text=prompt, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in encoded.items()}
            outputs = model(**inputs)
            for text_threshold in text_thresholds:
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
                for box_threshold in box_thresholds:
                    filtered = [item for item in cup_predictions if item[1] >= box_threshold]
                    predicted_boxes = [item[0] for item in filtered]
                    predicted_scores = [item[1] for item in filtered]
                    tp, fp, fn, matched = match_predictions(
                        predicted_boxes=predicted_boxes,
                        predicted_scores=predicted_scores,
                        truth_boxes=sample.boxes,
                        iou_threshold=iou_threshold,
                    )
                    current = counts[(box_threshold, text_threshold)]
                    current.tp += tp
                    current.fp += fp
                    current.fn += fn
                    small_indices = {
                        index
                        for index, truth in enumerate(sample.boxes)
                        if (truth.absolute_xyxy[2] - truth.absolute_xyxy[0])
                        * (truth.absolute_xyxy[3] - truth.absolute_xyxy[1])
                        < small_area
                    }
                    current.small_total += len(small_indices)
                    current.small_tp += len(matched.intersection(small_indices))
                    if sample.scenario == multi_scenario:
                        current.multi_total += len(sample.boxes)
                        current.multi_tp += len(matched)
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
    return results


def _save_checkpoint(
    *,
    torch: Any,
    model: Any,
    processor: Any,
    optimizer: Any,
    scheduler: Any,
    checkpoints_root: Path,
    epoch: int,
    identity: dict[str, str],
    result: ValidationResult,
    history: list[dict[str, Any]],
) -> Path:
    final = checkpoints_root / f"epoch-{epoch:03d}"
    staging = checkpoints_root / f".epoch-{epoch:03d}.staging"
    if final.exists() or staging.exists():
        raise FileExistsError(f"checkpoint path already exists: {final}")
    staging.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(staging, safe_serialization=True)
    processor.save_pretrained(staging)
    _atomic_torch_save(
        torch,
        staging / "training-state.pt",
        {
            "completed_epoch": epoch,
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "python_random_state": random.getstate(),
            "numpy_random_state": __import__("numpy").random.get_state(),
            "torch_cpu_rng_state": torch.get_rng_state(),
            "torch_cuda_rng_state_all": torch.cuda.get_rng_state_all(),
            "validation_history": history,
        },
    )
    manifest = {
        "schema_version": 1,
        "complete": True,
        "completed_epoch": epoch,
        "identity": identity,
        "selected_val_metrics": result.as_dict(),
        "files": checkpoint_file_entries(staging),
    }
    exclusive_json(staging / "checkpoint-manifest.json", manifest)
    _fsync_directory(staging)
    staging.rename(final)
    _fsync_directory(checkpoints_root)
    return final


def _append_jsonl(path: Path, document: dict[str, Any]) -> None:
    with path.open("ab") as stream:
        stream.write((json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def _restore_rng(torch: Any, state: dict[str, Any]) -> None:
    import numpy as np

    random.setstate(state["python_random_state"])
    np.random.set_state(state["numpy_random_state"])
    torch.set_rng_state(state["torch_cpu_rng_state"])
    torch.cuda.set_rng_state_all(state["torch_cuda_rng_state_all"])


def _fresh_reload(
    *,
    contract_path: Path,
    checkpoint: Path,
    image: Path,
    output: Path,
) -> None:
    command = [
        sys.executable,
        "-m",
        "so101_demo.cli.verify_grounding_dino_checkpoint",
        "--contract",
        str(contract_path),
        "--checkpoint",
        str(checkpoint),
        "--image",
        str(image),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, check=False, env=os.environ.copy())
    if result.returncode != 0:
        raise RuntimeError(f"FRESH_CHECKPOINT_RELOAD_FAILED: exit {result.returncode}")


def run_training(
    *,
    contract_path: Path,
    train_inventory: Path,
    val_inventory: Path,
    train_images: Path,
    val_images: Path,
    base_model: Path,
    output_root: Path,
    mode: str,
    training_commit: str,
    resume_checkpoint: Path | None = None,
) -> dict[str, Any]:
    import numpy as np
    import torch
    from transformers import AutoProcessor, GroundingDinoForObjectDetection

    if mode not in {"smoke", "formal"}:
        raise ValueError("mode must be smoke or formal")
    if len(training_commit) != 40 or any(
        character not in "0123456789abcdef" for character in training_commit
    ):
        raise ValueError("training commit must be a lowercase 40-character SHA")
    contract, contract_sha = load_contract(contract_path)
    _validate_contract(contract)
    model_contract = contract["model"]
    data_contract = contract["data"]
    training_contract = dict(contract["training"])
    _validate_sha_mapping(Path(base_model), model_contract["files"])
    device = require_cuda(torch)
    if output_root.exists() or output_root.is_symlink():
        raise FileExistsError(f"training output root already exists: {output_root}")
    if not output_root.parent.is_dir():
        raise FileNotFoundError(f"training output parent does not exist: {output_root.parent}")
    train_split = load_verified_split(
        inventory_path=train_inventory,
        image_root=train_images,
        expected_inventory_sha256=data_contract["train_inventory_sha256"],
        expected_split="train",
        expected_sample_count=data_contract["train_sample_count"],
        expected_source_archive_sha256=data_contract["source_archive_sha256"],
        expected_source_manifest_sha256=data_contract["source_manifest_sha256"],
        expected_generator_commit=data_contract["generator_commit"],
        expected_converter_commit=data_contract["converter_commit"],
    )
    val_split = load_verified_split(
        inventory_path=val_inventory,
        image_root=val_images,
        expected_inventory_sha256=data_contract["val_inventory_sha256"],
        expected_split="val",
        expected_sample_count=data_contract["val_sample_count"],
        expected_source_archive_sha256=data_contract["source_archive_sha256"],
        expected_source_manifest_sha256=data_contract["source_manifest_sha256"],
        expected_generator_commit=data_contract["generator_commit"],
        expected_converter_commit=data_contract["converter_commit"],
    )
    if mode == "smoke":
        train_split = select_smoke_subset(train_split)
        val_split = select_smoke_subset(val_split)
        training_contract.update(
            {
                "epochs": contract["smoke"]["epochs"],
                "batch_size": contract["smoke"]["batch_size"],
                "gradient_accumulation_steps": contract["smoke"]["gradient_accumulation_steps"],
            }
        )
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = training_contract["cublas_workspace_config"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    seed = training_contract["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(training_contract["deterministic_algorithms"])
    torch.backends.cudnn.benchmark = training_contract["cudnn_benchmark"]
    torch.backends.cudnn.deterministic = training_contract["cudnn_deterministic"]
    if training_contract["disable_flash_sdp"]:
        torch.backends.cuda.enable_flash_sdp(False)
    if training_contract["disable_memory_efficient_sdp"]:
        torch.backends.cuda.enable_mem_efficient_sdp(False)
    output_root.mkdir(mode=0o700, exist_ok=False)
    checkpoints_root = output_root / "checkpoints"
    checkpoints_root.mkdir()
    identity = _checkpoint_identity(
        contract_sha256=contract_sha, document=contract, training_commit=training_commit
    )
    resolved = {
        "schema_version": 1,
        "mode": mode,
        "training_commit": training_commit,
        "contract_sha256": contract_sha,
        "model": model_contract,
        "data": data_contract,
        "training": training_contract,
        "validation": contract["validation"],
        "resolved_sample_counts": {
            "train": len(train_split.samples),
            "val": len(val_split.samples),
        },
        "sealed_test_mounted": False,
        "coco100_mounted": False,
        "sam_loaded": False,
    }
    exclusive_json(output_root / "resolved-config.json", resolved)
    exclusive_json(
        output_root / "environment.json",
        {
            "python": sys.version,
            "python_executable": sys.executable,
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "transformers": __import__("transformers").__version__,
            "device": device,
            "gpu_name": torch.cuda.get_device_name(0),
            "gpu_uuid": str(torch.cuda.get_device_properties(0).uuid),
            "bf16_supported": torch.cuda.is_bf16_supported(),
            "cpu_fallback": False,
        },
    )
    exclusive_json(
        output_root / "provenance.json",
        {
            "training_commit": training_commit,
            "base_model_root": str(Path(base_model).resolve()),
            "train_inventory": str(Path(train_inventory).resolve()),
            "val_inventory": str(Path(val_inventory).resolve()),
            "train_image_root": str(Path(train_images).resolve()),
            "val_image_root": str(Path(val_images).resolve()),
            "synthetic_test_access": "none",
            "coco100_access": "none",
            "network": "none",
        },
    )
    verified_resume = None
    if resume_checkpoint is not None:
        verified_resume = verify_complete_checkpoint(resume_checkpoint, expected_identity=identity)
        processor_source = verified_resume.root
        model_source = verified_resume.root
    else:
        processor_source = Path(base_model)
        model_source = Path(base_model)
    processor = AutoProcessor.from_pretrained(processor_source, local_files_only=True)
    model = GroundingDinoForObjectDetection.from_pretrained(
        model_source, local_files_only=True, use_safetensors=True
    )
    model.to(device)
    if training_contract["gradient_checkpointing"]:
        model.gradient_checkpointing_enable()
    model.train()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=training_contract["learning_rate"],
        betas=tuple(training_contract["betas"]),
        eps=training_contract["epsilon"],
        weight_decay=training_contract["weight_decay"],
    )
    accumulation = training_contract["gradient_accumulation_steps"]
    batches_per_epoch = math.ceil(len(train_split.samples) / training_contract["batch_size"])
    optimizer_steps_per_epoch = math.ceil(batches_per_epoch / accumulation)
    total_steps = optimizer_steps_per_epoch * training_contract["epochs"]
    warmup_steps = int(math.ceil(total_steps * training_contract["warmup_ratio"]))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lr_lambda=lambda step: _linear_factor(
            step, total_steps=total_steps, warmup_steps=warmup_steps
        ),
    )
    start_epoch = 1
    history: list[dict[str, Any]] = []
    if verified_resume is not None:
        state = torch.load(
            verified_resume.root / "training-state.pt", map_location="cpu", weights_only=False
        )
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        _restore_rng(torch, state)
        start_epoch = verified_resume.completed_epoch + 1
        history = list(state.get("validation_history", []))
    if start_epoch > training_contract["epochs"]:
        raise RuntimeError("RESUME_EPOCH_OUT_OF_RANGE")
    probe_dataset = _ProcessedDataset(train_split.samples, processor, data_contract["prompt"])
    negative_index = next(
        index for index, sample in enumerate(train_split.samples) if not sample.boxes
    )
    positive_index = next(index for index, sample in enumerate(train_split.samples) if sample.boxes)
    negative_probe = probe_dataset[negative_index]
    positive_probe = probe_dataset[positive_index]
    class_labels = positive_probe["labels"]["class_labels"]
    boxes = positive_probe["labels"]["boxes"]
    negative_boxes = negative_probe["labels"]["boxes"]
    input_ids = positive_probe["input_ids"]
    if input_ids.numel() <= 2 or boxes.ndim != 2 or boxes.shape[-1] != 4:
        raise RuntimeError("PROCESSOR_SMOKE_CONTRACT_INVALID")
    if (
        class_labels.ndim != 1
        or class_labels.numel() == 0
        or negative_boxes.shape != (0, 4)
        or not torch.all((boxes >= 0.0) & (boxes <= 1.0))
    ):
        raise RuntimeError("PROCESSOR_SMOKE_CONTRACT_INVALID")
    exclusive_json(
        output_root / "processor-label-contract.json",
        {
            "input_token_count": int(input_ids.numel()),
            "box_shape": list(boxes.shape),
            "class_label_count": int(class_labels.numel()),
            "normalized_center_boxes": True,
            "negative_box_shape": list(negative_boxes.shape),
            "negative_target_present": True,
            "prompt": data_contract["prompt"],
        },
    )
    validation = contract["validation"]
    box_thresholds = [float(value) for value in validation["box_threshold_grid"]]
    text_thresholds = [float(value) for value in validation["text_threshold_grid"]]
    epoch_results: list[ValidationResult] = []
    checkpoint_by_epoch: dict[int, Path] = {}
    training_started = time.monotonic()
    metrics_path = output_root / "epoch-metrics.jsonl"
    for epoch in range(start_epoch, training_contract["epochs"] + 1):
        model.train()
        torch.cuda.reset_peak_memory_stats()
        loader = _training_loader(
            torch=torch,
            samples=train_split.samples,
            processor=processor,
            prompt=data_contract["prompt"],
            batch_size=training_contract["batch_size"],
            workers=training_contract["data_workers"],
            seed=seed + epoch,
        )
        optimizer.zero_grad(set_to_none=True)
        epoch_loss = 0.0
        for batch_index, batch in enumerate(loader, start=1):
            moved = _move_batch(batch, device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                outputs = model(**moved)
                loss = outputs.loss
            if loss is None or not torch.isfinite(loss):
                raise RuntimeError("NONFINITE_OR_MISSING_LOSS")
            epoch_loss += float(loss.detach().cpu())
            (loss / accumulation).backward()
            if batch_index % accumulation == 0 or batch_index == len(loader):
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), training_contract["max_grad_norm"]
                )
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if batch_index == 1 or batch_index % 25 == 0 or batch_index == len(loader):
                elapsed = time.monotonic() - training_started
                completed_batches = (epoch - start_epoch) * len(loader) + batch_index
                total_batches = (training_contract["epochs"] - start_epoch + 1) * len(loader)
                eta = elapsed / completed_batches * max(0, total_batches - completed_batches)
                print(
                    json.dumps(
                        {
                            "event": "training_progress",
                            "epoch": epoch,
                            "batch": batch_index,
                            "batches": len(loader),
                            "loss": float(loss.detach().cpu()),
                            "eta_seconds": eta,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
        grid_results = _evaluate(
            model=model,
            processor=processor,
            samples=val_split.samples,
            prompt=data_contract["prompt"],
            epoch=epoch,
            device=device,
            box_thresholds=box_thresholds,
            text_thresholds=text_thresholds,
            iou_threshold=float(validation["box_iou_threshold"]),
            small_area=float(validation["small_area_max_exclusive_px2"]),
            multi_scenario=validation["multi_cup_scenario"],
        )
        best = select_best_threshold(grid_results)
        epoch_results.append(best)
        elapsed = time.monotonic() - training_started
        remaining_epochs = training_contract["epochs"] - epoch
        completed_epochs = epoch - start_epoch + 1
        epoch_document = {
            "event": "epoch_complete",
            "epoch": epoch,
            "mean_loss": epoch_loss / len(loader),
            "selected_val": best.as_dict(),
            "threshold_grid_results": [result.as_dict() for result in grid_results],
            "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
            "elapsed_seconds": elapsed,
            "eta_seconds": elapsed / completed_epochs * remaining_epochs,
            "learning_rate": scheduler.get_last_lr()[0],
        }
        history.append(epoch_document)
        checkpoint = _save_checkpoint(
            torch=torch,
            model=model,
            processor=processor,
            optimizer=optimizer,
            scheduler=scheduler,
            checkpoints_root=checkpoints_root,
            epoch=epoch,
            identity=identity,
            result=best,
            history=history,
        )
        checkpoint_by_epoch[epoch] = checkpoint
        epoch_document["checkpoint_manifest_sha256"] = sha256_file(
            checkpoint / "checkpoint-manifest.json"
        )
        _append_jsonl(metrics_path, epoch_document)
        print(json.dumps(epoch_document, sort_keys=True), flush=True)
    selected = select_best_checkpoint(epoch_results)
    selected_checkpoint = checkpoint_by_epoch[selected.epoch]
    verified = verify_complete_checkpoint(selected_checkpoint, expected_identity=identity)
    frozen_manifest = {
        "schema_version": 1,
        "status": "FROZEN",
        "selection_source": "synthetic_val_only",
        "selected_epoch": selected.epoch,
        "selected_metrics": selected.as_dict(),
        "checkpoint_relative_path": selected_checkpoint.relative_to(output_root).as_posix(),
        "checkpoint_manifest_sha256": verified.manifest_sha256,
        "identity": identity,
        "prompt": data_contract["prompt"],
        "class_name": data_contract["class_name"],
        "synthetic_test_access": "none",
        "coco100_access": "none",
        "sam_training": "none",
    }
    exclusive_json(output_root / "frozen-model-manifest.json", frozen_manifest)
    reload_output = output_root / "fresh-reload-verification.json"
    _fresh_reload(
        contract_path=Path(contract_path).resolve(),
        checkpoint=selected_checkpoint,
        image=val_split.samples[0].image_path,
        output=reload_output,
    )
    result = {
        "status": "VALID",
        "mode": mode,
        "selected_epoch": selected.epoch,
        "selected_metrics": selected.as_dict(),
        "checkpoint": str(selected_checkpoint),
        "checkpoint_manifest_sha256": verified.manifest_sha256,
        "fresh_reload_sha256": sha256_file(reload_output),
        "synthetic_test_access": "none",
        "coco100_access": "none",
        "cpu_fallback": False,
    }
    exclusive_json(output_root / "run-result.json", result)
    _fsync_directory(output_root)
    return result


def verify_checkpoint_in_fresh_process(
    *, contract_path: Path, checkpoint: Path, image: Path, output: Path
) -> dict[str, Any]:
    import torch
    from PIL import Image
    from transformers import AutoProcessor, GroundingDinoForObjectDetection

    contract, contract_sha = load_contract(contract_path)
    _validate_contract(contract)
    training_commit = json.loads(
        (checkpoint / "checkpoint-manifest.json").read_text(encoding="utf-8")
    )["identity"]["training_commit"]
    identity = _checkpoint_identity(
        contract_sha256=contract_sha, document=contract, training_commit=training_commit
    )
    verified = verify_complete_checkpoint(checkpoint, expected_identity=identity)
    device = require_cuda(torch)
    processor = AutoProcessor.from_pretrained(verified.root, local_files_only=True)
    model = GroundingDinoForObjectDetection.from_pretrained(
        verified.root, local_files_only=True, use_safetensors=True
    ).to(device)
    model.eval()
    with Image.open(image) as source:
        rgb = source.convert("RGB")
        encoded = processor(images=rgb, text=contract["data"]["prompt"], return_tensors="pt")
    inputs = {key: value.to(device) for key, value in encoded.items()}
    with torch.inference_mode():
        outputs = model(**inputs)
    finite = bool(torch.isfinite(outputs.logits).all() and torch.isfinite(outputs.pred_boxes).all())
    if not finite or outputs.logits.device.type != "cuda":
        raise RuntimeError("FRESH_RELOAD_INFERENCE_INVALID")
    document = {
        "status": "VALID",
        "device": str(outputs.logits.device),
        "cpu_fallback": False,
        "input_token_count": int(inputs["input_ids"].numel()),
        "query_count": int(outputs.pred_boxes.shape[1]),
        "finite_outputs": finite,
        "checkpoint_manifest_sha256": verified.manifest_sha256,
        "prompt": contract["data"]["prompt"],
    }
    exclusive_json(output, document)
    return document
