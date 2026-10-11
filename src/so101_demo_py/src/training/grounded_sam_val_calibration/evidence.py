"""Write the calibration evidence and collect the raw validation records."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from PIL import Image

from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import CollectionMode
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    read_mask,
)
from so101_demo.perception_benchmark.contracts import RawCandidate
from so101_demo.training.grounded_sam_val_calibration.datasets import (
    _COMMIT,
    _RAW_LIMITS,
    _RAW_RECORD_SCHEMA,
    _RAW_RUN_SCHEMA,
    _SHA256,
    ValCalibrationError,
    ValDataset,
    _read_canonical,
    candidate_from_document,
    candidate_to_document,
)


def _create_output_root(path: Path) -> Path:
    root = Path(path)
    if not root.is_absolute() or root.is_symlink() or not root.parent.is_dir():
        raise ValCalibrationError("OUTPUT_ROOT_INVALID", str(root))
    if os.path.lexists(root):
        raise ValCalibrationError("OUTPUT_ROOT_ALREADY_EXISTS", str(root))
    try:
        os.mkdir(root, 0o700)
    except OSError as error:
        raise ValCalibrationError("OUTPUT_ROOT_CREATE_FAILED", str(root)) from error
    return root


def write_calibration_evidence(
    *,
    output_root: Path,
    dataset: ValDataset,
    raw_run_root: Path,
    raw_manifest_sha256: str,
    source_commit: str,
    selected: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Persist one exclusive deterministic val calibration result."""

    if (
        _SHA256.fullmatch(raw_manifest_sha256) is None
        or _COMMIT.fullmatch(source_commit) is None
        or not Path(raw_run_root).is_absolute()
    ):
        raise ValCalibrationError("CALIBRATION_PROVENANCE_INVALID")
    root = _create_output_root(output_root)
    report = {
        "schema_version": "so101-grounded-sam-val-calibration-report/v1",
        "source_commit": source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "raw_run_root": str(Path(raw_run_root)),
        "raw_manifest_sha256": raw_manifest_sha256,
        "selected_sam_quality": selected["sam_quality"],
        "selected": dict(selected),
        "grid_points": [dict(point) for point in points],
    }
    try:
        report_sha = atomic_write_json(root / "report.json", report)
        atomic_write_json(
            root / "manifest.json",
            {
                "schema_version": "so101-grounded-sam-val-calibration-run/v1",
                "status": "VALID",
                "source_commit": source_commit,
                "val_inventory_sha256": dataset.inventory_sha256,
                "raw_manifest_sha256": raw_manifest_sha256,
                "report_sha256": report_sha,
            },
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValCalibrationError("CALIBRATION_WRITE_FAILED") from error
    return MappingProxyType(report)


def _write_exclusive_json(path: Path, document: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(document)
    target = Path(path)
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ValCalibrationError("OUTPUT_COLLISION", str(target)) from error
    return hashlib.sha256(payload).hexdigest()


def _record_inventory_sha(record_hashes: Sequence[str]) -> str:
    return hashlib.sha256(
        canonical_json_bytes({"record_sha256s": list(record_hashes)})
    ).hexdigest()


def _replace_manifest(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.next")
    if os.path.lexists(temporary):
        raise ValCalibrationError("OUTPUT_COLLISION", str(temporary))
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ValCalibrationError("MANIFEST_WRITE_FAILED", str(path)) from error


def collect_val_raw(
    *,
    dataset: ValDataset,
    adapter: Any | None = None,
    adapter_factory: Callable[[Path], Any] | None = None,
    output_root: Path,
    run_id: str,
    source_commit: str,
    model_manifest_sha256: str,
) -> Mapping[str, Any]:
    """Run one complete CUDA low-floor collection and persist all metadata."""

    if (
        not isinstance(dataset, ValDataset)
        or not isinstance(run_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", run_id) is None
        or _COMMIT.fullmatch(source_commit) is None
        or _SHA256.fullmatch(model_manifest_sha256) is None
        or ((adapter is None) == (adapter_factory is None))
    ):
        raise ValCalibrationError("RAW_RUN_IDENTITY_INVALID")
    root = _create_output_root(output_root)
    records_root = root / "records"
    records_root.mkdir(mode=0o700)
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": _RAW_RUN_SCHEMA,
        "status": "RUNNING",
        "run_id": run_id,
        "source_commit": source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "model_manifest_sha256": model_manifest_sha256,
        "expected_sample_count": len(dataset.samples),
        "record_count": 0,
        "record_inventory_sha256": _record_inventory_sha(()),
        "inference_error_count": 0,
    }
    _write_exclusive_json(manifest_path, manifest)
    record_hashes: list[str] = []
    try:
        active_adapter = adapter if adapter is not None else adapter_factory(root)
        if (
            getattr(active_adapter, "model_id", None)
            != "grounding-dino-tiny+sam2.1-hiera-tiny"
            or getattr(active_adapter, "runtime_device", None) != "cuda"
        ):
            raise ValCalibrationError("RAW_RUN_IDENTITY_INVALID")
        for sample in dataset.samples:
            try:
                image_payload = sample.image_path.read_bytes()
                if hashlib.sha256(image_payload).hexdigest() != sample.image_sha256:
                    raise ValCalibrationError("VAL_IMAGE_SHA256_MISMATCH", str(sample.seed))
                with Image.open(sample.image_path) as opened:
                    rgb = np.asarray(opened.convert("RGB"), dtype=np.uint8)
                frame = DetectionFrame(
                    rgb8=rgb,
                    source_stamp_ns=sample.seed,
                    source_frame_id="synthetic_val_camera",
                )
                result = active_adapter.collect(frame, CollectionMode.LOW_FLOOR)
                candidates = tuple(result.raw_candidates)
                if (
                    result.model_id != "grounding-dino-tiny+sam2.1-hiera-tiny"
                    or result.runtime_device != "cuda"
                    or result.dtype != "float32"
                    or CollectionMode(result.collection_mode) is not CollectionMode.LOW_FLOOR
                    or result.fallback_used is not False
                    or dict(result.irreversible_limits) != _RAW_LIMITS
                    or len(candidates) > 300
                    or any(candidate.label != "cup" for candidate in candidates)
                ):
                    raise ValCalibrationError("RAW_RUNTIME_CONTRACT_INVALID", str(sample.seed))
                for candidate in candidates:
                    read_mask(candidate.mask, root)
                record = {
                    "schema_version": _RAW_RECORD_SCHEMA,
                    "formal_sample_index": sample.formal_sample_index,
                    "seed": sample.seed,
                    "scenario": sample.scenario,
                    "image_sha256": sample.image_sha256,
                    "raw_candidates": [candidate_to_document(item) for item in candidates],
                    "runtime": {
                        "device": "cuda",
                        "dtype": "float32",
                        "fallback_used": False,
                    },
                    "irreversible_limits": dict(_RAW_LIMITS),
                }
                record_hashes.append(
                    _write_exclusive_json(
                        records_root / f"{sample.formal_sample_index:06d}.json",
                        record,
                    )
                )
                manifest["record_count"] = len(record_hashes)
                manifest["record_inventory_sha256"] = _record_inventory_sha(record_hashes)
                _replace_manifest(manifest_path, manifest)
                if len(record_hashes) % 10 == 0 or len(record_hashes) == len(dataset.samples):
                    print(
                        f"VAL_RAW_PROGRESS completed={len(record_hashes)} "
                        f"total={len(dataset.samples)}",
                        flush=True,
                    )
            except Exception as error:
                manifest["status"] = "INVALID"
                manifest["inference_error_count"] = 1
                manifest["record_count"] = len(record_hashes)
                manifest["record_inventory_sha256"] = _record_inventory_sha(record_hashes)
                _replace_manifest(manifest_path, manifest)
                if isinstance(error, ValCalibrationError):
                    raise
                raise ValCalibrationError(
                    "RAW_INFERENCE_FAILED", type(error).__name__
                ) from error
        manifest["status"] = "VALID"
        _replace_manifest(manifest_path, manifest)
        return MappingProxyType(dict(manifest))
    except Exception:
        if manifest["status"] == "RUNNING":
            manifest["status"] = "INVALID"
            manifest["inference_error_count"] = 1
            manifest["record_count"] = len(record_hashes)
            manifest["record_inventory_sha256"] = _record_inventory_sha(record_hashes)
            _replace_manifest(manifest_path, manifest)
        raise


def load_verified_raw_records(
    root: Path,
    *,
    dataset: ValDataset,
    expected_model_manifest_sha256: str,
    expected_source_commit: str,
) -> tuple[tuple[RawCandidate, ...], ...]:
    """Load a terminal val raw run and verify every record and mask."""

    evidence_root = Path(root)
    if (
        not evidence_root.is_absolute()
        or evidence_root.is_symlink()
        or not evidence_root.is_dir()
        or _SHA256.fullmatch(expected_model_manifest_sha256) is None
        or _COMMIT.fullmatch(expected_source_commit) is None
    ):
        raise ValCalibrationError("RAW_RUN_IDENTITY_INVALID")
    manifest, _ = _read_canonical(evidence_root / "manifest.json", "RAW_MANIFEST_INVALID")
    expected_manifest = {
        "schema_version": _RAW_RUN_SCHEMA,
        "status": "VALID",
        "run_id": manifest.get("run_id"),
        "source_commit": expected_source_commit,
        "val_inventory_sha256": dataset.inventory_sha256,
        "source_manifest_sha256": dataset.source_manifest_sha256,
        "model_manifest_sha256": expected_model_manifest_sha256,
        "expected_sample_count": len(dataset.samples),
        "record_count": len(dataset.samples),
        "record_inventory_sha256": manifest.get("record_inventory_sha256"),
        "inference_error_count": 0,
    }
    if dict(manifest) != expected_manifest or not isinstance(manifest.get("run_id"), str):
        raise ValCalibrationError("RAW_MANIFEST_INVALID", "identity")
    record_hashes: list[str] = []
    output: list[tuple[RawCandidate, ...]] = []
    records_root = evidence_root / "records"
    paths = tuple(sorted(records_root.glob("*.json")))
    if len(paths) != len(dataset.samples):
        raise ValCalibrationError("RAW_DENOMINATOR_INVALID")
    for sample, path in zip(dataset.samples, paths, strict=True):
        if path.name != f"{sample.formal_sample_index:06d}.json":
            raise ValCalibrationError("RAW_RECORD_ORDER_INVALID")
        record, payload = _read_canonical(path, "RAW_RECORD_INVALID")
        if (
            set(record)
            != {
                "formal_sample_index",
                "image_sha256",
                "irreversible_limits",
                "raw_candidates",
                "runtime",
                "scenario",
                "schema_version",
                "seed",
            }
            or record.get("schema_version") != _RAW_RECORD_SCHEMA
            or record.get("formal_sample_index") != sample.formal_sample_index
            or record.get("seed") != sample.seed
            or record.get("scenario") != sample.scenario
            or record.get("image_sha256") != sample.image_sha256
            or record.get("runtime")
            != {"device": "cuda", "dtype": "float32", "fallback_used": False}
            or record.get("irreversible_limits") != _RAW_LIMITS
            or not isinstance(record.get("raw_candidates"), list)
        ):
            raise ValCalibrationError("RAW_RECORD_INVALID", path.name)
        candidates = tuple(
            candidate_from_document(item) for item in record["raw_candidates"]
        )
        if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
            raise ValCalibrationError("RAW_CANDIDATE_INVALID", "duplicate IDs")
        try:
            for candidate in candidates:
                read_mask(candidate.mask, evidence_root)
        except (OSError, ValueError) as error:
            raise ValCalibrationError("RAW_MASK_INVALID", path.name) from error
        record_hashes.append(hashlib.sha256(payload).hexdigest())
        output.append(candidates)
    inventory_sha = hashlib.sha256(
        canonical_json_bytes({"record_sha256s": record_hashes})
    ).hexdigest()
    if inventory_sha != manifest["record_inventory_sha256"]:
        raise ValCalibrationError("RAW_RECORD_INVENTORY_INVALID")
    return tuple(output)


def verify_val_truth_rebind(
    *,
    raw_dataset: ValDataset,
    truth_dataset: ValDataset,
) -> Mapping[str, Any]:
    """Bind verified raw records to corrected truth only for identical val images."""

    if (
        not isinstance(raw_dataset, ValDataset)
        or not isinstance(truth_dataset, ValDataset)
        or len(raw_dataset.samples) != len(truth_dataset.samples)
    ):
        raise ValCalibrationError("RAW_TRUTH_REBIND_INVALID", "denominator")
    identities = []
    for raw_sample, truth_sample in zip(
        raw_dataset.samples,
        truth_dataset.samples,
        strict=True,
    ):
        raw_identity = (
            raw_sample.formal_sample_index,
            raw_sample.seed,
            raw_sample.scenario,
            raw_sample.configured_cup_count,
            raw_sample.image_sha256,
        )
        truth_identity = (
            truth_sample.formal_sample_index,
            truth_sample.seed,
            truth_sample.scenario,
            truth_sample.configured_cup_count,
            truth_sample.image_sha256,
        )
        if raw_identity != truth_identity:
            raise ValCalibrationError(
                "RAW_TRUTH_REBIND_INVALID",
                str(raw_sample.formal_sample_index),
            )
        identities.append(
            {
                "configured_cup_count": raw_sample.configured_cup_count,
                "formal_sample_index": raw_sample.formal_sample_index,
                "image_sha256": raw_sample.image_sha256,
                "scenario": raw_sample.scenario,
                "seed": raw_sample.seed,
            }
        )
    receipt = {
        "raw_source_manifest_sha256": raw_dataset.source_manifest_sha256,
        "raw_val_inventory_sha256": raw_dataset.inventory_sha256,
        "sample_count": len(identities),
        "sample_identity_sha256": hashlib.sha256(
            canonical_json_bytes({"samples": identities})
        ).hexdigest(),
        "truth_source_manifest_sha256": truth_dataset.source_manifest_sha256,
        "truth_val_inventory_sha256": truth_dataset.inventory_sha256,
    }
    return MappingProxyType(receipt)
