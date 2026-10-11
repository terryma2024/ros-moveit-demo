"""The dataset archive verifier and the exact tree and inventory checks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

import numpy as np
from PIL import Image

from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    decode_mask_rle,
    encode_mask_rle,
)
from so101_demo.perception_benchmark.contracts import (
    SCHEMA_VERSION,
    MaskRef,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.dataset.archive import (
    _require_triplets,
    _sealed_test_document,
    _sealed_test_sha,
    _validate_test_chain,
    _VerifiedArchiveSnapshot,
)
from so101_demo.perception_benchmark.dataset.contracts import (
    _EXPECTED_IMAGE_SIZE,
    _EXPECTED_SAMPLE_COUNT,
    _EXPECTED_SCENARIO_COUNTS,
    _INVENTORY_KEYS,
    _KINDS,
    _RASTERIZER,
    _SAMPLE_KEYS,
    ArchiveInventory,
    DatasetInventory,
    DatasetSampleRef,
    DatasetVerificationError,
    Split,
    TestSeal,
    _parse_canonical_access_log,
    _require_sha256,
)
from so101_demo.perception_benchmark.dataset.pinned_files import (
    _classify_member,
    _PinnedDirectory,
    _PinnedFileError,
    _safe_member_path,
)
from so101_demo.perception_benchmark.dataset.truth import (
    _at_label_coordinate_precision,
    _issue_inventory,
    _read_label_polygons_bytes,
    _read_truth_bytes,
    _require_inventory_capability,
    _require_rasterizer_version,
    _truth_polygons,
    rasterize_polygon,
)


class DatasetArchiveVerifier:
    def verify_archive(
        self,
        archive: Path,
        expected_sha256: str,
        sealed_test_inventory_path: Path,
    ) -> ArchiveInventory:
        sealed_path = Path(sealed_test_inventory_path)
        if sealed_path.exists() or sealed_path.is_symlink():
            raise DatasetVerificationError("OUTPUT_ROOT_ALREADY_EXISTS")
        with _VerifiedArchiveSnapshot(Path(archive), expected_sha256) as snapshot:
            _require_triplets(snapshot.classified, "test", _EXPECTED_SAMPLE_COUNT)
            sealed_document = _sealed_test_document(snapshot.classified, snapshot.expected_sha256)
            safe_member_count = len(snapshot.members)
        sealed_sha = atomic_write_json(sealed_path, sealed_document)
        return ArchiveInventory(
            expected_sha256,
            sealed_sha,
            safe_member_count,
            _EXPECTED_SAMPLE_COUNT,
            None,
        )

    def verify_and_extract_split(
        self,
        archive: Path,
        expected_sha256: str,
        output_root: Path,
        split: Split,
        test_seal: TestSeal | None,
    ) -> DatasetInventory:
        root = Path(output_root)
        if root.exists() or root.is_symlink():
            raise DatasetVerificationError("OUTPUT_ROOT_ALREADY_EXISTS")
        if split not in {"val", "test"}:
            raise DatasetVerificationError("SPLIT_INVALID")
        if split == "test" and (test_seal is None or test_seal.access_grant is None):
            raise DatasetVerificationError("TEST_SEALED")
        if split == "val" and test_seal is not None and test_seal.access_grant is not None:
            raise DatasetVerificationError("VAL_TEST_SEAL_CONFLICT")
        _require_rasterizer_version()
        root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent))
        try:
            with _VerifiedArchiveSnapshot(Path(archive), expected_sha256) as snapshot:
                triplets = _require_triplets(snapshot.classified, split, _EXPECTED_SAMPLE_COUNT)
                seal_for_inventory = None
                if split == "test":
                    _validate_test_chain(
                        test_seal,
                        _sealed_test_sha(snapshot.classified, snapshot.expected_sha256),
                    )
                    seal_for_inventory = test_seal
                snapshot.copy_split(staging_root, triplets)
                inventory = self._build_semantic_inventory(
                    staging_root,
                    root,
                    split,
                    expected_sha256,
                    seal_for_inventory,
                )
                snapshot.assert_unchanged()
            if root.exists() or root.is_symlink():
                raise DatasetVerificationError("OUTPUT_ROOT_ALREADY_EXISTS")
            os.replace(staging_root, root)
            _issue_inventory(inventory)
            return inventory
        except DatasetVerificationError:
            raise
        except OSError as error:
            raise DatasetVerificationError("SPLIT_EXTRACTION_FAILED") from error
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root)

    def _build_semantic_inventory(
        self,
        root: Path,
        dataset_root: Path,
        split: Split,
        archive_sha256: str,
        test_seal: TestSeal | None,
    ) -> DatasetInventory:
        records: list[DatasetSampleRef] = []
        sample_documents: list[dict[str, object]] = []
        image_shas: set[str] = set()
        scenarios: Counter[str] = Counter()
        access_grant = None if test_seal is None else test_seal.access_grant
        images = {path.stem: path for path in (root / "images" / split).glob("*.png")}
        labels = {path.stem: path for path in (root / "labels" / split).glob("*.txt")}
        truths = {path.stem: path for path in (root / "truth" / split).glob("*.json")}
        if not (set(images) == set(labels) == set(truths)) or len(images) != _EXPECTED_SAMPLE_COUNT:
            raise DatasetVerificationError("SPLIT_MEMBER_COUNT_INVALID")
        for stem in sorted(images):
            image_path = images[stem]
            try:
                image_payload = image_path.read_bytes()
                label_payload = labels[stem].read_bytes()
                truth_payload = truths[stem].read_bytes()
                with Image.open(BytesIO(image_payload)) as image:
                    size = image.size
                    image.verify()
            except (OSError, ValueError) as error:
                raise DatasetVerificationError("IMAGE_DECODE_FAILED") from error
            if size != _EXPECTED_IMAGE_SIZE:
                raise DatasetVerificationError("IMAGE_DIMENSIONS_INVALID")
            image_sha = hashlib.sha256(image_payload).hexdigest()
            if image_sha in image_shas:
                raise DatasetVerificationError("DUPLICATE_IMAGE_SHA256")
            image_shas.add(image_sha)
            truth = _read_truth_bytes(truth_payload, split)
            label_polygons = _read_label_polygons_bytes(label_payload)
            truth_polygons = _truth_polygons(truth)
            if label_polygons != _at_label_coordinate_precision(truth_polygons):
                raise DatasetVerificationError("LABEL_TRUTH_POLYGON_MISMATCH")
            scenario = truth["scenario"]
            scenarios[scenario] += 1
            record = DatasetSampleRef(
                formal_sample_index=0,
                split=split,
                scenario=scenario,
                image_relpath=image_path.relative_to(root).as_posix(),
                label_relpath=labels[stem].relative_to(root).as_posix(),
                truth_relpath=truths[stem].relative_to(root).as_posix(),
                image_sha256=image_sha,
                truth_count=len(truth_polygons),
            )
            records.append(record)
            sample_documents.append(
                {
                    "record": record,
                    "label_sha256": hashlib.sha256(label_payload).hexdigest(),
                    "truth_sha256": hashlib.sha256(truth_payload).hexdigest(),
                }
            )
        if dict(scenarios) != _EXPECTED_SCENARIO_COUNTS:
            raise DatasetVerificationError("SCENARIO_COUNTS_INVALID")
        ordered = tuple(
            replace(record, formal_sample_index=index)
            for index, record in enumerate(sorted(records, key=lambda item: item.image_sha256))
        )
        raw_hashes_by_image_sha = {
            item["record"].image_sha256: (
                item["label_sha256"],
                item["truth_sha256"],
            )
            for item in sample_documents
        }
        test_access = None
        if split == "test":
            if access_grant is None:
                raise DatasetVerificationError("TEST_SEALED")
            test_access = {
                "event_sha256": access_grant.event_sha256,
                "sealed_member_inventory_sha256": access_grant.sealed_member_inventory_sha256,
                "threshold_lock_sha256s": list(access_grant.threshold_lock_sha256s),
                "granted_at": access_grant.granted_at,
                "access_log_path": str(test_seal.access_log_path),
            }
        document = {
            "schema_version": SCHEMA_VERSION,
            "split": split,
            "archive_sha256": archive_sha256,
            "sample_count": len(ordered),
            "scenario_counts": dict(sorted(scenarios.items())),
            "rasterizer": _RASTERIZER,
            "test_access": test_access,
            "samples": [
                {
                    "formal_sample_index": sample.formal_sample_index,
                    "split": sample.split,
                    "scenario": sample.scenario,
                    "image_relpath": sample.image_relpath,
                    "label_relpath": sample.label_relpath,
                    "truth_relpath": sample.truth_relpath,
                    "image_sha256": sample.image_sha256,
                    "label_sha256": raw_hashes_by_image_sha[sample.image_sha256][0],
                    "truth_sha256": raw_hashes_by_image_sha[sample.image_sha256][1],
                    "truth_count": sample.truth_count,
                }
                for sample in ordered
            ],
        }
        inventory_path = root / "inventory.json"
        inventory_sha = atomic_write_json(inventory_path, document)
        inventory_path.chmod(0o444)
        sha_path = root / "inventory.sha256"
        try:
            with sha_path.open("x", encoding="ascii") as stream:
                stream.write(f"{inventory_sha}  inventory.json\n")
                stream.flush()
                os.fsync(stream.fileno())
            sha_path.chmod(0o444)
        except OSError as error:
            raise DatasetVerificationError("INVENTORY_WRITE_FAILED") from error
        return DatasetInventory(
            SCHEMA_VERSION,
            split,
            archive_sha256,
            inventory_sha,
            dataset_root,
            len(ordered),
            dict(scenarios),
            ordered,
            None if access_grant is None else access_grant.event_sha256,
            None if access_grant is None else test_seal.access_log_path,
        )


def _read_regular_bound_file(
    root: Path,
    relative_path: str,
    *,
    pinned_root: _PinnedDirectory | None = None,
) -> bytes:
    try:
        if pinned_root is not None:
            if Path(os.path.realpath(os.path.abspath(root))) != pinned_root.path:
                raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")
            return pinned_root.read_file(relative_path)
        with _PinnedDirectory.open(root) as opened:
            return opened.read_file(relative_path)
    except DatasetVerificationError:
        raise
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH") from error


def _derive_truth_artifacts(
    inventory: DatasetInventory,
    split: Split,
    truth_payloads: Mapping[str, bytes],
) -> tuple[
    tuple[TruthSample, ...],
    tuple[tuple[Path, dict[str, object], MaskRef], ...],
]:
    validated: list[
        tuple[
            DatasetSampleRef,
            list[dict[str, object]],
            tuple[tuple[tuple[Decimal, Decimal], ...], ...],
        ]
    ] = []
    for sample_ref in inventory.samples:
        truth = _read_truth_bytes(truth_payloads[sample_ref.truth_relpath], split)
        polygons = _truth_polygons(truth)
        raw_instances = truth["instances"]
        if not isinstance(raw_instances, list) or len(raw_instances) != sample_ref.truth_count:
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        normalized_instances: list[dict[str, object]] = []
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            body_name = raw_instance.get("body_name")
            if not isinstance(body_name, str) or not body_name.startswith("plastic_cup"):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            normalized_instances.append(raw_instance)
        if truth["scenario"] != sample_ref.scenario:
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        validated.append((sample_ref, normalized_instances, polygons))

    samples: list[TruthSample] = []
    mask_artifacts: list[tuple[Path, dict[str, object], MaskRef]] = []
    for sample_ref, raw_instances, polygons in validated:
        instances: list[TruthInstance] = []
        stem = Path(sample_ref.truth_relpath).stem
        for instance_index, (raw_instance, decimal_polygon) in enumerate(
            zip(raw_instances, polygons, strict=True)
        ):
            mask = rasterize_polygon(
                tuple((float(x), float(y)) for x, y in decimal_polygon),
                _EXPECTED_IMAGE_SIZE[0],
                _EXPECTED_IMAGE_SIZE[1],
            )
            relative_path = Path("truth_masks") / split / f"{stem}-{instance_index:02d}.json"
            decoded_sha = hashlib.sha256(
                mask.astype(np.uint8, copy=False).tobytes(order="C")
            ).hexdigest()
            body_name = raw_instance["body_name"]
            assert isinstance(body_name, str)
            mask_ref = MaskRef(
                relative_path=relative_path.as_posix(),
                sha256=decoded_sha,
                pixel_count=int(mask.sum()),
                image_width=_EXPECTED_IMAGE_SIZE[0],
                image_height=_EXPECTED_IMAGE_SIZE[1],
            )
            mask_artifacts.append((relative_path, encode_mask_rle(mask), mask_ref))
            instances.append(
                TruthInstance(
                    instance_id=f"{body_name}-{instance_index}",
                    label="plastic_cup",
                    mask=mask_ref,
                )
            )
        samples.append(
            TruthSample(
                formal_sample_index=sample_ref.formal_sample_index,
                split=split,
                scenario=sample_ref.scenario,
                image_relpath=sample_ref.image_relpath,
                image_sha256=sample_ref.image_sha256,
                image_width=_EXPECTED_IMAGE_SIZE[0],
                image_height=_EXPECTED_IMAGE_SIZE[1],
                instances=tuple(instances),
            )
        )
    return tuple(samples), tuple(mask_artifacts)


def _read_pinned_absolute_file(path: Path) -> bytes:
    absolute = Path(os.path.abspath(os.fspath(Path(path))))
    if not absolute.is_absolute():
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
    try:
        if absolute.name == "":
            raise _PinnedFileError("absolute file path is empty")
        with _PinnedDirectory.open(absolute.parent) as parent:
            return parent.read_file(absolute.name)
    except (_PinnedFileError, ValueError) as error:
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID") from error


def _verify_exact_dataset_tree(
    pinned_root: _PinnedDirectory,
    inventory: DatasetInventory,
    truth_payloads: Mapping[str, bytes],
    *,
    require_truth_masks: bool = False,
) -> frozenset[str]:
    core_files = {"inventory.json", "inventory.sha256"}
    for sample in inventory.samples:
        core_files.update((sample.image_relpath, sample.label_relpath, sample.truth_relpath))
    core_directories = {
        parent.as_posix()
        for path in core_files
        for parent in PurePosixPath(path).parents
        if parent.as_posix() != "."
    }
    try:
        actual_files, actual_directories = pinned_root.tree()
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH") from error
    if actual_files == core_files and actual_directories == core_directories:
        if require_truth_masks:
            raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")
        return frozenset()

    _, mask_artifacts = _derive_truth_artifacts(inventory, inventory.split, truth_payloads)
    mask_files = {relative_path.as_posix() for relative_path, _, _ in mask_artifacts}
    expected_files = core_files | mask_files
    expected_directories = {
        parent.as_posix()
        for path in expected_files
        for parent in PurePosixPath(path).parents
        if parent.as_posix() != "."
    }
    if actual_files != expected_files or actual_directories != expected_directories:
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")
    for relative_path, expected_document, mask_ref in mask_artifacts:
        try:
            payload = pinned_root.read_file(relative_path.as_posix())
            document = json.loads(payload)
            if (
                not isinstance(document, Mapping)
                or canonical_json_bytes(document) != payload
                or payload != canonical_json_bytes(expected_document)
            ):
                raise ValueError("mask document is not canonical expected evidence")
            decoded = decode_mask_rle(document)
        except (
            _PinnedFileError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as error:
            raise DatasetVerificationError("INVENTORY_TREE_MISMATCH") from error
        decoded_sha = hashlib.sha256(
            decoded.astype(np.uint8, copy=False).tobytes(order="C")
        ).hexdigest()
        if (
            (decoded.shape[1], decoded.shape[0]) != (mask_ref.image_width, mask_ref.image_height)
            or int(decoded.sum()) != mask_ref.pixel_count
            or decoded_sha != mask_ref.sha256
        ):
            raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")
    return frozenset(mask_files)


def _verify_truth_mask_refs(
    samples: tuple[TruthSample, ...], verified_paths: frozenset[str]
) -> None:
    referenced_paths = {
        instance.mask.relative_path for sample in samples for instance in sample.instances
    }
    if referenced_paths != set(verified_paths) or any(
        not _safe_member_path(path) for path in referenced_paths
    ):
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")


def _validate_persisted_access(
    test_access: object,
    event_sha: str | None,
    access_log_path_override: Path | None = None,
) -> None:
    if not isinstance(test_access, Mapping):
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
    expected_keys = {
        "event_sha256",
        "sealed_member_inventory_sha256",
        "threshold_lock_sha256s",
        "granted_at",
        "access_log_path",
    }
    if set(test_access) != expected_keys:
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
    try:
        persisted_event_sha = _require_sha256(
            test_access["event_sha256"], "INVENTORY_ACCESS_CHAIN_INVALID"
        )
        sealed_sha = _require_sha256(
            test_access["sealed_member_inventory_sha256"],
            "INVENTORY_ACCESS_CHAIN_INVALID",
        )
        raw_locks = test_access["threshold_lock_sha256s"]
        if not isinstance(raw_locks, list) or len(raw_locks) != 2:
            raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
        locks = tuple(
            _require_sha256(value, "INVENTORY_ACCESS_CHAIN_INVALID") for value in raw_locks
        )
        if locks[0] == locks[1] or persisted_event_sha != event_sha:
            raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
        granted_at = test_access["granted_at"]
        access_log_path = test_access["access_log_path"]
        if not isinstance(granted_at, str) or not isinstance(access_log_path, str):
            raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
        parsed_time = datetime.fromisoformat(granted_at)
        if parsed_time.tzinfo is None or parsed_time.utcoffset() != timezone.utc.utcoffset(
            parsed_time
        ):
            raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
    except (TypeError, ValueError) as error:
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID") from error
    without_sha = {
        "event_type": "TEST_ACCESS_GRANTED",
        "granted_at": granted_at,
        "sealed_member_inventory_sha256": sealed_sha,
        "threshold_lock_sha256s": list(locks),
    }
    if hashlib.sha256(canonical_json_bytes(without_sha)).hexdigest() != event_sha:
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
    expected_event = {**without_sha, "event_sha256": event_sha}
    try:
        effective_access_log = (
            Path(access_log_path)
            if access_log_path_override is None
            else access_log_path_override
        )
        events = _parse_canonical_access_log(
            _read_pinned_absolute_file(effective_access_log)
        )
    except DatasetVerificationError as error:
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID") from error
    if events != (expected_event,):
        raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")


def _verify_inventory_and_tree(
    root: Path,
    split: Split,
    inventory: DatasetInventory,
    *,
    pinned_root: _PinnedDirectory | None = None,
    require_capability: bool = True,
    require_exact_core_tree: bool = False,
) -> dict[str, bytes]:
    if require_capability:
        _require_inventory_capability(inventory)
    root_path = Path(os.path.abspath(root))
    if inventory.split != split:
        raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
    owned_pinned = pinned_root is None
    try:
        active_pinned = pinned_root or _PinnedDirectory.open(root_path)
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_DATASET_ROOT_INVALID") from error
    try:
        try:
            if pinned_root is not None:
                with _PinnedDirectory.open(root_path) as requested_root:
                    if not active_pinned.same_identity(requested_root):
                        raise _PinnedFileError("requested root identity differs")
            with _PinnedDirectory.open(inventory.dataset_root) as inventory_root:
                if not active_pinned.same_identity(inventory_root):
                    raise _PinnedFileError("inventory root identity differs")
        except _PinnedFileError as error:
            raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH") from error
        root_path = active_pinned.path
        inventory_payload = _read_regular_bound_file(
            root_path, "inventory.json", pinned_root=active_pinned
        )
        sidecar = _read_regular_bound_file(root_path, "inventory.sha256", pinned_root=active_pinned)
        truth_payloads = _verify_inventory_documents_and_samples(
            root_path,
            split,
            inventory,
            inventory_payload,
            sidecar,
            active_pinned,
        )
        if require_exact_core_tree:
            _verify_exact_dataset_tree(active_pinned, inventory, truth_payloads)
        return truth_payloads
    finally:
        if owned_pinned:
            active_pinned.close()


def _verify_inventory_documents_and_samples(
    root: Path,
    split: Split,
    inventory: DatasetInventory,
    inventory_payload: bytes,
    sidecar: bytes,
    pinned_root: _PinnedDirectory,
) -> dict[str, bytes]:
    try:
        document = json.loads(inventory_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID") from error
    if (
        not isinstance(document, Mapping)
        or set(document) != _INVENTORY_KEYS
        or canonical_json_bytes(document) != inventory_payload
        or hashlib.sha256(inventory_payload).hexdigest() != inventory.inventory_sha256
    ):
        raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
    if sidecar != f"{inventory.inventory_sha256}  inventory.json\n".encode("ascii"):
        raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
    if (
        document.get("schema_version") != inventory.schema_version
        or document.get("split") != split
        or document.get("archive_sha256") != inventory.archive_sha256
        or document.get("sample_count") != inventory.sample_count
        or inventory.sample_count != _EXPECTED_SAMPLE_COUNT
        or document.get("rasterizer") != _RASTERIZER
        or document.get("scenario_counts") != dict(inventory.scenario_counts)
    ):
        raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
    if split == "test":
        _require_sha256(inventory.test_access_event_sha256, "TEST_SEALED")
        _validate_persisted_access(
            document.get("test_access"),
            inventory.test_access_event_sha256,
            inventory.access_log_path,
        )
    elif inventory.test_access_event_sha256 is not None or document.get("test_access") is not None:
        raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
    raw_samples = document.get("samples")
    if (
        not isinstance(raw_samples, list)
        or len(raw_samples) != _EXPECTED_SAMPLE_COUNT
        or len(inventory.samples) != _EXPECTED_SAMPLE_COUNT
    ):
        raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
    if [sample.formal_sample_index for sample in inventory.samples] != list(
        range(_EXPECTED_SAMPLE_COUNT)
    ) or [sample.image_sha256 for sample in inventory.samples] != sorted(
        sample.image_sha256 for sample in inventory.samples
    ):
        raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
    truth_payloads: dict[str, bytes] = {}
    current_image_shas: set[str] = set()
    current_scenarios: Counter[str] = Counter()
    for sample, raw_sample in zip(inventory.samples, raw_samples, strict=True):
        if not isinstance(raw_sample, Mapping) or set(raw_sample) != _SAMPLE_KEYS:
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
        expected_record = {
            "formal_sample_index": sample.formal_sample_index,
            "split": sample.split,
            "scenario": sample.scenario,
            "image_relpath": sample.image_relpath,
            "label_relpath": sample.label_relpath,
            "truth_relpath": sample.truth_relpath,
            "image_sha256": sample.image_sha256,
            "truth_count": sample.truth_count,
        }
        if any(raw_sample.get(key) != value for key, value in expected_record.items()):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
        classifications = tuple(
            _classify_member(path)
            for path in (
                sample.image_relpath,
                sample.label_relpath,
                sample.truth_relpath,
            )
        )
        if (
            any(value is None for value in classifications)
            or {value[0] for value in classifications if value is not None} != set(_KINDS)
            or {value[1] for value in classifications if value is not None} != {split}
            or len({value[2] for value in classifications if value is not None}) != 1
        ):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
        image_payload = _read_regular_bound_file(
            root, sample.image_relpath, pinned_root=pinned_root
        )
        label_payload = _read_regular_bound_file(
            root, sample.label_relpath, pinned_root=pinned_root
        )
        truth_payload = _read_regular_bound_file(
            root, sample.truth_relpath, pinned_root=pinned_root
        )
        if (
            hashlib.sha256(image_payload).hexdigest() != sample.image_sha256
            or hashlib.sha256(label_payload).hexdigest() != raw_sample["label_sha256"]
            or hashlib.sha256(truth_payload).hexdigest() != raw_sample["truth_sha256"]
        ):
            raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")
        try:
            with Image.open(BytesIO(image_payload)) as image:
                image_size = image.size
                image.verify()
        except (OSError, ValueError) as error:
            raise DatasetVerificationError("IMAGE_DECODE_FAILED") from error
        if image_size != _EXPECTED_IMAGE_SIZE:
            raise DatasetVerificationError("IMAGE_DIMENSIONS_INVALID")
        if sample.image_sha256 in current_image_shas:
            raise DatasetVerificationError("DUPLICATE_IMAGE_SHA256")
        current_image_shas.add(sample.image_sha256)
        truth = _read_truth_bytes(truth_payload, split)
        truth_polygons = _truth_polygons(truth)
        if _read_label_polygons_bytes(label_payload) != _at_label_coordinate_precision(
            truth_polygons
        ):
            raise DatasetVerificationError("LABEL_TRUTH_POLYGON_MISMATCH")
        if truth["scenario"] != sample.scenario or len(truth_polygons) != sample.truth_count:
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        current_scenarios[sample.scenario] += 1
        truth_payloads[sample.truth_relpath] = truth_payload
    if dict(current_scenarios) != _EXPECTED_SCENARIO_COUNTS or dict(current_scenarios) != dict(
        inventory.scenario_counts
    ):
        raise DatasetVerificationError("SCENARIO_COUNTS_INVALID")
    return truth_payloads
