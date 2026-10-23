"""Calibrated detectors, bundles and collection validation."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from perception_benchmark_adapters_support import (
    _batch,
    _candidate,
    _colored_frame,
    _frame,
    _ParameterModule,
    _RecordingDetectorPort,
    _TorchApi,
    _yolo_adapter,
    _YoloModel,
)
import pytest

from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionQuery,
)
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    GroundedSamRawAdapter,
    VerifiedBenchmarkAssets,
    YoloCalibratedDetector,
    YoloRawAdapter,
    build_calibrated_detector_port,
    build_production_detector_port,
)
from so101_demo.perception_benchmark.calibration.results import (
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    GroundedSamBenchmarkThresholds,
    YoloThresholds,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
)
from so101_demo.ports.object_detector import DetectorPort


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

    batch = detector.detect(_colored_frame(), DetectionQuery("plastic_cup"))

    assert isinstance(batch, DetectionBatch)
    assert batch.runtime_device == "mps"
    assert model.predict_calls[-1]["source"][0, 0].tolist() == [30, 20, 10], "BGR, as the production detector hands it over"
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
