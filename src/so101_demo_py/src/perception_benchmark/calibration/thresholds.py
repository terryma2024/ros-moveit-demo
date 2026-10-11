"""The YOLO and Grounded SAM thresholds and their grids."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
import math

from so101_demo.perception_benchmark.calibration.contracts import (
    _TWO_DECIMAL,
    _decimal_document,
    _decimal_probability,
    _deduplicate_boxes,
    _normalized_json,
)
from so101_demo.perception_benchmark.contracts import (
    RawCandidate,
)


@dataclass(frozen=True, slots=True)
class YoloThresholds:
    conf: Decimal
    nms_iou: Decimal
    target_confidence_threshold: Decimal
    imgsz: int = 640

    def __post_init__(self) -> None:
        for name in ("conf", "nms_iou", "target_confidence_threshold"):
            object.__setattr__(self, name, _decimal_probability(name, getattr(self, name)))
        if type(self.imgsz) is not int or self.imgsz != 640:
            raise ValueError("imgsz must be the fixed integer 640")

    def to_document(self) -> dict[str, object]:
        return {
            "conf": _decimal_document(self.conf),
            "nms_iou": _decimal_document(self.nms_iou),
            "target_confidence_threshold": _decimal_document(self.target_confidence_threshold),
            "imgsz": self.imgsz,
        }

    @property
    def normalized_json(self) -> str:
        return _normalized_json(self.to_document())

    @property
    def safety_preference_key(self) -> tuple[Decimal, ...]:
        return (-self.conf, -self.target_confidence_threshold, self.nms_iou)

    def filter_candidates(self, candidates: tuple[RawCandidate, ...]) -> tuple[RawCandidate, ...]:
        class_filtered = tuple(
            candidate
            for candidate in candidates
            if candidate.class_confidence is not None
            and candidate.class_confidence >= float(self.conf)
        )
        deduplicated = _deduplicate_boxes(class_filtered, self.nms_iou)
        return tuple(
            candidate
            for candidate in deduplicated
            if candidate.ranking_score >= float(self.target_confidence_threshold)
        )


@dataclass(frozen=True, slots=True)
class GroundedSamBenchmarkThresholds:
    box_threshold: Decimal
    text_threshold: Decimal
    sam_quality: Decimal
    target_confidence_threshold: Decimal
    duplicate_iou: Decimal = Decimal("0.85")
    min_mask_pixels: int = 64
    max_mask_area_ratio: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        for name in (
            "box_threshold",
            "text_threshold",
            "sam_quality",
            "target_confidence_threshold",
            "duplicate_iou",
            "max_mask_area_ratio",
        ):
            object.__setattr__(self, name, _decimal_probability(name, getattr(self, name)))
        if self.duplicate_iou != Decimal("0.85"):
            raise ValueError("duplicate_iou must be fixed at 0.85")
        if type(self.min_mask_pixels) is not int or self.min_mask_pixels != 64:
            raise ValueError("min_mask_pixels must be the fixed integer 64")
        if self.max_mask_area_ratio != Decimal("0.50"):
            raise ValueError("max_mask_area_ratio must be fixed at 0.50")

    def to_document(self) -> dict[str, object]:
        return {
            "box_threshold": _decimal_document(self.box_threshold),
            "text_threshold": _decimal_document(self.text_threshold),
            "sam_quality": _decimal_document(self.sam_quality),
            "target_confidence_threshold": _decimal_document(self.target_confidence_threshold),
            "duplicate_iou": _decimal_document(self.duplicate_iou),
            "min_mask_pixels": self.min_mask_pixels,
            "max_mask_area_ratio": _decimal_document(self.max_mask_area_ratio),
        }

    @property
    def normalized_json(self) -> str:
        return _normalized_json(self.to_document())

    @property
    def safety_preference_key(self) -> tuple[Decimal, ...]:
        return (
            -self.box_threshold,
            -self.text_threshold,
            -self.sam_quality,
            -self.target_confidence_threshold,
        )

    def filter_candidates(self, candidates: tuple[RawCandidate, ...]) -> tuple[RawCandidate, ...]:
        grounding_filtered = tuple(
            candidate
            for candidate in candidates
            if candidate.grounding_box_score is not None
            and candidate.grounding_text_score is not None
            and candidate.grounding_box_score >= float(self.box_threshold)
            and candidate.grounding_text_score >= float(self.text_threshold)
        )
        deduplicated = _deduplicate_boxes(grounding_filtered, self.duplicate_iou)
        return tuple(
            candidate
            for candidate in deduplicated
            if candidate.sam_quality is not None
            and candidate.sam_quality >= float(self.sam_quality)
            and candidate.mask.pixel_count >= self.min_mask_pixels
            and (
                candidate.mask.pixel_count
                / (candidate.mask.image_width * candidate.mask.image_height)
            )
            <= float(self.max_mask_area_ratio)
            and candidate.ranking_score >= float(self.target_confidence_threshold)
        )


def decimal_range(start: str, stop: str, step: str) -> tuple[Decimal, ...]:
    current = Decimal(start)
    end = Decimal(stop)
    increment = Decimal(step)
    if increment <= 0:
        raise ValueError("step must be positive")
    values: list[Decimal] = []
    while current <= end:
        values.append(current.quantize(_TWO_DECIMAL))
        current += increment
    return tuple(values)


_GROUNDING_PREFIX_GRID = tuple(
    product(
        decimal_range("0.05", "0.90", "0.05"),
        decimal_range("0.05", "0.50", "0.05"),
    )
)


def enumerate_yolo_grid() -> Iterator[YoloThresholds]:
    for conf, nms_iou, selector in product(
        decimal_range("0.05", "0.95", "0.05"),
        decimal_range("0.30", "0.90", "0.10"),
        decimal_range("0.05", "0.95", "0.05"),
    ):
        yield YoloThresholds(conf, nms_iou, selector, 640)


def enumerate_grounded_sam_grid() -> Iterator[GroundedSamBenchmarkThresholds]:
    for box, text, sam, selector in product(
        decimal_range("0.05", "0.90", "0.05"),
        decimal_range("0.05", "0.50", "0.05"),
        decimal_range("0.50", "0.95", "0.05"),
        decimal_range("0.05", "0.90", "0.05"),
    ):
        yield GroundedSamBenchmarkThresholds(
            box,
            text,
            sam,
            selector,
            Decimal("0.85"),
            64,
            Decimal("0.50"),
        )


def _optional_probability(name: str, value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be null or a finite probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be null or a finite probability")
    return result


def _required_probability(name: str, value: object) -> float:
    result = _optional_probability(name, value)
    if result is None:
        raise ValueError(f"{name} must be a finite probability")
    return result
