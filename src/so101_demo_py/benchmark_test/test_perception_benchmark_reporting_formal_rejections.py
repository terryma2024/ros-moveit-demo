"""Formal validation refusals: drift, locks, cold processes and resource phases."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from perception_benchmark_reporting_support import (
    _ARCHIVE_SHA,
    _INVENTORY_SHA,
    _SOURCE_COMMIT,
    _extended_document,
    _fixture,
    _positive_formal_input,
    _truth,
)
import pytest

from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    DecisionOutput,
    PredictionRecord,
    TruthSample,
)
from so101_demo.perception_benchmark.reporting.aggregator import MetricsAggregator
from so101_demo.perception_benchmark.reporting.records import (
    AggregationInput,
)


def _empty_truths(root: Path, scenario_counts: dict[str, int]) -> tuple[TruthSample, ...]:
    root.mkdir(parents=True, exist_ok=True)
    truths: list[TruthSample] = []
    for scenario, count in scenario_counts.items():
        for _ in range(count):
            index = len(truths)
            truths.append(_truth(root, index, scenario, ()))
    return tuple(truths)


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
