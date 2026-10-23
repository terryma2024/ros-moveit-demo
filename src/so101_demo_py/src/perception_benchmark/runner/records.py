"""Validate the run specification, build the record documents and publish the candidate masks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import math
from pathlib import Path, PurePosixPath
import re

import numpy as np

from so101_demo.core.detection import DetectionCandidate, DetectionFrame
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    ProductionObservation,
    RawDetectionResult,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    decode_mask_rle,
    encode_mask_rle,
    read_mask,
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
    model_id_for_name,
)
from so101_demo.perception_benchmark.dataset.contracts import DatasetSampleRef
from so101_demo.perception_benchmark.dataset.pinned_files import _PinnedDirectory, _PinnedFileError
from so101_demo.perception_benchmark.matching import mask_iou
from so101_demo.perception_benchmark.runner.contracts import (
    _CANDIDATE_ID,
    _CANDIDATE_KEYS,
    _MASK_KEYS,
    _OBSERVED_RUN_KINDS,
    _PHASE_TIMING_KEYS,
    _RAW_RUN_KINDS,
    _RECORD_DOCUMENT_KEYS,
    _RESOURCE_SAMPLE_KEYS,
    _RUNTIME_PROVENANCE_KEYS,
    _SOURCE_COMMIT,
    _TIMING_BREAKDOWN_KEYS,
    RunCheckpoint,
    RunIntegrityError,
    RunSpec,
    _FatalRunError,
)
from so101_demo.perception_benchmark.runner.storage import (
    _atomic_write_new_bytes,
    _create_new_directory,
    _jsonable,
    _read_canonical_json,
    _read_pinned_canonical_json,
    _require_directory,
    _require_sha,
    _safe_relative_path,
    _sha256,
)
from so101_demo.perception_benchmark.runner.verification import (
    _classify_error,
    _decision_from_candidates,
    _runtime_provenance,
    _sanitize_summary,
    _verify_threshold_lock_chain,
)
from so101_demo.perception_benchmark.timing import (
    PhaseTimingBreakdown,
    ResourceSample,
)


def _validate_spec(spec: RunSpec, adapter: object) -> None:
    if not isinstance(spec.run_id, str) or not spec.run_id:
        raise RunIntegrityError("RUN_ID_INVALID")
    if spec.platform not in {"macos", "linux"}:
        raise RunIntegrityError("PLATFORM_INVALID")
    if spec.model not in {"yolo_seg", "grounded_sam"}:
        raise RunIntegrityError("MODEL_INVALID")
    if spec.device not in {"mps", "cuda"}:
        raise RunIntegrityError("FORMAL_DEVICE_INVALID")
    if (spec.platform, spec.device) not in {("macos", "mps"), ("linux", "cuda")}:
        raise RunIntegrityError("PLATFORM_DEVICE_MISMATCH")
    if spec.dtype != "float32":
        raise RunIntegrityError("NON_FP32_RUNTIME")
    _require_sha(spec.config_sha256, "CONFIG_SHA256_INVALID")
    if not isinstance(spec.source_commit, str) or _SOURCE_COMMIT.fullmatch(
        spec.source_commit
    ) is None:
        raise RunIntegrityError("SOURCE_COMMIT_INVALID")
    if spec.collection_mode is not CollectionMode.LOW_FLOOR:
        raise RunIntegrityError("COLLECTION_MODE_INVALID")
    if spec.max_gpu_temperature_celsius is not None and (
        isinstance(spec.max_gpu_temperature_celsius, bool)
        or not isinstance(spec.max_gpu_temperature_celsius, (int, float))
        or not math.isfinite(float(spec.max_gpu_temperature_celsius))
        or float(spec.max_gpu_temperature_celsius) <= 0.0
    ):
        raise RunIntegrityError("THERMAL_LIMIT_INVALID")
    locked = spec.run_kind.name.startswith("TEST_") or (
        spec.run_kind is RunKind.ORACLE_DIAGNOSTIC
    )
    if spec.run_kind is RunKind.VAL_RAW and (
        spec.threshold_lock_sha256 is not None
        or spec.threshold_lock_path is not None
    ):
        raise RunIntegrityError("VAL_RAW_FORBIDS_THRESHOLD_LOCK")
    if locked:
        _require_sha(
            spec.threshold_lock_sha256,
            "LOCKED_RUN_REQUIRES_THRESHOLD_LOCK",
        )
        if spec.inventory.split != "test":
            raise RunIntegrityError("LOCKED_RUN_REQUIRES_TEST_INVENTORY")
        _require_sha(
            spec.inventory.test_access_event_sha256,
            "LOCKED_RUN_REQUIRES_TEST_ACCESS",
        )
        _verify_threshold_lock_chain(spec)
    elif (
        spec.threshold_lock_sha256 is not None
        or spec.threshold_lock_path is not None
    ):
        raise RunIntegrityError("UNLOCKED_RUN_FORBIDS_THRESHOLD_LOCK")
    if spec.run_kind in {RunKind.VAL_RAW, RunKind.NON_FORMAL_DRY_RUN} and (
        spec.inventory.split != "val"
    ):
        raise RunIntegrityError("VAL_RUN_REQUIRES_VAL_INVENTORY")
    if spec.run_kind in _OBSERVED_RUN_KINDS and spec.production_observer is None:
        raise RunIntegrityError("PRODUCTION_OBSERVER_REQUIRED")
    if spec.run_kind in _RAW_RUN_KINDS and spec.production_observer is not None:
        raise RunIntegrityError("RAW_RUN_FORBIDS_PRODUCTION_OBSERVER")
    adapter_device = getattr(adapter, "runtime_device", None)
    if adapter_device != spec.device:
        raise RunIntegrityError("ADAPTER_DEVICE_MISMATCH")
    adapter_model_id = getattr(adapter, "model_id", None)
    if adapter_model_id != model_id_for_name(spec.model):
        raise RunIntegrityError("ADAPTER_MODEL_MISMATCH")
    _runtime_provenance(spec, adapter)


def _record_document(
    record: PredictionRecord,
    spec: RunSpec,
    *,
    timings: PhaseTimingBreakdown | None,
    resources: tuple[ResourceSample, ...],
    irreversible_limits: Mapping[str, int | float | str],
) -> dict[str, object]:
    document = dict(_jsonable(record))
    document.update(
        {
            "platform": spec.platform,
            "model": spec.model,
            "device": spec.device,
            "dtype": spec.dtype,
            "source_commit": spec.source_commit,
            "inventory_sha256": spec.inventory.inventory_sha256,
            "collection_mode": spec.collection_mode.value,
            "max_gpu_temperature_celsius": spec.max_gpu_temperature_celsius,
            "timing_breakdown": _jsonable(timings),
            "resource_samples": _jsonable(resources),
            "irreversible_limits": _jsonable(irreversible_limits),
        }
    )
    return document


def _adapter_evidence_root(adapter: object, run_root: Path) -> Path:
    direct = getattr(adapter, "evidence_root", None)
    if isinstance(direct, Path):
        return _require_directory(direct, "ADAPTER_EVIDENCE_ROOT_INVALID")
    store = getattr(adapter, "_artifact_store", None)
    stored = getattr(store, "root", None)
    if isinstance(stored, Path):
        return _require_directory(stored, "ADAPTER_EVIDENCE_ROOT_INVALID")
    return run_root


def _read_verified_adapter_mask(mask: MaskRef, source_root: Path) -> tuple[np.ndarray, bytes]:
    path = _safe_relative_path(
        source_root, mask.relative_path, "RECORD_MASK_PATH_INVALID"
    )
    document, payload = _read_canonical_json(
        path, "RECORD_MASK_CANONICAL_INVALID"
    )
    if canonical_json_bytes(document) != payload:
        raise RunIntegrityError("RECORD_MASK_CANONICAL_INVALID")
    try:
        value = read_mask(mask, source_root)
    except (OSError, ValueError) as error:
        raise RunIntegrityError("RECORD_MASK_INTEGRITY_INVALID") from error
    return value, payload


def _publish_candidate_masks(
    candidates: tuple[RawCandidate, ...],
    formal_sample_index: int,
    source_root: Path,
    run_root: Path,
    observed_candidates: Mapping[str, DetectionCandidate] | None = None,
) -> tuple[RawCandidate, ...]:
    if not candidates:
        return ()
    for candidate in candidates:
        if _CANDIDATE_ID.fullmatch(candidate.candidate_id) is None:
            raise RunIntegrityError("CANDIDATE_ID_UNSAFE")
    masks_root = run_root / "masks"
    if masks_root.is_symlink():
        raise RunIntegrityError("MASK_DIRECTORY_INVALID")
    if not masks_root.exists():
        _create_new_directory(masks_root, run_root, "MASK_DIRECTORY_ALREADY_EXISTS")
    masks_root = _require_directory(masks_root, "MASK_DIRECTORY_INVALID")
    index_dir = masks_root / f"{formal_sample_index:06d}"
    _create_new_directory(index_dir, run_root, "MASK_INDEX_ALREADY_EXISTS")
    published: list[RawCandidate] = []
    for candidate in candidates:
        relative = f"masks/{formal_sample_index:06d}/{candidate.candidate_id}.rle.json"
        target = run_root / relative
        observed = (
            None
            if observed_candidates is None
            else observed_candidates.get(candidate.candidate_id)
        )
        if observed is None:
            _, payload = _read_verified_adapter_mask(candidate.mask, source_root)
            published_candidate = replace(
                candidate,
                mask=replace(candidate.mask, relative_path=relative),
            )
        else:
            value = np.asarray(observed.mask, dtype=bool)
            payload = canonical_json_bytes(encode_mask_rle(value))
            mask_ref = MaskRef(
                relative_path=relative,
                sha256=_mask_sha256(value),
                pixel_count=int(value.sum()),
                image_width=int(value.shape[1]),
                image_height=int(value.shape[0]),
            )
            published_candidate = replace(
                candidate,
                bbox_xyxy=tuple(observed.bbox_xyxy),
                mask=mask_ref,
                ranking_score=float(observed.confidence),
                grounding_box_score=float(observed.confidence),
                sam_quality=float(observed.segmentation_quality),
            )
        _atomic_write_new_bytes(target, payload, "MASK_WRITE_FAILED")
        published.append(published_candidate)
    return tuple(published)


def _mask_sha256(value: np.ndarray) -> str:
    return _sha256(value.astype(np.uint8, copy=False).tobytes(order="C"))


def _production_mask(spec: RunSpec, value: np.ndarray) -> np.ndarray:
    if spec.model == "yolo_seg":
        from so101_demo.adapters.perception.yolo_seg import _trim_mask_boundary

        value = _trim_mask_boundary(value)
    return np.asarray(value, dtype=bool)


def _matches_production_candidate(
    spec: RunSpec,
    raw: RawCandidate,
    observed: DetectionCandidate,
    raw_mask: np.ndarray,
) -> bool:
    if (
        observed.class_id != raw.label
        or tuple(observed.bbox_xyxy) != raw.bbox_xyxy
        or observed.confidence != raw.ranking_score
    ):
        return False
    if spec.model == "yolo_seg":
        return (
            _mask_sha256(observed.mask) == _mask_sha256(raw_mask)
            and raw.class_confidence == observed.confidence
            and observed.segmentation_quality is None
        )
    return (
        raw.grounding_box_score == observed.confidence
        and raw.sam_quality is not None
        and observed.segmentation_quality is not None
        and mask_iou(raw_mask, np.asarray(observed.mask, dtype=bool))
        >= spec.production_candidate_mask_iou_threshold
    )


def _reconcile_production_candidates(
    spec: RunSpec,
    frame: DetectionFrame,
    result: RawDetectionResult,
    observation: ProductionObservation,
    provenance: RuntimeProvenance,
    source_root: Path,
) -> tuple[
    tuple[RawCandidate, ...],
    str | None,
    Mapping[str, DetectionCandidate],
]:
    batch = observation.batch
    if batch is None:
        if observation.decision is not DecisionOutput.ERROR:
            raise RunIntegrityError("PRODUCTION_BATCH_REQUIRED")
        return result.raw_candidates, None, {}
    if (
        batch.model_id != result.model_id
        or batch.weights_sha256 != provenance.weights_sha256
        or batch.runtime_device != spec.device
        or (batch.image_width, batch.image_height)
        != (frame.image_width, frame.image_height)
    ):
        raise RunIntegrityError("PRODUCTION_BATCH_IDENTITY_MISMATCH")
    raw_masks = {
        raw.candidate_id: _production_mask(
            spec,
            _read_verified_adapter_mask(raw.mask, source_root)[0]
        )
        for raw in result.raw_candidates
    }
    available = {raw.candidate_id: raw for raw in result.raw_candidates}
    mapped: list[RawCandidate] = []
    ids: dict[str, str] = {}
    observed_by_raw_id: dict[str, DetectionCandidate] = {}
    for observed in batch.candidates:
        if (
            observed.source_stamp_ns != frame.source_stamp_ns
            or observed.source_frame_id != frame.source_frame_id
            or (observed.image_width, observed.image_height)
            != (frame.image_width, frame.image_height)
        ):
            raise RunIntegrityError("PRODUCTION_CANDIDATE_FRAME_MISMATCH")
        matches = [
            raw
            for raw in available.values()
            if _matches_production_candidate(
                spec,
                raw,
                observed,
                raw_masks[raw.candidate_id],
            )
        ]
        if len(matches) != 1:
            raise RunIntegrityError("PRODUCTION_CANDIDATE_MAPPING_INVALID")
        raw = matches[0]
        available.pop(raw.candidate_id)
        mapped.append(raw)
        ids[observed.instance_id] = raw.candidate_id
        if spec.model == "grounded_sam":
            observed_by_raw_id[raw.candidate_id] = observed
    selected = None
    if observation.selected_candidate_id is not None:
        selected = ids.get(observation.selected_candidate_id)
        if selected is None:
            raise RunIntegrityError("PRODUCTION_SELECTED_MAPPING_INVALID")
    return tuple(mapped), selected, observed_by_raw_id


def _sanitize_observer_summary(error_type: str, summary: str) -> str:
    synthetic = RuntimeError(summary)
    sanitized = _sanitize_summary(synthetic)
    prefix = "RuntimeError: "
    if sanitized.startswith(prefix):
        sanitized = sanitized[len(prefix) :]
    return sanitized or error_type


def _observer_error_flags(error_type: str, summary: str) -> tuple[bool, bool]:
    combined = f"{error_type} {summary}".lower()
    timed_out = "timeout" in combined or "timed out" in combined
    oom = (
        "out of memory" in combined
        or "outofmemory" in combined
        or re.search(r"\boom\b", combined) is not None
    )
    return timed_out, oom


def _ok_record(
    spec: RunSpec,
    sample: DatasetSampleRef,
    frame: DetectionFrame,
    result: RawDetectionResult,
    provenance: RuntimeProvenance,
    observation: ProductionObservation | None,
    run_root: Path,
    source_root: Path,
) -> tuple[PredictionRecord, dict[str, object]]:
    candidates = result.raw_candidates
    observed_candidates: Mapping[str, DetectionCandidate] = {}
    selector_ms = result.phase_timings.selector_ms
    if observation is None:
        decision, selected, rejection = _decision_from_candidates(candidates)
        error_type = None
        error_summary = None
        record_status = RecordStatus.OK
    else:
        decision = observation.decision
        candidates, selected, observed_candidates = _reconcile_production_candidates(
            spec,
            frame,
            result,
            observation,
            provenance,
            source_root,
        )
        rejection = observation.rejection_reason
        selector_ms = observation.selector_ms
        error_type = observation.error_type
        error_summary = observation.error_summary
        record_status = (
            RecordStatus.ERROR
            if decision is DecisionOutput.ERROR
            else RecordStatus.OK
        )
        if record_status is RecordStatus.ERROR:
            if error_type is None or error_summary is None:
                raise RunIntegrityError("PRODUCTION_ERROR_FIELDS_INVALID")
            error_summary = _sanitize_observer_summary(error_type, error_summary)
    candidates = _publish_candidate_masks(
        candidates,
        sample.formal_sample_index,
        source_root,
        run_root,
        observed_candidates,
    )
    timed_out = False
    oom = False
    if record_status is RecordStatus.ERROR:
        timed_out, oom = _observer_error_flags(
            str(error_type), str(error_summary)
        )
    phase_timings = PhaseTimings(
        grounding_ms=result.phase_timings.dino_or_yolo_ms,
        sam_ms=result.phase_timings.sam_ms,
        selector_ms=selector_ms,
    )
    record = PredictionRecord(
        run_id=spec.run_id,
        schema_version=SCHEMA_VERSION,
        run_kind=spec.run_kind,
        record_status=record_status,
        formal_sample_index=sample.formal_sample_index,
        split=sample.split,
        scenario=sample.scenario,
        image_relpath=sample.image_relpath,
        image_sha256=sample.image_sha256,
        image_width=frame.image_width,
        image_height=frame.image_height,
        model_id=result.model_id,
        runtime_provenance=provenance,
        config_sha256=spec.config_sha256,
        threshold_lock_sha256=spec.threshold_lock_sha256,
        raw_candidates=candidates,
        phase_timings=phase_timings,
        raw_count=len(candidates),
        decision=decision,
        selected_candidate_id=selected,
        rejection_reason=rejection,
        error_type=error_type,
        error_summary=error_summary,
        timed_out=timed_out,
        oom=oom,
        fallback_used=False,
    )
    irreversible_limits = dict(result.irreversible_limits)
    if observation is not None and spec.model == "grounded_sam":
        irreversible_limits["production_candidate_mask_iou_threshold"] = (
            spec.production_candidate_mask_iou_threshold
        )
    return record, _record_document(
        record,
        spec,
        timings=result.phase_timings,
        resources=result.resource_samples,
        irreversible_limits=irreversible_limits,
    )


def _error_record(
    spec: RunSpec,
    sample: DatasetSampleRef,
    frame: DetectionFrame,
    provenance: RuntimeProvenance,
    model_id: str,
    error: BaseException,
    *,
    result: RawDetectionResult | None = None,
    run_root: Path | None = None,
    source_root: Path | None = None,
) -> tuple[PredictionRecord, dict[str, object]]:
    if model_id != model_id_for_name(spec.model):
        raise _FatalRunError("MODEL_IDENTITY_MISMATCH")
    classified = _classify_error(error)
    candidates: tuple[RawCandidate, ...] = ()
    timings: PhaseTimingBreakdown | None = None
    resources: tuple[ResourceSample, ...] = ()
    irreversible_limits: Mapping[str, int | float | str] = {}
    if result is not None:
        if run_root is None or source_root is None:
            raise RunIntegrityError("ERROR_EVIDENCE_ROOT_MISSING")
        candidates = _publish_candidate_masks(
            result.raw_candidates,
            sample.formal_sample_index,
            source_root,
            run_root,
        )
        timings = result.phase_timings
        resources = result.resource_samples
        irreversible_limits = result.irreversible_limits
    record = PredictionRecord(
        run_id=spec.run_id,
        schema_version=SCHEMA_VERSION,
        run_kind=spec.run_kind,
        record_status=RecordStatus.ERROR,
        formal_sample_index=sample.formal_sample_index,
        split=sample.split,
        scenario=sample.scenario,
        image_relpath=sample.image_relpath,
        image_sha256=sample.image_sha256,
        image_width=frame.image_width,
        image_height=frame.image_height,
        model_id=model_id,
        runtime_provenance=provenance,
        config_sha256=spec.config_sha256,
        threshold_lock_sha256=spec.threshold_lock_sha256,
        raw_candidates=candidates,
        phase_timings=PhaseTimings(
            grounding_ms=None if timings is None else timings.dino_or_yolo_ms,
            sam_ms=None if timings is None else timings.sam_ms,
            selector_ms=None if timings is None else timings.selector_ms,
        ),
        raw_count=len(candidates),
        decision=DecisionOutput.ERROR,
        selected_candidate_id=None,
        rejection_reason=None,
        error_type=classified.error_type,
        error_summary=classified.summary,
        timed_out=classified.timed_out,
        oom=classified.oom,
        fallback_used=False,
    )
    return record, _record_document(
        record,
        spec,
        timings=timings,
        resources=resources,
        irreversible_limits=irreversible_limits,
    )


def _candidate_from_document(document: object) -> RawCandidate:
    if not isinstance(document, Mapping) or set(document) != _CANDIDATE_KEYS:
        raise RunIntegrityError("RECORD_SCHEMA_INVALID")
    mask = document.get("mask")
    bbox = document.get("bbox_xyxy")
    if (
        not isinstance(mask, Mapping)
        or set(mask) != _MASK_KEYS
        or not isinstance(bbox, list)
        or len(bbox) != 4
    ):
        raise RunIntegrityError("RECORD_SCHEMA_INVALID")
    try:
        return RawCandidate(
            candidate_id=document["candidate_id"],
            label=document["label"],
            bbox_xyxy=tuple(bbox),
            mask=MaskRef(
                relative_path=mask["relative_path"],
                sha256=mask["sha256"],
                pixel_count=mask["pixel_count"],
                image_width=mask["image_width"],
                image_height=mask["image_height"],
            ),
            ranking_score=document["ranking_score"],
            ranking_score_source=document["ranking_score_source"],
            class_confidence=document["class_confidence"],
            grounding_box_score=document["grounding_box_score"],
            grounding_text_score=document["grounding_text_score"],
            sam_quality=document["sam_quality"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RunIntegrityError("RECORD_SCHEMA_INVALID") from error


def _record_from_document(document: Mapping[str, object]) -> PredictionRecord:
    runtime = document.get("runtime_provenance")
    phases = document.get("phase_timings")
    candidates = document.get("raw_candidates")
    environment = runtime.get("environment") if isinstance(runtime, Mapping) else None
    if (
        not isinstance(runtime, Mapping)
        or set(runtime) != _RUNTIME_PROVENANCE_KEYS
        or not isinstance(phases, Mapping)
        or set(phases) != _PHASE_TIMING_KEYS
        or not isinstance(candidates, list)
        or not isinstance(environment, Mapping)
        or not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            and value
            for key, value in environment.items()
        )
    ):
        raise RunIntegrityError("RECORD_SCHEMA_INVALID")
    try:
        provenance = RuntimeProvenance(
            runtime_device=runtime["runtime_device"],
            runtime_name=runtime["runtime_name"],
            runtime_version=runtime["runtime_version"],
            weights_sha256=runtime["weights_sha256"],
            environment=environment,
        )
        return PredictionRecord(
            run_id=document["run_id"],
            schema_version=document["schema_version"],
            run_kind=document["run_kind"],
            record_status=document["record_status"],
            formal_sample_index=document["formal_sample_index"],
            split=document["split"],
            scenario=document["scenario"],
            image_relpath=document["image_relpath"],
            image_sha256=document["image_sha256"],
            image_width=document["image_width"],
            image_height=document["image_height"],
            model_id=document["model_id"],
            runtime_provenance=provenance,
            config_sha256=document["config_sha256"],
            threshold_lock_sha256=document["threshold_lock_sha256"],
            raw_candidates=tuple(_candidate_from_document(item) for item in candidates),
            phase_timings=PhaseTimings(
                grounding_ms=phases["grounding_ms"],
                sam_ms=phases["sam_ms"],
                selector_ms=phases["selector_ms"],
            ),
            raw_count=document["raw_count"],
            decision=document["decision"],
            selected_candidate_id=document["selected_candidate_id"],
            rejection_reason=document["rejection_reason"],
            error_type=document["error_type"],
            error_summary=document["error_summary"],
            timed_out=document["timed_out"],
            oom=document["oom"],
            fallback_used=document["fallback_used"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RunIntegrityError("RECORD_SCHEMA_INVALID") from error


def _verify_extended_record(document: Mapping[str, object]) -> None:
    if set(document) != _RECORD_DOCUMENT_KEYS:
        raise RunIntegrityError("RECORD_SCHEMA_INVALID")
    timings = document.get("timing_breakdown")
    if timings is not None:
        if (
            not isinstance(timings, Mapping)
            or set(timings) != _TIMING_BREAKDOWN_KEYS
        ):
            raise RunIntegrityError("RECORD_TIMING_INVALID")
        try:
            PhaseTimingBreakdown(**timings)
        except (TypeError, ValueError) as error:
            raise RunIntegrityError("RECORD_TIMING_INVALID") from error
    resources = document.get("resource_samples")
    if not isinstance(resources, list):
        raise RunIntegrityError("RECORD_RESOURCE_INVALID")
    for raw in resources:
        if not isinstance(raw, Mapping) or set(raw) != _RESOURCE_SAMPLE_KEYS:
            raise RunIntegrityError("RECORD_RESOURCE_INVALID")
        unavailable_reasons = raw.get("unavailable_reasons")
        tool_versions = raw.get("tool_versions")
        if (
            not isinstance(unavailable_reasons, Mapping)
            or not isinstance(tool_versions, Mapping)
            or not all(
                isinstance(key, str)
                and key
                and isinstance(value, str)
                and value
                for key, value in unavailable_reasons.items()
            )
            or not all(
                isinstance(key, str)
                and key
                and isinstance(value, str)
                and value
                for key, value in tool_versions.items()
            )
        ):
            raise RunIntegrityError("RECORD_RESOURCE_INVALID")
        try:
            ResourceSample(**raw)
        except (TypeError, ValueError) as error:
            raise RunIntegrityError("RECORD_RESOURCE_INVALID") from error
    limits = document.get("irreversible_limits")
    if not isinstance(limits, Mapping) or not all(
        isinstance(key, str)
        and key
        and (
            isinstance(value, str)
            or (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(float(value))
            )
        )
        for key, value in limits.items()
    ):
        raise RunIntegrityError("RECORD_LIMITS_INVALID")


def _checkpoint_identity(checkpoint: RunCheckpoint) -> dict[str, object]:
    return {
        "run_id": checkpoint.run_id,
        "platform": checkpoint.platform,
        "model": checkpoint.model,
        "model_id": checkpoint.model_id,
        "device": checkpoint.device,
        "dtype": checkpoint.dtype,
        "run_kind": (
            checkpoint.run_kind.value if checkpoint.run_kind is not None else None
        ),
        "config_sha256": checkpoint.config_sha,
        "threshold_lock_sha256": checkpoint.threshold_lock_sha256,
        "source_commit": checkpoint.source_commit,
        "inventory_sha256": checkpoint.inventory_sha256,
        "collection_mode": (
            checkpoint.collection_mode.value
            if checkpoint.collection_mode is not None
            else None
        ),
        "max_gpu_temperature_celsius": checkpoint.max_gpu_temperature_celsius,
    }


def _verify_record_mask(
    mask: MaskRef,
    evidence_root: Path,
    formal_sample_index: int,
    candidate_id: str,
    *,
    pinned_root: _PinnedDirectory | None = None,
) -> None:
    expected = f"masks/{formal_sample_index:06d}/{candidate_id}.rle.json"
    if mask.relative_path != expected:
        raise RunIntegrityError("RECORD_MASK_LAYOUT_INVALID")
    if pinned_root is None:
        path = _safe_relative_path(
            evidence_root, mask.relative_path, "RECORD_MASK_PATH_INVALID"
        )
        document, payload = _read_canonical_json(
            path, "RECORD_MASK_CANONICAL_INVALID"
        )
    else:
        document, payload = _read_pinned_canonical_json(
            pinned_root,
            mask.relative_path,
            "RECORD_MASK_CANONICAL_INVALID",
        )
    if canonical_json_bytes(document) != payload:
        raise RunIntegrityError("RECORD_MASK_CANONICAL_INVALID")
    try:
        if pinned_root is None:
            read_mask(mask, evidence_root)
        else:
            decoded = decode_mask_rle(document)
            if (decoded.shape[1], decoded.shape[0]) != (
                mask.image_width,
                mask.image_height,
            ):
                raise ValueError("mask dimensions do not match MaskRef")
            if int(decoded.sum()) != mask.pixel_count:
                raise ValueError("mask pixel_count does not match MaskRef")
            digest = sha256_bytes(
                decoded.astype(np.uint8, copy=False).tobytes(order="C")
            )
            if digest != mask.sha256:
                raise ValueError("mask sha256 does not match MaskRef")
    except (OSError, ValueError) as error:
        raise RunIntegrityError("RECORD_MASK_INTEGRITY_INVALID") from error


def _verify_mask_tree(
    evidence_root: Path,
    expected_paths: set[str],
    *,
    pinned_root: _PinnedDirectory | None = None,
) -> None:
    if pinned_root is not None:
        try:
            all_files, all_directories = pinned_root.tree()
        except _PinnedFileError as error:
            raise RunIntegrityError("RUN_EVIDENCE_FILE_UNSAFE") from error
        actual = {path for path in all_files if path.startswith("masks/")}
        actual_directories = {
            path for path in all_directories if path.startswith("masks/")
        }
        if "masks" in all_directories:
            actual_directories.add("masks")
        expected_directories = (
            {"masks"}
            | {str(PurePosixPath(path).parent) for path in expected_paths}
            if expected_paths
            else set()
        )
        if actual != expected_paths or actual_directories != expected_directories:
            raise RunIntegrityError("MASK_TREE_UNEXPECTED")
        return
    masks_root = evidence_root / "masks"
    if not expected_paths:
        if masks_root.exists() or masks_root.is_symlink():
            raise RunIntegrityError("MASK_TREE_UNEXPECTED")
        return
    root = _require_directory(masks_root, "MASK_DIRECTORY_INVALID")
    actual: set[str] = set()
    actual_directories: set[str] = set()
    for index_entry in root.iterdir():
        if (
            index_entry.is_symlink()
            or not index_entry.is_dir()
            or re.fullmatch(r"\d{6}", index_entry.name) is None
        ):
            raise RunIntegrityError("MASK_TREE_UNEXPECTED")
        actual_directories.add(index_entry.relative_to(evidence_root).as_posix())
        for mask_path in index_entry.iterdir():
            if mask_path.is_symlink() or not mask_path.is_file():
                raise RunIntegrityError("MASK_TREE_UNEXPECTED")
            actual.add(mask_path.relative_to(evidence_root).as_posix())
    expected_directories = {
        str(PurePosixPath(path).parent) for path in expected_paths
    }
    if actual != expected_paths or actual_directories != expected_directories:
        raise RunIntegrityError("MASK_TREE_UNEXPECTED")
