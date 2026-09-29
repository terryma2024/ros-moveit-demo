"""P1-1 RED/GREEN - the bottom-io frame must be what the REAL detector declares.

The verdict's P1-1: *"``task8_bottom_io`` 的 frame 必须返回真实 YoloSegDetector 所需的 DetectionFrame（含 rgb8、真实
时间戳和 frame identity），不能返回 ndarray"*.

Two facts are asserted here rather than assumed:

* what the real detector declares - read from ``YoloSegDetector.detect``'s own signature, so the contract cannot drift
  away from this test;
* what the bottom-io frame source actually returns - rendered through the real MuJoCo scene with the real head camera,
  then handed to the production ``MeasurementDetectorAdapter``, which is the object the driver calls.

The detector is the ONE boundary ``_bottom_io_from_seam`` says the success test may stand in for, so the double below
enforces the real declaration instead of loosening it: it refuses anything that is not a ``DetectionFrame``.
"""

from __future__ import annotations

import inspect
import os
import typing
from pathlib import Path

import pytest

os.environ.setdefault("MUJOCO_GL", "egl")

from so101_demo.core.detection import (  # noqa: E402
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
)


def _scene_path() -> Path:
    from ament_index_python.packages import get_package_share_directory

    return Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"


def test_the_real_detector_declares_a_detection_frame() -> None:
    """The contract this test enforces is the production one, read from the production signature."""

    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

    signature = inspect.signature(YoloSegDetector.detect)
    assert "frame" in signature.parameters, list(signature.parameters)
    # the module uses `from __future__ import annotations`, so the annotation is a string until it is resolved
    resolved = typing.get_type_hints(YoloSegDetector.detect)["frame"]
    assert resolved is DetectionFrame, f"YoloSegDetector.detect(frame=...) resolves to {resolved!r}"


class _DetectorEnforcingTheDeclaration:
    """Stands in for the detector FACTORY only - the boundary the seam documents - and enforces its signature."""

    def __init__(self) -> None:
        self.seen: list[DetectionFrame] = []

    def detect(self, frame, query):
        assert isinstance(frame, DetectionFrame), (
            f"the bottom-io frame reached the detector as {type(frame).__name__}, not DetectionFrame")
        assert frame.rgb8.dtype.name == "uint8", frame.rgb8.dtype
        assert frame.rgb8.ndim == 3 and frame.rgb8.shape[2] == 3, frame.rgb8.shape
        assert frame.source_stamp_ns > 0, frame.source_stamp_ns
        assert frame.source_frame_id, frame.source_frame_id
        assert isinstance(query, DetectionQuery), type(query).__name__
        self.seen.append(frame)
        # the REAL production return type: `_serializable_detection` accepts only a `DetectionBatch`, and refuses
        # anything else by name (`PRODUCTION_DETECTION_RESULT_UNSUPPORTED`). The candidate echoes the frame's own
        # stamp and frame id, because that is what a detector reports about the frame it was handed.
        import numpy as np

        mask = np.zeros((frame.image_height, frame.image_width), dtype=bool)
        mask[frame.image_height // 4:frame.image_height // 2, frame.image_width // 4:frame.image_width // 2] = True
        candidate = DetectionCandidate(
            instance_id="p1-1-double-1", class_id="plastic_cup", confidence=0.75,
            bbox_xyxy=(frame.image_width // 4, frame.image_height // 4,
                       frame.image_width // 2, frame.image_height // 2),
            image_width=frame.image_width, image_height=frame.image_height,
            mask=mask, source_stamp_ns=frame.source_stamp_ns, source_frame_id=frame.source_frame_id)
        return DetectionBatch(
            model_id="p1-1-contract-double", weights_sha256="a" * 64, runtime_device="cuda",
            inference_latency_ms=0.0, image_width=frame.image_width, image_height=frame.image_height,
            candidates=(candidate,))


def test_the_bottom_io_frame_source_returns_a_detection_frame() -> None:
    """RED before the fix: the source returned ``renderer.render()`` - a bare ndarray."""

    from so101_demo.act.task8_bottom_io import ModelFrameSource

    source = ModelFrameSource(_scene_path())
    try:
        frame = source()
        assert isinstance(frame, DetectionFrame), (
            f"ModelFrameSource returned {type(frame).__name__}; the real detector declares DetectionFrame")
    finally:
        source.close()


def test_the_production_adapter_carries_that_frame_to_the_detector() -> None:
    """The object the driver actually calls, with the real frame source and a contract-enforcing detector."""

    from so101_demo.act.task8_bottom_io import ModelFrameSource
    from so101_demo.act.task8_production_composition import MeasurementDetectorAdapter

    detector = _DetectorEnforcingTheDeclaration()
    source = ModelFrameSource(_scene_path())
    try:
        adapter = MeasurementDetectorAdapter(detector, frame_source=source)
        result = adapter({"camera": "head_camera"})
        assert len(detector.seen) == 1, "the detector must have been handed exactly one frame"
        # the CLOSED translation: fixed keys, no numpy, the mask reduced to shape + digest
        assert set(result) == {"model_id", "weights_sha256", "runtime_device", "inference_latency_ms",
                               "image_width", "image_height", "candidates"}, sorted(result)
        assert result["runtime_device"] == "cuda"
        (candidate_document,) = result["candidates"]
        assert candidate_document["instance_id"] == "p1-1-double-1"
        assert candidate_document["class_id"] == "plastic_cup"
        assert candidate_document["mask_shape"] == [detector.seen[0].image_height, detector.seen[0].image_width]
        assert len(candidate_document["mask_sha256"]) == 64
        assert not any(hasattr(value, "dtype") for value in candidate_document.values()), "no numpy in the document"
    finally:
        source.close()
