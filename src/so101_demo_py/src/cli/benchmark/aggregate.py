"""The aggregate and evidence verification subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from so101_demo.cli.benchmark.calibrate import _expectation
from so101_demo.cli.benchmark.common import (
    _CONFIG_SHA256,
    _MODELS,
    _SHA256,
    BenchmarkError,
    _bind_dataset_sha,
    _frozen_asset_sha,
    _frozen_model_id,
    _load_frozen_config,
    _mapping,
    _preflight_output_root,
    _read_json,
    _sha,
    _source_commit,
)
from so101_demo.perception_benchmark.calibration.lock_io import verify_threshold_lock
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RunKind,
)
from so101_demo.perception_benchmark.dataset.contracts import sha256_file
from so101_demo.perception_benchmark.dataset.loading import (
    load_dataset_inventory,
    load_truth_samples,
)
from so101_demo.perception_benchmark.reporting.aggregator import MetricsAggregator
from so101_demo.perception_benchmark.reporting.records import (
    AggregationInput,
    ColdProcessSample,
    ResourceObservation,
    ResourceTrace,
    RunAggregationEvidence,
)
from so101_demo.perception_benchmark.reporting.writer import (
    load_evidence_index,
    ReportWriter,
    verify_evidence_index,
)
from so101_demo.perception_benchmark.runner.resume import load_verified_run_evidence
from so101_demo.perception_benchmark.timing import ResourceSample


def _resource_sample(document: Mapping[str, Any]) -> ResourceSample:
    if set(document) != {
        "process_rss_bytes",
        "process_cpu_percent",
        "gpu_memory_allocated_bytes",
        "gpu_memory_reserved_bytes",
        "gpu_utilization_percent",
        "gpu_temperature_celsius",
        "gpu_power_watts",
        "unavailable_reasons",
        "tool_versions",
    } or not all(
        isinstance(document[name], Mapping) for name in ("unavailable_reasons", "tool_versions")
    ):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    return ResourceSample(**document)


def _parse_aggregation_resources(
    document: Mapping[str, Any],
) -> tuple[tuple[ColdProcessSample, ...], ResourceTrace | None]:
    raw_cold = document.get("cold_process_samples", [])
    raw_trace = document.get("resource_trace")
    if not isinstance(raw_cold, list):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    try:
        cold = tuple(
            ColdProcessSample(**_mapping(item, "AGGREGATION_PLAN_INVALID")) for item in raw_cold
        )
        trace = None
        if raw_trace is not None:
            trace_document = _mapping(raw_trace, "AGGREGATION_PLAN_INVALID")
            if set(trace_document) != {"sampling_frequency_hz", "observations"} or not isinstance(
                trace_document["observations"], list
            ):
                raise BenchmarkError("AGGREGATION_PLAN_INVALID")
            observations = []
            for value in trace_document["observations"]:
                item = _mapping(value, "AGGREGATION_PLAN_INVALID")
                if set(item) != {
                    "phase",
                    "monotonic_ns",
                    "formal_sample_index",
                    "sample",
                }:
                    raise BenchmarkError("AGGREGATION_PLAN_INVALID")
                observations.append(
                    ResourceObservation(
                        phase=item["phase"],
                        monotonic_ns=item["monotonic_ns"],
                        formal_sample_index=item["formal_sample_index"],
                        sample=_resource_sample(
                            _mapping(item["sample"], "AGGREGATION_PLAN_INVALID")
                        ),
                    )
                )
            trace = ResourceTrace(trace_document["sampling_frequency_hz"], tuple(observations))
    except (TypeError, ValueError) as error:
        raise BenchmarkError("AGGREGATION_PLAN_INVALID") from error
    return cold, trace


def _aggregation_evidence(document: Mapping[str, Any], loaded) -> RunAggregationEvidence:
    cold, trace = _parse_aggregation_resources(document)
    return RunAggregationEvidence(
        evidence_root=loaded.evidence_root,
        extended_record_documents=loaded.extended_record_documents,
        cold_process_samples=cold,
        resource_trace=trace,
    )


def _absolute_path_field(document: Mapping[str, Any], name: str) -> Path:
    value = document.get(name)
    if not isinstance(value, str) or not value:
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    path = Path(value)
    if not path.is_absolute():
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    return path


def _validated_aggregation_plan(
    document: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], list[Mapping[str, Any]], str]:
    if (
        set(document)
        != {
            "schema_version",
            "dataset",
            "threshold_locks",
            "runs",
            "source_commit",
        }
        or document.get("schema_version") != "so101-perception-benchmark/aggregation-plan-v1"
    ):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    dataset = _mapping(document.get("dataset"), "AGGREGATION_PLAN_INVALID")
    locks = _mapping(document.get("threshold_locks"), "AGGREGATION_PLAN_INVALID")
    raw_runs = document.get("runs")
    if set(dataset) != {
        "root",
        "archive_sha256",
        "inventory_sha256",
        "test_access_event_sha256",
        "sealed_member_inventory_sha256",
        "threshold_lock_sha256s",
    } or set(locks) != set(_MODELS):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    _absolute_path_field(dataset, "root")
    for name in (
        "archive_sha256",
        "inventory_sha256",
        "test_access_event_sha256",
        "sealed_member_inventory_sha256",
    ):
        _sha(dataset.get(name), "AGGREGATION_PLAN_INVALID")
    lock_shas = dataset.get("threshold_lock_sha256s")
    if (
        not isinstance(lock_shas, list)
        or len(lock_shas) != 2
        or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in lock_shas
        )
    ):
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    for model in _MODELS:
        anchor = _mapping(locks.get(model), "AGGREGATION_PLAN_INVALID")
        if set(anchor) != {"path", "sha256"}:
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _absolute_path_field(anchor, "path")
        _sha(anchor.get("sha256"), "AGGREGATION_PLAN_INVALID")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise BenchmarkError("AGGREGATION_PLAN_INVALID")
    runs: list[Mapping[str, Any]] = []
    required = {
        "platform",
        "model",
        "config",
        "run_root",
        "expectation",
        "expectation_sha256",
    }
    optional = {"cold_process_samples", "resource_trace"}
    for value in raw_runs:
        item = _mapping(value, "AGGREGATION_PLAN_INVALID")
        if not required.issubset(item) or not set(item).issubset(required | optional):
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _absolute_path_field(item, "run_root")
        _absolute_path_field(item, "expectation")
        _sha(item.get("expectation_sha256"), "AGGREGATION_PLAN_INVALID")
        if (
            not isinstance(item.get("platform"), str)
            or item["platform"] not in {"macos", "linux"}
            or not isinstance(item.get("model"), str)
            or item["model"] not in set(_MODELS)
            or not isinstance(item.get("config"), str)
            or item["config"]
            not in {
                "TEST_RAW_FROZEN",
                "production",
                "calibrated",
                "characterization",
                "ORACLE_DIAGNOSTIC",
            }
        ):
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _parse_aggregation_resources(item)
        runs.append(item)
    return dataset, locks, runs, _source_commit(document.get("source_commit"))


def _validate_aggregate_run_provenance(
    loaded: object,
    *,
    platform_name: str,
    model: str,
    config_name: str,
    source_commit: str,
    config: Mapping[str, Any],
) -> None:
    kinds = {
        "TEST_RAW_FROZEN": RunKind.TEST_RAW_FROZEN,
        "production": RunKind.TEST_PRODUCTION,
        "calibrated": RunKind.TEST_CALIBRATED,
        "characterization": RunKind.TEST_CHARACTERIZATION,
        "ORACLE_DIAGNOSTIC": RunKind.ORACLE_DIAGNOSTIC,
    }
    expected = {
        "platform": platform_name,
        "model": model,
        "device": "mps" if platform_name == "macos" else "cuda",
        "dtype": "float32",
        "run_kind": kinds[config_name],
        "source_commit": source_commit,
        "config_sha256": _CONFIG_SHA256,
        "model_id": _frozen_model_id(config, model),
        "weights_sha256": _frozen_asset_sha(config, model),
    }
    manifest = getattr(loaded, "manifest", None)
    if manifest is None or any(
        getattr(manifest, name, None) != expected_value for name, expected_value in expected.items()
    ):
        raise BenchmarkError("RUN_PROVENANCE_MISMATCH")


def _handle_aggregate(arguments: argparse.Namespace) -> int:
    config_document = _load_frozen_config(arguments.config)
    _preflight_output_root(arguments.output_root)
    plan = _read_json(
        arguments.aggregation_plan, "AGGREGATION_PLAN_INVALID", arguments.aggregation_plan_sha256
    )
    dataset, locks_document, runs, source_commit = _validated_aggregation_plan(plan)
    _bind_dataset_sha(dataset["archive_sha256"], config_document)
    threshold_locks = {}
    for model in _MODELS:
        lock_anchor = locks_document.get(model)
        if not isinstance(lock_anchor, Mapping) or set(lock_anchor) != {"path", "sha256"}:
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        lock_path = _absolute_path_field(lock_anchor, "path")
        expected_lock_sha = _sha(lock_anchor["sha256"], "AGGREGATION_PLAN_INVALID")
        lock = verify_threshold_lock(lock_path)
        if (
            lock.lock_sha256 != expected_lock_sha
            or lock.model != model
            or lock.source_commit != source_commit
        ):
            raise BenchmarkError("THRESHOLD_LOCK_MISMATCH")
        threshold_locks[model] = lock
    inventory = load_dataset_inventory(
        _absolute_path_field(dataset, "root"),
        expected_split="test",
        expected_archive_sha256=dataset["archive_sha256"],
        expected_inventory_sha256=dataset["inventory_sha256"],
        expected_test_access_event_sha256=dataset["test_access_event_sha256"],
        expected_sealed_member_inventory_sha256=dataset["sealed_member_inventory_sha256"],
        expected_threshold_lock_sha256s=tuple(dataset["threshold_lock_sha256s"]),
    )
    truths = load_truth_samples(inventory.dataset_root, "test", inventory)
    raw: dict[str, dict[str, tuple[PredictionRecord, ...]]] = {}
    formal: dict[str, dict[str, dict[str, tuple[PredictionRecord, ...]]]] = {}
    oracle: dict[str, dict[str, tuple[PredictionRecord, ...]]] = {}
    evidence: dict[tuple[str, str, str], RunAggregationEvidence] = {}
    oracle_evidence: dict[tuple[str, str, str], RunAggregationEvidence] = {}
    for item in runs:
        expectation = _expectation(
            _absolute_path_field(item, "expectation"), item["expectation_sha256"]
        )
        loaded = load_verified_run_evidence(
            _absolute_path_field(item, "run_root"), inventory, expectation
        )
        platform, model, config_name = item["platform"], item["model"], item["config"]
        if (
            platform not in {"macos", "linux"}
            or model not in set(_MODELS)
            or config_name
            not in {
                "TEST_RAW_FROZEN",
                "production",
                "calibrated",
                "characterization",
                "ORACLE_DIAGNOSTIC",
            }
        ):
            raise BenchmarkError("AGGREGATION_PLAN_INVALID")
        _validate_aggregate_run_provenance(
            loaded,
            platform_name=platform,
            model=model,
            config_name=config_name,
            source_commit=source_commit,
            config=config_document,
        )
        run_evidence = _aggregation_evidence(item, loaded)
        if config_name == "TEST_RAW_FROZEN":
            raw.setdefault(platform, {})[model] = loaded.records
            evidence[(platform, model, config_name)] = run_evidence
        elif config_name == "ORACLE_DIAGNOSTIC":
            oracle.setdefault(platform, {})[model] = loaded.records
            oracle_evidence[(platform, model, config_name)] = run_evidence
        else:
            formal.setdefault(platform, {}).setdefault(model, {})[config_name] = loaded.records
            evidence[(platform, model, config_name)] = run_evidence
    value = AggregationInput(
        formal=True,
        source_commit=source_commit,
        dataset_archive_sha256=inventory.archive_sha256,
        test_inventory_sha256=inventory.inventory_sha256,
        truth_evidence_root=inventory.dataset_root,
        truth_samples=truths,
        raw_frozen_records=raw,
        formal_records=formal,
        threshold_locks=threshold_locks,
        run_evidence=evidence,
        oracle_records=oracle,
        oracle_evidence=oracle_evidence,
        bootstrap_seed=arguments.bootstrap_seed,
        bootstrap_repetitions=arguments.bootstrap_repetitions,
    )
    summary = MetricsAggregator().aggregate(value)
    ReportWriter().write(summary, arguments.output_root)
    verify_evidence_index(arguments.output_root)
    print(arguments.output_root / "evidence-index.json")
    return 0


def _handle_verify_evidence(arguments: argparse.Namespace) -> int:
    index = load_evidence_index(arguments.output_root)
    if arguments.print_inventory_sha:
        print(sha256_file(arguments.output_root / "evidence-index.json"))
    else:
        print(f"VERIFIED {len(index.entries)}")
    return 0
