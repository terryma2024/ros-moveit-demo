"""Mask artifacts, the raw result and the low floor of both models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from perception_benchmark_adapters_support import (
    _colored_frame,
    _frame,
    _grounded_adapter,
    _GroundingModel,
    _GroundingProcessor,
    _SamProcessor,
    _yolo_adapter,
    _YoloModel,
    _YoloResult,
)
import pytest

from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
)
from so101_demo.perception_benchmark.codec import decode_mask_rle, sha256_bytes


def test_yolo_low_floor_uses_exact_irreversible_settings_and_class_score(
    tmp_path: Path,
) -> None:
    """Catch a raw YOLO run using a higher floor or hiding NMS/max-det loss."""

    model = _YoloModel()
    result = _yolo_adapter(tmp_path, model=model).collect(_colored_frame(), CollectionMode.LOW_FLOOR)

    assert len(model.predict_calls) == 1
    call = model.predict_calls[0]
    source = call.pop("source")
    np.testing.assert_array_equal(source, _colored_frame().rgb8[:, :, ::-1])   # Ultralytics reads a numpy array as BGR
    assert source[0, 0].tolist() == [30, 20, 10] and source.flags["C_CONTIGUOUS"]
    assert call == {
        "imgsz": 640,
        "device": "mps",
        "conf": 0.01,
        "iou": 0.90,
        "max_det": 300,
        "half": False,
        "verbose": False,
    }
    candidate = result.raw_candidates[0]
    assert candidate.candidate_id == "yolo-000"
    assert candidate.ranking_score == pytest.approx(0.82)
    assert candidate.ranking_score_source == "class_confidence"
    assert candidate.class_confidence == pytest.approx(0.82)
    assert candidate.grounding_box_score is None
    assert candidate.grounding_text_score is None
    assert candidate.sam_quality is None
    assert result.irreversible_limits == {"nms_iou": 0.90, "max_det": 300}
    assert result.phase_timings.sam_ms is None


def test_mask_artifacts_are_lossless_relative_fsynced_and_never_overwritten(
    tmp_path: Path,
) -> None:
    """Catch result publication before a durable lossless mask or path reuse."""

    adapter = _yolo_adapter(tmp_path)
    first = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)
    second = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    first_ref = first.raw_candidates[0].mask
    second_ref = second.raw_candidates[0].mask
    assert first_ref.relative_path != second_ref.relative_path
    assert not Path(first_ref.relative_path).is_absolute()
    artifact = tmp_path / first_ref.relative_path
    decoded = decode_mask_rle(json.loads(artifact.read_text(encoding="utf-8")))
    assert int(decoded.sum()) == first_ref.pixel_count
    assert sha256_bytes(decoded.astype(np.uint8).tobytes(order="C")) == first_ref.sha256
    original = artifact.read_bytes()
    with pytest.raises(FileExistsError):
        adapter._artifact_store.write_mask(  # type: ignore[attr-defined]
            first_ref.relative_path, decoded
        )
    assert artifact.read_bytes() == original


def test_zero_candidate_collection_is_representable_in_evidence_index(
    tmp_path: Path,
) -> None:
    """Keep a durable file carrier for frames that correctly yield no masks."""

    from so101_demo.cli.benchmark.common import _write_index

    class _EmptyYoloModel(_YoloModel):
        def predict(self, **kwargs: object) -> list[SimpleNamespace]:
            self.predict_calls.append(kwargs)
            return [
                SimpleNamespace(
                    boxes=SimpleNamespace(
                        xyxy=np.empty((0, 4), dtype=np.float32),
                        cls=np.empty((0,), dtype=np.float32),
                        conf=np.empty((0,), dtype=np.float32),
                    ),
                    masks=None,
                )
            ]

    result = _yolo_adapter(tmp_path, model=_EmptyYoloModel()).collect(
        _frame(), CollectionMode.LOW_FLOOR
    )

    assert result.raw_candidates == ()
    index = _write_index(tmp_path)
    assert [entry.relative_path for entry in index.entries] == [
        "benchmark-masks/yolo-seg/collection-000000/collection.json"
    ]


@pytest.mark.parametrize(
    "symlink_level",
    ("evidence-root", "benchmark-masks", "namespace", "collection"),
)
def test_mask_artifact_store_rejects_preexisting_symlink_escape(
    tmp_path: Path, symlink_level: str
) -> None:
    """Catch any adapter-owned parent following a symlink outside evidence_root."""

    outside = tmp_path / "outside"
    outside.mkdir()
    evidence_root = tmp_path
    if symlink_level == "evidence-root":
        evidence_root = tmp_path / "root-link"
        evidence_root.symlink_to(outside, target_is_directory=True)
    benchmark_masks = evidence_root / "benchmark-masks"
    namespace = benchmark_masks / "yolo-seg"
    if symlink_level == "evidence-root":
        pass
    elif symlink_level == "benchmark-masks":
        benchmark_masks.symlink_to(outside, target_is_directory=True)
    elif symlink_level == "namespace":
        benchmark_masks.mkdir()
        namespace.symlink_to(outside, target_is_directory=True)
    else:
        namespace.mkdir(parents=True)
        (namespace / "collection-000000").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        _yolo_adapter(evidence_root)

    assert list(outside.iterdir()) == []


def test_mask_write_rejects_collection_swapped_to_outside_symlink(
    tmp_path: Path,
) -> None:
    """Catch a post-allocation collection swap writing beyond evidence_root."""

    outside = tmp_path / "outside"
    outside.mkdir()

    class _SwappingYoloModel(_YoloModel):
        def predict(self, **kwargs: object) -> list[_YoloResult]:
            collection = tmp_path / "benchmark-masks" / "yolo-seg" / "collection-000000"
            (collection / "collection.json").unlink()
            collection.rmdir()
            collection.symlink_to(outside, target_is_directory=True)
            return super().predict(**kwargs)

    adapter = _yolo_adapter(tmp_path, model=_SwappingYoloModel())

    with pytest.raises(ValueError, match="symlink"):
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert list(outside.iterdir()) == []


def test_mask_artifact_directory_entries_are_fsynced_before_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch publication before newly owned directories and file entries are durable."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    synchronized: list[Path] = []
    monkeypatch.setattr(
        base_module,
        "_fsync_directory",
        lambda path: synchronized.append(Path(path)),
    )

    result = _yolo_adapter(tmp_path).collect(_frame(), CollectionMode.LOW_FLOOR)
    artifact = tmp_path / result.raw_candidates[0].mask.relative_path
    collection = artifact.parent
    benchmark_masks = tmp_path / "benchmark-masks"
    namespace = benchmark_masks / "yolo-seg"

    assert synchronized == [
        benchmark_masks,
        tmp_path,
        namespace,
        benchmark_masks,
        collection,
        namespace,
        collection,
        collection,
    ]


def test_raw_result_owns_immutable_candidates_limits_and_resource_samples(
    tmp_path: Path,
) -> None:
    """Catch caller-owned collections mutating a recorded raw observation."""

    result = _yolo_adapter(tmp_path).collect(_frame(), CollectionMode.LOW_FLOOR)

    with pytest.raises(FrozenInstanceError):
        result.raw_candidates = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.irreversible_limits["max_det"] = 1  # type: ignore[index]
    assert isinstance(result.resource_samples, tuple)


def test_grounded_low_floor_is_stateless_and_keeps_distinct_model_scores(
    tmp_path: Path,
) -> None:
    """Catch prompt drift, tracker reuse, score multiplication, or a SAM quality rank."""

    adapter, processor, grounding_model, sam_processor, sam_model = _grounded_adapter(tmp_path)
    first = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)
    second = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert grounding_model.call_count == 2
    assert sam_model.call_count == 2
    assert [call["text"] for call in processor.calls] == [
        "plastic cup.",
        "plastic cup.",
    ]
    assert [call["input_boxes"].shape for call in sam_processor.calls] == [
        (1, 1, 4),
        (1, 1, 4),
    ]
    assert processor.postprocess_calls[0]["threshold"] == 0.01
    assert processor.postprocess_calls[0]["text_threshold"] == 0.01
    candidate = first.raw_candidates[0]
    assert candidate.candidate_id == "grounded-sam-000"
    assert candidate.ranking_score == pytest.approx(0.91)
    assert candidate.ranking_score_source == "grounding_box_score"
    assert candidate.class_confidence is None
    assert candidate.grounding_box_score == pytest.approx(0.91)
    assert candidate.grounding_text_score == pytest.approx(0.79, abs=1e-6)
    assert candidate.sam_quality == pytest.approx(0.84)
    assert second.raw_candidates[0].candidate_id == candidate.candidate_id
    assert not hasattr(adapter, "tracker")


def test_grounded_low_floor_supports_single_token_generic_cup_profile(
    tmp_path: Path,
) -> None:
    """Catch the raw adapter requiring a plastic token after the model profile changes."""

    class CupTokenizer:
        def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
            return [{101: "[CLS]", 12: "cup", 102: "[SEP]"}[value] for value in ids]

    class CupProcessor(_GroundingProcessor):
        tokenizer = CupTokenizer()

        def __call__(self, **kwargs: object) -> dict[str, np.ndarray]:
            self.calls.append(kwargs)
            return {"input_ids": np.asarray([[101, 12, 102]], dtype=np.int64)}

        def post_process_grounded_object_detection(
            self, outputs: object, **kwargs: object
        ) -> list[dict[str, object]]:
            del outputs
            self.postprocess_calls.append(kwargs)
            return [
                {
                    "boxes": np.asarray([[3.0, 2.0, 13.0, 10.0]], dtype=np.float32),
                    "scores": np.asarray([0.91], dtype=np.float32),
                    "text_labels": ["cup"],
                    "query_indices": np.asarray([0], dtype=np.int64),
                }
            ]

    class CupModel(_GroundingModel):
        def __call__(self, **inputs: object) -> SimpleNamespace:
            assert "input_ids" in inputs
            self.call_count += 1
            probabilities = np.asarray([0.1, 0.79, 0.1], dtype=np.float32)
            logits = np.log(probabilities / (1.0 - probabilities)).reshape(1, 1, 3)
            return SimpleNamespace(logits=logits)

    processor = CupProcessor()
    adapter = _grounded_adapter(
        tmp_path,
        grounding_processor=processor,
        grounding_model=CupModel(),
        target_class_id="cup",
        prompt="cup.",
    )[0]

    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert processor.calls[0]["text"] == "cup."
    assert result.raw_candidates[0].label == "cup"
    assert result.raw_candidates[0].grounding_text_score == pytest.approx(0.79, abs=1e-6)


def test_grounded_low_floor_uses_prompt_token_score_when_decoded_label_is_noisy(
    tmp_path: Path,
) -> None:
    """Keep the generic cup query when a low text floor expands its decoded phrase."""

    class CupTokenizer:
        def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
            return [{101: "[CLS]", 12: "cup", 102: "[SEP]"}[value] for value in ids]

    class NoisyCupProcessor(_GroundingProcessor):
        tokenizer = CupTokenizer()

        def __call__(self, **kwargs: object) -> dict[str, np.ndarray]:
            self.calls.append(kwargs)
            return {"input_ids": np.asarray([[101, 12, 102]], dtype=np.int64)}

        def post_process_grounded_object_detection(
            self, outputs: object, **kwargs: object
        ) -> list[dict[str, object]]:
            del outputs
            self.postprocess_calls.append(kwargs)
            return [
                {
                    "boxes": np.asarray([[3.0, 2.0, 13.0, 10.0]], dtype=np.float32),
                    "scores": np.asarray([0.79], dtype=np.float32),
                    "text_labels": ["[CLS] cup. [SEP]"],
                    "query_indices": np.asarray([0], dtype=np.int64),
                }
            ]

    class CupModel(_GroundingModel):
        def __call__(self, **inputs: object) -> SimpleNamespace:
            assert "input_ids" in inputs
            self.call_count += 1
            probabilities = np.asarray([0.1, 0.79, 0.1], dtype=np.float32)
            logits = np.log(probabilities / (1.0 - probabilities)).reshape(1, 1, 3)
            return SimpleNamespace(logits=logits)

    result = _grounded_adapter(
        tmp_path,
        grounding_processor=NoisyCupProcessor(),
        grounding_model=CupModel(),
        target_class_id="cup",
        prompt="cup.",
    )[0].collect(_frame(), CollectionMode.LOW_FLOOR)

    assert len(result.raw_candidates) == 1
    assert result.raw_candidates[0].grounding_box_score == pytest.approx(0.79)
    assert result.raw_candidates[0].grounding_text_score == pytest.approx(0.79, abs=1e-6)


def test_grounded_low_floor_rejects_query_below_prompt_token_floor(tmp_path: Path) -> None:
    """Reject a box-only response whose mapped generic cup token score is below 0.01."""

    class CupTokenizer:
        def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
            return [{101: "[CLS]", 12: "cup", 102: "[SEP]"}[value] for value in ids]

    class CupProcessor(_GroundingProcessor):
        tokenizer = CupTokenizer()

        def __call__(self, **kwargs: object) -> dict[str, np.ndarray]:
            self.calls.append(kwargs)
            return {"input_ids": np.asarray([[101, 12, 102]], dtype=np.int64)}

        def post_process_grounded_object_detection(
            self, outputs: object, **kwargs: object
        ) -> list[dict[str, object]]:
            del outputs
            self.postprocess_calls.append(kwargs)
            return [
                {
                    "boxes": np.asarray([[3.0, 2.0, 13.0, 10.0]], dtype=np.float32),
                    "scores": np.asarray([0.91], dtype=np.float32),
                    "text_labels": ["cup"],
                    "query_indices": np.asarray([0], dtype=np.int64),
                }
            ]

    class WeakCupModel(_GroundingModel):
        def __call__(self, **inputs: object) -> SimpleNamespace:
            assert "input_ids" in inputs
            self.call_count += 1
            probabilities = np.asarray([0.91, 0.005, 0.1], dtype=np.float32)
            logits = np.log(probabilities / (1.0 - probabilities)).reshape(1, 1, 3)
            return SimpleNamespace(logits=logits)

    result = _grounded_adapter(
        tmp_path,
        grounding_processor=CupProcessor(),
        grounding_model=WeakCupModel(),
        target_class_id="cup",
        prompt="cup.",
    )[0].collect(_frame(), CollectionMode.LOW_FLOOR)

    assert result.raw_candidates == ()


def test_grounded_low_floor_retains_the_fixed_prompt_with_terminal_punctuation(
    tmp_path: Path,
) -> None:
    """Catch display punctuation removing a real proposal before calibration."""

    class _PunctuatedGroundingProcessor(_GroundingProcessor):
        def post_process_grounded_object_detection(
            self, outputs: object, **kwargs: object
        ) -> list[dict[str, object]]:
            results = super().post_process_grounded_object_detection(outputs, **kwargs)
            results[0]["text_labels"] = ["plastic cup."]
            return results

    adapter = _grounded_adapter(
        tmp_path,
        grounding_processor=_PunctuatedGroundingProcessor(),
    )[0]

    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert len(result.raw_candidates) == 1
    assert result.raw_candidates[0].grounding_box_score == pytest.approx(0.91)
    assert result.raw_candidates[0].sam_quality == pytest.approx(0.84)


def test_grounded_accepts_fixed_text_logit_capacity_larger_than_prompt(
    tmp_path: Path,
) -> None:
    """Match Grounding-DINO's fixed 256-token logits to a shorter prompt."""

    class _FixedCapacityGroundingModel(_GroundingModel):
        def __call__(self, **inputs: object) -> SimpleNamespace:
            assert "input_ids" in inputs
            self.call_count += 1
            probabilities = np.full(256, 0.01, dtype=np.float32)
            probabilities[:4] = np.asarray([0.1, 0.88, 0.79, 0.1], dtype=np.float32)
            logits = np.log(probabilities / (1.0 - probabilities)).reshape(1, 1, 256)
            return SimpleNamespace(logits=logits)

    adapter = _grounded_adapter(
        tmp_path,
        grounding_model=_FixedCapacityGroundingModel(),
    )[0]

    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert len(result.raw_candidates) == 1
    assert result.raw_candidates[0].grounding_text_score == pytest.approx(0.79, abs=1e-6)


def test_grounded_rejects_text_logit_capacity_smaller_than_prompt(
    tmp_path: Path,
) -> None:
    class _UndersizedGroundingModel(_GroundingModel):
        def __call__(self, **inputs: object) -> SimpleNamespace:
            assert "input_ids" in inputs
            self.call_count += 1
            return SimpleNamespace(logits=np.zeros((1, 1, 3), dtype=np.float32))

    adapter = _grounded_adapter(
        tmp_path,
        grounding_model=_UndersizedGroundingModel(),
    )[0]

    with pytest.raises(ModelSetupError, match="grounding logits shape is invalid"):
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)


def test_pinned_transformers_sam2_boolean_masks_are_consumed_losslessly(
    tmp_path: Path,
) -> None:
    """Pin the real 4.56.2 processor dtype/shape and the matching fake contract."""

    # This test is about the real torch/transformers processor; without torch in the interpreter that runs the gate it cannot run.
    torch = pytest.importorskip("torch", reason="needs torch (the real Sam2 processor); the test venv does not install it")
    import transformers
    from transformers import Sam2Processor
    from transformers.models.sam2.image_processing_sam2_fast import (
        Sam2ImageProcessorFast,
    )

    assert transformers.__version__ == "4.56.2"
    processor = Sam2Processor(image_processor=Sam2ImageProcessorFast())
    logits = torch.zeros((1, 1, 1, 16, 20), dtype=torch.float32)
    logits[0, 0, 0, 2:10, 3:13] = 1.0
    processed = processor.post_process_masks(logits, torch.tensor([[16, 20]], dtype=torch.int64))

    assert len(processed) == 1
    assert processed[0].dtype is torch.bool
    assert tuple(processed[0].shape) == (1, 1, 16, 20)
    assert int(processed[0].sum()) == 80
    fake_processed = _SamProcessor().post_process_masks(
        logits.numpy(), np.asarray([[16, 20]], dtype=np.int64)
    )
    assert fake_processed[0].dtype == np.bool_
    np.testing.assert_array_equal(fake_processed[0], processed[0].numpy())

    result = _grounded_adapter(tmp_path)[0].collect(_frame(), CollectionMode.LOW_FLOOR)
    mask_ref = result.raw_candidates[0].mask
    decoded = decode_mask_rle(
        json.loads((tmp_path / mask_ref.relative_path).read_text(encoding="utf-8"))
    )
    assert decoded.dtype == np.bool_
    assert int(decoded.sum()) == 80
    assert result.raw_candidates[0].sam_quality == pytest.approx(0.84)
