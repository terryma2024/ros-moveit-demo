"""The verified archive snapshot and the sealed test document chain."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
import hashlib
import os
from pathlib import Path
import stat
import tarfile

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    SCHEMA_VERSION,
)
from so101_demo.perception_benchmark.dataset.contracts import (
    _KINDS,
    DatasetVerificationError,
    Split,
    TestAccessGrant,
    TestSeal,
    _require_sha256,
    _valid_grant_capability,
    _validate_access_event,
)
from so101_demo.perception_benchmark.dataset.pinned_files import (
    _ArchiveMember,
    _hash_open_stream,
    _inspect_open_tar,
)


class _VerifiedArchiveSnapshot(AbstractContextManager["_VerifiedArchiveSnapshot"]):
    def __init__(self, archive: Path, expected_sha256: str) -> None:
        self.path = Path(archive)
        self.expected_sha256 = _require_sha256(expected_sha256, "DATASET_ARCHIVE_SHA256_INVALID")
        self._file: object | None = None
        self._tar: tarfile.TarFile | None = None
        self._stat: os.stat_result | None = None
        self.members: list[tarfile.TarInfo] = []
        self.classified: list[_ArchiveMember] = []

    def __enter__(self) -> "_VerifiedArchiveSnapshot":
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
            file_object = os.fdopen(descriptor, "rb")
            self._file = file_object
            opened_stat = os.fstat(file_object.fileno())
            path_stat = os.lstat(self.path)
            if not stat.S_ISREG(opened_stat.st_mode) or (
                opened_stat.st_dev,
                opened_stat.st_ino,
            ) != (path_stat.st_dev, path_stat.st_ino):
                raise DatasetVerificationError("DATASET_ARCHIVE_UNREADABLE")
            self._stat = opened_stat
            if _hash_open_stream(file_object) != self.expected_sha256:
                raise DatasetVerificationError("DATASET_ARCHIVE_HASH_MISMATCH")
            file_object.seek(0)
            self._tar = tarfile.open(fileobj=file_object, mode="r:gz")
            self.members, self.classified = _inspect_open_tar(self._tar)
            return self
        except DatasetVerificationError:
            self._close()
            raise
        except (OSError, tarfile.TarError) as error:
            self._close()
            raise DatasetVerificationError("DATASET_ARCHIVE_INVALID") from error

    def copy_split(
        self,
        root: Path,
        triplets: Mapping[str, Mapping[str, _ArchiveMember]],
    ) -> None:
        if self._tar is None:
            raise DatasetVerificationError("DATASET_ARCHIVE_INVALID")
        selected = {
            member.archive_path: member
            for by_kind in triplets.values()
            for member in by_kind.values()
        }
        for tar_member in self.members:
            selected_member = selected.get(tar_member.name)
            if selected_member is None:
                continue
            source = self._tar.extractfile(tar_member)
            if source is None:
                raise DatasetVerificationError("ARCHIVE_MEMBER_UNREADABLE")
            target = root / selected_member.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with target.open("xb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if digest.hexdigest() != selected_member.sha256:
                raise DatasetVerificationError("ARCHIVE_MEMBER_CHANGED")
            target.chmod(0o444)

    def assert_unchanged(self) -> None:
        if self._file is None or self._stat is None:
            raise DatasetVerificationError("DATASET_ARCHIVE_INVALID")
        try:
            descriptor_stat = os.fstat(self._file.fileno())  # type: ignore[attr-defined]
            path_stat = os.lstat(self.path)
            if (
                (descriptor_stat.st_dev, descriptor_stat.st_ino)
                != (self._stat.st_dev, self._stat.st_ino)
                or (path_stat.st_dev, path_stat.st_ino) != (self._stat.st_dev, self._stat.st_ino)
                or descriptor_stat.st_size != self._stat.st_size
                or descriptor_stat.st_mtime_ns != self._stat.st_mtime_ns
                or _hash_open_stream(self._file) != self.expected_sha256
            ):
                raise DatasetVerificationError("ARCHIVE_CHANGED_DURING_VERIFICATION")
        except DatasetVerificationError:
            raise
        except OSError as error:
            raise DatasetVerificationError("ARCHIVE_CHANGED_DURING_VERIFICATION") from error

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        try:
            if exc_type is None:
                self.assert_unchanged()
        finally:
            self._close()

    def _close(self) -> None:
        if self._tar is not None:
            self._tar.close()
            self._tar = None
        if self._file is not None:
            self._file.close()  # type: ignore[attr-defined]
            self._file = None


def _require_triplets(
    members: list[_ArchiveMember], split: Split, expected_count: int
) -> dict[str, dict[str, _ArchiveMember]]:
    triplets: dict[str, dict[str, _ArchiveMember]] = {}
    for member in members:
        if member.split != split:
            continue
        by_kind = triplets.setdefault(member.stem, {})
        if member.kind in by_kind:
            code = "TEST_MEMBER_COUNT_INVALID" if split == "test" else "SPLIT_MEMBER_COUNT_INVALID"
            raise DatasetVerificationError(code)
        by_kind[member.kind] = member
    valid = len(triplets) == expected_count and all(
        set(by_kind) == set(_KINDS) for by_kind in triplets.values()
    )
    if not valid:
        code = "TEST_MEMBER_COUNT_INVALID" if split == "test" else "SPLIT_MEMBER_COUNT_INVALID"
        raise DatasetVerificationError(code)
    return triplets


def _sealed_test_document(
    classified: list[_ArchiveMember],
    archive_sha256: str,
) -> dict[str, object]:
    test_members = sorted(
        (member for member in classified if member.split == "test"),
        key=lambda item: item.relative_path,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "split": "test",
        "archive_sha256": _require_sha256(archive_sha256, "DATASET_ARCHIVE_SHA256_INVALID"),
        "members": [
            {
                "path": member.archive_path,
                "sha256": member.sha256,
                "size": member.size,
            }
            for member in test_members
        ],
    }


def _sealed_test_sha(classified: list[_ArchiveMember], archive_sha256: str) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_sealed_test_document(classified, archive_sha256))
    ).hexdigest()


def _validate_test_chain(
    test_seal: TestSeal | None,
    current_sealed_sha: str,
) -> TestAccessGrant:
    if test_seal is None or test_seal.access_grant is None:
        raise DatasetVerificationError("TEST_SEALED")
    if test_seal.sealed_member_inventory_sha256 != current_sealed_sha:
        raise DatasetVerificationError("TEST_SEAL_ARCHIVE_MISMATCH")
    grant = test_seal.access_grant
    if grant.sealed_member_inventory_sha256 != current_sealed_sha or not _valid_grant_capability(
        grant
    ):
        raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
    _validate_access_event(test_seal.access_log_path, grant)
    return grant
