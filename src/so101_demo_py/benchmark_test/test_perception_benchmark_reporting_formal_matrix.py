"""The complete formal matrix and the runner record codec."""

from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
from perception_benchmark_reporting_support import (
    _ARCHIVE_SHA,
    _FORMAL_SCENARIOS,
    _INVENTORY_SHA,
    _SOURCE_COMMIT,
    _extended_document,
    _positive_formal_input,
)
import pytest

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    DecisionOutput,
)
from so101_demo.perception_benchmark.reporting import evidence as reporting_module_evidence
from so101_demo.perception_benchmark.reporting import records as reporting_module_records
from so101_demo.perception_benchmark.reporting.aggregator import MetricsAggregator
from so101_demo.perception_benchmark.reporting.records import (
    AggregationInput,
    RunAggregationEvidence,
)
from so101_demo.perception_benchmark.reporting.writer import (
    ReportWriter,
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
        reporting_module_evidence._validate_input(value)


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
    from so101_demo.perception_benchmark.runner.records import _record_from_document

    full = _positive_formal_input(tmp_path)
    source_key = ("linux", "grounded_sam", "TEST_RAW_FROZEN")
    source_evidence = full.run_evidence[source_key]
    document = json.loads(
        canonical_json_bytes(
            reporting_module_records._plain(
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
