"""Low-frequency perception benchmark regression tests."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.adapters.perception.yolo_seg import YoloResultError
from so101_demo.application.object_pose import TargetSelector
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
)
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    GroundedSamRawAdapter,
    RawDetectionResult,
    ResourceSamplingError,
    VerifiedBenchmarkAssets,
    YoloCalibratedDetector,
    YoloRawAdapter,
    build_calibrated_detector_port,
    build_production_detector_port,
    run_production_detector_port,
)
from so101_demo.perception_benchmark.calibration import (
    GroundedSamBenchmarkThresholds,
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
    YoloThresholds,
)
from so101_demo.perception_benchmark.codec import decode_mask_rle, sha256_bytes
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    DecisionOutput,
)
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    ResourceSample,
    ResourceSampler,
)
from so101_demo.ports.object_detector import DetectorPort


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


class _ControlledResourceSampler:
    device = "mps"

    def __init__(
        self,
        *,
        result: object | None = None,
        error: Exception | None = None,
        construct_invalid: bool = False,
    ) -> None:
        self.result = result
        self.error = error
        self.construct_invalid = construct_invalid
        self.sample_calls = 0

    def sample(self) -> Any:
        self.sample_calls += 1
        if self.error is not None:
            raise self.error
        if self.construct_invalid:
            return ResourceSample(
                process_rss_bytes=-1,
                process_cpu_percent=10.0,
                gpu_memory_allocated_bytes=1,
                gpu_memory_reserved_bytes=2,
                gpu_utilization_percent=3.0,
                gpu_temperature_celsius=4.0,
                gpu_power_watts=5.0,
            )
        assert self.result is not None
        return self.result


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
    )
    return adapter, grounding_processor, grounding_model, sam_processor, sam_model


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_both_adapters_emit_same_raw_contract(tmp_path: Path, model: str) -> None:
    """Catch either model bypassing the shared immutable raw schema."""

    adapter = _yolo_adapter(tmp_path) if model == "yolo" else _grounded_adapter(tmp_path)[0]
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert isinstance(result, RawDetectionResult)
    assert result.raw_candidates
    assert result.phase_timings.total_ms >= 0.0
    assert all(candidate.mask.sha256 for candidate in result.raw_candidates)
    assert result.fallback_used is False
    assert result.runtime_device == "mps"
    assert result.dtype == "float32"


@pytest.mark.parametrize(
    "model_id",
    (
        "not-yolo-imposter",
        f"prefix-{YOLO_MODEL_ID}",
        f"{YOLO_MODEL_ID}-suffix",
    ),
)
def test_yolo_raw_adapter_rejects_noncanonical_identity_before_model_use(
    tmp_path: Path, model_id: str
) -> None:
    model = _YoloModel()
    torch_api = _TorchApi()

    with pytest.raises(ValueError, match="model_id"):
        YoloRawAdapter(
            model=model,
            model_id=model_id,
            runtime_device="mps",
            weights_sha256="a" * 64,
            evidence_root=tmp_path,
            synchronizer=DeviceSynchronizer(torch_api, "mps"),
            resource_sampler=_resource_sampler(torch_api),
        )

    assert model.predict_calls == []


@pytest.mark.parametrize(
    "model_id",
    (
        "grounded-sam-wrong",
        f"prefix-{GROUNDED_SAM_MODEL_ID}",
        f"{GROUNDED_SAM_MODEL_ID}-suffix",
    ),
)
def test_grounded_raw_adapter_rejects_noncanonical_identity(tmp_path: Path, model_id: str) -> None:
    torch_api = _TorchApi()

    with pytest.raises(ValueError, match="model_id"):
        GroundedSamRawAdapter(
            model_id=model_id,
            runtime_device="mps",
            manifest_sha256="b" * 64,
            evidence_root=tmp_path,
            torch_api=torch_api,
            grounding_processor=_GroundingProcessor(),
            grounding_model=_GroundingModel(),
            sam_processor=_SamProcessor(),
            sam_model=_SamModel(),
            synchronizer=DeviceSynchronizer(torch_api, "mps"),
            resource_sampler=_resource_sampler(torch_api),
        )


@pytest.mark.parametrize(
    ("model_id", "model"),
    [
        (f"{YOLO_MODEL_ID}-suffix", "yolo"),
        (f"{GROUNDED_SAM_MODEL_ID}-suffix", "grounded_sam"),
    ],
)
def test_raw_detection_result_rejects_near_identity_with_candidates(
    tmp_path: Path, model_id: str, model: str
) -> None:
    adapter = _yolo_adapter(tmp_path) if model == "yolo" else _grounded_adapter(tmp_path)[0]
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    with pytest.raises(ValueError, match="model_id"):
        replace(result, model_id=model_id)


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_resource_sampling_failure_has_typed_adapter_boundary(tmp_path: Path, model: str) -> None:
    """Catch raw telemetry failures escaping without a machine-readable type."""

    expected = ValueError("opaque failure 731")
    sampler = _ControlledResourceSampler(error=expected)
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    with pytest.raises(Exception) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert type(caught.value).__name__ == "ResourceSamplingError"
    assert isinstance(caught.value, ResourceSamplingError)
    assert caught.value.__cause__ is expected
    assert sampler.sample_calls == 1


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_invalid_resource_sample_validation_has_typed_adapter_boundary(
    tmp_path: Path, model: str
) -> None:
    """Catch ResourceSample validation errors leaking as untyped ValueError."""

    sampler = _ControlledResourceSampler(construct_invalid=True)
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    with pytest.raises(Exception) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert type(caught.value).__name__ == "ResourceSamplingError"
    assert isinstance(caught.value.__cause__, ValueError)
    assert sampler.sample_calls == 1


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_inference_value_error_is_not_reclassified_as_resource_sampling(
    tmp_path: Path, model: str
) -> None:
    """Catch an overly broad resource wrapper swallowing model exceptions."""

    expected = ValueError("opaque failure 731")
    sample = ResourceSample(4096, 10.0, 1, 2, 3.0, 4.0, 5.0)
    sampler = _ControlledResourceSampler(result=sample)
    if model == "yolo":
        adapter = _yolo_adapter(
            tmp_path,
            model=_YoloModel(error=expected),
            resource_sampler=sampler,
        )
    else:
        adapter = _grounded_adapter(
            tmp_path,
            grounding_model=_GroundingModel(error=expected),
            resource_sampler=sampler,
        )[0]

    with pytest.raises(Exception) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert type(caught.value).__name__ != "ResourceSamplingError"
    if model == "yolo":
        assert isinstance(caught.value, YoloResultError)
        assert caught.value.__cause__ is expected
    else:
        assert caught.value is expected
    assert sampler.sample_calls == 0


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_result_schema_value_error_is_not_reclassified_as_resource_sampling(
    tmp_path: Path, model: str
) -> None:
    """Catch resource wrapping extending beyond the sample call into result schema."""

    sampler = _ControlledResourceSampler(result=object())
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    with pytest.raises(ValueError, match="resource_samples") as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert not isinstance(caught.value, ResourceSamplingError)
    assert caught.value.__cause__ is None
    assert sampler.sample_calls == 1


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_successful_resource_sampling_is_preserved(tmp_path: Path, model: str) -> None:
    """Catch the typed failure boundary changing successful resource records."""

    sample = ResourceSample(4096, 10.0, 1, 2, 3.0, 4.0, 5.0)
    sampler = _ControlledResourceSampler(result=sample)
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert result.resource_samples == (sample,)
    assert result.resource_samples[0] is sample
    assert sampler.sample_calls == 1


def test_yolo_low_floor_uses_exact_irreversible_settings_and_class_score(
    tmp_path: Path,
) -> None:
    """Catch a raw YOLO run using a higher floor or hiding NMS/max-det loss."""

    model = _YoloModel()
    result = _yolo_adapter(tmp_path, model=model).collect(_frame(), CollectionMode.LOW_FLOOR)

    assert len(model.predict_calls) == 1
    call = model.predict_calls[0]
    np.testing.assert_array_equal(call.pop("source"), _frame().rgb8)
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

    from so101_demo.cli.perception_benchmark import _write_index

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

    import torch
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


def test_raw_inference_exceptions_synchronize_and_preserve_original_error(
    tmp_path: Path,
) -> None:
    """Catch YOLO or Grounded-SAM skipping the requested-device error boundary."""

    yolo_error = RuntimeError("yolo exploded")
    yolo_torch = _TorchApi()
    yolo = _yolo_adapter(
        tmp_path,
        model=_YoloModel(error=yolo_error),
        torch_api=yolo_torch,
    )
    with pytest.raises(YoloResultError) as yolo_caught:
        yolo.collect(_frame(), CollectionMode.LOW_FLOOR)
    assert yolo_caught.value.__cause__ is yolo_error
    assert yolo_torch.mps.synchronize_calls == 3

    grounding_error = RuntimeError("grounding exploded")
    grounded_torch = _TorchApi()
    grounded = _grounded_adapter(
        tmp_path,
        torch_api=grounded_torch,
        grounding_model=_GroundingModel(error=grounding_error),
    )[0]
    with pytest.raises(RuntimeError) as grounded_caught:
        grounded.collect(_frame(), CollectionMode.LOW_FLOOR)
    assert grounded_caught.value is grounding_error
    assert grounded_torch.mps.synchronize_calls == 3

    sam_error = RuntimeError("SAM exploded")
    sam_torch = _TorchApi()
    grounded_with_raising_sam = _grounded_adapter(
        tmp_path,
        torch_api=sam_torch,
        sam_model=_SamModel(error=sam_error),
    )[0]
    with pytest.raises(RuntimeError) as sam_caught:
        grounded_with_raising_sam.collect(_frame(), CollectionMode.LOW_FLOOR)
    assert sam_caught.value is sam_error
    assert sam_torch.mps.synchronize_calls == 4


def test_calibrated_yolo_exception_synchronizes_without_swallowing_cause(
    tmp_path: Path,
) -> None:
    """Catch the calibrated warm-up path omitting its post-inference sync."""

    weights = tmp_path / "raising.pt"
    weights.write_bytes(b"raising-weights")
    expected = RuntimeError("warm-up exploded")
    torch_api = _TorchApi()

    with pytest.raises(YoloResultError) as caught:
        YoloCalibratedDetector(
            weights_path=weights,
            expected_sha256=hashlib.sha256(b"raising-weights").hexdigest(),
            requested_device="mps",
            model_id="plastic-cup-yolo11s-seg-v2",
            thresholds=YoloThresholds(Decimal("0.50"), Decimal("0.70"), Decimal("0.50"), 640),
            torch_api=torch_api,
            model_factory=lambda _: _YoloModel(error=expected),
        )

    assert caught.value.__cause__ is expected
    assert torch_api.mps.synchronize_calls == 2


def test_production_observation_calls_real_port_and_real_target_selector() -> None:
    """Catch raw replay substituting for the production detector/selector path."""

    assert DetectorPort.__module__ == "so101_demo.ports.object_detector"
    detector = _RecordingDetectorPort(_batch(_candidate("cup-7")))
    frame = _frame()

    observed = run_production_detector_port(detector, frame, selector_threshold=0.50)

    assert detector.detect_calls == [(frame, DetectionQuery("plastic_cup"))]
    assert observed.decision is DecisionOutput.UNIQUE
    assert observed.selected_candidate_id == "cup-7"
    assert observed.batch is detector._batch


def test_production_observation_uses_detector_declared_generic_target_class() -> None:
    """Catch the benchmark production path querying a fine-tuned detector as plastic_cup."""

    candidate = replace(_candidate("cup-8"), class_id="cup")
    detector = _RecordingDetectorPort(_batch(candidate), model_id=GROUNDED_SAM_MODEL_ID)
    detector.target_class_id = "cup"  # type: ignore[attr-defined]
    frame = _frame()

    observed = run_production_detector_port(detector, frame, selector_threshold=0.50)

    assert detector.detect_calls == [(frame, DetectionQuery("cup"))]
    assert observed.decision is DecisionOutput.UNIQUE
    assert observed.selected_candidate_id == "cup-8"


def test_production_selector_timing_synchronizes_both_boundaries() -> None:
    """Catch selector timing starting or ending before accelerator work is complete."""

    torch_api = _TorchApi()
    observed = run_production_detector_port(
        _RecordingDetectorPort(_batch(_candidate("cup"))),
        _frame(),
        selector_threshold=0.50,
        synchronizer=DeviceSynchronizer(torch_api, "mps"),
    )

    assert observed.decision is DecisionOutput.UNIQUE
    assert torch_api.mps.synchronize_calls == 2


@pytest.mark.parametrize(
    ("batch", "expected", "reason"),
    (
        (_batch(), DecisionOutput.NOT_FOUND, "TARGET_NOT_FOUND"),
        (
            _batch(_candidate("a"), _candidate("b")),
            DecisionOutput.AMBIGUOUS,
            "TARGET_AMBIGUOUS",
        ),
    ),
)
def test_production_observation_maps_selector_errors_to_four_state_contract(
    batch: DetectionBatch,
    expected: DecisionOutput,
    reason: str,
) -> None:
    """Catch selector rejections being collapsed or persisted outside four states."""

    observed = run_production_detector_port(
        _RecordingDetectorPort(batch), _frame(), selector_threshold=0.50
    )

    assert observed.decision is expected
    assert observed.selected_candidate_id is None
    assert observed.rejection_reason == reason


def test_production_observation_maps_detector_and_selector_failures_to_error() -> None:
    """Catch an exception escaping without a denominator ERROR observation."""

    detector_error = run_production_detector_port(
        _RecordingDetectorPort(error=RuntimeError("boom")),
        _frame(),
        selector_threshold=0.50,
    )
    selector_error = run_production_detector_port(
        _RecordingDetectorPort(_batch(_candidate("cup"))),
        _frame(),
        selector_threshold=float("nan"),
    )

    assert detector_error.decision is DecisionOutput.ERROR
    assert detector_error.error_type == "DETECTOR_ERROR"
    assert selector_error.decision is DecisionOutput.ERROR
    assert selector_error.error_type == "SELECTOR_ERROR"


def test_production_observation_fails_if_selector_mutates_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch a selector changing candidate masks/confidence/identity in place."""

    original_select = TargetSelector.select

    def mutating_select(
        self: TargetSelector, *args: object, **kwargs: object
    ) -> DetectionCandidate:
        selected = original_select(self, *args, **kwargs)  # type: ignore[arg-type]
        selected.mask.setflags(write=True)
        selected.mask[2, 3] = False
        return selected

    monkeypatch.setattr(TargetSelector, "select", mutating_select)

    with pytest.raises(RuntimeError, match="DETECTION_BATCH_MUTATED"):
        run_production_detector_port(
            _RecordingDetectorPort(_batch(_candidate("cup"))),
            _frame(),
            selector_threshold=0.50,
        )


def test_configured_production_builder_requires_a_real_detect_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch the detector factory's narrow metadata protocol being mistaken for the port."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda options: SimpleNamespace(detector=SimpleNamespace(runtime_device="mps")),
    )
    with pytest.raises(TypeError, match="DetectorPort"):
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps", allow_cpu_fallback=False, backend="grounded_sam"
            )
        )

    expected = _RecordingDetectorPort(_batch())
    expected._grounding_model = _ParameterModule()  # type: ignore[attr-defined]
    expected._sam_model = _ParameterModule()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda options: SimpleNamespace(detector=expected),
    )
    assert (
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps", allow_cpu_fallback=False, backend="grounded_sam"
            )
        )
        is expected
    )


def test_production_builder_rejects_fallback_device_mismatch_and_live_config_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch formal production collection lying about device or YOLO predictor config."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    options = SimpleNamespace(
        requested_device="mps", allow_cpu_fallback=False, backend="grounded_sam"
    )
    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda _options: SimpleNamespace(
            detector=_RecordingDetectorPort(_batch(), runtime_device="cpu")
        ),
    )
    with pytest.raises(ModelSetupError, match="DEVICE_MISMATCH"):
        build_production_detector_port(options)

    with pytest.raises(ModelSetupError, match="CPU fallback"):
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps",
                allow_cpu_fallback=True,
                backend="grounded_sam",
            )
        )

    drifted = _RecordingDetectorPort(_batch())
    drifted._model = _YoloModel()  # type: ignore[attr-defined]
    drifted._model.predictor.args.conf = 0.24  # type: ignore[attr-defined]
    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda _options: SimpleNamespace(detector=drifted),
    )
    with pytest.raises(ModelSetupError, match="PRODUCTION_CONFIG_MISMATCH"):
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps",
                allow_cpu_fallback=False,
                backend="yolo_seg",
            )
        )


def _safe_metrics() -> PlatformCalibrationMetrics:
    return PlatformCalibrationMetrics(
        sample_count=200,
        error_count=0,
        macro_f1=0.8,
        mask_ap50_95=0.7,
        unsafe_unique_count=0,
        unsafe_unique_denominator=100,
        unsafe_unique_rate=0.0,
        two_cup_both_matched_recall=0.75,
    )


def _lock(model: str) -> ThresholdLock:
    selected: YoloThresholds | GroundedSamBenchmarkThresholds
    if model == "yolo_seg":
        selected = YoloThresholds(Decimal("0.50"), Decimal("0.70"), Decimal("0.50"), 640)
        grid_version = "yolo-seg-grid/v1"
    else:
        selected = GroundedSamBenchmarkThresholds(
            Decimal("0.35"),
            Decimal("0.25"),
            Decimal("0.75"),
            Decimal("0.50"),
        )
        grid_version = "grounded-sam-grid/v1"
    metrics = _safe_metrics()
    lock = ThresholdLock(
        schema_version="so101-threshold-lock/v1",
        model=model,  # type: ignore[arg-type]
        grid_version=grid_version,
        objective_version="joint-platform-val/v1",
        tie_break_version="joint-platform-seven-level/v1",
        val_inventory_sha256="1" * 64,
        mac_prediction_inventory_sha256="2" * 64,
        linux_prediction_inventory_sha256="3" * 64,
        formal=True,
        platform_sample_counts={"macos": 200, "linux": 200},
        selected=selected,
        outcome="SAFE_CALIBRATED",
        deployable=True,
        source_commit="a" * 40,
        objective_metrics=ObjectiveCalibrationMetrics(0.8, 0.8, 0.7, 0.75),
        platform_metrics={"macos": metrics, "linux": metrics},
        lock_sha256="0" * 64,
    )
    return lock.with_recomputed_sha256()


def test_calibrated_builder_configures_existing_grounded_detector_from_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Catch calibrated Grounded-SAM replay replacing the real detector port."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    captured: list[dict[str, object]] = []
    detector = _RecordingDetectorPort(_batch(_candidate("cup")), model_id=GROUNDED_SAM_MODEL_ID)
    detector._grounding_model = _ParameterModule()  # type: ignore[attr-defined]
    detector._sam_model = _ParameterModule()  # type: ignore[attr-defined]

    def grounded_factory(**kwargs: object) -> _RecordingDetectorPort:
        captured.append(kwargs)
        return detector

    monkeypatch.setattr(base_module, "verify_model_bundle", lambda root, sha: "bundle")
    monkeypatch.setattr(base_module, "GroundedSamDetector", grounded_factory)
    assets = VerifiedBenchmarkAssets(
        model="grounded_sam",
        asset_root=tmp_path.resolve(),
        weights_sha256=None,
        manifest_sha256="b" * 64,
        requested_device="mps",
        allow_cpu_fallback=False,
    )

    built: DetectorPort = build_calibrated_detector_port(
        "grounded_sam", _lock("grounded_sam"), assets
    )
    batch = built.detect(_frame(), DetectionQuery("plastic_cup"))

    assert isinstance(batch, DetectionBatch)
    thresholds = captured[0]["thresholds"]
    assert thresholds.box_threshold == 0.35  # type: ignore[union-attr]
    assert thresholds.text_threshold == 0.25  # type: ignore[union-attr]
    assert thresholds.sam_quality == 0.75  # type: ignore[union-attr]
    assert captured[0]["requested_device"] == "mps"
    assert captured[0]["allow_cpu_fallback"] is False


def test_calibrated_grounded_builder_rejects_noncanonical_detector_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import so101_demo.perception_benchmark.adapters.base as base_module

    detector = _RecordingDetectorPort(_batch(_candidate("cup")), model_id="grounded-sam-wrong")
    detector._grounding_model = _ParameterModule()  # type: ignore[attr-defined]
    detector._sam_model = _ParameterModule()  # type: ignore[attr-defined]
    monkeypatch.setattr(base_module, "verify_model_bundle", lambda root, sha: "bundle")
    monkeypatch.setattr(base_module, "GroundedSamDetector", lambda **kwargs: detector)
    assets = VerifiedBenchmarkAssets(
        model="grounded_sam",
        asset_root=tmp_path.resolve(),
        weights_sha256=None,
        manifest_sha256="b" * 64,
        requested_device="mps",
        allow_cpu_fallback=False,
    )

    with pytest.raises(ValueError, match="model_id"):
        build_calibrated_detector_port("grounded_sam", _lock("grounded_sam"), assets)


def test_yolo_calibrated_detector_implements_real_detect_port(
    tmp_path: Path,
) -> None:
    """Catch calibrated YOLO returning raw records instead of DetectionBatch."""

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    model = _YoloModel()
    torch_api = _TorchApi()
    detector: DetectorPort = YoloCalibratedDetector(
        weights_path=weights,
        expected_sha256=hashlib.sha256(b"weights").hexdigest(),
        requested_device="mps",
        model_id="plastic-cup-yolo11s-seg-v2",
        thresholds=YoloThresholds(Decimal("0.50"), Decimal("0.70"), Decimal("0.50"), 640),
        torch_api=torch_api,
        model_factory=lambda _: model,
    )

    batch = detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert isinstance(batch, DetectionBatch)
    assert batch.runtime_device == "mps"
    assert model.predict_calls[-1]["conf"] == 0.50
    assert model.predict_calls[-1]["iou"] == 0.70
    assert model.predict_calls[-1]["imgsz"] == 640
    assert model.predict_calls[-1]["half"] is False


def test_yolo_calibrated_detector_rejects_identity_before_model_load(
    tmp_path: Path,
) -> None:
    model_factory_calls: list[str] = []

    def model_factory(path: str) -> _YoloModel:
        model_factory_calls.append(path)
        return _YoloModel()

    with pytest.raises(ValueError, match="model_id"):
        YoloCalibratedDetector(
            weights_path=tmp_path / "missing.pt",
            expected_sha256="a" * 64,
            requested_device="mps",
            model_id=f"{YOLO_MODEL_ID}-suffix",
            thresholds=YoloThresholds(Decimal("0.50"), Decimal("0.70"), Decimal("0.50"), 640),
            torch_api=_TorchApi(),
            model_factory=model_factory,
        )

    assert model_factory_calls == []


def test_yolo_allows_first_prediction_to_move_verified_model_to_device(
    tmp_path: Path,
) -> None:
    """Catch rejecting a verified Ultralytics model before its requested-device predict."""

    model = _YoloModel(device="cpu", move_on_predict=True)

    result = _yolo_adapter(tmp_path, model=model).collect(_frame(), CollectionMode.LOW_FLOOR)

    assert result.runtime_device == "mps"
    assert model.device == "mps"


def test_yolo_raw_from_weights_verifies_asset_before_model_load(
    tmp_path: Path,
) -> None:
    """Catch a raw run trusting a claimed digest or loading tampered weights."""

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"verified-weights")
    digest = hashlib.sha256(b"verified-weights").hexdigest()
    model = _YoloModel(device="cpu", move_on_predict=True)

    adapter = YoloRawAdapter.from_weights(
        weights_path=weights,
        expected_sha256=digest,
        requested_device="mps",
        model_id="plastic-cup-yolo11s-seg-v2",
        evidence_root=tmp_path,
        torch_api=_TorchApi(),
        model_factory=lambda _: model,
    )
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert result.runtime_device == "mps"
    assert model.device == "mps"

    with pytest.raises(ModelSetupError, match="WEIGHTS_HASH_MISMATCH"):
        YoloRawAdapter.from_weights(
            weights_path=weights,
            expected_sha256="f" * 64,
            requested_device="mps",
            model_id="plastic-cup-yolo11s-seg-v2",
            evidence_root=tmp_path,
            torch_api=_TorchApi(),
            model_factory=pytest.fail,
        )


def test_yolo_production_snapshot_is_resolved_from_current_predictor(
    tmp_path: Path,
) -> None:
    """Catch hard-coded production settings or guessed historical NMS values."""

    model = _YoloModel()
    adapter = _yolo_adapter(tmp_path, model=model)

    snapshot = adapter.resolved_production_config()

    assert snapshot.conf == 0.25
    assert snapshot.nms_iou == 0.70
    assert snapshot.imgsz == 640
    model.predictor.args.conf = 0.24
    with pytest.raises(ModelSetupError, match="PRODUCTION_CONFIG_MISMATCH"):
        adapter.resolved_production_config()
    model.predictor.args.conf = 0.25
    del model.predictor.args.iou
    with pytest.raises(ModelSetupError, match="PRODUCTION_NMS_UNAVAILABLE"):
        adapter.resolved_production_config()


def test_offline_missing_bundle_never_calls_network_loader(tmp_path: Path) -> None:
    """Catch a missing pinned bundle initiating an implicit network download."""

    with pytest.raises(ModelSetupError, match="MODEL_UNAVAILABLE"):
        GroundedSamRawAdapter.from_bundle(
            tmp_path / "missing",
            expected_manifest_sha256="a" * 64,
            requested_device="mps",
            evidence_root=tmp_path,
            network_loader=pytest.fail,
        )


def test_tampered_grounded_bundle_fails_before_any_loader(tmp_path: Path) -> None:
    """Catch a manifest mismatch reaching either a local or network model loader."""

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ModelSetupError, match="MODEL_HASH_MISMATCH"):
        GroundedSamRawAdapter.from_bundle(
            bundle,
            expected_manifest_sha256="a" * 64,
            requested_device="mps",
            evidence_root=tmp_path,
            grounding_processor_loader=pytest.fail,
            grounding_model_loader=pytest.fail,
            sam_processor_loader=pytest.fail,
            sam_model_loader=pytest.fail,
            network_loader=pytest.fail,
        )


def test_assets_and_raw_result_reject_cpu_fallback_non_fp32_and_hash_mismatch(
    tmp_path: Path,
) -> None:
    """Catch a formal adapter accepting fallback, CPU, mixed precision, or tampering."""

    with pytest.raises(ValueError, match="requested_device"):
        VerifiedBenchmarkAssets(
            model="yolo_seg",
            asset_root=tmp_path,
            weights_sha256="a" * 64,
            manifest_sha256=None,
            requested_device="cpu",  # type: ignore[arg-type]
            allow_cpu_fallback=False,
        )
    with pytest.raises(ValueError, match="CPU fallback"):
        VerifiedBenchmarkAssets(
            model="yolo_seg",
            asset_root=tmp_path,
            weights_sha256="a" * 64,
            manifest_sha256=None,
            requested_device="mps",
            allow_cpu_fallback=True,  # type: ignore[arg-type]
        )

    result = _yolo_adapter(tmp_path).collect(_frame(), CollectionMode.LOW_FLOOR)
    with pytest.raises(ValueError, match="runtime_device"):
        replace(result, runtime_device="cpu")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="float32"):
        replace(result, dtype="float16")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fallback"):
        replace(result, fallback_used=True)

    weights = tmp_path / "tampered.pt"
    weights.write_bytes(b"tampered")
    with pytest.raises(ModelSetupError, match="WEIGHTS_HASH_MISMATCH"):
        YoloCalibratedDetector(
            weights_path=weights,
            expected_sha256="f" * 64,
            requested_device="mps",
            model_id="plastic-cup-yolo11s-seg-v2",
            thresholds=YoloThresholds(Decimal("0.50"), Decimal("0.70"), Decimal("0.50"), 640),
            torch_api=_TorchApi(),
            model_factory=lambda _: _YoloModel(),
        )


@pytest.mark.parametrize(
    ("device", "dtype", "message"),
    (
        ("cpu", np.dtype(np.float32), "DEVICE_MISMATCH"),
        ("mps", np.dtype(np.float16), "NON_FP32_RUNTIME"),
    ),
)
def test_yolo_collection_rejects_device_or_dtype_mismatch(
    tmp_path: Path,
    device: str,
    dtype: np.dtype[Any],
    message: str,
) -> None:
    """Catch reported MPS/FP32 provenance disagreeing with actual model output."""

    with pytest.raises(ModelSetupError, match=message):
        adapter = _yolo_adapter(tmp_path, model=_YoloModel(device=device, dtype=dtype))
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)


def test_yolo_collection_accepts_binary_uint8_result_masks_from_fp32_mps_model(
    tmp_path: Path,
) -> None:
    """Ultralytics may materialize postprocessed binary masks as uint8."""

    result = _yolo_adapter(
        tmp_path,
        model=_YoloModel(mask_dtype=np.dtype(np.uint8)),
    ).collect(_frame(), CollectionMode.LOW_FLOOR)

    assert result.dtype == "float32"
    assert result.runtime_device == "mps"
    assert len(result.raw_candidates) == 1


def test_yolo_collection_rejects_float16_result_masks_from_fp32_mps_model(
    tmp_path: Path,
) -> None:
    """Keep the mask-storage exception limited to lossless binary encodings."""

    with pytest.raises(ModelSetupError, match="NON_FP32_RUNTIME"):
        _yolo_adapter(
            tmp_path,
            model=_YoloModel(mask_dtype=np.dtype(np.float16)),
        ).collect(_frame(), CollectionMode.LOW_FLOOR)


@pytest.mark.parametrize(
    ("model", "message"),
    (
        (
            _YoloModel(parameter_devices=("mps", "cpu")),
            "DEVICE_MISMATCH",
        ),
        (
            _YoloModel(
                parameter_devices=("mps",),
                parameter_dtypes=(np.dtype(np.float16),),
            ),
            "NON_FP32_RUNTIME",
        ),
    ),
)
def test_production_yolo_rejects_mixed_or_non_fp32_underlying_parameters(
    monkeypatch: pytest.MonkeyPatch,
    model: _YoloModel,
    message: str,
) -> None:
    """Catch trusting Ultralytics wrapper claims instead of torch parameters."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    detector = _RecordingDetectorPort(_batch())
    detector._model = model  # type: ignore[attr-defined]
    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda _options: SimpleNamespace(detector=detector),
    )

    with pytest.raises(ModelSetupError, match=message):
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps",
                allow_cpu_fallback=False,
                backend="yolo_seg",
            )
        )


def test_production_runtime_rejects_missing_parameter_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch declared runtime_device becoming the only formal runtime evidence."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    detector = _RecordingDetectorPort(_batch())
    detector._model = _YoloModel()  # type: ignore[attr-defined]
    detector._model.model = SimpleNamespace()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda _options: SimpleNamespace(detector=detector),
    )

    with pytest.raises(ModelSetupError, match="RUNTIME_PROVENANCE_UNAVAILABLE"):
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps",
                allow_cpu_fallback=False,
                backend="yolo_seg",
            )
        )


def test_production_grounded_validates_both_loaded_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch the SAM component escaping formal device/FP32 validation."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    detector = _RecordingDetectorPort(_batch())
    detector._grounding_model = _ParameterModule()  # type: ignore[attr-defined]
    detector._sam_model = _ParameterModule(  # type: ignore[attr-defined]
        devices=("cpu",)
    )
    monkeypatch.setattr(
        base_module,
        "build_detector",
        lambda _options: SimpleNamespace(detector=detector),
    )

    with pytest.raises(ModelSetupError, match="DEVICE_MISMATCH"):
        build_production_detector_port(
            SimpleNamespace(
                requested_device="mps",
                allow_cpu_fallback=False,
                backend="grounded_sam",
            )
        )


@pytest.mark.parametrize(
    ("runtime_device", "model_dtype", "message"),
    (
        ("cpu", np.dtype(np.float32), "DEVICE_MISMATCH"),
        ("mps", np.dtype(np.float16), "NON_FP32_RUNTIME"),
    ),
)
def test_calibrated_grounded_builder_rejects_actual_device_or_dtype_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runtime_device: str,
    model_dtype: np.dtype[Any],
    message: str,
) -> None:
    """Catch calibrated Grounded-SAM provenance disagreeing with loaded models."""

    import so101_demo.perception_benchmark.adapters.base as base_module

    detector = _RecordingDetectorPort(
        _batch(),
        runtime_device=runtime_device,
        model_id=GROUNDED_SAM_MODEL_ID,
    )
    detector._grounding_model = _ParameterModule(  # type: ignore[attr-defined]
        devices=(runtime_device,), dtypes=(model_dtype,)
    )
    detector._sam_model = _ParameterModule(  # type: ignore[attr-defined]
        devices=(runtime_device,)
    )
    monkeypatch.setattr(base_module, "verify_model_bundle", lambda root, sha: "bundle")
    monkeypatch.setattr(base_module, "GroundedSamDetector", lambda **kwargs: detector)
    assets = VerifiedBenchmarkAssets(
        model="grounded_sam",
        asset_root=tmp_path.resolve(),
        weights_sha256=None,
        manifest_sha256="b" * 64,
        requested_device="mps",
        allow_cpu_fallback=False,
    )

    with pytest.raises(ModelSetupError, match=message):
        build_calibrated_detector_port("grounded_sam", _lock("grounded_sam"), assets)
