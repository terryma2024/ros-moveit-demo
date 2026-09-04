from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from so101_demo.training.grounding_dino_finetune import (
    CheckpointError,
    TrainingDataError,
    ValidationResult,
    build_coco_annotation,
    load_verified_split,
    require_cuda,
    select_best_checkpoint,
    select_best_threshold,
    verify_complete_checkpoint,
)
from so101_demo.training.grounding_dino_runtime import (
    _validate_fresh_reload_statistics,
    enable_grounding_dino_gradient_checkpointing,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_inventory(tmp_path: Path, *, split: str = "train") -> tuple[Path, Path]:
    image_root = tmp_path / f"{split}-images"
    image_root.mkdir()
    image_path = image_root / "410000001.png"
    Image.new("RGB", (640, 480), (20, 40, 60)).save(image_path)
    document = {
        "schema_version": 1,
        "converter_commit": "2" * 40,
        "source_generator_commit": "1" * 40,
        "source_archive_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "source_mjcf_sha256": "c" * 64,
        "split": split,
        "class_name": "cup",
        "prompt": "cup.",
        "image_width": 640,
        "image_height": 480,
        "sample_count": 1,
        "samples": [
            {
                "seed": 410000001,
                "scenario": "one_cup_distractors",
                "configured_cup_count": 1,
                "visible_instance_count": 1,
                "image_relpath": f"images/{split}/410000001.png",
                "image_sha256": _sha256(image_path),
                "label_relpath": f"labels/{split}/410000001.txt",
                "label_sha256": "d" * 64,
                "truth_relpath": f"truth/{split}/410000001.json",
                "truth_sha256": "e" * 64,
                "boxes": [
                    {
                        "absolute_xyxy": [64.0, 48.0, 192.0, 144.0],
                        "normalized_xyxy": [0.1, 0.1, 0.3, 0.3],
                        "class_name": "cup",
                        "text": "cup.",
                        "visible_pixel_count": 4096,
                        "occlusion": None,
                    }
                ],
            }
        ],
    }
    inventory_path = tmp_path / f"{split}-inventory.json"
    inventory_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return inventory_path, image_root


def _load(tmp_path: Path):
    inventory, images = _write_inventory(tmp_path)
    return load_verified_split(
        inventory_path=inventory,
        image_root=images,
        expected_inventory_sha256=_sha256(inventory),
        expected_split="train",
        expected_sample_count=1,
        expected_source_archive_sha256="a" * 64,
        expected_source_manifest_sha256="b" * 64,
        expected_generator_commit="1" * 40,
        expected_converter_commit="2" * 40,
    )


def test_verified_split_confines_images_and_preserves_generic_cup_truth(
    tmp_path: Path,
) -> None:
    split = _load(tmp_path)

    assert split.name == "train"
    assert len(split.samples) == 1
    sample = split.samples[0]
    assert sample.image_path == (tmp_path / "train-images/410000001.png").resolve()
    assert sample.scenario == "one_cup_distractors"
    assert sample.boxes[0].absolute_xyxy == (64.0, 48.0, 192.0, 144.0)
    assert sample.boxes[0].normalized_xyxy == (0.1, 0.1, 0.3, 0.3)
    assert sample.boxes[0].class_name == "cup"
    assert sample.boxes[0].text == "cup."


def test_verified_split_rejects_tamper_and_test_or_path_escape(tmp_path: Path) -> None:
    inventory, images = _write_inventory(tmp_path)
    expected_sha = _sha256(inventory)
    document = json.loads(inventory.read_text(encoding="utf-8"))
    document["samples"][0]["image_relpath"] = "images/test/440000000.png"
    inventory.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(TrainingDataError, match="INVENTORY_SHA256_MISMATCH"):
        load_verified_split(
            inventory_path=inventory,
            image_root=images,
            expected_inventory_sha256=expected_sha,
            expected_split="train",
            expected_sample_count=1,
            expected_source_archive_sha256="a" * 64,
            expected_source_manifest_sha256="b" * 64,
            expected_generator_commit="1" * 40,
            expected_converter_commit="2" * 40,
        )

    inventory.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TrainingDataError, match="IMAGE_PATH_INVALID"):
        load_verified_split(
            inventory_path=inventory,
            image_root=images,
            expected_inventory_sha256=_sha256(inventory),
            expected_split="train",
            expected_sample_count=1,
            expected_source_archive_sha256="a" * 64,
            expected_source_manifest_sha256="b" * 64,
            expected_generator_commit="1" * 40,
            expected_converter_commit="2" * 40,
        )


def test_coco_annotation_converts_xyxy_and_supports_a_negative_target(
    tmp_path: Path,
) -> None:
    sample = _load(tmp_path).samples[0]

    positive = build_coco_annotation(sample, image_id=7)
    negative = build_coco_annotation(
        SimpleNamespace(boxes=()),
        image_id=8,
    )

    assert positive == {
        "image_id": 7,
        "annotations": [
            {
                "bbox": [64.0, 48.0, 128.0, 96.0],
                "area": 12288.0,
                "category_id": 0,
                "iscrowd": 0,
            }
        ],
    }
    assert negative == {"image_id": 8, "annotations": []}


def _result(
    *,
    epoch: int,
    f1: float,
    recall: float,
    small_recall: float,
    multi_cup_recall: float,
    fp: int,
    box_threshold: float,
    text_threshold: float,
) -> ValidationResult:
    return ValidationResult(
        epoch=epoch,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        tp=8,
        fp=fp,
        fn=2,
        precision=0.8,
        recall=recall,
        f1=f1,
        small_target_recall=small_recall,
        multi_cup_recall=multi_cup_recall,
    )


def test_threshold_and_checkpoint_selection_use_the_preregistered_order() -> None:
    lower_f1 = _result(
        epoch=1,
        f1=0.79,
        recall=0.99,
        small_recall=0.99,
        multi_cup_recall=0.99,
        fp=0,
        box_threshold=0.5,
        text_threshold=0.5,
    )
    lower_recall = _result(
        epoch=1,
        f1=0.8,
        recall=0.79,
        small_recall=0.99,
        multi_cup_recall=0.99,
        fp=0,
        box_threshold=0.5,
        text_threshold=0.5,
    )
    lower_small = _result(
        epoch=1,
        f1=0.8,
        recall=0.8,
        small_recall=0.79,
        multi_cup_recall=0.99,
        fp=0,
        box_threshold=0.5,
        text_threshold=0.5,
    )
    lower_multi = _result(
        epoch=1,
        f1=0.8,
        recall=0.8,
        small_recall=0.8,
        multi_cup_recall=0.79,
        fp=0,
        box_threshold=0.5,
        text_threshold=0.5,
    )
    more_fp = _result(
        epoch=1,
        f1=0.8,
        recall=0.8,
        small_recall=0.8,
        multi_cup_recall=0.8,
        fp=2,
        box_threshold=0.5,
        text_threshold=0.5,
    )
    winner = _result(
        epoch=1,
        f1=0.8,
        recall=0.8,
        small_recall=0.8,
        multi_cup_recall=0.8,
        fp=1,
        box_threshold=0.5,
        text_threshold=0.45,
    )
    lower_threshold = _result(
        epoch=1,
        f1=0.8,
        recall=0.8,
        small_recall=0.8,
        multi_cup_recall=0.8,
        fp=1,
        box_threshold=0.45,
        text_threshold=0.5,
    )

    assert (
        select_best_threshold(
            [lower_f1, lower_recall, lower_small, lower_multi, more_fp, lower_threshold, winner]
        )
        == winner
    )

    same_metrics_later = ValidationResult(**{**winner.as_dict(), "epoch": 2})
    assert select_best_checkpoint([same_metrics_later, winner]) == winner


def _write_complete_checkpoint(root: Path, identity: dict[str, str]) -> None:
    root.mkdir()
    weights = root / "model.safetensors"
    state = root / "training-state.pt"
    weights.write_bytes(b"weights")
    state.write_bytes(b"state")
    files = [
        {"path": path.name, "sha256": _sha256(path), "size": path.stat().st_size}
        for path in (weights, state)
    ]
    manifest = {
        "schema_version": 1,
        "complete": True,
        "completed_epoch": 1,
        "identity": identity,
        "files": files,
    }
    (root / "checkpoint-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_complete_checkpoint_is_exact_and_tamper_fails_closed(tmp_path: Path) -> None:
    identity = {
        "contract_sha256": "a" * 64,
        "base_model_sha256": "b" * 64,
        "train_inventory_sha256": "c" * 64,
        "val_inventory_sha256": "d" * 64,
    }
    checkpoint = tmp_path / "epoch-001"
    _write_complete_checkpoint(checkpoint, identity)

    verified = verify_complete_checkpoint(checkpoint, expected_identity=identity)
    assert verified.completed_epoch == 1
    assert verified.root == checkpoint.resolve()

    (checkpoint / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(CheckpointError, match="CHECKPOINT_FILE_MISMATCH"):
        verify_complete_checkpoint(checkpoint, expected_identity=identity)


def test_cuda_requirement_rejects_cpu_fallback() -> None:
    unavailable = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)
    )
    available = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1)
    )

    with pytest.raises(RuntimeError, match="CPU_FALLBACK_FORBIDDEN"):
        require_cuda(unavailable)
    assert require_cuda(available) == "cuda:0"


def test_grounding_dino_decoder_layers_use_keyword_safe_checkpointing() -> None:
    class DecoderLayer:
        training = True

        def forward(
            self,
            hidden_states,
            position_embeddings=None,
            reference_points=None,
            spatial_shapes=None,
            spatial_shapes_list=None,
            level_start_index=None,
            vision_encoder_hidden_states=None,
            vision_encoder_attention_mask=None,
            text_encoder_hidden_states=None,
            text_encoder_attention_mask=None,
            self_attn_mask=None,
            output_attentions=False,
        ):
            return hidden_states, spatial_shapes_list, output_attentions

    layer = DecoderLayer()
    decoder = SimpleNamespace(gradient_checkpointing=True, layers=[layer])

    class GroundingDino:
        def __init__(self) -> None:
            self.model = SimpleNamespace(decoder=decoder)

        @property
        def is_gradient_checkpointing(self) -> bool:
            return any(
                getattr(module, "gradient_checkpointing", False)
                for module in self.model.decoder.layers
            )

    checkpoint_calls = []

    def checkpoint(function, *args, use_reentrant, **kwargs):
        checkpoint_calls.append((use_reentrant, kwargs.copy()))
        return function(*args, **kwargs)

    model = GroundingDino()
    method = enable_grounding_dino_gradient_checkpointing(model, checkpoint_function=checkpoint)

    assert method == "so101-grounding-dino-layer-keyword-non-reentrant"
    assert model.model.decoder.gradient_checkpointing is False
    assert layer.gradient_checkpointing is True
    assert model.is_gradient_checkpointing is True
    assert layer.forward("hidden", spatial_shapes_list="shapes", output_attentions=True) == (
        "hidden",
        "shapes",
        True,
    )
    assert checkpoint_calls == [
        (False, {"spatial_shapes_list": "shapes", "output_attentions": True})
    ]

    incomplete = SimpleNamespace(
        model=SimpleNamespace(decoder=SimpleNamespace(gradient_checkpointing=True))
    )
    with pytest.raises(RuntimeError, match="GRADIENT_CHECKPOINTING_UNSUPPORTED"):
        enable_grounding_dino_gradient_checkpointing(incomplete, checkpoint_function=checkpoint)


def test_fresh_reload_accepts_only_masked_negative_infinity() -> None:
    valid = {
        "device_type": "cuda",
        "active_token_count": 4,
        "active_logits_finite": True,
        "logits_nan_count": 0,
        "logits_posinf_count": 0,
        "logits_neginf_count": 226800,
        "inactive_logits_neginf_count": 226800,
        "pred_boxes_finite": True,
    }

    _validate_fresh_reload_statistics(**valid)

    invalid_overrides = (
        {"device_type": "cpu"},
        {"active_token_count": 0},
        {"active_logits_finite": False},
        {"logits_nan_count": 1},
        {"logits_posinf_count": 1},
        {"logits_neginf_count": 226801},
        {"inactive_logits_neginf_count": 226799},
        {"pred_boxes_finite": False},
    )
    for override in invalid_overrides:
        with pytest.raises(RuntimeError, match="FRESH_RELOAD_INFERENCE_INVALID"):
            _validate_fresh_reload_statistics(**{**valid, **override})
