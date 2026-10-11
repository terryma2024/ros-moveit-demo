"""Production observation, selector timing and the production builders."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
from pathlib import Path
from types import SimpleNamespace

from perception_benchmark_adapters_support import (
    _batch,
    _candidate,
    _frame,
    _grounded_adapter,
    _GroundingModel,
    _ParameterModule,
    _RecordingDetectorPort,
    _SamModel,
    _TorchApi,
    _yolo_adapter,
    _YoloModel,
)
import pytest

from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.adapters.perception.yolo_seg import YoloResultError
from so101_demo.application.object_pose import TargetSelector
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionQuery,
)
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    YoloCalibratedDetector,
    build_production_detector_port,
    run_production_detector_port,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    YoloThresholds,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    DecisionOutput,
)
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
)
from so101_demo.ports.object_detector import DetectorPort


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

    # The builder hands the detector a device synchronizer made from the `torch` module; what this test pins is the DetectorPort check,
    # so the module is the suite's stand-in (the same `_TorchApi` the other adapter tests use) and torch need not be installed.
    real_import = base_module.importlib.import_module
    monkeypatch.setattr(
        base_module,
        "importlib",
        SimpleNamespace(import_module=lambda name: _TorchApi() if name == "torch" else real_import(name)),
    )
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
