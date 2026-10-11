"""Fake models, processors and helpers shared by the benchmark adapter tests."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
)
from so101_demo.perception_benchmark.adapters import (
    GroundedSamRawAdapter,
    YoloRawAdapter,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
)
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    ResourceSampler,
)


class _Availability:
    def __init__(self, value: bool) -> None:
        self._value = value

    def is_available(self) -> bool:
        return self._value


class _Accelerator:
    def __init__(self, available: bool) -> None:
        self._availability = _Availability(available)
        self.synchronize_calls = 0

    def is_available(self) -> bool:
        return self._availability.is_available()

    def synchronize(self) -> None:
        self.synchronize_calls += 1

    def current_allocated_memory(self) -> int:
        return 1024

    def driver_allocated_memory(self) -> int:
        return 2048


class _TorchApi:
    __version__ = "2.test"
    float32 = np.float32

    def __init__(self, *, cuda: bool = False, mps: bool = True) -> None:
        self.cuda = _Accelerator(cuda)
        self.mps = _Accelerator(mps)
        self.backends = SimpleNamespace(mps=self.mps)

    def inference_mode(self) -> nullcontext[None]:
        return nullcontext()


class _Process:
    def memory_info(self) -> SimpleNamespace:
        return SimpleNamespace(rss=4096)

    def cpu_percent(self, interval: object = None) -> float:
        assert interval is None
        return 10.0


def _frame() -> DetectionFrame:
    return DetectionFrame(
        np.zeros((16, 20, 3), dtype=np.uint8),
        7,
        "task_camera_frame",
    )


def _colored_frame() -> DetectionFrame:
    """A frame whose three channels differ (R=10, G=20, B=30), so a channel-order mistake is visible."""
    rgb = np.zeros((16, 20, 3), dtype=np.uint8)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 10, 20, 30
    return DetectionFrame(rgb, 7, "task_camera_frame")


def _mask() -> np.ndarray:
    value = np.zeros((16, 20), dtype=bool)
    value[2:10, 3:13] = True
    return value


def _candidate(instance_id: str, confidence: float = 0.9) -> DetectionCandidate:
    return DetectionCandidate(
        instance_id=instance_id,
        class_id="plastic_cup",
        confidence=confidence,
        bbox_xyxy=(3.0, 2.0, 13.0, 10.0),
        mask=_mask(),
        source_stamp_ns=7,
        source_frame_id="task_camera_frame",
        image_width=20,
        image_height=16,
        segmentation_quality=0.8,
    )


def _batch(*candidates: DetectionCandidate) -> DetectionBatch:
    return DetectionBatch(
        model_id="plastic-cup-yolo11s-seg-v2",
        weights_sha256="a" * 64,
        runtime_device="mps",
        inference_latency_ms=3.0,
        image_width=20,
        image_height=16,
        candidates=tuple(candidates),
    )


class _RecordingDetectorPort:
    def __init__(
        self,
        batch: DetectionBatch | None = None,
        error: Exception | None = None,
        *,
        runtime_device: str = "mps",
        model_id: str = YOLO_MODEL_ID,
    ) -> None:
        self._batch = batch
        self._error = error
        self.runtime_device = runtime_device
        self.model_id = model_id
        self.detect_calls: list[tuple[DetectionFrame, DetectionQuery]] = []

    def detect(self, frame: DetectionFrame, query: DetectionQuery) -> DetectionBatch:
        self.detect_calls.append((frame, query))
        if self._error is not None:
            raise self._error
        assert self._batch is not None
        return self._batch


class _YoloResult:
    def __init__(
        self,
        *,
        dtype: np.dtype[Any] = np.dtype(np.float32),
        mask_dtype: np.dtype[Any] | None = None,
    ) -> None:
        self.boxes = SimpleNamespace(
            xyxy=np.asarray([[3.0, 2.0, 13.0, 10.0]], dtype=dtype),
            cls=np.asarray([0.0], dtype=dtype),
            conf=np.asarray([0.82], dtype=dtype),
        )
        mask = np.zeros((1, 16, 20), dtype=mask_dtype or dtype)
        mask[0, 2:10, 3:13] = 1.0
        self.masks = SimpleNamespace(data=mask)


class _Parameter:
    def __init__(self, device: str, dtype: np.dtype[Any]) -> None:
        self.device = device
        self.dtype = dtype


class _ParameterModule:
    def __init__(
        self,
        devices: tuple[str, ...] = ("mps",),
        dtypes: tuple[np.dtype[Any], ...] = (np.dtype(np.float32),),
    ) -> None:
        if len(devices) != len(dtypes):
            raise ValueError("parameter devices/dtypes must align")
        self._parameters = tuple(
            _Parameter(device, dtype) for device, dtype in zip(devices, dtypes)
        )

    def parameters(self) -> Any:
        return iter(self._parameters)

    def move(self, device: str) -> None:
        for parameter in self._parameters:
            parameter.device = device


class _YoloModel:
    names = {0: "plastic_cup"}

    def __init__(
        self,
        *,
        device: str = "mps",
        dtype: np.dtype[Any] = np.dtype(np.float32),
        move_on_predict: bool = False,
        parameter_devices: tuple[str, ...] | None = None,
        parameter_dtypes: tuple[np.dtype[Any], ...] | None = None,
        mask_dtype: np.dtype[Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.device = device
        self.dtype = dtype
        self.move_on_predict = move_on_predict
        self.mask_dtype = mask_dtype
        self.error = error
        devices = parameter_devices or (device,)
        dtypes = parameter_dtypes or tuple(dtype for _ in devices)
        self.model = _ParameterModule(devices, dtypes)
        self.predict_calls: list[dict[str, object]] = []
        self.predictor = SimpleNamespace(args=SimpleNamespace(conf=0.25, iou=0.70, imgsz=640))

    def predict(self, **kwargs: object) -> list[_YoloResult]:
        self.predict_calls.append(kwargs)
        if self.move_on_predict:
            self.device = str(kwargs["device"])
            self.model.move(self.device)
        if self.error is not None:
            raise self.error
        return [_YoloResult(dtype=self.dtype, mask_dtype=self.mask_dtype)]


class _GroundingTokenizer:
    def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
        mapping = {101: "[CLS]", 11: "plastic", 12: "cup", 102: "[SEP]"}
        return [mapping[value] for value in ids]


class _GroundingProcessor:
    tokenizer = _GroundingTokenizer()

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.postprocess_calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> dict[str, np.ndarray]:
        self.calls.append(kwargs)
        return {"input_ids": np.asarray([[101, 11, 12, 102]], dtype=np.int64)}

    def post_process_grounded_object_detection(
        self, outputs: object, **kwargs: object
    ) -> list[dict[str, object]]:
        del outputs
        self.postprocess_calls.append(kwargs)
        return [
            {
                "boxes": np.asarray([[3.0, 2.0, 13.0, 10.0]], dtype=np.float32),
                "scores": np.asarray([0.91], dtype=np.float32),
                "text_labels": ["plastic cup"],
                "query_indices": np.asarray([0], dtype=np.int64),
            }
        ]


class _GroundingModel:
    dtype = np.float32
    device = "mps"

    def __init__(self, *, error: Exception | None = None) -> None:
        self.call_count = 0
        self.error = error
        self._parameters = _ParameterModule()

    def parameters(self) -> Any:
        return self._parameters.parameters()

    def __call__(self, **inputs: object) -> SimpleNamespace:
        assert "input_ids" in inputs
        self.call_count += 1
        if self.error is not None:
            raise self.error
        probabilities = np.asarray([0.1, 0.88, 0.79, 0.1], dtype=np.float32)
        logits = np.log(probabilities / (1.0 - probabilities)).reshape(1, 1, 4)
        return SimpleNamespace(logits=logits)


class _SamProcessor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> dict[str, np.ndarray]:
        self.calls.append(kwargs)
        return {
            "original_sizes": np.asarray([[16, 20]], dtype=np.int64),
            "input_boxes": np.asarray(kwargs["input_boxes"], dtype=np.float32),
        }

    def post_process_masks(
        self,
        masks: np.ndarray,
        original_sizes: np.ndarray,
        mask_threshold: float = 0.0,
        binarize: bool = True,
        max_hole_area: float = 0.0,
        max_sprinkle_area: float = 0.0,
        apply_non_overlapping_constraints: bool = False,
        **kwargs: object,
    ) -> list[np.ndarray]:
        del max_hole_area, max_sprinkle_area, apply_non_overlapping_constraints, kwargs
        assert tuple(original_sizes[0]) == (16, 20)
        assert binarize is True
        return [np.asarray(masks[0]) > mask_threshold]


class _SamModel:
    dtype = np.float32
    device = "mps"

    def __init__(self, *, error: Exception | None = None) -> None:
        self.call_count = 0
        self.error = error
        self._parameters = _ParameterModule()

    def parameters(self) -> Any:
        return self._parameters.parameters()

    def __call__(self, **inputs: object) -> SimpleNamespace:
        assert np.asarray(inputs["input_boxes"]).shape == (1, 1, 4)
        self.call_count += 1
        if self.error is not None:
            raise self.error
        masks = np.zeros((1, 1, 1, 16, 20), dtype=np.float32)
        masks[0, 0, 0, 2:10, 3:13] = 1.0
        return SimpleNamespace(
            pred_masks=masks,
            iou_scores=np.asarray([[[0.84]]], dtype=np.float32),
        )


def _resource_sampler(torch_api: _TorchApi) -> ResourceSampler:
    return ResourceSampler(process=_Process(), torch_api=torch_api, device="mps")


def _yolo_adapter(
    evidence_root: Path,
    *,
    model: _YoloModel | None = None,
    torch_api: _TorchApi | None = None,
    resource_sampler: Any | None = None,
) -> YoloRawAdapter:
    torch_api = torch_api or _TorchApi()
    return YoloRawAdapter(
        model=model or _YoloModel(),
        model_id=YOLO_MODEL_ID,
        runtime_device="mps",
        weights_sha256="a" * 64,
        evidence_root=evidence_root,
        synchronizer=DeviceSynchronizer(torch_api, "mps"),
        resource_sampler=resource_sampler or _resource_sampler(torch_api),
    )


def _grounded_adapter(
    evidence_root: Path,
    *,
    torch_api: _TorchApi | None = None,
    grounding_processor: _GroundingProcessor | None = None,
    grounding_model: _GroundingModel | None = None,
    sam_model: _SamModel | None = None,
    resource_sampler: Any | None = None,
    target_class_id: str = "plastic_cup",
    prompt: str = "plastic cup.",
    proposal_observer: Any | None = None,
) -> tuple[
    GroundedSamRawAdapter,
    _GroundingProcessor,
    _GroundingModel,
    _SamProcessor,
    _SamModel,
]:
    torch_api = torch_api or _TorchApi()
    grounding_processor = grounding_processor or _GroundingProcessor()
    grounding_model = grounding_model or _GroundingModel()
    sam_processor = _SamProcessor()
    sam_model = sam_model or _SamModel()
    adapter = GroundedSamRawAdapter(
        model_id=GROUNDED_SAM_MODEL_ID,
        runtime_device="mps",
        manifest_sha256="b" * 64,
        evidence_root=evidence_root,
        torch_api=torch_api,
        grounding_processor=grounding_processor,
        grounding_model=grounding_model,
        sam_processor=sam_processor,
        sam_model=sam_model,
        synchronizer=DeviceSynchronizer(torch_api, "mps"),
        resource_sampler=resource_sampler or _resource_sampler(torch_api),
        target_class_id=target_class_id,
        prompt=prompt,
        **({"proposal_observer": proposal_observer} if proposal_observer is not None else {}),
    )
    return adapter, grounding_processor, grounding_model, sam_processor, sam_model
