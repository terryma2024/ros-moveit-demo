"""Load and verify the evidence of a run to resume and of a finished run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime, timezone
import json
import math
from pathlib import Path, PurePosixPath

from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RecordStatus,
    RunKind,
    RunStatus,
    RuntimeProvenance,
    model_id_for_name,
)
from so101_demo.perception_benchmark.dataset.contracts import DatasetInventory
from so101_demo.perception_benchmark.dataset.pinned_files import _PinnedDirectory, _PinnedFileError
from so101_demo.perception_benchmark.runner.contracts import (
    _RECORD_NAME,
    _SHA256,
    _SOURCE_COMMIT,
    RunCheckpoint,
    RunEvidenceExpectation,
    RunIntegrityError,
    RunManifest,
    RunSpec,
)
from so101_demo.perception_benchmark.runner.records import (
    _checkpoint_identity,
    _record_from_document,
    _verify_extended_record,
    _verify_mask_tree,
    _verify_record_mask,
)
from so101_demo.perception_benchmark.runner.storage import (
    LoadedRunEvidence,
    _freeze_document,
    _read_canonical_json,
    _read_pinned_canonical_json,
    _require_directory,
    _require_sha,
    _sha256,
)
from so101_demo.perception_benchmark.runner.verification import (
    _verify_current_images,
    _verify_inventory,
)


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
            if checkpoint.records_dir.name != "records" or ".." in checkpoint.records_dir.parts:
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
