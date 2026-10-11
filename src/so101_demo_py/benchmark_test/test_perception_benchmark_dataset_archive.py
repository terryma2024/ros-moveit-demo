"""Archive inventory, extraction, the test grant and the access event."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile

import numpy as np
from perception_benchmark_dataset_support import (
    _add_bytes,
    _skip_what_needs_the_pinned_rasterizer,  # noqa: F401  (pytest fixtures)
    _verified_unlocked_seal,
    build_fixture_archive,
)
import PIL
import pytest

from so101_demo.perception_benchmark.codec import read_mask
from so101_demo.perception_benchmark.contracts import TruthSample
from so101_demo.perception_benchmark.dataset.contracts import DatasetVerificationError, sha256_file
from so101_demo.perception_benchmark.dataset.contracts import (
    TestAccessGrant as DatasetTestAccessGrant,
)
from so101_demo.perception_benchmark.dataset.contracts import TestSeal as DatasetTestSeal
from so101_demo.perception_benchmark.dataset.loading import (
    load_truth_samples,
)
from so101_demo.perception_benchmark.dataset.truth import rasterize_polygon
from so101_demo.perception_benchmark.dataset.verifier import DatasetArchiveVerifier


def _unlocked_seal(tmp_path: Path, sealed_sha: str = "a" * 64) -> DatasetTestSeal:
    return DatasetTestSeal(sealed_sha, tmp_path / "test-access.jsonl").unlock(
        tmp_path / "yolo-lock.json",
        tmp_path / "grounded-lock.json",
        verify_lock=lambda path: {
            "yolo-lock.json": "b" * 64,
            "grounded-lock.json": "c" * 64,
        }[path.name],
    )


def test_polygon_rule_is_round_half_up_and_includes_pillow_boundary() -> None:
    polygon = ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0))

    mask = rasterize_polygon(polygon, width=5, height=5)

    assert mask.dtype == np.bool_
    assert mask.tolist() == [
        [True, True, True, True, True],
        [False, True, True, True, False],
        [False, True, True, True, False],
        [False, False, True, False, False],
        [False, False, True, False, False],
    ]


def test_prelock_archive_inventory_hashes_opaque_test_bytes(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)

    inventory = DatasetArchiveVerifier().verify_archive(
        archive, sha256_file(archive), tmp_path / "sealed-test-members.json"
    )

    assert inventory.test_triplet_count == 200
    assert inventory.test_scenario_counts is None
    assert inventory.safe_member_count == 600
    assert not (tmp_path / "test-open").exists()
    sealed_document = json.loads(
        (tmp_path / "sealed-test-members.json").read_text(encoding="utf-8")
    )
    assert sealed_document["split"] == "test"
    assert len(sealed_document["members"]) == 600
    assert all(set(member) == {"path", "sha256", "size"} for member in sealed_document["members"])
    serialized = json.dumps(sealed_document)
    assert "scenario" not in serialized
    assert "polygon" not in serialized
    assert "truth_count" not in serialized


def test_archive_rejects_path_traversal_before_writing_seal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        _add_bytes(stream, "dataset/../../escape", b"escape")

    with pytest.raises(DatasetVerificationError, match="ARCHIVE_PATH_UNSAFE"):
        DatasetArchiveVerifier().verify_archive(
            archive, sha256_file(archive), tmp_path / "sealed.json"
        )

    assert not (tmp_path / "sealed.json").exists()


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_archive_rejects_links(tmp_path: Path, link_kind: str) -> None:
    archive = tmp_path / f"{link_kind}.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("dataset/images/test/link.png")
        member.type = tarfile.SYMTYPE if link_kind == "symlink" else tarfile.LNKTYPE
        member.linkname = "dataset/images/test/000300000.png"
        stream.addfile(member)

    with pytest.raises(DatasetVerificationError, match="ARCHIVE_PATH_UNSAFE"):
        DatasetArchiveVerifier().verify_archive(
            archive, sha256_file(archive), tmp_path / "sealed.json"
        )


def test_archive_rejects_199_test_triplets(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, split_count=199, semantic_payloads=False)

    with pytest.raises(DatasetVerificationError, match="TEST_MEMBER_COUNT_INVALID"):
        DatasetArchiveVerifier().verify_archive(
            archive, sha256_file(archive), tmp_path / "sealed.json"
        )


def test_archive_hash_mismatch_fails_before_tar_inspection(tmp_path: Path) -> None:
    archive = tmp_path / "not-even-a-tar"
    archive.write_bytes(b"opaque")

    with pytest.raises(DatasetVerificationError, match="DATASET_ARCHIVE_HASH_MISMATCH"):
        DatasetArchiveVerifier().verify_archive(archive, "0" * 64, tmp_path / "sealed.json")


def test_archive_verification_refuses_existing_seal_output(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)
    sealed = tmp_path / "sealed.json"
    sealed.write_text("preserve-me\n", encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        DatasetArchiveVerifier().verify_archive(archive, sha256_file(archive), sealed)

    assert sealed.read_text(encoding="utf-8") == "preserve-me\n"


def test_test_extraction_requires_two_verified_threshold_locks(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)
    seal = DatasetTestSeal("a" * 64, tmp_path / "test-access.jsonl")

    with pytest.raises(DatasetVerificationError, match="TEST_SEALED"):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive, sha256_file(archive), tmp_path / "test-open", "test", seal
        )

    assert not (tmp_path / "test-open").exists()


def test_verified_locks_open_test_and_validate_exact_histogram(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path)
    seal = _verified_unlocked_seal(archive, tmp_path)

    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "test-open", "test", seal
    )

    assert inventory.sample_count == 200
    assert inventory.scenario_counts == {
        "no_cup": 50,
        "one_cup_distractors": 50,
        "two_cups": 50,
        "cup_near_bottle": 50,
    }
    assert inventory.test_access_event_sha256 == seal.access_grant.event_sha256
    assert [sample.formal_sample_index for sample in inventory.samples] == list(range(200))
    assert [sample.image_sha256 for sample in inventory.samples] == sorted(
        sample.image_sha256 for sample in inventory.samples
    )
    assert all(
        not (tmp_path / "test-open" / sample.image_relpath).stat().st_mode & 0o222
        for sample in inventory.samples
    )
    document = json.loads((tmp_path / "test-open/inventory.json").read_text())
    assert document["test_access"]["event_sha256"] == seal.access_grant.event_sha256
    assert document["test_access"]["threshold_lock_sha256s"] == ["b" * 64, "c" * 64]
    assert document["rasterizer"] == {
        "library": "Pillow",
        "version": "12.3.0",
        "coordinate_scale": "dimension_minus_one",
        "rounding": "floor(x+0.5)",
        "boundary": "ImageDraw.polygon fill=1",
    }
    granted_at = datetime.fromisoformat(seal.access_grant.granted_at).timestamp()
    assert all(
        (tmp_path / "test-open" / sample.image_relpath).stat().st_mtime >= granted_at
        for sample in inventory.samples
    )


def test_val_opens_without_test_grant_and_truth_loader_binds_masks(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)

    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    truths = load_truth_samples(tmp_path / "val-open", "val", inventory)

    assert inventory.sample_count == 200
    assert inventory.test_access_event_sha256 is None
    assert not (tmp_path / "val-open/images/test").exists()
    assert not (tmp_path / "val-open/labels/test").exists()
    assert not (tmp_path / "val-open/truth/test").exists()
    assert len(truths) == 200
    assert all(isinstance(sample, TruthSample) and sample.split == "val" for sample in truths)
    assert all(
        instance.mask.relative_path.startswith("truth_masks/val/")
        and instance.mask.image_width == 640
        and instance.mask.image_height == 480
        for sample in truths
        for instance in sample.instances
    )
    first_mask = next(instance.mask for sample in truths for instance in sample.instances)
    mask_path = tmp_path / "val-open" / first_mask.relative_path
    mask_document = json.loads(mask_path.read_text())
    assert mask_document["size"] == [480, 640]
    assert read_mask(first_mask, tmp_path / "val-open").shape == (480, 640)
    assert not mask_path.stat().st_mode & 0o222


def test_truth_loader_rejects_test_inventory_without_access_event(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive,
        sha256_file(archive),
        tmp_path / "test-open",
        "test",
        _verified_unlocked_seal(archive, tmp_path),
    )
    stripped_inventory = replace(inventory, test_access_event_sha256=None)

    with pytest.raises(DatasetVerificationError, match="TEST_SEALED"):
        load_truth_samples(tmp_path / "test-open", "test", stripped_inventory)

    assert not (tmp_path / "test-open/truth_masks").exists()


def test_extraction_refuses_existing_output_root(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(DatasetVerificationError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive, sha256_file(archive), output, "test", _unlocked_seal(tmp_path)
        )


def test_formal_extraction_rejects_another_pillow_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "opaque.tar.gz"
    archive.write_bytes(b"not inspected before the version gate")
    monkeypatch.setattr(PIL, "__version__", "12.2.0")

    with pytest.raises(DatasetVerificationError, match="RASTERIZER_VERSION_MISMATCH"):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive,
            sha256_file(archive),
            tmp_path / "val-open",
            "val",
            None,
        )

    assert not (tmp_path / "val-open").exists()


@pytest.mark.parametrize(
    ("fixture_overrides", "error_code"),
    [
        ({"image_size": (639, 480)}, "IMAGE_DIMENSIONS_INVALID"),
        ({"duplicate_image_sha": True}, "DUPLICATE_IMAGE_SHA256"),
        ({"scenario_for_index": lambda _: "no_cup"}, "SCENARIO_COUNTS_INVALID"),
        ({"label_mismatch": True}, "LABEL_TRUTH_POLYGON_MISMATCH"),
    ],
)
def test_open_split_rejects_invalid_formal_semantics(
    tmp_path: Path,
    fixture_overrides: dict[str, object],
    error_code: str,
) -> None:
    archive = build_fixture_archive(tmp_path, **fixture_overrides)

    with pytest.raises(DatasetVerificationError, match=error_code):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive,
            sha256_file(archive),
            tmp_path / "test-open",
            "test",
            _verified_unlocked_seal(archive, tmp_path),
        )


def test_open_split_accepts_generator_nine_decimal_label_precision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        globals(),
        "_POLYGON",
        (
            (0.2500000004, 0.2500000004),
            (0.7499999996, 0.2500000004),
            (0.5000000004, 0.7499999996),
        ),
    )
    archive = build_fixture_archive(tmp_path)

    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive,
        sha256_file(archive),
        tmp_path / "test-open",
        "test",
        _verified_unlocked_seal(archive, tmp_path),
    )

    assert len(inventory.samples) == 200


def test_test_access_event_is_hash_linked_and_records_utc_time(tmp_path: Path) -> None:
    seal = _unlocked_seal(tmp_path)

    assert seal.access_grant is not None
    assert seal.access_grant.sealed_member_inventory_sha256 == "a" * 64
    assert seal.access_grant.threshold_lock_sha256s == ("b" * 64, "c" * 64)
    assert datetime.fromisoformat(seal.access_grant.granted_at).tzinfo == timezone.utc
    event = json.loads((tmp_path / "test-access.jsonl").read_text())
    unhashed = dict(event)
    event_sha = unhashed.pop("event_sha256")
    canonical = (json.dumps(unhashed, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert event_sha == hashlib.sha256(canonical).hexdigest()
    assert event_sha == seal.access_grant.event_sha256


def test_inventory_and_seal_records_are_immutable(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)
    inventory = DatasetArchiveVerifier().verify_archive(
        archive, sha256_file(archive), tmp_path / "sealed.json"
    )

    with pytest.raises(FrozenInstanceError):
        inventory.test_triplet_count = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        seal = DatasetTestSeal("a" * 64, tmp_path / "events.jsonl")
        seal.access_grant = None  # type: ignore[misc]


@pytest.mark.parametrize(
    ("event_sha", "lock_shas"),
    [
        ("z" * 64, ("b" * 64, "c" * 64)),
        ("d" * 64, ("b" * 64, "b" * 64)),
    ],
)
def test_access_grant_constructor_rejects_invalid_or_duplicate_shas(
    event_sha: str,
    lock_shas: tuple[str, str],
) -> None:
    with pytest.raises(DatasetVerificationError, match="TEST_ACCESS_GRANT_INVALID"):
        DatasetTestAccessGrant(
            event_sha,
            "a" * 64,
            lock_shas,
            "2026-09-02T12:00:00+00:00",
        )


def test_test_seal_rejects_fabricated_grant_without_issued_capability(
    tmp_path: Path,
) -> None:
    forged = DatasetTestAccessGrant(
        "d" * 64,
        "a" * 64,
        ("b" * 64, "c" * 64),
        "2026-09-02T12:00:00+00:00",
    )

    with pytest.raises(DatasetVerificationError, match="TEST_ACCESS_GRANT_INVALID"):
        DatasetTestSeal("a" * 64, tmp_path / "missing.jsonl", forged)


def test_test_extraction_rejects_tampered_access_event_before_semantics(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)
    seal = _verified_unlocked_seal(archive, tmp_path)
    seal.access_log_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="TEST_ACCESS_EVENT_INVALID"):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive,
            sha256_file(archive),
            tmp_path / "test-open",
            "test",
            seal,
        )

    assert not (tmp_path / "test-open").exists()


def test_test_extraction_rejects_cross_archive_seal_before_semantics(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = build_fixture_archive(first_root, semantic_payloads=False, payload_marker=b"-first")
    second = build_fixture_archive(second_root, semantic_payloads=False, payload_marker=b"-second")
    seal = _verified_unlocked_seal(first, tmp_path)

    with pytest.raises(DatasetVerificationError, match="TEST_SEAL_ARCHIVE_MISMATCH"):
        DatasetArchiveVerifier().verify_and_extract_split(
            second,
            sha256_file(second),
            tmp_path / "test-open",
            "test",
            seal,
        )

    assert not (tmp_path / "test-open").exists()


def test_test_extraction_rejects_identical_test_subtree_from_different_archive(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = build_fixture_archive(
        first_root,
        include_val=True,
        extra_member_payload=b"first archive metadata",
    )
    second = build_fixture_archive(
        second_root,
        include_val=True,
        extra_member_payload=b"second archive metadata",
    )
    assert sha256_file(first) != sha256_file(second)
    seal = _verified_unlocked_seal(first, tmp_path)

    with pytest.raises(DatasetVerificationError, match="TEST_SEAL_ARCHIVE_MISMATCH"):
        DatasetArchiveVerifier().verify_and_extract_split(
            second,
            sha256_file(second),
            tmp_path / "test-open",
            "test",
            seal,
        )

    assert not (tmp_path / "test-open").exists()


def test_loader_rejects_fabricated_inventory_capability(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    fabricated = replace(inventory)

    with pytest.raises(DatasetVerificationError, match="INVENTORY_CAPABILITY_INVALID"):
        load_truth_samples(tmp_path / "val-open", "val", fabricated)

    assert not (tmp_path / "val-open/truth_masks").exists()


def test_loader_rejects_issued_inventory_with_mutated_sample_count(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    object.__setattr__(inventory, "sample_count", 199)

    with pytest.raises(DatasetVerificationError, match="INVENTORY_CAPABILITY_INVALID"):
        load_truth_samples(tmp_path / "val-open", "val", inventory)

    assert not (tmp_path / "val-open/truth_masks").exists()


def test_loader_rejects_tampered_inventory_document_and_output_tree(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    inventory_path = tmp_path / "val-open/inventory.json"
    inventory_path.chmod(0o644)
    inventory_path.write_bytes(inventory_path.read_bytes() + b" ")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_INTEGRITY_INVALID"):
        load_truth_samples(tmp_path / "val-open", "val", inventory)

    assert not (tmp_path / "val-open/truth_masks").exists()


def test_loader_rejects_truth_file_drift_before_semantic_parse(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    truth_path = tmp_path / "val-open" / inventory.samples[0].truth_relpath
    truth_path.chmod(0o644)
    truth_path.write_bytes(truth_path.read_bytes() + b" ")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_truth_samples(tmp_path / "val-open", "val", inventory)

    assert not (tmp_path / "val-open/truth_masks").exists()
