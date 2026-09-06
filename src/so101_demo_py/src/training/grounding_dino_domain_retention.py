"""Contracts and loss helpers for Grounding DINO domain-retention training."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .grounding_dino_finetune import ValidationResult

TRAINABLE_PREFIXES = (
    "model.decoder.",
    "model.query_position_embeddings.",
    "model.encoder_output_bbox_embed.",
    "model.enc_output.",
    "model.enc_output_norm.",
)
LAST_SWIN_STAGE_PREFIX = "model.backbone.conv_encoder.model.encoder.layers.3."
_FROZEN_BACKBONE_PREFIXES = ("model.backbone.", "model.text_backbone.")


@dataclass(frozen=True, slots=True)
class DistillationLosses:
    token_logits: Any
    candidate_boxes: Any
    candidate_count: int


@dataclass(frozen=True, slots=True)
class JointThresholdSelection:
    near: ValidationResult
    real: ValidationResult
    harmonic_f1: float


def _parameter_receipt(model: Any) -> dict[str, Any]:
    trainable_names = []
    frozen_names = []
    trainable_numel = 0
    frozen_numel = 0
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            trainable_names.append(name)
            trainable_numel += parameter.numel()
        else:
            frozen_names.append(name)
            frozen_numel += parameter.numel()
    return {
        "trainable_parameter_names": sorted(trainable_names),
        "frozen_parameter_names": sorted(frozen_names),
        "trainable_numel": trainable_numel,
        "frozen_numel": frozen_numel,
        "total_numel": trainable_numel + frozen_numel,
    }


def _configure_trainability(model: Any, prefixes: tuple[str, ...]) -> dict[str, Any]:
    names = []
    prefix_hits = {prefix: 0 for prefix in prefixes}
    frozen_backbone_hits = {prefix: 0 for prefix in _FROZEN_BACKBONE_PREFIXES}
    for name, parameter in model.named_parameters():
        names.append(name)
        trainable = False
        for prefix in prefixes:
            if name.startswith(prefix):
                trainable = True
                prefix_hits[prefix] += 1
        for prefix in _FROZEN_BACKBONE_PREFIXES:
            if name.startswith(prefix):
                frozen_backbone_hits[prefix] += 1
        parameter.requires_grad = trainable
    if not names or any(count == 0 for count in prefix_hits.values()):
        raise RuntimeError("TRAINABLE_ALLOWLIST_MODEL_MISMATCH")
    if any(count == 0 for count in frozen_backbone_hits.values()):
        raise RuntimeError("FROZEN_BACKBONE_MODEL_MISMATCH")
    receipt = _parameter_receipt(model)
    receipt["trainable_prefixes"] = list(prefixes)
    receipt["prefix_parameter_counts"] = prefix_hits
    receipt["frozen_backbone_parameter_counts"] = frozen_backbone_hits
    return receipt


def configure_student_trainability(model: Any) -> dict[str, Any]:
    """Freeze every student parameter outside the exact decoder/query/head allowlist."""

    return _configure_trainability(model, TRAINABLE_PREFIXES)


def configure_last_stage_trainability(model: Any) -> dict[str, Any]:
    """Open only the final Swin stage in addition to the frozen-phase heads."""

    return _configure_trainability(model, (*TRAINABLE_PREFIXES, LAST_SWIN_STAGE_PREFIX))


def optimizer_parameter_groups(
    model: Any, *, head_learning_rate: float, backbone_learning_rate: float
) -> list[dict[str, Any]]:
    if (
        not math.isclose(head_learning_rate, 0.000002)
        or not math.isclose(backbone_learning_rate, head_learning_rate / 10.0)
    ):
        raise RuntimeError("LAST_STAGE_LEARNING_RATE_INVALID")
    head = []
    backbone = []
    unexpected = []
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if name.startswith(LAST_SWIN_STAGE_PREFIX):
            backbone.append(parameter)
        elif any(name.startswith(prefix) for prefix in TRAINABLE_PREFIXES):
            head.append(parameter)
        else:
            unexpected.append(name)
    if unexpected or not head or not backbone:
        raise RuntimeError("LAST_STAGE_OPTIMIZER_GROUP_INVALID")
    return [
        {"params": head, "lr": head_learning_rate},
        {"params": backbone, "lr": backbone_learning_rate},
    ]


def freeze_teacher(model: Any) -> dict[str, Any]:
    for parameter in model.parameters():
        parameter.requires_grad = False
    model.eval()
    receipt = _parameter_receipt(model)
    if receipt["trainable_numel"] != 0:
        raise RuntimeError("TEACHER_FREEZE_FAILED")
    return receipt


def compute_distillation_losses(
    *,
    student_logits: Any,
    student_boxes: Any,
    teacher_logits: Any,
    teacher_boxes: Any,
    attention_mask: Any,
    candidate_threshold: float,
    topk_fallback: int,
) -> DistillationLosses:
    import torch
    import torch.nn.functional as functional

    if (
        student_logits.shape != teacher_logits.shape
        or student_boxes.shape != teacher_boxes.shape
        or student_logits.ndim != 3
        or student_boxes.ndim != 3
        or student_boxes.shape[-1] != 4
        or attention_mask.ndim != 2
        or attention_mask.shape[0] != student_logits.shape[0]
        or attention_mask.shape[1] > student_logits.shape[2]
        or not 0.0 < candidate_threshold < 1.0
        or type(topk_fallback) is not int
        or topk_fallback <= 0
    ):
        raise RuntimeError("DISTILLATION_INPUT_INVALID")
    token_count = attention_mask.shape[1]
    active = attention_mask.to(device=student_logits.device, dtype=torch.bool)
    active = active[:, None, :].expand(-1, student_logits.shape[1], -1)
    student_active = student_logits[:, :, :token_count][active]
    teacher_active = teacher_logits[:, :, :token_count].to(student_logits.device)[active]
    if (
        student_active.numel() == 0
        or not torch.isfinite(student_active).all()
        or not torch.isfinite(teacher_active).all()
        or not torch.isfinite(student_boxes).all()
        or not torch.isfinite(teacher_boxes).all()
    ):
        raise RuntimeError("DISTILLATION_NONFINITE")
    token_loss = functional.mse_loss(student_active, teacher_active)
    teacher_slice = teacher_logits[:, :, :token_count].to(student_logits.device)
    confidence = teacher_slice.sigmoid().masked_fill(~active, 0.0).amax(dim=-1)
    candidates = confidence >= candidate_threshold
    if not bool(candidates.any()):
        count = min(topk_fallback, confidence.numel())
        flat_indices = confidence.flatten().topk(count, sorted=False).indices
        candidates = torch.zeros_like(confidence, dtype=torch.bool).flatten()
        candidates[flat_indices] = True
        candidates = candidates.reshape_as(confidence)
    candidate_count = int(candidates.sum().item())
    box_loss = functional.smooth_l1_loss(
        student_boxes[candidates], teacher_boxes.to(student_boxes.device)[candidates]
    )
    return DistillationLosses(
        token_logits=token_loss,
        candidate_boxes=box_loss,
        candidate_count=candidate_count,
    )


def _harmonic_mean(left: float, right: float) -> float:
    return 0.0 if left <= 0.0 or right <= 0.0 else 2.0 * left * right / (left + right)


def select_joint_threshold(
    near_results: Iterable[ValidationResult], real_results: Iterable[ValidationResult]
) -> JointThresholdSelection:
    near_by_threshold = {
        (result.box_threshold, result.text_threshold): result for result in near_results
    }
    real_by_threshold = {
        (result.box_threshold, result.text_threshold): result for result in real_results
    }
    if not near_by_threshold or set(near_by_threshold) != set(real_by_threshold):
        raise ValueError("JOINT_THRESHOLD_GRID_MISMATCH")

    def rank(threshold: tuple[float, float]) -> tuple[float, ...]:
        near = near_by_threshold[threshold]
        real = real_by_threshold[threshold]
        return (
            _harmonic_mean(near.f1, real.f1),
            min(near.recall, real.recall),
            _harmonic_mean(near.recall, real.recall),
            near.f1,
            real.f1,
            -float(near.fp + real.fp),
            threshold[0],
            threshold[1],
        )

    selected_threshold = max(near_by_threshold, key=rank)
    near = near_by_threshold[selected_threshold]
    real = real_by_threshold[selected_threshold]
    return JointThresholdSelection(
        near=near,
        real=real,
        harmonic_f1=_harmonic_mean(near.f1, real.f1),
    )


def _first_matching(samples: tuple[Any, ...], predicate: Any, label: str) -> Any:
    try:
        return next(sample for sample in samples if predicate(sample))
    except StopIteration as error:
        raise RuntimeError(f"SMOKE_SUBSET_INCOMPLETE:{label}") from error


def select_smoke_samples(
    train_samples: tuple[Any, ...],
    near_val_samples: tuple[Any, ...],
    real_val_samples: tuple[Any, ...],
) -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]:
    train = (
        _first_matching(
            train_samples,
            lambda sample: sample.domain_role == "near_synthetic"
            and sample.scenario == "one_cup_distractors",
            "near-one",
        ),
        _first_matching(
            train_samples,
            lambda sample: sample.domain_role == "near_synthetic"
            and sample.scenario == "partially_occluded_cup",
            "near-occluded",
        ),
        _first_matching(
            train_samples,
            lambda sample: sample.domain_role == "real_train" and len(sample.boxes) == 1,
            "real-single",
        ),
        _first_matching(
            train_samples,
            lambda sample: sample.domain_role == "real_train" and len(sample.boxes) >= 2,
            "real-multi",
        ),
        _first_matching(
            train_samples, lambda sample: sample.domain_role == "generic", "generic"
        ),
        _first_matching(
            train_samples,
            lambda sample: sample.domain_role == "hard_negative",
            "hard-negative",
        ),
    )
    near = tuple(
        _first_matching(
            near_val_samples,
            lambda sample, scenario=scenario: sample.scenario == scenario,
            f"near-val-{scenario}",
        )
        for scenario in ("one_cup_distractors", "two_cups", "partially_occluded_cup")
    )
    real_single = _first_matching(
        real_val_samples, lambda sample: len(sample.boxes) == 1, "real-val-single"
    )
    real_multi = _first_matching(
        real_val_samples, lambda sample: len(sample.boxes) >= 2, "real-val-multi"
    )
    real_third = _first_matching(
        real_val_samples,
        lambda sample: sample is not real_single and sample is not real_multi,
        "real-val-third",
    )
    return train, near, (real_single, real_multi, real_third)


def validate_domain_retention_contract(contract: dict[str, Any]) -> None:
    try:
        model = contract["model"]
        training = contract["training"]
        validation = contract["validation"]
        initialization = training["initialization"]
        common_valid = (
            model["model_id"] == "IDEA-Research/grounding-dino-tiny"
            and model["revision"] == "a2bb814dd30d776dcf7e30523b00659f4f141c71"
            and training["resume_checkpoint"] is None
            and math.isclose(training["learning_rate"], 0.000002)
            and math.isclose(training["teacher_token_logit_lambda"], 1.0)
            and math.isclose(training["teacher_candidate_box_lambda"], 1.0)
            and 0.0 < training["teacher_candidate_threshold"] < 1.0
            and type(training["teacher_candidate_topk_fallback"]) is int
            and training["teacher_candidate_topk_fallback"] > 0
            and validation["streams"]
            == ["near_synthetic", "real", "dino_only_raw_candidates"]
            and validation["checkpoint_selection"] == "joint_harmonic_f1"
        )
        if initialization == "official_base_teacher_and_student":
            phase_valid = (
                2 <= training["epochs"] <= 3
                and tuple(training["trainable_prefixes"]) == TRAINABLE_PREFIXES
                and "backbone_learning_rate" not in training
                and "student_initialization_checkpoint_manifest_sha256" not in training
            )
        elif initialization == "selected_phase1_student_official_base_teacher":
            checkpoint_sha = training["student_initialization_checkpoint_manifest_sha256"]
            model_sha = training["student_initialization_model_sha256"]
            phase_valid = (
                1 <= training["epochs"] <= 2
                and math.isclose(
                    training["backbone_learning_rate"], training["learning_rate"] / 10.0
                )
                and tuple(training["trainable_prefixes"])
                == (*TRAINABLE_PREFIXES, LAST_SWIN_STAGE_PREFIX)
                and isinstance(checkpoint_sha, str)
                and len(checkpoint_sha) == 64
                and all(character in "0123456789abcdef" for character in checkpoint_sha)
                and isinstance(model_sha, str)
                and len(model_sha) == 64
                and all(character in "0123456789abcdef" for character in model_sha)
                and training["student_initialization_completed_epoch"] == 2
            )
        else:
            phase_valid = False
        valid = common_valid and phase_valid
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RuntimeError("DOMAIN_RETENTION_CONTRACT_INVALID")
