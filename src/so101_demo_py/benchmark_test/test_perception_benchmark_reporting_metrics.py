"""Error records, false positive rates, bootstrap intervals and aggregation refusals."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from perception_benchmark_reporting_support import _candidate, _extended_document, _fixture
import pytest

from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    DecisionOutput,
    PredictionRecord,
    RunKind,
)
from so101_demo.perception_benchmark.reporting import records as reporting_module_records
from so101_demo.perception_benchmark.reporting.aggregator import MetricsAggregator
from so101_demo.perception_benchmark.reporting.records import (
    RunAggregationEvidence,
)
from so101_demo.perception_benchmark.timing import ResourceSample


def test_report_keeps_error_record_in_every_denominator(tmp_path: Path) -> None:
    summary = MetricsAggregator().aggregate(_fixture(tmp_path))
    formal = summary.formal_by_platform_model_config["linux"]["yolo_seg"][
        "production"
    ]

    assert formal.sample_count == 4
    assert formal.error_count == 1
    assert formal.error_rate == 0.25
    assert formal.timeout_count == 1
    assert formal.decision_metrics.sample_count == 4
    assert sum(
        sum(outputs.values())
        for outputs in formal.decision_metrics.confusion.values()
    ) == 4
    assert formal.instance_metrics.fn >= 1
    assert formal.scenarios["no_cup"].sample_count == 1
    assert formal.scenarios["one_cup"].timeout_count == 1
    assert formal.scenarios["one_cup"].oom_count == 0
    assert formal.scenarios["one_cup"].confidence_intervals[
        "timeout_rate"
    ].lower == pytest.approx(1.0)
    assert formal.scenarios["one_cup"].confidence_intervals[
        "oom_rate"
    ].upper == pytest.approx(0.0)
    assert formal.performance.images_per_second == pytest.approx(4 / 0.086)
    assert len(summary.per_image) == 8
    assert summary.formal is False
    assert summary.deployable is False
    assert summary.qualification_status == "NON_FORMAL_INVALID_FOR_DEPLOYMENT"


@pytest.mark.parametrize("flag", ("timed_out", "oom"))
def test_ok_record_cannot_claim_timeout_or_oom(
    tmp_path: Path,
    flag: str,
) -> None:
    aggregation_input = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    records = list(aggregation_input.raw_frozen_records["linux"]["yolo_seg"])
    records[0] = replace(records[0], **{flag: True})
    record_tuple = tuple(records)
    evidence = aggregation_input.run_evidence[key]
    aggregation_input = replace(
        aggregation_input,
        raw_frozen_records={"linux": {"yolo_seg": record_tuple}},
        run_evidence={
            **aggregation_input.run_evidence,
            key: replace(
                evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=10.0 + position)
                    for position, record in enumerate(record_tuple)
                ),
            ),
        },
    )

    with pytest.raises(ValueError, match="timeout|OOM|ERROR"):
        MetricsAggregator().aggregate(aggregation_input)


def test_no_cup_fpr_uses_effective_raw_candidates_not_selector_decision(
    tmp_path: Path,
) -> None:
    aggregation_input = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    candidate_root = aggregation_input.run_evidence[key].evidence_root
    false_positive = _candidate(
        candidate_root,
        0,
        0,
        [[1, 0, 0], [0, 0, 0], [0, 0, 0]],
        score=0.1,
    )
    records = list(aggregation_input.raw_frozen_records["linux"]["yolo_seg"])
    records[0] = replace(
        records[0],
        raw_candidates=(false_positive,),
        raw_count=1,
    )
    record_tuple = tuple(records)
    evidence = aggregation_input.run_evidence[key]
    aggregation_input = replace(
        aggregation_input,
        raw_frozen_records={"linux": {"yolo_seg": record_tuple}},
        run_evidence={
            **aggregation_input.run_evidence,
            key: replace(
                evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=10.0 + position)
                    for position, record in enumerate(record_tuple)
                ),
            ),
        },
    )

    summary = MetricsAggregator().aggregate(aggregation_input)
    safety = summary.raw_frozen_by_platform_model["linux"]["yolo_seg"].scenarios[
        "no_cup"
    ].safety_metrics

    assert records[0].decision is DecisionOutput.NOT_FOUND
    assert safety.no_cup_false_positive_count == 1
    assert safety.no_cup_false_positive_rate == 1.0


def test_all_zero_predicted_leakage_bootstrap_is_undefined(tmp_path: Path) -> None:
    aggregation_input = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    records = list(aggregation_input.raw_frozen_records["linux"]["yolo_seg"])
    records[3] = replace(
        records[3],
        raw_candidates=(),
        raw_count=0,
        decision=DecisionOutput.NOT_FOUND,
        selected_candidate_id=None,
        rejection_reason="TARGET_NOT_FOUND",
    )
    record_tuple = tuple(records)
    evidence = aggregation_input.run_evidence[key]
    aggregation_input = replace(
        aggregation_input,
        raw_frozen_records={"linux": {"yolo_seg": record_tuple}},
        run_evidence={
            **aggregation_input.run_evidence,
            key: replace(
                evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=10.0 + position)
                    for position, record in enumerate(record_tuple)
                ),
            ),
        },
    )

    summary = MetricsAggregator().aggregate(aggregation_input)
    interval = summary.raw_frozen_by_platform_model["linux"]["yolo_seg"].scenarios[
        "cup_near_bottle"
    ].confidence_intervals["non_cup_leakage_ratio"]

    assert interval.lower is None
    assert interval.upper is None


def test_unavailable_resource_telemetry_stays_null_with_reasons(
    tmp_path: Path,
) -> None:
    value = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    evidence = value.run_evidence[key]
    missing_fields = (
        "process_rss_bytes",
        "process_cpu_percent",
        "gpu_memory_allocated_bytes",
        "gpu_memory_reserved_bytes",
        "gpu_utilization_percent",
        "gpu_temperature_celsius",
        "gpu_power_watts",
    )
    sample = ResourceSample(
        process_rss_bytes=None,
        process_cpu_percent=None,
        gpu_memory_allocated_bytes=None,
        gpu_memory_reserved_bytes=None,
        gpu_utilization_percent=None,
        gpu_temperature_celsius=None,
        gpu_power_watts=None,
        unavailable_reasons={field: "probe unavailable" for field in missing_fields},
        tool_versions={"resource-probe": "1.0"},
    )
    trace = reporting_module_records.ResourceTrace(
        sampling_frequency_hz=2.0,
        observations=(
            reporting_module_records.ResourceObservation(
                phase="inference",
                monotonic_ns=1_000_000,
                formal_sample_index=0,
                sample=sample,
            ),
        ),
    )
    records = value.raw_frozen_records["linux"]["yolo_seg"]
    documents = tuple(
        _extended_document(
            record,
            total_ms=10.0 + position,
            resource_samples=(sample,) if position == 0 else (),
        )
        for position, record in enumerate(records)
    )
    value = replace(
        value,
        run_evidence={
            **value.run_evidence,
            key: replace(
                evidence,
                extended_record_documents=documents,
                resource_trace=trace,
            ),
        },
    )

    summary = MetricsAggregator().aggregate(value)
    resources = summary.resource_summary["linux/yolo_seg/TEST_RAW_FROZEN"]

    assert resources.peak_process_cpu_percent is None
    assert resources.peak_gpu_power_watts is None
    assert resources.unavailable_reasons["peak_gpu_power_watts"] == (
        "probe unavailable"
    )
    assert resources.phase_summaries[
        "inference"
    ].peak_gpu_utilization_percent is None


def test_error_record_may_retain_partial_candidates_but_metrics_count_zero(
    tmp_path: Path,
) -> None:
    aggregation_input = _fixture(tmp_path)
    raw_records = aggregation_input.raw_frozen_records["linux"]["yolo_seg"]
    production_records = list(
        aggregation_input.formal_records["linux"]["yolo_seg"]["production"]
    )
    production_records[1] = replace(
        production_records[1],
        raw_candidates=raw_records[1].raw_candidates,
        raw_count=1,
    )
    records = tuple(production_records)
    evidence = aggregation_input.run_evidence[("linux", "yolo_seg", "production")]
    aggregation_input = replace(
        aggregation_input,
        formal_records={"linux": {"yolo_seg": {"production": records}}},
        run_evidence={
            **aggregation_input.run_evidence,
            ("linux", "yolo_seg", "production"): replace(
                evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=20.0 + position)
                    for position, record in enumerate(records)
                ),
            ),
        },
    )

    summary = MetricsAggregator().aggregate(aggregation_input)
    row = next(
        item
        for item in summary.per_image
        if item.config == "production" and item.formal_sample_index == 1
    )

    assert row.record_status == "ERROR"
    assert row.candidate_count == 0
    assert row.false_positive == 0


def test_raw_frozen_ap_is_rankable_but_oracle_is_separate(tmp_path: Path) -> None:
    aggregation_input = _fixture(tmp_path)
    raw_records = aggregation_input.raw_frozen_records["linux"]["yolo_seg"]
    oracle_records = tuple(
        replace(record, run_kind=RunKind.ORACLE_DIAGNOSTIC, run_id="oracle-run")
        for record in raw_records
    )
    raw_evidence = aggregation_input.run_evidence[
        ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    ]
    oracle_documents = tuple(
        _extended_document(record, total_ms=50.0 + position)
        for position, record in enumerate(oracle_records)
    )
    aggregation_input = replace(
        aggregation_input,
        oracle_records={"linux": {"yolo_seg": oracle_records}},
        oracle_evidence={
            ("linux", "yolo_seg", "ORACLE_DIAGNOSTIC"): replace(
                raw_evidence,
                extended_record_documents=oracle_documents,
            )
        },
    )

    summary = MetricsAggregator().aggregate(aggregation_input)

    assert summary.raw_frozen_by_platform_model["linux"]["yolo_seg"].mask_ap50 > 0.0
    assert "ORACLE_DIAGNOSTIC" not in summary.formal_by_platform_model_config[
        "linux"
    ]["yolo_seg"]
    assert "yolo_seg" in summary.oracle_diagnostic_by_platform_model["linux"]


def test_scenarios_retain_ap_decisions_and_deterministic_ap_intervals(
    tmp_path: Path,
) -> None:
    summary = MetricsAggregator().aggregate(_fixture(tmp_path))
    raw = summary.raw_frozen_by_platform_model["linux"]["yolo_seg"]
    scenario = raw.scenarios["one_cup"]

    assert raw.ap_confidence_intervals["mask_ap50"].lower is not None
    assert scenario.mask_ap50 == pytest.approx(1.0)
    assert scenario.mask_ap50_95 == pytest.approx(1.0)
    assert scenario.ap_confidence_intervals["mask_ap50"].lower == pytest.approx(
        1.0
    )
    assert scenario.decision_metrics.sample_count == 1
    assert sum(
        sum(outputs.values())
        for outputs in scenario.decision_metrics.confusion.values()
    ) == 1


def test_bootstrap_skips_undefined_replicates_instead_of_coercing_zero(
    tmp_path: Path,
) -> None:
    aggregation_input = _fixture(tmp_path)
    truths = tuple(
        replace(truth, scenario="one_cup")
        if truth.formal_sample_index == 0
        else truth
        for truth in aggregation_input.truth_samples
    )

    def mutate_records(
        records: tuple[PredictionRecord, ...],
    ) -> tuple[PredictionRecord, ...]:
        return tuple(
            replace(record, scenario="one_cup")
            if record.formal_sample_index == 0
            else record
            for record in records
        )

    raw_records = mutate_records(
        aggregation_input.raw_frozen_records["linux"]["yolo_seg"]
    )
    production_records = mutate_records(
        aggregation_input.formal_records["linux"]["yolo_seg"]["production"]
    )
    raw_evidence = aggregation_input.run_evidence[
        ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    ]
    production_evidence = aggregation_input.run_evidence[
        ("linux", "yolo_seg", "production")
    ]
    aggregation_input = replace(
        aggregation_input,
        truth_samples=truths,
        raw_frozen_records={"linux": {"yolo_seg": raw_records}},
        formal_records={
            "linux": {"yolo_seg": {"production": production_records}}
        },
        run_evidence={
            ("linux", "yolo_seg", "TEST_RAW_FROZEN"): replace(
                raw_evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=10.0 + position)
                    for position, record in enumerate(raw_records)
                ),
            ),
            ("linux", "yolo_seg", "production"): replace(
                production_evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=20.0 + position)
                    for position, record in enumerate(production_records)
                ),
            ),
        },
    )

    summary = MetricsAggregator().aggregate(aggregation_input)
    interval = summary.raw_frozen_by_platform_model["linux"]["yolo_seg"].scenarios[
        "one_cup"
    ].metric_details.confidence_intervals["mean_iou"]

    assert interval.lower == pytest.approx(1.0)
    assert interval.upper == pytest.approx(1.0)


def test_leakage_bootstrap_uses_the_pixel_weighted_metric(tmp_path: Path) -> None:
    aggregation_input = _fixture(tmp_path)
    candidate_root = aggregation_input.run_evidence[
        ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    ].evidence_root
    all_pixels = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
    leaky_candidate = _candidate(candidate_root, 2, 99, all_pixels, score=0.8)

    truths = tuple(
        replace(truth, scenario="cup_near_bottle")
        if truth.formal_sample_index == 2
        else truth
        for truth in aggregation_input.truth_samples
    )

    def mutate_records(
        records: tuple[PredictionRecord, ...],
    ) -> tuple[PredictionRecord, ...]:
        return tuple(
            replace(
                record,
                scenario="cup_near_bottle",
                raw_candidates=(record.raw_candidates[0], leaky_candidate),
                raw_count=2,
            )
            if record.formal_sample_index == 2
            else record
            for record in records
        )

    raw_records = mutate_records(
        aggregation_input.raw_frozen_records["linux"]["yolo_seg"]
    )
    production_records = mutate_records(
        aggregation_input.formal_records["linux"]["yolo_seg"]["production"]
    )
    raw_evidence = aggregation_input.run_evidence[
        ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    ]
    production_evidence = aggregation_input.run_evidence[
        ("linux", "yolo_seg", "production")
    ]
    aggregation_input = replace(
        aggregation_input,
        truth_samples=truths,
        raw_frozen_records={"linux": {"yolo_seg": raw_records}},
        formal_records={
            "linux": {"yolo_seg": {"production": production_records}}
        },
        run_evidence={
            ("linux", "yolo_seg", "TEST_RAW_FROZEN"): replace(
                raw_evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=10.0 + position)
                    for position, record in enumerate(raw_records)
                ),
            ),
            ("linux", "yolo_seg", "production"): replace(
                production_evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=20.0 + position)
                    for position, record in enumerate(production_records)
                ),
            ),
        },
        bootstrap_repetitions=1,
    )

    summary = MetricsAggregator().aggregate(aggregation_input)
    scenario = summary.raw_frozen_by_platform_model["linux"]["yolo_seg"].scenarios[
        "cup_near_bottle"
    ]
    interval = scenario.confidence_intervals["non_cup_leakage_ratio"]

    assert scenario.safety_metrics.non_cup_leakage_ratio == pytest.approx(3 / 13)
    assert interval.lower == pytest.approx(3 / 13)
    assert interval.upper == pytest.approx(3 / 13)


def test_aggregation_rejects_extended_document_identity_tamper(tmp_path: Path) -> None:
    aggregation_input = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "production")
    evidence = aggregation_input.run_evidence[key]
    documents = [dict(document) for document in evidence.extended_record_documents]
    documents[0]["image_sha256"] = "f" * 64
    aggregation_input = replace(
        aggregation_input,
        run_evidence={
            **aggregation_input.run_evidence,
            key: replace(evidence, extended_record_documents=tuple(documents)),
        },
    )

    with pytest.raises(ValueError, match="extended record.*identity|does not match"):
        MetricsAggregator().aggregate(aggregation_input)


def test_aggregation_rejects_nonfinite_error_wall_time(tmp_path: Path) -> None:
    aggregation_input = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "production")
    evidence = aggregation_input.run_evidence[key]
    documents = [dict(document) for document in evidence.extended_record_documents]
    timing = dict(documents[1]["timing_breakdown"])
    timing["total_ms"] = float("nan")
    documents[1]["timing_breakdown"] = timing
    aggregation_input = replace(
        aggregation_input,
        run_evidence={
            **aggregation_input.run_evidence,
            key: replace(evidence, extended_record_documents=tuple(documents)),
        },
    )

    with pytest.raises(ValueError, match="total_ms"):
        MetricsAggregator().aggregate(aggregation_input)


def test_aggregation_rejects_typed_model_to_cell_anchor_mismatch(
    tmp_path: Path,
) -> None:
    aggregation_input = _fixture(tmp_path)
    renamed_evidence: dict[tuple[str, str, str], RunAggregationEvidence] = {}
    for (platform, _model, config), evidence in aggregation_input.run_evidence.items():
        documents = []
        for document in evidence.extended_record_documents:
            renamed = dict(document)
            renamed["model"] = "grounded_sam"
            documents.append(renamed)
        renamed_evidence[(platform, "grounded_sam", config)] = replace(
            evidence,
            extended_record_documents=tuple(documents),
        )
    aggregation_input = replace(
        aggregation_input,
        raw_frozen_records={
            "linux": {
                "grounded_sam": aggregation_input.raw_frozen_records["linux"][
                    "yolo_seg"
                ]
            }
        },
        formal_records={
            "linux": {
                "grounded_sam": {
                    "production": aggregation_input.formal_records["linux"][
                        "yolo_seg"
                    ]["production"]
                }
            }
        },
        run_evidence=renamed_evidence,
    )

    with pytest.raises(ValueError, match="model.*anchor"):
        MetricsAggregator().aggregate(aggregation_input)


@pytest.mark.parametrize("mutation", ("model_id", "weights_sha256"))
def test_aggregation_rejects_mixed_runtime_signature_within_one_cell(
    tmp_path: Path,
    mutation: str,
) -> None:
    aggregation_input = _fixture(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    records = list(aggregation_input.raw_frozen_records["linux"]["yolo_seg"])
    if mutation == "model_id":
        records[1] = replace(
            records[1],
            model_id=GROUNDED_SAM_MODEL_ID,
            raw_candidates=(),
            raw_count=0,
            decision=DecisionOutput.NOT_FOUND,
            selected_candidate_id=None,
            rejection_reason="TARGET_NOT_FOUND",
        )
    else:
        records[1] = replace(
            records[1],
            runtime_provenance=replace(
                records[1].runtime_provenance,
                weights_sha256="8" * 64,
            ),
        )
    record_tuple = tuple(records)
    evidence = aggregation_input.run_evidence[key]
    aggregation_input = replace(
        aggregation_input,
        raw_frozen_records={"linux": {"yolo_seg": record_tuple}},
        run_evidence={
            **aggregation_input.run_evidence,
            key: replace(
                evidence,
                extended_record_documents=tuple(
                    _extended_document(record, total_ms=10.0 + position)
                    for position, record in enumerate(record_tuple)
                ),
            ),
        },
    )

    expected_error = (
        "canonical model identity"
        if mutation == "model_id"
        else "homogeneous runtime/model signature"
    )
    with pytest.raises(ValueError, match=expected_error):
        MetricsAggregator().aggregate(aggregation_input)
