"""Catch dropped threshold injection and accidental changes to generic detectors."""

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.adapters.perception.detector_factory import DetectorFactoryOptions, build_detector
from so101_demo.adapters.perception.yolo_seg import YoloSegDetector
from so101_demo.core.detection import DetectionFrame, DetectionQuery


@pytest.mark.parametrize("change,code", [
    ({"torch_threads": 2}, "HEAD_SEARCH_THREAD_DRIFT"),
    ({"torch_interop_threads": 2}, "HEAD_SEARCH_THREAD_DRIFT"),
    ({"torch_version": "wrong"}, "HEAD_SEARCH_RUNTIME_VERSION_DRIFT"),
    ({"ultralytics_version": "wrong"}, "HEAD_SEARCH_RUNTIME_VERSION_DRIFT"),
    ({"score_threshold": 0.8}, "HEAD_SEARCH_MODEL_DRIFT"),
    ({"model_id": "wrong"}, "HEAD_SEARCH_MODEL_DRIFT"),
])
def test_head_configuration_cannot_drift_from_bound_execution(tmp_path, change, code):
    from test_config_identity import campaign_fixture, config_module
    service = campaign_fixture(tmp_path)["head_service"]
    binding = SimpleNamespace(detector={
        "requested_device": "cuda", "allow_cpu_fallback": False,
        "model_id": "head-model", "weights_path": service["model"]["weights"]["path"],
        "weights_sha256": service["model"]["weights"]["sha256"], "image_size_px": 640,
        "torch_threads": 1, "torch_interop_threads": 1,
        "torch_version": "2.13.0+cu130", "ultralytics_version": "8.4.115"})
    versions = {"torch_version": "2.13.0+cu130", "ultralytics_version": "8.4.115"}
    config_module().verify_head_configuration(service, binding=binding, runtime_versions=versions)
    for name, value in change.items():
        if name in versions: versions[name] = value
        elif name in service: service[name] = value
        else: service["model"][name] = value
    with pytest.raises(ValueError, match=code):
        config_module().verify_head_configuration(service, binding=binding, runtime_versions=versions)


@pytest.mark.parametrize("threshold", [0.25, 0.8, 0.0, 1.0])
def test_explicit_threshold_reaches_actual_predict(tmp_path, threshold):
    weights = tmp_path / "weights.pt"
    weights.write_bytes(b"model")
    observed = []
    class Model:
        names = {0: "plastic_cup"}
        def predict(self, **kwargs):
            observed.append(kwargs)
            return [SimpleNamespace(boxes=SimpleNamespace(xyxy=np.empty((0, 4)),
                cls=np.empty(0), conf=np.empty(0)), masks=None)]
    cuda = SimpleNamespace(is_available=lambda: True)
    built = build_detector(DetectorFactoryOptions(backend="yolo_seg", requested_device="cuda",
        allow_cpu_fallback=False, yolo_weights_path=weights,
        yolo_weights_sha256=hashlib.sha256(b"model").hexdigest(), yolo_model_id="configured-id",
        yolo_imgsz=640, yolo_score_threshold=threshold),
        yolo_detector_factory=lambda **kwargs: YoloSegDetector(**kwargs,
            torch_api=SimpleNamespace(cuda=cuda), model_factory=lambda _: Model()))
    rgb = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
    result = built.detector.detect(DetectionFrame(rgb, 7, "head"), DetectionQuery("plastic_cup"))
    assert [call["conf"] for call in observed] == [threshold, threshold]
    np.testing.assert_array_equal(observed[-1]["source"], [[[3, 2, 1], [6, 5, 4]]])
    assert result.model_id == "configured-id"


@pytest.mark.parametrize("threshold", [True, -0.1, 1.1, float("nan"), float("inf"), "0.25"])
def test_invalid_threshold_rejected_before_model_load(tmp_path, threshold):
    with pytest.raises(ValueError, match="score_threshold"):
        YoloSegDetector(weights_path=tmp_path / "absent.pt", expected_sha256="a" * 64,
            requested_device="cuda", allow_cpu_fallback=False, model_id="m", imgsz=640,
            score_threshold=threshold)
