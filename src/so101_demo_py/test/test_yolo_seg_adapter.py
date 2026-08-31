from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.adapters.perception.yolo_seg import (
    ModelSetupError,
    YoloResultError,
    YoloSegDetector,
    convert_yolo_result,
    select_runtime_device,
    verify_weights,
)
from so101_demo.core.detection import DetectionFrame, DetectionQuery


class _DeviceAvailability:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


def _torch_api(*, cuda: bool, mps: bool):
    return SimpleNamespace(
        cuda=_DeviceAvailability(cuda),
        backends=SimpleNamespace(mps=_DeviceAvailability(mps)),
    )


def _frame() -> DetectionFrame:
    return DetectionFrame(
        np.zeros((4, 6, 3), dtype=np.uint8),
        7,
        "task_camera_frame",
    )


def _result(
    *,
    boxes: np.ndarray | None = None,
    classes: np.ndarray | None = None,
    confidences: np.ndarray | None = None,
    masks: np.ndarray | None = None,
):
    return SimpleNamespace(
        boxes=SimpleNamespace(
            xyxy=np.array(
                [[0.0, 0.0, 3.0, 2.0], [3.0, 2.0, 6.0, 4.0]]
                if boxes is None
                else boxes,
                dtype=np.float64,
            ),
            cls=np.array([0.0, 0.0] if classes is None else classes, dtype=np.float64),
            conf=np.array(
                [0.8, 0.9] if confidences is None else confidences,
                dtype=np.float64,
            ),
        ),
        masks=SimpleNamespace(
            data=np.array(
                [
                    [[1.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
                    [[0.0, 0.0, 0.0], [0.0, 1.0, 1.0]],
                ]
                if masks is None
                else masks,
                dtype=np.float32,
            )
        ),
    )


def test_verify_weights_returns_actual_sha256(tmp_path: Path) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    expected = hashlib.sha256(b"weights-v1").hexdigest()

    assert verify_weights(weights, expected) == expected


def test_verify_weights_fails_closed_for_missing_or_mismatched_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pt"
    with pytest.raises(ModelSetupError, match="MODEL_UNAVAILABLE"):
        verify_weights(missing, "a" * 64)

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"wrong")
    with pytest.raises(ModelSetupError, match="WEIGHTS_HASH_MISMATCH"):
        verify_weights(weights, "a" * 64)

    link = tmp_path / "linked.pt"
    link.symlink_to(weights)
    with pytest.raises(ModelSetupError, match="MODEL_UNAVAILABLE"):
        verify_weights(link, hashlib.sha256(b"wrong").hexdigest())


@pytest.mark.parametrize(
    ("requested", "allow_cpu", "cuda", "mps", "expected"),
    [
        ("cuda", False, True, False, "cuda"),
        ("mps", False, False, True, "mps"),
        ("cpu", False, False, False, "cpu"),
        ("auto", False, True, True, "cuda"),
        ("auto", False, False, True, "mps"),
        ("auto", True, False, False, "cpu"),
    ],
)
def test_select_runtime_device_obeys_explicit_fallback_contract(
    requested: str,
    allow_cpu: bool,
    cuda: bool,
    mps: bool,
    expected: str,
) -> None:
    assert (
        select_runtime_device(requested, allow_cpu, _torch_api(cuda=cuda, mps=mps))
        == expected
    )


@pytest.mark.parametrize(
    ("requested", "allow_cpu", "cuda", "mps"),
    [
        ("cuda", True, False, True),
        ("mps", True, True, False),
        ("auto", False, False, False),
        ("tpu", True, True, True),
    ],
)
def test_unavailable_or_unknown_device_does_not_silently_fall_back(
    requested: str, allow_cpu: bool, cuda: bool, mps: bool
) -> None:
    with pytest.raises(ModelSetupError, match="DEVICE_UNAVAILABLE"):
        select_runtime_device(requested, allow_cpu, _torch_api(cuda=cuda, mps=mps))


def test_converter_preserves_all_instances_and_resizes_masks() -> None:
    batch = convert_yolo_result(
        _result(),
        _frame(),
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="mps",
        inference_latency_ms=12.0,
        class_names={0: "plastic_cup"},
    )

    assert [candidate.instance_id for candidate in batch.candidates] == ["0", "1"]
    assert [candidate.class_id for candidate in batch.candidates] == [
        "plastic_cup",
        "plastic_cup",
    ]
    assert [candidate.mask.shape for candidate in batch.candidates] == [(4, 6), (4, 6)]
    assert all(candidate.mask.any() for candidate in batch.candidates)


def test_converter_accepts_a_frame_with_no_detections() -> None:
    result = _result(
        boxes=np.empty((0, 4)),
        classes=np.empty((0,)),
        confidences=np.empty((0,)),
        masks=np.empty((0, 2, 3)),
    )

    batch = convert_yolo_result(
        result,
        _frame(),
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="cpu",
        inference_latency_ms=12.0,
        class_names={0: "plastic_cup"},
    )

    assert batch.candidates == ()


def test_converter_accepts_ultralytics_no_detection_result_without_masks() -> None:
    result = _result(
        boxes=np.empty((0, 4)),
        classes=np.empty((0,)),
        confidences=np.empty((0,)),
    )
    result.masks = None

    batch = convert_yolo_result(
        result,
        _frame(),
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="mps",
        inference_latency_ms=12.0,
        class_names={0: "plastic_cup"},
    )

    assert batch.candidates == ()


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (_result(confidences=np.array([0.8])), "counts"),
        (_result(confidences=np.array([float("nan"), 0.9])), "confidence"),
        (_result(classes=np.array([0.0, 1.0])), "class index"),
        (_result(boxes=np.array([[-1.0, 0.0, 3.0, 2.0], [3.0, 2.0, 6.0, 4.0]])), "bbox"),
        (_result(masks=np.zeros((2, 2, 3), dtype=np.float32)), "mask"),
    ],
)
def test_converter_rejects_corrupt_yolo_results(result: object, message: str) -> None:
    with pytest.raises(YoloResultError, match=message):
        convert_yolo_result(
            result,
            _frame(),
            model_id="plastic-cup-yolo11n-seg-v1",
            weights_sha256="a" * 64,
            runtime_device="cuda",
            inference_latency_ms=12.0,
            class_names={0: "plastic_cup"},
        )


def test_detector_loads_local_weights_warms_up_and_records_actual_device(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    expected = hashlib.sha256(b"weights-v1").hexdigest()
    predict_calls: list[dict[str, object]] = []

    class FakeModel:
        names = {0: "plastic_cup"}

        def predict(self, **kwargs):
            predict_calls.append(kwargs)
            return [_result(boxes=np.array([[0.0, 0.0, 3.0, 2.0]]), classes=np.array([0.0]), confidences=np.array([0.8]), masks=np.array([[[1.0, 1.0, 0.0], [0.0, 0.0, 0.0]]]))]

    factory_paths: list[str] = []

    def model_factory(path: str) -> FakeModel:
        factory_paths.append(path)
        return FakeModel()

    detector = YoloSegDetector(
        weights_path=weights,
        expected_sha256=expected,
        requested_device="mps",
        allow_cpu_fallback=False,
        model_id="plastic-cup-yolo11n-seg-v1",
        imgsz=640,
        torch_api=_torch_api(cuda=False, mps=True),
        model_factory=model_factory,
        monotonic_ns=iter([0, 10_000_000, 20_000_000, 32_000_000]).__next__,
    )

    batch = detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert factory_paths == [str(weights)]
    assert detector.runtime_device == "mps"
    assert detector.cold_start_latency_ms == 10.0
    assert batch.inference_latency_ms == 12.0
    assert [call["device"] for call in predict_calls] == ["mps", "mps"]
    assert predict_calls[0]["source"].shape == (640, 640, 3)
    assert predict_calls[1]["source"].shape == (4, 6, 3)


def test_detector_sets_a_candidate_floor_on_every_model_prediction(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    predict_calls: list[dict[str, object]] = []

    class FakeModel:
        names = {0: "plastic_cup"}

        def predict(self, **kwargs):
            predict_calls.append(kwargs)
            return [
                _result(
                    boxes=np.array([[0.0, 0.0, 3.0, 2.0]]),
                    classes=np.array([0.0]),
                    confidences=np.array([0.8]),
                    masks=np.array(
                        [[[1.0, 1.0, 0.0], [0.0, 0.0, 0.0]]]
                    ),
                )
            ]

    detector = YoloSegDetector(
        weights_path=weights,
        expected_sha256=hashlib.sha256(b"weights-v1").hexdigest(),
        requested_device="mps",
        allow_cpu_fallback=False,
        model_id="plastic-cup-yolo11n-seg-v1",
        imgsz=640,
        torch_api=_torch_api(cuda=False, mps=True),
        model_factory=lambda _: FakeModel(),
    )
    detector.detect(_frame(), DetectionQuery("plastic_cup"))

    assert [call["conf"] for call in predict_calls] == [0.25, 0.25]
