"""Epoch evidence must survive readback and reject partial or colliding writes."""

import importlib

import pytest
from so101_demo.training.grounding_dino_finetune import verify_complete_checkpoint


def runtime_api():
    spec = importlib.util.find_spec("so101_demo.training.sam_decoder_runtime")
    assert spec is not None, "SAM training runtime is not implemented"
    return importlib.import_module("so101_demo.training.sam_decoder_runtime")


def test_epoch_export_binds_model_optimizer_receipt_and_identity(tmp_path):
    torch = pytest.importorskip("torch")
    model = torch.nn.Linear(2, 1)
    optimizer = torch.optim.AdamW(model.parameters())
    model(torch.ones(1, 2)).sum().backward()
    optimizer.step()
    identity = {"source_commit": "a" * 40, "base_model": "b" * 64}

    def export(directory):
        directory.mkdir()
        torch.save(model.state_dict(), directory / "weights.pt")

    root = tmp_path / "epoch-1"
    receipt = runtime_api().save_epoch_checkpoint(
        root, epoch=1, identity=identity, export_model=export,
        training_state={"optimizer": optimizer.state_dict(), "seed": 430000079},
        receipt={"loss_mean": 0.25, "order": [2, 1, 0]},
    )
    verified = verify_complete_checkpoint(root, expected_identity=identity)
    assert verified.completed_epoch == 1
    assert verified.manifest_sha256 == receipt.manifest_sha256
    restored = torch.load(root / "model/weights.pt", weights_only=True)
    assert torch.equal(restored["weight"], model.weight)
    state = torch.load(root / "training-state.pt", weights_only=True)
    assert state["seed"] == 430000079
    assert state["optimizer"]["state"]
    with pytest.raises(FileExistsError):
        runtime_api().save_epoch_checkpoint(
            root, epoch=2, identity=identity, export_model=export,
            training_state={}, receipt={},
        )
    assert verify_complete_checkpoint(root, expected_identity=identity).completed_epoch == 1


def test_export_failure_never_marks_checkpoint_complete(tmp_path):
    def interrupted(directory):
        directory.mkdir()
        (directory / "partial.bin").write_bytes(b"partial evidence")
        raise RuntimeError("interrupted export")

    root = tmp_path / "epoch-1"
    with pytest.raises(RuntimeError, match="interrupted export"):
        runtime_api().save_epoch_checkpoint(
            root, epoch=1, identity={"source_commit": "a" * 40},
            export_model=interrupted, training_state={}, receipt={},
        )
    assert (root / "model/partial.bin").read_bytes() == b"partial evidence"
    assert not (root / "checkpoint-manifest.json").exists()


def test_training_rejects_output_collision_before_loading_inputs(tmp_path):
    marker = tmp_path / "evidence.txt"
    marker.write_text("preserve")
    with pytest.raises(ValueError, match="OUTPUT_ROOT_COLLISION"):
        runtime_api().run_training(output_root=tmp_path, source_commit="a" * 40, inputs={})
    assert marker.read_text() == "preserve"


def test_training_rejects_invalid_source_before_creating_output(tmp_path):
    root = tmp_path / "run"
    with pytest.raises(ValueError, match="SOURCE_COMMIT_INVALID"):
        runtime_api().run_training(output_root=root, source_commit="bad", inputs={})
    assert not root.exists()


def test_real_processor_accepts_two_jittered_box_prompts():
    from types import SimpleNamespace

    import numpy as np
    from PIL import Image

    transformers = pytest.importorskip("transformers")
    processor = transformers.Sam2Processor(
        image_processor=transformers.Sam2ImageProcessorFast(size={"height": 32, "width": 32})
    )
    helper = getattr(runtime_api(), "prepare_training_frame", None)
    assert callable(helper), "processor-safe training frame preparation is not implemented"
    mask = np.ones((16, 16), dtype=bool)
    sample = SimpleNamespace(seed=410000002, truths=(
        {"absolute_xyxy": (1, 1, 5, 5), "mask": mask},
        {"absolute_xyxy": (8, 8, 14, 14), "mask": mask},
    ))
    image = Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8))
    prepared, truth, boxes = helper(processor, image, sample, epoch=1)
    assert tuple(prepared["input_boxes"].shape) == (1, 2, 4)
    assert tuple(prepared["pixel_values"].shape) == (1, 3, 32, 32)
    assert truth.shape == (2, 16, 16)
    assert all(isinstance(box, list) for box in boxes)
