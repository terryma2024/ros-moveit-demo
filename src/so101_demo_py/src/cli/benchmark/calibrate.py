"""The calibrate subcommand."""

from __future__ import annotations

import argparse
from dataclasses import fields, replace
from pathlib import Path, PurePosixPath
import re
import sys
import time
from typing import Any, Mapping

from so101_demo.cli.benchmark.common import (
    _CONFIG_SHA256,
    BenchmarkError,
    _bind_dataset_sha,
    _frozen_asset_sha,
    _frozen_model_id,
    _load_frozen_config,
    _preflight_output_root,
    _read_json,
    _source_commit,
    _write_index,
)
from so101_demo.perception_benchmark.calibration.contracts import CalibrationProgress
from so101_demo.perception_benchmark.calibration.evaluation import calibrate_joint_platform_val
from so101_demo.perception_benchmark.calibration.lock_io import write_threshold_lock
from so101_demo.perception_benchmark.codec import (
    read_mask,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
    RunKind,
)
from so101_demo.perception_benchmark.dataset.loading import (
    load_dataset_inventory,
    load_truth_samples,
)
from so101_demo.perception_benchmark.runner.contracts import RunEvidenceExpectation
from so101_demo.perception_benchmark.runner.resume import load_verified_run_evidence


def _expectation(path: Path, sha: str) -> RunEvidenceExpectation:
    document = _read_json(path, "RUN_EXPECTATION_INVALID", sha)
    expected = {item.name for item in fields(RunEvidenceExpectation)}
    if set(document) != expected:
        raise BenchmarkError("RUN_EXPECTATION_INVALID")
    try:
        return RunEvidenceExpectation(**document)
    except (TypeError, ValueError) as error:
        raise BenchmarkError("RUN_EXPECTATION_INVALID") from error


def _paths_overlap(first: Path, second: Path) -> bool:
    left = Path(first).resolve(strict=False)
    right = Path(second).resolve(strict=False)
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _preflight_calibration_output(arguments: argparse.Namespace) -> None:
    output = _preflight_output_root(arguments.output_root)
    protected = (
        arguments.dataset_inventory.parent,
        arguments.mac_run_root,
        arguments.linux_run_root,
    )
    if any(_paths_overlap(output, path) for path in protected):
        raise BenchmarkError("CALIBRATION_OUTPUT_OVERLAP")


def _validate_val_run_provenance(
    loaded: object,
    *,
    platform_name: str,
    device: str,
    arguments: argparse.Namespace,
    config: Mapping[str, Any],
) -> None:
    manifest = getattr(loaded, "manifest", None)
    expected = {
        "model": arguments.model,
        "model_id": _frozen_model_id(config, arguments.model),
        "platform": platform_name,
        "device": device,
        "dtype": "float32",
        "run_kind": RunKind.VAL_RAW,
        "source_commit": arguments.source_commit,
        "config_sha256": _CONFIG_SHA256,
        "weights_sha256": _frozen_asset_sha(config, arguments.model),
    }
    if manifest is None or any(
        getattr(manifest, name, None) != value for name, value in expected.items()
    ):
        raise BenchmarkError("RUN_PROVENANCE_MISMATCH")


def _safe_rehome_mask(mask_ref: object, source: Path) -> bytes:
    relative_value = getattr(mask_ref, "relative_path", None)
    if not isinstance(relative_value, str):
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    relative = PurePosixPath(relative_value)
    if (
        relative.is_absolute()
        or "\\" in relative_value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    root = Path(source).resolve(strict=True)
    target = root.joinpath(*relative.parts)
    try:
        metadata = target.lstat()
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise BenchmarkError("CALIBRATION_MASK_INVALID") from error
    if (
        target.is_symlink()
        or not target.is_file()
        or metadata.st_nlink != 1
        or not resolved.is_relative_to(root)
    ):
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    try:
        payload = target.read_bytes()
        read_mask(mask_ref, root)
        after = target.lstat()
    except (OSError, ValueError) as error:
        raise BenchmarkError("CALIBRATION_MASK_INVALID") from error
    before_identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity:
        raise BenchmarkError("CALIBRATION_MASK_INVALID")
    return payload


def _print_calibration_progress(event: CalibrationProgress) -> None:
    percent = 100.0 * event.completed / event.total
    print(
        "CALIBRATION_PROGRESS "
        f"phase={event.phase} completed={event.completed} total={event.total} "
        f"percent={percent:.1f} elapsed={event.elapsed_seconds:.1f}s",
        file=sys.stderr,
        flush=True,
    )


def _handle_calibrate(arguments: argparse.Namespace) -> int:
    workers = getattr(arguments, "calibration_workers", 1)
    if type(workers) is not int or not 1 <= workers <= 64:
        raise BenchmarkError("CALIBRATION_WORKERS_INVALID")
    progress_started_at = time.monotonic()
    _print_calibration_progress(CalibrationProgress("verify", 0, 1, 0.0))
    config = _load_frozen_config(arguments.config)
    _bind_dataset_sha(arguments.dataset_archive_sha256, config)
    _source_commit(arguments.source_commit)
    _preflight_calibration_output(arguments)
    inventory = load_dataset_inventory(
        arguments.dataset_inventory.parent,
        expected_split="val",
        expected_archive_sha256=arguments.dataset_archive_sha256,
        expected_inventory_sha256=arguments.inventory_sha256,
    )
    truths = load_truth_samples(inventory.dataset_root, "val", inventory)
    mac_expectation = _expectation(
        arguments.mac_run_expectation, arguments.mac_run_expectation_sha256
    )
    linux_expectation = _expectation(
        arguments.linux_run_expectation, arguments.linux_run_expectation_sha256
    )
    mac = load_verified_run_evidence(arguments.mac_run_root, inventory, mac_expectation)
    linux = load_verified_run_evidence(arguments.linux_run_root, inventory, linux_expectation)
    if any(
        _paths_overlap(arguments.output_root, path)
        for path in (inventory.dataset_root, mac.evidence_root, linux.evidence_root)
    ):
        raise BenchmarkError("CALIBRATION_OUTPUT_OVERLAP")
    _validate_val_run_provenance(
        mac,
        platform_name="macos",
        device="mps",
        arguments=arguments,
        config=config,
    )
    _validate_val_run_provenance(
        linux,
        platform_name="linux",
        device="cuda",
        arguments=arguments,
        config=config,
    )
    _print_calibration_progress(
        CalibrationProgress("verify", 1, 1, time.monotonic() - progress_started_at)
    )
    arguments.output_root.mkdir(parents=False, mode=0o700)
    mask_root = arguments.output_root / "calibration-masks"
    mask_root.mkdir()
    rehome_total = sum(
        len(record.raw_candidates) for record in (*mac.records, *linux.records)
    ) + sum(len(truth.instances) for truth in truths)
    rehome_total = max(1, rehome_total)
    rehome_completed = 0
    rehome_step = max(1, rehome_total // 100)
    _print_calibration_progress(
        CalibrationProgress("rehome", 0, rehome_total, time.monotonic() - progress_started_at)
    )

    def rehome_mask(mask_ref: object, source: Path, relative: str):
        nonlocal rehome_completed
        payload = _safe_rehome_mask(mask_ref, source)
        destination = mask_root / relative
        if destination.exists() or destination.is_symlink():
            raise BenchmarkError("CALIBRATION_MASK_OVERWRITE")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as handle:
                handle.write(payload)
        except FileExistsError as error:
            raise BenchmarkError("CALIBRATION_MASK_OVERWRITE") from error
        rehome_completed += 1
        if rehome_completed == rehome_total or rehome_completed % rehome_step == 0:
            _print_calibration_progress(
                CalibrationProgress(
                    "rehome",
                    rehome_completed,
                    rehome_total,
                    time.monotonic() - progress_started_at,
                )
            )
        return replace(mask_ref, relative_path=relative)

    def rehome(records: tuple[PredictionRecord, ...], source: Path, platform: str):
        updated = []
        for record in records:
            candidates = []
            for candidate in record.raw_candidates:
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", candidate.candidate_id) is None:
                    raise BenchmarkError("CALIBRATION_MASK_INVALID")
                relative = (
                    f"{platform}/{record.formal_sample_index:06d}/{candidate.candidate_id}.json"
                )
                candidates.append(
                    replace(
                        candidate,
                        mask=rehome_mask(candidate.mask, source, relative),
                    )
                )
            updated.append(replace(record, raw_candidates=tuple(candidates)))
        return tuple(updated)

    def rehome_truths():
        updated = []
        for truth in truths:
            instances = []
            for ordinal, instance in enumerate(truth.instances):
                relative = f"truth/{truth.formal_sample_index:06d}/{ordinal:06d}.json"
                instances.append(
                    replace(
                        instance,
                        mask=rehome_mask(instance.mask, inventory.dataset_root, relative),
                    )
                )
            updated.append(replace(truth, instances=tuple(instances)))
        return tuple(updated)

    mac_records = rehome(mac.records, mac.evidence_root, "macos")
    linux_records = rehome(linux.records, linux.evidence_root, "linux")
    rehomed_truths = rehome_truths()
    if rehome_completed == 0:
        _print_calibration_progress(
            CalibrationProgress("rehome", 1, 1, time.monotonic() - progress_started_at)
        )
    lock = calibrate_joint_platform_val(
        arguments.model,
        mac_records,
        linux_records,
        rehomed_truths,
        inventory.inventory_sha256,
        evidence_root=mask_root,
        mac_prediction_inventory_sha256=mac.manifest.record_inventory_sha256,
        linux_prediction_inventory_sha256=linux.manifest.record_inventory_sha256,
        source_commit=mac.manifest.source_commit,
        workers=workers,
        progress_callback=_print_calibration_progress,
        progress_started_at=progress_started_at,
    )
    write_threshold_lock(arguments.output_root / "threshold-lock.json", lock)
    _write_index(arguments.output_root)
    print(lock.lock_sha256)
    return 0
