"""Archive replacement, truth mask publication and failure cleanup."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import tarfile

from perception_benchmark_dataset_support import (
    _skip_what_needs_the_pinned_rasterizer,  # noqa: F401  (pytest fixtures)
    _verified_unlocked_seal,
    build_fixture_archive,
)
import pytest

from so101_demo.perception_benchmark.dataset import loading as dataset_module_loading
from so101_demo.perception_benchmark.dataset import pinned_files as dataset_module_pinned_files
from so101_demo.perception_benchmark.dataset.contracts import DatasetVerificationError, sha256_file
from so101_demo.perception_benchmark.dataset.loading import (
    load_truth_samples,
)
from so101_demo.perception_benchmark.dataset.verifier import DatasetArchiveVerifier


def test_archive_path_replacement_during_open_fails_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    archive = build_fixture_archive(first_root, include_val=True)
    replacement = build_fixture_archive(second_root, include_val=True, image_offset=5000)
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

    monkeypatch.setattr(tarfile, "open", open_then_replace)

    with pytest.raises(DatasetVerificationError, match="ARCHIVE_CHANGED_DURING_VERIFICATION"):
        DatasetArchiveVerifier().verify_and_extract_split(
            archive,
            expected_sha,
            tmp_path / "val-open",
            "val",
            None,
        )

    assert not (tmp_path / "val-open").exists()


def test_round5_truth_mask_publish_failure_retains_staging_for_explicit_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), tmp_path / "val-open", "val", None
    )
    real_write = os.write
    writes = 0

    def fail_third_write(descriptor: int, payload: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes == 3:
            raise OSError("injected mask staging failure")
        return real_write(descriptor, payload)

    monkeypatch.setattr(os, "write", fail_third_write)
    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(tmp_path / "val-open", "val", inventory)

    assert not (tmp_path / "val-open/truth_masks/val").exists()
    retained = [
        path for path in (tmp_path / "val-open").iterdir() if path.name.startswith(".truth-masks-")
    ]
    assert len(retained) == 1
    staging = retained[0]
    assert len(list((staging / "val").iterdir())) == 3


def test_round5_prestat_substitute_is_retained_when_publication_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "actually-created-staging"
    real_mkdir = os.mkdir
    staging_name: str | None = None
    substitute_identity: tuple[int, int] | None = None

    def substitute_before_first_stat(
        path: object,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal staging_name, substitute_identity
        real_mkdir(path, mode=mode, dir_fd=dir_fd)
        if (
            staging_name is None
            and isinstance(path, str)
            and path.startswith(".truth-masks-stage-")
            and dir_fd is not None
        ):
            staging_name = path
            (root / path).rename(moved)
            real_mkdir(path, mode=0o700, dir_fd=dir_fd)
            metadata = (root / path).stat()
            substitute_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(os, "mkdir", substitute_before_first_stat)
    monkeypatch.setattr(
        dataset_module_loading,
        "_rename_directory_noreplace",
        lambda *args: (_ for _ in ()).throw(OSError(errno.EIO, "injected")),
    )

    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(root, "val", inventory)

    assert staging_name is not None
    assert substitute_identity is not None
    substitute = root / staging_name
    assert substitute.is_dir()
    metadata = substitute.stat()
    assert (metadata.st_dev, metadata.st_ino) == substitute_identity
    assert len(list((substitute / "val").iterdir())) == 200
    assert moved.is_dir()
    assert list(moved.iterdir()) == []


def test_round5_failure_cleanup_never_unlinks_through_a_moved_staging_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "moved-after-identity-check"
    real_unlink = os.unlink
    raced = False
    moved_snapshot: tuple[tuple[str, bytes], ...] | None = None

    def move_staging_after_identity_check(
        path: object,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal moved_snapshot, raced
        if not raced and isinstance(path, str) and dir_fd is not None:
            opened = os.fstat(dir_fd)
            candidates = [
                candidate
                for candidate in root.iterdir()
                if candidate.name.startswith(".truth-masks-stage-")
                and (candidate / "val").is_dir()
                and (
                    (candidate / "val").stat().st_dev,
                    (candidate / "val").stat().st_ino,
                )
                == (opened.st_dev, opened.st_ino)
            ]
            if len(candidates) == 1:
                raced = True
                staging = candidates[0]
                staging.rename(moved)
                staging.mkdir()
                (staging / "unowned-marker.bin").write_bytes(b"keep")
                moved_snapshot = tuple(
                    (item.relative_to(moved).as_posix(), item.read_bytes())
                    for item in sorted(moved.rglob("*"))
                    if item.is_file()
                )
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", move_staging_after_identity_check)
    monkeypatch.setattr(
        dataset_module_loading,
        "_rename_directory_noreplace",
        lambda *args: (_ for _ in ()).throw(OSError(errno.EIO, "injected")),
    )

    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(root, "val", inventory)

    if raced:
        assert moved_snapshot is not None
        current = tuple(
            (item.relative_to(moved).as_posix(), item.read_bytes())
            for item in sorted(moved.rglob("*"))
            if item.is_file()
        )
        assert current == moved_snapshot
    assert not raced
    retained = [path for path in root.iterdir() if path.name.startswith(".truth-masks-stage-")]
    assert len(retained) == 1
    assert len(list((retained[0] / "val").iterdir())) == 200


def test_round5_source_name_swap_at_noreplace_call_fails_closed_inside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "moved-after-precheck"
    real_noreplace = dataset_module_pinned_files._rename_directory_noreplace
    substitute_identity: tuple[int, int] | None = None
    moved_snapshot: tuple[tuple[str, bytes], ...] | None = None

    def swap_source_name_then_call_kernel(
        source_fd: int,
        source_name: str,
        destination_fd: int,
        destination_name: str,
    ) -> None:
        nonlocal moved_snapshot, substitute_identity
        staging = root / source_name
        staging.rename(moved)
        staging.mkdir()
        (staging / "unowned-marker.bin").write_bytes(b"confined inside root")
        substitute = staging.stat()
        substitute_identity = substitute.st_dev, substitute.st_ino
        moved_snapshot = tuple(
            (item.relative_to(moved).as_posix(), item.read_bytes())
            for item in sorted(moved.rglob("*"))
            if item.is_file()
        )
        real_noreplace(
            source_fd,
            source_name,
            destination_fd,
            destination_name,
        )

    monkeypatch.setattr(
        dataset_module_loading,
        "_rename_directory_noreplace",
        swap_source_name_then_call_kernel,
    )

    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(root, "val", inventory)

    assert substitute_identity is not None
    assert moved_snapshot is not None
    installed = root / "truth_masks"
    metadata = installed.stat()
    assert (metadata.st_dev, metadata.st_ino) == substitute_identity
    assert (installed / "unowned-marker.bin").read_bytes() == b"confined inside root"
    current = tuple(
        (item.relative_to(moved).as_posix(), item.read_bytes())
        for item in sorted(moved.rglob("*"))
        if item.is_file()
    )
    assert current == moved_snapshot
    assert len(current) == 200


def test_truth_mask_publication_rejects_preexisting_empty_destination(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    dataset_root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), dataset_root, "val", None
    )
    mask_parent = dataset_root / "truth_masks"
    mask_parent.mkdir()
    metadata = mask_parent.stat()

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_truth_samples(dataset_root, "val", inventory)

    current = mask_parent.stat()
    assert (current.st_dev, current.st_ino) == (metadata.st_dev, metadata.st_ino)
    assert not (mask_parent / "val").exists()
    assert not any(path.name.startswith(".truth-masks-") for path in dataset_root.iterdir())


def test_round4_truth_mask_publication_never_replaces_racing_empty_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    dataset_root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), dataset_root, "val", None
    )
    mask_parent = dataset_root / "truth_masks"
    real_fsync = os.fsync
    destination_identity: tuple[int, int] | None = None

    def create_empty_destination_after_staging_sync(
        descriptor: int,
    ) -> None:
        nonlocal destination_identity
        real_fsync(descriptor)
        try:
            names = os.listdir(descriptor)
        except OSError:
            return
        if destination_identity is None and names == ["val"] and not mask_parent.exists():
            mask_parent.mkdir()
            metadata = mask_parent.stat()
            destination_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(os, "fsync", create_empty_destination_after_staging_sync)
    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(dataset_root, "val", inventory)

    assert destination_identity is not None
    assert mask_parent.is_dir()
    metadata = mask_parent.stat()
    assert (metadata.st_dev, metadata.st_ino) == destination_identity
    assert list(mask_parent.iterdir()) == []


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
