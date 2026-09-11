"""Ultralytics YOLO-Seg adapter behind the model-independent detector port."""

from __future__ import annotations

import hashlib
import importlib
import math
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import numpy as np

from so101_demo.adapters.perception.errors import (
    DeterministicModelResultError, ModelRuntimeInfrastructureError,
)

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
    RuntimeDevice,
)
from so101_demo.adapters.perception.model_runtime import (
    ModelSetupError,
    RequestedDevice,
    select_runtime_device,
)


class YoloResultError(DeterministicModelResultError):
    pass


def verify_weights(path: Path, expected_sha256: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ModelSetupError("MODEL_UNAVAILABLE", f"weights are not a regular file: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ModelSetupError(
            "WEIGHTS_HASH_MISMATCH",
            f"expected {expected_sha256}, observed {digest}",
        )
    return digest


def _to_numpy(value: Any) -> np.ndarray:
    current = value
    try:
        if hasattr(current, "detach"):
            current = current.detach()
        if hasattr(current, "cpu"):
            current = current.cpu()
        if hasattr(current, "numpy"):
            current = current.numpy()
    except Exception as error:
        raise ModelRuntimeInfrastructureError(f"TENSOR_TRANSFER_FAILED: {error}") from error
    try:
        return np.asarray(current)
    except (TypeError, ValueError) as error:
        raise YoloResultError(f"invalid output array: {error}") from error


def _resize_mask_nearest(mask: np.ndarray, height: int, width: int) -> np.ndarray:
    if mask.ndim != 2 or mask.shape[0] <= 0 or mask.shape[1] <= 0:
        raise YoloResultError("mask must be a non-empty two-dimensional array")
    source_height, source_width = mask.shape
    rows = np.minimum(
        np.floor(np.arange(height, dtype=np.float64) * source_height / height).astype(int),
        source_height - 1,
    )
    columns = np.minimum(
        np.floor(np.arange(width, dtype=np.float64) * source_width / width).astype(int),
        source_width - 1,
    )
    return np.asarray(mask[np.ix_(rows, columns)] >= 0.5, dtype=bool)


def _trim_mask_boundary(mask: np.ndarray) -> np.ndarray:
    if mask.ndim != 2 or mask.shape[0] <= 0 or mask.shape[1] <= 0:
        raise YoloResultError("mask must be a non-empty two-dimensional array")
    trimmed = np.asarray(mask, dtype=bool)
    for _ in range(2):
        padded = np.pad(trimmed, 1, mode="constant", constant_values=False)
        candidate = (
            padded[1:-1, 1:-1]
            & padded[:-2, 1:-1]
            & padded[2:, 1:-1]
            & padded[1:-1, :-2]
            & padded[1:-1, 2:]
        )
        if not bool(candidate.any()):
            break
        trimmed = candidate
    return np.asarray(trimmed, dtype=bool)


def _class_name(class_names: Mapping[int, str] | list[str], index: int) -> str:
    try:
        if isinstance(class_names, Mapping):
            return class_names[index]
        return class_names[index]
    except (IndexError, KeyError, TypeError) as error:
        raise YoloResultError(f"class index {index} is not mapped") from error


def convert_yolo_result(
    result: Any,
    frame: DetectionFrame,
    *,
    model_id: str,
    weights_sha256: str,
    runtime_device: RuntimeDevice,
    inference_latency_ms: float,
    class_names: Mapping[int, str] | list[str],
) -> DetectionBatch:
    try:
        raw_boxes = result.boxes.xyxy
        raw_classes = result.boxes.cls
        raw_confidences = result.boxes.conf
        raw_masks = result.masks
    except AttributeError as error:
        raise YoloResultError("boxes, classes, confidence, and masks are required") from error
    boxes = _to_numpy(raw_boxes)
    classes = _to_numpy(raw_classes)
    confidences = _to_numpy(raw_confidences)
    if any(array.dtype.kind not in 'iuf' for array in (boxes, classes, confidences)):
        raise YoloResultError("boxes, classes and confidence must be numeric")

    if boxes.ndim != 2 or boxes.shape[1:] != (4,):
        raise YoloResultError("bbox array must have shape (count, 4)")
    if classes.ndim != 1 or confidences.ndim != 1:
        raise YoloResultError("classes or confidence dimensions are invalid")
    count = len(boxes)
    if raw_masks is None and count == 0:
        masks = np.empty((0, frame.image_height, frame.image_width), dtype=bool)
    else:
        try:
            mask_data = raw_masks.data
        except AttributeError as error:
            raise YoloResultError("masks are required for detected instances") from error
        masks = _to_numpy(mask_data)
    if masks.ndim != 3:
        raise YoloResultError("mask dimensions are invalid")
    if masks.dtype.kind not in 'biuf' or not np.isfinite(masks).all():
        raise YoloResultError("mask values must be finite")
    if not (len(classes) == len(confidences) == len(masks) == count):
        raise YoloResultError("YOLO output counts differ")

    candidates: list[DetectionCandidate] = []
    for instance_index in range(count):
        class_value = float(classes[instance_index])
        if not math.isfinite(class_value) or not class_value.is_integer():
            raise YoloResultError(f"class index is invalid: {class_value}")
        confidence = float(confidences[instance_index])
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise YoloResultError(f"confidence is invalid: {confidence}")
        bbox = tuple(float(value) for value in boxes[instance_index])
        mask = _trim_mask_boundary(
            _resize_mask_nearest(
                masks[instance_index],
                frame.image_height,
                frame.image_width,
            )
        )
        if not bool(mask.any()):
            raise YoloResultError(f"mask for instance {instance_index} is empty")
        try:
            candidate = DetectionCandidate(
                instance_id=str(instance_index),
                class_id=_class_name(class_names, int(class_value)),
                confidence=confidence,
                bbox_xyxy=cast(tuple[float, float, float, float], bbox),
                mask=mask,
                source_stamp_ns=frame.source_stamp_ns,
                source_frame_id=frame.source_frame_id,
                image_width=frame.image_width,
                image_height=frame.image_height,
            )
        except ValueError as error:
            raise YoloResultError(str(error)) from error
        candidates.append(candidate)

    return DetectionBatch(
        model_id=model_id,
        weights_sha256=weights_sha256,
        runtime_device=runtime_device,
        inference_latency_ms=inference_latency_ms,
        image_width=frame.image_width,
        image_height=frame.image_height,
        candidates=tuple(candidates),
    )


class YoloSegDetector:
    def __init__(
        self,
        *,
        weights_path: Path,
        expected_sha256: str,
        requested_device: RequestedDevice,
        allow_cpu_fallback: bool,
        model_id: str,
        imgsz: int,
        torch_api: Any | None = None,
        model_factory: Callable[[str], Any] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if imgsz <= 0:
            raise ModelSetupError("MODEL_UNAVAILABLE", "imgsz must be positive")
        self._monotonic_ns = monotonic_ns
        start_ns = monotonic_ns()
        self._weights_sha256 = verify_weights(weights_path, expected_sha256)
        if torch_api is None:
            torch_api = importlib.import_module("torch")
        self.runtime_device = select_runtime_device(
            requested_device,
            allow_cpu_fallback,
            torch_api,
        )
        if model_factory is None:
            ultralytics = importlib.import_module("ultralytics")
            model_factory = ultralytics.YOLO
        self._model = model_factory(str(weights_path))
        self._model_id = model_id
        self._imgsz = imgsz
        self._class_names = self._model.names
        warmup = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
        self._predict(warmup)
        self.cold_start_latency_ms = (monotonic_ns() - start_ns) / 1_000_000.0

    def _predict(self, source: np.ndarray) -> list[Any]:
        try:
            results = self._model.predict(
                source=source,
                imgsz=self._imgsz,
                device=self.runtime_device,
                conf=0.25,
                verbose=False,
            )
        except Exception as error:
            raise ModelRuntimeInfrastructureError(f"INFERENCE_FAILED: {error}") from error
        if not isinstance(results, (list, tuple)) or len(results) != 1:
            raise YoloResultError("RESULT_CONTRACT_INVALID: expected exactly one YOLO result")
        return list(results)

    def detect(
        self,
        frame: DetectionFrame,
        query: DetectionQuery,
    ) -> DetectionBatch:
        del query
        start_ns = self._monotonic_ns()
        result = self._predict(frame.rgb8)[0]
        latency_ms = (self._monotonic_ns() - start_ns) / 1_000_000.0
        return convert_yolo_result(
            result,
            frame,
            model_id=self._model_id,
            weights_sha256=self._weights_sha256,
            runtime_device=self.runtime_device,
            inference_latency_ms=latency_ms,
            class_names=self._class_names,
        )
