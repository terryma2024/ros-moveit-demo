from __future__ import annotations

import numpy as np
import pytest

from so101_demo.application.object_pose import TargetSelectionError, TargetSelector
from so101_demo.core.detection import DetectionBatch, DetectionCandidate, DetectionQuery


def _candidate(
    instance_id: str,
    *,
    class_id: str = "plastic_cup",
    confidence: float = 0.9,
) -> DetectionCandidate:
    mask = np.zeros((4, 6), dtype=bool)
    mask[1:3, 2:5] = True
    return DetectionCandidate(
        instance_id=instance_id,
        class_id=class_id,
        confidence=confidence,
        bbox_xyxy=(2.0, 1.0, 5.0, 3.0),
        mask=mask,
        source_stamp_ns=7,
        source_frame_id="task_camera_frame",
        image_width=6,
        image_height=4,
    )


def _batch(*candidates: DetectionCandidate) -> DetectionBatch:
    return DetectionBatch(
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="cuda",
        inference_latency_ms=10.0,
        image_width=6,
        image_height=4,
        candidates=tuple(candidates),
    )


@pytest.mark.parametrize(
    ("candidates", "code"),
    [
        ((), "TARGET_NOT_FOUND"),
        ((_candidate("0"), _candidate("1")), "TARGET_AMBIGUOUS"),
    ],
)
def test_selector_fails_closed_for_zero_or_multiple_matching_candidates(
    candidates: tuple[DetectionCandidate, ...], code: str
) -> None:
    with pytest.raises(TargetSelectionError, match=code) as caught:
        TargetSelector().select(
            _batch(*candidates), DetectionQuery("plastic_cup"), 0.50
        )

    assert caught.value.code == code


def test_selector_returns_the_only_matching_candidate() -> None:
    selected = TargetSelector().select(
        _batch(_candidate("bottle", class_id="orange_bottle"), _candidate("cup")),
        DetectionQuery("plastic_cup"),
        0.50,
    )

    assert selected.instance_id == "cup"


def test_selector_filters_confidence_before_counting_matches() -> None:
    selected = TargetSelector().select(
        _batch(_candidate("low", confidence=0.49), _candidate("accepted", confidence=0.50)),
        DetectionQuery("plastic_cup"),
        0.50,
    )

    assert selected.instance_id == "accepted"


@pytest.mark.parametrize("threshold", [float("nan"), -0.1, 1.1])
def test_selector_rejects_invalid_confidence_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="confidence_threshold"):
        TargetSelector().select(
            _batch(_candidate("cup")), DetectionQuery("plastic_cup"), threshold
        )
