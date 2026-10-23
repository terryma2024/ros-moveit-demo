"""The detector benchmark runner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import os
from pathlib import Path

from so101_demo.perception_benchmark.adapters.base import (
    ProductionObservation,
    RawDetectorAdapter,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    RunStatus,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.runner.contracts import (
    RunCheckpoint,
    RunIntegrityError,
    RunManifest,
    RunSpec,
    _FatalRunError,
)
from so101_demo.perception_benchmark.runner.records import (
    _adapter_evidence_root,
    _error_record,
    _ok_record,
    _validate_spec,
)
from so101_demo.perception_benchmark.runner.resume import (
    _manifest_from_document,
    _read_checkpoint,
    _record_inventory,
    _verify_checkpoint_spec_identity,
    _verify_manifest_anchor,
    _verify_manifest_identity,
    _verify_manifest_schema,
    verify_resume,
)
from so101_demo.perception_benchmark.runner.storage import (
    _atomic_replace_json,
    _atomic_write_new_json,
    _create_directory,
    _open_directory,
    _read_canonical_json,
    _require_directory,
    _sha256,
    _utc_now,
)
from so101_demo.perception_benchmark.runner.verification import (
    _fatal_error_code,
    _load_frame,
    _runtime_provenance,
    _validate_raw_result,
    _verify_current_images,
    _verify_inventory,
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
