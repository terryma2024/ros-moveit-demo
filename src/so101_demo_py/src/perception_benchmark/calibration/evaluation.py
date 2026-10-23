"""Input validation, record precompute, grid evaluation and the joint platform calibration."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal
import math
from pathlib import Path
import time
from types import MappingProxyType
from typing import Literal

from so101_demo.perception_benchmark.calibration.contracts import (
    _AP_THRESHOLDS,
    _GRID_VERSIONS,
    LOCK_SCHEMA_VERSION,
    OBJECTIVE_VERSION,
    TIE_BREAK_VERSION,
    CalibrationError,
    ModelName,
    ProgressCallback,
    _deduplicate_boxes,
    _emit_progress,
)
from so101_demo.perception_benchmark.calibration.results import (
    CalibrationResult,
    PlatformCalibrationMetrics,
    ThresholdLock,
    _candidate_model_matches,
    _identity,
    _objective_metrics,
    _validate_record,
    _validate_truth,
    _validated_sha,
    _validated_source_commit,
    select_calibration_result,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    _GROUNDING_PREFIX_GRID,
    GroundedSamBenchmarkThresholds,
    YoloThresholds,
    decimal_range,
    enumerate_grounded_sam_grid,
    enumerate_yolo_grid,
)
from so101_demo.perception_benchmark.codec import (
    read_mask,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.decisions import (
    DecisionMetrics,
    aggregate_decisions,
    aggregate_scenarios,
)
from so101_demo.perception_benchmark.matching import (
    mask_iou,
    maximize_mask_iou_assignment,
)
from so101_demo.perception_benchmark.metrics import ImageMetricInput, compute_ap


def _validate_inputs(
    model: object,
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    inventory_sha: object,
    evidence_root: Path,
    mac_prediction_inventory_sha256: object,
    linux_prediction_inventory_sha256: object,
    source_commit: object,
    fixture_mode: object,
) -> tuple[
    ModelName,
    tuple[PredictionRecord, ...],
    tuple[PredictionRecord, ...],
    tuple[TruthSample, ...],
    Path,
    str,
    str,
    str,
    str,
]:
    if model not in ("yolo_seg", "grounded_sam"):
        raise CalibrationError("CALIBRATION_MODEL_INVALID")
    normalized_model: ModelName = model
    val_inventory_sha = _validated_sha(inventory_sha)
    mac_inventory_sha = _validated_sha(mac_prediction_inventory_sha256)
    linux_inventory_sha = _validated_sha(linux_prediction_inventory_sha256)
    commit = _validated_source_commit(source_commit)
    if not isinstance(fixture_mode, bool):
        raise CalibrationError("CALIBRATION_FIXTURE_MODE_INVALID")
    try:
        root = Path(evidence_root).resolve(strict=True)
    except (OSError, TypeError, RuntimeError) as error:
        raise CalibrationError("CALIBRATION_EVIDENCE_ROOT_INVALID") from error
    if not root.is_dir():
        raise CalibrationError("CALIBRATION_EVIDENCE_ROOT_INVALID")

    mac = tuple(_validate_record(record) for record in mac_records)
    linux = tuple(_validate_record(record) for record in linux_records)
    truth_items = tuple(_validate_truth(truth) for truth in truths)
    if not mac or not linux or not truth_items:
        raise CalibrationError("CALIBRATION_INVENTORY_EMPTY")
    if any(item.split != "val" for item in (*mac, *linux, *truth_items)):
        raise CalibrationError("CALIBRATION_VAL_ONLY")
    if any(
        record.run_kind is not RunKind.VAL_RAW or record.threshold_lock_sha256 is not None
        for record in (*mac, *linux)
    ):
        raise CalibrationError("CALIBRATION_VAL_ONLY")
    if any(record.record_status is RecordStatus.ERROR for record in (*mac, *linux)):
        raise CalibrationError("CALIBRATION_ERROR_RECORD_FORBIDDEN")
    if any(not _candidate_model_matches(record, normalized_model) for record in (*mac, *linux)):
        raise CalibrationError("CALIBRATION_MODEL_MISMATCH")

    mac_identities = tuple(_identity(record) for record in mac)
    linux_identities = tuple(_identity(record) for record in linux)
    truth_identities = tuple(_identity(truth) for truth in truth_items)
    for identities in (mac_identities, linux_identities, truth_identities):
        if len(identities) != len(set(identities)):
            raise CalibrationError("CALIBRATION_INVENTORY_IDENTITY_DUPLICATE")
        if len({identity[1] for identity in identities}) != len(identities):
            raise CalibrationError("CALIBRATION_INVENTORY_IDENTITY_DUPLICATE")
    if set(mac_identities) != set(linux_identities):
        raise CalibrationError("PLATFORM_INVENTORY_IDENTITY_MISMATCH")
    if set(mac_identities) != set(truth_identities):
        raise CalibrationError("CALIBRATION_TRUTH_IDENTITY_MISMATCH")
    if not fixture_mode and (
        len(mac_identities) != 200 or len(linux_identities) != 200 or len(truth_identities) != 200
    ):
        raise CalibrationError("FORMAL_VAL_INVENTORY_INVALID")

    mac_by_identity = {_identity(record): record for record in mac}
    linux_by_identity = {_identity(record): record for record in linux}
    truths_by_identity = {_identity(truth): truth for truth in truth_items}
    ordered_identities = tuple(sorted(truths_by_identity))
    ordered_mac = tuple(mac_by_identity[identity] for identity in ordered_identities)
    ordered_linux = tuple(linux_by_identity[identity] for identity in ordered_identities)
    ordered_truths = tuple(truths_by_identity[identity] for identity in ordered_identities)
    for platform_records in (ordered_mac, ordered_linux):
        for record, truth in zip(platform_records, ordered_truths, strict=True):
            if (
                record.formal_sample_index != truth.formal_sample_index
                or record.split != truth.split
                or record.scenario != truth.scenario
                or record.image_relpath != truth.image_relpath
                or record.image_sha256 != truth.image_sha256
                or record.image_width != truth.image_width
                or record.image_height != truth.image_height
            ):
                raise CalibrationError("CALIBRATION_RECORD_TRUTH_MISMATCH")

    verified_refs: set[tuple[object, ...]] = set()
    try:
        for truth in ordered_truths:
            for instance in truth.instances:
                key = (
                    instance.mask.relative_path,
                    instance.mask.sha256,
                    instance.mask.pixel_count,
                    instance.mask.image_width,
                    instance.mask.image_height,
                )
                if key not in verified_refs:
                    read_mask(instance.mask, root)
                    verified_refs.add(key)
        for record in (*ordered_mac, *ordered_linux):
            for candidate in record.raw_candidates:
                key = (
                    candidate.mask.relative_path,
                    candidate.mask.sha256,
                    candidate.mask.pixel_count,
                    candidate.mask.image_width,
                    candidate.mask.image_height,
                )
                if key not in verified_refs:
                    read_mask(candidate.mask, root)
                    verified_refs.add(key)
    except (OSError, ValueError) as error:
        raise CalibrationError("MASK_EVIDENCE_INVALID") from error

    return (
        normalized_model,
        ordered_mac,
        ordered_linux,
        ordered_truths,
        root,
        val_inventory_sha,
        mac_inventory_sha,
        linux_inventory_sha,
        commit,
    )


def _record_with_candidates(
    record: PredictionRecord,
    candidates: tuple[RawCandidate, ...],
) -> PredictionRecord:
    if not candidates:
        decision = DecisionOutput.NOT_FOUND
        selected = None
        rejection = "TARGET_NOT_FOUND"
    elif len(candidates) == 1:
        decision = DecisionOutput.UNIQUE
        selected = candidates[0].candidate_id
        rejection = None
    else:
        decision = DecisionOutput.AMBIGUOUS
        selected = None
        rejection = "TARGET_AMBIGUOUS"
    return replace(
        record,
        raw_candidates=candidates,
        raw_count=len(candidates),
        decision=decision,
        selected_candidate_id=selected,
        rejection_reason=rejection,
        error_type=None,
        error_summary=None,
        timed_out=False,
        oom=False,
    )


def _selection_signature(
    records: Sequence[PredictionRecord],
    candidate_sets: Sequence[tuple[RawCandidate, ...]],
) -> tuple[tuple[int, str, tuple[str, ...]], ...]:
    return tuple(
        (
            record.formal_sample_index,
            record.image_sha256,
            tuple(candidate.candidate_id for candidate in candidates),
        )
        for record, candidates in zip(records, candidate_sets, strict=True)
    )


@dataclass(frozen=True, slots=True)
class _RecordPrecomputeTask:
    platform: Literal["macos", "linux"]
    ordinal: int
    model: ModelName
    candidates: tuple[RawCandidate, ...]
    truth_instances: tuple[TruthInstance, ...]
    evidence_root: str


@dataclass(frozen=True, slots=True)
class _RecordPrecompute:
    platform: Literal["macos", "linux"]
    ordinal: int
    grounded_prefixes: tuple[tuple[Decimal, Decimal, tuple[RawCandidate, ...]], ...]
    ious: tuple[tuple[str, str, float], ...]


def _precompute_record(task: _RecordPrecomputeTask) -> _RecordPrecompute:
    grounded_prefixes: list[tuple[Decimal, Decimal, tuple[RawCandidate, ...]]] = []
    if task.model == "grounded_sam":
        for box_threshold, text_threshold in _GROUNDING_PREFIX_GRID:
            grounding_filtered = tuple(
                candidate
                for candidate in task.candidates
                if candidate.grounding_box_score is not None
                and candidate.grounding_text_score is not None
                and candidate.grounding_box_score >= float(box_threshold)
                and candidate.grounding_text_score >= float(text_threshold)
            )
            grounded_prefixes.append(
                (
                    box_threshold,
                    text_threshold,
                    _deduplicate_boxes(grounding_filtered, Decimal("0.85")),
                )
            )

    root = Path(task.evidence_root)
    truth_masks = tuple(
        (instance.instance_id, read_mask(instance.mask, root)) for instance in task.truth_instances
    )
    candidate_masks = tuple(
        (candidate.candidate_id, read_mask(candidate.mask, root)) for candidate in task.candidates
    )
    ious = tuple(
        (truth_id, candidate_id, mask_iou(truth_mask, candidate_mask))
        for truth_id, truth_mask in truth_masks
        for candidate_id, candidate_mask in candidate_masks
    )
    return _RecordPrecompute(
        task.platform,
        task.ordinal,
        tuple(grounded_prefixes),
        ious,
    )


def _filter_precomputed_grounded(
    config: GroundedSamBenchmarkThresholds,
    candidates: tuple[RawCandidate, ...],
) -> tuple[RawCandidate, ...]:
    return tuple(
        candidate
        for candidate in candidates
        if candidate.sam_quality is not None
        and candidate.sam_quality >= float(config.sam_quality)
        and candidate.mask.pixel_count >= config.min_mask_pixels
        and (
            candidate.mask.pixel_count / (candidate.mask.image_width * candidate.mask.image_height)
        )
        <= float(config.max_mask_area_ratio)
        and candidate.ranking_score >= float(config.target_confidence_threshold)
    )


def _precompute_records(
    model: ModelName,
    mac: tuple[PredictionRecord, ...],
    linux: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    evidence_root: Path,
    workers: int,
    callback: ProgressCallback | None,
    started_at: float,
) -> tuple[
    Mapping[str, tuple[Mapping[tuple[Decimal, Decimal], tuple[RawCandidate, ...]], ...]],
    Mapping[str, Mapping[int, Mapping[tuple[str, str], float]]],
]:
    tasks = tuple(
        _RecordPrecomputeTask(
            platform,
            ordinal,
            model,
            record.raw_candidates,
            truth.instances,
            str(evidence_root),
        )
        for platform, records in (("macos", mac), ("linux", linux))
        for ordinal, (record, truth) in enumerate(zip(records, truths, strict=True))
    )
    total = len(tasks)
    _emit_progress(callback, "precompute", 0, total, started_at)
    if workers == 1:
        results = map(_precompute_record, tasks)
        executor = None
    else:
        executor = ProcessPoolExecutor(max_workers=workers)
        chunksize = max(1, total // (workers * 4))
        results = executor.map(_precompute_record, tasks, chunksize=chunksize)

    grounded: dict[str, list[Mapping[tuple[Decimal, Decimal], tuple[RawCandidate, ...]]]] = {
        "macos": [{} for _ in mac],
        "linux": [{} for _ in linux],
    }
    ious: dict[str, dict[int, Mapping[tuple[str, str], float]]] = {
        "macos": {},
        "linux": {},
    }
    step = max(1, total // 100)
    try:
        for completed, result in enumerate(results, start=1):
            grounded[result.platform][result.ordinal] = {
                (box, text): candidates for box, text, candidates in result.grounded_prefixes
            }
            record = (mac if result.platform == "macos" else linux)[result.ordinal]
            ious[result.platform][record.formal_sample_index] = {
                (truth_id, candidate_id): value for truth_id, candidate_id, value in result.ious
            }
            if completed == total or completed % step == 0:
                _emit_progress(callback, "precompute", completed, total, started_at)
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    return (
        MappingProxyType({platform: tuple(values) for platform, values in grounded.items()}),
        MappingProxyType(
            {platform: MappingProxyType(dict(values)) for platform, values in ious.items()}
        ),
    )


@dataclass(frozen=True, slots=True)
class _PlatformEvaluation:
    records: tuple[PredictionRecord, ...]
    decision_metrics: DecisionMetrics
    frozen_metrics: PlatformCalibrationMetrics


@dataclass(frozen=True, slots=True)
class _GridEvaluationContext:
    model: ModelName
    mac: tuple[PredictionRecord, ...]
    linux: tuple[PredictionRecord, ...]
    truths: tuple[TruthSample, ...]
    evidence_root: Path
    grounded_prefixes: Mapping[
        str,
        tuple[Mapping[tuple[Decimal, Decimal], tuple[RawCandidate, ...]], ...],
    ]
    precomputed_ious: Mapping[
        str,
        Mapping[int, Mapping[tuple[str, str], float]],
    ]


_GRID_WORKER_CONTEXT: _GridEvaluationContext | None = None


_GRID_WORKER_PLATFORM_CACHE: dict[
    tuple[str, tuple[tuple[int, str, tuple[str, ...]], ...]],
    _PlatformEvaluation,
] = {}


_GRID_WORKER_MERGED_CACHE: dict[
    tuple[
        tuple[tuple[int, str, tuple[str, ...]], ...],
        tuple[tuple[int, str, tuple[str, ...]], ...],
    ],
    tuple[float, float | None],
] = {}


def _evaluate_platform(
    filtered_records: tuple[PredictionRecord, ...],
    truths: tuple[TruthSample, ...],
    evidence_root: Path,
    precomputed_ious: Mapping[int, Mapping[tuple[str, str], float]],
) -> _PlatformEvaluation:
    decisions = aggregate_decisions(filtered_records, truths)
    ap = compute_ap(
        filtered_records,
        truths,
        evidence_root,
        _AP_THRESHOLDS,
        precomputed_ious=precomputed_ious,
    )
    matches: dict[tuple[int, str], ImageMetricInput] = {}
    for record, truth in zip(filtered_records, truths, strict=True):
        assigned = (
            maximize_mask_iou_assignment(
                truth.instances,
                record.raw_candidates,
                evidence_root,
                precomputed_ious=precomputed_ious[record.formal_sample_index],
            )
            if truth.instances and record.raw_candidates
            else ()
        )
        identity = (record.formal_sample_index, record.image_sha256)
        matches[identity] = ImageMetricInput(
            formal_sample_index=record.formal_sample_index,
            truth_count=len(truth.instances),
            candidate_count=len(record.raw_candidates),
            matches=assigned,
        )
    scenarios = aggregate_scenarios(filtered_records, truths, matches, evidence_root)
    two_cup = scenarios.get("two_cups")
    if decisions.macro_f1 is None:
        raise CalibrationError("CALIBRATION_FULL_DENOMINATOR_REQUIRED")
    metrics = PlatformCalibrationMetrics(
        sample_count=decisions.sample_count,
        error_count=decisions.error_count,
        macro_f1=decisions.macro_f1,
        mask_ap50_95=ap.mask_map,
        unsafe_unique_count=decisions.unsafe_unique_count,
        unsafe_unique_denominator=decisions.unsafe_unique_denominator,
        unsafe_unique_rate=decisions.unsafe_unique_rate,
        two_cup_both_matched_recall=(
            None if two_cup is None else two_cup.two_cup_both_matched_recall
        ),
    )
    return _PlatformEvaluation(filtered_records, decisions, metrics)


def _combined_macro_f1(first: DecisionMetrics, second: DecisionMetrics) -> float:
    truth_classes = ("0", "1", "2+")
    expected = {
        "0": DecisionOutput.NOT_FOUND.value,
        "1": DecisionOutput.UNIQUE.value,
        "2+": DecisionOutput.AMBIGUOUS.value,
    }
    scores: list[float] = []
    for truth_class in truth_classes:
        output = expected[truth_class]
        true_positive = first.confusion[truth_class][output] + second.confusion[truth_class][output]
        false_positive = sum(
            first.confusion[other][output] + second.confusion[other][output]
            for other in truth_classes
            if other != truth_class
        )
        false_negative = sum(
            first.confusion[truth_class][actual] + second.confusion[truth_class][actual]
            for actual in ("NOT_FOUND", "UNIQUE", "AMBIGUOUS", "ERROR")
            if actual != output
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(0.0 if denominator == 0 else (2.0 * true_positive) / denominator)
    return float(sum(scores) / len(scores))


def _remap_for_merged(
    records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    parity: int,
) -> tuple[tuple[PredictionRecord, ...], tuple[TruthSample, ...]]:
    remapped_records = tuple(
        replace(record, formal_sample_index=record.formal_sample_index * 2 + parity)
        for record in records
    )
    remapped_truths = tuple(
        replace(truth, formal_sample_index=truth.formal_sample_index * 2 + parity)
        for truth in truths
    )
    return remapped_records, remapped_truths


def _merged_ap(
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    evidence_root: Path,
    mac_precomputed_ious: Mapping[int, Mapping[tuple[str, str], float]],
    linux_precomputed_ious: Mapping[int, Mapping[tuple[str, str], float]],
) -> float | None:
    mac_remapped, mac_truths = _remap_for_merged(mac_records, truths, 0)
    linux_remapped, linux_truths = _remap_for_merged(linux_records, truths, 1)
    merged_ious = {
        sample_index * 2: values for sample_index, values in mac_precomputed_ious.items()
    }
    merged_ious.update(
        {sample_index * 2 + 1: values for sample_index, values in linux_precomputed_ious.items()}
    )
    return compute_ap(
        mac_remapped + linux_remapped,
        mac_truths + linux_truths,
        evidence_root,
        _AP_THRESHOLDS,
        precomputed_ious=merged_ious,
    ).mask_map


def _evaluate_grid_config(
    config: YoloThresholds | GroundedSamBenchmarkThresholds,
    context: _GridEvaluationContext,
    platform_cache: dict[
        tuple[str, tuple[tuple[int, str, tuple[str, ...]], ...]],
        _PlatformEvaluation,
    ],
    merged_cache: dict[
        tuple[
            tuple[tuple[int, str, tuple[str, ...]], ...],
            tuple[tuple[int, str, tuple[str, ...]], ...],
        ],
        tuple[float, float | None],
    ],
) -> CalibrationResult:
    if isinstance(config, GroundedSamBenchmarkThresholds):
        prefix_key = (config.box_threshold, config.text_threshold)
        mac_candidates = tuple(
            _filter_precomputed_grounded(config, candidates[prefix_key])
            for candidates in context.grounded_prefixes["macos"]
        )
        linux_candidates = tuple(
            _filter_precomputed_grounded(config, candidates[prefix_key])
            for candidates in context.grounded_prefixes["linux"]
        )
    else:
        mac_candidates = tuple(
            config.filter_candidates(record.raw_candidates) for record in context.mac
        )
        linux_candidates = tuple(
            config.filter_candidates(record.raw_candidates) for record in context.linux
        )
    mac_signature = _selection_signature(context.mac, mac_candidates)
    linux_signature = _selection_signature(context.linux, linux_candidates)
    mac_key = ("macos", mac_signature)
    linux_key = ("linux", linux_signature)
    if mac_key not in platform_cache:
        mac_filtered = tuple(
            _record_with_candidates(record, candidates)
            for record, candidates in zip(context.mac, mac_candidates, strict=True)
        )
        platform_cache[mac_key] = _evaluate_platform(
            mac_filtered,
            context.truths,
            context.evidence_root,
            context.precomputed_ious["macos"],
        )
    if linux_key not in platform_cache:
        linux_filtered = tuple(
            _record_with_candidates(record, candidates)
            for record, candidates in zip(context.linux, linux_candidates, strict=True)
        )
        platform_cache[linux_key] = _evaluate_platform(
            linux_filtered,
            context.truths,
            context.evidence_root,
            context.precomputed_ious["linux"],
        )
    mac_evaluation = platform_cache[mac_key]
    linux_evaluation = platform_cache[linux_key]
    merged_key = (mac_signature, linux_signature)
    if merged_key not in merged_cache:
        merged_cache[merged_key] = (
            _combined_macro_f1(
                mac_evaluation.decision_metrics,
                linux_evaluation.decision_metrics,
            ),
            _merged_ap(
                mac_evaluation.records,
                linux_evaluation.records,
                context.truths,
                context.evidence_root,
                context.precomputed_ious["macos"],
                context.precomputed_ious["linux"],
            ),
        )
    merged_macro, merged_mask_ap = merged_cache[merged_key]
    return CalibrationResult(
        selected=config,
        platform_metrics={
            "macos": mac_evaluation.frozen_metrics,
            "linux": linux_evaluation.frozen_metrics,
        },
        merged_macro_f1=merged_macro,
        merged_mask_ap50_95=merged_mask_ap,
    )


def _initialize_grid_worker(context: _GridEvaluationContext) -> None:
    global _GRID_WORKER_CONTEXT
    global _GRID_WORKER_PLATFORM_CACHE
    global _GRID_WORKER_MERGED_CACHE
    _GRID_WORKER_CONTEXT = context
    _GRID_WORKER_PLATFORM_CACHE = {}
    _GRID_WORKER_MERGED_CACHE = {}


def _evaluate_grid_worker(
    config: YoloThresholds | GroundedSamBenchmarkThresholds,
) -> CalibrationResult:
    if _GRID_WORKER_CONTEXT is None:
        raise RuntimeError("calibration grid worker is not initialized")
    return _evaluate_grid_config(
        config,
        _GRID_WORKER_CONTEXT,
        _GRID_WORKER_PLATFORM_CACHE,
        _GRID_WORKER_MERGED_CACHE,
    )


def calibrate_joint_platform_val(
    model: str,
    mac_records: Sequence[PredictionRecord],
    linux_records: Sequence[PredictionRecord],
    truths: Sequence[TruthSample],
    inventory_sha: str,
    *,
    evidence_root: Path,
    mac_prediction_inventory_sha256: str,
    linux_prediction_inventory_sha256: str,
    source_commit: str,
    fixture_mode: bool = False,
    workers: int = 1,
    progress_callback: ProgressCallback | None = None,
    progress_started_at: float | None = None,
) -> ThresholdLock:
    """Calibrate one exact grid over aligned macOS and Linux val records."""

    if type(workers) is not int or not 1 <= workers <= 64:
        raise CalibrationError("CALIBRATION_WORKERS_INVALID")
    if progress_callback is not None and not callable(progress_callback):
        raise CalibrationError("CALIBRATION_PROGRESS_CALLBACK_INVALID")
    if progress_started_at is None:
        started_at = time.monotonic()
    elif (
        isinstance(progress_started_at, bool)
        or not isinstance(progress_started_at, (int, float))
        or not math.isfinite(progress_started_at)
    ):
        raise CalibrationError("CALIBRATION_PROGRESS_CONFIG_INVALID")
    else:
        started_at = float(progress_started_at)
    _emit_progress(progress_callback, "verify", 0, 1, started_at)

    (
        normalized_model,
        mac,
        linux,
        truth_items,
        root,
        val_inventory_sha,
        mac_inventory_sha,
        linux_inventory_sha,
        commit,
    ) = _validate_inputs(
        model,
        mac_records,
        linux_records,
        truths,
        inventory_sha,
        evidence_root,
        mac_prediction_inventory_sha256,
        linux_prediction_inventory_sha256,
        source_commit,
        fixture_mode,
    )
    _emit_progress(progress_callback, "verify", 1, 1, started_at)
    grounded_prefixes, precomputed_ious = _precompute_records(
        normalized_model,
        mac,
        linux,
        truth_items,
        root,
        workers,
        progress_callback,
        started_at,
    )
    grid: Iterator[YoloThresholds | GroundedSamBenchmarkThresholds]
    grid = (
        enumerate_yolo_grid() if normalized_model == "yolo_seg" else enumerate_grounded_sam_grid()
    )
    points: list[CalibrationResult] = []
    grid_total = 2527 if normalized_model == "yolo_seg" else 32400
    grid_step = max(1, grid_total // 100)
    context = _GridEvaluationContext(
        normalized_model,
        mac,
        linux,
        truth_items,
        root,
        {
            platform: tuple(dict(prefixes) for prefixes in platform_values)
            for platform, platform_values in grounded_prefixes.items()
        },
        {
            platform: {
                sample_index: dict(values)
                for sample_index, values in platform_values.items()
            }
            for platform, platform_values in precomputed_ious.items()
        },
    )
    grid_executor = None
    if normalized_model == "grounded_sam" and workers > 1:
        grid_executor = ProcessPoolExecutor(
            max_workers=workers,
            initializer=_initialize_grid_worker,
            initargs=(context,),
        )
        results = grid_executor.map(
            _evaluate_grid_worker,
            grid,
            chunksize=len(decimal_range("0.50", "0.95", "0.05"))
            * len(decimal_range("0.05", "0.90", "0.05")),
        )
    else:
        platform_cache: dict[
            tuple[str, tuple[tuple[int, str, tuple[str, ...]], ...]],
            _PlatformEvaluation,
        ] = {}
        merged_cache: dict[
            tuple[
                tuple[tuple[int, str, tuple[str, ...]], ...],
                tuple[tuple[int, str, tuple[str, ...]], ...],
            ],
            tuple[float, float | None],
        ] = {}
        results = (
            _evaluate_grid_config(config, context, platform_cache, merged_cache)
            for config in grid
        )
    _emit_progress(progress_callback, "grid", 0, grid_total, started_at)
    try:
        for grid_completed, point in enumerate(results, start=1):
            points.append(point)
            if grid_completed == grid_total or grid_completed % grid_step == 0:
                _emit_progress(
                    progress_callback,
                    "grid",
                    grid_completed,
                    grid_total,
                    started_at,
                )
    finally:
        if grid_executor is not None:
            grid_executor.shutdown(wait=True, cancel_futures=True)
    _emit_progress(progress_callback, "finalize", 0, 1, started_at)
    result = select_calibration_result(points)
    lock = ThresholdLock(
        schema_version=LOCK_SCHEMA_VERSION,
        model=normalized_model,
        grid_version=_GRID_VERSIONS[normalized_model],
        objective_version=OBJECTIVE_VERSION,
        tie_break_version=TIE_BREAK_VERSION,
        val_inventory_sha256=val_inventory_sha,
        mac_prediction_inventory_sha256=mac_inventory_sha,
        linux_prediction_inventory_sha256=linux_inventory_sha,
        formal=not fixture_mode,
        platform_sample_counts={"macos": len(mac), "linux": len(linux)},
        selected=result.selected,
        outcome=result.outcome,
        deployable=result.deployable,
        source_commit=commit,
        objective_metrics=_objective_metrics(result),
        platform_metrics=result.platform_metrics,
        lock_sha256="0" * 64,
    )
    finalized = lock.with_recomputed_sha256()
    _emit_progress(progress_callback, "finalize", 1, 1, started_at)
    return finalized
