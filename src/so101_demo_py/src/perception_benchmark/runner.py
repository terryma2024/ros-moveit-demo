"""Fail-closed, resumable execution for perception benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal

import numpy as np
from PIL import Image
from so101_demo.core.detection import DetectionCandidate, DetectionFrame
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    ProductionObservation,
    RawDetectionResult,
    RawDetectorAdapter,
    ResourceSamplingError,
)
from so101_demo.perception_benchmark.calibration import (
    CalibrationError,
    ThresholdLock,
    verify_threshold_lock,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    decode_mask_rle,
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
    RunStatus,
    RuntimeProvenance,
    model_id_for_name,
)
from so101_demo.perception_benchmark.dataset import (
    DatasetInventory,
    DatasetSampleRef,
    DatasetVerificationError,
    _PinnedDirectory,
    _PinnedFileError,
    _require_inventory_capability,
    _validate_persisted_access,
)
from so101_demo.perception_benchmark.timing import (
    PhaseTimingBreakdown,
    ResourceSample,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_RECORD_NAME = re.compile(r"^(\d{6})\.json$")
_CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SENSITIVE = re.compile(
    r"(?i)(api[_-]?(?:key|token)|access[_-]?token|token|password|secret)"
    r"\s*[:=]\s*\S+"
)
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s:]+/?)+")
_RAW_RUN_KINDS = {
    RunKind.NON_FORMAL_DRY_RUN,
    RunKind.VAL_RAW,
    RunKind.TEST_RAW_FROZEN,
    RunKind.ORACLE_DIAGNOSTIC,
}
_OBSERVED_RUN_KINDS = {
    RunKind.TEST_PRODUCTION,
    RunKind.TEST_CALIBRATED,
    RunKind.TEST_CHARACTERIZATION,
}
_CANDIDATE_KEYS = {
    "candidate_id",
    "label",
    "bbox_xyxy",
    "mask",
    "ranking_score",
    "ranking_score_source",
    "class_confidence",
    "grounding_box_score",
    "grounding_text_score",
    "sam_quality",
}
_MASK_KEYS = {
    "relative_path",
    "sha256",
    "pixel_count",
    "image_width",
    "image_height",
}
_RUNTIME_PROVENANCE_KEYS = {
    "runtime_device",
    "runtime_name",
    "runtime_version",
    "weights_sha256",
    "environment",
}
_PHASE_TIMING_KEYS = {"grounding_ms", "sam_ms", "selector_ms"}
_TIMING_BREAKDOWN_KEYS = {
    "preprocess_ms",
    "dino_or_yolo_ms",
    "sam_ms",
    "postprocess_ms",
    "selector_ms",
    "total_ms",
}
_RESOURCE_SAMPLE_KEYS = {item.name for item in fields(ResourceSample)}
_RECORD_DOCUMENT_KEYS = {item.name for item in fields(PredictionRecord)} | {
    "platform",
    "model",
    "device",
    "dtype",
    "source_commit",
    "inventory_sha256",
    "collection_mode",
    "max_gpu_temperature_celsius",
    "timing_breakdown",
    "resource_samples",
    "irreversible_limits",
    "previous_record_sha256",
}


class RunIntegrityError(ValueError):
    """A stable fail-closed benchmark run integrity error."""


class _FatalRunError(RunIntegrityError):
    pass


class _ResourceStreamValidationError(_FatalRunError):
    pass


class _ThermalValidationError(_FatalRunError):
    pass


@dataclass(frozen=True, slots=True)
class RunEvidenceExpectation:
    """External anchors required to trust one persisted terminal run."""

    run_id: str
    run_kind: RunKind
    platform: Literal["macos", "linux"]
    model: Literal["yolo_seg", "grounded_sam"]
    device: Literal["mps", "cuda"]
    dtype: Literal["float32"]
    source_commit: str
    config_sha256: str
    threshold_lock_sha256: str | None
    model_id: str
    weights_sha256: str
    runtime_name: str
    runtime_version: str
    runtime_environment: Mapping[str, str]
    max_gpu_temperature_celsius: float | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "run_kind", RunKind(self.run_kind))
        except ValueError as error:
            raise ValueError("run_kind is unsupported") from error
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be non-empty")
        if self.platform not in {"macos", "linux"}:
            raise ValueError("platform is unsupported")
        if self.model not in {"yolo_seg", "grounded_sam"}:
            raise ValueError("model is unsupported")
        if self.device not in {"mps", "cuda"}:
            raise ValueError("device is unsupported")
        if self.dtype != "float32":
            raise ValueError("dtype must be float32")
        if _SOURCE_COMMIT.fullmatch(self.source_commit) is None:
            raise ValueError("source_commit must be a lowercase Git commit")
        for name in ("config_sha256", "weights_sha256"):
            if _SHA256.fullmatch(str(getattr(self, name))) is None:
                raise ValueError(f"{name} must be a lowercase SHA256 digest")
        if self.threshold_lock_sha256 is not None and _SHA256.fullmatch(
            self.threshold_lock_sha256
        ) is None:
            raise ValueError("threshold_lock_sha256 must be null or a SHA256 digest")
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be non-empty")
        for name in ("runtime_name", "runtime_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.runtime_environment, Mapping):
            raise ValueError("runtime_environment must be a mapping")
        environment = dict(self.runtime_environment)
        if not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            and value
            for key, value in environment.items()
        ):
            raise ValueError("runtime_environment must map non-empty strings")
        object.__setattr__(
            self, "runtime_environment", MappingProxyType(environment)
        )
        if self.max_gpu_temperature_celsius is not None and (
            isinstance(self.max_gpu_temperature_celsius, bool)
            or not isinstance(self.max_gpu_temperature_celsius, (int, float))
            or not math.isfinite(float(self.max_gpu_temperature_celsius))
            or float(self.max_gpu_temperature_celsius) <= 0.0
        ):
            raise ValueError("max_gpu_temperature_celsius must be null or positive")


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_id: str
    run_kind: RunKind
    platform: Literal["macos", "linux"]
    model: Literal["yolo_seg", "grounded_sam"]
    device: Literal["mps", "cuda"]
    dtype: Literal["float32"]
    inventory: DatasetInventory
    config_sha256: str
    threshold_lock_sha256: str | None
    source_commit: str
    output_root: Path
    collection_mode: CollectionMode
    threshold_lock_path: Path | None = None
    max_gpu_temperature_celsius: float | None = None
    production_observer: Callable[[DetectionFrame], ProductionObservation] | None = None
    runtime_provenance: RuntimeProvenance | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "run_kind", RunKind(self.run_kind))
            object.__setattr__(
                self, "collection_mode", CollectionMode(self.collection_mode)
            )
        except ValueError as error:
            raise ValueError("run kind or collection mode is unsupported") from error
        object.__setattr__(self, "output_root", Path(self.output_root))
        if self.threshold_lock_path is not None:
            object.__setattr__(
                self, "threshold_lock_path", Path(self.threshold_lock_path)
            )


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    run_id: str
    config_sha: str
    source_commit: str
    inventory_sha256: str
    records_dir: Path
    last_formal_sample_index: int
    last_record_sha256: str
    platform: str | None = None
    model: str | None = None
    model_id: str | None = None
    weights_sha256: str | None = None
    device: str | None = None
    dtype: str | None = None
    run_kind: RunKind | None = None
    threshold_lock_sha256: str | None = None
    collection_mode: CollectionMode | None = None
    runtime_name: str | None = None
    runtime_version: str | None = None
    runtime_environment: Mapping[str, str] | None = None
    max_gpu_temperature_celsius: float | None = None
    record_count: int = 0
    error_count: int = 0
    record_inventory_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records_dir", Path(self.records_dir))
        if self.run_kind is not None:
            try:
                object.__setattr__(self, "run_kind", RunKind(self.run_kind))
            except ValueError as error:
                raise ValueError("checkpoint run_kind is unsupported") from error
        if self.collection_mode is not None:
            try:
                object.__setattr__(
                    self,
                    "collection_mode",
                    CollectionMode(self.collection_mode),
                )
            except ValueError as error:
                raise ValueError("checkpoint collection_mode is unsupported") from error
        if self.runtime_environment is not None:
            object.__setattr__(
                self, "runtime_environment", dict(self.runtime_environment)
            )


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    run_kind: RunKind
    status: RunStatus
    platform: str
    model: str
    device: str
    dtype: str
    source_commit: str
    inventory_sha256: str
    config_sha256: str
    threshold_lock_sha256: str | None
    collection_mode: CollectionMode
    model_id: str
    weights_sha256: str
    runtime_name: str
    runtime_version: str
    runtime_environment: Mapping[str, str]
    max_gpu_temperature_celsius: float | None
    record_count: int
    error_count: int
    record_inventory_sha256: str
    record_chain_head_sha256: str | None
    started_at: str
    ended_at: str | None
    invalid_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_kind", RunKind(self.run_kind))
        object.__setattr__(self, "status", RunStatus(self.status))
        object.__setattr__(
            self, "collection_mode", CollectionMode(self.collection_mode)
        )
        object.__setattr__(
            self,
            "runtime_environment",
            MappingProxyType(dict(self.runtime_environment)),
        )


@dataclass(frozen=True, slots=True)
class LoadedRunEvidence:
    """Immutable typed and extended documents from one verified terminal run."""

    manifest: RunManifest
    evidence_root: Path
    records: tuple[PredictionRecord, ...]
    extended_record_documents: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_root", Path(self.evidence_root))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(
            self,
            "extended_record_documents",
            tuple(_freeze_document(item) for item in self.extended_record_documents),
        )


@dataclass(frozen=True, slots=True)
class _ClassifiedError:
    error_type: str
    summary: str
    timed_out: bool
    oom: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RunIntegrityError(code)
    return value


def _jsonable(value: object) -> object:
    """Explicitly serialize the closed evidence vocabulary."""

    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise RunIntegrityError("NONFINITE_DOCUMENT_VALUE")
        return format(value, "f")
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _jsonable(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RunIntegrityError("DOCUMENT_MAPPING_KEY_INVALID")
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RunIntegrityError("NONFINITE_DOCUMENT_VALUE")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise RunIntegrityError("DOCUMENT_VALUE_UNSUPPORTED")


def _freeze_document(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_document(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_document(item) for item in value)
    return value


def _document_bytes(document: object) -> bytes:
    return canonical_json_bytes(_jsonable(document))


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags)


def _fsync_directory(path: Path) -> None:
    descriptor = _open_directory(path)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_directory(path: Path, code: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise RunIntegrityError(code)
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise RunIntegrityError(code) from error


def _create_directory(path: Path, root: Path) -> None:
    parent = _require_directory(path.parent, "OUTPUT_DIRECTORY_INVALID")
    if not parent.is_relative_to(root) and parent != root:
        raise RunIntegrityError("OUTPUT_DIRECTORY_ESCAPE")
    descriptor = _open_directory(parent)
    try:
        try:
            os.mkdir(path.name, 0o700, dir_fd=descriptor)
        except FileExistsError:
            pass
        os.fsync(descriptor)
    except OSError as error:
        raise RunIntegrityError("OUTPUT_DIRECTORY_CREATE_FAILED") from error
    finally:
        os.close(descriptor)
    _require_directory(path, "OUTPUT_DIRECTORY_INVALID")
    _fsync_directory(path)


def _atomic_write_new_json(path: Path, document: object) -> str:
    """Publish a new canonical record atomically without overwrite."""

    parent = _require_directory(path.parent, "RECORDS_DIRECTORY_INVALID")
    if path.exists() or path.is_symlink():
        raise RunIntegrityError("RECORD_ALREADY_EXISTS")
    payload = _document_bytes(document)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        temporary = None
        _fsync_directory(parent)
    except FileExistsError as error:
        raise RunIntegrityError("RECORD_ALREADY_EXISTS") from error
    except OSError as error:
        raise RunIntegrityError("RECORD_WRITE_FAILED") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return _sha256(payload)


def _atomic_write_new_bytes(path: Path, payload: bytes, code: str) -> None:
    parent = _require_directory(path.parent, "MASK_DIRECTORY_INVALID")
    if path.exists() or path.is_symlink():
        raise RunIntegrityError("MASK_ALREADY_EXISTS")
    descriptor = _open_directory(parent)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(path.name, flags, 0o600, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(descriptor)
    except FileExistsError as error:
        raise RunIntegrityError("MASK_ALREADY_EXISTS") from error
    except OSError as error:
        raise RunIntegrityError(code) from error
    finally:
        os.close(descriptor)
    _fsync_directory(parent)


def _atomic_replace_json(path: Path, document: object, code: str) -> str:
    parent = _require_directory(path.parent, "OUTPUT_DIRECTORY_INVALID")
    if path.is_symlink():
        raise RunIntegrityError(code)
    payload = _document_bytes(document)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    except OSError as error:
        raise RunIntegrityError(code) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return _sha256(payload)


def _safe_relative_path(root: Path, relative_path: str, code: str) -> Path:
    if not isinstance(relative_path, str) or "\\" in relative_path:
        raise RunIntegrityError(code)
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RunIntegrityError(code)
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise RunIntegrityError(code)
    target = root.joinpath(*relative.parts)
    if target.is_symlink() or not target.is_file():
        raise RunIntegrityError(code)
    try:
        target.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise RunIntegrityError(code) from error
    return target


def _create_new_directory(path: Path, root: Path, code: str) -> Path:
    if path.exists() or path.is_symlink():
        raise RunIntegrityError(code)
    parent = _require_directory(path.parent, "MASK_DIRECTORY_INVALID")
    if parent != root and not parent.is_relative_to(root):
        raise RunIntegrityError("OUTPUT_DIRECTORY_ESCAPE")
    descriptor = _open_directory(parent)
    try:
        os.mkdir(path.name, 0o700, dir_fd=descriptor)
        os.fsync(descriptor)
    except FileExistsError as error:
        raise RunIntegrityError(code) from error
    except OSError as error:
        raise RunIntegrityError("MASK_DIRECTORY_CREATE_FAILED") from error
    finally:
        os.close(descriptor)
    return _require_directory(path, "MASK_DIRECTORY_INVALID")


def _decode_canonical_json(
    payload: bytes, code: str
) -> tuple[dict[str, object], bytes]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunIntegrityError(code) from error
    if not isinstance(document, dict):
        raise RunIntegrityError(code)
    try:
        canonical = canonical_json_bytes(document)
    except (TypeError, ValueError) as error:
        raise RunIntegrityError(code) from error
    if canonical != payload:
        raise RunIntegrityError(code)
    return document, payload


def _read_canonical_json(path: Path, code: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink() or not path.is_file():
        raise RunIntegrityError(code)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise RunIntegrityError(code) from error
    return _decode_canonical_json(payload, code)


def _read_pinned_canonical_json(
    pinned_root: _PinnedDirectory,
    relative_path: str,
    code: str,
) -> tuple[dict[str, object], bytes]:
    try:
        payload = pinned_root.read_file(relative_path)
    except _PinnedFileError as error:
        raise RunIntegrityError("RUN_EVIDENCE_FILE_UNSAFE") from error
    return _decode_canonical_json(payload, code)


def _sample_document_matches(
    document: object, sample: DatasetSampleRef
) -> bool:
    if not isinstance(document, Mapping):
        return False
    expected = {
        "formal_sample_index": sample.formal_sample_index,
        "split": sample.split,
        "scenario": sample.scenario,
        "image_relpath": sample.image_relpath,
        "label_relpath": sample.label_relpath,
        "truth_relpath": sample.truth_relpath,
        "image_sha256": sample.image_sha256,
        "truth_count": sample.truth_count,
    }
    return all(document.get(name) == value for name, value in expected.items())


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
        _, payload = _read_verified_adapter_mask(candidate.mask, source_root)
        relative = f"masks/{formal_sample_index:06d}/{candidate.candidate_id}.rle.json"
        target = run_root / relative
        _atomic_write_new_bytes(target, payload, "MASK_WRITE_FAILED")
        published.append(
            replace(
                candidate,
                mask=replace(candidate.mask, relative_path=relative),
            )
        )
    return tuple(published)


def _mask_sha256(value: np.ndarray) -> str:
    return _sha256(value.astype(np.uint8, copy=False).tobytes(order="C"))


def _matches_production_candidate(
    spec: RunSpec,
    raw: RawCandidate,
    observed: DetectionCandidate,
    raw_mask_sha256: str,
) -> bool:
    if (
        observed.class_id != raw.label
        or tuple(observed.bbox_xyxy) != raw.bbox_xyxy
        or _mask_sha256(observed.mask) != raw_mask_sha256
        or observed.confidence != raw.ranking_score
    ):
        return False
    if spec.model == "yolo_seg":
        return (
            raw.class_confidence == observed.confidence
            and observed.segmentation_quality is None
        )
    return (
        raw.grounding_box_score == observed.confidence
        and raw.sam_quality == observed.segmentation_quality
    )


def _reconcile_production_candidates(
    spec: RunSpec,
    frame: DetectionFrame,
    result: RawDetectionResult,
    observation: ProductionObservation,
    provenance: RuntimeProvenance,
    source_root: Path,
) -> tuple[tuple[RawCandidate, ...], str | None]:
    batch = observation.batch
    if batch is None:
        if observation.decision is not DecisionOutput.ERROR:
            raise RunIntegrityError("PRODUCTION_BATCH_REQUIRED")
        return result.raw_candidates, None
    if (
        batch.model_id != result.model_id
        or batch.weights_sha256 != provenance.weights_sha256
        or batch.runtime_device != spec.device
        or (batch.image_width, batch.image_height)
        != (frame.image_width, frame.image_height)
    ):
        raise RunIntegrityError("PRODUCTION_BATCH_IDENTITY_MISMATCH")
    raw_mask_shas = {
        raw.candidate_id: _mask_sha256(
            _read_verified_adapter_mask(raw.mask, source_root)[0]
        )
        for raw in result.raw_candidates
    }
    available = {raw.candidate_id: raw for raw in result.raw_candidates}
    mapped: list[RawCandidate] = []
    ids: dict[str, str] = {}
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
                raw_mask_shas[raw.candidate_id],
            )
        ]
        if len(matches) != 1:
            raise RunIntegrityError("PRODUCTION_CANDIDATE_MAPPING_INVALID")
        raw = matches[0]
        available.pop(raw.candidate_id)
        mapped.append(raw)
        ids[observed.instance_id] = raw.candidate_id
    selected = None
    if observation.selected_candidate_id is not None:
        selected = ids.get(observation.selected_candidate_id)
        if selected is None:
            raise RunIntegrityError("PRODUCTION_SELECTED_MAPPING_INVALID")
    return tuple(mapped), selected


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
    selector_ms = result.phase_timings.selector_ms
    if observation is None:
        decision, selected, rejection = _decision_from_candidates(candidates)
        error_type = None
        error_summary = None
        record_status = RecordStatus.OK
    else:
        decision = observation.decision
        candidates, selected = _reconcile_production_candidates(
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
    return record, _record_document(
        record,
        spec,
        timings=result.phase_timings,
        resources=result.resource_samples,
        irreversible_limits=result.irreversible_limits,
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


def _load_verified_resume_evidence(
    checkpoint: RunCheckpoint,
    inventory: DatasetInventory,
    config_sha: str,
    source_commit: str,
    *,
    pinned_root: _PinnedDirectory | None = None,
    pinned_inventory_root: _PinnedDirectory | None = None,
) -> tuple[tuple[PredictionRecord, ...], tuple[Mapping[str, object], ...]]:
    """Verify and return the exact durable record prefix."""

    if not isinstance(checkpoint, RunCheckpoint):
        raise RunIntegrityError("CHECKPOINT_TYPE_INVALID")
    if checkpoint.config_sha != config_sha or checkpoint.source_commit != source_commit:
        raise RunIntegrityError("RESUME_PROVENANCE_CHANGED")
    if checkpoint.inventory_sha256 != inventory.inventory_sha256:
        raise RunIntegrityError("RESUME_INVENTORY_CHANGED")
    _verify_inventory(inventory, pinned_root=pinned_inventory_root)
    _verify_current_images(inventory, pinned_root=pinned_inventory_root)
    paths: list[tuple[int, Path | str]] = []
    if pinned_root is None:
        records_dir = _require_directory(
            checkpoint.records_dir, "RECORDS_DIRECTORY_INVALID"
        )
        if records_dir != checkpoint.records_dir.resolve(strict=True):
            raise RunIntegrityError("RECORDS_DIRECTORY_CHANGED")
        evidence_root = records_dir.parent
        for path in records_dir.iterdir():
            match = _RECORD_NAME.fullmatch(path.name)
            if match is None or path.is_symlink() or not path.is_file():
                raise RunIntegrityError("RECORDS_DIRECTORY_UNEXPECTED_ENTRY")
            paths.append((int(match.group(1)), path))
    else:
        try:
            all_files, all_directories = pinned_root.tree()
        except _PinnedFileError as error:
            raise RunIntegrityError("RUN_EVIDENCE_FILE_UNSAFE") from error
        record_directories = {
            path for path in all_directories if path.startswith("records")
        }
        if record_directories != {"records"}:
            raise RunIntegrityError("RECORDS_DIRECTORY_UNEXPECTED_ENTRY")
        evidence_root = pinned_root.path
        for relative_path in all_files:
            parts = PurePosixPath(relative_path).parts
            if not parts or parts[0] != "records":
                continue
            if len(parts) != 2:
                raise RunIntegrityError("RECORDS_DIRECTORY_UNEXPECTED_ENTRY")
            match = _RECORD_NAME.fullmatch(parts[1])
            if match is None:
                raise RunIntegrityError("RECORDS_DIRECTORY_UNEXPECTED_ENTRY")
            paths.append((int(match.group(1)), relative_path))
    paths.sort(key=lambda item: item[0])
    indices = [index for index, _ in paths]
    if indices != list(range(len(indices))) or len(indices) > len(inventory.samples):
        raise RunIntegrityError("NON_CONTIGUOUS_RECORDS")
    expected_identity = _checkpoint_identity(checkpoint)
    record_shas: list[str] = []
    previous_record_sha256: str | None = None
    error_count = 0
    expected_mask_paths: set[str] = set()
    verified_records: list[PredictionRecord] = []
    verified_documents: list[Mapping[str, object]] = []
    for index, path in paths:
        if pinned_root is None:
            if not isinstance(path, Path):
                raise RunIntegrityError("RECORDS_DIRECTORY_UNEXPECTED_ENTRY")
            document, payload = _read_canonical_json(
                path, "RECORD_CANONICAL_INVALID"
            )
            persisted_index = int(path.stem)
        else:
            if not isinstance(path, str):
                raise RunIntegrityError("RECORDS_DIRECTORY_UNEXPECTED_ENTRY")
            document, payload = _read_pinned_canonical_json(
                pinned_root, path, "RECORD_CANONICAL_INVALID"
            )
            persisted_index = int(PurePosixPath(path).stem)
        record_sha = _sha256(payload)
        record_shas.append(record_sha)
        if (
            "previous_record_sha256" not in document
            or document.get("previous_record_sha256") != previous_record_sha256
        ):
            raise RunIntegrityError("RECORD_HASH_CHAIN_INVALID")
        record = _record_from_document(document)
        _verify_extended_record(document)
        if document.get("max_gpu_temperature_celsius") != (
            checkpoint.max_gpu_temperature_celsius
        ):
            raise RunIntegrityError("RESUME_THERMAL_POLICY_CHANGED")
        sample = inventory.samples[index]
        if (
            record.formal_sample_index != index
            or record.formal_sample_index != persisted_index
            or record.split != sample.split
            or record.scenario != sample.scenario
            or record.image_relpath != sample.image_relpath
            or record.image_sha256 != sample.image_sha256
        ):
            raise RunIntegrityError("RECORD_SAMPLE_IDENTITY_MISMATCH")
        if any(document.get(name) != value for name, value in expected_identity.items()):
            raise RunIntegrityError("RESUME_RECORD_IDENTITY_CHANGED")
        if (
            record.model_id != checkpoint.model_id
            or record.runtime_provenance.weights_sha256
            != checkpoint.weights_sha256
            or record.runtime_provenance.runtime_device != checkpoint.device
            or record.runtime_provenance.runtime_name != checkpoint.runtime_name
            or record.runtime_provenance.runtime_version != checkpoint.runtime_version
            or dict(record.runtime_provenance.environment)
            != dict(checkpoint.runtime_environment or {})
        ):
            raise RunIntegrityError("RESUME_RUNTIME_IDENTITY_CHANGED")
        for candidate in record.raw_candidates:
            _verify_record_mask(
                candidate.mask,
                evidence_root,
                index,
                candidate.candidate_id,
                pinned_root=pinned_root,
            )
            expected_mask_paths.add(candidate.mask.relative_path)
        if record.record_status is RecordStatus.ERROR:
            error_count += 1
        verified_records.append(record)
        verified_documents.append(document)
        previous_record_sha256 = record_sha
    expected_last = len(paths) - 1
    if checkpoint.last_formal_sample_index != expected_last:
        raise RunIntegrityError("CHECKPOINT_RECORD_PREFIX_MISMATCH")
    if expected_last < 0:
        if checkpoint.last_record_sha256 != "0" * 64:
            raise RunIntegrityError("CHECKPOINT_RECORD_SHA256_MISMATCH")
    elif checkpoint.last_record_sha256 != record_shas[-1]:
        raise RunIntegrityError("CHECKPOINT_RECORD_SHA256_MISMATCH")
    digest = _sha256(
        canonical_json_bytes(
            {
                "records": [
                    {"formal_sample_index": index, "sha256": digest}
                    for (index, _), digest in zip(paths, record_shas, strict=True)
                ]
            }
        )
    )
    if (
        checkpoint.record_count != len(paths)
        or checkpoint.error_count != error_count
        or checkpoint.record_inventory_sha256 != digest
    ):
        raise RunIntegrityError("CHECKPOINT_RECORD_INVENTORY_MISMATCH")
    _verify_mask_tree(
        evidence_root, expected_mask_paths, pinned_root=pinned_root
    )
    return (
        tuple(verified_records),
        tuple(_freeze_document(document) for document in verified_documents),
    )


def verify_resume(
    checkpoint: RunCheckpoint,
    inventory: DatasetInventory,
    config_sha: str,
    source_commit: str,
) -> int:
    """Return the exact verified prefix length or reject the entire resume."""

    records, _ = _load_verified_resume_evidence(
        checkpoint, inventory, config_sha, source_commit
    )
    return len(records)


def _read_checkpoint(path: Path) -> RunCheckpoint:
    document, _ = _read_canonical_json(path, "CHECKPOINT_CANONICAL_INVALID")
    return _checkpoint_from_document(document)


def _checkpoint_from_document(document: Mapping[str, object]) -> RunCheckpoint:
    if set(document) != {item.name for item in fields(RunCheckpoint)}:
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    if (
        not isinstance(document.get("records_dir"), str)
        or not document["records_dir"]
        or document.get("run_kind")
        not in {item.value for item in RunKind}
        or document.get("collection_mode")
        not in {item.value for item in CollectionMode}
        or not isinstance(document.get("runtime_environment"), Mapping)
    ):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    try:
        checkpoint = RunCheckpoint(**document)
    except (TypeError, ValueError) as error:
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID") from error
    _verify_checkpoint_schema(checkpoint)
    return checkpoint


def _verify_checkpoint_schema(checkpoint: RunCheckpoint) -> None:
    string_fields = (
        "run_id",
        "platform",
        "model",
        "model_id",
        "weights_sha256",
        "device",
        "dtype",
        "source_commit",
        "config_sha",
        "inventory_sha256",
        "last_record_sha256",
        "record_inventory_sha256",
        "runtime_name",
        "runtime_version",
    )
    if any(
        not isinstance(getattr(checkpoint, name), str)
        or not getattr(checkpoint, name)
        for name in string_fields
    ):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    if (
        checkpoint.platform not in {"macos", "linux"}
        or checkpoint.model not in {"yolo_seg", "grounded_sam"}
        or checkpoint.device not in {"mps", "cuda"}
        or (checkpoint.platform, checkpoint.device)
        not in {("macos", "mps"), ("linux", "cuda")}
        or checkpoint.dtype != "float32"
        or not isinstance(checkpoint.run_kind, RunKind)
        or not isinstance(checkpoint.collection_mode, CollectionMode)
        or _SOURCE_COMMIT.fullmatch(str(checkpoint.source_commit)) is None
        or _SHA256.fullmatch(str(checkpoint.config_sha)) is None
        or _SHA256.fullmatch(str(checkpoint.inventory_sha256)) is None
        or _SHA256.fullmatch(str(checkpoint.weights_sha256 or "")) is None
        or _SHA256.fullmatch(str(checkpoint.last_record_sha256)) is None
        or _SHA256.fullmatch(str(checkpoint.record_inventory_sha256 or ""))
        is None
        or (
            checkpoint.threshold_lock_sha256 is not None
            and (
                not isinstance(checkpoint.threshold_lock_sha256, str)
                or _SHA256.fullmatch(checkpoint.threshold_lock_sha256) is None
            )
        )
        or not checkpoint.records_dir.is_absolute()
    ):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    locked = checkpoint.run_kind.name.startswith("TEST_") or (
        checkpoint.run_kind is RunKind.ORACLE_DIAGNOSTIC
    )
    if locked != (checkpoint.threshold_lock_sha256 is not None):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    if not isinstance(checkpoint.runtime_environment, Mapping) or not all(
        isinstance(key, str)
        and key
        and isinstance(value, str)
        and value
        for key, value in checkpoint.runtime_environment.items()
    ):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    if (
        type(checkpoint.last_formal_sample_index) is not int
        or type(checkpoint.record_count) is not int
        or type(checkpoint.error_count) is not int
        or checkpoint.record_count < 0
        or checkpoint.record_count > 200
        or checkpoint.error_count < 0
        or checkpoint.error_count > checkpoint.record_count
        or checkpoint.last_formal_sample_index != checkpoint.record_count - 1
        or (
            checkpoint.record_count == 0
            and checkpoint.last_record_sha256 != "0" * 64
        )
    ):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")
    if checkpoint.max_gpu_temperature_celsius is not None and (
        isinstance(checkpoint.max_gpu_temperature_celsius, bool)
        or not isinstance(checkpoint.max_gpu_temperature_celsius, (int, float))
        or not math.isfinite(float(checkpoint.max_gpu_temperature_celsius))
        or float(checkpoint.max_gpu_temperature_celsius) <= 0.0
    ):
        raise RunIntegrityError("CHECKPOINT_SCHEMA_INVALID")


def _manifest_from_document(document: Mapping[str, object]) -> RunManifest:
    if set(document) != {item.name for item in fields(RunManifest)}:
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    if (
        document.get("run_kind") not in {item.value for item in RunKind}
        or document.get("status") not in {item.value for item in RunStatus}
        or document.get("collection_mode")
        not in {item.value for item in CollectionMode}
        or not isinstance(document.get("runtime_environment"), Mapping)
    ):
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    try:
        return RunManifest(**document)
    except (TypeError, ValueError) as error:
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID") from error


def _canonical_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID") from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.isoformat() != value
    ):
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    return parsed


def _verify_manifest_identity(
    manifest: RunManifest,
    spec: RunSpec,
    provenance: RuntimeProvenance,
    adapter: object,
) -> None:
    _verify_manifest_schema(manifest)
    expected = {
        "run_id": spec.run_id,
        "run_kind": spec.run_kind,
        "platform": spec.platform,
        "model": spec.model,
        "device": spec.device,
        "dtype": spec.dtype,
        "source_commit": spec.source_commit,
        "inventory_sha256": spec.inventory.inventory_sha256,
        "config_sha256": spec.config_sha256,
        "threshold_lock_sha256": spec.threshold_lock_sha256,
        "collection_mode": spec.collection_mode,
        "model_id": str(getattr(adapter, "model_id", "")),
        "weights_sha256": provenance.weights_sha256,
        "runtime_name": provenance.runtime_name,
        "runtime_version": provenance.runtime_version,
        "runtime_environment": dict(provenance.environment),
        "max_gpu_temperature_celsius": spec.max_gpu_temperature_celsius,
    }
    if any(getattr(manifest, name) != value for name, value in expected.items()):
        raise RunIntegrityError("RESUME_MANIFEST_IDENTITY_CHANGED")


def _verify_manifest_schema(manifest: RunManifest) -> None:
    started_at = _canonical_utc_timestamp(manifest.started_at)
    ended_at = (
        None
        if manifest.ended_at is None
        else _canonical_utc_timestamp(manifest.ended_at)
    )
    string_fields = (
        "run_id",
        "platform",
        "model",
        "device",
        "dtype",
        "source_commit",
        "inventory_sha256",
        "config_sha256",
        "model_id",
        "weights_sha256",
        "runtime_name",
        "runtime_version",
        "record_inventory_sha256",
    )
    if any(
        not isinstance(getattr(manifest, name), str)
        or not getattr(manifest, name)
        for name in string_fields
    ):
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    if (
        type(manifest.record_count) is not int
        or type(manifest.error_count) is not int
        or manifest.record_count < 0
        or manifest.record_count > 200
        or manifest.error_count < 0
        or manifest.error_count > manifest.record_count
        or _SHA256.fullmatch(str(manifest.record_inventory_sha256)) is None
        or (manifest.record_count == 0) != (manifest.record_chain_head_sha256 is None)
        or (
            manifest.record_chain_head_sha256 is not None
            and (
                not isinstance(manifest.record_chain_head_sha256, str)
                or _SHA256.fullmatch(manifest.record_chain_head_sha256) is None
            )
        )
    ):
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    if (
        not isinstance(manifest.run_id, str)
        or not manifest.run_id
        or not isinstance(manifest.run_kind, RunKind)
        or not isinstance(manifest.status, RunStatus)
        or not isinstance(manifest.collection_mode, CollectionMode)
        or manifest.platform not in {"macos", "linux"}
        or manifest.model not in {"yolo_seg", "grounded_sam"}
        or manifest.device not in {"mps", "cuda"}
        or manifest.dtype != "float32"
        or _SOURCE_COMMIT.fullmatch(str(manifest.source_commit)) is None
        or _SHA256.fullmatch(str(manifest.inventory_sha256)) is None
        or _SHA256.fullmatch(str(manifest.config_sha256)) is None
        or (
            manifest.threshold_lock_sha256 is not None
            and (
                not isinstance(manifest.threshold_lock_sha256, str)
                or _SHA256.fullmatch(manifest.threshold_lock_sha256) is None
            )
        )
        or not isinstance(manifest.model_id, str)
        or not manifest.model_id
        or _SHA256.fullmatch(str(manifest.weights_sha256)) is None
        or not isinstance(manifest.runtime_name, str)
        or not manifest.runtime_name
        or not isinstance(manifest.runtime_version, str)
        or not manifest.runtime_version
        or not isinstance(manifest.runtime_environment, Mapping)
        or not all(
            isinstance(key, str)
            and key
            and isinstance(value, str)
            and value
            for key, value in manifest.runtime_environment.items()
        )
        or (
            manifest.max_gpu_temperature_celsius is not None
            and (
                isinstance(manifest.max_gpu_temperature_celsius, bool)
                or not isinstance(
                    manifest.max_gpu_temperature_celsius, (int, float)
                )
                or not math.isfinite(
                    float(manifest.max_gpu_temperature_celsius)
                )
                or float(manifest.max_gpu_temperature_celsius) <= 0.0
            )
        )
    ):
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    locked = manifest.run_kind.name.startswith("TEST_") or (
        manifest.run_kind is RunKind.ORACLE_DIAGNOSTIC
    )
    if locked != (manifest.threshold_lock_sha256 is not None):
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    if ended_at is not None and ended_at < started_at:
        raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    if manifest.status is RunStatus.RUNNING:
        if manifest.ended_at is not None or manifest.invalid_reason is not None:
            raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    elif manifest.status is RunStatus.VALID:
        if manifest.ended_at is None or manifest.invalid_reason is not None:
            raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")
    elif manifest.status is RunStatus.INVALID:
        if (
            manifest.ended_at is None
            or not isinstance(manifest.invalid_reason, str)
            or not manifest.invalid_reason
        ):
            raise RunIntegrityError("MANIFEST_SCHEMA_INVALID")


def _record_inventory(records_dir: Path) -> tuple[int, int, str, str | None]:
    if records_dir.is_symlink() or not records_dir.is_dir():
        return 0, 0, _sha256(canonical_json_bytes({"records": []})), None
    rows: list[dict[str, object]] = []
    error_count = 0
    for path in sorted(records_dir.iterdir(), key=lambda item: item.name):
        match = _RECORD_NAME.fullmatch(path.name)
        if match is None or path.is_symlink() or not path.is_file():
            continue
        try:
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            document = None
            payload = b""
        if isinstance(document, Mapping) and document.get("record_status") == "ERROR":
            error_count += 1
        rows.append(
            {
                "formal_sample_index": int(match.group(1)),
                "sha256": _sha256(payload),
            }
        )
    digest = _sha256(canonical_json_bytes({"records": rows}))
    head = None if not rows else str(rows[-1]["sha256"])
    return len(rows), error_count, digest, head


def _verify_manifest_anchor(
    manifest: RunManifest, checkpoint: RunCheckpoint
) -> None:
    if (
        manifest.record_count != checkpoint.record_count
        or manifest.error_count != checkpoint.error_count
        or manifest.record_inventory_sha256
        != checkpoint.record_inventory_sha256
        or manifest.record_chain_head_sha256
        != (
            None if checkpoint.record_count == 0 else checkpoint.last_record_sha256
        )
    ):
        raise RunIntegrityError("RESUME_MANIFEST_ANCHOR_MISMATCH")


def _verify_checkpoint_spec_identity(
    checkpoint: RunCheckpoint,
    spec: RunSpec,
    provenance: RuntimeProvenance,
    adapter: object,
) -> None:
    expected = {
        "run_id": spec.run_id,
        "platform": spec.platform,
        "model": spec.model,
        "model_id": str(getattr(adapter, "model_id")),
        "weights_sha256": provenance.weights_sha256,
        "device": spec.device,
        "dtype": spec.dtype,
        "run_kind": spec.run_kind,
        "threshold_lock_sha256": spec.threshold_lock_sha256,
        "collection_mode": spec.collection_mode,
        "runtime_name": provenance.runtime_name,
        "runtime_version": provenance.runtime_version,
        "runtime_environment": dict(provenance.environment),
        "max_gpu_temperature_celsius": spec.max_gpu_temperature_celsius,
    }
    if any(getattr(checkpoint, name) != value for name, value in expected.items()):
        raise RunIntegrityError("RESUME_SPEC_CHANGED")


def _verify_loaded_expectation(
    manifest: RunManifest,
    checkpoint: RunCheckpoint,
    inventory: DatasetInventory,
    expectation: RunEvidenceExpectation,
    inventory_document: Mapping[str, object],
) -> None:
    if not isinstance(expectation, RunEvidenceExpectation):
        raise RunIntegrityError("RUN_EVIDENCE_EXPECTATION_TYPE_INVALID")
    if expectation.run_kind is RunKind.NON_FORMAL_DRY_RUN:
        raise RunIntegrityError("NON_FORMAL_DRY_RUN_REQUIRES_SEPARATE_CARRIER")
    if (expectation.platform, expectation.device) not in {
        ("macos", "mps"),
        ("linux", "cuda"),
    }:
        raise RunIntegrityError("PLATFORM_DEVICE_MISMATCH")
    try:
        canonical_model_id = model_id_for_name(expectation.model)
    except ValueError as error:
        raise RunIntegrityError("MODEL_IDENTITY_MISMATCH") from error
    if expectation.model_id != canonical_model_id:
        raise RunIntegrityError("MODEL_IDENTITY_MISMATCH")
    locked = expectation.run_kind.name.startswith("TEST_") or (
        expectation.run_kind is RunKind.ORACLE_DIAGNOSTIC
    )
    if locked:
        _require_sha(
            expectation.threshold_lock_sha256,
            "LOCKED_RUN_REQUIRES_THRESHOLD_LOCK",
        )
        if inventory.split != "test":
            raise RunIntegrityError("LOCKED_RUN_REQUIRES_TEST_INVENTORY")
        access = inventory_document.get("test_access")
        registered = (
            access.get("threshold_lock_sha256s")
            if isinstance(access, Mapping)
            else None
        )
        if (
            not isinstance(registered, list)
            or expectation.threshold_lock_sha256 not in registered
        ):
            raise RunIntegrityError("THRESHOLD_LOCK_NOT_REGISTERED")
    elif expectation.threshold_lock_sha256 is not None:
        raise RunIntegrityError("UNLOCKED_RUN_FORBIDS_THRESHOLD_LOCK")
    if expectation.run_kind is RunKind.VAL_RAW and inventory.split != "val":
        raise RunIntegrityError("VAL_RUN_REQUIRES_VAL_INVENTORY")

    required = {
        "run_id": expectation.run_id,
        "run_kind": expectation.run_kind,
        "platform": expectation.platform,
        "model": expectation.model,
        "device": expectation.device,
        "dtype": expectation.dtype,
        "source_commit": expectation.source_commit,
        "inventory_sha256": inventory.inventory_sha256,
        "config_sha256": expectation.config_sha256,
        "threshold_lock_sha256": expectation.threshold_lock_sha256,
        "collection_mode": CollectionMode.LOW_FLOOR,
        "model_id": expectation.model_id,
        "weights_sha256": expectation.weights_sha256,
        "runtime_name": expectation.runtime_name,
        "runtime_version": expectation.runtime_version,
        "max_gpu_temperature_celsius": (
            expectation.max_gpu_temperature_celsius
        ),
    }
    if any(getattr(manifest, name) != value for name, value in required.items()):
        raise RunIntegrityError("RUN_EVIDENCE_EXPECTATION_MISMATCH")
    checkpoint_required = {
        "run_id": expectation.run_id,
        "run_kind": expectation.run_kind,
        "platform": expectation.platform,
        "model": expectation.model,
        "device": expectation.device,
        "dtype": expectation.dtype,
        "source_commit": expectation.source_commit,
        "inventory_sha256": inventory.inventory_sha256,
        "config_sha": expectation.config_sha256,
        "threshold_lock_sha256": expectation.threshold_lock_sha256,
        "collection_mode": CollectionMode.LOW_FLOOR,
        "model_id": expectation.model_id,
        "weights_sha256": expectation.weights_sha256,
        "runtime_name": expectation.runtime_name,
        "runtime_version": expectation.runtime_version,
        "max_gpu_temperature_celsius": (
            expectation.max_gpu_temperature_celsius
        ),
    }
    if any(
        getattr(checkpoint, name) != value
        for name, value in checkpoint_required.items()
    ):
        raise RunIntegrityError("RUN_EVIDENCE_EXPECTATION_MISMATCH")
    if dict(manifest.runtime_environment) != dict(
        expectation.runtime_environment
    ) or dict(checkpoint.runtime_environment or {}) != dict(
        expectation.runtime_environment
    ):
        raise RunIntegrityError("RUN_EVIDENCE_EXPECTATION_MISMATCH")
    common = (
        "run_id",
        "run_kind",
        "platform",
        "model",
        "model_id",
        "weights_sha256",
        "device",
        "dtype",
        "source_commit",
        "inventory_sha256",
        "config_sha256",
        "threshold_lock_sha256",
        "collection_mode",
        "runtime_name",
        "runtime_version",
        "max_gpu_temperature_celsius",
    )
    for name in common:
        checkpoint_name = "config_sha" if name == "config_sha256" else name
        if getattr(manifest, name) != getattr(checkpoint, checkpoint_name):
            raise RunIntegrityError("MANIFEST_CHECKPOINT_IDENTITY_MISMATCH")
    if dict(manifest.runtime_environment) != dict(
        checkpoint.runtime_environment or {}
    ):
        raise RunIntegrityError("MANIFEST_CHECKPOINT_IDENTITY_MISMATCH")


def load_verified_run_evidence(
    run_root: Path,
    inventory: DatasetInventory,
    expectation: RunEvidenceExpectation,
) -> LoadedRunEvidence:
    """Read and fully verify one immutable terminal run without rewriting it."""

    if (
        not isinstance(inventory, DatasetInventory)
        or inventory.sample_count != 200
        or len(inventory.samples) != 200
    ):
        raise RunIntegrityError("TERMINAL_RUN_DENOMINATOR_INCOMPLETE")
    try:
        pinned_root = _PinnedDirectory.open(Path(run_root))
    except _PinnedFileError as error:
        raise RunIntegrityError("RUN_EVIDENCE_ROOT_INVALID") from error
    with pinned_root:
        try:
            pinned_inventory_root = _PinnedDirectory.open(
                Path(inventory.dataset_root)
            )
        except _PinnedFileError as error:
            raise RunIntegrityError("INVENTORY_DATASET_ROOT_INVALID") from error
        with pinned_inventory_root:
            root = pinned_root.path
            manifest_document, _ = _read_pinned_canonical_json(
                pinned_root, "manifest.json", "MANIFEST_CANONICAL_INVALID"
            )
            manifest = _manifest_from_document(manifest_document)
            _verify_manifest_schema(manifest)
            if manifest.status is not RunStatus.VALID:
                raise RunIntegrityError("TERMINAL_RUN_NOT_VALID")
            checkpoint_document, _ = _read_pinned_canonical_json(
                pinned_root, "checkpoint.json", "CHECKPOINT_CANONICAL_INVALID"
            )
            checkpoint = _checkpoint_from_document(checkpoint_document)
            inventory_document = _verify_inventory(
                inventory, pinned_root=pinned_inventory_root
            )
            _verify_current_images(
                inventory, pinned_root=pinned_inventory_root
            )
            records_dir = root / "records"
            if checkpoint.records_dir != records_dir:
                raise RunIntegrityError("RESUME_RECORDS_DIRECTORY_CHANGED")
            _verify_loaded_expectation(
                manifest,
                checkpoint,
                inventory,
                expectation,
                inventory_document,
            )
            records, documents = _load_verified_resume_evidence(
                checkpoint,
                inventory,
                expectation.config_sha256,
                expectation.source_commit,
                pinned_root=pinned_root,
                pinned_inventory_root=pinned_inventory_root,
            )
            _verify_manifest_anchor(manifest, checkpoint)
            if (
                len(records) != 200
                or checkpoint.record_count != 200
                or manifest.record_count != 200
            ):
                raise RunIntegrityError("TERMINAL_RUN_DENOMINATOR_INCOMPLETE")
            return LoadedRunEvidence(
                manifest=manifest,
                evidence_root=root,
                records=records,
                extended_record_documents=documents,
            )


class DetectorBenchmarkRunner:
    """Execute exactly one durable record for every canonical inventory sample."""

    def __init__(
        self,
        adapter: RawDetectorAdapter,
        output_root: Path | None = None,
    ) -> None:
        self.adapter = adapter
        self.output_root = None if output_root is None else Path(output_root)
        self._active_root: Path | None = None

    def _root_for(self, spec: RunSpec) -> Path:
        root = Path(spec.output_root)
        if self.output_root is not None and os.path.abspath(root) != os.path.abspath(
            self.output_root
        ):
            raise RunIntegrityError("RUNNER_OUTPUT_ROOT_MISMATCH")
        if not root.is_absolute():
            raise RunIntegrityError("OUTPUT_ROOT_MUST_BE_ABSOLUTE")
        if root.is_symlink():
            raise RunIntegrityError("OUTPUT_ROOT_SYMLINK_FORBIDDEN")
        if not root.exists():
            parent = _require_directory(root.parent, "OUTPUT_ROOT_PARENT_INVALID")
            descriptor = _open_directory(parent)
            try:
                os.mkdir(root.name, 0o700, dir_fd=descriptor)
                os.fsync(descriptor)
            except OSError as error:
                raise RunIntegrityError("OUTPUT_ROOT_CREATE_FAILED") from error
            finally:
                os.close(descriptor)
        return _require_directory(root, "OUTPUT_ROOT_INVALID")

    def _records_dir(self, root: Path) -> Path:
        records_dir = root / "records"
        if not records_dir.exists() and not records_dir.is_symlink():
            _create_directory(records_dir, root)
        return _require_directory(records_dir, "RECORDS_DIRECTORY_INVALID")

    def _write_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        if self._active_root is None:
            raise RunIntegrityError("RUNNER_NOT_ACTIVE")
        _atomic_replace_json(
            self._active_root / "checkpoint.json",
            checkpoint,
            "CHECKPOINT_WRITE_FAILED",
        )

    def _write_manifest(self, root: Path, manifest: RunManifest) -> None:
        _atomic_replace_json(
            root / "manifest.json", manifest, "MANIFEST_WRITE_FAILED"
        )

    def _verify_terminal_valid(
        self,
        root: Path,
        spec: RunSpec,
        manifest: RunManifest,
    ) -> None:
        _verify_inventory(spec.inventory)
        _validate_spec(spec, self.adapter)
        _verify_current_images(spec.inventory)
        provenance = _runtime_provenance(spec, self.adapter)
        _verify_manifest_identity(manifest, spec, provenance, self.adapter)
        records_dir = _require_directory(
            root / "records", "RECORDS_DIRECTORY_INVALID"
        )
        checkpoint = _read_checkpoint(root / "checkpoint.json")
        checkpoint_records = _require_directory(
            checkpoint.records_dir, "RECORDS_DIRECTORY_INVALID"
        )
        if checkpoint_records != records_dir:
            raise RunIntegrityError("RESUME_RECORDS_DIRECTORY_CHANGED")
        _verify_checkpoint_spec_identity(
            checkpoint, spec, provenance, self.adapter
        )
        verified_count = verify_resume(
            checkpoint,
            spec.inventory,
            spec.config_sha256,
            spec.source_commit,
        )
        _verify_manifest_anchor(manifest, checkpoint)
        if (
            verified_count != spec.inventory.sample_count
            or checkpoint.record_count != spec.inventory.sample_count
            or manifest.record_count != spec.inventory.sample_count
        ):
            raise RunIntegrityError("TERMINAL_RUN_DENOMINATOR_INCOMPLETE")

    def _manifest(
        self,
        spec: RunSpec,
        status: RunStatus,
        started_at: str,
        invalid_reason: str | None,
        records_dir: Path | None,
        provenance: RuntimeProvenance | None,
        *,
        preserve: RunManifest | None = None,
    ) -> RunManifest:
        if preserve is not None:
            return replace(
                preserve,
                status=status,
                ended_at=None if status is RunStatus.RUNNING else _utc_now(),
                invalid_reason=invalid_reason,
            )
        if records_dir is None:
            record_count = 0
            error_count = 0
            inventory_sha = _sha256(canonical_json_bytes({"records": []}))
            chain_head = None
        else:
            record_count, error_count, inventory_sha, chain_head = _record_inventory(
                records_dir
            )
        active_provenance = provenance
        if active_provenance is None and isinstance(
            spec.runtime_provenance, RuntimeProvenance
        ):
            active_provenance = spec.runtime_provenance
        runtime_name = "unverified"
        runtime_version = "unverified"
        weights_sha256 = "0" * 64
        environment: Mapping[str, str] = {"state": "unverified"}
        if active_provenance is not None:
            runtime_name = active_provenance.runtime_name
            runtime_version = active_provenance.runtime_version
            weights_sha256 = active_provenance.weights_sha256
            environment = active_provenance.environment
        return RunManifest(
            run_id=spec.run_id,
            run_kind=spec.run_kind,
            status=status,
            platform=spec.platform,
            model=spec.model,
            device=spec.device,
            dtype=spec.dtype,
            source_commit=spec.source_commit,
            inventory_sha256=spec.inventory.inventory_sha256,
            config_sha256=spec.config_sha256,
            threshold_lock_sha256=spec.threshold_lock_sha256,
            collection_mode=spec.collection_mode,
            model_id=str(getattr(self.adapter, "model_id", "unverified")),
            weights_sha256=weights_sha256,
            runtime_name=runtime_name,
            runtime_version=runtime_version,
            runtime_environment=environment,
            max_gpu_temperature_celsius=spec.max_gpu_temperature_celsius,
            record_count=record_count,
            error_count=error_count,
            record_inventory_sha256=inventory_sha,
            record_chain_head_sha256=chain_head,
            started_at=started_at,
            ended_at=None if status is RunStatus.RUNNING else _utc_now(),
            invalid_reason=invalid_reason,
        )

    def run(self, spec: RunSpec) -> RunManifest:
        started_at = _utc_now()
        root: Path | None = None
        records_dir: Path | None = None
        provenance: RuntimeProvenance | None = None
        existing_manifest: RunManifest | None = None
        manifest_schema_verified = False
        resume_verified = False
        terminal_read_only = False
        try:
            root = self._root_for(spec)
            self._active_root = root
            manifest_path = root / "manifest.json"
            if manifest_path.exists() or manifest_path.is_symlink():
                manifest_document, _ = _read_canonical_json(
                    manifest_path, "MANIFEST_CANONICAL_INVALID"
                )
                terminal_read_only = manifest_document.get("status") in {
                    RunStatus.VALID.value,
                    RunStatus.INVALID.value,
                }
                existing_manifest = _manifest_from_document(manifest_document)
                _verify_manifest_schema(existing_manifest)
                manifest_schema_verified = True
                if existing_manifest.status is RunStatus.VALID:
                    self._verify_terminal_valid(root, spec, existing_manifest)
                    return existing_manifest
                if existing_manifest.status is RunStatus.INVALID:
                    return existing_manifest
                if existing_manifest.status is not RunStatus.RUNNING:
                    raise RunIntegrityError("MANIFEST_NOT_RESUMABLE")
                started_at = existing_manifest.started_at
            _verify_inventory(spec.inventory)
            _validate_spec(spec, self.adapter)
            _verify_current_images(spec.inventory)
            provenance = _runtime_provenance(spec, self.adapter)
            if existing_manifest is not None:
                _verify_manifest_identity(
                    existing_manifest, spec, provenance, self.adapter
                )
            if existing_manifest is None and any(
                (root / name).exists() or (root / name).is_symlink()
                for name in ("records", "masks", "checkpoint.json")
            ):
                raise RunIntegrityError("UNOWNED_RUN_ARTIFACTS")
            records_dir = self._records_dir(root)
            checkpoint_path = root / "checkpoint.json"
            record_entries = tuple(records_dir.iterdir())
            if checkpoint_path.exists() or checkpoint_path.is_symlink():
                if existing_manifest is None:
                    raise RunIntegrityError("RESUME_MANIFEST_MISSING")
                checkpoint = _read_checkpoint(checkpoint_path)
                if checkpoint.records_dir.resolve(strict=True) != records_dir:
                    raise RunIntegrityError("RESUME_RECORDS_DIRECTORY_CHANGED")
                start_index = verify_resume(
                    checkpoint,
                    spec.inventory,
                    spec.config_sha256,
                    spec.source_commit,
                )
                _verify_checkpoint_spec_identity(
                    checkpoint, spec, provenance, self.adapter
                )
                _verify_manifest_anchor(existing_manifest, checkpoint)
                resume_verified = True
                previous_record_sha256: str | None = (
                    checkpoint.last_record_sha256 if start_index else None
                )
            elif record_entries:
                raise RunIntegrityError("RESUME_CHECKPOINT_MISSING")
            else:
                start_index = 0
                previous_record_sha256 = None
                if existing_manifest is not None:
                    empty_sha = _sha256(canonical_json_bytes({"records": []}))
                    if (
                        existing_manifest.record_count != 0
                        or existing_manifest.error_count != 0
                        or existing_manifest.record_inventory_sha256 != empty_sha
                        or existing_manifest.record_chain_head_sha256 is not None
                    ):
                        raise RunIntegrityError("RESUME_MANIFEST_ANCHOR_MISMATCH")
                    resume_verified = True
            if existing_manifest is None:
                running = self._manifest(
                    spec,
                    RunStatus.RUNNING,
                    started_at,
                    None,
                    records_dir,
                    provenance,
                )
                self._write_manifest(root, running)
            else:
                running = existing_manifest
            source_root = _adapter_evidence_root(self.adapter, root)
            for sample in spec.inventory.samples[start_index:]:
                frame = _load_frame(spec.inventory, sample)
                try:
                    result = self.adapter.collect(frame, spec.collection_mode)
                except Exception as error:
                    fatal = _fatal_error_code(error)
                    if fatal is not None:
                        raise _FatalRunError(fatal) from error
                    record, document = _error_record(
                        spec,
                        sample,
                        frame,
                        provenance,
                        str(getattr(self.adapter, "model_id")),
                        error,
                    )
                else:
                    _validate_raw_result(spec, result)
                    if result.model_id != getattr(self.adapter, "model_id", None):
                        raise _FatalRunError("MODEL_IDENTITY_MISMATCH")
                    observation = None
                    if spec.production_observer is not None:
                        observed_frame = _load_frame(spec.inventory, sample)
                        try:
                            observation = spec.production_observer(observed_frame)
                        except Exception as error:
                            fatal = _fatal_error_code(error)
                            if fatal is not None:
                                raise _FatalRunError(fatal) from error
                            record, document = _error_record(
                                spec,
                                sample,
                                observed_frame,
                                provenance,
                                str(getattr(self.adapter, "model_id")),
                                error,
                                result=result,
                                run_root=root,
                                source_root=source_root,
                            )
                        else:
                            if not isinstance(observation, ProductionObservation):
                                raise _FatalRunError("PRODUCTION_OBSERVATION_INVALID")
                            record, document = _ok_record(
                                spec,
                                sample,
                                observed_frame,
                                result,
                                provenance,
                                observation,
                                root,
                                source_root,
                            )
                    else:
                        record, document = _ok_record(
                            spec,
                            sample,
                            frame,
                            result,
                            provenance,
                            None,
                            root,
                            source_root,
                        )
                del record
                document["previous_record_sha256"] = previous_record_sha256
                record_path = records_dir / f"{sample.formal_sample_index:06d}.json"
                record_sha = _atomic_write_new_json(record_path, document)
                _, persisted_payload = _read_canonical_json(
                    record_path, "RECORD_READBACK_INVALID"
                )
                if _sha256(persisted_payload) != record_sha:
                    raise RunIntegrityError("RECORD_READBACK_INVALID")
                (
                    record_count,
                    error_count,
                    record_inventory_sha256,
                    _,
                ) = _record_inventory(records_dir)
                checkpoint = RunCheckpoint(
                    run_id=spec.run_id,
                    config_sha=spec.config_sha256,
                    source_commit=spec.source_commit,
                    inventory_sha256=spec.inventory.inventory_sha256,
                    records_dir=records_dir,
                    last_formal_sample_index=sample.formal_sample_index,
                    last_record_sha256=record_sha,
                    platform=spec.platform,
                    model=spec.model,
                    model_id=str(getattr(self.adapter, "model_id")),
                    weights_sha256=provenance.weights_sha256,
                    device=spec.device,
                    dtype=spec.dtype,
                    run_kind=spec.run_kind,
                    threshold_lock_sha256=spec.threshold_lock_sha256,
                    collection_mode=spec.collection_mode,
                    runtime_name=provenance.runtime_name,
                    runtime_version=provenance.runtime_version,
                    runtime_environment=dict(provenance.environment),
                    max_gpu_temperature_celsius=spec.max_gpu_temperature_celsius,
                    record_count=record_count,
                    error_count=error_count,
                    record_inventory_sha256=record_inventory_sha256,
                )
                self._write_checkpoint(checkpoint)
                previous_record_sha256 = record_sha
                running = self._manifest(
                    spec,
                    RunStatus.RUNNING,
                    started_at,
                    None,
                    records_dir,
                    provenance,
                )
                self._write_manifest(root, running)
            final_checkpoint = _read_checkpoint(root / "checkpoint.json")
            if verify_resume(
                final_checkpoint,
                spec.inventory,
                spec.config_sha256,
                spec.source_commit,
            ) != len(spec.inventory.samples):
                raise RunIntegrityError("RUN_DENOMINATOR_INCOMPLETE")
            _verify_manifest_anchor(running, final_checkpoint)
            manifest = self._manifest(
                spec,
                RunStatus.VALID,
                started_at,
                None,
                records_dir,
                provenance,
            )
            self._write_manifest(root, manifest)
            return manifest
        except Exception as error:
            if terminal_read_only:
                raise
            if isinstance(error, RunIntegrityError):
                reason = str(error)
            elif isinstance(error, OSError):
                reason = "PERSISTENCE_FAILED"
            else:
                reason = f"UNEXPECTED_RUNNER_FAILURE:{type(error).__name__}"
            preserve = (
                existing_manifest
                if (
                    existing_manifest is not None
                    and manifest_schema_verified
                    and not resume_verified
                )
                else None
            )
            if records_dir is None and root is not None:
                candidate_records = root / "records"
                if candidate_records.is_dir() and not candidate_records.is_symlink():
                    records_dir = candidate_records.resolve(strict=True)
            manifest = self._manifest(
                spec,
                RunStatus.INVALID,
                started_at,
                reason,
                records_dir,
                provenance,
                preserve=preserve,
            )
            if root is not None and not root.is_symlink():
                try:
                    self._write_manifest(root, manifest)
                except RunIntegrityError:
                    pass
            return manifest
        finally:
            self._active_root = None


__all__ = (
    "DetectorBenchmarkRunner",
    "LoadedRunEvidence",
    "RunCheckpoint",
    "RunEvidenceExpectation",
    "RunIntegrityError",
    "RunManifest",
    "RunSpec",
    "load_verified_run_evidence",
    "verify_resume",
)
