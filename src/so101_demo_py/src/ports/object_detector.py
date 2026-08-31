"""Port for RGB-only instance segmentation adapters."""

from __future__ import annotations

from typing import Protocol

from so101_demo.core.detection import DetectionBatch, DetectionFrame, DetectionQuery


class DetectorPort(Protocol):
    def detect(
        self,
        frame: DetectionFrame,
        query: DetectionQuery,
    ) -> DetectionBatch: ...
