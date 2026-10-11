"""Constants, errors and the run specification, checkpoint, manifest and expectation records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Literal

from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    ProductionObservation,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RunKind,
    RunStatus,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.dataset.contracts import DatasetInventory
from so101_demo.perception_benchmark.timing import (
    ResourceSample,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")


_RECORD_NAME = re.compile(r"^(\d{6})\.json$")


_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


_SENSITIVE = re.compile(
    r"(?i)(api[_-]?(?:key|token)|access[_-]?token|token|password|secret)"
    r"\s*[:=]\s*\S+"
)


_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s:]+/?)+")


_RAW_RUN_KINDS = {
    RunKind.NON_FORMAL_DRY_RUN,
    RunKind.VAL_RAW,
    RunKind.TEST_RAW_FROZEN,
    RunKind.ORACLE_DIAGNOSTIC,
}


_OBSERVED_RUN_KINDS = {
    RunKind.TEST_PRODUCTION,
    RunKind.TEST_CALIBRATED,
    RunKind.TEST_CHARACTERIZATION,
}


_CANDIDATE_KEYS = {
    "candidate_id",
    "label",
    "bbox_xyxy",
    "mask",
    "ranking_score",
    "ranking_score_source",
    "class_confidence",
    "grounding_box_score",
    "grounding_text_score",
    "sam_quality",
}


_MASK_KEYS = {
    "relative_path",
    "sha256",
    "pixel_count",
    "image_width",
    "image_height",
}


_RUNTIME_PROVENANCE_KEYS = {
    "runtime_device",
    "runtime_name",
    "runtime_version",
    "weights_sha256",
    "environment",
}


_PHASE_TIMING_KEYS = {"grounding_ms", "sam_ms", "selector_ms"}


_TIMING_BREAKDOWN_KEYS = {
    "preprocess_ms",
    "dino_or_yolo_ms",
    "sam_ms",
    "postprocess_ms",
    "selector_ms",
    "total_ms",
}


_RESOURCE_SAMPLE_KEYS = {item.name for item in fields(ResourceSample)}


_RECORD_DOCUMENT_KEYS = {item.name for item in fields(PredictionRecord)} | {
    "platform",
    "model",
    "device",
    "dtype",
    "source_commit",
    "inventory_sha256",
    "collection_mode",
    "max_gpu_temperature_celsius",
    "timing_breakdown",
    "resource_samples",
    "irreversible_limits",
    "previous_record_sha256",
}


class RunIntegrityError(ValueError):
    """A stable fail-closed benchmark run integrity error."""


class _FatalRunError(RunIntegrityError):
    pass


class _ResourceStreamValidationError(_FatalRunError):
    pass


class _ThermalValidationError(_FatalRunError):
    pass


@dataclass(frozen=True, slots=True)
class RunEvidenceExpectation:
    """External anchors required to trust one persisted terminal run."""

    run_id: str
    run_kind: RunKind
    platform: Literal["macos", "linux"]
    model: Literal["yolo_seg", "grounded_sam"]
    device: Literal["mps", "cuda"]
    dtype: Literal["float32"]
    source_commit: str
    config_sha256: str
    threshold_lock_sha256: str | None
    model_id: str
    weights_sha256: str
    runtime_name: str
    runtime_version: str
    runtime_environment: Mapping[str, str]
    max_gpu_temperature_celsius: float | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "run_kind", RunKind(self.run_kind))
        except ValueError as error:
            raise ValueError("run_kind is unsupported") from error
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be non-empty")
        if self.platform not in {"macos", "linux"}:
            raise ValueError("platform is unsupported")
        if self.model not in {"yolo_seg", "grounded_sam"}:
            raise ValueError("model is unsupported")
        if self.device not in {"mps", "cuda"}:
            raise ValueError("device is unsupported")
        if self.dtype != "float32":
            raise ValueError("dtype must be float32")
        if _SOURCE_COMMIT.fullmatch(self.source_commit) is None:
            raise ValueError("source_commit must be a lowercase Git commit")
        for name in ("config_sha256", "weights_sha256"):
            if _SHA256.fullmatch(str(getattr(self, name))) is None:
                raise ValueError(f"{name} must be a lowercase SHA256 digest")
        if self.threshold_lock_sha256 is not None and _SHA256.fullmatch(
            self.threshold_lock_sha256
        ) is None:
            raise ValueError("threshold_lock_sha256 must be null or a SHA256 digest")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be non-empty")
        for name in ("runtime_name", "runtime_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.runtime_environment, Mapping):
            raise ValueError("runtime_environment must be a mapping")
        environment = dict(self.runtime_environment)
        if not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            and value
            for key, value in environment.items()
        ):
            raise ValueError("runtime_environment must map non-empty strings")
        object.__setattr__(
            self, "runtime_environment", MappingProxyType(environment)
        )
        if self.max_gpu_temperature_celsius is not None and (
            isinstance(self.max_gpu_temperature_celsius, bool)
            or not isinstance(self.max_gpu_temperature_celsius, (int, float))
            or not math.isfinite(float(self.max_gpu_temperature_celsius))
            or float(self.max_gpu_temperature_celsius) <= 0.0
        ):
            raise ValueError("max_gpu_temperature_celsius must be null or positive")


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_id: str
    run_kind: RunKind
    platform: Literal["macos", "linux"]
    model: Literal["yolo_seg", "grounded_sam"]
    device: Literal["mps", "cuda"]
    dtype: Literal["float32"]
    inventory: DatasetInventory
    config_sha256: str
    threshold_lock_sha256: str | None
    source_commit: str
    output_root: Path
    collection_mode: CollectionMode
    threshold_lock_path: Path | None = None
    max_gpu_temperature_celsius: float | None = None
    production_observer: Callable[[DetectionFrame], ProductionObservation] | None = None
    runtime_provenance: RuntimeProvenance | None = None
    production_candidate_mask_iou_threshold: float = 0.98

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "run_kind", RunKind(self.run_kind))
            object.__setattr__(
                self, "collection_mode", CollectionMode(self.collection_mode)
            )
        except ValueError as error:
            raise ValueError("run kind or collection mode is unsupported") from error
        object.__setattr__(self, "output_root", Path(self.output_root))
        if self.threshold_lock_path is not None:
            object.__setattr__(
                self, "threshold_lock_path", Path(self.threshold_lock_path)
            )
        threshold = self.production_candidate_mask_iou_threshold
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or not 0.0 < float(threshold) <= 1.0
        ):
            raise ValueError(
                "production_candidate_mask_iou_threshold must be in (0, 1]"
            )
        object.__setattr__(
            self,
            "production_candidate_mask_iou_threshold",
            float(threshold),
        )


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    run_id: str
    config_sha: str
    source_commit: str
    inventory_sha256: str
    records_dir: Path
    last_formal_sample_index: int
    last_record_sha256: str
    platform: str | None = None
    model: str | None = None
    model_id: str | None = None
    weights_sha256: str | None = None
    device: str | None = None
    dtype: str | None = None
    run_kind: RunKind | None = None
    threshold_lock_sha256: str | None = None
    collection_mode: CollectionMode | None = None
    runtime_name: str | None = None
    runtime_version: str | None = None
    runtime_environment: Mapping[str, str] | None = None
    max_gpu_temperature_celsius: float | None = None
    record_count: int = 0
    error_count: int = 0
    record_inventory_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records_dir", Path(self.records_dir))
        if self.run_kind is not None:
            try:
                object.__setattr__(self, "run_kind", RunKind(self.run_kind))
            except ValueError as error:
                raise ValueError("checkpoint run_kind is unsupported") from error
        if self.collection_mode is not None:
            try:
                object.__setattr__(
                    self,
                    "collection_mode",
                    CollectionMode(self.collection_mode),
                )
            except ValueError as error:
                raise ValueError("checkpoint collection_mode is unsupported") from error
        if self.runtime_environment is not None:
            object.__setattr__(
                self, "runtime_environment", dict(self.runtime_environment)
            )


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    run_kind: RunKind
    status: RunStatus
    platform: str
    model: str
    device: str
    dtype: str
    source_commit: str
    inventory_sha256: str
    config_sha256: str
    threshold_lock_sha256: str | None
    collection_mode: CollectionMode
    model_id: str
    weights_sha256: str
    runtime_name: str
    runtime_version: str
    runtime_environment: Mapping[str, str]
    max_gpu_temperature_celsius: float | None
    record_count: int
    error_count: int
    record_inventory_sha256: str
    record_chain_head_sha256: str | None
    started_at: str
    ended_at: str | None
    invalid_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_kind", RunKind(self.run_kind))
        object.__setattr__(self, "status", RunStatus(self.status))
        object.__setattr__(
            self, "collection_mode", CollectionMode(self.collection_mode)
        )
        object.__setattr__(
            self,
            "runtime_environment",
            MappingProxyType(dict(self.runtime_environment)),
        )


@dataclass(frozen=True, slots=True)
class _ClassifiedError:
    error_type: str
    summary: str
    timed_out: bool
    oom: bool
