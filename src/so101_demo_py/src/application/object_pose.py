"""Application rules for selecting and localizing one requested object."""

from __future__ import annotations

import math

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionQuery,
)


class TargetSelectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TargetSelector:
    def select(
        self,
        batch: DetectionBatch,
        query: DetectionQuery,
        confidence_threshold: float,
    ) -> DetectionCandidate:
        if not math.isfinite(confidence_threshold) or not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be finite and in [0, 1]")
        matches = tuple(
            candidate
            for candidate in batch.candidates
            if candidate.class_id == query.class_id
            and candidate.confidence >= confidence_threshold
        )
        if not matches:
            raise TargetSelectionError("TARGET_NOT_FOUND")
        if len(matches) > 1:
            raise TargetSelectionError("TARGET_AMBIGUOUS")
        return matches[0]
