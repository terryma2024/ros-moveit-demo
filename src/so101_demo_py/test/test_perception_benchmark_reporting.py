from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    SCHEMA_VERSION,
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
    MetricsAggregator,
    ReportWriter,
    RunAggregationEvidence,
)


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
        model_id="yolo_seg",
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
        "device": "cuda",
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
        "resource_samples": [],
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
        records[1] = replace(records[1], model_id="yolo_seg_other")
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

    with pytest.raises(ValueError, match="homogeneous runtime/model signature"):
        MetricsAggregator().aggregate(aggregation_input)


def _empty_truths(root: Path, scenario_counts: dict[str, int]) -> tuple[TruthSample, ...]:
    root.mkdir(parents=True, exist_ok=True)
    truths: list[TruthSample] = []
    for scenario, count in scenario_counts.items():
        for _ in range(count):
            index = len(truths)
            truths.append(_truth(root, index, scenario, ()))
    return tuple(truths)


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
        {"no_cup": 51, "one_cup": 49, "two_cups": 50, "cup_near_bottle": 50},
    )

    with pytest.raises(ValueError, match="50 samples per scenario"):
        MetricsAggregator().aggregate(_formal_shell(tmp_path, truths))


def test_formal_aggregation_rejects_missing_required_matrix_cell(
    tmp_path: Path,
) -> None:
    truths = _empty_truths(
        tmp_path / "truth",
        {"no_cup": 50, "one_cup": 50, "two_cups": 50, "cup_near_bottle": 50},
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
