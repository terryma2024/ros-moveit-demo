"""P1-1 (rereview 5), second half: the real ``DetectionBatch`` must become a CLOSED, serializable document.

The verdict's finding, verbatim: *"``MeasurementDetectorAdapter`` around line 93 returns ``detect()`` unchanged. The
real result is ``core/detection.py``'s ``DetectionBatch`` dataclass, but the driver embeds it in a document later
serialized by ordinary ``json.dumps()``. Tests return dictionaries and do not expose that protocol mismatch."*

So this file uses the **real** return type - a real ``DetectionBatch`` carrying a real ``DetectionCandidate`` whose
mask is a real ``numpy`` array - and asserts what the driver needs: the adapter's result can be canonicalized. It is
a RED until the adapter translates, and it keeps the real interface rather than substituting a dictionary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # noqa: E402

from so101_demo.act.task8_production_composition import (  # noqa: E402
    MeasurementDetectorAdapter, ProductionCompositionError,
)
from so101_demo.core.detection import DetectionBatch, DetectionCandidate  # noqa: E402

FRAME = np.zeros((48, 64, 3), dtype=np.uint8)


def _batch() -> DetectionBatch:
    """A real batch, of the real types, with the mask that makes it non-serializable as it stands."""

    # the REAL candidate validates its own mask: boolean dtype, and the shape must match the declared image
    mask = np.zeros((48, 64), dtype=bool)
    mask[10:20, 12:28] = True
    candidate = DetectionCandidate(
        instance_id="cup-1", class_id="plastic_cup", confidence=0.9,
        bbox_xyxy=(12.0, 10.0, 28.0, 20.0), mask=mask, source_stamp_ns=1_500_000_000,
        source_frame_id="wrist-1", image_width=64, image_height=48)
    return DetectionBatch(
        model_id="yolo-seg-v1", weights_sha256="a" * 64, runtime_device="cuda",        # RuntimeDevice is a Literal, not an enum
        inference_latency_ms=4.5, image_width=64, image_height=48, candidates=(candidate,))


class _RealDetector:
    """The production interface - ``detect(frame, query)`` - returning the production type."""

    def __init__(self):
        self.calls = []

    def detect(self, frame, query):
        self.calls.append((frame.shape, query))
        return _batch()


def _adapter():
    detector = _RealDetector()
    adapter = MeasurementDetectorAdapter(detector, frame_source=lambda request: FRAME)
    return adapter, detector


def test_the_adapters_result_is_a_closed_serializable_document():
    """The driver canonicalizes what the detector returns, so the adapter must make it canonicalizable."""

    adapter, detector = _adapter()
    result = adapter({"anchor": "default", "sample": 0})
    assert detector.calls, "the real detector interface was exercised"

    # the driver's own rule (`task8_measurement_driver._canonical`): ordinary json.dumps, sorted keys
    try:
        payload = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    except TypeError as error:  # the RED: a dataclass with an ndarray mask is not JSON-serializable
        pytest.fail(f"the adapter's result is not serializable by the driver's own canonicalizer: {error}")

    document = json.loads(payload)
    # and it is CLOSED and traceable: the batch's identity and geometry survive, and the mask is carried as a digest
    assert document["model_id"] == "yolo-seg-v1"
    assert document["weights_sha256"] == "a" * 64
    assert document["image_width"] == 64 and document["image_height"] == 48
    assert document["runtime_device"] in ("cuda", "CUDA")
    assert len(document["candidates"]) == 1
    candidate = document["candidates"][0]
    assert candidate["instance_id"] == "cup-1" and candidate["class_id"] == "plastic_cup"
    assert candidate["bbox_xyxy"] == [12.0, 10.0, 28.0, 20.0]
    assert candidate["source_stamp_ns"] == 1_500_000_000
    # the mask cannot travel as an array, so it travels as what a reader can verify: its shape and its digest
    assert candidate["mask_shape"] == [48, 64]
    assert len(candidate["mask_sha256"]) == 64


def test_an_object_the_composition_does_not_understand_is_refused_by_name():
    """Fail closed rather than storing something the driver would choke on later."""

    class _SomethingElse:
        def detect(self, frame, query):
            return {"not": "a batch"}

    adapter = MeasurementDetectorAdapter(_SomethingElse(), frame_source=lambda request: FRAME)
    with pytest.raises((ProductionCompositionError, ValueError)) as error:
        adapter({"anchor": "default", "sample": 0})
    assert "DETECTION" in str(error.value).upper(), str(error.value)
