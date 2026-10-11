"""Report fixtures and helpers shared by the benchmark reporting tests."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path

import numpy as np

from so101_demo.perception_benchmark.calibration.contracts import (
    LOCK_SCHEMA_VERSION,
    OBJECTIVE_VERSION,
    TIE_BREAK_VERSION,
)
from so101_demo.perception_benchmark.calibration.results import (
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    GroundedSamBenchmarkThresholds,
    YoloThresholds,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
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
from so101_demo.perception_benchmark.reporting import records as reporting_module_records
from so101_demo.perception_benchmark.reporting.records import (
    AggregationInput,
    RunAggregationEvidence,
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
        reporting_module_records.ResourceObservation(
            phase=phase,
            monotonic_ns=1_000_000_000 + position * 100_000_000,
            formal_sample_index=0 if phase == "inference" else None,
            sample=samples[position],
        )
        for position, phase in enumerate(("load", "warmup", "inference"))
    )
    trace = reporting_module_records.ResourceTrace(
        sampling_frequency_hz=10.0,
        observations=observations,
    )
    first = records[0].runtime_provenance
    cold_samples = tuple(
        reporting_module_records.ColdProcessSample(
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
