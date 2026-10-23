"""The asset verification, archive inspection, dataset preparation and test unlock subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

import numpy as np

from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.adapters.perception.yolo_seg import verify_weights
from so101_demo.cli.benchmark.common import (
    BenchmarkError,
    DryRunSample,
    _bind_archive_arguments,
    _bind_model_arguments,
    _load_frozen_config,
    _preflight_append_log,
    _preflight_output_root,
    _read_bytes,
)
from so101_demo.perception_benchmark.calibration.lock_io import unlock_test_seal
from so101_demo.perception_benchmark.codec import (
    sha256_bytes,
)
from so101_demo.perception_benchmark.dataset.contracts import sha256_file, TestSeal
from so101_demo.perception_benchmark.dataset.verifier import DatasetArchiveVerifier


def _handle_verify_assets(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_model_arguments(arguments, config)
    if arguments.model == "yolo_seg":
        if arguments.weights is None or arguments.weights_sha256 is None:
            raise BenchmarkError("MODEL_ASSET_ARGUMENTS_INVALID")
        verified = verify_weights(arguments.weights, arguments.weights_sha256)
    else:
        if arguments.model_root is None or arguments.manifest_sha256 is None:
            raise BenchmarkError("MODEL_ASSET_ARGUMENTS_INVALID")
        verified = verify_model_bundle(
            arguments.model_root, arguments.manifest_sha256
        ).manifest_sha256
    print(verified)
    return 0


def _handle_inspect_archive(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_archive_arguments(arguments, config)
    _preflight_output_root(arguments.sealed_member_inventory)
    result = DatasetArchiveVerifier().verify_archive(
        arguments.archive,
        arguments.expected_sha256,
        arguments.sealed_member_inventory,
    )
    print(result.sealed_test_member_inventory_sha256)
    return 0


def _handle_prepare_dataset(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_archive_arguments(arguments, config)
    _preflight_output_root(arguments.output_root)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        arguments.archive,
        arguments.expected_sha256,
        arguments.output_root,
        "val",
        None,
    )
    print(inventory.inventory_sha256)
    return 0


def _handle_unlock_test(arguments: argparse.Namespace) -> int:
    config = _load_frozen_config(arguments.config)
    _bind_archive_arguments(arguments, config)
    _preflight_output_root(arguments.output_root)
    if (
        not arguments.yolo_threshold_lock.is_file()
        or not arguments.grounded_sam_threshold_lock.is_file()
    ):
        raise BenchmarkError("TEST_SEALED", "two verified threshold locks are required")
    if arguments.yolo_threshold_lock == arguments.grounded_sam_threshold_lock:
        raise BenchmarkError("TEST_SEALED", "two distinct verified threshold locks are required")
    _read_bytes(arguments.yolo_threshold_lock, "THRESHOLD_LOCK_INVALID")
    _read_bytes(arguments.grounded_sam_threshold_lock, "THRESHOLD_LOCK_INVALID")
    _preflight_append_log(arguments.access_log)
    archive = Path(arguments.archive)
    try:
        metadata = archive.lstat()
    except OSError as error:
        raise BenchmarkError("DATASET_ARCHIVE_UNREADABLE") from error
    if archive.is_symlink() or not archive.is_file() or metadata.st_nlink != 1:
        raise BenchmarkError("DATASET_ARCHIVE_UNREADABLE")
    if sha256_file(archive) != arguments.expected_sha256:
        raise BenchmarkError("DATASET_ARCHIVE_SHA256_MISMATCH")
    sealed_sha = sha256_bytes(
        _read_bytes(arguments.sealed_member_inventory, "SEALED_MEMBER_INVENTORY_INVALID")
    )
    with tempfile.TemporaryDirectory(
        prefix=".unlock-preflight-", dir=arguments.output_root.parent
    ) as temporary:
        inspected = DatasetArchiveVerifier().verify_archive(
            arguments.archive,
            arguments.expected_sha256,
            Path(temporary) / "sealed-test-members.json",
        )
    if inspected.sealed_test_member_inventory_sha256 != sealed_sha:
        raise BenchmarkError("TEST_SEAL_ARCHIVE_MISMATCH")
    _preflight_output_root(arguments.output_root)
    seal = unlock_test_seal(
        TestSeal(sealed_sha, arguments.access_log),
        arguments.yolo_threshold_lock,
        arguments.grounded_sam_threshold_lock,
    )
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        arguments.archive,
        arguments.expected_sha256,
        arguments.output_root,
        "test",
        seal,
    )
    print(inventory.inventory_sha256)
    return 0


def _candidate_mask(sample: DryRunSample, candidate_index: int) -> np.ndarray:
    mask = np.zeros((480, 640), dtype=bool)
    x0 = 55 + sample.formal_sample_index * 13 + candidate_index * 190
    y0 = 90 + sample.formal_sample_index * 7
    mask[y0 : y0 + 120, x0 : x0 + 95] = True
    return mask
