from __future__ import annotations

import numpy as np
import pytest

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
)


def _mask() -> np.ndarray:
    value = np.zeros((4, 6), dtype=bool)
    value[1:3, 2:5] = True
    return value


def _candidate(**overrides: object) -> DetectionCandidate:
    values: dict[str, object] = {
        "instance_id": "cup-0",
        "class_id": "plastic_cup",
        "confidence": 0.9,
        "bbox_xyxy": (2.0, 1.0, 5.0, 3.0),
        "mask": _mask(),
        "source_stamp_ns": 7,
        "source_frame_id": "task_camera_frame",
        "image_width": 6,
        "image_height": 4,
    }
    values.update(overrides)
    return DetectionCandidate(**values)  # type: ignore[arg-type]


def test_detection_frame_owns_read_only_rgb_copy() -> None:
    source = np.zeros((4, 6, 3), dtype=np.uint8)
    frame = DetectionFrame(source, 7, "task_camera_frame")

    source[0, 0] = 255

    assert frame.rgb8.shape == (4, 6, 3)
    assert frame.rgb8[0, 0].tolist() == [0, 0, 0]
    assert not frame.rgb8.flags.writeable


@pytest.mark.parametrize(
    ("rgb8", "stamp_ns", "frame_id", "message"),
    [
        (np.zeros((4, 6), dtype=np.uint8), 7, "camera", "rgb8 shape"),
        (np.zeros((4, 6, 3), dtype=np.float32), 7, "camera", "rgb8 dtype"),
        (np.zeros((4, 6, 3), dtype=np.uint8), 0, "camera", "stamp"),
        (np.zeros((4, 6, 3), dtype=np.uint8), 7, "", "frame_id"),
    ],
)
def test_detection_frame_rejects_invalid_source(
    rgb8: np.ndarray, stamp_ns: int, frame_id: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DetectionFrame(rgb8, stamp_ns, frame_id)


def test_detection_query_accepts_only_canonical_class() -> None:
    assert DetectionQuery("plastic_cup").class_id == "plastic_cup"
    for invalid in ("", "cup", "Plastic_Cup"):
        with pytest.raises(ValueError, match="class_id"):
            DetectionQuery(invalid)


def test_candidate_owns_read_only_boolean_mask_copy() -> None:
    source = _mask()
    candidate = _candidate(mask=source)

    source[:] = False

    assert int(candidate.mask.sum()) == 6
    assert not candidate.mask.flags.writeable


def test_candidate_rejects_mask_with_wrong_image_shape() -> None:
    with pytest.raises(ValueError, match="mask shape"):
        _candidate(mask=np.ones((2, 2), dtype=bool))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"instance_id": ""}, "instance_id"),
        ({"class_id": "Plastic-Cup"}, "class_id"),
        ({"confidence": float("nan")}, "confidence"),
        ({"confidence": -0.1}, "confidence"),
        ({"confidence": 1.1}, "confidence"),
        ({"bbox_xyxy": (2.0, 1.0, 2.0, 3.0)}, "bbox"),
        ({"bbox_xyxy": (-1.0, 1.0, 5.0, 3.0)}, "bbox"),
        ({"mask": np.ones((4, 6), dtype=np.uint8)}, "mask dtype"),
        ({"mask": np.zeros((4, 6), dtype=bool)}, "mask must contain"),
        ({"source_stamp_ns": 0}, "stamp"),
        ({"source_frame_id": ""}, "frame_id"),
        ({"image_width": 0}, "image dimensions"),
    ],
)
def test_candidate_rejects_invalid_fields(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _candidate(**overrides)


def test_batch_accepts_candidates_with_matching_frame_contract() -> None:
    batch = DetectionBatch(
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="mps",
        inference_latency_ms=12.5,
        image_width=6,
        image_height=4,
        candidates=(_candidate(),),
    )

    assert batch.candidates[0].instance_id == "cup-0"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"model_id": ""}, "model_id"),
        ({"weights_sha256": "A" * 64}, "weights_sha256"),
        ({"runtime_device": "auto"}, "runtime_device"),
        ({"inference_latency_ms": -1.0}, "inference_latency"),
        ({"image_width": 0}, "image dimensions"),
        (
            {
                "candidates": (
                    _candidate(instance_id="same"),
                    _candidate(instance_id="same"),
                )
            },
            "instance_id",
        ),
        (
            {
                "candidates": (
                    _candidate(
                        image_width=7,
                        mask=np.pad(_mask(), ((0, 0), (0, 1))),
                    ),
                )
            },
            "dimensions",
        ),
    ],
)
def test_batch_rejects_invalid_provenance_or_candidates(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "model_id": "plastic-cup-yolo11n-seg-v1",
        "weights_sha256": "a" * 64,
        "runtime_device": "cuda",
        "inference_latency_ms": 12.5,
        "image_width": 6,
        "image_height": 4,
        "candidates": (_candidate(),),
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        DetectionBatch(**values)  # type: ignore[arg-type]
