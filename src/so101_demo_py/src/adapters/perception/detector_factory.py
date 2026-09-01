"""Validated construction for RGB-D detector backends."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.adapters.perception.model_runtime import RequestedDevice
from so101_demo.adapters.perception.yolo_seg import YoloSegDetector, verify_weights


DetectorBackend = Literal["yolo_seg", "grounded_sam"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DetectorPort(Protocol):
    runtime_device: str
    cold_start_latency_ms: float


@dataclass(frozen=True, slots=True)
class DetectorFactoryOptions:
    backend: DetectorBackend
    requested_device: RequestedDevice
    allow_cpu_fallback: bool
    yolo_weights_path: Path | None = None
    yolo_weights_sha256: str | None = None
    yolo_model_id: str | None = None
    yolo_imgsz: int | None = None
    grounded_model_root: Path | None = None
    grounded_manifest_sha256: str | None = None
    grounded_thresholds: GroundedSamThresholds | None = None


@dataclass(frozen=True, slots=True)
class BuiltDetector:
    detector: DetectorPort
    cold_start_latency_ms: float
    provenance_document: Mapping[str, Any]


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _validate_options(options: DetectorFactoryOptions) -> None:
    if options.backend not in {"yolo_seg", "grounded_sam"}:
        raise ValueError("backend configuration is unsupported")
    if options.requested_device not in {"auto", "cuda", "mps", "cpu"}:
        raise ValueError("backend configuration has an invalid device")
    if not isinstance(options.allow_cpu_fallback, bool):
        raise ValueError("backend configuration has an invalid CPU fallback")

    yolo_values = (
        options.yolo_weights_path,
        options.yolo_weights_sha256,
        options.yolo_model_id,
        options.yolo_imgsz,
    )
    grounded_values = (
        options.grounded_model_root,
        options.grounded_manifest_sha256,
        options.grounded_thresholds,
    )
    if options.backend == "yolo_seg":
        if any(value is not None for value in grounded_values) or any(
            value is None for value in yolo_values
        ):
            raise ValueError("backend configuration mixes or omits YOLO artifacts")
        if (
            not isinstance(options.yolo_weights_path, Path)
            or not options.yolo_weights_path.is_absolute()
            or options.yolo_weights_path.is_symlink()
            or not options.yolo_weights_path.is_file()
            or not _valid_sha256(options.yolo_weights_sha256)
            or not isinstance(options.yolo_model_id, str)
            or not options.yolo_model_id
            or isinstance(options.yolo_imgsz, bool)
            or not isinstance(options.yolo_imgsz, int)
            or options.yolo_imgsz <= 0
        ):
            raise ValueError("backend configuration has invalid YOLO artifacts")
        return
    if any(value is not None for value in yolo_values) or any(
        value is None for value in grounded_values
    ):
        raise ValueError("backend configuration mixes or omits Grounded SAM artifacts")
    if (
        not isinstance(options.grounded_model_root, Path)
        or not options.grounded_model_root.is_absolute()
        or not _valid_sha256(options.grounded_manifest_sha256)
        or not isinstance(options.grounded_thresholds, GroundedSamThresholds)
    ):
        raise ValueError("backend configuration has invalid Grounded SAM artifacts")


def _cold_start_latency(detector: DetectorPort) -> float:
    latency = detector.cold_start_latency_ms
    if not isinstance(latency, (int, float)) or isinstance(latency, bool):
        raise RuntimeError("detector cold-start latency is invalid")
    normalized = float(latency)
    if not math.isfinite(normalized) or normalized < 0.0:
        raise RuntimeError("detector cold-start latency is invalid")
    return normalized


def build_detector(
    options: DetectorFactoryOptions,
    *,
    yolo_detector_factory: Callable[..., DetectorPort] = YoloSegDetector,
    grounded_detector_factory: Callable[..., DetectorPort] = GroundedSamDetector,
) -> BuiltDetector:
    """Verify backend-specific artifacts and build exactly one detector."""

    _validate_options(options)
    if options.backend == "yolo_seg":
        verified_sha256 = verify_weights(
            options.yolo_weights_path, options.yolo_weights_sha256
        )
        detector = yolo_detector_factory(
            weights_path=options.yolo_weights_path,
            expected_sha256=verified_sha256,
            requested_device=options.requested_device,
            allow_cpu_fallback=options.allow_cpu_fallback,
            model_id=options.yolo_model_id,
            imgsz=options.yolo_imgsz,
        )
        return BuiltDetector(
            detector=detector,
            cold_start_latency_ms=_cold_start_latency(detector),
            provenance_document={
                "backend": "yolo_seg",
                "model_id": options.yolo_model_id,
                "weights_sha256": verified_sha256,
            },
        )

    bundle = verify_model_bundle(
        options.grounded_model_root, options.grounded_manifest_sha256
    )
    detector = grounded_detector_factory(
        bundle=bundle,
        thresholds=options.grounded_thresholds,
        requested_device=options.requested_device,
        allow_cpu_fallback=options.allow_cpu_fallback,
    )
    return BuiltDetector(
        detector=detector,
        cold_start_latency_ms=_cold_start_latency(detector),
        provenance_document={
            "backend": "grounded_sam",
            "pipeline_id": bundle.manifest["pipeline_id"],
            "manifest_sha256": bundle.manifest_sha256,
            "manifest": bundle.manifest,
        },
    )
