"""Fixed five-epoch, CUDA-only SAM decoder adaptation with immutable evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .grounding_dino_finetune import (
    checkpoint_file_entries,
    exclusive_json,
    verify_complete_checkpoint,
)


def _freeze_tree(root: Path) -> None:
    for member in root.rglob("*"):
        if member.is_file():
            with member.open("rb") as stream:
                os.fsync(stream.fileno())
            member.chmod(0o444)
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        directory.chmod(0o555)
    root.chmod(0o555)


def save_epoch_checkpoint(
    root: Path,
    *,
    epoch: int,
    identity: Mapping[str, str],
    export_model: Callable[[Path], None],
    training_state: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> Any:
    """Mark complete only after an exclusive model/state export and inventory."""
    import torch

    if type(epoch) is not int or epoch < 1:
        raise ValueError("CHECKPOINT_EPOCH_INVALID")
    root = Path(root)
    root.mkdir(mode=0o700)
    export_model(root / "model")
    with (root / "training-state.pt").open("xb") as stream:
        torch.save(dict(training_state), stream)
        stream.flush()
        os.fsync(stream.fileno())
    exclusive_json(root / "epoch-receipt.json", dict(receipt))
    exclusive_json(root / "checkpoint-manifest.json", {
        "schema_version": 1,
        "complete": True,
        "completed_epoch": epoch,
        "identity": dict(identity),
        "files": checkpoint_file_entries(root),
    })
    verified = verify_complete_checkpoint(root, expected_identity=identity)
    _freeze_tree(root)
    return verified


def _state_hashes(model: Any) -> dict[str, str]:
    return {
        name: hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
        for name, value in model.state_dict().items()
    }


def _require_loading_keys(info: Mapping[str, Any]) -> None:
    if any(info.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
        raise ValueError("MODEL_STATE_BINDING_INVALID")


def prepare_training_frame(processor: Any, image: Any, sample: Any, *, epoch: int) -> tuple[Any, Any, list]:
    """Keep SAM processor's nested-list box contract and original truth grid."""
    import numpy as np

    from .sam_decoder_training import jitter_training_box

    width, height = image.size
    boxes = [list(jitter_training_box(
        tuple(item["absolute_xyxy"]), width=width, height=height,
        epoch=epoch, sample_seed=sample.seed, instance_index=instance,
    )) for instance, item in enumerate(sample.truths)]
    prepared = processor(images=image, input_boxes=[boxes], return_tensors="pt")
    truth = np.stack([np.asarray(item["mask"], dtype=np.float32) for item in sample.truths])
    return prepared, truth, boxes


def run_training(*, output_root: Path, source_commit: str, inputs: Mapping[str, str]) -> dict[str, Any]:
    """Train from verified original weights; no validation or sealed split access."""
    root = Path(output_root)
    if os.path.lexists(root):
        raise ValueError("OUTPUT_ROOT_COLLISION")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("SOURCE_COMMIT_INVALID")
    if not root.is_absolute() or root.resolve() != root or not root.parent.is_dir():
        raise ValueError("OUTPUT_ROOT_INVALID")
    repository = Path(__file__).resolve().parents[4]
    actual_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    if actual_commit != source_commit or subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "src/so101_demo_py"],
        cwd=repository, check=False,
    ).returncode:
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    required = {
        "train_inventory_path", "train_inventory_sha256", "source_root",
        "source_manifest_sha256", "base_bundle_root", "base_manifest_sha256",
    }
    if set(inputs) != required:
        raise ValueError("TRAINING_INPUTS_INVALID")
    if any(os.environ.get(key) != "1" for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise ValueError("OFFLINE_RUNTIME_REQUIRED")

    import numpy as np
    import torch
    from PIL import Image
    from transformers import Sam2Model, Sam2Processor

    from ..adapters.perception.model_bundle import verify_model_bundle
    from .grounded_sam_val_calibration import load_locked_train_dataset
    from .sam_decoder_training import (
        configure_decoder_training,
        decoder_loss,
    )

    if not torch.cuda.is_available():
        raise ValueError("CUDA_REQUIRED")
    seed = 430000079
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    dataset = load_locked_train_dataset(
        inventory_path=Path(inputs["train_inventory_path"]),
        expected_inventory_sha256=inputs["train_inventory_sha256"],
        source_root=Path(inputs["source_root"]),
        expected_source_manifest_sha256=inputs["source_manifest_sha256"],
    )
    if (
        len(dataset.samples) != 1200
        or {sample.seed for sample in dataset.samples} != set(range(410000000, 410001200))
    ):
        raise ValueError("TRAINING_DENOMINATOR_INVALID")
    active = [sample for sample in dataset.samples if sample.truths]
    if len(active) != 1000 or sum(len(s.truths) for s in active) != 1200:
        raise ValueError("TRAINING_DENOMINATOR_INVALID")
    bundle = verify_model_bundle(Path(inputs["base_bundle_root"]), inputs["base_manifest_sha256"])
    if bundle.prompt != "cup." or bundle.target_class_id != "cup":
        raise ValueError("MODEL_CLASS_INVALID")
    processor = Sam2Processor.from_pretrained(bundle.segmenter_dir, local_files_only=True)
    model, loading = Sam2Model.from_pretrained(
        bundle.segmenter_dir, local_files_only=True, output_loading_info=True
    )
    _require_loading_keys(loading)
    model = model.to("cuda").float()
    if any(p.device.type != "cuda" for p in model.parameters()):
        raise ValueError("CUDA_REQUIRED")
    parameters = configure_decoder_training(model)
    baseline = _state_hashes(model)
    optimizer = torch.optim.AdamW(parameters, lr=0.00001, weight_decay=0.01)
    identity = {
        "source_commit": source_commit,
        "base_manifest_sha256": inputs["base_manifest_sha256"],
        "train_inventory_sha256": inputs["train_inventory_sha256"],
        "source_manifest_sha256": inputs["source_manifest_sha256"],
        "recipe": "CP-170-CP-180-CP-184-five-epoch-decoder-only",
    }
    root.mkdir(mode=0o700)
    exclusive_json(root / "training-contract.json", {
        "identity": identity, "inputs": dict(inputs), "epochs": 5,
        "seed": seed, "learning_rate": 0.00001, "weight_decay": 0.01,
        "gradient_clip_norm": 1.0, "optimizer": "AdamW", "dtype": "float32",
        "multimask_output": True, "batch_size_images": 1,
        "train_images": 1200, "prompted_images_per_epoch": 1000,
        "instances_per_epoch": 1200, "validation_access": "none",
    })
    started = time.monotonic()
    epoch_reports = []
    for epoch in range(1, 6):
        order = np.random.default_rng(np.random.SeedSequence([seed, epoch, 0])).permutation(len(active))
        losses = []
        epoch_started = time.monotonic()
        with (root / f"epoch-{epoch}-steps.jsonl").open("x", encoding="utf-8") as log:
            for ordinal, index in enumerate(order, start=1):
                sample = active[int(index)]
                if hashlib.sha256(sample.image_path.read_bytes()).hexdigest() != sample.image_sha256:
                    raise ValueError("IMAGE_SHA256_MISMATCH")
                with Image.open(sample.image_path) as opened:
                    image = opened.convert("RGB")
                prepared, truth_array, boxes = prepare_training_frame(processor, image, sample, epoch=epoch)
                truth = torch.from_numpy(truth_array).to("cuda")[None]
                optimizer.zero_grad(set_to_none=True)
                output = model(
                    pixel_values=prepared["pixel_values"].to("cuda").float(),
                    input_boxes=prepared["input_boxes"].to("cuda").float(),
                    multimask_output=True,
                )
                loss = decoder_loss(output.pred_masks, output.iou_scores, truth)
                if not torch.isfinite(loss).item():
                    raise ValueError("NONFINITE_TRAINING_LOSS")
                loss.backward()
                if any(p.grad is not None for name, p in model.named_parameters() if not name.startswith("mask_decoder.")):
                    raise ValueError("FROZEN_GRADIENT_INVALID")
                norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
                optimizer.step()
                scalar = float(loss.detach())
                losses.append(scalar)
                log.write(json.dumps({
                    "epoch": epoch, "step": ordinal, "seed": sample.seed,
                    "boxes": boxes, "loss": scalar, "gradient_norm": float(norm),
                }, sort_keys=True) + "\n")
                if ordinal % 100 == 0:
                    log.flush()
                    os.fsync(log.fileno())
                    print(json.dumps({"epoch": epoch, "step": ordinal, "loss_mean": float(np.mean(losses))}), flush=True)
            log.flush()
            os.fsync(log.fileno())
        current = _state_hashes(model)
        if any(current[name] != value for name, value in baseline.items() if not name.startswith("mask_decoder.")):
            raise ValueError("FROZEN_STATE_CHANGED")
        if not any(current[name] != baseline[name] for name in current if name.startswith("mask_decoder.")):
            raise ValueError("DECODER_NOT_UPDATED")

        def export_model(directory: Path) -> None:
            model.save_pretrained(directory, safe_serialization=True)
            processor.save_pretrained(directory)
            reloaded, info = Sam2Model.from_pretrained(directory, local_files_only=True, output_loading_info=True)
            _require_loading_keys(info)
            if _state_hashes(reloaded) != current:
                raise ValueError("RELOADED_STATE_MISMATCH")

        receipt = {
            "epoch": epoch, "steps": len(losses), "loss_mean": float(np.mean(losses)),
            "loss_first": losses[0], "loss_last": losses[-1],
            "order_seeds": [active[int(i)].seed for i in order],
            "frozen_state_unchanged": True, "state_hashes": current,
            "epoch_seconds_before_export": time.monotonic() - epoch_started,
        }
        checkpoint = save_epoch_checkpoint(
            root / f"epoch-{epoch}", epoch=epoch, identity=identity,
            export_model=export_model,
            training_state={
                "optimizer": optimizer.state_dict(), "seed": seed, "epoch": epoch,
                "torch_rng_state": torch.get_rng_state(), "cuda_rng_state": torch.cuda.get_rng_state_all(),
            }, receipt=receipt,
        )
        epoch_reports.append({
            "epoch": epoch, "steps": len(losses), "loss_mean": float(np.mean(losses)),
            "checkpoint_manifest_sha256": checkpoint.manifest_sha256,
        })
        print(json.dumps({"checkpoint_complete": epoch_reports[-1]}, sort_keys=True), flush=True)
    report = {
        "status": "VALID_TRAINING_COMPLETE_PENDING_VAL_SELECTION", "candidate": False,
        "identity": identity, "epochs": epoch_reports, "optimizer_steps": 5000,
        "device": "cuda", "cpu_fallback": False, "elapsed_seconds": time.monotonic() - started,
        "peak_cuda_bytes": torch.cuda.max_memory_allocated(),
        "sealed_access": {"val": "none", "test": "none", "coco100": "none", "pickplace": "none", "mac": "none"},
    }
    exclusive_json(root / "training-report.json", report)
    _freeze_tree(root)
    return report
