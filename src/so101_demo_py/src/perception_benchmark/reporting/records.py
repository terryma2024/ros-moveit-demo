"""Constants, validators and the sample, trace, aggregation, summary and evidence index records of a benchmark report."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.calibration.results import ThresholdLock
from so101_demo.perception_benchmark.comparison import (
    CrossPlatformSummary,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RawCandidate,
    RunStatus,
    TruthSample,
)
from so101_demo.perception_benchmark.decisions import (
    DecisionMetrics,
    ScenarioMetrics,
)
from so101_demo.perception_benchmark.metrics import (
    ConfidenceInterval,
    InstanceMetricSummary,
)
from so101_demo.perception_benchmark.timing import ResourceSample

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")


_SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
)


_FORMAL_PLATFORMS = ("linux", "macos")


_FORMAL_MODELS = ("yolo_seg", "grounded_sam")


_IOU_THRESHOLDS = tuple(value / 100.0 for value in range(50, 96, 5))


_TIMING_FIELDS = (
    "preprocess_ms",
    "dino_or_yolo_ms",
    "sam_ms",
    "postprocess_ms",
    "selector_ms",
    "total_ms",
)


_PAYLOAD_PATHS = (
    "metrics/summary.json",
    "metrics/per-scenario.csv",
    "metrics/per-image.csv",
    "metrics/cross-platform-mismatches.csv",
    "performance/latency.json",
    "performance/resources.json",
    "report/benchmark.md",
)


_INDEX_SEMANTICS = (
    "payload files only; evidence-index.json is excluded to avoid self-reference"
)


_INDEX_SCHEMA_VERSION = "so101-perception-benchmark/evidence-index/v1"


def _index_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("evidence path must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("evidence path must be a safe relative path")
    if value == "evidence-index.json":
        raise ValueError("evidence index cannot include itself")
    return value


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _mapping_proxy(value: Mapping[object, object]) -> Mapping[object, object]:
    return MappingProxyType(dict(value))


def _finite_nonnegative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating)):
        raise ValueError(f"{name} must be finite and nonnegative")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _optional_finite_nonnegative(name: str, value: object) -> float | None:
    if value is None:
        return None
    return _finite_nonnegative(name, value)


def _require_sha(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA256 digest")
    return value


def _require_source_commit(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_COMMIT.fullmatch(value) is None:
        raise ValueError("source_commit must be a lowercase Git commit")
    return value


def _existing_root(name: str, value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"{name} must be an existing directory") from error
    if not root.is_dir():
        raise ValueError(f"{name} must be an existing directory")
    return root


@dataclass(frozen=True, slots=True)
class ColdProcessSample:
    """One cold latency observation anchored to a provably fresh process."""

    process_id: str
    pid: int
    process_started_ns: int
    latency_ms: float
    runtime_name: str
    runtime_version: str
    weights_sha256: str
    executable_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.process_id, str) or not self.process_id:
            raise ValueError("cold process_id must be non-empty")
        if isinstance(self.pid, bool) or not isinstance(self.pid, int) or self.pid <= 0:
            raise ValueError("cold pid must be a positive integer")
        if (
            isinstance(self.process_started_ns, bool)
            or not isinstance(self.process_started_ns, int)
            or self.process_started_ns < 0
        ):
            raise ValueError("cold process_started_ns must be nonnegative")
        object.__setattr__(
            self, "latency_ms", _finite_nonnegative("cold latency_ms", self.latency_ms)
        )
        for name in ("runtime_name", "runtime_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"cold {name} must be non-empty")
        _require_sha("cold weights_sha256", self.weights_sha256)
        _require_sha("cold executable_sha256", self.executable_sha256)


@dataclass(frozen=True, slots=True)
class ResourceObservation:
    """One phase-tagged resource observation in a run trace."""

    phase: str
    monotonic_ns: int
    formal_sample_index: int | None
    sample: ResourceSample

    def __post_init__(self) -> None:
        if self.phase not in {"load", "warmup", "inference"}:
            raise ValueError("resource phase must be load, warmup, or inference")
        if (
            isinstance(self.monotonic_ns, bool)
            or not isinstance(self.monotonic_ns, int)
            or self.monotonic_ns < 0
        ):
            raise ValueError("resource monotonic_ns must be nonnegative")
        if self.formal_sample_index is not None and (
            isinstance(self.formal_sample_index, bool)
            or not isinstance(self.formal_sample_index, int)
            or self.formal_sample_index < 0
        ):
            raise ValueError("resource formal_sample_index must be null or nonnegative")
        if not isinstance(self.sample, ResourceSample):
            raise ValueError("resource observation sample must be a ResourceSample")


@dataclass(frozen=True, slots=True)
class ResourceTrace:
    """Ordered phase-tagged resource observations plus sampling provenance."""

    sampling_frequency_hz: float
    observations: tuple[ResourceObservation, ...]

    def __post_init__(self) -> None:
        frequency = _finite_nonnegative(
            "sampling_frequency_hz", self.sampling_frequency_hz
        )
        if frequency == 0.0:
            raise ValueError("sampling_frequency_hz must be positive")
        object.__setattr__(self, "sampling_frequency_hz", frequency)
        observations = tuple(self.observations)
        if not all(isinstance(item, ResourceObservation) for item in observations):
            raise ValueError("resource trace must contain ResourceObservation values")
        timestamps = [item.monotonic_ns for item in observations]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("resource observations must have unique ordered timestamps")
        object.__setattr__(self, "observations", observations)


@dataclass(frozen=True, slots=True)
class RunAggregationEvidence:
    """Immutable capability and safety evidence for one platform/model/config run.

    The legacy float/resource tuples exist only for explicit non-formal fixtures. Formal
    inputs must use fresh-process samples and a phase-tagged resource trace.
    """

    evidence_root: Path
    extended_record_documents: tuple[Mapping[str, object], ...]
    cold_process_samples: tuple[ColdProcessSample, ...] = ()
    resource_trace: ResourceTrace | None = None
    cold_latency_ms: tuple[float, ...] = ()
    resource_samples: tuple[ResourceSample, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_root", Path(self.evidence_root))
        documents = tuple(self.extended_record_documents)
        if not all(isinstance(document, Mapping) for document in documents):
            raise ValueError("extended_record_documents must contain mappings")
        object.__setattr__(
            self,
            "extended_record_documents",
            tuple(_freeze(document) for document in documents),
        )
        cold_processes = tuple(self.cold_process_samples)
        if not all(isinstance(sample, ColdProcessSample) for sample in cold_processes):
            raise ValueError("cold_process_samples must contain ColdProcessSample values")
        object.__setattr__(self, "cold_process_samples", cold_processes)
        if self.resource_trace is not None and not isinstance(
            self.resource_trace, ResourceTrace
        ):
            raise ValueError("resource_trace must be a ResourceTrace or null")
        object.__setattr__(
            self,
            "cold_latency_ms",
            tuple(
                _finite_nonnegative("cold_latency_ms", value)
                for value in self.cold_latency_ms
            ),
        )
        resources = tuple(self.resource_samples)
        if not all(isinstance(sample, ResourceSample) for sample in resources):
            raise ValueError("resource_samples must contain ResourceSample values")
        object.__setattr__(self, "resource_samples", resources)


def _freeze_record_mapping(
    value: Mapping[str, Mapping[str, Sequence[PredictionRecord]]],
) -> Mapping[str, Mapping[str, tuple[PredictionRecord, ...]]]:
    return MappingProxyType(
        {
            platform: MappingProxyType(
                {model: tuple(records) for model, records in models.items()}
            )
            for platform, models in value.items()
        }
    )


def _freeze_formal_mapping(
    value: Mapping[
        str, Mapping[str, Mapping[str, Sequence[PredictionRecord]]]
    ],
) -> Mapping[
    str, Mapping[str, Mapping[str, tuple[PredictionRecord, ...]]]
]:
    return MappingProxyType(
        {
            platform: MappingProxyType(
                {
                    model: MappingProxyType(
                        {
                            config: tuple(records)
                            for config, records in configs.items()
                        }
                    )
                    for model, configs in models.items()
                }
            )
            for platform, models in value.items()
        }
    )


@dataclass(frozen=True, slots=True)
class AggregationInput:
    """Complete explicit input; missing provenance is never inferred."""

    formal: bool
    source_commit: str
    dataset_archive_sha256: str
    test_inventory_sha256: str
    truth_evidence_root: Path
    truth_samples: tuple[TruthSample, ...]
    raw_frozen_records: Mapping[
        str, Mapping[str, tuple[PredictionRecord, ...]]
    ]
    formal_records: Mapping[
        str, Mapping[str, Mapping[str, tuple[PredictionRecord, ...]]]
    ]
    threshold_locks: Mapping[str, ThresholdLock]
    run_evidence: Mapping[tuple[str, str, str], RunAggregationEvidence]
    oracle_records: Mapping[
        str, Mapping[str, tuple[PredictionRecord, ...]]
    ]
    oracle_evidence: Mapping[tuple[str, str, str], RunAggregationEvidence]
    bootstrap_seed: int = 20260902
    bootstrap_repetitions: int = 10_000

    def __post_init__(self) -> None:
        if type(self.formal) is not bool:
            raise ValueError("formal must be boolean")
        object.__setattr__(self, "truth_evidence_root", Path(self.truth_evidence_root))
        truths = tuple(self.truth_samples)
        if not all(isinstance(sample, TruthSample) for sample in truths):
            raise ValueError("truth_samples must contain TruthSample values")
        object.__setattr__(self, "truth_samples", truths)
        object.__setattr__(
            self, "raw_frozen_records", _freeze_record_mapping(self.raw_frozen_records)
        )
        object.__setattr__(
            self, "formal_records", _freeze_formal_mapping(self.formal_records)
        )
        object.__setattr__(
            self, "oracle_records", _freeze_record_mapping(self.oracle_records)
        )
        object.__setattr__(
            self, "threshold_locks", MappingProxyType(dict(self.threshold_locks))
        )
        object.__setattr__(self, "run_evidence", _mapping_proxy(self.run_evidence))
        object.__setattr__(
            self, "oracle_evidence", _mapping_proxy(self.oracle_evidence)
        )
        if isinstance(self.bootstrap_seed, bool) or not isinstance(
            self.bootstrap_seed, int
        ):
            raise ValueError("bootstrap_seed must be an integer")
        if (
            isinstance(self.bootstrap_repetitions, bool)
            or not isinstance(self.bootstrap_repetitions, int)
            or self.bootstrap_repetitions <= 0
        ):
            raise ValueError("bootstrap_repetitions must be positive")


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    cold_p50_ms: float | None
    cold_p95_ms: float | None
    cold_p99_ms: float | None
    warmed_p50_ms: float | None
    warmed_p95_ms: float | None
    warmed_p99_ms: float | None
    phase_percentiles: Mapping[str, Mapping[str, float | None]]
    images_per_second: float | None


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    peak_rss_bytes: int | None
    peak_process_cpu_percent: float | None
    peak_device_allocated_bytes: int | None
    peak_device_reserved_bytes: int | None
    peak_gpu_utilization_percent: float | None
    peak_gpu_temperature_celsius: float | None
    peak_gpu_power_watts: float | None
    sampling_frequency_hz: float | None
    sampling_gaps_ms: tuple[float, ...]
    max_sampling_gap_ms: float | None
    tool_versions: Mapping[str, tuple[str, ...]]
    phase_summaries: Mapping[str, "ResourcePhaseSummary"]
    unavailable_reasons: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ResourcePhaseSummary:
    sample_count: int
    peak_rss_bytes: int | None
    peak_process_cpu_percent: float | None
    peak_device_allocated_bytes: int | None
    peak_device_reserved_bytes: int | None
    peak_gpu_utilization_percent: float | None
    peak_gpu_temperature_celsius: float | None
    peak_gpu_power_watts: float | None
    unavailable_reasons: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class MetricDetails:
    f1: float | None
    median_iou: float | None
    median_dice: float | None
    exact_count_accuracy: float | None
    fp_per_image: float | None
    fn_per_image: float | None
    confidence_intervals: Mapping[str, ConfidenceInterval]


@dataclass(frozen=True, slots=True)
class ScenarioMetricSummary:
    sample_count: int
    error_count: int
    timeout_count: int
    oom_count: int
    mask_ap50: float | None
    mask_ap50_95: float | None
    ap_confidence_intervals: Mapping[str, ConfidenceInterval]
    decision_metrics: DecisionMetrics
    decision_confidence_intervals: Mapping[str, ConfidenceInterval]
    instance_metrics: InstanceMetricSummary
    metric_details: MetricDetails
    safety_metrics: ScenarioMetrics
    confidence_intervals: Mapping[str, ConfidenceInterval]


@dataclass(frozen=True, slots=True)
class RawMetricSummary:
    sample_count: int
    mask_ap50: float | None
    mask_ap50_95: float | None
    ap_confidence_intervals: Mapping[str, ConfidenceInterval]
    candidate_count_distribution: Mapping[str, float]
    error_count: int
    instance_metrics: InstanceMetricSummary
    metric_details: MetricDetails
    scenarios: Mapping[str, ScenarioMetricSummary]


@dataclass(frozen=True, slots=True)
class FormalMetricSummary:
    sample_count: int
    error_count: int
    error_rate: float
    timeout_count: int
    oom_count: int
    mask_ap50: float | None
    mask_ap50_95: float | None
    ap_confidence_intervals: Mapping[str, ConfidenceInterval]
    decision_metrics: DecisionMetrics
    instance_metrics: InstanceMetricSummary
    metric_details: MetricDetails
    safety_confidence_intervals: Mapping[str, ConfidenceInterval]
    scenarios: Mapping[str, ScenarioMetricSummary]
    performance: PerformanceSummary


@dataclass(frozen=True, slots=True)
class PerImageSummary:
    platform: str
    model: str
    config: str
    run_kind: str
    formal_sample_index: int
    image_sha256: str
    scenario: str
    record_status: str
    truth_count: int
    candidate_count: int
    candidates: tuple[RawCandidate, ...]
    matched_count_at_50: int
    true_positive: int
    false_positive: int
    false_negative: int
    exact_count: bool
    decision: str
    error_type: str | None
    timed_out: bool
    oom: bool
    total_ms: float
    phase_timings_ms: Mapping[str, float | None]
    resource_observations: tuple[ResourceObservation, ...]
    resource_sampling_frequency_hz: float | None
    resource_sampling_gaps_ms: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    schema_version: str
    formal: bool
    qualification_status: str
    deployable: bool
    source_commit: str
    dataset_archive_sha256: str
    test_inventory_sha256: str
    threshold_lock_sha256_by_model: Mapping[str, str]
    raw_frozen_by_platform_model: Mapping[str, Mapping[str, RawMetricSummary]]
    formal_by_platform_model_config: Mapping[
        str, Mapping[str, Mapping[str, FormalMetricSummary]]
    ]
    oracle_diagnostic_by_platform_model: Mapping[
        str, Mapping[str, RawMetricSummary]
    ]
    cross_platform: Mapping[str, CrossPlatformSummary]
    performance: Mapping[str, PerformanceSummary]
    resource_summary: Mapping[str, ResourceSummary]
    per_image: tuple[PerImageSummary, ...]
    overall_status: RunStatus
    invalid_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "relative_path", _index_relative_path(self.relative_path)
        )
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("evidence size_bytes must be a nonnegative integer")
        _require_sha("evidence sha256", self.sha256)


@dataclass(frozen=True, slots=True)
class EvidenceIndex:
    schema_version: str
    payload_index_semantics: str
    entries: tuple[EvidenceEntry, ...]

    def __post_init__(self) -> None:
        if self.schema_version != _INDEX_SCHEMA_VERSION:
            raise ValueError("evidence index schema_version is unsupported")
        if self.payload_index_semantics != _INDEX_SEMANTICS:
            raise ValueError("evidence index semantics are unsupported")
        entries = tuple(self.entries)
        if not all(isinstance(entry, EvidenceEntry) for entry in entries):
            raise ValueError("evidence index entries must contain EvidenceEntry values")
        paths = [entry.relative_path for entry in entries]
        if len(paths) != len(set(paths)):
            raise ValueError("evidence index paths must be unique")
        object.__setattr__(self, "entries", entries)
