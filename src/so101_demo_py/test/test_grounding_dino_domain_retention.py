from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch
from so101_demo.training.grounding_dino_domain_retention import (
    LAST_SWIN_STAGE_PREFIX,
    TRAINABLE_PREFIXES,
    compute_distillation_losses,
    configure_last_stage_trainability,
    configure_student_trainability,
    freeze_teacher,
    optimizer_parameter_groups,
    select_joint_threshold,
    select_smoke_samples,
    validate_domain_retention_contract,
)
from so101_demo.training.grounding_dino_finetune import ValidationResult


class _Parameter:
    def __init__(self, elements: int) -> None:
        self.requires_grad = True
        self._elements = elements

    def numel(self) -> int:
        return self._elements


class _Model:
    def __init__(self) -> None:
        self.training = True
        self.parameters_by_name = {
            "model.backbone.conv_encoder.model.encoder.layers.2.weight": _Parameter(11),
            "model.backbone.conv_encoder.model.encoder.layers.3.weight": _Parameter(12),
            "model.text_backbone.encoder.weight": _Parameter(13),
            "model.encoder.layers.0.weight": _Parameter(17),
            "model.decoder.layers.0.weight": _Parameter(19),
            "model.query_position_embeddings.weight": _Parameter(23),
            "model.encoder_output_bbox_embed.layers.0.weight": _Parameter(29),
            "model.enc_output.weight": _Parameter(31),
            "model.enc_output_norm.weight": _Parameter(37),
            "model.input_proj_vision.0.weight": _Parameter(41),
        }

    def named_parameters(self):
        return self.parameters_by_name.items()

    def parameters(self):
        return self.parameters_by_name.values()

    def eval(self):
        self.training = False
        return self


def test_trainability_is_an_exact_allowlist_and_teacher_is_fully_frozen() -> None:
    student = _Model()
    receipt = configure_student_trainability(student)

    expected_trainable = {
        name
        for name in student.parameters_by_name
        if any(name.startswith(prefix) for prefix in TRAINABLE_PREFIXES)
    }
    assert set(receipt["trainable_parameter_names"]) == expected_trainable
    assert receipt["trainable_numel"] == sum(
        student.parameters_by_name[name].numel() for name in expected_trainable
    )
    assert all(
        parameter.requires_grad == (name in expected_trainable)
        for name, parameter in student.named_parameters()
    )
    assert not student.parameters_by_name[
        "model.backbone.conv_encoder.model.encoder.layers.3.weight"
    ].requires_grad
    assert not student.parameters_by_name["model.text_backbone.encoder.weight"].requires_grad
    assert not student.parameters_by_name["model.encoder.layers.0.weight"].requires_grad

    teacher = _Model()
    teacher_receipt = freeze_teacher(teacher)
    assert teacher.training is False
    assert teacher_receipt["trainable_numel"] == 0
    assert all(not parameter.requires_grad for parameter in teacher.parameters())


def test_last_stage_trainability_and_optimizer_groups_are_exact() -> None:
    student = _Model()

    receipt = configure_last_stage_trainability(student)
    groups = optimizer_parameter_groups(
        student, head_learning_rate=0.000002, backbone_learning_rate=0.0000002
    )

    expected = {
        name
        for name in student.parameters_by_name
        if name.startswith(LAST_SWIN_STAGE_PREFIX)
        or any(name.startswith(prefix) for prefix in TRAINABLE_PREFIXES)
    }
    assert set(receipt["trainable_parameter_names"]) == expected
    assert student.parameters_by_name[
        "model.backbone.conv_encoder.model.encoder.layers.3.weight"
    ].requires_grad
    assert not student.parameters_by_name[
        "model.backbone.conv_encoder.model.encoder.layers.2.weight"
    ].requires_grad
    assert not student.parameters_by_name["model.text_backbone.encoder.weight"].requires_grad
    assert [group["lr"] for group in groups] == [0.000002, 0.0000002]
    assert groups[0]["params"] == [
        parameter
        for name, parameter in student.named_parameters()
        if any(name.startswith(prefix) for prefix in TRAINABLE_PREFIXES)
    ]
    assert groups[1]["params"] == [
        student.parameters_by_name[
            "model.backbone.conv_encoder.model.encoder.layers.3.weight"
        ]
    ]


def test_distillation_masks_inactive_tokens_and_uses_teacher_candidates() -> None:
    negative_infinity = float("-inf")
    teacher_logits = torch.tensor(
        [[[2.0, 0.0, negative_infinity, negative_infinity], [-4.0, -4.0, negative_infinity, negative_infinity]]]
    )
    student_logits = torch.tensor(
        [[[1.0, 0.5, negative_infinity, negative_infinity], [-3.0, -5.0, negative_infinity, negative_infinity]]],
        requires_grad=True,
    )
    teacher_boxes = torch.tensor([[[0.5, 0.5, 0.2, 0.2], [0.2, 0.2, 0.1, 0.1]]])
    student_boxes = torch.tensor(
        [[[0.4, 0.6, 0.3, 0.1], [0.8, 0.8, 0.4, 0.4]]], requires_grad=True
    )
    losses = compute_distillation_losses(
        student_logits=student_logits,
        student_boxes=student_boxes,
        teacher_logits=teacher_logits,
        teacher_boxes=teacher_boxes,
        attention_mask=torch.tensor([[1, 1, 0, 0]]),
        candidate_threshold=0.25,
        topk_fallback=1,
    )

    assert losses.candidate_count == 1
    assert losses.token_logits.item() == pytest.approx(0.8125)
    assert losses.candidate_boxes.item() > 0.0
    (losses.token_logits + losses.candidate_boxes).backward()
    assert torch.isfinite(student_logits.grad[:, :, :2]).all()
    assert torch.isfinite(student_boxes.grad).all()


def _metric(*, f1: float, recall: float, box: float = 0.25, text: float = 0.25):
    return ValidationResult(
        epoch=1,
        box_threshold=box,
        text_threshold=text,
        tp=1,
        fp=0,
        fn=0,
        precision=1.0,
        recall=recall,
        f1=f1,
        small_target_recall=recall,
        multi_cup_recall=recall,
    )


def test_joint_threshold_prefers_balanced_near_and_real_f1() -> None:
    near = [_metric(f1=1.0, recall=1.0), _metric(f1=0.8, recall=0.8, box=0.35, text=0.35)]
    real = [_metric(f1=0.2, recall=0.2), _metric(f1=0.8, recall=0.8, box=0.35, text=0.35)]

    selected = select_joint_threshold(near, real)

    assert selected.near.box_threshold == 0.35
    assert selected.real.text_threshold == 0.35
    assert selected.harmonic_f1 == pytest.approx(0.8)


def test_smoke_subset_is_six_train_plus_three_near_and_three_real() -> None:
    def sample(role: str | None, scenario: str, boxes: int):
        return SimpleNamespace(domain_role=role, scenario=scenario, boxes=(object(),) * boxes)

    train = (
        sample("near_synthetic", "one_cup_distractors", 1),
        sample("near_synthetic", "partially_occluded_cup", 1),
        sample("real_train", "one_cup_distractors", 1),
        sample("real_train", "two_cups", 2),
        sample("generic", "no_cup", 0),
        sample("hard_negative", "no_cup", 0),
    )
    near = (
        sample(None, "one_cup_distractors", 1),
        sample(None, "two_cups", 2),
        sample(None, "partially_occluded_cup", 1),
    )
    real = (
        sample("real_val", "one_cup_distractors", 1),
        sample("real_val", "two_cups", 2),
        sample("real_val", "one_cup_distractors", 1),
    )

    selected_train, selected_near, selected_real = select_smoke_samples(train, near, real)

    assert len(selected_train) == 6
    assert len(selected_near) == 3
    assert len(selected_real) == 3
    assert {sample.domain_role for sample in selected_train} == {
        "near_synthetic",
        "real_train",
        "generic",
        "hard_negative",
    }


def test_domain_retention_contract_rejects_epoch5_resume_or_wrong_recipe() -> None:
    contract = {
        "model": {
            "model_id": "IDEA-Research/grounding-dino-tiny",
            "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        },
        "training": {
            "initialization": "official_base_teacher_and_student",
            "resume_checkpoint": None,
            "learning_rate": 0.000002,
            "epochs": 3,
            "teacher_token_logit_lambda": 1.0,
            "teacher_candidate_box_lambda": 1.0,
            "teacher_candidate_threshold": 0.25,
            "teacher_candidate_topk_fallback": 16,
            "trainable_prefixes": list(TRAINABLE_PREFIXES),
        },
        "validation": {
            "streams": ["near_synthetic", "real", "dino_only_raw_candidates"],
            "checkpoint_selection": "joint_harmonic_f1",
        },
    }
    validate_domain_retention_contract(contract)

    for path, value in (
        (("training", "resume_checkpoint"), "/epoch-005"),
        (("training", "learning_rate"), 0.00001),
        (("training", "teacher_candidate_box_lambda"), 0.5),
        (("model", "revision"), "epoch-5"),
    ):
        changed = {key: dict(item) for key, item in contract.items()}
        changed[path[0]][path[1]] = value
        with pytest.raises(RuntimeError, match="DOMAIN_RETENTION_CONTRACT_INVALID"):
            validate_domain_retention_contract(changed)


def test_last_stage_contract_requires_new_phase_checkpoint_and_one_tenth_lr() -> None:
    contract = {
        "model": {
            "model_id": "IDEA-Research/grounding-dino-tiny",
            "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        },
        "training": {
            "initialization": "selected_phase1_student_official_base_teacher",
            "resume_checkpoint": None,
            "learning_rate": 0.000002,
            "backbone_learning_rate": 0.0000002,
            "epochs": 2,
            "teacher_token_logit_lambda": 1.0,
            "teacher_candidate_box_lambda": 1.0,
            "teacher_candidate_threshold": 0.25,
            "teacher_candidate_topk_fallback": 16,
            "trainable_prefixes": [*TRAINABLE_PREFIXES, LAST_SWIN_STAGE_PREFIX],
            "student_initialization_checkpoint_manifest_sha256": "a" * 64,
            "student_initialization_model_sha256": "b" * 64,
            "student_initialization_completed_epoch": 2,
        },
        "validation": {
            "streams": ["near_synthetic", "real", "dino_only_raw_candidates"],
            "checkpoint_selection": "joint_harmonic_f1",
        },
    }
    validate_domain_retention_contract(contract)

    selected_epoch_three = {key: dict(item) for key, item in contract.items()}
    selected_epoch_three["training"]["student_initialization_completed_epoch"] = 3
    validate_domain_retention_contract(selected_epoch_three)

    for field, value in (
        ("backbone_learning_rate", 0.000002),
        ("epochs", 3),
        ("student_initialization_checkpoint_manifest_sha256", "epoch-5"),
        ("student_initialization_completed_epoch", 5),
    ):
        changed = {key: dict(item) for key, item in contract.items()}
        changed["training"][field] = value
        with pytest.raises(RuntimeError, match="DOMAIN_RETENTION_CONTRACT_INVALID"):
            validate_domain_retention_contract(changed)
