"""Fail-closed benchmark aggregation and deterministic report publication."""

from __future__ import annotations

import csv
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
import io
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.calibration import ThresholdLock
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    read_mask,
    sha256_bytes,
)
from so101_demo.perception_benchmark.comparison import (
    CrossPlatformSummary,
    compare_platforms,
)
from so101_demo.perception_benchmark.contracts import (
    MODEL_ID_BY_NAME,
    SCHEMA_VERSION,
    DecisionOutput,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RunStatus,
    TruthSample,
)
from so101_demo.perception_benchmark.decisions import (
    DecisionMetrics,
    ScenarioMetrics,
    aggregate_decisions,
    aggregate_scenarios,
)
from so101_demo.perception_benchmark.matching import (
    MaskMatch,
    maximize_mask_iou_assignment,
)
from so101_demo.perception_benchmark.metrics import (
    ConfidenceInterval,
    ImageMetricInput,
    InstanceMetricSummary,
    compute_ap,
    interpolated_ap,
    summarize_image_metrics,
    _thresholded_match_count,
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
    """Task 8-only immutable evidence for one platform/model/config run.

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


@dataclass(frozen=True, slots=True)
class EvidenceIndex:
    schema_version: str
    payload_index_semantics: str
    entries: tuple[EvidenceEntry, ...]


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if isinstance(quantile, bool) or not isinstance(quantile, (int, float)):
        raise ValueError("quantile must be in [0, 1]")
    normalized = float(quantile)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError("quantile must be in [0, 1]")
    finite = np.asarray(
        [float(value) for value in values if math.isfinite(float(value))],
        dtype=np.float64,
    )
    return (
        None
        if finite.size == 0
        else float(np.quantile(finite, normalized, method="linear"))
    )


def _candidate_document(candidate: RawCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "label": candidate.label,
        "bbox_xyxy": list(candidate.bbox_xyxy),
        "mask": {
            "relative_path": candidate.mask.relative_path,
            "sha256": candidate.mask.sha256,
            "pixel_count": candidate.mask.pixel_count,
            "image_width": candidate.mask.image_width,
            "image_height": candidate.mask.image_height,
        },
        "ranking_score": candidate.ranking_score,
        "ranking_score_source": candidate.ranking_score_source,
        "class_confidence": candidate.class_confidence,
        "grounding_box_score": candidate.grounding_box_score,
        "grounding_text_score": candidate.grounding_text_score,
        "sam_quality": candidate.sam_quality,
    }


def _record_document(record: PredictionRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "schema_version": record.schema_version,
        "run_kind": record.run_kind.value,
        "record_status": record.record_status.value,
        "formal_sample_index": record.formal_sample_index,
        "split": record.split,
        "scenario": record.scenario,
        "image_relpath": record.image_relpath,
        "image_sha256": record.image_sha256,
        "image_width": record.image_width,
        "image_height": record.image_height,
        "model_id": record.model_id,
        "runtime_provenance": {
            "runtime_device": record.runtime_provenance.runtime_device,
            "runtime_name": record.runtime_provenance.runtime_name,
            "runtime_version": record.runtime_provenance.runtime_version,
            "weights_sha256": record.runtime_provenance.weights_sha256,
            "environment": dict(record.runtime_provenance.environment),
        },
        "config_sha256": record.config_sha256,
        "threshold_lock_sha256": record.threshold_lock_sha256,
        "raw_candidates": [
            _candidate_document(candidate) for candidate in record.raw_candidates
        ],
        "phase_timings": {
            "grounding_ms": record.phase_timings.grounding_ms,
            "sam_ms": record.phase_timings.sam_ms,
            "selector_ms": record.phase_timings.selector_ms,
        },
        "raw_count": record.raw_count,
        "decision": record.decision.value,
        "selected_candidate_id": record.selected_candidate_id,
        "rejection_reason": record.rejection_reason,
        "error_type": record.error_type,
        "error_summary": record.error_summary,
        "timed_out": record.timed_out,
        "oom": record.oom,
        "fallback_used": record.fallback_used,
    }


def _resource_from_document(document: object) -> ResourceSample:
    if not isinstance(document, Mapping):
        raise ValueError("extended resource sample must be an object")
    try:
        return ResourceSample(**dict(_plain(document)))
    except (TypeError, ValueError) as error:
        raise ValueError("extended resource sample is malformed") from error


def _validate_extended_documents(
    records: tuple[PredictionRecord, ...],
    evidence: RunAggregationEvidence,
    *,
    platform: str,
    model: str,
    source_commit: str,
    inventory_sha256: str,
) -> tuple[Mapping[str, float | None], ...]:
    documents = evidence.extended_record_documents
    if len(documents) != len(records):
        raise ValueError("extended record document count does not match records")
    timings: list[Mapping[str, float | None]] = []
    document_resources: list[ResourceSample] = []
    document_resource_groups: list[tuple[ResourceSample, ...]] = []
    common_fields = tuple(_record_document(records[0])) if records else ()
    for position, (record, document) in enumerate(zip(records, documents, strict=True)):
        expected = _record_document(record)
        for field in common_fields:
            if field not in document or _plain(document[field]) != expected[field]:
                raise ValueError(
                    f"extended record at position {position} does not match typed record identity/common fields"
                )
        anchors = {
            "platform": platform,
            "model": model,
            "device": record.runtime_provenance.runtime_device,
            "dtype": "float32",
            "source_commit": source_commit,
            "inventory_sha256": inventory_sha256,
            "collection_mode": "LOW_FLOOR",
        }
        if any(_plain(document.get(name)) != value for name, value in anchors.items()):
            raise ValueError("extended record cross-field anchor does not match aggregation input")
        timing = document.get("timing_breakdown")
        if not isinstance(timing, Mapping) or set(timing) != set(_TIMING_FIELDS):
            raise ValueError("extended record timing_breakdown is missing or malformed")
        normalized = {
            name: _optional_finite_nonnegative(name, timing[name])
            for name in _TIMING_FIELDS
        }
        if normalized["total_ms"] is None:
            raise ValueError("total_ms must retain per-image wall time, including ERROR")
        if record.record_status is RecordStatus.OK:
            for required in ("preprocess_ms", "dino_or_yolo_ms", "postprocess_ms"):
                if normalized[required] is None:
                    raise ValueError(f"{required} is required for OK records")
            phase_sum = sum(
                value
                for name, value in normalized.items()
                if name != "total_ms" and value is not None
            )
            if not math.isclose(
                float(normalized["total_ms"]),
                phase_sum,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise ValueError("total_ms does not equal the retained phase timings")
        typed_pairs = (
            (record.phase_timings.grounding_ms, normalized["dino_or_yolo_ms"]),
            (record.phase_timings.sam_ms, normalized["sam_ms"]),
            (record.phase_timings.selector_ms, normalized["selector_ms"]),
        )
        if any(first != second for first, second in typed_pairs):
            raise ValueError("extended timing phases do not match typed record")
        resources = document.get("resource_samples")
        if not isinstance(resources, (list, tuple)):
            raise ValueError("extended record resource_samples must be a sequence")
        resource_group = tuple(_resource_from_document(item) for item in resources)
        document_resource_groups.append(resource_group)
        document_resources.extend(resource_group)
        timings.append(MappingProxyType(normalized))
    expected_resources = (
        tuple(item.sample for item in evidence.resource_trace.observations)
        if evidence.resource_trace is not None
        else evidence.resource_samples
    )
    if tuple(document_resources) != expected_resources:
        raise ValueError("extended resource rows do not match run resource stream")
    if evidence.resource_trace is not None:
        expected_groups = tuple(
            tuple(
                observation.sample
                for observation in evidence.resource_trace.observations
                if observation.formal_sample_index == record.formal_sample_index
                or (
                    observation.formal_sample_index is None
                    and position == 0
                )
            )
            for position, record in enumerate(records)
        )
        if tuple(document_resource_groups) != expected_groups:
            raise ValueError(
                "extended resource rows do not match their phase/image anchors"
            )
    return tuple(timings)


def _validate_run_evidence(
    records: tuple[PredictionRecord, ...],
    evidence: RunAggregationEvidence,
    *,
    formal: bool,
) -> None:
    cold = evidence.cold_process_samples
    if formal:
        if evidence.cold_latency_ms or evidence.resource_samples:
            raise ValueError("formal evidence forbids unanchored fixture samples")
        if len(cold) < 3:
            raise ValueError("formal evidence requires at least three distinct fresh processes")
        if evidence.resource_trace is None:
            raise ValueError(
                "formal resource trace requires load, warmup, and inference phases"
            )
    if cold:
        process_ids = [sample.process_id for sample in cold]
        process_anchors = [
            (sample.pid, sample.process_started_ns) for sample in cold
        ]
        if len(set(process_ids)) != len(process_ids) or len(
            set(process_anchors)
        ) != len(process_anchors):
            raise ValueError("cold samples must identify distinct fresh processes")
        provenance = records[0].runtime_provenance
        if any(
            sample.runtime_name != provenance.runtime_name
            or sample.runtime_version != provenance.runtime_version
            or sample.weights_sha256 != provenance.weights_sha256
            for sample in cold
        ):
            raise ValueError("cold process provenance does not match run records")
    trace = evidence.resource_trace
    if trace is None:
        return
    phases = {observation.phase for observation in trace.observations}
    if formal and phases != {"load", "warmup", "inference"}:
        raise ValueError(
            "formal resource trace requires load, warmup, and inference phases"
        )
    valid_indices = {record.formal_sample_index for record in records}
    for observation in trace.observations:
        if observation.phase in {"load", "warmup"}:
            if observation.formal_sample_index is not None:
                raise ValueError("load/warmup resources cannot claim an image index")
        elif observation.formal_sample_index not in valid_indices:
            raise ValueError("inference resource observation has no record anchor")


def _validate_record_group(
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    *,
    platform: str,
    model: str,
    run_kind: RunKind,
    config: str,
) -> None:
    if not records:
        raise ValueError("record groups must be non-empty")
    if not all(isinstance(record, PredictionRecord) for record in records):
        raise ValueError("record groups must contain PredictionRecord values")
    if any(record.run_kind is not run_kind for record in records):
        raise ValueError(f"{config} record group has the wrong run kind")
    if platform not in {"linux", "macos"}:
        raise ValueError("platform cell key must be linux or macos")
    if model not in {"yolo_seg", "grounded_sam"}:
        raise ValueError("model cell key must be yolo_seg or grounded_sam")
    expected_model_id = MODEL_ID_BY_NAME[model]
    if any(record.model_id != expected_model_id for record in records):
        raise ValueError(
            "typed record model does not match the canonical model identity cell anchor"
        )
    first_record = records[0]
    if any(
        record.model_id != first_record.model_id
        or record.runtime_provenance != first_record.runtime_provenance
        for record in records[1:]
    ):
        raise ValueError(
            "one aggregation cell requires a homogeneous runtime/model signature"
        )
    expected_device = "cuda" if platform == "linux" else "mps"
    if any(
        record.runtime_provenance.runtime_device != expected_device
        for record in records
    ):
        raise ValueError("typed record device does not match the platform cell anchor")
    if any(
        (record.timed_out or record.oom)
        and (
            record.record_status is not RecordStatus.ERROR
            or record.decision is not DecisionOutput.ERROR
        )
        for record in records
    ):
        raise ValueError("timeout or OOM evidence requires ERROR status and decision")
    if len({record.run_id for record in records}) != 1:
        raise ValueError("one aggregation cell must contain exactly one run_id")
    if len({record.config_sha256 for record in records}) != 1:
        raise ValueError("one aggregation cell must contain exactly one config SHA")
    if len({record.threshold_lock_sha256 for record in records}) != 1:
        raise ValueError("one aggregation cell must contain exactly one lock SHA")
    identities = [
        (record.formal_sample_index, record.image_sha256) for record in records
    ]
    truth_identities = [
        (truth.formal_sample_index, truth.image_sha256) for truth in truths
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("record group composite identities must be unique")
    if identities != truth_identities:
        raise ValueError("record group order/identity does not match truth inventory")
    for record, truth in zip(records, truths, strict=True):
        if (
            record.split != truth.split
            or record.scenario != truth.scenario
            or record.image_relpath != truth.image_relpath
            or record.image_width != truth.image_width
            or record.image_height != truth.image_height
        ):
            raise ValueError("prediction record does not match truth sample")


def _formal_matrix_gate(value: AggregationInput) -> None:
    truths = value.truth_samples
    image_shas = [truth.image_sha256 for truth in truths]
    if len(truths) != 200 or len(set(image_shas)) != 200:
        raise ValueError("formal aggregation requires exactly 200 unique TEST images")
    scenario_counts = {
        scenario: sum(truth.scenario == scenario for truth in truths)
        for scenario in _SCENARIOS
    }
    if scenario_counts != {scenario: 50 for scenario in _SCENARIOS}:
        raise ValueError("formal aggregation requires exactly 50 samples per scenario")
    if any(truth.split != "test" for truth in truths):
        raise ValueError("formal aggregation requires only the test split")
    if set(value.raw_frozen_records) != set(_FORMAL_PLATFORMS) or any(
        set(value.raw_frozen_records[platform]) != set(_FORMAL_MODELS)
        for platform in _FORMAL_PLATFORMS
    ):
        raise ValueError("formal matrix is missing a raw platform/model cell")
    if set(value.formal_records) != set(_FORMAL_PLATFORMS) or any(
        set(value.formal_records[platform]) != set(_FORMAL_MODELS)
        for platform in _FORMAL_PLATFORMS
    ):
        raise ValueError("formal matrix is missing a safety platform/model cell")
    for platform in _FORMAL_PLATFORMS:
        for model in _FORMAL_MODELS:
            configs = set(value.formal_records[platform][model])
            if "production" not in configs or len(configs & {"calibrated", "characterization"}) != 1 or len(configs) != 2:
                raise ValueError(
                    "formal matrix requires production and exactly one calibrated-or-characterization cell"
                )
    if set(value.threshold_locks) != set(_FORMAL_MODELS):
        raise ValueError("formal matrix requires both model threshold locks")
    locks = value.threshold_locks
    if not all(isinstance(lock, ThresholdLock) and lock.formal for lock in locks.values()):
        raise ValueError("formal aggregation requires formal ThresholdLock values")
    if locks["yolo_seg"].lock_sha256 == locks["grounded_sam"].lock_sha256:
        raise ValueError("formal aggregation requires distinct model threshold locks")
    if (
        locks["yolo_seg"].val_inventory_sha256
        != locks["grounded_sam"].val_inventory_sha256
    ):
        raise ValueError("formal threshold locks must share the same validation inventory")
    for model, lock in locks.items():
        if lock.model != model or lock.source_commit != value.source_commit:
            raise ValueError("threshold lock model/source anchor mismatch")
        if lock.with_recomputed_sha256().lock_sha256 != lock.lock_sha256:
            raise ValueError("threshold lock digest does not read back")
        expected_config = "calibrated" if lock.deployable else "characterization"
        if any(
            expected_config not in value.formal_records[platform][model]
            for platform in _FORMAL_PLATFORMS
        ):
            raise ValueError("formal safety cell does not match ThresholdLock outcome")
    if value.bootstrap_seed != 20260902 or value.bootstrap_repetitions != 10_000:
        raise ValueError("formal aggregation fixes bootstrap seed 20260902 and 10000 repetitions")


def _expected_evidence_keys(value: AggregationInput) -> set[tuple[str, str, str]]:
    keys = {
        (platform, model, "TEST_RAW_FROZEN")
        for platform, models in value.raw_frozen_records.items()
        for model in models
    }
    keys.update(
        (platform, model, config)
        for platform, models in value.formal_records.items()
        for model, configs in models.items()
        for config in configs
    )
    return keys


def _validate_formal_runtime_identities(value: AggregationInput) -> None:
    first_by_platform_model: dict[tuple[str, str], PredictionRecord] = {}
    for platform in _FORMAL_PLATFORMS:
        for model in _FORMAL_MODELS:
            groups = (
                value.raw_frozen_records[platform][model],
                *value.formal_records[platform][model].values(),
            )
            if any(not records for records in groups):
                raise ValueError("formal matrix record groups must be non-empty")
            first = groups[0][0]
            signature = (
                first.model_id,
                first.runtime_provenance.runtime_device,
                first.runtime_provenance.runtime_name,
                first.runtime_provenance.runtime_version,
                first.runtime_provenance.weights_sha256,
                dict(first.runtime_provenance.environment),
            )
            if any(
                (
                    records[0].model_id,
                    records[0].runtime_provenance.runtime_device,
                    records[0].runtime_provenance.runtime_name,
                    records[0].runtime_provenance.runtime_version,
                    records[0].runtime_provenance.weights_sha256,
                    dict(records[0].runtime_provenance.environment),
                )
                != signature
                for records in groups[1:]
            ):
                raise ValueError(
                    "formal run kinds require one frozen model/runtime identity"
                )
            first_by_platform_model[(platform, model)] = first
    for model in _FORMAL_MODELS:
        mac = first_by_platform_model[("macos", model)]
        linux = first_by_platform_model[("linux", model)]
        if (
            mac.model_id != linux.model_id
            or mac.runtime_provenance.weights_sha256
            != linux.runtime_provenance.weights_sha256
        ):
            raise ValueError("formal cross-platform model asset identity must match")


def _records_for_key(
    value: AggregationInput, key: tuple[str, str, str]
) -> tuple[PredictionRecord, ...]:
    platform, model, config = key
    if config == "TEST_RAW_FROZEN":
        return value.raw_frozen_records[platform][model]
    return value.formal_records[platform][model][config]


def _run_kind_for_config(config: str) -> RunKind:
    return {
        "TEST_RAW_FROZEN": RunKind.TEST_RAW_FROZEN,
        "production": RunKind.TEST_PRODUCTION,
        "calibrated": RunKind.TEST_CALIBRATED,
        "characterization": RunKind.TEST_CHARACTERIZATION,
        "ORACLE_DIAGNOSTIC": RunKind.ORACLE_DIAGNOSTIC,
    }[config]


def _validate_input(value: AggregationInput) -> tuple[Path, dict[tuple[str, str, str], tuple[Mapping[str, float | None], ...]]]:
    if not isinstance(value, AggregationInput):
        raise ValueError("input must be an AggregationInput")
    _require_source_commit(value.source_commit)
    _require_sha("dataset_archive_sha256", value.dataset_archive_sha256)
    _require_sha("test_inventory_sha256", value.test_inventory_sha256)
    truth_root = _existing_root("truth_evidence_root", value.truth_evidence_root)
    identities = [
        (truth.formal_sample_index, truth.image_sha256) for truth in value.truth_samples
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("truth composite identities must be unique")
    if identities != sorted(identities):
        raise ValueError("truth_samples must be in deterministic formal index order")
    if value.formal:
        _formal_matrix_gate(value)
        _validate_formal_runtime_identities(value)
    expected_keys = _expected_evidence_keys(value)
    if set(value.run_evidence) != expected_keys:
        raise ValueError("run_evidence keys do not match the raw/formal matrix")
    timings_by_key: dict[
        tuple[str, str, str], tuple[Mapping[str, float | None], ...]
    ] = {}
    for key in sorted(expected_keys):
        platform, model, config = key
        records = _records_for_key(value, key)
        _validate_record_group(
            records,
            value.truth_samples,
            platform=platform,
            model=model,
            run_kind=_run_kind_for_config(config),
            config=config,
        )
        evidence = value.run_evidence[key]
        _existing_root("candidate evidence_root", evidence.evidence_root)
        _validate_run_evidence(records, evidence, formal=value.formal)
        timings_by_key[key] = _validate_extended_documents(
            records,
            evidence,
            platform=platform,
            model=model,
            source_commit=value.source_commit,
            inventory_sha256=value.test_inventory_sha256,
        )
        if value.formal:
            lock = value.threshold_locks[model]
            if any(
                record.threshold_lock_sha256 != lock.lock_sha256
                for record in records
            ):
                raise ValueError("formal record threshold-lock anchor mismatch")
    oracle_keys = {
        (platform, model, "ORACLE_DIAGNOSTIC")
        for platform, models in value.oracle_records.items()
        for model in models
    }
    if set(value.oracle_evidence) != oracle_keys:
        raise ValueError("oracle_evidence keys do not match separate oracle records")
    for key in sorted(oracle_keys):
        platform, model, config = key
        records = value.oracle_records[platform][model]
        _validate_record_group(
            records,
            value.truth_samples,
            platform=platform,
            model=model,
            run_kind=RunKind.ORACLE_DIAGNOSTIC,
            config=config,
        )
        evidence = value.oracle_evidence[key]
        _existing_root("oracle candidate evidence_root", evidence.evidence_root)
        _validate_run_evidence(records, evidence, formal=False)
        timings_by_key[key] = _validate_extended_documents(
            records,
            evidence,
            platform=platform,
            model=model,
            source_commit=value.source_commit,
            inventory_sha256=value.test_inventory_sha256,
        )
    return truth_root, timings_by_key


def _image_inputs(
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    truth_root: Path,
    candidate_root: Path,
) -> tuple[ImageMetricInput, ...]:
    values: list[ImageMetricInput] = []
    for record, truth in zip(records, truths, strict=True):
        matches: tuple[MaskMatch, ...] = ()
        if record.record_status is RecordStatus.OK and truth.instances and record.raw_candidates:
            matches = maximize_mask_iou_assignment(
                truth.instances,
                record.raw_candidates,
                truth_root,
                candidate_evidence_root=candidate_root,
            )
        values.append(
            ImageMetricInput(
                formal_sample_index=record.formal_sample_index,
                truth_count=len(truth.instances),
                candidate_count=(
                    0
                    if record.record_status is RecordStatus.ERROR
                    else len(record.raw_candidates)
                ),
                matches=matches,
            )
        )
    return tuple(values)


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else float(numerator / denominator)


def _f1(summary: InstanceMetricSummary) -> float | None:
    if summary.precision is None or summary.recall is None:
        return None
    denominator = summary.precision + summary.recall
    return 0.0 if denominator == 0.0 else float(
        2.0 * summary.precision * summary.recall / denominator
    )


def _metric_f1(samples: Sequence[ImageMetricInput]) -> float | None:
    return _f1(summarize_image_metrics(samples, iou_threshold=0.50))


def _null_interval() -> ConfidenceInterval:
    return ConfidenceInterval(None, None)


def _bootstrap_rows(
    rows: Sequence[object],
    metric: Callable[[tuple[object, ...]], float | None],
    *,
    seed: int,
    repetitions: int,
) -> ConfidenceInterval:
    items = tuple(rows)
    point = metric(items)
    if not items or point is None:
        return _null_interval()
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(repetitions):
        selected = rng.integers(0, len(items), size=len(items))
        result = metric(tuple(items[index] for index in selected))
        if result is None:
            continue
        numeric = float(result)
        if not math.isfinite(numeric):
            raise ValueError("bootstrap metric returned a nonfinite value")
        values.append(numeric)
    if not values:
        return _null_interval()
    return ConfidenceInterval(
        float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
    )


def _ap_prefix_traces(
    records: tuple[PredictionRecord, ...],
) -> tuple[tuple[RawCandidate, ...], ...]:
    return tuple(
        tuple(
            sorted(
                record.raw_candidates,
                key=lambda candidate: (-candidate.ranking_score, candidate.candidate_id),
            )
        )
        if record.record_status is RecordStatus.OK
        else ()
        for record in records
    )


def _ap_match_traces(
    ordered_candidates: tuple[tuple[RawCandidate, ...], ...],
    truths: tuple[TruthSample, ...],
    truth_root: Path,
    candidate_root: Path,
) -> Mapping[tuple[int, float], tuple[int, ...]]:
    traces: dict[tuple[int, float], tuple[int, ...]] = {}
    for image_position, (candidates, truth) in enumerate(
        zip(ordered_candidates, truths, strict=True)
    ):
        for threshold in _IOU_THRESHOLDS:
            traces[(image_position, threshold)] = tuple(
                _thresholded_match_count(
                    truth.instances,
                    candidates[:prefix_length],
                    truth_root,
                    threshold,
                    candidate_evidence_root=candidate_root,
                )
                for prefix_length in range(1, len(candidates) + 1)
            )
    return MappingProxyType(traces)


def _bootstrap_ap_value(
    selected: tuple[object, ...],
    *,
    ordered_candidates: tuple[tuple[RawCandidate, ...], ...],
    truths: tuple[TruthSample, ...],
    match_traces: Mapping[tuple[int, float], tuple[int, ...]],
    mean_over_thresholds: bool,
) -> float | None:
    selected_positions = tuple(int(position) for position in selected)
    total_truth = sum(len(truths[position].instances) for position in selected_positions)
    if total_truth == 0:
        return None
    events = sorted(
        (
            -candidate.ranking_score,
            copy_position,
            candidate.candidate_id,
            source_position,
            prefix_position,
        )
        for copy_position, source_position in enumerate(selected_positions)
        for prefix_position, candidate in enumerate(
            ordered_candidates[source_position]
        )
    )
    values: list[float] = []
    thresholds = _IOU_THRESHOLDS if mean_over_thresholds else (0.50,)
    for threshold in thresholds:
        matched_by_copy: dict[int, int] = {}
        current_total = 0
        precision: list[float] = []
        recall: list[float] = []
        for rank, (_, copy_position, _, source_position, prefix_position) in enumerate(
            events, start=1
        ):
            matched = match_traces[(source_position, threshold)][prefix_position]
            current_total += matched - matched_by_copy.get(copy_position, 0)
            matched_by_copy[copy_position] = matched
            precision.append(float(current_total / rank))
            recall.append(float(current_total / total_truth))
        ap = interpolated_ap(np.asarray(recall), np.asarray(precision))
        if ap is not None:
            values.append(ap)
    return None if not values else float(np.mean(values))


def _ap_intervals(
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    truth_root: Path,
    candidate_root: Path,
    *,
    seed: int,
    repetitions: int,
) -> Mapping[str, ConfidenceInterval]:
    ordered_candidates = _ap_prefix_traces(records)
    match_traces = _ap_match_traces(
        ordered_candidates, truths, truth_root, candidate_root
    )
    rows = tuple(range(len(records)))

    def metric(
        selected: tuple[object, ...], *, mean_over_thresholds: bool
    ) -> float | None:
        return _bootstrap_ap_value(
            selected,
            ordered_candidates=ordered_candidates,
            truths=truths,
            match_traces=match_traces,
            mean_over_thresholds=mean_over_thresholds,
        )

    return MappingProxyType(
        {
            "mask_ap50": _bootstrap_rows(
                rows,
                lambda selected: metric(selected, mean_over_thresholds=False),
                seed=seed,
                repetitions=repetitions,
            ),
            "mask_ap50_95": _bootstrap_rows(
                rows,
                lambda selected: metric(selected, mean_over_thresholds=True),
                seed=seed,
                repetitions=repetitions,
            ),
        }
    )


def _metric_details(
    inputs: tuple[ImageMetricInput, ...],
    records: tuple[PredictionRecord, ...],
    *,
    seed: int,
    repetitions: int,
) -> tuple[InstanceMetricSummary, MetricDetails]:
    summary = summarize_image_metrics(inputs, iou_threshold=0.50)
    qualified = [
        match.iou
        for sample in inputs
        for match in sample.matches
        if match.iou >= 0.50
    ]
    dice = [(2.0 * iou) / (1.0 + iou) for iou in qualified]
    exact = sum(
        record.record_status is RecordStatus.OK
        and sample.truth_count == sample.candidate_count
        for record, sample in zip(records, inputs, strict=True)
    )
    count = len(inputs)
    f1_value = _f1(summary)
    f1_interval = (
        _null_interval()
        if f1_value is None
        else _bootstrap_rows(
            inputs,
            _metric_f1,
            seed=seed,
            repetitions=repetitions,
        )
    )
    def qualified_values(selected: Sequence[ImageMetricInput]) -> tuple[float, ...]:
        return tuple(
            match.iou
            for sample in selected
            for match in sample.matches
            if match.iou >= 0.50
        )

    def bootstrap_instance_metric(
        point: float | None,
        metric: Callable[[Sequence[ImageMetricInput]], float | None],
    ) -> ConfidenceInterval:
        if point is None:
            return _null_interval()

        return _bootstrap_rows(
            inputs,
            lambda selected: metric(selected),
            seed=seed,
            repetitions=repetitions,
        )

    median_iou = float(np.median(qualified)) if qualified else None
    median_dice = float(np.median(dice)) if dice else None
    precision_interval = bootstrap_instance_metric(
        summary.precision,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).precision,
    )
    recall_interval = bootstrap_instance_metric(
        summary.recall,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).recall,
    )
    mean_iou_interval = bootstrap_instance_metric(
        summary.mean_iou,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).mean_iou,
    )
    mean_dice_interval = bootstrap_instance_metric(
        summary.mean_dice,
        lambda selected: summarize_image_metrics(
            selected, iou_threshold=0.50
        ).mean_dice,
    )
    median_iou_interval = bootstrap_instance_metric(
        median_iou,
        lambda selected: (
            float(np.median(qualified_values(selected)))
            if qualified_values(selected)
            else None
        ),
    )
    median_dice_interval = bootstrap_instance_metric(
        median_dice,
        lambda selected: (
            float(
                np.median(
                    [
                        (2.0 * iou) / (1.0 + iou)
                        for iou in qualified_values(selected)
                    ]
                )
            )
            if qualified_values(selected)
            else None
        ),
    )
    rows = tuple(zip(records, inputs, strict=True))

    def exact_metric(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        correct = 0
        for row in selected:
            record, sample = row  # type: ignore[misc]
            correct += bool(
                record.record_status is RecordStatus.OK
                and sample.truth_count == sample.candidate_count
            )
        return float(correct / len(selected))

    def fp_metric(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        samples = tuple(row[1] for row in selected)  # type: ignore[index]
        return float(
            summarize_image_metrics(samples, iou_threshold=0.50).fp
            / len(samples)
        )

    def fn_metric(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        samples = tuple(row[1] for row in selected)  # type: ignore[index]
        return float(
            summarize_image_metrics(samples, iou_threshold=0.50).fn
            / len(samples)
        )

    intervals = MappingProxyType(
        {
            "precision_at_50": precision_interval,
            "recall_at_50": recall_interval,
            "f1_at_50": f1_interval,
            "mean_iou": mean_iou_interval,
            "median_iou": median_iou_interval,
            "mean_dice": mean_dice_interval,
            "median_dice": median_dice_interval,
            "exact_count_accuracy": _bootstrap_rows(
                rows, exact_metric, seed=seed, repetitions=repetitions
            ),
            "fp_per_image": _bootstrap_rows(
                rows, fp_metric, seed=seed, repetitions=repetitions
            ),
            "fn_per_image": _bootstrap_rows(
                rows, fn_metric, seed=seed, repetitions=repetitions
            ),
        }
    )
    return summary, MetricDetails(
        f1=f1_value,
        median_iou=median_iou,
        median_dice=median_dice,
        exact_count_accuracy=_rate(exact, count),
        fp_per_image=None if count == 0 else float(summary.fp / count),
        fn_per_image=None if count == 0 else float(summary.fn / count),
        confidence_intervals=intervals,
    )


def _per_image_leakage_counts(
    record: PredictionRecord,
    truth: TruthSample,
    truth_root: Path,
    candidate_root: Path,
) -> tuple[int, int]:
    if record.record_status is RecordStatus.ERROR or not record.raw_candidates:
        return (0, 0)
    predicted = np.zeros((truth.image_height, truth.image_width), dtype=bool)
    truth_union = np.zeros_like(predicted)
    for candidate in record.raw_candidates:
        predicted |= read_mask(candidate.mask, candidate_root)
    for instance in truth.instances:
        truth_union |= read_mask(instance.mask, truth_root)
    predicted_pixels = int(predicted.sum())
    return (
        int(np.count_nonzero(predicted & ~truth_union)),
        predicted_pixels,
    )


def _scenario_summaries(
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    inputs: tuple[ImageMetricInput, ...],
    safety: Mapping[str, ScenarioMetrics],
    truth_root: Path,
    candidate_root: Path,
    *,
    seed: int,
    repetitions: int,
) -> Mapping[str, ScenarioMetricSummary]:
    summaries: dict[str, ScenarioMetricSummary] = {}
    for scenario in sorted({truth.scenario for truth in truths}):
        selected = tuple(
            (record, truth, sample)
            for record, truth, sample in zip(records, truths, inputs, strict=True)
            if truth.scenario == scenario
        )
        scenario_records = tuple(row[0] for row in selected)
        scenario_truths = tuple(row[1] for row in selected)
        scenario_inputs = tuple(row[2] for row in selected)
        scenario_ap = compute_ap(
            scenario_records,
            scenario_truths,
            truth_root,
            _IOU_THRESHOLDS,
            candidate_evidence_root=candidate_root,
        )
        scenario_ap_intervals = _ap_intervals(
            scenario_records,
            scenario_truths,
            truth_root,
            candidate_root,
            seed=seed,
            repetitions=repetitions,
        )
        scenario_decisions = aggregate_decisions(
            scenario_records, scenario_truths
        )
        instance, details = _metric_details(
            scenario_inputs,
            scenario_records,
            seed=seed,
            repetitions=repetitions,
        )
        no_cup_outcomes: dict[tuple[int, str], int] = {}
        for record, truth, image_input in selected:
            if truth.instances:
                continue
            single_metrics = aggregate_scenarios(
                (record,),
                (truth,),
                MappingProxyType(
                    {
                        (
                            record.formal_sample_index,
                            record.image_sha256,
                        ): image_input
                    }
                ),
                truth_root,
                candidate_evidence_root=candidate_root,
            )
            no_cup_outcomes[(
                record.formal_sample_index,
                record.image_sha256,
            )] = single_metrics[scenario].no_cup_false_positive_count
        leakage_outcomes = {
            (record.formal_sample_index, record.image_sha256): (
                _per_image_leakage_counts(
                    record, truth, truth_root, candidate_root
                )
            )
            for record, truth, _ in selected
            if truth.scenario == "cup_near_bottle"
        }

        def error_rate(rows: tuple[object, ...]) -> float | None:
            if not rows:
                return None
            return float(
                sum(row[0].record_status is RecordStatus.ERROR for row in rows)  # type: ignore[index]
                / len(rows)
            )

        def timeout_rate(rows: tuple[object, ...]) -> float | None:
            if not rows:
                return None
            return float(sum(row[0].timed_out for row in rows) / len(rows))  # type: ignore[index]

        def oom_rate(rows: tuple[object, ...]) -> float | None:
            if not rows:
                return None
            return float(sum(row[0].oom for row in rows) / len(rows))  # type: ignore[index]

        def no_cup_fpr(rows: tuple[object, ...]) -> float | None:
            eligible = [row for row in rows if not row[1].instances]  # type: ignore[index]
            if not eligible:
                return None
            false_positives = sum(
                no_cup_outcomes[(
                    row[0].formal_sample_index,  # type: ignore[index]
                    row[0].image_sha256,  # type: ignore[index]
                )]
                for row in eligible
            )
            return float(false_positives / len(eligible))

        def two_cup_recall(rows: tuple[object, ...]) -> float | None:
            eligible = [row for row in rows if len(row[1].instances) >= 2]  # type: ignore[index]
            if not eligible:
                return None
            return float(
                sum(
                    sum(match.iou >= 0.50 for match in row[2].matches) >= 2  # type: ignore[index]
                    for row in eligible
                )
                / len(eligible)
            )

        def leakage(rows: tuple[object, ...]) -> float | None:
            eligible = [row for row in rows if row[1].scenario == "cup_near_bottle"]  # type: ignore[index]
            if not eligible:
                return None
            counts = tuple(
                leakage_outcomes[(
                    row[0].formal_sample_index,  # type: ignore[index]
                    row[0].image_sha256,  # type: ignore[index]
                )]
                for row in eligible
            )
            predicted_pixels = sum(count[1] for count in counts)
            return (
                None
                if predicted_pixels == 0
                else float(sum(count[0] for count in counts) / predicted_pixels)
            )

        intervals = MappingProxyType(
            {
                "error_rate": _bootstrap_rows(
                    selected, error_rate, seed=seed, repetitions=repetitions
                ),
                "timeout_rate": _bootstrap_rows(
                    selected, timeout_rate, seed=seed, repetitions=repetitions
                ),
                "oom_rate": _bootstrap_rows(
                    selected, oom_rate, seed=seed, repetitions=repetitions
                ),
                "no_cup_false_positive_rate": _bootstrap_rows(
                    selected, no_cup_fpr, seed=seed, repetitions=repetitions
                ),
                "two_cup_both_matched_recall": _bootstrap_rows(
                    selected, two_cup_recall, seed=seed, repetitions=repetitions
                ),
                "non_cup_leakage_ratio": _bootstrap_rows(
                    selected, leakage, seed=seed, repetitions=repetitions
                ),
            }
        )
        summaries[scenario] = ScenarioMetricSummary(
            sample_count=len(selected),
            error_count=sum(
                record.record_status is RecordStatus.ERROR
                for record in scenario_records
            ),
            timeout_count=sum(record.timed_out for record in scenario_records),
            oom_count=sum(record.oom for record in scenario_records),
            mask_ap50=scenario_ap.mask_ap50,
            mask_ap50_95=scenario_ap.mask_map,
            ap_confidence_intervals=scenario_ap_intervals,
            decision_metrics=scenario_decisions,
            decision_confidence_intervals=_decision_intervals(
                scenario_records,
                scenario_truths,
                seed=seed,
                repetitions=repetitions,
            ),
            instance_metrics=instance,
            metric_details=details,
            safety_metrics=safety[scenario],
            confidence_intervals=intervals,
        )
    return MappingProxyType(summaries)


def _performance(
    evidence: RunAggregationEvidence,
    timings: tuple[Mapping[str, float | None], ...],
) -> PerformanceSummary:
    cold = (
        tuple(sample.latency_ms for sample in evidence.cold_process_samples)
        if evidence.cold_process_samples
        else evidence.cold_latency_ms
    )
    warmed = tuple(float(row["total_ms"]) for row in timings)
    phase_percentiles = MappingProxyType(
        {
            phase: MappingProxyType(
                {
                    "p50": percentile(
                        tuple(
                            float(row[phase])
                            for row in timings
                            if row[phase] is not None
                        ),
                        0.50,
                    ),
                    "p95": percentile(
                        tuple(
                            float(row[phase])
                            for row in timings
                            if row[phase] is not None
                        ),
                        0.95,
                    ),
                    "p99": percentile(
                        tuple(
                            float(row[phase])
                            for row in timings
                            if row[phase] is not None
                        ),
                        0.99,
                    ),
                }
            )
            for phase in _TIMING_FIELDS[:-1]
        }
    )
    wall_ms = sum(warmed)
    return PerformanceSummary(
        cold_p50_ms=percentile(cold, 0.50),
        cold_p95_ms=percentile(cold, 0.95),
        cold_p99_ms=percentile(cold, 0.99),
        warmed_p50_ms=percentile(warmed, 0.50),
        warmed_p95_ms=percentile(warmed, 0.95),
        warmed_p99_ms=percentile(warmed, 0.99),
        phase_percentiles=phase_percentiles,
        images_per_second=(
            None if not warmed or wall_ms == 0.0 else float(len(warmed) / (wall_ms / 1000.0))
        ),
    )


_RESOURCE_FIELDS_AND_OUTPUT = (
    ("process_rss_bytes", "peak_rss_bytes"),
    ("process_cpu_percent", "peak_process_cpu_percent"),
    ("gpu_memory_allocated_bytes", "peak_device_allocated_bytes"),
    ("gpu_memory_reserved_bytes", "peak_device_reserved_bytes"),
    ("gpu_utilization_percent", "peak_gpu_utilization_percent"),
    ("gpu_temperature_celsius", "peak_gpu_temperature_celsius"),
    ("gpu_power_watts", "peak_gpu_power_watts"),
)


def _resource_peaks(
    samples: tuple[ResourceSample, ...],
) -> tuple[dict[str, int | float | None], Mapping[str, str]]:
    peaks: dict[str, int | float | None] = {}
    reasons: dict[str, str] = {}
    for source, output in _RESOURCE_FIELDS_AND_OUTPUT:
        values = [
            getattr(sample, source)
            for sample in samples
            if getattr(sample, source) is not None
        ]
        peaks[output] = max(values) if values else None
        if not values:
            described = sorted(
                {
                    sample.unavailable_reasons[source]
                    for sample in samples
                    if source in sample.unavailable_reasons
                }
            )
            reasons[output] = (
                "; ".join(described) if described else "resource stream unavailable"
            )
    return peaks, MappingProxyType(reasons)


def _resource_phase_summary(
    samples: tuple[ResourceSample, ...],
) -> ResourcePhaseSummary:
    peaks, reasons = _resource_peaks(samples)
    return ResourcePhaseSummary(
        sample_count=len(samples),
        peak_rss_bytes=peaks["peak_rss_bytes"],  # type: ignore[arg-type]
        peak_process_cpu_percent=peaks["peak_process_cpu_percent"],  # type: ignore[arg-type]
        peak_device_allocated_bytes=peaks["peak_device_allocated_bytes"],  # type: ignore[arg-type]
        peak_device_reserved_bytes=peaks["peak_device_reserved_bytes"],  # type: ignore[arg-type]
        peak_gpu_utilization_percent=peaks["peak_gpu_utilization_percent"],  # type: ignore[arg-type]
        peak_gpu_temperature_celsius=peaks["peak_gpu_temperature_celsius"],  # type: ignore[arg-type]
        peak_gpu_power_watts=peaks["peak_gpu_power_watts"],  # type: ignore[arg-type]
        unavailable_reasons=reasons,
    )


def _resource_summary(evidence: RunAggregationEvidence) -> ResourceSummary:
    trace = evidence.resource_trace
    observations = () if trace is None else trace.observations
    samples = (
        tuple(item.sample for item in observations)
        if trace is not None
        else evidence.resource_samples
    )
    peaks, reasons = _resource_peaks(samples)
    versions: dict[str, set[str]] = {}
    for sample in samples:
        for tool, version in sample.tool_versions.items():
            versions.setdefault(tool, set()).add(version)
    gaps = tuple(
        (later.monotonic_ns - earlier.monotonic_ns) / 1_000_000.0
        for earlier, later in zip(observations, observations[1:])
    )
    phase_summaries = MappingProxyType(
        {
            phase: _resource_phase_summary(
                tuple(
                    observation.sample
                    for observation in observations
                    if observation.phase == phase
                )
            )
            for phase in ("load", "warmup", "inference")
            if any(observation.phase == phase for observation in observations)
        }
    )
    return ResourceSummary(
        peak_rss_bytes=peaks["peak_rss_bytes"],  # type: ignore[arg-type]
        peak_process_cpu_percent=peaks["peak_process_cpu_percent"],  # type: ignore[arg-type]
        peak_device_allocated_bytes=peaks["peak_device_allocated_bytes"],  # type: ignore[arg-type]
        peak_device_reserved_bytes=peaks["peak_device_reserved_bytes"],  # type: ignore[arg-type]
        peak_gpu_utilization_percent=peaks["peak_gpu_utilization_percent"],  # type: ignore[arg-type]
        peak_gpu_temperature_celsius=peaks["peak_gpu_temperature_celsius"],  # type: ignore[arg-type]
        peak_gpu_power_watts=peaks["peak_gpu_power_watts"],  # type: ignore[arg-type]
        sampling_frequency_hz=(
            None if trace is None else trace.sampling_frequency_hz
        ),
        sampling_gaps_ms=gaps,
        max_sampling_gap_ms=max(gaps) if gaps else None,
        tool_versions=MappingProxyType(
            {
                tool: tuple(sorted(tool_versions))
                for tool, tool_versions in sorted(versions.items())
            }
        ),
        phase_summaries=phase_summaries,
        unavailable_reasons=reasons,
    )


def _per_image_rows(
    platform: str,
    model: str,
    config: str,
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    inputs: tuple[ImageMetricInput, ...],
    timings: tuple[Mapping[str, float | None], ...],
    evidence: RunAggregationEvidence,
) -> tuple[PerImageSummary, ...]:
    rows: list[PerImageSummary] = []
    observations = (
        ()
        if evidence.resource_trace is None
        else evidence.resource_trace.observations
    )
    resource_gaps = tuple(
        (later.monotonic_ns - earlier.monotonic_ns) / 1_000_000.0
        for earlier, later in zip(observations, observations[1:])
    )
    first_index = records[0].formal_sample_index
    for record, truth, sample, timing in zip(records, truths, inputs, timings, strict=True):
        matched = sum(match.iou >= 0.50 for match in sample.matches)
        rows.append(
            PerImageSummary(
                platform=platform,
                model=model,
                config=config,
                run_kind=record.run_kind.value,
                formal_sample_index=record.formal_sample_index,
                image_sha256=record.image_sha256,
                scenario=record.scenario,
                record_status=record.record_status.value,
                truth_count=len(truth.instances),
                candidate_count=sample.candidate_count,
                candidates=(
                    record.raw_candidates
                    if record.record_status is RecordStatus.OK
                    else ()
                ),
                matched_count_at_50=matched,
                true_positive=matched,
                false_positive=sample.candidate_count - matched,
                false_negative=len(truth.instances) - matched,
                exact_count=(
                    record.record_status is RecordStatus.OK
                    and sample.candidate_count == len(truth.instances)
                ),
                decision=record.decision.value,
                error_type=record.error_type,
                timed_out=record.timed_out,
                oom=record.oom,
                total_ms=float(timing["total_ms"]),
                phase_timings_ms=MappingProxyType(
                    {name: timing[name] for name in _TIMING_FIELDS[:-1]}
                ),
                resource_observations=tuple(
                    observation
                    for observation in observations
                    if observation.formal_sample_index == record.formal_sample_index
                    or (
                        observation.formal_sample_index is None
                        and record.formal_sample_index == first_index
                    )
                ),
                resource_sampling_frequency_hz=(
                    None
                    if evidence.resource_trace is None
                    else evidence.resource_trace.sampling_frequency_hz
                ),
                resource_sampling_gaps_ms=resource_gaps,
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class _MetricCore:
    ap50: float | None
    ap50_95: float | None
    ap_intervals: Mapping[str, ConfidenceInterval]
    instance: InstanceMetricSummary
    details: MetricDetails
    safety: Mapping[str, ScenarioMetrics]
    scenarios: Mapping[str, ScenarioMetricSummary]


def _metric_cache_key(
    value: AggregationInput,
    records: tuple[PredictionRecord, ...],
    inputs: tuple[ImageMetricInput, ...],
) -> tuple[object, ...]:
    """Identify only inputs that can affect Task8 capability/safety metrics.

    Every mask in a matched non-error image has already been read and SHA-verified by
    ``_image_inputs`` before this key is used. Roots, platforms, runtimes, phases, and
    configs deliberately remain outside this cache because their summaries are built
    independently; only byte-equivalent metric semantics may share the expensive
    10,000-replicate bootstrap result.
    """

    rows: list[object] = []
    for record, truth, image_input in zip(
        records, value.truth_samples, inputs, strict=True
    ):
        rows.append(
            (
                record.record_status.value,
                record.decision.value,
                record.timed_out,
                record.oom,
                tuple(
                    (
                        candidate.candidate_id,
                        candidate.ranking_score,
                        candidate.mask.sha256,
                        candidate.mask.pixel_count,
                        candidate.mask.image_width,
                        candidate.mask.image_height,
                    )
                    for candidate in (
                        record.raw_candidates
                        if record.record_status is RecordStatus.OK
                        else ()
                    )
                ),
                truth.scenario,
                tuple(
                    (
                        instance.instance_id,
                        instance.mask.sha256,
                        instance.mask.pixel_count,
                        instance.mask.image_width,
                        instance.mask.image_height,
                    )
                    for instance in truth.instances
                ),
                image_input.truth_count,
                image_input.candidate_count,
                tuple(
                    (match.truth_instance_id, match.candidate_id, match.iou)
                    for match in image_input.matches
                ),
            )
        )
    return (
        value.bootstrap_seed,
        value.bootstrap_repetitions,
        _IOU_THRESHOLDS,
        tuple(rows),
    )


@dataclass(frozen=True, slots=True)
class _CellResult:
    ap50: float | None
    ap50_95: float | None
    ap_intervals: Mapping[str, ConfidenceInterval]
    instance: InstanceMetricSummary
    details: MetricDetails
    safety: Mapping[str, ScenarioMetrics]
    scenarios: Mapping[str, ScenarioMetricSummary]
    performance: PerformanceSummary
    resource: ResourceSummary
    per_image: tuple[PerImageSummary, ...]


def _aggregate_cell(
    value: AggregationInput,
    truth_root: Path,
    timings_by_key: Mapping[
        tuple[str, str, str], tuple[Mapping[str, float | None], ...]
    ],
    *,
    platform: str,
    model: str,
    config: str,
    records: tuple[PredictionRecord, ...],
    evidence: RunAggregationEvidence,
    metric_cache: dict[tuple[object, ...], _MetricCore],
) -> _CellResult:
    candidate_root = _existing_root("candidate evidence_root", evidence.evidence_root)
    inputs = _image_inputs(records, value.truth_samples, truth_root, candidate_root)
    cache_key = _metric_cache_key(value, records, inputs)
    core = metric_cache.get(cache_key)
    if core is None:
        keyed_inputs = MappingProxyType(
            {
                (record.formal_sample_index, record.image_sha256): sample
                for record, sample in zip(records, inputs, strict=True)
            }
        )
        ap = compute_ap(
            records,
            value.truth_samples,
            truth_root,
            _IOU_THRESHOLDS,
            candidate_evidence_root=candidate_root,
        )
        ap_intervals = _ap_intervals(
            records,
            value.truth_samples,
            truth_root,
            candidate_root,
            seed=value.bootstrap_seed,
            repetitions=value.bootstrap_repetitions,
        )
        instance, details = _metric_details(
            inputs,
            records,
            seed=value.bootstrap_seed,
            repetitions=value.bootstrap_repetitions,
        )
        metric_records = tuple(
            replace(record, raw_candidates=(), raw_count=0)
            if record.record_status is RecordStatus.ERROR and record.raw_candidates
            else record
            for record in records
        )
        safety = aggregate_scenarios(
            metric_records,
            value.truth_samples,
            keyed_inputs,
            truth_root,
            candidate_evidence_root=candidate_root,
        )
        scenarios = _scenario_summaries(
            records,
            value.truth_samples,
            inputs,
            safety,
            truth_root,
            candidate_root,
            seed=value.bootstrap_seed,
            repetitions=value.bootstrap_repetitions,
        )
        core = _MetricCore(
            ap50=ap.mask_ap50,
            ap50_95=ap.mask_map,
            ap_intervals=ap_intervals,
            instance=instance,
            details=details,
            safety=safety,
            scenarios=scenarios,
        )
        metric_cache[cache_key] = core
    performance = _performance(evidence, timings_by_key[(platform, model, config)])
    return _CellResult(
        ap50=core.ap50,
        ap50_95=core.ap50_95,
        ap_intervals=core.ap_intervals,
        instance=core.instance,
        details=core.details,
        safety=core.safety,
        scenarios=core.scenarios,
        performance=performance,
        resource=_resource_summary(evidence),
        per_image=_per_image_rows(
            platform,
            model,
            config,
            records,
            value.truth_samples,
            inputs,
            timings_by_key[(platform, model, config)],
            evidence,
        ),
    )


def _candidate_distribution(records: tuple[PredictionRecord, ...]) -> Mapping[str, float]:
    counts: dict[int, int] = {}
    for record in records:
        count = 0 if record.record_status is RecordStatus.ERROR else record.raw_count
        counts[count] = counts.get(count, 0) + 1
    return MappingProxyType(
        {
            str(count): float(frequency / len(records))
            for count, frequency in sorted(counts.items())
        }
    )


def _decision_intervals(
    records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    *,
    seed: int,
    repetitions: int,
) -> Mapping[str, ConfidenceInterval]:
    rows = tuple(zip(records, truths, strict=True))

    def error_rate(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        return float(
            sum(row[0].record_status is RecordStatus.ERROR for row in selected)  # type: ignore[index]
            / len(selected)
        )

    def unique_success(selected: tuple[object, ...]) -> float | None:
        eligible = [row for row in selected if len(row[1].instances) == 1]  # type: ignore[index]
        if not eligible:
            return None
        return float(
            sum(row[0].decision is DecisionOutput.UNIQUE for row in eligible)  # type: ignore[index]
            / len(eligible)
        )

    def unsafe_unique(selected: tuple[object, ...]) -> float | None:
        eligible = [row for row in selected if len(row[1].instances) != 1]  # type: ignore[index]
        if not eligible:
            return None
        return float(
            sum(row[0].decision is DecisionOutput.UNIQUE for row in eligible)  # type: ignore[index]
            / len(eligible)
        )

    def macro_f1(selected: tuple[object, ...]) -> float | None:
        if not selected:
            return None
        truth_classes = ("0", "1", "2+")
        outputs = ("NOT_FOUND", "UNIQUE", "AMBIGUOUS", "ERROR")
        expected = {"0": "NOT_FOUND", "1": "UNIQUE", "2+": "AMBIGUOUS"}
        matrix = {
            truth_class: {output: 0 for output in outputs}
            for truth_class in truth_classes
        }
        for row in selected:
            record, truth = row  # type: ignore[misc]
            count = len(truth.instances)
            truth_class = "0" if count == 0 else "1" if count == 1 else "2+"
            matrix[truth_class][record.decision.value] += 1
        scores: list[float] = []
        for truth_class in truth_classes:
            output = expected[truth_class]
            true_positive = matrix[truth_class][output]
            false_positive = sum(
                matrix[other][output]
                for other in truth_classes
                if other != truth_class
            )
            false_negative = sum(
                count
                for actual, count in matrix[truth_class].items()
                if actual != output
            )
            denominator = 2 * true_positive + false_positive + false_negative
            scores.append(
                0.0 if denominator == 0 else (2.0 * true_positive) / denominator
            )
        return float(sum(scores) / len(scores))

    return MappingProxyType(
        {
            "macro_f1": _bootstrap_rows(
                rows, macro_f1, seed=seed, repetitions=repetitions
            ),
            "error_rate": _bootstrap_rows(
                rows, error_rate, seed=seed, repetitions=repetitions
            ),
            "unique_success_rate": _bootstrap_rows(
                rows, unique_success, seed=seed, repetitions=repetitions
            ),
            "unsafe_unique_rate": _bootstrap_rows(
                rows, unsafe_unique, seed=seed, repetitions=repetitions
            ),
        }
    )


def _cross_platform(
    value: AggregationInput,
) -> Mapping[str, CrossPlatformSummary]:
    summaries: dict[str, CrossPlatformSummary] = {}
    shared_models = set(value.raw_frozen_records.get("macos", {})) & set(
        value.raw_frozen_records.get("linux", {})
    )
    for model in sorted(shared_models):
        key = f"{model}/TEST_RAW_FROZEN"
        summaries[key] = compare_platforms(
            value.raw_frozen_records["macos"][model],
            value.raw_frozen_records["linux"][model],
            mac_evidence_root=value.run_evidence[
                ("macos", model, "TEST_RAW_FROZEN")
            ].evidence_root,
            linux_evidence_root=value.run_evidence[
                ("linux", model, "TEST_RAW_FROZEN")
            ].evidence_root,
        )
    shared_formal_models = set(value.formal_records.get("macos", {})) & set(
        value.formal_records.get("linux", {})
    )
    for model in sorted(shared_formal_models):
        shared_configs = set(value.formal_records["macos"][model]) & set(
            value.formal_records["linux"][model]
        )
        for config in sorted(shared_configs):
            key = f"{model}/{config}"
            summaries[key] = compare_platforms(
                value.formal_records["macos"][model][config],
                value.formal_records["linux"][model][config],
                mac_evidence_root=value.run_evidence[
                    ("macos", model, config)
                ].evidence_root,
                linux_evidence_root=value.run_evidence[
                    ("linux", model, config)
                ].evidence_root,
            )
    return MappingProxyType(summaries)


class MetricsAggregator:
    """Aggregate the exact raw/formal/oracle matrices without dropping errors."""

    def aggregate(self, input: AggregationInput) -> BenchmarkSummary:
        truth_root, timings_by_key = _validate_input(input)
        raw: dict[str, Mapping[str, RawMetricSummary]] = {}
        formal: dict[str, Mapping[str, Mapping[str, FormalMetricSummary]]] = {}
        oracle: dict[str, Mapping[str, RawMetricSummary]] = {}
        performances: dict[str, PerformanceSummary] = {}
        resources: dict[str, ResourceSummary] = {}
        per_image: list[PerImageSummary] = []
        metric_cache: dict[tuple[object, ...], _MetricCore] = {}

        for platform in sorted(input.raw_frozen_records):
            models: dict[str, RawMetricSummary] = {}
            for model in sorted(input.raw_frozen_records[platform]):
                records = input.raw_frozen_records[platform][model]
                key = (platform, model, "TEST_RAW_FROZEN")
                cell = _aggregate_cell(
                    input,
                    truth_root,
                    timings_by_key,
                    platform=platform,
                    model=model,
                    config="TEST_RAW_FROZEN",
                    records=records,
                    evidence=input.run_evidence[key],
                    metric_cache=metric_cache,
                )
                models[model] = RawMetricSummary(
                    sample_count=len(records),
                    mask_ap50=cell.ap50,
                    mask_ap50_95=cell.ap50_95,
                    ap_confidence_intervals=cell.ap_intervals,
                    candidate_count_distribution=_candidate_distribution(records),
                    error_count=sum(
                        record.record_status is RecordStatus.ERROR
                        for record in records
                    ),
                    instance_metrics=cell.instance,
                    metric_details=cell.details,
                    scenarios=cell.scenarios,
                )
                label = f"{platform}/{model}/TEST_RAW_FROZEN"
                performances[label] = cell.performance
                resources[label] = cell.resource
                per_image.extend(cell.per_image)
            raw[platform] = MappingProxyType(models)

        for platform in sorted(input.formal_records):
            models: dict[str, Mapping[str, FormalMetricSummary]] = {}
            for model in sorted(input.formal_records[platform]):
                configs: dict[str, FormalMetricSummary] = {}
                for config in sorted(input.formal_records[platform][model]):
                    records = input.formal_records[platform][model][config]
                    key = (platform, model, config)
                    cell = _aggregate_cell(
                        input,
                        truth_root,
                        timings_by_key,
                        platform=platform,
                        model=model,
                        config=config,
                        records=records,
                        evidence=input.run_evidence[key],
                        metric_cache=metric_cache,
                    )
                    decisions = aggregate_decisions(records, input.truth_samples)
                    configs[config] = FormalMetricSummary(
                        sample_count=len(records),
                        error_count=decisions.error_count,
                        error_rate=float(decisions.error_count / len(records)),
                        timeout_count=sum(record.timed_out for record in records),
                        oom_count=sum(record.oom for record in records),
                        mask_ap50=cell.ap50,
                        mask_ap50_95=cell.ap50_95,
                        ap_confidence_intervals=cell.ap_intervals,
                        decision_metrics=decisions,
                        instance_metrics=cell.instance,
                        metric_details=cell.details,
                        safety_confidence_intervals=_decision_intervals(
                            records,
                            input.truth_samples,
                            seed=input.bootstrap_seed,
                            repetitions=input.bootstrap_repetitions,
                        ),
                        scenarios=cell.scenarios,
                        performance=cell.performance,
                    )
                    label = f"{platform}/{model}/{config}"
                    performances[label] = cell.performance
                    resources[label] = cell.resource
                    per_image.extend(cell.per_image)
                models[model] = MappingProxyType(configs)
            formal[platform] = MappingProxyType(models)

        for platform in sorted(input.oracle_records):
            models: dict[str, RawMetricSummary] = {}
            for model in sorted(input.oracle_records[platform]):
                records = input.oracle_records[platform][model]
                key = (platform, model, "ORACLE_DIAGNOSTIC")
                cell = _aggregate_cell(
                    input,
                    truth_root,
                    timings_by_key,
                    platform=platform,
                    model=model,
                    config="ORACLE_DIAGNOSTIC",
                    records=records,
                    evidence=input.oracle_evidence[key],
                    metric_cache=metric_cache,
                )
                models[model] = RawMetricSummary(
                    sample_count=len(records),
                    mask_ap50=cell.ap50,
                    mask_ap50_95=cell.ap50_95,
                    ap_confidence_intervals=cell.ap_intervals,
                    candidate_count_distribution=_candidate_distribution(records),
                    error_count=sum(
                        record.record_status is RecordStatus.ERROR
                        for record in records
                    ),
                    instance_metrics=cell.instance,
                    metric_details=cell.details,
                    scenarios=cell.scenarios,
                )
                per_image.extend(cell.per_image)
            oracle[platform] = MappingProxyType(models)

        deployable = False
        qualification = "NON_FORMAL_INVALID_FOR_DEPLOYMENT"
        overall_status = RunStatus.INVALID
        invalid_reasons = ("NON_FORMAL",)
        if input.formal:
            safety_summaries = [
                summary
                for platform in formal.values()
                for models in platform.values()
                for summary in models.values()
            ]
            lock_safe = all(
                lock.deployable and lock.outcome == "SAFE_CALIBRATED"
                for lock in input.threshold_locks.values()
            )
            decision_safe = all(
                summary.error_count == 0
                and summary.decision_metrics.unsafe_unique_rate == 0.0
                for summary in safety_summaries
            )
            deployable = lock_safe and decision_safe
            qualification = (
                "FORMAL_DEPLOYABLE"
                if deployable
                else "FORMAL_CHARACTERIZATION_NOT_DEPLOYABLE"
            )
            overall_status = RunStatus.VALID
            invalid_reasons = ()
        locks = MappingProxyType(
            {
                model: lock.lock_sha256
                for model, lock in sorted(input.threshold_locks.items())
            }
        )
        return BenchmarkSummary(
            schema_version=SCHEMA_VERSION,
            formal=input.formal,
            qualification_status=qualification,
            deployable=deployable,
            source_commit=input.source_commit,
            dataset_archive_sha256=input.dataset_archive_sha256,
            test_inventory_sha256=input.test_inventory_sha256,
            threshold_lock_sha256_by_model=locks,
            raw_frozen_by_platform_model=MappingProxyType(raw),
            formal_by_platform_model_config=MappingProxyType(formal),
            oracle_diagnostic_by_platform_model=MappingProxyType(oracle),
            cross_platform=_cross_platform(input),
            performance=MappingProxyType(dict(sorted(performances.items()))),
            resource_summary=MappingProxyType(dict(sorted(resources.items()))),
            per_image=tuple(
                sorted(
                    per_image,
                    key=lambda row: (
                        row.platform,
                        row.model,
                        row.config,
                        row.formal_sample_index,
                        row.image_sha256,
                    ),
                )
            ),
            overall_status=overall_status,
            invalid_reasons=invalid_reasons,
        )


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[Mapping[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=tuple(fieldnames),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _scenario_rows(summary: BenchmarkSummary) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def append_group(
        section: str,
        platform: str,
        model: str,
        config: str,
        scenarios: Mapping[str, ScenarioMetricSummary],
    ) -> None:
        for scenario, values in sorted(scenarios.items()):
            safety = values.safety_metrics
            rows.append(
                {
                    "section": section,
                    "platform": platform,
                    "model": model,
                    "config": config,
                    "scenario": scenario,
                    "sample_count": values.sample_count,
                    "error_count": values.error_count,
                    "timeout_count": values.timeout_count,
                    "oom_count": values.oom_count,
                    "mask_ap50": values.mask_ap50,
                    "mask_ap50_95": values.mask_ap50_95,
                    "precision_at_50": values.instance_metrics.precision,
                    "recall_at_50": values.instance_metrics.recall,
                    "f1_at_50": values.metric_details.f1,
                    "exact_count_accuracy": values.metric_details.exact_count_accuracy,
                    "fp_per_image": values.metric_details.fp_per_image,
                    "fn_per_image": values.metric_details.fn_per_image,
                    "no_cup_fpr": safety.no_cup_false_positive_rate,
                    "two_cup_both_recall": safety.two_cup_both_matched_recall,
                    "non_cup_leakage_ratio": safety.non_cup_leakage_ratio,
                    "decision_macro_f1": values.decision_metrics.macro_f1,
                    "unique_success_rate": (
                        values.decision_metrics.unique_success_rate
                    ),
                    "unsafe_unique_rate": (
                        values.decision_metrics.unsafe_unique_rate
                    ),
                    "decision_confusion_json": canonical_json_bytes(
                        _jsonable(values.decision_metrics.confusion)
                    ).decode("utf-8").strip(),
                    "confidence_intervals_json": canonical_json_bytes(
                        {
                            "ap": _jsonable(values.ap_confidence_intervals),
                            "decision": _jsonable(
                                values.decision_confidence_intervals
                            ),
                            "instance": _jsonable(
                                values.metric_details.confidence_intervals
                            ),
                            "safety": _jsonable(values.confidence_intervals),
                        }
                    ).decode("utf-8").strip(),
                }
            )

    for platform, models in summary.raw_frozen_by_platform_model.items():
        for model, values in models.items():
            append_group("TEST_RAW_FROZEN", platform, model, "TEST_RAW_FROZEN", values.scenarios)
    for platform, models in summary.formal_by_platform_model_config.items():
        for model, configs in models.items():
            for config, values in configs.items():
                append_group("FORMAL_SAFETY", platform, model, config, values.scenarios)
    for platform, models in summary.oracle_diagnostic_by_platform_model.items():
        for model, values in models.items():
            append_group("ORACLE_DIAGNOSTIC", platform, model, "ORACLE_DIAGNOSTIC", values.scenarios)
    return rows


def _per_image_rows_for_csv(summary: BenchmarkSummary) -> list[dict[str, object]]:
    return [
        {
            "platform": row.platform,
            "model": row.model,
            "config": row.config,
            "run_kind": row.run_kind,
            "formal_sample_index": row.formal_sample_index,
            "image_sha256": row.image_sha256,
            "scenario": row.scenario,
            "record_status": row.record_status,
            "truth_count": row.truth_count,
            "candidate_count": row.candidate_count,
            "candidates_json": canonical_json_bytes(
                _jsonable(row.candidates)
            ).decode("utf-8").strip(),
            "matched_count_at_50": row.matched_count_at_50,
            "true_positive": row.true_positive,
            "false_positive": row.false_positive,
            "false_negative": row.false_negative,
            "exact_count": row.exact_count,
            "decision": row.decision,
            "error_type": row.error_type,
            "timed_out": row.timed_out,
            "oom": row.oom,
            "total_ms": row.total_ms,
            "phase_timings_json": canonical_json_bytes(
                _jsonable(row.phase_timings_ms)
            ).decode("utf-8").strip(),
            "resource_observations_json": canonical_json_bytes(
                _jsonable(row.resource_observations)
            ).decode("utf-8").strip(),
            "resource_sampling_frequency_hz": (
                row.resource_sampling_frequency_hz
            ),
            "resource_sampling_gaps_ms_json": canonical_json_bytes(
                row.resource_sampling_gaps_ms
            ).decode("utf-8").strip(),
        }
        for row in summary.per_image
    ]


def _mismatch_rows(summary: BenchmarkSummary) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for comparison, values in summary.cross_platform.items():
        for item in values.items:
            if not item.is_mismatch:
                continue
            rows.append(
                {
                    "comparison": comparison,
                    "formal_sample_index": item.formal_sample_index,
                    "image_sha256": item.image_sha256,
                    "model_id": item.model_id,
                    "config_sha256": item.config_sha256,
                    "run_kind": item.run_kind,
                    "candidate_count_equal": item.candidate_count_equal,
                    "candidate_ids_equal": item.candidate_ids_equal,
                    "decision_equal": item.decision_equal,
                    "error_type_equal": item.error_type_equal,
                    "mac_decision": item.mac_decision,
                    "linux_decision": item.linux_decision,
                    "mac_error_type": item.mac_error_type,
                    "linux_error_type": item.linux_error_type,
                    "mac_runtime_device": item.mac_runtime_device,
                    "linux_runtime_device": item.linux_runtime_device,
                    "runtime_device_pair_expected": item.runtime_device_pair_expected,
                    "weights_sha256_equal": item.weights_sha256_equal,
                    "runtime_name_equal": item.runtime_name_equal,
                    "runtime_version_equal": item.runtime_version_equal,
                    "runtime_environment_equal": item.runtime_environment_equal,
                    "runtime_environment_identity_equal": (
                        item.runtime_environment_identity_equal
                    ),
                    "mac_runtime_environment_json": canonical_json_bytes(
                        _jsonable(item.mac_runtime_environment)
                    ).decode("utf-8").strip(),
                    "linux_runtime_environment_json": canonical_json_bytes(
                        _jsonable(item.linux_runtime_environment)
                    ).decode("utf-8").strip(),
                    "candidate_pairs_json": canonical_json_bytes(
                        _jsonable(item.candidate_pairs)
                    ).decode("utf-8").strip(),
                    "unmatched_mac_candidate_ids_json": canonical_json_bytes(
                        item.unmatched_mac_candidate_ids
                    ).decode("utf-8").strip(),
                    "unmatched_linux_candidate_ids_json": canonical_json_bytes(
                        item.unmatched_linux_candidate_ids
                    ).decode("utf-8").strip(),
                }
            )
    return rows


def _benchmark_markdown(summary: BenchmarkSummary) -> bytes:
    lines = [
        "# Perception benchmark report",
        "",
        f"Qualification status: `{summary.qualification_status}`",
        f"Formal: `{str(summary.formal).lower()}`",
        f"Deployable: `{str(summary.deployable).lower()}`",
        "",
        "## TEST_RAW_FROZEN raw capability",
        "",
        "Raw AP ranks model capability only; it does not establish deployment safety.",
        "",
    ]
    ranked = sorted(
        (
            (values.mask_ap50_95, platform, model, values)
            for platform, models in summary.raw_frozen_by_platform_model.items()
            for model, values in models.items()
        ),
        key=lambda row: (
            row[0] is None,
            0.0 if row[0] is None else -row[0],
            row[1],
            row[2],
        ),
    )
    for rank, (_, platform, model, values) in enumerate(ranked, start=1):
        lines.append(
            f"{rank}. `{platform}/{model}`: mask_AP50={values.mask_ap50}, mask_AP50_95={values.mask_ap50_95}, n={values.sample_count}"
        )
    lines.extend(["", "## Production safety contract", ""])
    for platform, models in summary.formal_by_platform_model_config.items():
        for model, configs in models.items():
            if "production" not in configs:
                continue
            values = configs["production"]
            lines.append(
                f"- `{platform}/{model}/production`: unsafe_unique={values.decision_metrics.unsafe_unique_rate}, errors={values.error_count}/{values.sample_count}"
            )
    lines.extend(["", "## Calibrated / characterization safety contract", ""])
    for platform, models in summary.formal_by_platform_model_config.items():
        for model, configs in models.items():
            for config, values in configs.items():
                if config == "production":
                    continue
                lines.append(
                    f"- `{platform}/{model}/{config}`: unsafe_unique={values.decision_metrics.unsafe_unique_rate}, errors={values.error_count}/{values.sample_count}"
                )
    lines.extend(
        [
            "",
            "## Deployment decision",
            "",
            "Deployment is derived only from formal decision metrics and frozen ThresholdLock deployable/outcome fields.",
        ]
    )
    if summary.oracle_diagnostic_by_platform_model:
        lines.extend(
            [
                "",
                "## ORACLE_DIAGNOSTIC (optional, excluded)",
                "",
                "These values are excluded from capability ranking, safety, deployment, and configuration backfill.",
            ]
        )
        for platform, models in summary.oracle_diagnostic_by_platform_model.items():
            for model, values in models.items():
                lines.append(
                    f"- `{platform}/{model}`: mask_AP50={values.mask_ap50}, n={values.sample_count}"
                )
    return ("\n".join(lines) + "\n").encode("utf-8")


class ReportWriter:
    """Publish the exact report tree atomically into a previously absent root."""

    def write(self, summary: BenchmarkSummary, output_root: Path) -> EvidenceIndex:
        if not isinstance(summary, BenchmarkSummary):
            raise ValueError("summary must be a BenchmarkSummary")
        target = Path(output_root)
        if target.exists() or target.is_symlink():
            raise FileExistsError("output_root must be absent for atomic publication")
        parent = target.parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError("output_root parent must be an existing directory")
        temporary = Path(
            tempfile.mkdtemp(dir=parent, prefix=f".{target.name}.task8-")
        )
        scenario_fields = (
            "section", "platform", "model", "config", "scenario",
            "sample_count", "error_count", "timeout_count", "oom_count",
            "mask_ap50", "mask_ap50_95",
            "precision_at_50", "recall_at_50",
            "f1_at_50", "exact_count_accuracy", "fp_per_image", "fn_per_image",
            "no_cup_fpr", "two_cup_both_recall", "non_cup_leakage_ratio",
            "decision_macro_f1", "unique_success_rate", "unsafe_unique_rate",
            "decision_confusion_json",
            "confidence_intervals_json",
        )
        per_image_fields = (
            "platform", "model", "config", "run_kind", "formal_sample_index",
            "image_sha256", "scenario", "record_status", "truth_count",
            "candidate_count", "candidates_json", "matched_count_at_50",
            "true_positive",
            "false_positive", "false_negative", "exact_count", "decision",
            "error_type", "timed_out", "oom", "total_ms", "phase_timings_json",
            "resource_observations_json",
            "resource_sampling_frequency_hz", "resource_sampling_gaps_ms_json",
        )
        mismatch_fields = (
            "comparison", "formal_sample_index", "image_sha256", "model_id",
            "config_sha256", "run_kind", "candidate_count_equal",
            "candidate_ids_equal", "decision_equal", "error_type_equal",
            "mac_decision", "linux_decision", "mac_error_type", "linux_error_type",
            "mac_runtime_device", "linux_runtime_device",
            "runtime_device_pair_expected", "weights_sha256_equal",
            "runtime_name_equal", "runtime_version_equal",
            "runtime_environment_equal", "runtime_environment_identity_equal",
            "mac_runtime_environment_json", "linux_runtime_environment_json",
            "candidate_pairs_json", "unmatched_mac_candidate_ids_json",
            "unmatched_linux_candidate_ids_json",
        )
        payloads = {
            "metrics/summary.json": canonical_json_bytes(_jsonable(summary)),
            "metrics/per-scenario.csv": _csv_bytes(
                scenario_fields, _scenario_rows(summary)
            ),
            "metrics/per-image.csv": _csv_bytes(
                per_image_fields, _per_image_rows_for_csv(summary)
            ),
            "metrics/cross-platform-mismatches.csv": _csv_bytes(
                mismatch_fields, _mismatch_rows(summary)
            ),
            "performance/latency.json": canonical_json_bytes(
                _jsonable(summary.performance)
            ),
            "performance/resources.json": canonical_json_bytes(
                _jsonable(summary.resource_summary)
            ),
            "report/benchmark.md": _benchmark_markdown(summary),
        }
        if tuple(payloads) != _PAYLOAD_PATHS:
            raise RuntimeError("report payload tree does not match the planned tree")
        try:
            for relative_path, payload in payloads.items():
                _atomic_write_bytes(temporary / relative_path, payload)
            entries = tuple(
                EvidenceEntry(
                    relative_path=relative_path,
                    size_bytes=len(payloads[relative_path]),
                    sha256=sha256_bytes(payloads[relative_path]),
                )
                for relative_path in _PAYLOAD_PATHS
            )
            index = EvidenceIndex(
                schema_version="so101-perception-benchmark/evidence-index/v1",
                payload_index_semantics=_INDEX_SEMANTICS,
                entries=entries,
            )
            _atomic_write_bytes(
                temporary / "evidence-index.json",
                canonical_json_bytes(_jsonable(index)),
            )
            os.replace(temporary, target)
            descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return index
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise


__all__ = (
    "AggregationInput",
    "BenchmarkSummary",
    "ColdProcessSample",
    "EvidenceEntry",
    "EvidenceIndex",
    "FormalMetricSummary",
    "MetricDetails",
    "MetricsAggregator",
    "PerImageSummary",
    "PerformanceSummary",
    "RawMetricSummary",
    "ReportWriter",
    "ResourceObservation",
    "ResourcePhaseSummary",
    "ResourceSummary",
    "ResourceTrace",
    "RunAggregationEvidence",
    "ScenarioMetricSummary",
    "percentile",
)
