"""The evidence index verification, the CSV and Markdown rows and the report writer."""

from __future__ import annotations

import csv
from dataclasses import fields, is_dataclass
from enum import Enum
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    sha256_bytes,
)
from so101_demo.perception_benchmark.dataset.pinned_files import _PinnedDirectory, _PinnedFileError
from so101_demo.perception_benchmark.reporting.records import (
    _INDEX_SCHEMA_VERSION,
    _INDEX_SEMANTICS,
    _PAYLOAD_PATHS,
    BenchmarkSummary,
    EvidenceEntry,
    EvidenceIndex,
    ScenarioMetricSummary,
)


def verify_evidence_index(output_root: Path) -> EvidenceIndex:
    """Verify canonical index bytes and the exact indexed payload tree."""

    try:
        pinned_root = _PinnedDirectory.open(Path(output_root))
    except _PinnedFileError as error:
        raise ValueError(
            "output_root must be an existing non-symlink directory"
        ) from error
    with pinned_root:
        try:
            payload = pinned_root.read_file("evidence-index.json")
        except _PinnedFileError as error:
            raise ValueError(
                "evidence index must be a regular in-root file without hardlinks"
            ) from error
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("evidence index document is invalid") from error
        if not isinstance(document, Mapping) or set(document) != {
            "schema_version",
            "payload_index_semantics",
            "entries",
        }:
            raise ValueError("evidence index document has an invalid schema")
        raw_entries = document.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("evidence index entries must be a list")
        entries: list[EvidenceEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, Mapping) or set(raw) != {
                "relative_path",
                "size_bytes",
                "sha256",
            }:
                raise ValueError("evidence index entry has an invalid schema")
            entries.append(
                EvidenceEntry(
                    relative_path=raw["relative_path"],
                    size_bytes=raw["size_bytes"],
                    sha256=raw["sha256"],
                )
            )
        index = EvidenceIndex(
            schema_version=document["schema_version"],
            payload_index_semantics=document["payload_index_semantics"],
            entries=tuple(entries),
        )
        try:
            canonical = canonical_json_bytes(_jsonable(index))
        except (TypeError, ValueError) as error:
            raise ValueError("evidence index document is not canonical") from error
        if canonical != payload:
            raise ValueError("evidence index document is not canonical")
        indexed_paths = {entry.relative_path for entry in index.entries}
        expected_files = indexed_paths | {"evidence-index.json"}
        expected_directories = {
            parent.as_posix()
            for path in indexed_paths
            for parent in PurePosixPath(path).parents
            if parent.as_posix() != "."
        }
        try:
            actual_files, actual_directories = pinned_root.tree()
        except _PinnedFileError as error:
            raise ValueError(
                "evidence tree cannot contain symlinks, hardlinks, or special entries"
            ) from error
        if (
            actual_files != expected_files
            or actual_directories != expected_directories
        ):
            raise ValueError("evidence tree does not exactly match its index")
        for entry in index.entries:
            try:
                item_payload = pinned_root.read_file(entry.relative_path)
            except _PinnedFileError as error:
                raise ValueError(
                    "evidence payload must be a regular in-root file without hardlinks"
                ) from error
            if (
                len(item_payload) != entry.size_bytes
                or sha256_bytes(item_payload) != entry.sha256
            ):
                raise ValueError("evidence payload size or SHA256 mismatch")
        return index


def load_evidence_index(output_root: Path) -> EvidenceIndex:
    """Load one immutable evidence index only after full tree verification."""

    return verify_evidence_index(output_root)


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
            tempfile.mkdtemp(dir=parent, prefix=f".{target.name}.staging-")
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
                schema_version=_INDEX_SCHEMA_VERSION,
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
