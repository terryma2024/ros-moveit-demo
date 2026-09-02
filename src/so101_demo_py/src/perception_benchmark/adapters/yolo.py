"""Lossless YOLO low-floor collection and calibrated detector port."""

from __future__ import annotations

import importlib
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

import numpy as np

from so101_demo.adapters.perception.model_runtime import (
    ModelSetupError,
    RequestedDevice,
    select_runtime_device,
)
from so101_demo.adapters.perception.yolo_seg import (
    YoloResultError,
    convert_yolo_result,
    verify_weights,
)
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionFrame,
    DetectionQuery,
    RuntimeDevice,
)
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    RawDetectionResult,
    ResourceSamplingError,
    _MaskArtifactStore,
    _validate_accelerated_component,
)
from so101_demo.perception_benchmark.calibration import YoloThresholds
from so101_demo.perception_benchmark.contracts import RawCandidate
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    PhaseTimer,
    ResourceSampler,
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


def _assert_model_device_and_dtype(
    model: Any, requested_device: RuntimeDevice, arrays: tuple[np.ndarray, ...] = ()
) -> None:
    _validate_accelerated_component(model, requested_device, "YOLO model")
    if any(array.dtype != np.float32 for array in arrays):
        observed = sorted({array.dtype.name for array in arrays})
        raise ModelSetupError(
            "NON_FP32_RUNTIME", f"observed output dtypes {observed}"
        )


def _resize_mask(mask: np.ndarray, height: int, width: int) -> np.ndarray:
    if mask.ndim != 2 or mask.shape[0] <= 0 or mask.shape[1] <= 0:
        raise YoloResultError("raw mask must be non-empty and two-dimensional")
    source_height, source_width = mask.shape
    rows = np.minimum(
        np.floor(np.arange(height) * source_height / height).astype(int),
        source_height - 1,
    )
    columns = np.minimum(
        np.floor(np.arange(width) * source_width / width).astype(int),
        source_width - 1,
    )
    return np.asarray(mask[np.ix_(rows, columns)] >= 0.5, dtype=bool)


def _class_name(names: Mapping[int, str] | list[str], index: int) -> str:
    try:
        return names[index]
    except (KeyError, IndexError) as error:
        raise YoloResultError(f"class index {index} is not mapped") from error


@dataclass(frozen=True, slots=True)
class YoloProductionSnapshot:
    conf: float
    nms_iou: float
    imgsz: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.conf) or not 0.0 <= self.conf <= 1.0:
            raise ValueError("production conf must be a finite probability")
        if not math.isfinite(self.nms_iou) or not 0.0 <= self.nms_iou <= 1.0:
            raise ValueError("production NMS IoU must be a finite probability")
        if type(self.imgsz) is not int or self.imgsz != 640:
            raise ValueError("production imgsz must equal 640")


def resolve_yolo_production_config(model: Any) -> YoloProductionSnapshot:
    args = getattr(getattr(model, "predictor", None), "args", None)
    if args is None:
        raise ModelSetupError(
            "PRODUCTION_CONFIG_UNAVAILABLE", "current predictor args are unavailable"
        )
    if not hasattr(args, "iou"):
        raise ModelSetupError(
            "PRODUCTION_NMS_UNAVAILABLE", "current predictor NMS IoU is unavailable"
        )
    try:
        conf = float(args.conf)
        nms_iou = float(args.iou)
        imgsz = args.imgsz
        snapshot = YoloProductionSnapshot(conf, nms_iou, imgsz)
    except (AttributeError, TypeError, ValueError) as error:
        raise ModelSetupError(
            "PRODUCTION_CONFIG_UNAVAILABLE", "current predictor args are invalid"
        ) from error
    if snapshot.conf != 0.25 or snapshot.imgsz != 640:
        raise ModelSetupError(
            "PRODUCTION_CONFIG_MISMATCH",
            f"required conf=0.25,imgsz=640; observed conf={snapshot.conf},imgsz={snapshot.imgsz}",
        )
    return snapshot


class YoloRawAdapter:
    """Collect post-NMS YOLO candidates at the preregistered low floor."""

    def __init__(
        self,
        *,
        model: Any,
        model_id: str,
        runtime_device: RuntimeDevice,
        weights_sha256: str,
        evidence_root: Path,
        synchronizer: DeviceSynchronizer,
        resource_sampler: ResourceSampler,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if runtime_device not in {"mps", "cuda"}:
            raise ValueError("formal YOLO collection requires mps or cuda")
        if synchronizer.device != runtime_device or resource_sampler.device != runtime_device:
            raise ValueError("timing/resource device does not match YOLO runtime")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("model_id must be non-empty")
        if not isinstance(weights_sha256, str) or len(weights_sha256) != 64:
            raise ValueError("weights_sha256 is invalid")
        self._model = model
        self.model_id = model_id
        self.runtime_device = runtime_device
        self._weights_sha256 = weights_sha256
        self._synchronizer = synchronizer
        self._resource_sampler = resource_sampler
        self._monotonic_ns = monotonic_ns
        self._class_names = model.names
        self._artifact_store = _MaskArtifactStore(evidence_root, "yolo-seg")

    @classmethod
    def from_weights(
        cls,
        *,
        weights_path: Path,
        expected_sha256: str,
        requested_device: RequestedDevice,
        model_id: str,
        evidence_root: Path,
        torch_api: Any | None = None,
        model_factory: Callable[[str], Any] | None = None,
        process: Any | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> "YoloRawAdapter":
        """Verify immutable local weights before constructing the raw model."""

        verified_sha256 = verify_weights(Path(weights_path), expected_sha256)
        if requested_device not in {"mps", "cuda"}:
            raise ModelSetupError(
                "DEVICE_UNAVAILABLE", "formal YOLO requires mps or cuda"
            )
        if torch_api is None:
            torch_api = importlib.import_module("torch")
        runtime_device = select_runtime_device(requested_device, False, torch_api)
        if model_factory is None:
            model_factory = importlib.import_module("ultralytics").YOLO
        try:
            model = model_factory(str(weights_path))
        except Exception as error:
            raise ModelSetupError("MODEL_LOAD_FAILED", str(error)) from error
        synchronizer = DeviceSynchronizer(torch_api, runtime_device)
        return cls(
            model=model,
            model_id=model_id,
            runtime_device=runtime_device,
            weights_sha256=verified_sha256,
            evidence_root=evidence_root,
            synchronizer=synchronizer,
            resource_sampler=ResourceSampler(
                process=process,
                torch_api=torch_api,
                device=runtime_device,
            ),
            monotonic_ns=monotonic_ns,
        )

    def resolved_production_config(self) -> YoloProductionSnapshot:
        """Read the live predictor arguments; never infer prior NMS settings."""

        return resolve_yolo_production_config(self._model)

    def _convert(
        self, result: Any, frame: DetectionFrame, collection: PurePosixPath
    ) -> tuple[RawCandidate, ...]:
        try:
            boxes = _to_numpy(result.boxes.xyxy)
            classes = _to_numpy(result.boxes.cls)
            confidences = _to_numpy(result.boxes.conf)
        except AttributeError as error:
            raise YoloResultError("raw boxes/classes/confidence are required") from error
        if boxes.ndim != 2 or boxes.shape[1:] != (4,):
            raise YoloResultError("raw boxes must have shape (count, 4)")
        count = len(boxes)
        if classes.shape != (count,) or confidences.shape != (count,):
            raise YoloResultError("raw YOLO output counts differ")
        if result.masks is None and count == 0:
            masks = np.empty((0, frame.image_height, frame.image_width), dtype=np.float32)
        else:
            try:
                masks = _to_numpy(result.masks.data)
            except AttributeError as error:
                raise YoloResultError("raw masks are required") from error
        if masks.ndim != 3 or len(masks) != count:
            raise YoloResultError("raw mask counts differ")
        _assert_model_device_and_dtype(
            self._model,
            self.runtime_device,
            (boxes, classes, confidences, masks),
        )
        candidates: list[RawCandidate] = []
        for index in range(count):
            class_value = float(classes[index])
            if not math.isfinite(class_value) or not class_value.is_integer():
                raise YoloResultError("raw class index is invalid")
            if _class_name(self._class_names, int(class_value)) != "plastic_cup":
                continue
            confidence = float(confidences[index])
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise YoloResultError("raw confidence is invalid")
            bbox = tuple(float(value) for value in boxes[index])
            if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
                raise YoloResultError("raw bbox is invalid")
            mask = _resize_mask(masks[index], frame.image_height, frame.image_width)
            candidate_id = f"yolo-{index:03d}"
            mask_ref = self._artifact_store.write_mask(
                collection / f"{candidate_id}.coco-rle.json", mask
            )
            candidates.append(
                RawCandidate(
                    candidate_id=candidate_id,
                    label="plastic_cup",
                    bbox_xyxy=cast(tuple[float, float, float, float], bbox),
                    mask=mask_ref,
                    ranking_score=confidence,
                    ranking_score_source="class_confidence",
                    class_confidence=confidence,
                    grounding_box_score=None,
                    grounding_text_score=None,
                    sam_quality=None,
                )
            )
        return tuple(candidates)

    def collect(
        self, frame: DetectionFrame, mode: CollectionMode
    ) -> RawDetectionResult:
        if not isinstance(frame, DetectionFrame):
            raise ValueError("frame must be a DetectionFrame")
        if CollectionMode(mode) is not CollectionMode.LOW_FLOOR:
            raise ValueError("YOLO collection mode is unsupported")
        collection = self._artifact_store.begin_collection()
        with PhaseTimer(
            self._synchronizer, monotonic_ns=self._monotonic_ns
        ) as timer:
            source = np.array(frame.rgb8, copy=True)
            timer.mark("preprocess")
            try:
                results = self._model.predict(
                    source=source,
                    imgsz=640,
                    device=self.runtime_device,
                    conf=0.01,
                    iou=0.90,
                    max_det=300,
                    half=False,
                    verbose=False,
                )
            except Exception as error:
                if isinstance(error, (ModelSetupError, YoloResultError)):
                    raise
                raise YoloResultError(f"INFERENCE_FAILED: {error}") from error
            if not isinstance(results, (list, tuple)) or len(results) != 1:
                raise YoloResultError("INFERENCE_FAILED: expected one YOLO result")
            _assert_model_device_and_dtype(self._model, self.runtime_device)
            timer.mark("dino_or_yolo")
            candidates = self._convert(results[0], frame, collection)
            timer.mark("postprocess")
        try:
            resource_sample = self._resource_sampler.sample()
        except Exception as error:
            raise ResourceSamplingError("YOLO resource sampling failed") from error
        return RawDetectionResult(
            model_id=self.model_id,
            runtime_device=self.runtime_device,
            dtype="float32",
            collection_mode=CollectionMode.LOW_FLOOR,
            raw_candidates=candidates,
            phase_timings=timer.to_timings(
                sam_applicable=False, selector_applicable=False
            ),
            resource_samples=(resource_sample,),
            fallback_used=False,
            irreversible_limits={"nms_iou": 0.90, "max_det": 300},
        )


class YoloCalibratedDetector:
    """Benchmark-only YOLO detector implementing the production object port."""

    def __init__(
        self,
        *,
        weights_path: Path,
        expected_sha256: str,
        requested_device: RequestedDevice,
        model_id: str,
        thresholds: YoloThresholds,
        torch_api: Any | None = None,
        model_factory: Callable[[str], Any] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if requested_device not in {"mps", "cuda"}:
            raise ModelSetupError(
                "DEVICE_UNAVAILABLE", "calibrated YOLO requires mps or cuda"
            )
        if not isinstance(thresholds, YoloThresholds):
            raise ValueError("thresholds must be YoloThresholds")
        started_ns = monotonic_ns()
        self._weights_sha256 = verify_weights(Path(weights_path), expected_sha256)
        if torch_api is None:
            torch_api = importlib.import_module("torch")
        self._torch = torch_api
        self.runtime_device = select_runtime_device(
            requested_device, False, self._torch
        )
        self._synchronizer = DeviceSynchronizer(self._torch, self.runtime_device)
        if model_factory is None:
            model_factory = importlib.import_module("ultralytics").YOLO
        self._model = model_factory(str(weights_path))
        self._model_id = model_id
        self._thresholds = thresholds
        self._class_names = self._model.names
        self._monotonic_ns = monotonic_ns
        self._predict(np.zeros((640, 640, 3), dtype=np.uint8))
        self.cold_start_latency_ms = (monotonic_ns() - started_ns) / 1_000_000.0

    def _predict(self, source: np.ndarray) -> Any:
        self._synchronizer.synchronize()
        try:
            results = self._model.predict(
                source=source,
                imgsz=640,
                device=self.runtime_device,
                conf=float(self._thresholds.conf),
                iou=float(self._thresholds.nms_iou),
                max_det=300,
                half=False,
                verbose=False,
            )
        except Exception as error:
            try:
                self._synchronizer.synchronize()
            except Exception as sync_error:
                error.add_note(
                    f"accelerator synchronization also failed: {sync_error}"
                )
            raise YoloResultError(f"INFERENCE_FAILED: {error}") from error
        self._synchronizer.synchronize()
        if not isinstance(results, (list, tuple)) or len(results) != 1:
            raise YoloResultError("INFERENCE_FAILED: expected one YOLO result")
        _assert_model_device_and_dtype(self._model, self.runtime_device)
        return results[0]

    def detect(
        self, frame: DetectionFrame, query: DetectionQuery
    ) -> DetectionBatch:
        if not isinstance(query, DetectionQuery) or query.class_id != "plastic_cup":
            raise YoloResultError("UNSUPPORTED_DETECTION_QUERY")
        started_ns = self._monotonic_ns()
        result = self._predict(frame.rgb8)
        latency_ms = (self._monotonic_ns() - started_ns) / 1_000_000.0
        return convert_yolo_result(
            result,
            frame,
            model_id=self._model_id,
            weights_sha256=self._weights_sha256,
            runtime_device=self.runtime_device,
            inference_latency_ms=latency_ms,
            class_names=self._class_names,
        )


__all__ = (
    "YoloCalibratedDetector",
    "YoloProductionSnapshot",
    "YoloRawAdapter",
    "resolve_yolo_production_config",
)
