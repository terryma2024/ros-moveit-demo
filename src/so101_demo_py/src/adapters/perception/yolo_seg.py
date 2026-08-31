"""Ultralytics YOLO-Seg adapter behind the model-independent detector port."""

from __future__ import annotations

import hashlib
import importlib
import math
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
    RuntimeDevice,
)

RequestedDevice = Literal["auto", "cuda", "mps", "cpu"]


class ModelSetupError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class YoloResultError(ValueError):
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


def select_runtime_device(
    requested: str,
    allow_cpu_fallback: bool,
    torch_api: Any,
) -> RuntimeDevice:
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if bool(torch_api.cuda.is_available()):
            return "cuda"
        raise ModelSetupError("DEVICE_UNAVAILABLE", "requested CUDA is unavailable")
    if requested == "mps":
        if bool(torch_api.backends.mps.is_available()):
            return "mps"
        raise ModelSetupError("DEVICE_UNAVAILABLE", "requested MPS is unavailable")
    if requested != "auto":
        raise ModelSetupError("DEVICE_UNAVAILABLE", f"unknown device request: {requested}")
    if bool(torch_api.cuda.is_available()):
        return "cuda"
    if bool(torch_api.backends.mps.is_available()):
        return "mps"
    if allow_cpu_fallback:
        return "cpu"
    raise ModelSetupError(
        "DEVICE_UNAVAILABLE",
        "auto found no accelerator and CPU fallback was not authorized",
    )


def _to_numpy(value: Any) -> np.ndarray:
    current = value
    if hasattr(current, "detach"):
        current = current.detach()
    if hasattr(current, "cpu"):
        current = current.cpu()
    if hasattr(current, "numpy"):
        current = current.numpy()
    return np.asarray(current)


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


def _class_name(class_names: Mapping[int, str] | list[str], index: int) -> str:
    try:
        if isinstance(class_names, Mapping):
            return class_names[index]
        return class_names[index]
    except (IndexError, KeyError) as error:
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
        boxes = _to_numpy(result.boxes.xyxy)
        classes = _to_numpy(result.boxes.cls)
        confidences = _to_numpy(result.boxes.conf)
        masks = _to_numpy(result.masks.data)
    except AttributeError as error:
        raise YoloResultError("boxes, classes, confidence, and masks are required") from error

    if boxes.ndim != 2 or boxes.shape[1:] != (4,):
        raise YoloResultError("bbox array must have shape (count, 4)")
    if classes.ndim != 1 or confidences.ndim != 1 or masks.ndim != 3:
        raise YoloResultError("classes, confidence, or mask dimensions are invalid")
    count = len(boxes)
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
        mask = _resize_mask_nearest(
            masks[instance_index],
            frame.image_height,
            frame.image_width,
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
            raise YoloResultError(f"INFERENCE_FAILED: {error}") from error
        if not isinstance(results, (list, tuple)) or len(results) != 1:
            raise YoloResultError("INFERENCE_FAILED: expected exactly one YOLO result")
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
