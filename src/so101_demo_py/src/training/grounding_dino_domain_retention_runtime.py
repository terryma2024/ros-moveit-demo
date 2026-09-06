"""CUDA-only frozen-backbone Grounding DINO domain-retention training runtime."""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

from .grounding_dino_domain_retention import (
    LAST_SWIN_STAGE_PREFIX,
    compute_decoder_supervised_loss,
    compute_distillation_losses,
    configure_last_stage_trainability,
    configure_student_trainability,
    freeze_teacher,
    optimizer_parameter_groups,
    select_joint_threshold,
    select_smoke_samples,
    validate_domain_retention_contract,
)
from .grounding_dino_finetune import (
    ValidationResult,
    checkpoint_file_entries,
    exclusive_json,
    load_contract,
    load_verified_split,
    require_cuda,
    sha256_file,
    verify_complete_checkpoint,
)
from .grounding_dino_runtime import (
    _append_jsonl,
    _checkpoint_identity,
    _evaluate,
    _fresh_reload,
    _fsync_directory,
    _linear_factor,
    _move_batch,
    _ProcessedDataset,
    _save_checkpoint,
    _training_loader,
    _validate_contract,
    _validate_sha_mapping,
    enable_grounding_dino_gradient_checkpointing,
)


def _last_swin_stage(student: Any) -> Any:
    layers = student.model.backbone.conv_encoder.model.encoder.layers
    if len(layers) != 4:
        raise RuntimeError("LAST_SWIN_STAGE_MODEL_MISMATCH")
    return layers[3]


def _student_training_mode(student: Any, *, train_last_swin_stage: bool = False) -> None:
    student.eval()
    student.model.decoder.train()
    student.model.encoder_output_bbox_embed.train()
    student.model.enc_output.train()
    student.model.enc_output_norm.train()
    if train_last_swin_stage:
        _last_swin_stage(student).train()


def _verify_student_initialization(root: Path, training: dict[str, Any]) -> dict[str, Any]:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise RuntimeError("STUDENT_INITIALIZATION_INVALID")
    candidate = candidate.resolve()
    manifest_path = candidate / "checkpoint-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("STUDENT_INITIALIZATION_MANIFEST_INVALID")
    if sha256_file(manifest_path) != training[
        "student_initialization_checkpoint_manifest_sha256"
    ]:
        raise RuntimeError("STUDENT_INITIALIZATION_MANIFEST_SHA256_MISMATCH")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("STUDENT_INITIALIZATION_MANIFEST_INVALID") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("complete") is not True
        or manifest.get("completed_epoch")
        != training["student_initialization_completed_epoch"]
        or manifest.get("files") != checkpoint_file_entries(candidate)
    ):
        raise RuntimeError("STUDENT_INITIALIZATION_MANIFEST_INVALID")
    model_path = candidate / "model.safetensors"
    if sha256_file(model_path) != training["student_initialization_model_sha256"]:
        raise RuntimeError("STUDENT_INITIALIZATION_MODEL_SHA256_MISMATCH")
    return {
        "root": str(candidate),
        "checkpoint_manifest_sha256": sha256_file(manifest_path),
        "model_safetensors_sha256": sha256_file(model_path),
        "completed_epoch": manifest["completed_epoch"],
    }


def _result_at(
    results: list[ValidationResult], *, box_threshold: float, text_threshold: float
) -> ValidationResult:
    matches = [
        result
        for result in results
        if result.box_threshold == box_threshold and result.text_threshold == text_threshold
    ]
    if len(matches) != 1:
        raise RuntimeError("VALIDATION_THRESHOLD_RESULT_MISSING")
    return matches[0]


def _joint_epoch_rank(record: dict[str, Any]) -> tuple[float, ...]:
    near = record["selected_near"]
    real = record["selected_real"]
    return (
        record["joint_harmonic_f1"],
        min(near["recall"], real["recall"]),
        near["f1"],
        real["f1"],
        -float(near["fp"] + real["fp"]),
        -float(record["epoch"]),
    )


def run_domain_retention_training(
    *,
    contract_path: Path,
    train_inventory: Path,
    real_val_inventory: Path,
    near_val_inventory: Path,
    train_images: Path,
    real_val_images: Path,
    near_val_images: Path,
    base_model: Path,
    output_root: Path,
    mode: str,
    training_commit: str,
    student_model: Path | None = None,
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
    validate_domain_retention_contract(contract)
    model_contract = contract["model"]
    data_contract = contract["data"]
    training = dict(contract["training"])
    train_last_swin_stage = (
        training["initialization"] == "selected_phase1_student_official_base_teacher"
    )
    if train_last_swin_stage:
        if student_model is None:
            raise RuntimeError("STUDENT_INITIALIZATION_REQUIRED")
        student_initialization = _verify_student_initialization(student_model, training)
    else:
        if student_model is not None:
            raise RuntimeError("STUDENT_INITIALIZATION_FORBIDDEN")
        student_initialization = {
            "root": str(Path(base_model).resolve()),
            "checkpoint_manifest_sha256": None,
            "model_safetensors_sha256": model_contract["files"]["model.safetensors"],
            "completed_epoch": 0,
        }
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
    real_val_split = load_verified_split(
        inventory_path=real_val_inventory,
        image_root=real_val_images,
        expected_inventory_sha256=data_contract["val_inventory_sha256"],
        expected_split="val",
        expected_sample_count=data_contract["val_sample_count"],
        expected_source_archive_sha256=data_contract["source_archive_sha256"],
        expected_source_manifest_sha256=data_contract["source_manifest_sha256"],
        expected_generator_commit=data_contract["generator_commit"],
        expected_converter_commit=data_contract["converter_commit"],
    )
    near_contract = data_contract["near_val"]
    near_val_split = load_verified_split(
        inventory_path=near_val_inventory,
        image_root=near_val_images,
        expected_inventory_sha256=near_contract["inventory_sha256"],
        expected_split="val",
        expected_sample_count=near_contract["sample_count"],
        expected_source_archive_sha256=near_contract["source_archive_sha256"],
        expected_source_manifest_sha256=near_contract["source_manifest_sha256"],
        expected_generator_commit=near_contract["generator_commit"],
        expected_converter_commit=near_contract["converter_commit"],
    )
    if mode == "smoke":
        train_samples, near_samples, real_samples = select_smoke_samples(
            train_split.samples, near_val_split.samples, real_val_split.samples
        )
        training.update(
            {
                "epochs": contract["smoke"]["epochs"],
                "batch_size": contract["smoke"]["batch_size"],
                "gradient_accumulation_steps": contract["smoke"][
                    "gradient_accumulation_steps"
                ],
            }
        )
    else:
        train_samples = train_split.samples
        near_samples = near_val_split.samples
        real_samples = real_val_split.samples

    os.environ["CUBLAS_WORKSPACE_CONFIG"] = training["cublas_workspace_config"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    seed = training["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(
        training["deterministic_algorithms"], warn_only=training["deterministic_warn_only"]
    )
    torch.backends.cudnn.benchmark = training["cudnn_benchmark"]
    torch.backends.cudnn.deterministic = training["cudnn_deterministic"]
    if training["disable_flash_sdp"]:
        torch.backends.cuda.enable_flash_sdp(False)
    if training["disable_memory_efficient_sdp"]:
        torch.backends.cuda.enable_mem_efficient_sdp(False)

    output_root.mkdir(mode=0o700, exist_ok=False)
    _fsync_directory(output_root.parent)
    checkpoints_root = output_root / "checkpoints"
    checkpoints_root.mkdir()
    identity = _checkpoint_identity(
        contract_sha256=contract_sha, document=contract, training_commit=training_commit
    )
    exclusive_json(
        output_root / "resolved-config.json",
        {
            "schema_version": 1,
            "mode": mode,
            "training_commit": training_commit,
            "contract_sha256": contract_sha,
            "model": model_contract,
            "data": data_contract,
            "training": training,
            "validation": contract["validation"],
            "resolved_sample_counts": {
                "train": len(train_samples),
                "near_val": len(near_samples),
                "real_val": len(real_samples),
                "val_total": len(near_samples) + len(real_samples),
            },
            "sealed_test_mounted": False,
            "coco100_mounted": False,
            "sam_loaded": False,
            "resume_checkpoint": None,
            "phase": "last_swin_stage" if train_last_swin_stage else "frozen_backbone",
            "student_initialization": student_initialization,
        },
    )
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
            "deterministic_algorithms_enabled": torch.are_deterministic_algorithms_enabled(),
            "deterministic_warn_only": torch.is_deterministic_algorithms_warn_only_enabled(),
            "cudnn_benchmark": torch.backends.cudnn.benchmark,
            "cudnn_deterministic": torch.backends.cudnn.deterministic,
            "flash_sdp_enabled": torch.backends.cuda.flash_sdp_enabled(),
            "memory_efficient_sdp_enabled": torch.backends.cuda.mem_efficient_sdp_enabled(),
        },
    )
    exclusive_json(
        output_root / "provenance.json",
        {
            "training_commit": training_commit,
            "base_model_root": str(Path(base_model).resolve()),
            "teacher_initialization": "official_pinned_base",
            "student_initialization": (
                "selected_phase1_checkpoint"
                if train_last_swin_stage
                else "official_pinned_base"
            ),
            "student_initialization_detail": student_initialization,
            "epoch5_checkpoint_access": "none",
            "train_inventory": str(Path(train_inventory).resolve()),
            "real_val_inventory": str(Path(real_val_inventory).resolve()),
            "near_val_inventory": str(Path(near_val_inventory).resolve()),
            "synthetic_test_access": "none",
            "coco100_access": "none",
            "sam_access": "none",
            "network": "none",
        },
    )

    processor = AutoProcessor.from_pretrained(base_model, local_files_only=True)
    teacher = GroundingDinoForObjectDetection.from_pretrained(
        base_model, local_files_only=True, use_safetensors=True
    )
    student = GroundingDinoForObjectDetection.from_pretrained(
        student_model if train_last_swin_stage else base_model,
        local_files_only=True,
        use_safetensors=True,
    )
    teacher_receipt = freeze_teacher(teacher)
    student_receipt = (
        configure_last_stage_trainability(student)
        if train_last_swin_stage
        else configure_student_trainability(student)
    )
    teacher.to(device)
    student.to(device)
    teacher.eval()
    if training["gradient_checkpointing"]:
        checkpointing_method = enable_grounding_dino_gradient_checkpointing(student)
    else:
        checkpointing_method = "disabled"
    _student_training_mode(student, train_last_swin_stage=train_last_swin_stage)
    if student.model.backbone.training or student.model.text_backbone.training:
        raise RuntimeError("FROZEN_BACKBONE_TRAINING_MODE_INVALID")
    exclusive_json(
        output_root / "trainability.json",
        {
            "teacher": teacher_receipt,
            "student": student_receipt,
            "student_backbone_training": student.model.backbone.training,
            "student_text_backbone_training": student.model.text_backbone.training,
            "student_encoder_training": student.model.encoder.training,
            "student_decoder_training": student.model.decoder.training,
            "student_last_swin_stage_training": _last_swin_stage(student).training,
            "last_swin_stage_prefix": (
                LAST_SWIN_STAGE_PREFIX if train_last_swin_stage else None
            ),
            "gradient_checkpointing_method": checkpointing_method,
            "teacher_and_student_initialized_separately": True,
        },
    )
    trainable_parameters = [parameter for parameter in student.parameters() if parameter.requires_grad]
    if not trainable_parameters:
        raise RuntimeError("NO_TRAINABLE_PARAMETERS")
    optimizer_parameters: Any = (
        optimizer_parameter_groups(
            student,
            head_learning_rate=training["learning_rate"],
            backbone_learning_rate=training["backbone_learning_rate"],
        )
        if train_last_swin_stage
        else trainable_parameters
    )
    optimizer = torch.optim.AdamW(
        optimizer_parameters,
        lr=training["learning_rate"],
        betas=tuple(training["betas"]),
        eps=training["epsilon"],
        weight_decay=training["weight_decay"],
    )
    accumulation = training["gradient_accumulation_steps"]
    batches_per_epoch = math.ceil(len(train_samples) / training["batch_size"])
    optimizer_steps_per_epoch = math.ceil(batches_per_epoch / accumulation)
    total_steps = optimizer_steps_per_epoch * training["epochs"]
    warmup_steps = int(math.ceil(total_steps * training["warmup_ratio"]))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lr_lambda=lambda step: _linear_factor(
            step, total_steps=total_steps, warmup_steps=warmup_steps
        ),
    )

    probe = _ProcessedDataset(train_samples, processor, data_contract["prompt"])
    negative = probe[next(index for index, sample in enumerate(train_samples) if not sample.boxes)]
    positive = probe[next(index for index, sample in enumerate(train_samples) if sample.boxes)]
    if negative["labels"]["boxes"].shape != (0, 4) or positive["labels"]["boxes"].shape[-1] != 4:
        raise RuntimeError("PROCESSOR_SMOKE_CONTRACT_INVALID")
    exclusive_json(
        output_root / "processor-label-contract.json",
        {
            "positive_box_shape": list(positive["labels"]["boxes"].shape),
            "negative_box_shape": list(negative["labels"]["boxes"].shape),
            "prompt": data_contract["prompt"],
        },
    )

    validation = contract["validation"]
    box_thresholds = [float(value) for value in validation["box_threshold_grid"]]
    text_thresholds = [float(value) for value in validation["text_threshold_grid"]]
    near_primary_samples = tuple(
        sample
        for sample in near_samples
        if sample.scenario != validation["primary_near_excluded_scenario"]
    )
    metrics_path = output_root / "epoch-metrics.jsonl"
    checkpoint_by_epoch: dict[int, Path] = {}
    epoch_records: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    training_started = time.monotonic()
    frozen_gradient_check_recorded = False
    for epoch in range(1, training["epochs"] + 1):
        _student_training_mode(student, train_last_swin_stage=train_last_swin_stage)
        teacher.eval()
        torch.cuda.reset_peak_memory_stats()
        loader = _training_loader(
            torch=torch,
            samples=train_samples,
            processor=processor,
            prompt=data_contract["prompt"],
            batch_size=training["batch_size"],
            workers=training["data_workers"],
            seed=seed + epoch,
        )
        optimizer.zero_grad(set_to_none=True)
        sums = {"supervised": 0.0, "token": 0.0, "box": 0.0, "total": 0.0}
        supervised_component_sums = {
            "loss_ce": 0.0,
            "loss_bbox": 0.0,
            "loss_giou": 0.0,
        }
        candidate_total = 0
        distilled_sample_total = 0
        skipped_negative_sample_total = 0
        for batch_index, batch in enumerate(loader, start=1):
            moved = _move_batch(batch, device)
            teacher_inputs = {key: value for key, value in moved.items() if key != "labels"}
            with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                teacher_outputs = teacher(**teacher_inputs)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                student_outputs = student(**moved)
                if student_outputs.loss_dict is None:
                    raise RuntimeError("SUPERVISED_LOSS_COMPONENTS_MISSING")
                supervised_loss = compute_decoder_supervised_loss(
                    loss_dict=student_outputs.loss_dict,
                    bbox_loss_coefficient=student.config.bbox_loss_coefficient,
                    giou_loss_coefficient=student.config.giou_loss_coefficient,
                )
                distill_samples = torch.tensor(
                    [label["boxes"].shape[0] > 0 for label in moved["labels"]],
                    dtype=torch.bool,
                    device=device,
                )
                distillation = compute_distillation_losses(
                    student_logits=student_outputs.logits,
                    student_boxes=student_outputs.pred_boxes,
                    teacher_logits=teacher_outputs.logits,
                    teacher_boxes=teacher_outputs.pred_boxes,
                    attention_mask=moved["attention_mask"],
                    distill_samples=distill_samples,
                    candidate_threshold=training["teacher_candidate_threshold"],
                    topk_fallback=training["teacher_candidate_topk_fallback"],
                )
                total_loss = (
                    supervised_loss
                    + training["teacher_token_logit_lambda"] * distillation.token_logits
                    + training["teacher_candidate_box_lambda"] * distillation.candidate_boxes
                )
            if supervised_loss is None or not all(
                bool(torch.isfinite(value))
                for value in (
                    supervised_loss,
                    distillation.token_logits,
                    distillation.candidate_boxes,
                    total_loss,
                )
            ):
                raise RuntimeError("NONFINITE_OR_MISSING_LOSS")
            values = {
                "supervised": float(supervised_loss.detach().cpu()),
                "token": float(distillation.token_logits.detach().cpu()),
                "box": float(distillation.candidate_boxes.detach().cpu()),
                "total": float(total_loss.detach().cpu()),
            }
            for key, value in values.items():
                sums[key] += value
            supervised_components = {
                key: float(student_outputs.loss_dict[key].detach().cpu())
                for key in supervised_component_sums
            }
            if not all(math.isfinite(value) for value in supervised_components.values()):
                raise RuntimeError("NONFINITE_SUPERVISED_LOSS_COMPONENT")
            for key, value in supervised_components.items():
                supervised_component_sums[key] += value
            candidate_total += distillation.candidate_count
            distilled_sample_total += int(distill_samples.sum().item())
            skipped_negative_sample_total += int((~distill_samples).sum().item())
            (total_loss / accumulation).backward()
            if not frozen_gradient_check_recorded:
                violations = [
                    name
                    for name, parameter in student.named_parameters()
                    if not parameter.requires_grad and parameter.grad is not None
                ]
                if violations:
                    raise RuntimeError(f"FROZEN_PARAMETER_GRADIENT:{violations[0]}")
                exclusive_json(
                    output_root / "frozen-gradient-check.json",
                    {"batch": batch_index, "epoch": epoch, "violations": [], "status": "PASS"},
                )
                frozen_gradient_check_recorded = True
            if batch_index % accumulation == 0 or batch_index == len(loader):
                torch.nn.utils.clip_grad_norm_(trainable_parameters, training["max_grad_norm"])
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if batch_index == 1 or batch_index % 25 == 0 or batch_index == len(loader):
                elapsed = time.monotonic() - training_started
                completed_batches = (epoch - 1) * len(loader) + batch_index
                total_batches = training["epochs"] * len(loader)
                eta = elapsed / completed_batches * max(0, total_batches - completed_batches)
                print(
                    json.dumps(
                        {
                            "event": "training_progress",
                            "epoch": epoch,
                            "batch": batch_index,
                            "batches": len(loader),
                            "supervised_loss": values["supervised"],
                            "supervised_decoder_loss_components": supervised_components,
                            "teacher_token_logit_loss": values["token"],
                            "teacher_candidate_box_loss": values["box"],
                            "total_loss": values["total"],
                            "teacher_candidate_count": distillation.candidate_count,
                            "teacher_distillation_samples": int(distill_samples.sum().item()),
                            "teacher_distillation_skipped_negative_samples": int(
                                (~distill_samples).sum().item()
                            ),
                            "eta_seconds": eta,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

        all_results = _evaluate(
            model=student,
            processor=processor,
            samples=near_samples,
            prompt=data_contract["prompt"],
            epoch=epoch,
            device=device,
            box_thresholds=box_thresholds,
            text_thresholds=text_thresholds,
            iou_threshold=float(validation["box_iou_threshold"]),
            small_area=float(validation["small_area_max_exclusive_px2"]),
            multi_scenario=validation["multi_cup_scenario"],
        )
        near_results = _evaluate(
            model=student,
            processor=processor,
            samples=near_primary_samples,
            prompt=data_contract["prompt"],
            epoch=epoch,
            device=device,
            box_thresholds=box_thresholds,
            text_thresholds=text_thresholds,
            iou_threshold=float(validation["box_iou_threshold"]),
            small_area=float(validation["small_area_max_exclusive_px2"]),
            multi_scenario=validation["multi_cup_scenario"],
        )
        real_results = _evaluate(
            model=student,
            processor=processor,
            samples=real_samples,
            prompt=data_contract["prompt"],
            epoch=epoch,
            device=device,
            box_thresholds=box_thresholds,
            text_thresholds=text_thresholds,
            iou_threshold=float(validation["box_iou_threshold"]),
            small_area=float(validation["small_area_max_exclusive_px2"]),
            multi_scenario=validation["multi_cup_scenario"],
        )
        joint = select_joint_threshold(near_results, real_results)
        all_selected = _result_at(
            all_results,
            box_threshold=joint.near.box_threshold,
            text_threshold=joint.near.text_threshold,
        )
        elapsed = time.monotonic() - training_started
        epoch_record = {
            "event": "epoch_complete",
            "epoch": epoch,
            "mean_losses": {key: value / len(loader) for key, value in sums.items()},
            "mean_supervised_decoder_loss_components": {
                key: value / len(loader) for key, value in supervised_component_sums.items()
            },
            "mean_teacher_candidates": candidate_total / len(loader),
            "teacher_distillation_samples": distilled_sample_total,
            "teacher_distillation_skipped_negative_samples": skipped_negative_sample_total,
            "selected_thresholds": {
                "box": joint.near.box_threshold,
                "text": joint.near.text_threshold,
            },
            "joint_harmonic_f1": joint.harmonic_f1,
            "selected_near": joint.near.as_dict(),
            "selected_real": joint.real.as_dict(),
            "selected_all_scenario": all_selected.as_dict(),
            "dino_only_raw_candidates": {
                "near": _result_at(
                    near_results,
                    box_threshold=min(box_thresholds),
                    text_threshold=min(text_thresholds),
                ).as_dict(),
                "real": _result_at(
                    real_results,
                    box_threshold=min(box_thresholds),
                    text_threshold=min(text_thresholds),
                ).as_dict(),
                "box_floor": min(box_thresholds),
                "text_floor": min(text_thresholds),
                "sam_loaded": False,
            },
            "near_threshold_grid_results": [result.as_dict() for result in near_results],
            "real_threshold_grid_results": [result.as_dict() for result in real_results],
            "all_scenario_threshold_grid_results": [result.as_dict() for result in all_results],
            "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
            "elapsed_seconds": elapsed,
            "eta_seconds": elapsed / epoch * (training["epochs"] - epoch),
            "learning_rate": scheduler.get_last_lr()[0],
        }
        history.append(epoch_record)
        checkpoint = _save_checkpoint(
            torch=torch,
            model=student,
            processor=processor,
            optimizer=optimizer,
            scheduler=scheduler,
            checkpoints_root=checkpoints_root,
            epoch=epoch,
            identity=identity,
            result=joint.near,
            history=history,
        )
        checkpoint_by_epoch[epoch] = checkpoint
        epoch_record["checkpoint_manifest_sha256"] = sha256_file(
            checkpoint / "checkpoint-manifest.json"
        )
        epoch_records.append(epoch_record)
        _append_jsonl(metrics_path, epoch_record)
        print(json.dumps(epoch_record, sort_keys=True), flush=True)

    selected_record = max(epoch_records, key=_joint_epoch_rank)
    selected_checkpoint = checkpoint_by_epoch[selected_record["epoch"]]
    verified = verify_complete_checkpoint(selected_checkpoint, expected_identity=identity)
    exclusive_json(
        output_root / "frozen-model-manifest.json",
        {
            "schema_version": 1,
            "status": "FROZEN",
            "selection_source": "joint_near_synthetic_and_independent_real_val_only",
            "selection_rule": "joint_harmonic_f1",
            "selected_epoch": selected_record["epoch"],
            "selected_thresholds": selected_record["selected_thresholds"],
            "joint_harmonic_f1": selected_record["joint_harmonic_f1"],
            "selected_near": selected_record["selected_near"],
            "selected_real": selected_record["selected_real"],
            "selected_all_scenario": selected_record["selected_all_scenario"],
            "checkpoint_relative_path": selected_checkpoint.relative_to(output_root).as_posix(),
            "checkpoint_manifest_sha256": verified.manifest_sha256,
            "identity": identity,
            "prompt": data_contract["prompt"],
            "class_name": data_contract["class_name"],
            "synthetic_test_access": "none",
            "coco100_access": "none",
            "sam_training": "none",
        },
    )
    reload_output = output_root / "fresh-reload-verification.json"
    _fresh_reload(
        contract_path=Path(contract_path).resolve(),
        checkpoint=selected_checkpoint,
        image=real_samples[0].image_path,
        output=reload_output,
    )
    result = {
        "status": "VALID",
        "mode": mode,
        "selected_epoch": selected_record["epoch"],
        "selected_thresholds": selected_record["selected_thresholds"],
        "joint_harmonic_f1": selected_record["joint_harmonic_f1"],
        "selected_near": selected_record["selected_near"],
        "selected_real": selected_record["selected_real"],
        "selected_all_scenario": selected_record["selected_all_scenario"],
        "checkpoint": str(selected_checkpoint),
        "checkpoint_manifest_sha256": verified.manifest_sha256,
        "fresh_reload_sha256": sha256_file(reload_output),
        "synthetic_test_access": "none",
        "coco100_access": "none",
        "sam_loaded": False,
        "cpu_fallback": False,
    }
    exclusive_json(output_root / "run-result.json", result)
    _fsync_directory(output_root)
    return result
