"""Truth loader aliasing and the pinned no-replace renames."""

from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import sys
import tempfile

from perception_benchmark_dataset_support import (
    _public_inventory_anchors,
    _skip_what_needs_the_pinned_rasterizer,  # noqa: F401  (pytest fixtures)
    build_fixture_archive,
)
import pytest

from so101_demo.perception_benchmark.dataset import pinned_files as dataset_module_pinned_files
from so101_demo.perception_benchmark.dataset.contracts import DatasetVerificationError, sha256_file
from so101_demo.perception_benchmark.dataset.loading import (
    load_dataset_inventory,
    load_truth_samples,
)
from so101_demo.perception_benchmark.dataset.verifier import DatasetArchiveVerifier


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


def test_round4_truth_loader_does_not_chase_moved_or_substituted_staging(
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
    moved = outside / "moved-owned-staging"
    real_fsync = os.fsync
    staging_name: str | None = None
    substitute_identity: tuple[int, int] | None = None
    moved_snapshot: tuple[tuple[str, bytes], ...] | None = None

    def move_and_substitute_after_staging_sync(descriptor: int) -> None:
        nonlocal moved_snapshot, staging_name, substitute_identity
        real_fsync(descriptor)
        try:
            names = os.listdir(descriptor)
        except OSError:
            return
        if staging_name is not None or names != ["val"] or (root / "truth_masks").exists():
            return
        metadata = os.fstat(descriptor)
        candidates = [
            path
            for path in root.iterdir()
            if path.name.startswith(".truth-masks-")
            and (path.stat().st_dev, path.stat().st_ino) == (metadata.st_dev, metadata.st_ino)
        ]
        assert len(candidates) == 1
        staging_path = candidates[0]
        staging_name = staging_path.name
        staging_path.rename(moved)
        staging_path.mkdir()
        marker = staging_path / "unowned-marker.bin"
        marker.write_bytes(b"do not delete substituted inode")
        substitute = staging_path.stat()
        substitute_identity = substitute.st_dev, substitute.st_ino
        moved_snapshot = tuple(
            (path.relative_to(moved).as_posix(), path.read_bytes())
            for path in sorted(moved.rglob("*"))
            if path.is_file()
        )

    monkeypatch.setattr(os, "fsync", move_and_substitute_after_staging_sync)

    with pytest.raises(DatasetVerificationError, match="TRUTH_MASK_PUBLISH_FAILED"):
        load_truth_samples(root, "val", inventory)

    assert staging_name is not None
    assert substitute_identity is not None
    assert moved_snapshot is not None
    substitute_path = root / staging_name
    substitute = substitute_path.stat()
    assert (substitute.st_dev, substitute.st_ino) == substitute_identity
    assert (substitute_path / "unowned-marker.bin").read_bytes() == (
        b"do not delete substituted inode"
    )
    assert moved.is_dir()
    assert (
        tuple(
            (path.relative_to(moved).as_posix(), path.read_bytes())
            for path in sorted(moved.rglob("*"))
            if path.is_file()
        )
        == moved_snapshot
    )
    assert not (root / "truth_masks").exists()


def test_round3_truth_loader_binds_alias_root_by_pinned_identity() -> None:
    with tempfile.TemporaryDirectory(prefix="so101-public-truth-", dir=Path("/tmp")) as temporary:
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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS renameatx_np contract")
def test_round4_macos_noreplace_installs_exact_source_inode(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    source = root / "source"
    source.mkdir()
    source_metadata = source.stat()
    wrapper = getattr(dataset_module_pinned_files, "_rename_directory_noreplace", None)
    assert callable(wrapper)

    with dataset_module_pinned_files._PinnedDirectory.open(root) as pinned:
        wrapper(pinned._descriptor, "source", pinned._descriptor, "truth_masks")

    installed = (root / "truth_masks").stat()
    assert (installed.st_dev, installed.st_ino) == (
        source_metadata.st_dev,
        source_metadata.st_ino,
    )
    assert not source.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS renameatx_np contract")
def test_round4_macos_noreplace_refuses_existing_empty_destination(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    source = root / "source"
    source.mkdir()
    destination = root / "truth_masks"
    destination.mkdir()
    source_metadata = source.stat()
    destination_metadata = destination.stat()
    wrapper = getattr(dataset_module_pinned_files, "_rename_directory_noreplace", None)
    assert callable(wrapper)

    with dataset_module_pinned_files._PinnedDirectory.open(root) as pinned:
        with pytest.raises(OSError) as caught:
            wrapper(
                pinned._descriptor,
                "source",
                pinned._descriptor,
                "truth_masks",
            )

    assert caught.value.errno == errno.EEXIST
    current_source = source.stat()
    current_destination = destination.stat()
    assert (current_source.st_dev, current_source.st_ino) == (
        source_metadata.st_dev,
        source_metadata.st_ino,
    )
    assert (current_destination.st_dev, current_destination.st_ino) == (
        destination_metadata.st_dev,
        destination_metadata.st_ino,
    )


def test_round4_linux_noreplace_selects_renameat2_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, bytes, int, bytes, int]] = []

    class FakeRenameAt2:
        argtypes: object = None
        restype: object = None

        def __call__(
            self,
            source_fd: int,
            source_name: bytes,
            destination_fd: int,
            destination_name: bytes,
            flags: int,
        ) -> int:
            calls.append(
                (
                    source_fd,
                    source_name,
                    destination_fd,
                    destination_name,
                    flags,
                )
            )
            return 0

    class FakeLibC:
        renameat2 = FakeRenameAt2()

    wrapper = getattr(dataset_module_pinned_files, "_rename_directory_noreplace", None)
    assert callable(wrapper)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: FakeLibC())

    wrapper(10, "source", 11, "truth_masks")

    assert calls == [(10, b"source", 11, b"truth_masks", 1)]


def test_round4_noreplace_fails_closed_when_kernel_primitive_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLibC:
        pass

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: FakeLibC())
    monkeypatch.setattr(
        os,
        "replace",
        lambda *args, **kwargs: pytest.fail("replace fallback must not run"),
    )
    monkeypatch.setattr(
        os,
        "rename",
        lambda *args, **kwargs: pytest.fail("rename fallback must not run"),
    )

    with pytest.raises(OSError) as caught:
        dataset_module_pinned_files._rename_directory_noreplace(
            10,
            "source",
            10,
            "truth_masks",
        )

    assert caught.value.errno == errno.ENOSYS


def test_round4_new_pinned_child_rejects_swap_before_open_without_cleanup_chase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / "moved-owned-staging"
    staging_name = ".truth-masks-stage-0123456789abcdef0123456789abcdef"
    real_open = os.open
    swapped = False

    with dataset_module_pinned_files._PinnedDirectory.open(root) as pinned:

        def swap_before_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal swapped
            if path == staging_name and dir_fd == pinned._descriptor and not swapped:
                swapped = True
                (root / staging_name).rename(moved)
                (root / staging_name).mkdir()
                (root / staging_name / "unowned-marker.bin").write_bytes(b"keep")
            return real_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", swap_before_open)
        with pytest.raises(ValueError, match="changed while opening"):
            pinned.create_pinned_child(staging_name)

    assert swapped
    assert moved.is_dir()
    assert list(moved.iterdir()) == []
    assert (root / staging_name / "unowned-marker.bin").read_bytes() == b"keep"
