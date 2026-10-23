"""The metrics aggregator."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from so101_demo.perception_benchmark.contracts import (
    SCHEMA_VERSION,
    RecordStatus,
    RunStatus,
)
from so101_demo.perception_benchmark.decisions import (
    aggregate_decisions,
)
from so101_demo.perception_benchmark.reporting.evidence import _validate_input
from so101_demo.perception_benchmark.reporting.records import (
    AggregationInput,
    BenchmarkSummary,
    FormalMetricSummary,
    PerformanceSummary,
    PerImageSummary,
    RawMetricSummary,
    ResourceSummary,
)
from so101_demo.perception_benchmark.reporting.summaries import (
    _aggregate_cell,
    _candidate_distribution,
    _cross_platform,
    _decision_intervals,
    _MetricCore,
)


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
