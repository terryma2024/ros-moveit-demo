from __future__ import annotations

import inspect
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.adapters.perception.model_bundle import VerifiedModelBundle
from so101_demo.core.detection import DetectionFrame, DetectionQuery


class _DeviceAvailability:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _InferenceMode:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> None:
        return None


class _DeviceTensor:
    """Mirror the host-transfer boundary of a CUDA/MPS torch tensor."""

    def __init__(self, value: np.ndarray, *, on_host: bool = False) -> None:
        self._value = value
        self._on_host = on_host

    def detach(self) -> "_DeviceTensor":
        return self

    def cpu(self) -> "_DeviceTensor":
        return _DeviceTensor(self._value, on_host=True)

    def numpy(self) -> np.ndarray:
        if not self._on_host:
            raise TypeError("device tensor must be copied to host before numpy conversion")
        return self._value

    def __len__(self) -> int:
        return len(self._value)

    def __array__(self, *_: object, **__: object) -> np.ndarray:
        raise TypeError("device tensor cannot be converted directly with numpy.asarray")


def _fake_torch(*, mps: bool) -> SimpleNamespace:
    return SimpleNamespace(
        cuda=_DeviceAvailability(False),
        backends=SimpleNamespace(mps=_DeviceAvailability(mps)),
        inference_mode=lambda: _InferenceMode(),
    )


def _verified_bundle(tmp_path: Path) -> VerifiedModelBundle:
    detector_dir = tmp_path / "grounding-dino-tiny"
    segmenter_dir = tmp_path / "sam2.1-hiera-tiny"
    return VerifiedModelBundle(
        root=tmp_path,
        manifest_sha256="a" * 64,
        detector_dir=detector_dir,
        segmenter_dir=segmenter_dir,
        manifest={},
    )


class _FakeGroundingProcessor:
    def __init__(
        self,
        *,
        two_boxes: bool = False,
        empty: bool = False,
        malformed: bool = False,
        device_results: bool = False,
    ) -> None:
        self._two_boxes = two_boxes
        self._empty = empty
        self._malformed = malformed
        self._device_results = device_results

    def __call__(self, **_: object) -> dict[str, object]:
        return {"input_ids": np.array([[1]], dtype=np.int64)}

    def post_process_grounded_object_detection(
        self, *_: object, **__: object
    ) -> list[dict[str, object]]:
        if self._malformed:
            return [{"boxes": np.zeros((1, 4)), "scores": np.array([0.9])}]
        if self._empty:
            return [{"boxes": np.empty((0, 4)), "scores": np.empty((0,)), "text_labels": []}]
        boxes = np.array([[1.0, 1.0, 9.0, 9.0]], dtype=np.float32)
        scores = np.array([0.9], dtype=np.float32)
        if self._two_boxes:
            boxes = np.array(
                [[1.0, 1.0, 9.0, 9.0], [10.0, 2.0, 18.0, 10.0]], dtype=np.float32
            )
            scores = np.array([0.9, 0.8], dtype=np.float32)
        if self._device_results:
            boxes = _DeviceTensor(boxes)
            scores = _DeviceTensor(scores)
        return [
            {
                "boxes": boxes,
                "scores": scores,
                "text_labels": ["plastic cup"] * len(scores),
            }
        ]


class _FakeGroundingModel:
    def __init__(self) -> None:
        self.call_count = 0
        self._fail_on_next_call = False

    def fail_on_next_call(self) -> None:
        self._fail_on_next_call = True

    def to(self, _: str) -> "_FakeGroundingModel":
        return self

    def eval(self) -> "_FakeGroundingModel":
        return self

    def __call__(self, **_: object) -> SimpleNamespace:
        self.call_count += 1
        if self._fail_on_next_call:
            raise RuntimeError("grounding exploded")
        return SimpleNamespace()


class _FakeSamProcessor:
    def __call__(
        self, *, images: np.ndarray, input_boxes: object, **_: object
    ) -> dict[str, object]:
        size = np.array([[images.shape[0], images.shape[1]]], dtype=np.int64)
        return {
            "input_boxes": np.asarray(input_boxes),
            "original_sizes": size,
            "reshaped_input_sizes": size,
        }

    def post_process_masks(
        self,
        masks: object,
        original_sizes: object,
        mask_threshold: float = 0.0,
        binarize: bool = True,
        max_hole_area: float = 0.0,
        max_sprinkle_area: float = 0.0,
        apply_non_overlapping_constraints: bool = False,
        **kwargs: object,
    ) -> list[np.ndarray]:
        del (
            original_sizes,
            binarize,
            max_hole_area,
            max_sprinkle_area,
            apply_non_overlapping_constraints,
            kwargs,
        )
        if isinstance(mask_threshold, bool) or not isinstance(mask_threshold, (int, float)):
            raise TypeError("mask_threshold must be a numeric threshold")
        return [np.asarray(masks)[0]]


class _FakeSamModel:
    def __init__(self, *, second_quality: float = 0.9) -> None:
        self.call_count = 0
        self.last_input_boxes = np.empty((0, 0, 4), dtype=np.float32)
        self._second_quality = second_quality

    def to(self, _: str) -> "_FakeSamModel":
        return self

    def eval(self) -> "_FakeSamModel":
        return self

    def __call__(self, **inputs: object) -> SimpleNamespace:
        self.call_count += 1
        self.last_input_boxes = np.asarray(inputs["input_boxes"])
        height, width = (16, 20)
        object_count = self.last_input_boxes.shape[1]
        masks = np.zeros((1, object_count, 3, height, width), dtype=np.float32)
        for index, box in enumerate(self.last_input_boxes[0]):
            x_min, y_min, x_max, y_max = (int(value) for value in box)
            masks[0, index, :, y_min:y_max, x_min:x_max] = 1.0
        quality = np.full((1, object_count, 3), 0.9, dtype=np.float32)
        if object_count > 1:
            quality[0, 1, :] = self._second_quality
        return SimpleNamespace(
            pred_masks=masks,
            iou_scores=quality,
        )


def test_fake_sam_processor_matches_transformers_4562_mask_postprocess_contract() -> None:
    """Catch the fake drifting from SAM2's public post-process keyword contract."""

    assert tuple(inspect.signature(_FakeSamProcessor.post_process_masks).parameters) == (
        "self",
        "masks",
        "original_sizes",
        "mask_threshold",
        "binarize",
        "max_hole_area",
        "max_sprinkle_area",
        "apply_non_overlapping_constraints",
        "kwargs",
    )
    masks = np.ones((1, 1, 3, 2, 3), dtype=np.float32)
    processed = _FakeSamProcessor().post_process_masks(
        masks,
        np.array([[2, 3]], dtype=np.int64),
        mask_threshold=0.25,
        binarize=False,
        max_hole_area=1.0,
        max_sprinkle_area=2.0,
        apply_non_overlapping_constraints=True,
        future_transformers_option="accepted-by-kwargs",
    )

    np.testing.assert_array_equal(processed[0], masks[0])


def _recording_loader(
    calls: list[tuple[str, Path, bool, str | None, str | None]],
    kind: str,
    value: object,
):
    def load(path: Path, *, local_files_only: bool) -> object:
        calls.append(
            (
                kind,
                path,
                local_files_only,
                os.environ.get("HF_HUB_OFFLINE"),
                os.environ.get("TRANSFORMERS_OFFLINE"),
            )
        )
        return value

    return load


def _frame() -> DetectionFrame:
    return DetectionFrame(np.zeros((16, 20, 3), dtype=np.uint8), 7, "task_camera_frame")


def _fake_detector(
    *,
    two_boxes: bool,
    empty: bool = False,
    malformed: bool = False,
    device_results: bool = False,
    second_quality: float = 0.9,
) -> tuple[GroundedSamDetector, _FakeGroundingModel, _FakeSamModel]:
    grounding_model = _FakeGroundingModel()
    sam_model = _FakeSamModel(second_quality=second_quality)
    detector = GroundedSamDetector(
        bundle=_verified_bundle(Path("/tmp")),
        thresholds=GroundedSamThresholds.defaults(),
        requested_device="mps",
        allow_cpu_fallback=False,
        torch_api=_fake_torch(mps=True),
        grounding_processor_loader=lambda *_args, **_kwargs: _FakeGroundingProcessor(
            two_boxes=two_boxes,
            empty=empty,
            malformed=malformed,
            device_results=device_results,
        ),
        grounding_model_loader=lambda *_args, **_kwargs: grounding_model,
        sam_processor_loader=lambda *_args, **_kwargs: _FakeSamProcessor(),
        sam_model_loader=lambda *_args, **_kwargs: sam_model,
        monotonic_ns=iter(range(0, 100_000_000, 1_000_000)).__next__,
    )
    grounding_model.call_count = 0
    sam_model.call_count = 0
    return detector, grounding_model, sam_model


def test_detector_loads_both_local_models_offline_and_warms_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch bypassing verified local paths or omitting either warm-up model call."""

    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    calls: list[tuple[str, Path, bool, str | None, str | None]] = []
    grounding_model = _FakeGroundingModel()
    sam_model = _FakeSamModel()
    detector = GroundedSamDetector(
        bundle=_verified_bundle(tmp_path),
        thresholds=GroundedSamThresholds.defaults(),
        requested_device="mps",
        allow_cpu_fallback=False,
        torch_api=_fake_torch(mps=True),
        grounding_processor_loader=_recording_loader(
            calls, "grounding-processor", _FakeGroundingProcessor()
        ),
        grounding_model_loader=_recording_loader(calls, "grounding-model", grounding_model),
        sam_processor_loader=_recording_loader(calls, "sam-processor", _FakeSamProcessor()),
        sam_model_loader=_recording_loader(calls, "sam-model", sam_model),
        monotonic_ns=iter([0, 5_000_000]).__next__,
    )

    assert {kind for kind, _path, _offline, _hf, _transformers in calls} == {
        "grounding-processor",
        "grounding-model",
        "sam-processor",
        "sam-model",
    }
    assert {path for _kind, path, _offline, _hf, _transformers in calls} == {
        tmp_path / "grounding-dino-tiny",
        tmp_path / "sam2.1-hiera-tiny",
    }
    assert all(
        local_files_only
        for _kind, _path, local_files_only, _hf, _transformers in calls
    )
    assert all(
        hf_offline == transformers_offline == "1"
        for _kind, _path, _local, hf_offline, transformers_offline in calls
    )
    assert detector.runtime_device == "mps"
    assert detector.cold_start_latency_ms == 5.0
    assert grounding_model.call_count == 1
    assert sam_model.call_count == 1


def test_detect_runs_grounding_then_one_batched_sam_call() -> None:
    """Catch dropping a proposal or making one SAM inference call per object."""

    detector, grounding_model, sam_model = _fake_detector(two_boxes=True)
    batch = detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert grounding_model.call_count == 1
    assert sam_model.call_count == 1
    assert sam_model.last_input_boxes.shape == (1, 2, 4)
    assert len(batch.candidates) == 2
    assert batch.model_id == "grounding-dino-tiny+sam2.1-hiera-tiny"
    assert batch.weights_sha256 == "a" * 64


def test_detect_copies_grounding_device_tensors_to_host_before_numpy_conversion() -> None:
    """Catch passing CUDA/MPS postprocess tensors directly into NumPy conversion."""

    detector, _grounding_model, _sam_model = _fake_detector(
        two_boxes=False,
        device_results=True,
    )

    batch = detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert len(batch.candidates) == 1
    assert batch.candidates[0].bbox_xyxy == (1.0, 1.0, 9.0, 9.0)
    assert batch.candidates[0].confidence == pytest.approx(0.9)


def test_empty_grounding_result_skips_sam_and_returns_empty_batch() -> None:
    """Catch invoking SAM when Grounding DINO found no supported cup proposal."""

    detector, grounding_model, sam_model = _fake_detector(two_boxes=False, empty=True)

    batch = detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert grounding_model.call_count == 1
    assert sam_model.call_count == 0
    assert batch.candidates == ()


def test_detect_recomputes_both_models_for_every_frame() -> None:
    """Catch retaining video state or reusing a previous frame's model result."""

    detector, grounding_model, sam_model = _fake_detector(two_boxes=True)
    detector.detect(_frame(), DetectionQuery("plastic_cup"))
    detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert grounding_model.call_count == 2
    assert sam_model.call_count == 2


def test_detect_wraps_model_execution_failure_with_stable_code() -> None:
    """Catch a raw model exception escaping the detector boundary."""

    detector, grounding_model, _sam_model = _fake_detector(two_boxes=True)
    grounding_model.fail_on_next_call()

    with pytest.raises(ValueError, match="INFERENCE_FAILED"):
        detector.detect(_frame(), DetectionQuery("plastic_cup"))


def test_detect_preserves_postprocess_contract_code() -> None:
    """Catch converting malformed model output into an unclassified runtime error."""

    detector, _grounding_model, _sam_model = _fake_detector(two_boxes=True, malformed=True)

    with pytest.raises(ValueError, match="RESULT_CONTRACT_INVALID"):
        detector.detect(_frame(), DetectionQuery("plastic_cup"))


def test_detect_logs_each_mask_rejection_with_observable_thresholds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Catch silently dropping a valid DINO proposal at a SAM mask gate."""

    detector, _grounding_model, _sam_model = _fake_detector(
        two_boxes=True, second_quality=0.5
    )

    logger = logging.getLogger(GroundedSamDetector.__module__)
    attach_capture_handler = not logger.propagate
    if attach_capture_handler:
        logger.addHandler(caplog.handler)
    try:
        with caplog.at_level("WARNING", logger=logger.name):
            batch = detector.detect(_frame(), DetectionQuery("plastic_cup"))
    finally:
        if attach_capture_handler:
            logger.removeHandler(caplog.handler)

    assert len(batch.candidates) == 1
    messages = [
        record.getMessage()
        for record in caplog.records
        if "MASK_REJECTED" in record.getMessage()
    ]
    assert len(messages) == 1
    assert "proposal_index=1" in messages[0]
    assert "dino_score=0.800000" in messages[0]
    assert "max_sam_quality=0.500000" in messages[0]
    assert "sam_quality=0.750000" in messages[0]
