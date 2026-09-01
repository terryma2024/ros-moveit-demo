"""Pure, deterministic Grounding DINO and SAM result post-processing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Sequence, cast

import numpy as np

from so101_demo.core.detection import DetectionCandidate, DetectionFrame, DetectionQuery


class GroundedSamResultError(ValueError):
    """A model-result contract violation with a stable machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _require_probability(name: str, value: object) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite probability")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be a finite probability")
    return normalized


def _require_positive_integer(name: str, value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


@dataclass(frozen=True, slots=True)
class GroundedSamThresholds:
    box_threshold: float
    text_threshold: float
    duplicate_iou: float
    max_candidates: int
    sam_quality: float
    min_mask_pixels: int
    max_mask_area_ratio: float

    def __post_init__(self) -> None:
        for name in ("box_threshold", "text_threshold", "duplicate_iou", "sam_quality"):
            object.__setattr__(self, name, _require_probability(name, getattr(self, name)))
        object.__setattr__(
            self, "max_candidates", _require_positive_integer("max_candidates", self.max_candidates)
        )
        object.__setattr__(
            self, "min_mask_pixels", _require_positive_integer("min_mask_pixels", self.min_mask_pixels)
        )
        max_mask_area_ratio = _require_probability(
            "max_mask_area_ratio", self.max_mask_area_ratio
        )
        if max_mask_area_ratio <= 0.0:
            raise ValueError("max_mask_area_ratio must be greater than zero")
        object.__setattr__(self, "max_mask_area_ratio", max_mask_area_ratio)

    @classmethod
    def defaults(cls) -> "GroundedSamThresholds":
        return cls(
            box_threshold=0.35,
            text_threshold=0.25,
            duplicate_iou=0.85,
            max_candidates=16,
            sam_quality=0.75,
            min_mask_pixels=64,
            max_mask_area_ratio=0.50,
        )


@dataclass(frozen=True, slots=True)
class GroundingProposal:
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float

    def __post_init__(self) -> None:
        if len(self.bbox_xyxy) != 4:
            raise ValueError("bbox_xyxy must contain four values")
        bbox = tuple(float(value) for value in self.bbox_xyxy)
        if not all(math.isfinite(value) for value in bbox):
            raise ValueError("bbox_xyxy must contain finite values")
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise ValueError("bbox_xyxy must have positive area")
        object.__setattr__(self, "bbox_xyxy", cast(tuple[float, float, float, float], bbox))
        object.__setattr__(self, "confidence", _require_probability("confidence", self.confidence))


def _contract_error(detail: str) -> GroundedSamResultError:
    return GroundedSamResultError("RESULT_CONTRACT_INVALID", detail)


def prompt_for_query(query: DetectionQuery) -> str:
    if not isinstance(query, DetectionQuery) or query.class_id != "plastic_cup":
        raise GroundedSamResultError("QUERY_UNSUPPORTED", "only plastic_cup is supported")
    return "plastic cup."


def _as_float_array(value: Any, name: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise _contract_error(f"{name} must be numeric") from error
    if not np.isfinite(array).all():
        raise _contract_error(f"{name} must contain only finite values")
    return array


def _iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / (first_area + second_area - intersection)


def convert_grounding_results(
    boxes: Any,
    scores: Any,
    labels: Sequence[str],
    frame: DetectionFrame,
    query: DetectionQuery,
    thresholds: GroundedSamThresholds,
) -> tuple[GroundingProposal, ...]:
    prompt_for_query(query)
    box_array = _as_float_array(boxes, "boxes")
    score_array = _as_float_array(scores, "scores")
    if box_array.ndim != 2 or box_array.shape[1:] != (4,):
        raise _contract_error("boxes must have shape (object_count, 4)")
    if score_array.ndim != 1:
        raise _contract_error("scores must have shape (object_count,)")
    count = int(box_array.shape[0])
    if count > thresholds.max_candidates:
        raise _contract_error("object_count exceeds max_candidates")
    if len(score_array) != count or len(labels) != count:
        raise _contract_error("boxes, scores, and labels must have the same object_count")
    if any(not isinstance(label, str) for label in labels):
        raise _contract_error("labels must contain strings")
    if np.any(score_array < 0.0) or np.any(score_array > 1.0):
        raise _contract_error("scores must be probabilities")

    normalized: list[GroundingProposal] = []
    for index, raw_bbox in enumerate(box_array):
        x_min, y_min, x_max, y_max = (float(value) for value in raw_bbox)
        if x_min >= x_max or y_min >= y_max:
            raise _contract_error(f"box {index} is degenerate")
        clipped = (
            min(max(x_min, 0.0), float(frame.image_width)),
            min(max(y_min, 0.0), float(frame.image_height)),
            min(max(x_max, 0.0), float(frame.image_width)),
            min(max(y_max, 0.0), float(frame.image_height)),
        )
        if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
            raise _contract_error(f"box {index} is outside the frame")
        if labels[index] != "plastic cup" or score_array[index] < thresholds.box_threshold:
            continue
        normalized.append(GroundingProposal(clipped, float(score_array[index])))

    normalized.sort(
        key=lambda proposal: (
            -proposal.confidence,
            proposal.bbox_xyxy[0],
            proposal.bbox_xyxy[1],
            proposal.bbox_xyxy[2],
            proposal.bbox_xyxy[3],
        )
    )
    deduplicated: list[GroundingProposal] = []
    for proposal in normalized:
        if all(_iou(proposal.bbox_xyxy, kept.bbox_xyxy) <= thresholds.duplicate_iou for kept in deduplicated):
            deduplicated.append(proposal)
    return tuple(deduplicated)


def _validate_sam_arrays(
    masks: Any,
    quality_scores: Any,
    object_count: int,
    frame: DetectionFrame,
) -> tuple[np.ndarray, np.ndarray]:
    mask_array = np.asarray(masks)
    if mask_array.ndim != 4 or mask_array.shape[0] != object_count:
        raise _contract_error("masks must have shape (object_count, mask_count, height, width)")
    if mask_array.shape[1] <= 0 or mask_array.shape[2:] != (
        frame.image_height,
        frame.image_width,
    ):
        raise _contract_error("masks must have shape (object_count, mask_count, height, width)")
    if not (np.issubdtype(mask_array.dtype, np.bool_) or np.issubdtype(mask_array.dtype, np.number)):
        raise _contract_error("masks must be boolean or numeric")
    if not np.isfinite(mask_array).all():
        raise _contract_error("masks must contain only finite values")
    quality_array = _as_float_array(quality_scores, "quality_scores")
    if quality_array.shape != mask_array.shape[:2]:
        raise _contract_error("quality_scores must have shape (object_count, mask_count)")
    if np.any(quality_array < 0.0) or np.any(quality_array > 1.0):
        raise _contract_error("quality_scores must be probabilities")
    return mask_array, quality_array


def _proposal_is_valid(proposal: GroundingProposal, frame: DetectionFrame) -> bool:
    x_min, y_min, x_max, y_max = proposal.bbox_xyxy
    return (
        0.0 <= x_min < x_max <= frame.image_width
        and 0.0 <= y_min < y_max <= frame.image_height
        and math.isfinite(proposal.confidence)
        and 0.0 <= proposal.confidence <= 1.0
    )


def _mask_inside_box_ratio(mask: np.ndarray, bbox: tuple[float, float, float, float]) -> float:
    x_min, y_min, x_max, y_max = bbox
    x_start = max(0, int(math.floor(x_min)))
    y_start = max(0, int(math.floor(y_min)))
    x_stop = min(mask.shape[1], int(math.ceil(x_max)))
    y_stop = min(mask.shape[0], int(math.ceil(y_max)))
    return float(mask[y_start:y_stop, x_start:x_stop].sum()) / float(mask.sum())


def convert_sam_results(
    proposals: Sequence[GroundingProposal],
    masks: Any,
    quality_scores: Any,
    frame: DetectionFrame,
    thresholds: GroundedSamThresholds,
) -> tuple[DetectionCandidate, ...]:
    proposals = tuple(proposals)
    if any(not isinstance(proposal, GroundingProposal) or not _proposal_is_valid(proposal, frame) for proposal in proposals):
        raise _contract_error("proposals must be valid, in-frame GroundingProposal values")
    mask_array, quality_array = _validate_sam_arrays(
        masks, quality_scores, len(proposals), frame
    )
    accepted: list[tuple[GroundingProposal, np.ndarray, float]] = []
    frame_area = frame.image_width * frame.image_height
    for object_index, proposal in enumerate(proposals):
        mask_index = int(np.argmax(quality_array[object_index]))
        quality = float(quality_array[object_index, mask_index])
        mask = np.asarray(mask_array[object_index, mask_index] >= 0.5, dtype=bool)
        selected_pixels = int(mask.sum())
        if quality < thresholds.sam_quality:
            continue
        if selected_pixels < thresholds.min_mask_pixels:
            continue
        if selected_pixels / frame_area > thresholds.max_mask_area_ratio:
            continue
        if _mask_inside_box_ratio(mask, proposal.bbox_xyxy) < 0.80:
            continue
        accepted.append((proposal, mask, quality))

    return tuple(
        DetectionCandidate(
            instance_id=f"grounded-sam-{index:03d}",
            class_id="plastic_cup",
            confidence=proposal.confidence,
            bbox_xyxy=proposal.bbox_xyxy,
            mask=mask,
            source_stamp_ns=frame.source_stamp_ns,
            source_frame_id=frame.source_frame_id,
            image_width=frame.image_width,
            image_height=frame.image_height,
            segmentation_quality=quality,
        )
        for index, (proposal, mask, quality) in enumerate(accepted)
    )
