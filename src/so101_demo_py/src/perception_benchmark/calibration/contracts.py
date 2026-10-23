"""Model names, outcomes, progress reporting and the box helpers of the threshold calibration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
import math
import re
import time
from typing import Callable, Literal

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    RawCandidate,
)

ModelName = Literal["yolo_seg", "grounded_sam"]


CalibrationOutcome = Literal["SAFE_CALIBRATED", "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"]


ThresholdConfig = "YoloThresholds | GroundedSamBenchmarkThresholds"


LOCK_SCHEMA_VERSION = "so101-threshold-lock/v1"


OBJECTIVE_VERSION = "joint-platform-val/v1"


TIE_BREAK_VERSION = "joint-platform-seven-level/v1"


_GRID_VERSIONS: dict[str, str] = {
    "yolo_seg": "yolo-seg-grid/v1",
    "grounded_sam": "grounded-sam-grid/v1",
}


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")


_TWO_DECIMAL = Decimal("0.01")


_AP_THRESHOLDS = tuple(value / 100 for value in range(50, 96, 5))


class CalibrationError(ValueError):
    """Stable fail-closed calibration or threshold-lock error."""


ProgressPhase = Literal["verify", "rehome", "precompute", "grid", "finalize"]


@dataclass(frozen=True, slots=True)
class CalibrationProgress:
    """One bounded calibration progress observation."""

    phase: ProgressPhase
    completed: int
    total: int
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if self.phase not in {"verify", "rehome", "precompute", "grid", "finalize"}:
            raise ValueError("calibration progress phase is invalid")
        if (
            type(self.completed) is not int
            or type(self.total) is not int
            or self.completed < 0
            or self.total <= 0
            or self.completed > self.total
        ):
            raise ValueError("calibration progress counts are invalid")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0.0:
            raise ValueError("calibration progress elapsed_seconds is invalid")


ProgressCallback = Callable[[CalibrationProgress], None]


def _emit_progress(
    callback: ProgressCallback | None,
    phase: ProgressPhase,
    completed: int,
    total: int,
    started_at: float,
) -> None:
    if callback is not None:
        callback(
            CalibrationProgress(
                phase,
                completed,
                total,
                max(0.0, time.monotonic() - started_at),
            )
        )


def _decimal_probability(name: str, value: object) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal with two decimal places")
    normalized = value.quantize(_TWO_DECIMAL)
    if normalized != value:
        raise ValueError(f"{name} must have at most two decimal places")
    if not Decimal("0.00") <= normalized <= Decimal("1.00"):
        raise ValueError(f"{name} must be in [0.00, 1.00]")
    return normalized


def _decimal_document(value: Decimal) -> str:
    return format(value, ".2f")


def _normalized_json(document: Mapping[str, object]) -> str:
    return canonical_json_bytes(dict(document)).decode("utf-8").removesuffix("\n")


def _box_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return float(intersection / (first_area + second_area - intersection))


def _deduplicate_boxes(
    candidates: Sequence[RawCandidate], threshold: Decimal
) -> tuple[RawCandidate, ...]:
    ordered = tuple(sorted(candidates, key=lambda item: (-item.ranking_score, item.candidate_id)))
    kept: list[RawCandidate] = []
    limit = float(threshold)
    for candidate in ordered:
        if all(_box_iou(candidate.bbox_xyxy, previous.bbox_xyxy) < limit for previous in kept):
            kept.append(candidate)
    return tuple(kept)
