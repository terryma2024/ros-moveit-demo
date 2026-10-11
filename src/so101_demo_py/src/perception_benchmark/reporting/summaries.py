"""Performance, resource and per-image summaries and the scenario cells."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from so101_demo.perception_benchmark.comparison import (
    CrossPlatformSummary,
    compare_platforms,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    PredictionRecord,
    RecordStatus,
    TruthSample,
)
from so101_demo.perception_benchmark.decisions import (
    ScenarioMetrics,
    aggregate_decisions,
    aggregate_scenarios,
)
from so101_demo.perception_benchmark.metrics import (
    ConfidenceInterval,
    ImageMetricInput,
    InstanceMetricSummary,
    compute_ap,
)
from so101_demo.perception_benchmark.reporting.evidence import _image_inputs, percentile
from so101_demo.perception_benchmark.reporting.metrics import (
    _ap_intervals,
    _bootstrap_rows,
    _metric_details,
    _per_image_leakage_counts,
)
from so101_demo.perception_benchmark.reporting.records import (
    _IOU_THRESHOLDS,
    _TIMING_FIELDS,
    AggregationInput,
    MetricDetails,
    PerformanceSummary,
    PerImageSummary,
    ResourcePhaseSummary,
    ResourceSummary,
    RunAggregationEvidence,
    ScenarioMetricSummary,
    _existing_root,
)
from so101_demo.perception_benchmark.timing import ResourceSample


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
    """Identify only inputs that can affect capability/safety metrics.

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
