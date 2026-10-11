"""Verify the run inventory, threshold lock chain, images and result documents."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re

import numpy as np
from PIL import Image

from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import (
    RawDetectionResult,
    ResourceSamplingError,
)
from so101_demo.perception_benchmark.calibration.contracts import CalibrationError
from so101_demo.perception_benchmark.calibration.lock_io import verify_threshold_lock
from so101_demo.perception_benchmark.calibration.results import ThresholdLock
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    RawCandidate,
    RuntimeProvenance,
    model_id_for_name,
)
from so101_demo.perception_benchmark.dataset.contracts import (
    DatasetInventory,
    DatasetSampleRef,
    DatasetVerificationError,
)
from so101_demo.perception_benchmark.dataset.pinned_files import _PinnedDirectory, _PinnedFileError
from so101_demo.perception_benchmark.dataset.truth import _require_inventory_capability
from so101_demo.perception_benchmark.dataset.verifier import _validate_persisted_access
from so101_demo.perception_benchmark.runner.contracts import (
    _ABSOLUTE_PATH,
    _SENSITIVE,
    _SHA256,
    RunIntegrityError,
    RunSpec,
    _ClassifiedError,
    _FatalRunError,
    _ResourceStreamValidationError,
    _ThermalValidationError,
)
from so101_demo.perception_benchmark.runner.storage import (
    _read_canonical_json,
    _read_pinned_canonical_json,
    _require_directory,
    _require_sha,
    _safe_relative_path,
    _sample_document_matches,
    _sha256,
)


def _verify_inventory(
    inventory: DatasetInventory,
    *,
    pinned_root: _PinnedDirectory | None = None,
) -> Mapping[str, object]:
    if not isinstance(inventory, DatasetInventory):
        raise RunIntegrityError("INVENTORY_TYPE_INVALID")
    try:
        _require_inventory_capability(inventory)
    except DatasetVerificationError as error:
        raise RunIntegrityError("INVENTORY_CAPABILITY_INVALID") from error
    root = Path(os.path.abspath(inventory.dataset_root))
    if pinned_root is None:
        root = _require_directory(root, "INVENTORY_DATASET_ROOT_INVALID")
        document, payload = _read_canonical_json(
            root / "inventory.json", "INVENTORY_CANONICAL_INVALID"
        )
        sidecar = _safe_relative_path(
            root, "inventory.sha256", "INVENTORY_CANONICAL_INVALID"
        )
        try:
            sidecar_payload = sidecar.read_bytes()
        except OSError as error:
            raise RunIntegrityError("INVENTORY_CANONICAL_INVALID") from error
    else:
        if pinned_root.path != Path(os.path.realpath(root)):
            raise RunIntegrityError("INVENTORY_DATASET_ROOT_INVALID")
        root = pinned_root.path
        document, payload = _read_pinned_canonical_json(
            pinned_root, "inventory.json", "INVENTORY_CANONICAL_INVALID"
        )
        try:
            sidecar_payload = pinned_root.read_file("inventory.sha256")
        except _PinnedFileError as error:
            raise RunIntegrityError("RUN_EVIDENCE_FILE_UNSAFE") from error
    if _sha256(payload) != inventory.inventory_sha256:
        raise RunIntegrityError("INVENTORY_SHA256_CHANGED")
    if sidecar_payload != (
        f"{inventory.inventory_sha256}  inventory.json\n".encode("ascii")
    ):
        raise RunIntegrityError("INVENTORY_CANONICAL_INVALID")
    samples = tuple(inventory.samples)
    if (
        inventory.sample_count != len(samples)
        or [sample.formal_sample_index for sample in samples]
        != list(range(len(samples)))
        or [sample.image_sha256 for sample in samples]
        != sorted(sample.image_sha256 for sample in samples)
        or len({sample.image_sha256 for sample in samples}) != len(samples)
    ):
        raise RunIntegrityError("INVENTORY_ORDER_INVALID")
    raw_samples = document.get("samples")
    if (
        document.get("schema_version") != inventory.schema_version
        or document.get("split") != inventory.split
        or document.get("archive_sha256") != inventory.archive_sha256
        or document.get("sample_count") != inventory.sample_count
        or document.get("scenario_counts") != dict(inventory.scenario_counts)
        or not isinstance(raw_samples, list)
        or len(raw_samples) != len(samples)
        or any(
            not _sample_document_matches(raw, sample)
            for raw, sample in zip(raw_samples, samples, strict=True)
        )
    ):
        raise RunIntegrityError("INVENTORY_DOCUMENT_MISMATCH")
    if inventory.split == "val" and (
        inventory.test_access_event_sha256 is not None
        or document.get("test_access") is not None
    ):
        raise RunIntegrityError("VAL_TEST_ACCESS_CONFLICT")
    if inventory.split == "test":
        _require_sha(
            inventory.test_access_event_sha256,
            "TEST_ACCESS_EVENT_REQUIRED",
        )
        try:
            _validate_persisted_access(
                document.get("test_access"),
                inventory.test_access_event_sha256,
                inventory.access_log_path,
            )
        except DatasetVerificationError as error:
            raise RunIntegrityError("INVENTORY_ACCESS_CHAIN_INVALID") from error
    return document


def _verify_threshold_lock_chain(spec: RunSpec) -> ThresholdLock:
    path = spec.threshold_lock_path
    if path is None:
        raise RunIntegrityError("LOCKED_RUN_REQUIRES_THRESHOLD_LOCK_PATH")
    try:
        lock = verify_threshold_lock(path)
    except CalibrationError as error:
        raise RunIntegrityError("THRESHOLD_LOCK_INVALID") from error
    if lock.lock_sha256 != spec.threshold_lock_sha256:
        raise RunIntegrityError("THRESHOLD_LOCK_SHA256_MISMATCH")
    if lock.model != spec.model:
        raise RunIntegrityError("THRESHOLD_LOCK_MODEL_MISMATCH")
    if not lock.formal or dict(lock.platform_sample_counts) != {
        "macos": 200,
        "linux": 200,
    }:
        raise RunIntegrityError("THRESHOLD_LOCK_NOT_FORMAL")
    if lock.source_commit != spec.source_commit:
        raise RunIntegrityError("THRESHOLD_LOCK_SOURCE_MISMATCH")
    root = Path(spec.inventory.dataset_root).resolve(strict=True)
    document, _ = _read_canonical_json(
        root / "inventory.json", "INVENTORY_CANONICAL_INVALID"
    )
    test_access = document.get("test_access")
    if not isinstance(test_access, Mapping):
        raise RunIntegrityError("LOCKED_RUN_REQUIRES_TEST_ACCESS")
    registered = test_access.get("threshold_lock_sha256s")
    if (
        not isinstance(registered, list)
        or spec.threshold_lock_sha256 not in registered
    ):
        raise RunIntegrityError("THRESHOLD_LOCK_NOT_REGISTERED")
    granted_at = test_access.get("granted_at")
    if not isinstance(granted_at, str):
        raise RunIntegrityError("INVENTORY_ACCESS_CHAIN_INVALID")
    try:
        lock_mtime = path.stat().st_mtime
        access_time = datetime.fromisoformat(granted_at).timestamp()
    except (OSError, ValueError) as error:
        raise RunIntegrityError("THRESHOLD_LOCK_TIME_INVALID") from error
    if lock_mtime > access_time:
        raise RunIntegrityError("THRESHOLD_LOCK_POSTDATES_TEST_ACCESS")
    return lock


def _read_verified_image(
    inventory: DatasetInventory,
    sample: DatasetSampleRef,
    *,
    pinned_root: _PinnedDirectory | None = None,
) -> tuple[bytes, Path]:
    root = Path(os.path.abspath(inventory.dataset_root))
    path = root.joinpath(*PurePosixPath(sample.image_relpath).parts)
    if pinned_root is None:
        root = root.resolve(strict=True)
        path = _safe_relative_path(root, sample.image_relpath, "INPUT_IMAGE_INVALID")
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise RunIntegrityError("INPUT_IMAGE_UNREADABLE") from error
    else:
        if pinned_root.path != Path(os.path.realpath(root)):
            raise RunIntegrityError("INVENTORY_DATASET_ROOT_INVALID")
        root = pinned_root.path
        path = root.joinpath(*PurePosixPath(sample.image_relpath).parts)
        try:
            payload = pinned_root.read_file(sample.image_relpath)
        except _PinnedFileError as error:
            raise RunIntegrityError("RUN_EVIDENCE_FILE_UNSAFE") from error
    if _sha256(payload) != sample.image_sha256:
        raise RunIntegrityError("INPUT_IMAGE_SHA256_CHANGED")
    return payload, path


def _verify_current_images(
    inventory: DatasetInventory,
    *,
    pinned_root: _PinnedDirectory | None = None,
) -> None:
    for sample in inventory.samples:
        _read_verified_image(inventory, sample, pinned_root=pinned_root)


def _load_frame(inventory: DatasetInventory, sample: DatasetSampleRef) -> DetectionFrame:
    payload, _ = _read_verified_image(inventory, sample)
    try:
        with Image.open(BytesIO(payload)) as image:
            rgb8 = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (OSError, ValueError) as error:
        raise RunIntegrityError("INPUT_IMAGE_DECODE_FAILED") from error
    return DetectionFrame(
        rgb8=rgb8,
        source_stamp_ns=sample.formal_sample_index + 1,
        source_frame_id=sample.image_relpath,
    )


def _sanitize_summary(error: BaseException) -> str:
    raw = f"{type(error).__name__}: {error}"
    single_line = " ".join(raw.replace("\x00", " ").split())
    redacted = _SENSITIVE.sub(lambda match: f"{match.group(1)}=<redacted>", single_line)
    redacted = _ABSOLUTE_PATH.sub("<path>", redacted)
    if not redacted:
        redacted = type(error).__name__
    return redacted[:240]


def _classify_error(error: BaseException) -> _ClassifiedError:
    name = type(error).__name__.lower()
    message = str(error).lower()
    if isinstance(error, TimeoutError) or "timeout" in name or "timed out" in message:
        kind = "TIMEOUT"
    elif (
        isinstance(error, MemoryError)
        or "outofmemory" in name
        or "out of memory" in message
        or re.search(r"\boom\b", message) is not None
    ):
        kind = "OOM"
    elif any(token in name or token in message for token in ("synchron", "device sync")):
        kind = "SYNC"
    elif isinstance(error, (TypeError, ValueError, json.JSONDecodeError)) or any(
        token in message
        for token in ("schema", "contract", "malformed", "result_invalid")
    ):
        kind = "SCHEMA"
    else:
        kind = "MODEL"
    return _ClassifiedError(
        error_type=kind,
        summary=_sanitize_summary(error),
        timed_out=kind == "TIMEOUT",
        oom=kind == "OOM",
    )


def _fatal_error_code(error: BaseException) -> str | None:
    if isinstance(error, ResourceSamplingError):
        return "RESOURCE_EVIDENCE_FAILED"
    if isinstance(error, _ResourceStreamValidationError):
        return str(error)
    if isinstance(error, _ThermalValidationError):
        return str(error)
    return None


def _decision_from_candidates(
    candidates: tuple[RawCandidate, ...],
) -> tuple[DecisionOutput, str | None, str | None]:
    if not candidates:
        return DecisionOutput.NOT_FOUND, None, "TARGET_NOT_FOUND"
    if len(candidates) == 1:
        return DecisionOutput.UNIQUE, candidates[0].candidate_id, None
    return DecisionOutput.AMBIGUOUS, None, "TARGET_AMBIGUOUS"


def _validate_resource_stream(spec: RunSpec, result: RawDetectionResult) -> None:
    if not result.resource_samples:
        raise _ResourceStreamValidationError("RESOURCE_STREAM_EMPTY")
    limit = spec.max_gpu_temperature_celsius
    if limit is None:
        return
    for sample in result.resource_samples:
        temperature = sample.gpu_temperature_celsius
        if temperature is not None and temperature > limit:
            raise _ThermalValidationError("THERMAL_LIMIT_EXCEEDED")


def _validate_raw_result(spec: RunSpec, result: RawDetectionResult) -> None:
    if not isinstance(result, RawDetectionResult):
        raise _FatalRunError("RAW_RESULT_SCHEMA_INVALID")
    if result.model_id != model_id_for_name(spec.model):
        raise _FatalRunError("MODEL_IDENTITY_MISMATCH")
    if result.runtime_device != spec.device:
        raise _FatalRunError("DEVICE_MISMATCH")
    if result.dtype != spec.dtype:
        raise _FatalRunError("NON_FP32_RUNTIME")
    if result.collection_mode is not spec.collection_mode:
        raise _FatalRunError("COLLECTION_MODE_MISMATCH")
    if result.fallback_used:
        raise _FatalRunError("FALLBACK_USED")
    _validate_resource_stream(spec, result)


def _weights_sha(adapter: object, model: str) -> str:
    names = (
        ("weights_sha256", "_weights_sha256")
        if model == "yolo_seg"
        else ("manifest_sha256", "_manifest_sha256")
    )
    for name in names:
        value = getattr(adapter, name, None)
        if isinstance(value, str) and _SHA256.fullmatch(value) is not None:
            return value
    raise RunIntegrityError("RUNTIME_WEIGHTS_PROVENANCE_UNAVAILABLE")


def _runtime_provenance(
    spec: RunSpec, adapter: object
) -> RuntimeProvenance:
    provenance = spec.runtime_provenance
    if not isinstance(provenance, RuntimeProvenance):
        raise RunIntegrityError("RUNTIME_PROVENANCE_REQUIRED")
    if provenance.runtime_device != spec.device:
        raise RunIntegrityError("RUNTIME_PROVENANCE_DEVICE_MISMATCH")
    if provenance.weights_sha256 != _weights_sha(adapter, spec.model):
        raise RunIntegrityError("RUNTIME_WEIGHTS_PROVENANCE_MISMATCH")
    return provenance
