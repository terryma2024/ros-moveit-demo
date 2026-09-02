from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable

import numpy as np
import pytest
import so101_demo.perception_benchmark.dataset as dataset_module
from PIL import Image
from so101_demo.perception_benchmark.codec import read_mask
from so101_demo.perception_benchmark.contracts import TruthSample
from so101_demo.perception_benchmark.dataset import (
    DatasetArchiveVerifier,
    DatasetVerificationError,
    load_dataset_inventory,
    load_truth_samples,
    rasterize_polygon,
    sha256_file,
)
from so101_demo.perception_benchmark.dataset import (
    TestAccessGrant as DatasetTestAccessGrant,
)
from so101_demo.perception_benchmark.dataset import (
    TestSeal as DatasetTestSeal,
)

SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
)
_POLYGON = ((0.25, 0.25), (0.75, 0.25), (0.5, 0.75))


def _png_bytes(index: int, *, width: int = 640, height: int = 480) -> bytes:
    image = Image.new(
        "RGB",
        (width, height),
        ((index >> 16) & 255, (index >> 8) & 255, index & 255),
    )
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _truth_and_label(index: int, scenario: str) -> tuple[bytes, bytes]:
    count = {
        "no_cup": 0,
        "one_cup_distractors": 1,
        "two_cups": 2,
        "cup_near_bottle": 1,
    }[scenario]
    instances = [
        {
            "body_id": instance_index + 1,
            "body_name": "plastic_cup" if instance_index == 0 else "plastic_cup_b",
            "visible_pixel_count": 3,
            "polygon_xy": [list(point) for point in _POLYGON],
        }
        for instance_index in range(count)
    ]
    truth = {
        "seed": 300000 + index,
        "split": "test",
        "scenario": scenario,
        "configured_cup_count": count,
        "visible_instance_count": count,
        "instances": instances,
    }
    label_line = "0 0.25 0.25 0.75 0.25 0.5 0.75\n"
    return (
        (json.dumps(truth, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        (label_line * count).encode(),
    )


def _add_bytes(
    archive: tarfile.TarFile,
    name: str,
    payload: bytes,
    *,
    mtime: int = 1,
) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    member.mtime = mtime
    archive.addfile(member, BytesIO(payload))


def build_fixture_archive(
    tmp_path: Path,
    *,
    split_count: int = 200,
    include_val: bool = False,
    semantic_payloads: bool = True,
    image_size: tuple[int, int] = (640, 480),
    duplicate_image_sha: bool = False,
    scenario_for_index: Callable[[int], str] | None = None,
    label_mismatch: bool = False,
    payload_marker: bytes = b"",
    image_offset: int = 0,
    extra_member_payload: bytes | None = None,
) -> Path:
    archive_path = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        splits = ("test", "val") if include_val else ("test",)
        for split in splits:
            for index in range(split_count):
                stem = f"{(300000 if split == 'test' else 200000) + index:09d}"
                prefix = "dataset"
                if not semantic_payloads:
                    image_payload = b"not-a-png" + payload_marker
                    truth_payload = (
                        b"not-json: scenario polygon truth_count" + payload_marker
                    )
                    label_payload = b"not-a-label" + payload_marker
                else:
                    image_index = 0 if duplicate_image_sha else index
                    image_payload = _png_bytes(
                        image_index
                        + image_offset
                        + (1000 if split == "val" else 0),
                        width=image_size[0],
                        height=image_size[1],
                    )
                    scenario = (
                        scenario_for_index(index)
                        if scenario_for_index is not None
                        else SCENARIOS[index % len(SCENARIOS)]
                    )
                    truth_payload, label_payload = _truth_and_label(index, scenario)
                    if split == "val":
                        document = json.loads(truth_payload)
                        document["seed"] = 200000 + index
                        document["split"] = "val"
                        truth_payload = (
                            json.dumps(document, sort_keys=True, separators=(",", ":"))
                            + "\n"
                        ).encode()
                    if label_mismatch and index == 0:
                        label_payload = b"0 0.1 0.1 0.2 0.1 0.15 0.2\n"
                _add_bytes(archive, f"{prefix}/images/{split}/{stem}.png", image_payload)
                _add_bytes(archive, f"{prefix}/labels/{split}/{stem}.txt", label_payload)
                _add_bytes(archive, f"{prefix}/truth/{split}/{stem}.json", truth_payload)
        if extra_member_payload is not None:
            _add_bytes(
                archive,
                "dataset/metadata/build.txt",
                extra_member_payload,
            )
    return archive_path


def _unlocked_seal(tmp_path: Path, sealed_sha: str = "a" * 64) -> DatasetTestSeal:
    return DatasetTestSeal(sealed_sha, tmp_path / "test-access.jsonl").unlock(
        tmp_path / "yolo-lock.json",
        tmp_path / "grounded-lock.json",
        verify_lock=lambda path: {
            "yolo-lock.json": "b" * 64,
            "grounded-lock.json": "c" * 64,
        }[path.name],
    )


def _verified_unlocked_seal(
    archive: Path,
    tmp_path: Path,
    *,
    suffix: str = "",
) -> DatasetTestSeal:
    inventory = DatasetArchiveVerifier().verify_archive(
        archive,
        sha256_file(archive),
        tmp_path / f"sealed{suffix}.json",
    )
    return DatasetTestSeal(
        inventory.sealed_test_member_inventory_sha256,
        tmp_path / f"test-access{suffix}.jsonl",
    ).unlock(
        tmp_path / f"yolo-lock{suffix}.json",
        tmp_path / f"grounded-lock{suffix}.json",
        verify_lock=lambda path: (
            "b" * 64 if path.name.startswith("yolo-lock") else "c" * 64
        ),
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
        DatasetArchiveVerifier().verify_archive(
            archive, "0" * 64, tmp_path / "sealed.json"
        )


def test_archive_verification_refuses_existing_seal_output(tmp_path: Path) -> None:
    archive = build_fixture_archive(tmp_path, semantic_payloads=False)
    sealed = tmp_path / "sealed.json"
    sealed.write_text("preserve-me\n", encoding="utf-8")

    with pytest.raises(DatasetVerificationError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        DatasetArchiveVerifier().verify_archive(
            archive, sha256_file(archive), sealed
        )

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
    monkeypatch.setattr(dataset_module.PIL, "__version__", "12.2.0")

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
    first = build_fixture_archive(
        first_root, semantic_payloads=False, payload_marker=b"-first"
    )
    second = build_fixture_archive(
        second_root, semantic_payloads=False, payload_marker=b"-second"
    )
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


def test_archive_path_replacement_during_open_fails_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    archive = build_fixture_archive(first_root, include_val=True)
    replacement = build_fixture_archive(
        second_root, include_val=True, image_offset=5000
    )
    expected_sha = sha256_file(archive)
    real_tar_open = tarfile.open
    replaced = False

    def open_then_replace(*args: object, **kwargs: object) -> tarfile.TarFile:
        nonlocal replaced
        opened = real_tar_open(*args, **kwargs)
        if not replaced:
            os.replace(replacement, archive)
            replaced = True
        return opened

    monkeypatch.setattr(dataset_module.tarfile, "open", open_then_replace)

    with pytest.raises(
        DatasetVerificationError, match="ARCHIVE_CHANGED_DURING_VERIFICATION"
    ):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive,
            expected_sha,
            tmp_path / "val-open",
            "val",
            None,
        )

    assert not (tmp_path / "val-open").exists()


def test_truth_mask_publish_failure_is_atomic_and_allows_clean_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    real_write = dataset_module.os.write
    writes = 0

    def fail_third_write(descriptor: int, payload: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes == 3:
            raise OSError("injected mask staging failure")
        return real_write(descriptor, payload)

    monkeypatch.setattr(dataset_module.os, "write", fail_third_write)
    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(tmp_path / "val-open", "val", inventory)

    assert not (tmp_path / "val-open/truth_masks/val").exists()
    assert not any(
        path.name.startswith(".truth-masks-")
        for path in (tmp_path / "val-open").iterdir()
    )
    monkeypatch.setattr(dataset_module.os, "write", real_write)
    truths = load_truth_samples(tmp_path / "val-open", "val", inventory)
    assert len(truths) == 200


def test_truth_mask_publish_failure_preserves_preexisting_empty_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    dataset_root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), dataset_root, "val", None
    )
    mask_parent = dataset_root / "truth_masks"
    mask_parent.mkdir()
    real_replace = dataset_module.os.replace

    def fail_publication(
        source: object,
        destination: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        if destination == "val" and "dst_dir_fd" in kwargs:
            raise OSError("injected final mask publication failure")
        real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(dataset_module.os, "replace", fail_publication)
    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(dataset_root, "val", inventory)

    assert mask_parent.is_dir()
    assert not (mask_parent / "val").exists()
    assert not any(
        path.name.startswith(".truth-masks-") for path in dataset_root.iterdir()
    )


def test_truth_mask_publish_failure_preserves_between_check_creator_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    dataset_root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), dataset_root, "val", None
    )
    mask_parent = dataset_root / "truth_masks"
    real_mkdir = dataset_module.os.mkdir
    injected = False

    def concurrent_creator_then_mkdir(
        path: object,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal injected
        if path == "truth_masks" and dir_fd is not None and not injected:
            injected = True
            real_mkdir(path, mode=mode, dir_fd=dir_fd)
        real_mkdir(path, mode=mode, dir_fd=dir_fd)

    monkeypatch.setattr(dataset_module.os, "mkdir", concurrent_creator_then_mkdir)
    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_truth_samples(dataset_root, "val", inventory)

    assert mask_parent.is_dir()
    assert not (mask_parent / "val").exists()


def test_val_rejects_unlocked_test_seal_without_creating_output(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    seal = _verified_unlocked_seal(archive, tmp_path)

    with pytest.raises(DatasetVerificationError, match="VAL_TEST_SEAL_CONFLICT"):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive,
            sha256_file(archive),
            tmp_path / "val-open",
            "val",
            seal,
        )

    assert not (tmp_path / "val-open").exists()


def _rewrite_inventory_document(root: Path, document: dict[str, object]) -> None:
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    (root / "inventory.json").chmod(0o644)
    (root / "inventory.json").write_bytes(payload)
    (root / "inventory.sha256").chmod(0o644)
    (root / "inventory.sha256").write_text(
        f"{hashlib.sha256(payload).hexdigest()}  inventory.json\n",
        encoding="ascii",
    )


def _public_inventory_anchors(root: Path, split: str) -> dict[str, object]:
    payload = (root / "inventory.json").read_bytes()
    document = json.loads(payload)
    anchors: dict[str, object] = {
        "expected_split": split,
        "expected_archive_sha256": document["archive_sha256"],
        "expected_inventory_sha256": hashlib.sha256(payload).hexdigest(),
    }
    if split == "test":
        access = document["test_access"]
        anchors.update(
            {
                "expected_test_access_event_sha256": access["event_sha256"],
                "expected_sealed_member_inventory_sha256": access[
                    "sealed_member_inventory_sha256"
                ],
                "expected_threshold_lock_sha256s": tuple(
                    access["threshold_lock_sha256s"]
                ),
            }
        )
    return anchors


def test_public_inventory_loader_reconstructs_and_reissues_verified_capability(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )

    inventory = load_dataset_inventory(root, **_public_inventory_anchors(root, "val"))

    assert inventory.dataset_root == root.resolve(strict=True)
    assert inventory.sample_count == 200
    assert inventory.scenario_counts == {
        "no_cup": 50,
        "one_cup_distractors": 50,
        "two_cups": 50,
        "cup_near_bottle": 50,
    }
    assert len(inventory.samples) == 200
    assert inventory._capability is not None
    assert b"capability" not in (root / "inventory.json").read_bytes()


@pytest.mark.parametrize(
    "mutation",
    (
        "extra-top-level",
        "missing-top-level",
        "extra-sample-field",
        "missing-sample-field",
        "path-escape",
        "wrong-split",
        "wrong-rasterizer",
        "wrong-count",
    ),
)
def test_public_inventory_loader_rejects_schema_or_sample_relaxation(
    tmp_path: Path, mutation: str
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    document = json.loads((root / "inventory.json").read_bytes())
    if mutation == "extra-top-level":
        document["extra"] = "forbidden"
    elif mutation == "missing-top-level":
        del document["archive_sha256"]
    elif mutation == "extra-sample-field":
        document["samples"][0]["extra"] = "forbidden"
    elif mutation == "missing-sample-field":
        del document["samples"][0]["truth_sha256"]
    elif mutation == "path-escape":
        document["samples"][0]["image_relpath"] = "../escape.png"
    elif mutation == "wrong-split":
        document["split"] = "training"
    elif mutation == "wrong-rasterizer":
        document["rasterizer"]["version"] = "0"
    else:
        document["sample_count"] = 199
    _rewrite_inventory_document(root, document)

    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(root, **anchors)


def test_public_inventory_loader_rejects_noncanonical_sidecar_tamper_and_symlink(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    canonical = (root / "inventory.json").read_bytes()
    (root / "inventory.json").chmod(0o644)
    (root / "inventory.json").write_bytes(canonical[:-1] + b" \n")
    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(root, **anchors)

    (root / "inventory.json").write_bytes(canonical)
    (root / "inventory.sha256").chmod(0o644)
    (root / "inventory.sha256").write_text("0" * 64 + "  inventory.json\n")
    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(root, **anchors)

    (root / "inventory.sha256").write_text(
        f"{hashlib.sha256(canonical).hexdigest()}  inventory.json\n"
    )
    linked = tmp_path / "linked-dataset"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(linked, **anchors)


def test_public_inventory_loader_rechecks_current_bytes_and_semantics(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    document = json.loads((root / "inventory.json").read_bytes())
    first = document["samples"][0]
    label_path = root / first["label_relpath"]
    label_path.chmod(0o644)
    label_path.write_text("0 0.1 0.1 0.2 0.1 0.15 0.2\n", encoding="utf-8")
    first["label_sha256"] = hashlib.sha256(label_path.read_bytes()).hexdigest()
    _rewrite_inventory_document(root, document)
    anchors["expected_inventory_sha256"] = hashlib.sha256(
        (root / "inventory.json").read_bytes()
    ).hexdigest()

    with pytest.raises(
        DatasetVerificationError, match="LABEL_TRUTH_POLYGON_MISMATCH"
    ):
        load_dataset_inventory(root, **anchors)


def test_public_inventory_loader_binds_loaded_object_to_original_tree(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    original = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), original, "val", None
    )
    inventory = load_dataset_inventory(
        original, **_public_inventory_anchors(original, "val")
    )
    moved = tmp_path / "moved-val-open"
    original.rename(moved)

    with pytest.raises(DatasetVerificationError):
        load_truth_samples(moved, "val", inventory)


def test_public_test_inventory_loader_rejects_changed_access_or_lock_chain(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path)
    seal = _verified_unlocked_seal(archive, tmp_path)
    root = tmp_path / "test-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "test", seal
    )
    assert seal.access_grant is not None
    anchors = _public_inventory_anchors(root, "test")
    access_log = seal.access_log_path
    access_log.write_bytes(access_log.read_bytes() + b"{}\n")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_ACCESS_CHAIN_INVALID"):
        load_dataset_inventory(root, **anchors)

    access_log.write_bytes(access_log.read_bytes()[:-3])
    document = json.loads((root / "inventory.json").read_bytes())
    document["test_access"]["threshold_lock_sha256s"][0] = "d" * 64
    _rewrite_inventory_document(root, document)
    with pytest.raises(DatasetVerificationError, match="INVENTORY_EXTERNAL_ANCHOR_MISMATCH"):
        load_dataset_inventory(root, **anchors)


def test_round1_public_inventory_loader_requires_all_external_val_anchors(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )

    with pytest.raises(TypeError):
        load_dataset_inventory(root)


def test_round1_public_inventory_loader_rejects_coherent_self_attested_rewrite_before_issuance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = build_fixture_archive(tmp_path)
    seal = _verified_unlocked_seal(archive, tmp_path)
    root = tmp_path / "test-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "test", seal
    )
    assert seal.access_grant is not None
    original_inventory_sha = hashlib.sha256(
        (root / "inventory.json").read_bytes()
    ).hexdigest()
    document = json.loads((root / "inventory.json").read_bytes())
    original_archive_sha = document["archive_sha256"]
    original_event_sha = document["test_access"]["event_sha256"]
    original_sealed_sha = document["test_access"][
        "sealed_member_inventory_sha256"
    ]
    original_locks = tuple(document["test_access"]["threshold_lock_sha256s"])
    document["archive_sha256"] = "d" * 64
    document["test_access"]["sealed_member_inventory_sha256"] = "e" * 64
    document["test_access"]["threshold_lock_sha256s"] = ["f" * 64, "9" * 64]
    event_without_sha = {
        "event_type": "TEST_ACCESS_GRANTED",
        "granted_at": document["test_access"]["granted_at"],
        "sealed_member_inventory_sha256": "e" * 64,
        "threshold_lock_sha256s": ["f" * 64, "9" * 64],
    }
    rewritten_event_sha = hashlib.sha256(
        dataset_module.canonical_json_bytes(event_without_sha)
    ).hexdigest()
    document["test_access"]["event_sha256"] = rewritten_event_sha
    seal.access_log_path.write_bytes(
        dataset_module.canonical_json_bytes(
            {**event_without_sha, "event_sha256": rewritten_event_sha}
        )
    )
    _rewrite_inventory_document(root, document)

    def forbidden_issue(inventory: object) -> None:
        raise RuntimeError("capability issued before external anchors verified")

    monkeypatch.setattr(dataset_module, "_issue_inventory", forbidden_issue)
    with pytest.raises(DatasetVerificationError, match="INVENTORY_EXTERNAL_ANCHOR_MISMATCH"):
        load_dataset_inventory(
            root,
            expected_split="test",
            expected_archive_sha256=original_archive_sha,
            expected_inventory_sha256=original_inventory_sha,
            expected_test_access_event_sha256=original_event_sha,
            expected_sealed_member_inventory_sha256=original_sealed_sha,
            expected_threshold_lock_sha256s=original_locks,
        )


def test_round1_public_val_inventory_rejects_test_access_anchors(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    inventory_payload = (root / "inventory.json").read_bytes()

    with pytest.raises(DatasetVerificationError, match="VAL_EXTERNAL_TEST_ANCHOR_CONFLICT"):
        load_dataset_inventory(
            root,
            expected_split="val",
            expected_archive_sha256=sha256_file(archive),
            expected_inventory_sha256=hashlib.sha256(inventory_payload).hexdigest(),
            expected_test_access_event_sha256="a" * 64,
            expected_sealed_member_inventory_sha256="b" * 64,
            expected_threshold_lock_sha256s=("c" * 64, "d" * 64),
        )


@pytest.mark.parametrize(
    "mutation",
    ("extra-file", "extra-dir", "symlink", "special", "unknown-split", "hardlink"),
)
def test_round1_public_inventory_loader_rejects_every_unreferenced_tree_entry(
    tmp_path: Path, mutation: str
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    inventory_payload = (root / "inventory.json").read_bytes()
    if mutation == "extra-file":
        (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    elif mutation == "extra-dir":
        (root / "extra").mkdir()
    elif mutation == "symlink":
        (root / "extra-link").symlink_to(root / "inventory.json")
    elif mutation == "special":
        os.mkfifo(root / "extra.fifo")
    elif mutation == "unknown-split":
        (root / "images/test").mkdir()
    else:
        os.link(root / "inventory.json", tmp_path / "external-inventory.json")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_dataset_inventory(
            root,
            expected_split="val",
            expected_archive_sha256=sha256_file(archive),
            expected_inventory_sha256=hashlib.sha256(inventory_payload).hexdigest(),
        )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is unavailable")
def test_round1_inventory_capability_is_invalidated_across_fork_until_public_reload(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    inventory_sha = hashlib.sha256((root / "inventory.json").read_bytes()).hexdigest()
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
        os.close(read_fd)
        outcome = b"ok"
        try:
            with pytest.raises(DatasetVerificationError, match="INVENTORY_CAPABILITY_INVALID"):
                dataset_module._require_inventory_capability(inventory)
            reloaded = load_dataset_inventory(
                root,
                expected_split="val",
                expected_archive_sha256=sha256_file(archive),
                expected_inventory_sha256=inventory_sha,
            )
            dataset_module._require_inventory_capability(reloaded)
        except BaseException as error:
            outcome = f"error:{type(error).__name__}:{error}".encode()
        os.write(write_fd, outcome)
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    outcome = os.read(read_fd, 4096)
    os.close(read_fd)
    _, status = os.waitpid(child_pid, 0)

    dataset_module._require_inventory_capability(inventory)
    assert os.waitstatus_to_exitcode(status) == 0
    assert outcome == b"ok"


@pytest.mark.parametrize(
    "alias_base",
    (Path("/tmp"), Path(tempfile.gettempdir())),
    ids=("tmp-alias", "default-var-alias"),
)
def test_round2_public_dataset_loader_accepts_macos_system_ancestor_aliases(
    alias_base: Path,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="so101-public-dataset-", dir=alias_base
    ) as temporary:
        workspace = Path(temporary)
        archive = build_fixture_archive(workspace, include_val=True)
        root = workspace / "val-open"
        DatasetArchiveVerifier().verify_and_extract_split(
            archive, sha256_file(archive), root, "val", None
        )

        loaded = load_dataset_inventory(
            root, **_public_inventory_anchors(root, "val")
        )

        assert loaded.dataset_root == root.resolve(strict=True)
        dataset_module._require_inventory_capability(loaded)


def test_round2_pinned_reader_rejects_descendant_modified_during_same_fd_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pinned"
    root.mkdir()
    target = root / "payload.bin"
    target.write_bytes(b"stable payload")
    real_read = dataset_module.os.read
    modified = False

    def mutate_after_read(descriptor: int, count: int) -> bytes:
        nonlocal modified
        payload = real_read(descriptor, count)
        if payload and not modified:
            modified = True
            target.write_bytes(payload + b" drift")
        return payload

    monkeypatch.setattr(dataset_module.os, "read", mutate_after_read)
    with dataset_module._PinnedDirectory.open(root) as pinned:
        with pytest.raises(ValueError, match="changed during pinned read"):
            pinned.read_file("payload.bin")


def test_round2_public_dataset_loader_accepts_complete_derived_truth_tree_and_reuses_it(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    first_truths = load_truth_samples(root, "val", inventory)

    reloaded = load_dataset_inventory(root, **anchors)
    second_truths = load_truth_samples(root, "val", reloaded)

    assert second_truths == first_truths
    dataset_module._require_inventory_capability(reloaded)


@pytest.mark.parametrize(
    "mutation",
    ("partial", "missing", "extra", "wrong-split", "symlink", "hardlink", "tamper"),
)
def test_round2_public_dataset_loader_rejects_incomplete_or_tampered_truth_mask_tree(
    tmp_path: Path, mutation: str
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    load_truth_samples(root, "val", inventory)
    mask_root = root / "truth_masks/val"
    mask_paths = sorted(mask_root.iterdir())
    first_mask = mask_paths[0]
    if mutation == "partial":
        first_mask.unlink()
    elif mutation == "missing":
        mask_root.rename(tmp_path / "removed-val-masks")
    elif mutation == "extra":
        (mask_root / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "wrong-split":
        mask_root.rename(mask_root.parent / "test")
    elif mutation == "symlink":
        outside = tmp_path / "outside-mask.json"
        outside.write_bytes(first_mask.read_bytes())
        first_mask.unlink()
        first_mask.symlink_to(outside)
    elif mutation == "hardlink":
        os.link(first_mask, tmp_path / "external-mask.json")
    else:
        first_mask.chmod(0o644)
        first_mask.write_bytes(first_mask.read_bytes() + b"tamper")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_dataset_inventory(root, **anchors)


def test_round3_truth_loader_rejects_symlink_mask_parent_without_touching_outside(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.bin"
    sentinel.write_bytes(b"outside must remain unchanged")
    (root / "truth_masks").symlink_to(outside, target_is_directory=True)
    before = tuple(
        (path.relative_to(outside).as_posix(), path.read_bytes())
        for path in sorted(outside.rglob("*"))
        if path.is_file()
    )

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_truth_samples(root, "val", inventory)

    after = tuple(
        (path.relative_to(outside).as_posix(), path.read_bytes())
        for path in sorted(outside.rglob("*"))
        if path.is_file()
    )
    assert after == before
    assert not (outside / "val").exists()


def test_round3_truth_loader_fails_closed_if_mask_parent_name_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    mask_parent = root / "truth_masks"
    mask_parent.mkdir()
    held_parent = root / "truth_masks-held"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.bin"
    sentinel.write_bytes(b"outside must remain unchanged")
    real_replace = dataset_module.os.replace
    swapped = False

    def swap_parent_before_publish(
        source: object,
        destination: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal swapped
        descriptor_relative_publish = (
            destination == "val" and "dst_dir_fd" in kwargs
        )
        if not swapped and (
            Path(destination) == mask_parent / "val"
            or descriptor_relative_publish
        ):
            swapped = True
            mask_parent.rename(held_parent)
            mask_parent.symlink_to(outside, target_is_directory=True)
        real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(dataset_module.os, "replace", swap_parent_before_publish)

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_truth_samples(root, "val", inventory)

    assert sentinel.read_bytes() == b"outside must remain unchanged"
    assert not (outside / "val").exists()


def test_round3_truth_loader_binds_alias_root_by_pinned_identity() -> None:
    with tempfile.TemporaryDirectory(
        prefix="so101-public-truth-", dir=Path("/tmp")
    ) as temporary:
        workspace = Path(temporary)
        archive = build_fixture_archive(workspace, include_val=True)
        root = workspace / "val-open"
        DatasetArchiveVerifier().verify_and_extract_split(
            archive, sha256_file(archive), root, "val", None
        )
        anchors = _public_inventory_anchors(root, "val")

        first_inventory = load_dataset_inventory(root, **anchors)
        first_truths = load_truth_samples(root, "val", first_inventory)
        second_inventory = load_dataset_inventory(root, **anchors)
        second_truths = load_truth_samples(root, "val", second_inventory)

        assert first_inventory.dataset_root == root.resolve(strict=True)
        assert second_inventory.dataset_root == root.resolve(strict=True)
        assert second_truths == first_truths
