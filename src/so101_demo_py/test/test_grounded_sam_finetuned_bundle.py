from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import so101_demo.adapters.perception.model_bundle as model_bundle
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.adapters.perception.model_runtime import ModelSetupError

BASE_MANIFEST_SHA256 = "b" * 64
CHECKPOINT_IDENTITY = {
    "base_model_sha256": "1" * 64,
    "contract_sha256": "2" * 64,
    "train_inventory_sha256": "3" * 64,
    "training_commit": "4" * 40,
    "val_inventory_sha256": "5" * 64,
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(document: object) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _compose(**kwargs: object) -> str:
    compose = getattr(model_bundle, "compose_finetuned_model_bundle", None)
    assert callable(compose), "fine-tuned bundle composition is not implemented"
    return compose(**kwargs)


def _compose_adapted(**kwargs: object) -> str:
    compose = getattr(model_bundle, "compose_adapted_model_bundle", None)
    assert callable(compose), "adapted Grounded-SAM bundle composition is not implemented"
    return compose(**kwargs)


def _source_bundle(root: Path) -> tuple[Path, str]:
    detector = root / "grounding-dino-tiny"
    segmenter = root / "sam2.1-hiera-tiny"
    detector.mkdir(parents=True)
    segmenter.mkdir()
    (detector / "config.json").write_bytes(b"base-detector")
    (segmenter / "config.json").write_bytes(b"sam-config")
    (segmenter / "model.safetensors").write_bytes(b"frozen-sam")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": _sha256(path.read_bytes()),
                    "size": path.stat().st_size,
                }
            )
    document = {
        "dependencies": {
            "Pillow": "12.3.0",
            "PyYAML": "6.0.2",
            "huggingface-hub": "0.34.4",
            "mujoco": "3.12.0",
            "safetensors": "0.6.2",
            "scipy": "1.17.1",
            "tokenizers": "0.22.0",
            "torch": "2.13.0",
            "torchvision": "0.28.0",
            "transformers": "4.56.2",
            "ultralytics": "8.4.115",
        },
        "files": files,
        "models": {
            "detector": {
                "directory": "grounding-dino-tiny",
                "model_id": "IDEA-Research/grounding-dino-tiny",
                "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
            },
            "segmenter": {
                "directory": "sam2.1-hiera-tiny",
                "model_id": "facebook/sam2.1-hiera-tiny",
                "revision": "de431c4043854a71d8101e17995dfe596bf101a5",
            },
        },
        "pipeline_id": "grounding-dino-tiny+sam2.1-hiera-tiny",
        "prompt_profile": {"plastic_cup": "plastic cup."},
        "schema_version": 1,
    }
    payload = _canonical(document)
    (root / "manifest.json").write_bytes(payload)
    return root, _sha256(payload)


def _checkpoint(root: Path) -> tuple[Path, str]:
    root.mkdir()
    payloads = {
        "config.json": b"fine-config",
        "model.safetensors": b"fine-weights",
        "preprocessor_config.json": b"fine-processor",
        "special_tokens_map.json": b"special-tokens",
        "tokenizer.json": b"tokenizer",
        "tokenizer_config.json": b"tokenizer-config",
        "training-state.pt": b"optimizer-must-not-ship",
        "vocab.txt": b"vocabulary",
    }
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    files = [
        {
            "path": name,
            "sha256": _sha256(payload),
            "size": len(payload),
        }
        for name, payload in sorted(payloads.items())
    ]
    document = {
        "complete": True,
        "completed_epoch": 7,
        "files": files,
        "identity": CHECKPOINT_IDENTITY,
        "schema_version": 1,
        "selected_val_metrics": {
            "box_threshold": 0.25,
            "epoch": 7,
            "f1": 0.85,
            "fn": 3,
            "fp": 2,
            "multi_cup_recall": 0.8,
            "precision": 0.84,
            "recall": 0.86,
            "small_target_recall": 0.78,
            "text_threshold": 0.25,
            "tp": 17,
        },
    }
    payload = _canonical(document)
    (root / "checkpoint-manifest.json").write_bytes(payload)
    return root, _sha256(payload)


def _sam_checkpoint(root: Path, source_manifest_sha256: str) -> tuple[Path, str, dict]:
    model = root / "model"
    model.mkdir(parents=True)
    payloads = {
        "epoch-receipt.json": b"sam-epoch-receipt",
        "model/config.json": b"adapted-sam-config",
        "model/model.safetensors": b"adapted-sam-weights",
        "model/preprocessor_config.json": b"adapted-sam-preprocessor",
        "model/processor_config.json": b"adapted-sam-processor",
        "training-state.pt": b"sam-optimizer-must-not-ship",
    }
    for name, payload in payloads.items():
        (root / name).write_bytes(payload)
    identity = {
        "base_manifest_sha256": source_manifest_sha256,
        "recipe": "decoder-only-five-epoch",
        "source_commit": "6" * 40,
        "source_manifest_sha256": "7" * 64,
        "train_inventory_sha256": "8" * 64,
    }
    document = {
        "complete": True,
        "completed_epoch": 4,
        "files": [
            {"path": name, "sha256": _sha256(payload), "size": len(payload)}
            for name, payload in sorted(payloads.items())
        ],
        "identity": identity,
        "schema_version": 1,
    }
    payload = _canonical(document)
    (root / "checkpoint-manifest.json").write_bytes(payload)
    return root, _sha256(payload), identity


def test_compose_finetuned_bundle_binds_generic_cup_and_excludes_training_state(
    tmp_path: Path,
) -> None:
    """Catch publishing a trained bundle with old prompt semantics or optimizer state."""

    source_root, source_sha = _source_bundle(tmp_path / "source-bundle")
    checkpoint, checkpoint_sha = _checkpoint(tmp_path / "checkpoint")
    destination = tmp_path / "fine-bundle"

    digest = _compose(
        checkpoint_root=checkpoint,
        expected_checkpoint_manifest_sha256=checkpoint_sha,
        source_bundle_root=source_root,
        expected_source_manifest_sha256=source_sha,
        destination=destination,
    )

    verified = verify_model_bundle(destination, digest)
    assert verified.target_class_id == "cup"
    assert verified.prompt == "cup."
    assert verified.manifest["schema_version"] == 2
    assert verified.manifest["models"]["detector"]["checkpoint_manifest_sha256"] == checkpoint_sha
    assert verified.manifest["models"]["detector"]["checkpoint_identity"] == CHECKPOINT_IDENTITY
    assert verified.manifest["models"]["segmenter"]["source_bundle_manifest_sha256"] == source_sha
    assert (verified.detector_dir / "model.safetensors").read_bytes() == b"fine-weights"
    assert (verified.segmenter_dir / "model.safetensors").read_bytes() == b"frozen-sam"
    assert not (verified.detector_dir / "training-state.pt").exists()
    assert not any(path.is_symlink() for path in destination.rglob("*"))


def test_compose_adapted_bundle_binds_both_checkpoints_and_excludes_training_state(
    tmp_path: Path,
) -> None:
    """Catch shipping adapted SAM bytes under frozen-snapshot provenance."""

    source_root, source_sha = _source_bundle(tmp_path / "source-bundle")
    detector, detector_sha = _checkpoint(tmp_path / "detector-checkpoint")
    segmenter, segmenter_sha, segmenter_identity = _sam_checkpoint(
        tmp_path / "segmenter-checkpoint", source_sha
    )
    destination = tmp_path / "adapted-bundle"

    digest = _compose_adapted(
        detector_checkpoint_root=detector,
        expected_detector_checkpoint_manifest_sha256=detector_sha,
        segmenter_checkpoint_root=segmenter,
        expected_segmenter_checkpoint_manifest_sha256=segmenter_sha,
        source_bundle_root=source_root,
        expected_source_manifest_sha256=source_sha,
        destination=destination,
    )

    verified = verify_model_bundle(destination, digest)
    assert verified.manifest["schema_version"] == 3
    assert verified.target_class_id == "cup"
    assert verified.prompt == "cup."
    assert verified.manifest["models"]["detector"]["checkpoint_manifest_sha256"] == detector_sha
    adapted = verified.manifest["models"]["segmenter"]
    assert adapted["artifact_kind"] == "decoder_only_checkpoint"
    assert adapted["checkpoint_manifest_sha256"] == segmenter_sha
    assert adapted["checkpoint_identity"] == segmenter_identity
    assert adapted["source_bundle_manifest_sha256"] == source_sha
    assert (verified.detector_dir / "model.safetensors").read_bytes() == b"fine-weights"
    assert (verified.segmenter_dir / "model.safetensors").read_bytes() == b"adapted-sam-weights"
    assert not any("training-state" in path.name for path in destination.rglob("*"))
    assert not any(path.is_symlink() for path in destination.rglob("*"))


def test_compose_finetuned_bundle_rejects_checkpoint_hash_before_destination_creation(
    tmp_path: Path,
) -> None:
    """Catch a changed checkpoint entering an immutable runtime bundle."""

    source_root, source_sha = _source_bundle(tmp_path / "source-bundle")
    checkpoint, _checkpoint_sha = _checkpoint(tmp_path / "checkpoint")
    destination = tmp_path / "fine-bundle"

    with pytest.raises(ValueError, match="checkpoint manifest SHA256"):
        _compose(
            checkpoint_root=checkpoint,
            expected_checkpoint_manifest_sha256="f" * 64,
            source_bundle_root=source_root,
            expected_source_manifest_sha256=source_sha,
            destination=destination,
        )

    assert not destination.exists()


def test_schema_v2_verifier_rejects_rehashed_non_generic_prompt(tmp_path: Path) -> None:
    """Catch a valid outer hash disguising prompt drift in a fine-tuned bundle."""

    source_root, source_sha = _source_bundle(tmp_path / "source-bundle")
    checkpoint, checkpoint_sha = _checkpoint(tmp_path / "checkpoint")
    destination = tmp_path / "fine-bundle"
    _compose(
        checkpoint_root=checkpoint,
        expected_checkpoint_manifest_sha256=checkpoint_sha,
        source_bundle_root=source_root,
        expected_source_manifest_sha256=source_sha,
        destination=destination,
    )
    document = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    document["prompt_profile"] = {"cup": "plastic cup."}
    payload = _canonical(document)
    (destination / "manifest.json").write_bytes(payload)

    with pytest.raises(ModelSetupError) as error:
        verify_model_bundle(destination, _sha256(payload))
    assert error.value.code == "MODEL_BUNDLE_INVALID"
