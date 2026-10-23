"""Read and validate the run evidence, the formal matrix and the report inputs."""

from __future__ import annotations

import math
from pathlib import Path, PurePosixPath
import stat
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from so101_demo.perception_benchmark.calibration.results import ThresholdLock
from so101_demo.perception_benchmark.contracts import (
    MODEL_ID_BY_NAME,
    DecisionOutput,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    TruthSample,
)
from so101_demo.perception_benchmark.matching import (
    MaskMatch,
    maximize_mask_iou_assignment,
)
from so101_demo.perception_benchmark.metrics import (
    ImageMetricInput,
)
from so101_demo.perception_benchmark.reporting.records import (
    _FORMAL_MODELS,
    _FORMAL_PLATFORMS,
    _SCENARIOS,
    _TIMING_FIELDS,
    AggregationInput,
    RunAggregationEvidence,
    _existing_root,
    _optional_finite_nonnegative,
    _plain,
    _require_sha,
    _require_source_commit,
)
from so101_demo.perception_benchmark.timing import ResourceSample


def _read_stable_regular_file(root: Path, relative_path: str) -> bytes:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or not resolved.is_relative_to(root)
        ):
            raise ValueError("evidence payload must be a regular in-root file")
        payload = path.read_bytes()
        after = path.lstat()
    except (OSError, RuntimeError) as error:
        raise ValueError("evidence payload cannot be read") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("evidence payload changed during verification")
    return payload


def _evidence_tree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()

    def visit(directory: Path) -> None:
        try:
            entries = tuple(directory.iterdir())
        except OSError as error:
            raise ValueError("evidence tree cannot be enumerated") from error
        for path in entries:
            relative = path.relative_to(root).as_posix()
            try:
                metadata = path.lstat()
            except OSError as error:
                raise ValueError("evidence tree cannot be inspected") from error
            if path.is_symlink():
                raise ValueError("evidence tree cannot contain symlinks")
            if stat.S_ISDIR(metadata.st_mode):
                directories.add(relative)
                visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                files.add(relative)
            else:
                raise ValueError("evidence tree entries must be regular")

    visit(root)
    return files, directories


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
