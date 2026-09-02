from __future__ import annotations

import csv
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import so101_demo.perception_benchmark.reporting as reporting_module
from so101_demo.perception_benchmark.calibration import (
    LOCK_SCHEMA_VERSION,
    OBJECTIVE_VERSION,
    TIE_BREAK_VERSION,
    GroundedSamBenchmarkThresholds,
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
    YoloThresholds,
)

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    MODEL_ID_BY_NAME,
    SCHEMA_VERSION,
    YOLO_MODEL_ID,
    DecisionOutput,
    MaskRef,
    PhaseTimings,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RuntimeProvenance,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.reporting import (
    AggregationInput,
    EvidenceEntry,
    EvidenceIndex,
    MetricsAggregator,
    ReportWriter,
    RunAggregationEvidence,
    load_evidence_index,
    verify_evidence_index,
)
from so101_demo.perception_benchmark.timing import ResourceSample


_SOURCE_COMMIT = "1" * 40
_ARCHIVE_SHA = "2" * 64
_INVENTORY_SHA = "3" * 64
_LOCK_SHA = "4" * 64
_RAW_CONFIG_SHA = "5" * 64
_PRODUCTION_CONFIG_SHA = "6" * 64


def _write_mask(root: Path, name: str, pixels: list[list[int]]) -> MaskRef:
    mask = np.asarray(pixels, dtype=bool)
    relative_path = f"masks/{name}.json"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(encode_mask_rle(mask)))
    return MaskRef(
        relative_path=relative_path,
        sha256=sha256_bytes(mask.astype(np.uint8).tobytes(order="C")),
        pixel_count=int(mask.sum()),
        image_width=mask.shape[1],
        image_height=mask.shape[0],
    )


def _truth(
    root: Path,
    index: int,
    scenario: str,
    masks: tuple[list[list[int]], ...],
) -> TruthSample:
    instances = tuple(
        TruthInstance(
            instance_id=f"truth-{index}-{position}",
            label="plastic_cup",
            mask=_write_mask(root, f"truth-{index}-{position}", pixels),
        )
        for position, pixels in enumerate(masks)
    )
    return TruthSample(
        formal_sample_index=index,
        split="test",
        scenario=scenario,
        image_relpath=f"images/{index:03d}.png",
        image_sha256=f"{index + 10:064x}",
        image_width=3,
        image_height=3,
        instances=instances,
    )


def _candidate(
    root: Path,
    sample_index: int,
    position: int,
    pixels: list[list[int]],
    *,
    score: float = 0.9,
) -> RawCandidate:
    candidate_id = f"candidate-{sample_index}-{position}"
    return RawCandidate(
        candidate_id=candidate_id,
        label="plastic_cup",
        bbox_xyxy=(0.0, 0.0, 3.0, 3.0),
        mask=_write_mask(root, candidate_id, pixels),
        ranking_score=score,
        ranking_score_source="class_confidence",
        class_confidence=score,
        grounding_box_score=None,
        grounding_text_score=None,
        sam_quality=None,
    )


def _record(
    truth: TruthSample,
    candidates: tuple[RawCandidate, ...],
    *,
    run_kind: RunKind,
    config_sha256: str,
    decision: DecisionOutput,
    error: bool = False,
) -> PredictionRecord:
    selected = candidates[0].candidate_id if decision is DecisionOutput.UNIQUE else None
    rejection = {
        DecisionOutput.NOT_FOUND: "TARGET_NOT_FOUND",
        DecisionOutput.AMBIGUOUS: "TARGET_AMBIGUOUS",
    }.get(decision)
    return PredictionRecord(
        run_id=f"linux-yolo-{run_kind.value.lower()}",
        schema_version=SCHEMA_VERSION,
        run_kind=run_kind,
        record_status=RecordStatus.ERROR if error else RecordStatus.OK,
        formal_sample_index=truth.formal_sample_index,
        split=truth.split,
        scenario=truth.scenario,
        image_relpath=truth.image_relpath,
        image_sha256=truth.image_sha256,
        image_width=truth.image_width,
        image_height=truth.image_height,
        model_id=YOLO_MODEL_ID,
        runtime_provenance=RuntimeProvenance(
            runtime_device="cuda",
            runtime_name="test-runtime",
            runtime_version="1",
            weights_sha256="7" * 64,
            environment={"platform": "linux"},
        ),
        config_sha256=config_sha256,
        threshold_lock_sha256=_LOCK_SHA,
        raw_candidates=() if error else candidates,
        phase_timings=PhaseTimings(
            grounding_ms=None if error else 2.0,
            sam_ms=None,
            selector_ms=None if error else 1.0,
        ),
        raw_count=0 if error else len(candidates),
        decision=DecisionOutput.ERROR if error else decision,
        selected_candidate_id=None if error else selected,
        rejection_reason=None if error else rejection,
        error_type="INFERENCE_ERROR" if error else None,
        error_summary="fixture failure" if error else None,
        timed_out=error,
        oom=False,
        fallback_used=False,
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


def _extended_document(
    record: PredictionRecord,
    *,
    total_ms: float,
    platform: str = "linux",
    model: str = "yolo_seg",
    resource_samples: tuple[ResourceSample, ...] = (),
) -> dict[str, object]:
    phases = record.phase_timings
    required_phase_total = sum(
        value
        for value in (1.0, phases.grounding_ms, phases.sam_ms, phases.selector_ms)
        if value is not None
    )
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
            "grounding_ms": phases.grounding_ms,
            "sam_ms": phases.sam_ms,
            "selector_ms": phases.selector_ms,
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
        "platform": platform,
        "model": model,
        "device": record.runtime_provenance.runtime_device,
        "dtype": "float32",
        "source_commit": _SOURCE_COMMIT,
        "inventory_sha256": _INVENTORY_SHA,
        "collection_mode": "LOW_FLOOR",
        "max_gpu_temperature_celsius": None,
        "timing_breakdown": {
            "preprocess_ms": None if record.record_status is RecordStatus.ERROR else 1.0,
            "dino_or_yolo_ms": phases.grounding_ms,
            "sam_ms": phases.sam_ms,
            "postprocess_ms": (
                None
                if record.record_status is RecordStatus.ERROR
                else total_ms - required_phase_total
            ),
            "selector_ms": phases.selector_ms,
            "total_ms": total_ms,
        },
        "resource_samples": [
            {
                "process_rss_bytes": sample.process_rss_bytes,
                "process_cpu_percent": sample.process_cpu_percent,
                "gpu_memory_allocated_bytes": sample.gpu_memory_allocated_bytes,
                "gpu_memory_reserved_bytes": sample.gpu_memory_reserved_bytes,
                "gpu_utilization_percent": sample.gpu_utilization_percent,
                "gpu_temperature_celsius": sample.gpu_temperature_celsius,
                "gpu_power_watts": sample.gpu_power_watts,
                "unavailable_reasons": dict(sample.unavailable_reasons),
                "tool_versions": dict(sample.tool_versions),
            }
            for sample in resource_samples
        ],
        "irreversible_limits": {},
    }


def _fixture(tmp_path: Path) -> AggregationInput:
    truth_root = tmp_path / "truth"
    candidate_root = tmp_path / "candidate"
    one = [[1, 1, 0], [1, 1, 0], [0, 0, 0]]
    other = [[0, 0, 0], [0, 0, 0], [0, 1, 1]]
    truths = (
        _truth(truth_root, 0, "no_cup", ()),
        _truth(truth_root, 1, "one_cup", (one,)),
        _truth(truth_root, 2, "two_cups", (one, other)),
        _truth(truth_root, 3, "cup_near_bottle", (one,)),
    )
    candidates = (
        (),
        (_candidate(candidate_root, 1, 0, one),),
        (
            _candidate(candidate_root, 2, 0, one),
            _candidate(candidate_root, 2, 1, other, score=0.8),
        ),
        (_candidate(candidate_root, 3, 0, one),),
    )
    decisions = (
        DecisionOutput.NOT_FOUND,
        DecisionOutput.UNIQUE,
        DecisionOutput.AMBIGUOUS,
        DecisionOutput.UNIQUE,
    )
    raw_records = tuple(
        _record(
            truth,
            sample_candidates,
            run_kind=RunKind.TEST_RAW_FROZEN,
            config_sha256=_RAW_CONFIG_SHA,
            decision=decision,
        )
        for truth, sample_candidates, decision in zip(
            truths, candidates, decisions, strict=True
        )
    )
    formal_records = tuple(
        _record(
            truth,
            sample_candidates,
            run_kind=RunKind.TEST_PRODUCTION,
            config_sha256=_PRODUCTION_CONFIG_SHA,
            decision=decision,
            error=truth.formal_sample_index == 1,
        )
        for truth, sample_candidates, decision in zip(
            truths, candidates, decisions, strict=True
        )
    )
    raw_documents = tuple(
        _extended_document(record, total_ms=10.0 + position)
        for position, record in enumerate(raw_records)
    )
    formal_documents = tuple(
        _extended_document(record, total_ms=20.0 + position)
        for position, record in enumerate(formal_records)
    )
    return AggregationInput(
        formal=False,
        source_commit=_SOURCE_COMMIT,
        dataset_archive_sha256=_ARCHIVE_SHA,
        test_inventory_sha256=_INVENTORY_SHA,
        truth_evidence_root=truth_root,
        truth_samples=truths,
        raw_frozen_records={"linux": {"yolo_seg": raw_records}},
        formal_records={
            "linux": {"yolo_seg": {"production": formal_records}}
        },
        threshold_locks={},
        run_evidence={
            ("linux", "yolo_seg", "TEST_RAW_FROZEN"): RunAggregationEvidence(
                evidence_root=candidate_root,
                extended_record_documents=raw_documents,
                cold_latency_ms=(30.0, 31.0, 32.0),
                resource_samples=(),
            ),
            ("linux", "yolo_seg", "production"): RunAggregationEvidence(
                evidence_root=candidate_root,
                extended_record_documents=formal_documents,
                cold_latency_ms=(40.0, 41.0, 42.0),
                resource_samples=(),
            ),
        },
        oracle_records={},
        oracle_evidence={},
        bootstrap_seed=20260902,
        bootstrap_repetitions=50,
    )


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
    trace = reporting_module.ResourceTrace(
        sampling_frequency_hz=2.0,
        observations=(
            reporting_module.ResourceObservation(
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


def _empty_truths(root: Path, scenario_counts: dict[str, int]) -> tuple[TruthSample, ...]:
    root.mkdir(parents=True, exist_ok=True)
    truths: list[TruthSample] = []
    for scenario, count in scenario_counts.items():
        for _ in range(count):
            index = len(truths)
            truths.append(_truth(root, index, scenario, ()))
    return tuple(truths)


_FORMAL_SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
)
_FORMAL_WEIGHTS = {
    "yolo_seg": "a" * 64,
    "grounded_sam": "b" * 64,
}


def _formal_lock(model: str, val_inventory_sha256: str) -> ThresholdLock:
    platform_metrics = {
        platform: PlatformCalibrationMetrics(
            sample_count=200,
            error_count=0,
            macro_f1=1.0,
            mask_ap50_95=None,
            unsafe_unique_count=0,
            unsafe_unique_denominator=100,
            unsafe_unique_rate=0.0,
            two_cup_both_matched_recall=1.0,
        )
        for platform in ("macos", "linux")
    }
    selected = (
        YoloThresholds(
            conf=Decimal("0.25"),
            nms_iou=Decimal("0.70"),
            target_confidence_threshold=Decimal("0.50"),
        )
        if model == "yolo_seg"
        else GroundedSamBenchmarkThresholds(
            box_threshold=Decimal("0.30"),
            text_threshold=Decimal("0.25"),
            sam_quality=Decimal("0.50"),
            target_confidence_threshold=Decimal("0.50"),
        )
    )
    lock = ThresholdLock(
        schema_version=LOCK_SCHEMA_VERSION,
        model=model,
        grid_version=(
            "yolo-seg-grid/v1"
            if model == "yolo_seg"
            else "grounded-sam-grid/v1"
        ),
        objective_version=OBJECTIVE_VERSION,
        tie_break_version=TIE_BREAK_VERSION,
        val_inventory_sha256=val_inventory_sha256,
        mac_prediction_inventory_sha256=("c" if model == "yolo_seg" else "d")
        * 64,
        linux_prediction_inventory_sha256=("e" if model == "yolo_seg" else "f")
        * 64,
        formal=True,
        platform_sample_counts={"macos": 200, "linux": 200},
        selected=selected,
        outcome="SAFE_CALIBRATED",
        deployable=True,
        source_commit=_SOURCE_COMMIT,
        objective_metrics=ObjectiveCalibrationMetrics(
            min_platform_macro_f1=1.0,
            merged_macro_f1=1.0,
            merged_mask_ap50_95=None,
            min_platform_two_cup_recall=1.0,
        ),
        platform_metrics=platform_metrics,
        lock_sha256="0" * 64,
    )
    return lock.with_recomputed_sha256()


def _formal_truth_inventory(root: Path) -> tuple[TruthSample, ...]:
    left = _write_mask(root, "formal-left", [[1, 0], [0, 0]])
    right = _write_mask(root, "formal-right", [[0, 0], [0, 1]])
    truths: list[TruthSample] = []
    for scenario in _FORMAL_SCENARIOS:
        for _ in range(50):
            index = len(truths)
            instances: tuple[TruthInstance, ...]
            if scenario == "no_cup":
                instances = ()
            elif scenario == "two_cups":
                instances = (
                    TruthInstance(f"truth-{index}-left", "plastic_cup", left),
                    TruthInstance(f"truth-{index}-right", "plastic_cup", right),
                )
            else:
                instances = (
                    TruthInstance(f"truth-{index}-left", "plastic_cup", left),
                )
            truths.append(
                TruthSample(
                    formal_sample_index=index,
                    split="test",
                    scenario=scenario,
                    image_relpath=f"images/{index:03d}.png",
                    image_sha256=f"{index + 1000:064x}",
                    image_width=2,
                    image_height=2,
                    instances=instances,
                )
            )
    return tuple(truths)


def _formal_records(
    truths: tuple[TruthSample, ...],
    *,
    candidate_root: Path,
    platform: str,
    model: str,
    config: str,
    run_kind: RunKind,
    lock_sha256: str,
) -> tuple[PredictionRecord, ...]:
    config_sha256 = hashlib.sha256(f"{model}/{config}".encode()).hexdigest()
    left = _write_mask(candidate_root, "formal-left", [[1, 0], [0, 0]])
    right = _write_mask(candidate_root, "formal-right", [[0, 0], [0, 1]])
    provenance = RuntimeProvenance(
        runtime_device="mps" if platform == "macos" else "cuda",
        runtime_name="torch",
        runtime_version="2.8.0",
        weights_sha256=_FORMAL_WEIGHTS[model],
        environment={
            "dependency_lock": "benchmark-lock-v1",
            "platform": platform,
            "accelerator": "mps" if platform == "macos" else "cuda",
        },
    )
    records: list[PredictionRecord] = []
    for truth in truths:
        masks_and_boxes = (
            ()
            if truth.scenario == "no_cup"
            else (
                (
                    left,
                    (0.0, 0.0, 1.0, 1.0),
                    0.9,
                ),
                *(
                    ((right, (1.0, 1.0, 2.0, 2.0), 0.8),)
                    if truth.scenario == "two_cups"
                    else ()
                ),
            )
        )
        candidates = tuple(
            RawCandidate(
                candidate_id=(
                    f"candidate-{truth.formal_sample_index}-{position}"
                ),
                label="plastic_cup",
                bbox_xyxy=bbox,
                mask=mask,
                ranking_score=score,
                ranking_score_source=(
                    "class_confidence"
                    if model == "yolo_seg"
                    else "grounding_box_score"
                ),
                class_confidence=score if model == "yolo_seg" else None,
                grounding_box_score=(
                    score if model == "grounded_sam" else None
                ),
                grounding_text_score=(
                    score - 0.1 if model == "grounded_sam" else None
                ),
                sam_quality=0.95 if model == "grounded_sam" else None,
            )
            for position, (mask, bbox, score) in enumerate(masks_and_boxes)
        )
        if len(candidates) == 0:
            decision = DecisionOutput.NOT_FOUND
            rejection_reason = "TARGET_NOT_FOUND"
        elif len(candidates) == 1:
            decision = DecisionOutput.UNIQUE
            rejection_reason = None
        else:
            decision = DecisionOutput.AMBIGUOUS
            rejection_reason = "TARGET_AMBIGUOUS"
        records.append(
            PredictionRecord(
                run_id=f"{platform}-{model}-{config}",
                schema_version=SCHEMA_VERSION,
                run_kind=run_kind,
                record_status=RecordStatus.OK,
                formal_sample_index=truth.formal_sample_index,
                split=truth.split,
                scenario=truth.scenario,
                image_relpath=truth.image_relpath,
                image_sha256=truth.image_sha256,
                image_width=truth.image_width,
                image_height=truth.image_height,
                model_id=MODEL_ID_BY_NAME[model],
                runtime_provenance=provenance,
                config_sha256=config_sha256,
                threshold_lock_sha256=lock_sha256,
                raw_candidates=candidates,
                phase_timings=PhaseTimings(
                    grounding_ms=2.0,
                    sam_ms=3.0 if model == "grounded_sam" else None,
                    selector_ms=1.0,
                ),
                raw_count=len(candidates),
                decision=decision,
                selected_candidate_id=(
                    candidates[0].candidate_id
                    if decision is DecisionOutput.UNIQUE
                    else None
                ),
                rejection_reason=rejection_reason,
                error_type=None,
                error_summary=None,
                timed_out=False,
                oom=False,
                fallback_used=False,
            )
        )
    return tuple(records)


def _formal_resource_sample(offset: int) -> ResourceSample:
    return ResourceSample(
        process_rss_bytes=1_000 + offset,
        process_cpu_percent=10.0 + offset,
        gpu_memory_allocated_bytes=2_000 + offset,
        gpu_memory_reserved_bytes=3_000 + offset,
        gpu_utilization_percent=40.0 + offset,
        gpu_temperature_celsius=50.0 + offset,
        gpu_power_watts=60.0 + offset,
        unavailable_reasons={},
        tool_versions={"resource-probe": "1.0", "psutil": "7.0"},
    )


def _formal_run_evidence(
    root: Path,
    records: tuple[PredictionRecord, ...],
    *,
    platform: str,
    model: str,
    config: str,
) -> RunAggregationEvidence:
    root.mkdir(parents=True, exist_ok=True)
    samples = tuple(_formal_resource_sample(offset) for offset in range(3))
    observations = tuple(
        reporting_module.ResourceObservation(
            phase=phase,
            monotonic_ns=1_000_000_000 + position * 100_000_000,
            formal_sample_index=0 if phase == "inference" else None,
            sample=samples[position],
        )
        for position, phase in enumerate(("load", "warmup", "inference"))
    )
    trace = reporting_module.ResourceTrace(
        sampling_frequency_hz=10.0,
        observations=observations,
    )
    first = records[0].runtime_provenance
    cold_samples = tuple(
        reporting_module.ColdProcessSample(
            process_id=f"{platform}-{model}-{config}-cold-{position}",
            pid=10_000 + position,
            process_started_ns=2_000_000_000 + position * 1_000_000,
            latency_ms=30.0 + position,
            runtime_name=first.runtime_name,
            runtime_version=first.runtime_version,
            weights_sha256=first.weights_sha256,
            executable_sha256="9" * 64,
        )
        for position in range(3)
    )
    documents = tuple(
        _extended_document(
            record,
            total_ms=10.0,
            platform=platform,
            model=model,
            resource_samples=samples if position == 0 else (),
        )
        for position, record in enumerate(records)
    )
    return RunAggregationEvidence(
        evidence_root=root,
        extended_record_documents=documents,
        cold_process_samples=cold_samples,
        resource_trace=trace,
    )


def _positive_formal_input(tmp_path: Path) -> AggregationInput:
    truth_root = tmp_path / "truth"
    truths = _formal_truth_inventory(truth_root)
    val_inventory_sha256 = "8" * 64
    locks = {
        model: _formal_lock(model, val_inventory_sha256)
        for model in ("yolo_seg", "grounded_sam")
    }
    raw: dict[str, dict[str, tuple[PredictionRecord, ...]]] = {}
    formal: dict[
        str, dict[str, dict[str, tuple[PredictionRecord, ...]]]
    ] = {}
    evidence: dict[tuple[str, str, str], RunAggregationEvidence] = {}
    for platform in ("macos", "linux"):
        raw[platform] = {}
        formal[platform] = {}
        for model in ("yolo_seg", "grounded_sam"):
            lock_sha = locks[model].lock_sha256
            raw_root = (
                tmp_path / "candidates" / platform / model / "TEST_RAW_FROZEN"
            )
            production_root = (
                tmp_path / "candidates" / platform / model / "production"
            )
            calibrated_root = (
                tmp_path / "candidates" / platform / model / "calibrated"
            )
            raw_records = _formal_records(
                truths,
                candidate_root=raw_root,
                platform=platform,
                model=model,
                config="TEST_RAW_FROZEN",
                run_kind=RunKind.TEST_RAW_FROZEN,
                lock_sha256=lock_sha,
            )
            production_records = _formal_records(
                truths,
                candidate_root=production_root,
                platform=platform,
                model=model,
                config="production",
                run_kind=RunKind.TEST_PRODUCTION,
                lock_sha256=lock_sha,
            )
            calibrated_records = _formal_records(
                truths,
                candidate_root=calibrated_root,
                platform=platform,
                model=model,
                config="calibrated",
                run_kind=RunKind.TEST_CALIBRATED,
                lock_sha256=lock_sha,
            )
            raw[platform][model] = raw_records
            formal[platform][model] = {
                "production": production_records,
                "calibrated": calibrated_records,
            }
            for config, records in (
                ("TEST_RAW_FROZEN", raw_records),
                ("production", production_records),
                ("calibrated", calibrated_records),
            ):
                evidence[(platform, model, config)] = _formal_run_evidence(
                    tmp_path / "candidates" / platform / model / config,
                    records,
                    platform=platform,
                    model=model,
                    config=config,
                )
    return AggregationInput(
        formal=True,
        source_commit=_SOURCE_COMMIT,
        dataset_archive_sha256=_ARCHIVE_SHA,
        test_inventory_sha256=_INVENTORY_SHA,
        truth_evidence_root=truth_root,
        truth_samples=truths,
        raw_frozen_records=raw,
        formal_records=formal,
        threshold_locks=locks,
        run_evidence=evidence,
        oracle_records={},
        oracle_evidence={},
    )


def _replace_formal_model_with_empty_impostor_records(
    value: AggregationInput,
    *,
    model: str,
    impostor_model_id: str,
) -> AggregationInput:
    raw = {
        platform: dict(models)
        for platform, models in value.raw_frozen_records.items()
    }
    formal = {
        platform: {
            current_model: dict(configs)
            for current_model, configs in models.items()
        }
        for platform, models in value.formal_records.items()
    }
    evidence = dict(value.run_evidence)
    for platform in ("macos", "linux"):
        for config in ("TEST_RAW_FROZEN", "production", "calibrated"):
            records = (
                raw[platform][model]
                if config == "TEST_RAW_FROZEN"
                else formal[platform][model][config]
            )
            changed = tuple(
                replace(
                    record,
                    model_id=impostor_model_id,
                    raw_candidates=(),
                    raw_count=0,
                    decision=DecisionOutput.NOT_FOUND,
                    selected_candidate_id=None,
                    rejection_reason="TARGET_NOT_FOUND",
                )
                for record in records
            )
            if config == "TEST_RAW_FROZEN":
                raw[platform][model] = changed
            else:
                formal[platform][model][config] = changed
            key = (platform, model, config)
            old_evidence = evidence[key]
            resource_samples = tuple(
                observation.sample
                for observation in old_evidence.resource_trace.observations
            )
            evidence[key] = replace(
                old_evidence,
                extended_record_documents=tuple(
                    _extended_document(
                        record,
                        total_ms=10.0,
                        platform=platform,
                        model=model,
                        resource_samples=resource_samples if position == 0 else (),
                    )
                    for position, record in enumerate(changed)
                ),
            )
    return replace(
        value,
        raw_frozen_records=raw,
        formal_records=formal,
        run_evidence=evidence,
    )


@pytest.mark.parametrize(
    ("model", "impostor_model_id"),
    (
        ("yolo_seg", f"prefix-{YOLO_MODEL_ID}"),
        ("yolo_seg", f"{YOLO_MODEL_ID}-suffix"),
        ("grounded_sam", f"prefix-{GROUNDED_SAM_MODEL_ID}"),
        ("grounded_sam", f"{GROUNDED_SAM_MODEL_ID}-suffix"),
    ),
)
def test_formal_validation_rejects_empty_candidate_impostor_model_ids(
    tmp_path: Path,
    model: str,
    impostor_model_id: str,
) -> None:
    value = _replace_formal_model_with_empty_impostor_records(
        _positive_formal_input(tmp_path),
        model=model,
        impostor_model_id=impostor_model_id,
    )

    with pytest.raises(ValueError, match="canonical model identity"):
        reporting_module._validate_input(value)


def test_complete_positive_formal_matrix_aggregates_and_is_deployable(
    tmp_path: Path,
) -> None:
    aggregation_input = _positive_formal_input(tmp_path)
    cells = tuple(
        records
        for platform in ("macos", "linux")
        for model in ("yolo_seg", "grounded_sam")
        for records in (
            aggregation_input.raw_frozen_records[platform][model],
            aggregation_input.formal_records[platform][model]["production"],
            aggregation_input.formal_records[platform][model]["calibrated"],
        )
    )
    assert len(cells) == 12
    assert all(len(records) == 200 for records in cells)
    assert all(
        {
            scenario: sum(record.scenario == scenario for record in records)
            for scenario in _FORMAL_SCENARIOS
        }
        == {scenario: 50 for scenario in _FORMAL_SCENARIOS}
        for records in cells
    )
    assert aggregation_input.raw_frozen_records["linux"]["grounded_sam"][
        0
    ].model_id == "grounding-dino-tiny+sam2.1-hiera-tiny"

    summary = MetricsAggregator().aggregate(aggregation_input)

    assert summary.formal is True
    assert summary.deployable is True
    assert summary.qualification_status == "FORMAL_DEPLOYABLE"
    assert set(summary.raw_frozen_by_platform_model) == {"macos", "linux"}
    assert set(summary.raw_frozen_by_platform_model["linux"]) == {
        "yolo_seg",
        "grounded_sam",
    }
    assert summary.raw_frozen_by_platform_model["linux"][
        "grounded_sam"
    ].sample_count == 200
    for platform in ("macos", "linux"):
        for model in ("yolo_seg", "grounded_sam"):
            raw_summary = summary.raw_frozen_by_platform_model[platform][model]
            assert raw_summary.mask_ap50 == pytest.approx(1.0)
            assert raw_summary.mask_ap50_95 == pytest.approx(1.0)
            assert raw_summary.instance_metrics.precision == pytest.approx(1.0)
            assert raw_summary.instance_metrics.recall == pytest.approx(1.0)
            assert raw_summary.metric_details.f1 == pytest.approx(1.0)
            assert raw_summary.instance_metrics.mean_iou == pytest.approx(1.0)
            assert raw_summary.metric_details.median_iou == pytest.approx(1.0)
            assert raw_summary.instance_metrics.mean_dice == pytest.approx(1.0)
            assert raw_summary.metric_details.median_dice == pytest.approx(1.0)
            assert raw_summary.candidate_count_distribution == {
                "0": 0.25,
                "1": 0.5,
                "2": 0.25,
            }
            assert raw_summary.scenarios[
                "two_cups"
            ].safety_metrics.two_cup_both_matched_recall == pytest.approx(1.0)
            assert raw_summary.scenarios[
                "cup_near_bottle"
            ].safety_metrics.non_cup_leakage_ratio == pytest.approx(0.0)
            for config in ("production", "calibrated"):
                decision_metrics = summary.formal_by_platform_model_config[
                    platform
                ][model][config].decision_metrics
                assert decision_metrics.macro_f1 == pytest.approx(1.0)
                assert decision_metrics.unique_success_rate == pytest.approx(1.0)
                assert decision_metrics.unsafe_unique_rate == pytest.approx(0.0)
                assert decision_metrics.confusion["0"] == {
                    "NOT_FOUND": 50,
                    "UNIQUE": 0,
                    "AMBIGUOUS": 0,
                    "ERROR": 0,
                }
                assert decision_metrics.confusion["1"]["UNIQUE"] == 100
                assert decision_metrics.confusion["2+"]["AMBIGUOUS"] == 50
    assert set(
        summary.raw_frozen_by_platform_model["linux"]["grounded_sam"].scenarios
    ) == set(_FORMAL_SCENARIOS)
    assert len(summary.per_image) == 2 * 2 * 3 * 200
    assert len(
        {
            lock.val_inventory_sha256
            for lock in aggregation_input.threshold_locks.values()
        }
    ) == 1
    resource = summary.resource_summary[
        "linux/grounded_sam/TEST_RAW_FROZEN"
    ]
    assert set(resource.phase_summaries) == {"load", "warmup", "inference"}
    assert resource.peak_process_cpu_percent == 12.0
    assert resource.peak_gpu_utilization_percent == 42.0
    assert resource.peak_gpu_temperature_celsius == 52.0
    assert resource.peak_gpu_power_watts == 62.0
    assert resource.sampling_frequency_hz == 10.0
    assert resource.sampling_gaps_ms == (100.0, 100.0)
    assert resource.tool_versions == {
        "psutil": ("7.0",),
        "resource-probe": ("1.0",),
    }
    first_row = next(
        row
        for row in summary.per_image
        if row.platform == "linux"
        and row.model == "grounded_sam"
        and row.config == "TEST_RAW_FROZEN"
        and row.formal_sample_index == 0
    )
    assert tuple(item.phase for item in first_row.resource_observations) == (
        "load",
        "warmup",
        "inference",
    )
    comparison = summary.cross_platform["grounded_sam/TEST_RAW_FROZEN"]
    assert comparison.mismatch_count == 0
    assert comparison.items[0].runtime_device_pair_expected is True
    assert comparison.items[0].runtime_environment_equal is False
    assert comparison.items[0].runtime_environment_identity_equal is True
    candidate_comparison = next(
        item for item in comparison.items if item.formal_sample_index == 50
    )
    assert len(candidate_comparison.candidate_pairs) == 1
    assert candidate_comparison.candidate_pairs[0].mask_iou == pytest.approx(1.0)
    assert candidate_comparison.candidate_pairs[0].box_iou == pytest.approx(1.0)
    assert candidate_comparison.candidate_pairs[
        0
    ].grounding_box_score_absolute_delta == pytest.approx(0.0)
    candidate_row = next(
        row
        for row in summary.per_image
        if row.platform == "linux"
        and row.model == "grounded_sam"
        and row.config == "TEST_RAW_FROZEN"
        and row.formal_sample_index == 50
    )
    assert candidate_row.candidate_count == 1
    assert len(candidate_row.candidates) == 1
    assert candidate_row.candidates[0].grounding_box_score == pytest.approx(0.9)
    report_root = tmp_path / "formal-report"
    ReportWriter().write(summary, report_root)
    resources_document = json.loads(
        (report_root / "performance/resources.json").read_text()
    )
    resource_document = resources_document[
        "linux/grounded_sam/TEST_RAW_FROZEN"
    ]
    assert resource_document["peak_gpu_power_watts"] == 62.0
    assert set(resource_document["phase_summaries"]) == {
        "load",
        "warmup",
        "inference",
    }
    with (report_root / "metrics/per-image.csv").open(newline="") as handle:
        per_image_rows = tuple(csv.DictReader(handle))
    retained_row = next(
        row
        for row in per_image_rows
        if row["platform"] == "linux"
        and row["model"] == "grounded_sam"
        and row["config"] == "TEST_RAW_FROZEN"
        and row["formal_sample_index"] == "0"
    )
    retained_observations = json.loads(
        retained_row["resource_observations_json"]
    )
    assert [item["phase"] for item in retained_observations] == [
        "load",
        "warmup",
        "inference",
    ]
    assert retained_row["resource_sampling_frequency_hz"] == "10.0"
    assert json.loads(retained_row["resource_sampling_gaps_ms_json"]) == [
        100.0,
        100.0,
    ]
    candidate_csv_row = next(
        row
        for row in per_image_rows
        if row["platform"] == "linux"
        and row["model"] == "grounded_sam"
        and row["config"] == "TEST_RAW_FROZEN"
        and row["formal_sample_index"] == "50"
    )
    retained_candidates = json.loads(candidate_csv_row["candidates_json"])
    assert retained_candidates[0]["candidate_id"] == "candidate-50-0"
    assert retained_candidates[0]["grounding_box_score"] == pytest.approx(0.9)


def test_formal_candidate_mask_sha_tamper_fails_closed(tmp_path: Path) -> None:
    value = _positive_formal_input(tmp_path)
    key = ("linux", "grounded_sam", "TEST_RAW_FROZEN")
    evidence = value.run_evidence[key]
    candidate = value.raw_frozen_records["linux"]["grounded_sam"][
        50
    ].raw_candidates[0]
    mask_path = evidence.evidence_root / candidate.mask.relative_path
    mask_path.write_bytes(
        canonical_json_bytes(encode_mask_rle(np.zeros((2, 2), dtype=bool)))
    )

    with pytest.raises(ValueError, match="digest|SHA|mask"):
        MetricsAggregator().aggregate(value)


def test_runner_record_codec_feeds_canonical_grounded_record_to_aggregator(
    tmp_path: Path,
) -> None:
    from so101_demo.perception_benchmark.runner import _record_from_document

    full = _positive_formal_input(tmp_path)
    source_key = ("linux", "grounded_sam", "TEST_RAW_FROZEN")
    source_evidence = full.run_evidence[source_key]
    document = json.loads(
        canonical_json_bytes(
            reporting_module._plain(
                source_evidence.extended_record_documents[50]
            )
        )
    )
    record = _record_from_document(document)
    truth = full.truth_samples[50]
    assert record.model_id == GROUNDED_SAM_MODEL_ID
    assert record.raw_candidates[0].grounding_box_score == pytest.approx(0.9)

    evidence = RunAggregationEvidence(
        evidence_root=source_evidence.evidence_root,
        extended_record_documents=(
            _extended_document(
                record,
                total_ms=10.0,
                platform="linux",
                model="grounded_sam",
            ),
        ),
        cold_latency_ms=(30.0,),
        resource_samples=(),
    )
    value = AggregationInput(
        formal=False,
        source_commit=_SOURCE_COMMIT,
        dataset_archive_sha256=_ARCHIVE_SHA,
        test_inventory_sha256=_INVENTORY_SHA,
        truth_evidence_root=full.truth_evidence_root,
        truth_samples=(truth,),
        raw_frozen_records={"linux": {"grounded_sam": (record,)}},
        formal_records={},
        threshold_locks={},
        run_evidence={source_key: evidence},
        oracle_records={},
        oracle_evidence={},
        bootstrap_seed=20260902,
        bootstrap_repetitions=10,
    )

    summary = MetricsAggregator().aggregate(value)

    raw = summary.raw_frozen_by_platform_model["linux"]["grounded_sam"]
    assert raw.sample_count == 1
    assert raw.mask_ap50 == pytest.approx(1.0)
    assert raw.mask_ap50_95 == pytest.approx(1.0)
    assert summary.per_image[0].candidates == record.raw_candidates


def _replace_formal_cell(
    value: AggregationInput,
    *,
    platform: str,
    model: str,
    config: str,
    records: tuple[PredictionRecord, ...],
) -> AggregationInput:
    raw = {
        outer_platform: dict(models)
        for outer_platform, models in value.raw_frozen_records.items()
    }
    formal = {
        outer_platform: {
            outer_model: dict(configs)
            for outer_model, configs in models.items()
        }
        for outer_platform, models in value.formal_records.items()
    }
    if config == "TEST_RAW_FROZEN":
        raw[platform][model] = records
    else:
        formal[platform][model][config] = records

    key = (platform, model, config)
    old_evidence = value.run_evidence[key]
    resource_samples = tuple(
        observation.sample
        for observation in old_evidence.resource_trace.observations
    )
    provenance = records[0].runtime_provenance
    evidence = replace(
        old_evidence,
        extended_record_documents=tuple(
            _extended_document(
                record,
                total_ms=10.0,
                platform=platform,
                model=model,
                resource_samples=resource_samples if position == 0 else (),
            )
            for position, record in enumerate(records)
        ),
        cold_process_samples=tuple(
            replace(
                sample,
                runtime_name=provenance.runtime_name,
                runtime_version=provenance.runtime_version,
                weights_sha256=provenance.weights_sha256,
            )
            for sample in old_evidence.cold_process_samples
        ),
    )
    return replace(
        value,
        raw_frozen_records=raw,
        formal_records=formal,
        run_evidence={**value.run_evidence, key: evidence},
    )


@pytest.mark.parametrize(
    "mutation",
    ("model_id", "weights_sha256", "runtime_name", "runtime_version", "environment"),
)
def test_formal_rejects_model_or_runtime_drift_between_run_kinds(
    tmp_path: Path,
    mutation: str,
) -> None:
    value = _positive_formal_input(tmp_path)
    records = value.formal_records["linux"]["yolo_seg"]["calibrated"]
    changed: list[PredictionRecord] = []
    for record in records:
        if mutation == "model_id":
            changed.append(
                replace(
                    record,
                    model_id=GROUNDED_SAM_MODEL_ID,
                    raw_candidates=(),
                    raw_count=0,
                    decision=DecisionOutput.NOT_FOUND,
                    selected_candidate_id=None,
                    rejection_reason="TARGET_NOT_FOUND",
                )
            )
            continue
        provenance = record.runtime_provenance
        if mutation == "weights_sha256":
            provenance = replace(provenance, weights_sha256="e" * 64)
        elif mutation == "runtime_name":
            provenance = replace(provenance, runtime_name="onnxruntime")
        elif mutation == "runtime_version":
            provenance = replace(provenance, runtime_version="2.9.0")
        else:
            provenance = replace(
                provenance,
                environment={
                    **provenance.environment,
                    "dependency_lock": "benchmark-lock-drift",
                },
            )
        changed.append(replace(record, runtime_provenance=provenance))
    value = _replace_formal_cell(
        value,
        platform="linux",
        model="yolo_seg",
        config="calibrated",
        records=tuple(changed),
    )

    with pytest.raises(ValueError, match="frozen model/runtime identity"):
        MetricsAggregator().aggregate(value)


def test_formal_rejects_model_asset_drift_between_platforms(tmp_path: Path) -> None:
    value = _positive_formal_input(tmp_path)
    for config in ("TEST_RAW_FROZEN", "production", "calibrated"):
        records = (
            value.raw_frozen_records["linux"]["yolo_seg"]
            if config == "TEST_RAW_FROZEN"
            else value.formal_records["linux"]["yolo_seg"][config]
        )
        changed = tuple(
            replace(
                record,
                runtime_provenance=replace(
                    record.runtime_provenance,
                    weights_sha256="e" * 64,
                ),
            )
            for record in records
        )
        value = _replace_formal_cell(
            value,
            platform="linux",
            model="yolo_seg",
            config=config,
            records=changed,
        )

    with pytest.raises(ValueError, match="cross-platform model asset identity"):
        MetricsAggregator().aggregate(value)


def test_formal_rejects_threshold_locks_with_different_val_inventories(
    tmp_path: Path,
) -> None:
    value = _positive_formal_input(tmp_path)
    grounded_lock = replace(
        value.threshold_locks["grounded_sam"],
        val_inventory_sha256="7" * 64,
        lock_sha256="0" * 64,
    ).with_recomputed_sha256()

    with pytest.raises(ValueError, match="same validation inventory"):
        MetricsAggregator().aggregate(
            replace(
                value,
                threshold_locks={
                    **value.threshold_locks,
                    "grounded_sam": grounded_lock,
                },
            )
        )


def test_formal_rejects_duplicate_cold_process_identity(tmp_path: Path) -> None:
    value = _positive_formal_input(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    evidence = value.run_evidence[key]
    samples = list(evidence.cold_process_samples)
    samples[1] = replace(
        samples[1],
        process_id=samples[0].process_id,
        pid=samples[0].pid,
        process_started_ns=samples[0].process_started_ns,
    )

    with pytest.raises(ValueError, match="distinct fresh process"):
        MetricsAggregator().aggregate(
            replace(
                value,
                run_evidence={
                    **value.run_evidence,
                    key: replace(evidence, cold_process_samples=tuple(samples)),
                },
            )
        )


def test_formal_rejects_nonformal_cold_float_convenience(tmp_path: Path) -> None:
    value = _positive_formal_input(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    evidence = value.run_evidence[key]

    with pytest.raises(ValueError, match="unanchored fixture samples"):
        MetricsAggregator().aggregate(
            replace(
                value,
                run_evidence={
                    **value.run_evidence,
                    key: replace(
                        evidence,
                        cold_process_samples=(),
                        cold_latency_ms=(30.0, 31.0, 32.0),
                    ),
                },
            )
        )


def test_formal_rejects_missing_resource_phase(tmp_path: Path) -> None:
    value = _positive_formal_input(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    evidence = value.run_evidence[key]
    trace = replace(
        evidence.resource_trace,
        observations=tuple(
            observation
            for observation in evidence.resource_trace.observations
            if observation.phase != "warmup"
        ),
    )

    with pytest.raises(ValueError, match="load, warmup, and inference"):
        MetricsAggregator().aggregate(
            replace(
                value,
                run_evidence={
                    **value.run_evidence,
                    key: replace(evidence, resource_trace=trace),
                },
            )
        )


def test_formal_rejects_resource_rows_moved_to_the_wrong_record(
    tmp_path: Path,
) -> None:
    value = _positive_formal_input(tmp_path)
    key = ("linux", "yolo_seg", "TEST_RAW_FROZEN")
    evidence = value.run_evidence[key]
    documents = [dict(document) for document in evidence.extended_record_documents]
    first_resources = documents[0]["resource_samples"]
    documents[0]["resource_samples"] = ()
    documents[1]["resource_samples"] = first_resources

    with pytest.raises(ValueError, match="phase/image anchors"):
        MetricsAggregator().aggregate(
            replace(
                value,
                run_evidence={
                    **value.run_evidence,
                    key: replace(
                        evidence,
                        extended_record_documents=tuple(documents),
                    ),
                },
            )
        )


def _formal_shell(
    tmp_path: Path, truths: tuple[TruthSample, ...]
) -> AggregationInput:
    return AggregationInput(
        formal=True,
        source_commit=_SOURCE_COMMIT,
        dataset_archive_sha256=_ARCHIVE_SHA,
        test_inventory_sha256=_INVENTORY_SHA,
        truth_evidence_root=tmp_path / "truth",
        truth_samples=truths,
        raw_frozen_records={},
        formal_records={},
        threshold_locks={},
        run_evidence={},
        oracle_records={},
        oracle_evidence={},
    )


def test_formal_aggregation_rejects_small_fixture(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    with pytest.raises(ValueError, match="exactly 200 unique"):
        MetricsAggregator().aggregate(replace(fixture, formal=True))


def test_formal_aggregation_rejects_wrong_scenario_distribution(
    tmp_path: Path,
) -> None:
    truths = _empty_truths(
        tmp_path / "truth",
        {
            "no_cup": 51,
            "one_cup_distractors": 49,
            "two_cups": 50,
            "cup_near_bottle": 50,
        },
    )

    with pytest.raises(ValueError, match="50 samples per scenario"):
        MetricsAggregator().aggregate(_formal_shell(tmp_path, truths))


def test_formal_aggregation_rejects_missing_required_matrix_cell(
    tmp_path: Path,
) -> None:
    truths = _empty_truths(
        tmp_path / "truth",
        {
            "no_cup": 50,
            "one_cup_distractors": 50,
            "two_cups": 50,
            "cup_near_bottle": 50,
        },
    )

    with pytest.raises(ValueError, match="formal matrix"):
        MetricsAggregator().aggregate(_formal_shell(tmp_path, truths))


def _file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_report_writer_is_deterministic_and_indexes_payload_not_itself(
    tmp_path: Path,
) -> None:
    summary = MetricsAggregator().aggregate(_fixture(tmp_path / "fixture"))
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = ReportWriter().write(summary, first_root)
    second = ReportWriter().write(summary, second_root)

    expected_files = {
        "metrics/summary.json",
        "metrics/per-scenario.csv",
        "metrics/per-image.csv",
        "metrics/cross-platform-mismatches.csv",
        "performance/latency.json",
        "performance/resources.json",
        "report/benchmark.md",
        "evidence-index.json",
    }
    assert set(_file_digests(first_root)) == expected_files
    assert _file_digests(first_root) == _file_digests(second_root)
    assert first == second
    assert {entry.relative_path for entry in first.entries} == expected_files - {
        "evidence-index.json"
    }
    index_document = json.loads((first_root / "evidence-index.json").read_text())
    assert index_document["payload_index_semantics"] == (
        "payload files only; evidence-index.json is excluded to avoid self-reference"
    )
    report = (first_root / "report/benchmark.md").read_text()
    assert "TEST_RAW_FROZEN raw capability" in report
    assert "Production safety contract" in report
    assert "NON_FORMAL_INVALID_FOR_DEPLOYMENT" in report
    assert "ORACLE_DIAGNOSTIC" not in report


def test_report_writer_never_publishes_partial_root_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from so101_demo.perception_benchmark import reporting

    summary = MetricsAggregator().aggregate(_fixture(tmp_path / "fixture"))
    output_root = tmp_path / "report-output"
    original = reporting._atomic_write_bytes

    def fail_on_per_image(path: Path, payload: bytes) -> None:
        if path.name == "per-image.csv":
            raise OSError("injected write failure")
        original(path, payload)

    monkeypatch.setattr(reporting, "_atomic_write_bytes", fail_on_per_image)

    with pytest.raises(OSError, match="injected write failure"):
        ReportWriter().write(summary, output_root)

    assert not output_root.exists()


def _write_generic_evidence_index(
    root: Path,
    *,
    entries: tuple[dict[str, object], ...] | None = None,
    schema_version: str = "so101-perception-benchmark/evidence-index/v1",
    semantics: str = (
        "payload files only; evidence-index.json is excluded to avoid self-reference"
    ),
) -> None:
    if entries is None:
        payload = b'{"formal":false}\n'
        path = root / "records/000000.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entries = (
            {
                "relative_path": "records/000000.json",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    (root / "evidence-index.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": schema_version,
                "payload_index_semantics": semantics,
                "entries": list(entries),
            }
        )
    )


def test_public_evidence_index_loaders_verify_report_and_generic_dry_run_trees(
    tmp_path: Path,
) -> None:
    summary = MetricsAggregator().aggregate(_fixture(tmp_path / "fixture"))
    report_root = tmp_path / "report"
    written = ReportWriter().write(summary, report_root)

    loaded = load_evidence_index(report_root)

    assert loaded == written
    assert verify_evidence_index(report_root) == written
    assert isinstance(loaded, EvidenceIndex)
    assert all(isinstance(entry, EvidenceEntry) for entry in loaded.entries)

    dry_run_root = tmp_path / "dry-run"
    dry_run_root.mkdir()
    _write_generic_evidence_index(dry_run_root)
    generic = verify_evidence_index(dry_run_root)
    assert generic.entries == (
        EvidenceEntry(
            "records/000000.json",
            len(b'{"formal":false}\n'),
            hashlib.sha256(b'{"formal":false}\n').hexdigest(),
        ),
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "tamper",
        "extra-file",
        "path-traversal",
        "self-entry",
        "duplicate",
        "size",
        "sha",
        "schema",
        "semantics",
        "noncanonical-index",
        "symlink-file",
        "symlink-directory",
    ),
)
def test_public_evidence_index_loader_rejects_tree_or_index_relaxation(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    _write_generic_evidence_index(root)
    document = json.loads((root / "evidence-index.json").read_bytes())
    payload_path = root / "records/000000.json"
    if mutation == "tamper":
        payload_path.write_bytes(payload_path.read_bytes() + b"tamper")
    elif mutation == "extra-file":
        (root / "extra.txt").write_text("extra\n")
    elif mutation == "path-traversal":
        document["entries"][0]["relative_path"] = "../escape.json"
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "self-entry":
        document["entries"][0]["relative_path"] = "evidence-index.json"
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "duplicate":
        document["entries"].append(dict(document["entries"][0]))
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "size":
        document["entries"][0]["size_bytes"] += 1
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "sha":
        document["entries"][0]["sha256"] = "0" * 64
        _write_generic_evidence_index(root, entries=tuple(document["entries"]))
    elif mutation == "schema":
        _write_generic_evidence_index(root, schema_version="unknown")
    elif mutation == "semantics":
        _write_generic_evidence_index(root, semantics="self is included")
    elif mutation == "noncanonical-index":
        (root / "evidence-index.json").write_text(
            json.dumps(document, indent=2), encoding="utf-8"
        )
    elif mutation == "symlink-file":
        outside = tmp_path / "outside.json"
        outside.write_bytes(payload_path.read_bytes())
        payload_path.unlink()
        payload_path.symlink_to(outside)
    else:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "000000.json").write_bytes(payload_path.read_bytes())
        payload_path.unlink()
        (root / "records").rmdir()
        (root / "records").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError):
        load_evidence_index(root)
