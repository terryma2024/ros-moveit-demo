"""Load the dataset inventory, publish the truth masks and load truth samples."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    SCHEMA_VERSION,
    MaskRef,
    TruthSample,
)
from so101_demo.perception_benchmark.dataset.contracts import (
    _EXPECTED_SAMPLE_COUNT,
    _EXPECTED_SCENARIO_COUNTS,
    _INVENTORY_KEYS,
    _RASTERIZER,
    _SAMPLE_KEYS,
    DatasetInventory,
    DatasetSampleRef,
    DatasetVerificationError,
    Split,
    _require_sha256,
)
from so101_demo.perception_benchmark.dataset.pinned_files import (
    _PinnedDirectory,
    _PinnedFileError,
    _rename_directory_noreplace,
)
from so101_demo.perception_benchmark.dataset.truth import (
    _issue_inventory,
    _require_rasterizer_version,
)
from so101_demo.perception_benchmark.dataset.verifier import (
    _derive_truth_artifacts,
    _read_regular_bound_file,
    _verify_exact_dataset_tree,
    _verify_inventory_and_tree,
    _verify_truth_mask_refs,
)


def load_dataset_inventory(
    dataset_root: Path,
    *,
    expected_split: Split,
    expected_archive_sha256: str,
    expected_inventory_sha256: str,
    expected_test_access_event_sha256: str | None = None,
    expected_sealed_member_inventory_sha256: str | None = None,
    expected_threshold_lock_sha256s: tuple[str, str] | None = None,
    expected_access_log_path: Path | None = None,
) -> DatasetInventory:
    """Load one formal persisted inventory and reissue only a local capability.

    The persisted document remains the source of every serializable field.  The
    process-local capability is minted only after strict reconstruction and is
    never written back to disk.  The accepted tree is either the core extracted
    dataset or that core plus one complete, rerasterized ``truth_masks`` tree.
    """

    _require_rasterizer_version()
    if expected_split not in {"val", "test"}:
        raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
    expected_archive_sha256 = _require_sha256(
        expected_archive_sha256, "INVENTORY_EXTERNAL_ANCHOR_INVALID"
    )
    expected_inventory_sha256 = _require_sha256(
        expected_inventory_sha256, "INVENTORY_EXTERNAL_ANCHOR_INVALID"
    )
    if expected_split == "val":
        if any(
            value is not None
            for value in (
                expected_test_access_event_sha256,
                expected_sealed_member_inventory_sha256,
                expected_threshold_lock_sha256s,
                expected_access_log_path,
            )
        ):
            raise DatasetVerificationError("VAL_EXTERNAL_TEST_ANCHOR_CONFLICT")
        normalized_event_sha = None
        normalized_sealed_sha = None
        normalized_locks = None
        normalized_access_log_path = None
    else:
        normalized_event_sha = _require_sha256(
            expected_test_access_event_sha256,
            "INVENTORY_EXTERNAL_ANCHOR_INVALID",
        )
        normalized_sealed_sha = _require_sha256(
            expected_sealed_member_inventory_sha256,
            "INVENTORY_EXTERNAL_ANCHOR_INVALID",
        )
        if (
            not isinstance(expected_threshold_lock_sha256s, tuple)
            or len(expected_threshold_lock_sha256s) != 2
        ):
            raise DatasetVerificationError("INVENTORY_EXTERNAL_ANCHOR_INVALID")
        normalized_locks = tuple(
            _require_sha256(value, "INVENTORY_EXTERNAL_ANCHOR_INVALID")
            for value in expected_threshold_lock_sha256s
        )
        if normalized_locks[0] == normalized_locks[1]:
            raise DatasetVerificationError("INVENTORY_EXTERNAL_ANCHOR_INVALID")
        if expected_access_log_path is None:
            normalized_access_log_path = None
        else:
            normalized_access_log_path = Path(expected_access_log_path)
            if not normalized_access_log_path.is_absolute():
                raise DatasetVerificationError("INVENTORY_EXTERNAL_ANCHOR_INVALID")
    try:
        pinned_root = _PinnedDirectory.open(Path(dataset_root))
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_DATASET_ROOT_INVALID") from error
    with pinned_root:
        root = pinned_root.path
        inventory_payload = _read_regular_bound_file(
            root, "inventory.json", pinned_root=pinned_root
        )
        try:
            document = json.loads(inventory_payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID") from error
        try:
            canonical = canonical_json_bytes(document)
        except (TypeError, ValueError) as error:
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID") from error
        if (
            not isinstance(document, Mapping)
            or set(document) != _INVENTORY_KEYS
            or canonical != inventory_payload
        ):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
        inventory_sha = hashlib.sha256(inventory_payload).hexdigest()
        if inventory_sha != expected_inventory_sha256:
            raise DatasetVerificationError("INVENTORY_EXTERNAL_ANCHOR_MISMATCH")
        sidecar = _read_regular_bound_file(root, "inventory.sha256", pinned_root=pinned_root)
        if sidecar != f"{inventory_sha}  inventory.json\n".encode("ascii"):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")

        split = document.get("split")
        if split not in {"val", "test"}:
            raise DatasetVerificationError("SPLIT_INVALID")
        if split != expected_split:
            raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
        archive_sha = _require_sha256(document.get("archive_sha256"), "INVENTORY_INTEGRITY_INVALID")
        if archive_sha != expected_archive_sha256:
            raise DatasetVerificationError("INVENTORY_EXTERNAL_ANCHOR_MISMATCH")
        sample_count = document.get("sample_count")
        scenario_counts = document.get("scenario_counts")
        raw_samples = document.get("samples")
        if (
            type(sample_count) is not int
            or sample_count != _EXPECTED_SAMPLE_COUNT
            or not isinstance(scenario_counts, Mapping)
            or set(scenario_counts) != set(_EXPECTED_SCENARIO_COUNTS)
            or any(
                type(value) is not int or value != _EXPECTED_SCENARIO_COUNTS[key]
                for key, value in scenario_counts.items()
            )
            or document.get("rasterizer") != _RASTERIZER
            or not isinstance(raw_samples, list)
            or len(raw_samples) != _EXPECTED_SAMPLE_COUNT
        ):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")

        samples: list[DatasetSampleRef] = []
        for expected_index, raw_sample in enumerate(raw_samples):
            if not isinstance(raw_sample, Mapping) or set(raw_sample) != _SAMPLE_KEYS:
                raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
            if (
                type(raw_sample.get("formal_sample_index")) is not int
                or raw_sample.get("formal_sample_index") != expected_index
                or raw_sample.get("split") != split
                or raw_sample.get("scenario") not in _EXPECTED_SCENARIO_COUNTS
                or type(raw_sample.get("truth_count")) is not int
                or raw_sample.get("truth_count") < 0
            ):
                raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
            for name in ("image_relpath", "label_relpath", "truth_relpath"):
                if not isinstance(raw_sample.get(name), str):
                    raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
            for name in ("image_sha256", "label_sha256", "truth_sha256"):
                _require_sha256(raw_sample.get(name), "INVENTORY_INTEGRITY_INVALID")
            samples.append(
                DatasetSampleRef(
                    formal_sample_index=expected_index,
                    split=split,
                    scenario=raw_sample["scenario"],
                    image_relpath=raw_sample["image_relpath"],
                    label_relpath=raw_sample["label_relpath"],
                    truth_relpath=raw_sample["truth_relpath"],
                    image_sha256=raw_sample["image_sha256"],
                    truth_count=raw_sample["truth_count"],
                )
            )
        if [sample.image_sha256 for sample in samples] != sorted(
            sample.image_sha256 for sample in samples
        ) or len({sample.image_sha256 for sample in samples}) != len(samples):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")

        test_access = document.get("test_access")
        if split == "test":
            if not isinstance(test_access, Mapping):
                raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
            event_sha = _require_sha256(
                test_access.get("event_sha256"), "INVENTORY_ACCESS_CHAIN_INVALID"
            )
            sealed_sha = _require_sha256(
                test_access.get("sealed_member_inventory_sha256"),
                "INVENTORY_ACCESS_CHAIN_INVALID",
            )
            raw_locks = test_access.get("threshold_lock_sha256s")
            if not isinstance(raw_locks, list) or len(raw_locks) != 2:
                raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
            persisted_locks = tuple(
                _require_sha256(value, "INVENTORY_ACCESS_CHAIN_INVALID") for value in raw_locks
            )
            if (
                event_sha != normalized_event_sha
                or sealed_sha != normalized_sealed_sha
                or persisted_locks != normalized_locks
            ):
                raise DatasetVerificationError("INVENTORY_EXTERNAL_ANCHOR_MISMATCH")
        else:
            if test_access is not None:
                raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
            event_sha = None
        inventory = DatasetInventory(
            schema_version=SCHEMA_VERSION,
            split=split,
            archive_sha256=archive_sha,
            inventory_sha256=inventory_sha,
            dataset_root=root,
            sample_count=sample_count,
            scenario_counts=dict(scenario_counts),
            samples=tuple(samples),
            test_access_event_sha256=event_sha,
            access_log_path=normalized_access_log_path,
        )
        _verify_inventory_and_tree(
            root,
            split,
            inventory,
            pinned_root=pinned_root,
            require_capability=False,
            require_exact_core_tree=True,
        )
        _issue_inventory(inventory)
        return inventory


def _verify_complete_truth_mask_tree(
    pinned_root: _PinnedDirectory,
    inventory: DatasetInventory,
    truth_payloads: Mapping[str, bytes],
    samples: tuple[TruthSample, ...],
) -> None:
    verified_paths = _verify_exact_dataset_tree(
        pinned_root,
        inventory,
        truth_payloads,
        require_truth_masks=True,
    )
    _verify_truth_mask_refs(samples, verified_paths)


def _metadata_identity(metadata: os.stat_result | None) -> tuple[int, int] | None:
    if metadata is None:
        return None
    return metadata.st_dev, metadata.st_ino


def _publish_truth_masks(
    pinned_root: _PinnedDirectory,
    split: Split,
    inventory: DatasetInventory,
    truth_payloads: Mapping[str, bytes],
    samples: tuple[TruthSample, ...],
    mask_artifacts: tuple[tuple[Path, dict[str, object], MaskRef], ...],
) -> None:
    try:
        destination = pinned_root.child_metadata("truth_masks")
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH") from error
    if destination is not None:
        _verify_complete_truth_mask_tree(
            pinned_root,
            inventory,
            truth_payloads,
            samples,
        )
        return

    staging: _PinnedDirectory | None = None
    try:
        staging_name, staging = pinned_root.create_random_pinned_child(".truth-masks-stage-")
        staging_identity = staging._identity
        split_directory = staging.create_pinned_child(
            split,
            mode=0o700,
            fsync_parent=False,
        )
        with split_directory:
            for relative_path, document, _ in mask_artifacts:
                filename = relative_path.name
                split_directory.write_new_file(filename, canonical_json_bytes(document))
            split_directory.fsync()
        staging.fsync()
        if _metadata_identity(pinned_root.child_metadata(staging_name)) != (staging_identity):
            raise _PinnedFileError("bound staging entry moved before publication")
        try:
            _rename_directory_noreplace(
                pinned_root._descriptor,
                staging_name,
                pinned_root._descriptor,
                "truth_masks",
            )
        except OSError as error:
            raise _PinnedFileError("atomic no-replace publication failed") from error
        if (
            pinned_root.child_metadata(staging_name) is not None
            or _metadata_identity(pinned_root.child_metadata("truth_masks")) != staging_identity
        ):
            raise _PinnedFileError("published truth mask identity is invalid")
        pinned_root.fsync()
    except _PinnedFileError as error:
        raise DatasetVerificationError("TRUTH_MASK_PUBLISH_FAILED") from error
    finally:
        if staging is not None:
            staging.close()

    _verify_complete_truth_mask_tree(
        pinned_root,
        inventory,
        truth_payloads,
        samples,
    )


def load_truth_samples(
    dataset_root: Path,
    split: Split,
    inventory: DatasetInventory,
) -> tuple[TruthSample, ...]:
    _require_rasterizer_version()
    if split not in {"val", "test"}:
        raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
    if split == "test" and inventory.test_access_event_sha256 is None:
        raise DatasetVerificationError("TEST_SEALED")
    try:
        pinned_root = _PinnedDirectory.open(Path(dataset_root))
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_DATASET_ROOT_INVALID") from error
    with pinned_root:
        truth_payloads = _verify_inventory_and_tree(
            pinned_root.path,
            split,
            inventory,
            pinned_root=pinned_root,
        )
        samples, mask_artifacts = _derive_truth_artifacts(inventory, split, truth_payloads)
        _publish_truth_masks(
            pinned_root,
            split,
            inventory,
            truth_payloads,
            samples,
            mask_artifacts,
        )
        return samples
