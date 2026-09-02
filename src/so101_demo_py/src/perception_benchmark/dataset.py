"""Fail-closed dataset archive access and truth loading for formal benchmarks."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import shutil
import stat
import tarfile
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal

import numpy as np
import PIL
from PIL import Image, ImageDraw
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

Split = Literal["val", "test"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_SAMPLE_COUNT = 200
_EXPECTED_IMAGE_SIZE = (640, 480)
_EXPECTED_SCENARIO_COUNTS = {
    "no_cup": 50,
    "one_cup_distractors": 50,
    "two_cups": 50,
    "cup_near_bottle": 50,
}
_RASTERIZER = {
    "library": "Pillow",
    "version": "12.3.0",
    "coordinate_scale": "dimension_minus_one",
    "rounding": "floor(x+0.5)",
    "boundary": "ImageDraw.polygon fill=1",
}
_KINDS = {"images": ".png", "labels": ".txt", "truth": ".json"}
_INVENTORY_KEYS = {
    "schema_version",
    "split",
    "archive_sha256",
    "sample_count",
    "scenario_counts",
    "rasterizer",
    "test_access",
    "samples",
}
_SAMPLE_KEYS = {
    "formal_sample_index",
    "split",
    "scenario",
    "image_relpath",
    "label_relpath",
    "truth_relpath",
    "image_sha256",
    "label_sha256",
    "truth_sha256",
    "truth_count",
}
_CAPABILITY_KEY = secrets.token_bytes(32)
_CAPABILITY_GENERATION_NONCE = secrets.token_bytes(32)


def _rotate_capability_generation() -> None:
    global _CAPABILITY_GENERATION_NONCE, _CAPABILITY_KEY
    _CAPABILITY_KEY = secrets.token_bytes(32)
    _CAPABILITY_GENERATION_NONCE = secrets.token_bytes(32)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_rotate_capability_generation)


class DatasetVerificationError(ValueError):
    """A stable fail-closed dataset verification error."""


def _require_sha256(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DatasetVerificationError(code)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise DatasetVerificationError("DATASET_ARCHIVE_UNREADABLE") from error
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetSampleRef:
    formal_sample_index: int
    split: Split
    scenario: str
    image_relpath: str
    label_relpath: str
    truth_relpath: str
    image_sha256: str
    truth_count: int


@dataclass(frozen=True, slots=True)
class ArchiveInventory:
    archive_sha256: str
    sealed_test_member_inventory_sha256: str
    safe_member_count: int
    test_triplet_count: int
    test_scenario_counts: Mapping[str, int] | None

    def __post_init__(self) -> None:
        if self.test_scenario_counts is not None:
            object.__setattr__(
                self,
                "test_scenario_counts",
                MappingProxyType(dict(self.test_scenario_counts)),
            )


@dataclass(frozen=True, slots=True)
class TestAccessGrant:
    event_sha256: str
    sealed_member_inventory_sha256: str
    threshold_lock_sha256s: tuple[str, str]
    granted_at: str
    _capability: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            event_sha = _require_sha256(
                self.event_sha256, "TEST_ACCESS_GRANT_INVALID"
            )
            sealed_sha = _require_sha256(
                self.sealed_member_inventory_sha256,
                "TEST_ACCESS_GRANT_INVALID",
            )
            locks = tuple(self.threshold_lock_sha256s)
            if len(locks) != 2:
                raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
            normalized_locks = tuple(
                _require_sha256(value, "TEST_ACCESS_GRANT_INVALID")
                for value in locks
            )
            if normalized_locks[0] == normalized_locks[1]:
                raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
            granted_at = datetime.fromisoformat(self.granted_at)
            if (
                granted_at.tzinfo is None
                or granted_at.utcoffset() != timezone.utc.utcoffset(granted_at)
            ):
                raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
        except (TypeError, ValueError) as error:
            raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID") from error
        object.__setattr__(self, "event_sha256", event_sha)
        object.__setattr__(self, "sealed_member_inventory_sha256", sealed_sha)
        object.__setattr__(self, "threshold_lock_sha256s", normalized_locks)


@dataclass(frozen=True, slots=True)
class DatasetInventory:
    schema_version: str
    split: Split
    archive_sha256: str
    inventory_sha256: str
    dataset_root: Path
    sample_count: int
    scenario_counts: Mapping[str, int]
    samples: tuple[DatasetSampleRef, ...]
    test_access_event_sha256: str | None
    _capability: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_root", Path(self.dataset_root))
        object.__setattr__(
            self, "scenario_counts", MappingProxyType(dict(self.scenario_counts))
        )
        object.__setattr__(self, "samples", tuple(self.samples))


@dataclass(frozen=True, slots=True)
class TestSeal:
    sealed_member_inventory_sha256: str
    access_log_path: Path
    access_grant: TestAccessGrant | None = None

    def __post_init__(self) -> None:
        _require_sha256(
            self.sealed_member_inventory_sha256,
            "SEALED_MEMBER_INVENTORY_SHA256_INVALID",
        )
        object.__setattr__(self, "access_log_path", Path(self.access_log_path))
        if self.access_grant is not None:
            if (
                not isinstance(self.access_grant, TestAccessGrant)
                or self.access_grant.sealed_member_inventory_sha256
                != self.sealed_member_inventory_sha256
                or not _valid_grant_capability(self.access_grant)
            ):
                raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
            _validate_access_event(self.access_log_path, self.access_grant)

    def unlock(
        self,
        yolo_lock_path: Path,
        grounded_sam_lock_path: Path,
        verify_lock: Callable[[Path], str],
    ) -> "TestSeal":
        if self.access_grant is not None:
            raise DatasetVerificationError("TEST_ACCESS_ALREADY_GRANTED")
        if Path(yolo_lock_path) == Path(grounded_sam_lock_path):
            raise DatasetVerificationError("THRESHOLD_LOCKS_NOT_DISTINCT")
        try:
            lock_shas = (
                _require_sha256(
                    verify_lock(Path(yolo_lock_path)), "THRESHOLD_LOCK_SHA256_INVALID"
                ),
                _require_sha256(
                    verify_lock(Path(grounded_sam_lock_path)),
                    "THRESHOLD_LOCK_SHA256_INVALID",
                ),
            )
        except DatasetVerificationError:
            raise
        except Exception as error:
            raise DatasetVerificationError("THRESHOLD_LOCK_VERIFICATION_FAILED") from error
        if lock_shas[0] == lock_shas[1]:
            raise DatasetVerificationError("THRESHOLD_LOCKS_NOT_DISTINCT")
        grant = append_test_access_event(
            self.access_log_path,
            self.sealed_member_inventory_sha256,
            lock_shas,
        )
        return replace(self, access_grant=grant)


def append_test_access_event(
    access_log_path: Path,
    sealed_member_inventory_sha256: str,
    threshold_lock_sha256s: tuple[str, str],
) -> TestAccessGrant:
    sealed_sha = _require_sha256(
        sealed_member_inventory_sha256,
        "SEALED_MEMBER_INVENTORY_SHA256_INVALID",
    )
    locks = tuple(
        _require_sha256(value, "THRESHOLD_LOCK_SHA256_INVALID")
        for value in threshold_lock_sha256s
    )
    if len(locks) != 2 or locks[0] == locks[1]:
        raise DatasetVerificationError("THRESHOLD_LOCKS_NOT_DISTINCT")
    target = Path(access_log_path)
    if target.is_symlink():
        raise DatasetVerificationError("TEST_ACCESS_LOG_UNSAFE")
    target.parent.mkdir(parents=True, exist_ok=True)
    granted_at = datetime.now(timezone.utc).isoformat()
    event_without_sha = {
        "event_type": "TEST_ACCESS_GRANTED",
        "granted_at": granted_at,
        "sealed_member_inventory_sha256": sealed_sha,
        "threshold_lock_sha256s": list(locks),
    }
    event_sha = hashlib.sha256(canonical_json_bytes(event_without_sha)).hexdigest()
    event = {**event_without_sha, "event_sha256": event_sha}
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "a+b") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise DatasetVerificationError("TEST_ACCESS_LOG_UNSAFE")
            stream.seek(0)
            _parse_canonical_access_log(stream.read())
            stream.seek(0, os.SEEK_END)
            stream.write(canonical_json_bytes(event))
            stream.flush()
            os.fsync(stream.fileno())
    except DatasetVerificationError:
        raise
    except OSError as error:
        raise DatasetVerificationError("TEST_ACCESS_LOG_WRITE_FAILED") from error
    grant = TestAccessGrant(event_sha, sealed_sha, locks, granted_at)
    object.__setattr__(grant, "_capability", _grant_capability(grant))
    return grant


def _capability_digest(kind: str, *parts: object) -> str:
    payload = canonical_json_bytes(
        {
            "kind": kind,
            "pid": os.getpid(),
            "generation_nonce": _CAPABILITY_GENERATION_NONCE.hex(),
            "parts": [str(part) for part in parts],
        }
    )
    return hmac.new(_CAPABILITY_KEY, payload, hashlib.sha256).hexdigest()


def _grant_capability(grant: TestAccessGrant) -> str:
    return _capability_digest(
        "test-access-grant",
        grant.event_sha256,
        grant.sealed_member_inventory_sha256,
        *grant.threshold_lock_sha256s,
        grant.granted_at,
    )


def _valid_grant_capability(grant: TestAccessGrant) -> bool:
    return grant._capability is not None and hmac.compare_digest(
        grant._capability, _grant_capability(grant)
    )


def _parse_canonical_access_log(payload: bytes) -> tuple[Mapping[str, object], ...]:
    if not payload:
        return ()
    events: list[Mapping[str, object]] = []
    for line in payload.splitlines(keepends=True):
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DatasetVerificationError("TEST_ACCESS_EVENT_INVALID") from error
        if not isinstance(event, Mapping) or canonical_json_bytes(event) != line:
            raise DatasetVerificationError("TEST_ACCESS_EVENT_INVALID")
        events.append(event)
    return tuple(events)


def _expected_access_event(grant: TestAccessGrant) -> dict[str, object]:
    without_sha = {
        "event_type": "TEST_ACCESS_GRANTED",
        "granted_at": grant.granted_at,
        "sealed_member_inventory_sha256": grant.sealed_member_inventory_sha256,
        "threshold_lock_sha256s": list(grant.threshold_lock_sha256s),
    }
    if hashlib.sha256(canonical_json_bytes(without_sha)).hexdigest() != grant.event_sha256:
        raise DatasetVerificationError("TEST_ACCESS_EVENT_INVALID")
    return {**without_sha, "event_sha256": grant.event_sha256}


def _validate_access_event(path: Path, grant: TestAccessGrant) -> None:
    if not _valid_grant_capability(grant):
        raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise DatasetVerificationError("TEST_ACCESS_EVENT_INVALID")
    try:
        events = _parse_canonical_access_log(target.read_bytes())
    except OSError as error:
        raise DatasetVerificationError("TEST_ACCESS_EVENT_INVALID") from error
    expected = _expected_access_event(grant)
    if sum(event == expected for event in events) != 1:
        raise DatasetVerificationError("TEST_ACCESS_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class _ArchiveMember:
    archive_path: str
    relative_path: str
    kind: str
    split: Split
    stem: str
    size: int
    sha256: str


def _safe_member_path(name: str) -> bool:
    if not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


class _PinnedFileError(ValueError):
    """A descriptor-pinned file or directory failed the safety contract."""


_OPEN_BASE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
_OPEN_DIRECTORY_FLAGS = _OPEN_BASE_FLAGS | getattr(os, "O_DIRECTORY", 0)
_CREATE_FILE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _stable_file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_nlink,
    )


class _PinnedDirectory:
    """Pin one directory and access descendants only through no-follow fds."""

    __slots__ = ("path", "_descriptor", "_identity")

    def __init__(
        self, path: Path, descriptor: int, identity: tuple[int, int]
    ) -> None:
        self.path = path
        self._descriptor = descriptor
        self._identity = identity

    @classmethod
    def open(cls, path: Path) -> "_PinnedDirectory":
        absolute = Path(os.path.abspath(os.fspath(Path(path))))
        descriptor: int | None = None
        try:
            descriptor = os.open(absolute, _OPEN_DIRECTORY_FLAGS)
            opened = os.fstat(descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                raise _PinnedFileError("pinned root is not a directory")
            lexical = os.lstat(absolute)
            if stat.S_ISLNK(lexical.st_mode):
                raise _PinnedFileError("pinned root cannot be a symlink")
            canonical = Path(os.path.realpath(absolute))
            bound = os.lstat(canonical)
            if (
                not stat.S_ISDIR(bound.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (lexical.st_dev, lexical.st_ino)
                or (opened.st_dev, opened.st_ino)
                != (bound.st_dev, bound.st_ino)
            ):
                raise _PinnedFileError("pinned root changed while opening")
            return cls(
                canonical,
                descriptor,
                (opened.st_dev, opened.st_ino),
            )
        except _PinnedFileError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise _PinnedFileError("pinned directory cannot be opened") from error

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, -1
        if descriptor >= 0:
            os.close(descriptor)

    def __enter__(self) -> "_PinnedDirectory":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _assert_identity(self) -> None:
        try:
            metadata = os.fstat(self._descriptor)
        except OSError as error:
            raise _PinnedFileError("pinned directory cannot be inspected") from error
        if (metadata.st_dev, metadata.st_ino) != self._identity:
            raise _PinnedFileError("pinned directory identity changed")

    def same_identity(self, other: "_PinnedDirectory") -> bool:
        self._assert_identity()
        other._assert_identity()
        return self._identity == other._identity

    def fsync(self) -> None:
        try:
            self._assert_identity()
            os.fsync(self._descriptor)
        except (_PinnedFileError, OSError) as error:
            raise _PinnedFileError("pinned directory cannot be synced") from error

    def child_metadata(self, name: str) -> os.stat_result | None:
        if not _safe_member_path(name) or len(PurePosixPath(name).parts) != 1:
            raise _PinnedFileError("child name is unsafe")
        try:
            self._assert_identity()
            return os.stat(name, dir_fd=self._descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except (_PinnedFileError, OSError) as error:
            raise _PinnedFileError("child metadata cannot be read") from error

    def mkdir_child(self, name: str, mode: int = 0o700) -> None:
        if self.child_metadata(name) is not None:
            raise _PinnedFileError("child already exists")
        try:
            os.mkdir(name, mode=mode, dir_fd=self._descriptor)
            self.fsync()
        except (_PinnedFileError, OSError) as error:
            raise _PinnedFileError("child directory cannot be created") from error

    def open_child_directory(self, name: str) -> "_PinnedDirectory":
        before = self.child_metadata(name)
        if before is None or not stat.S_ISDIR(before.st_mode):
            raise _PinnedFileError("child is not a real directory")
        descriptor: int | None = None
        try:
            descriptor = os.open(name, _OPEN_DIRECTORY_FLAGS, dir_fd=self._descriptor)
            opened = os.fstat(descriptor)
            after = self.child_metadata(name)
            if (
                after is None
                or not stat.S_ISDIR(opened.st_mode)
                or (before.st_dev, before.st_ino)
                != (opened.st_dev, opened.st_ino)
                or (before.st_dev, before.st_ino)
                != (after.st_dev, after.st_ino)
            ):
                raise _PinnedFileError("child directory changed while opening")
            return _PinnedDirectory(
                self.path / name,
                descriptor,
                (opened.st_dev, opened.st_ino),
            )
        except _PinnedFileError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise _PinnedFileError("child directory cannot be opened") from error

    def child_names(self) -> tuple[str, ...]:
        try:
            self._assert_identity()
            before = os.fstat(self._descriptor)
            names = tuple(sorted(os.listdir(self._descriptor)))
            after = os.fstat(self._descriptor)
        except (_PinnedFileError, OSError) as error:
            raise _PinnedFileError("child names cannot be read") from error
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise _PinnedFileError("directory changed while listing children")
        return names

    def write_new_file(self, name: str, payload: bytes) -> tuple[int, int]:
        if (
            not _safe_member_path(name)
            or len(PurePosixPath(name).parts) != 1
            or not isinstance(payload, bytes)
        ):
            raise _PinnedFileError("new file input is unsafe")
        descriptor: int | None = None
        created_identity: tuple[int, int] | None = None
        try:
            self._assert_identity()
            descriptor = os.open(
                name,
                _CREATE_FILE_FLAGS,
                0o400,
                dir_fd=self._descriptor,
            )
            created = os.fstat(descriptor)
            if not stat.S_ISREG(created.st_mode) or created.st_nlink != 1:
                raise _PinnedFileError("new file is not a single-link regular file")
            created_identity = created.st_dev, created.st_ino
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise _PinnedFileError("new file write made no progress")
                offset += written
            os.fchmod(descriptor, 0o444)
            os.fsync(descriptor)
            persisted = os.fstat(descriptor)
            if (
                persisted.st_dev,
                persisted.st_ino,
                persisted.st_size,
                persisted.st_nlink,
            ) != (
                created.st_dev,
                created.st_ino,
                len(payload),
                1,
            ):
                raise _PinnedFileError("new file changed while writing")
            return persisted.st_dev, persisted.st_ino
        except _PinnedFileError:
            if created_identity is not None:
                self.unlink_owned_file(name, created_identity)
            raise
        except OSError as error:
            if created_identity is not None:
                self.unlink_owned_file(name, created_identity)
            raise _PinnedFileError("new file cannot be persisted") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def unlink_owned_file(self, name: str, identity: tuple[int, int]) -> None:
        metadata = self.child_metadata(name)
        if (
            metadata is None
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != identity
        ):
            return
        try:
            os.unlink(name, dir_fd=self._descriptor)
            self.fsync()
        except OSError:
            return

    def rmdir_owned_child(self, name: str, identity: tuple[int, int]) -> None:
        metadata = self.child_metadata(name)
        if (
            metadata is None
            or not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != identity
        ):
            return
        try:
            os.rmdir(name, dir_fd=self._descriptor)
            self.fsync()
        except OSError:
            return

    def replace_child_into(
        self,
        source_name: str,
        destination_parent: "_PinnedDirectory",
        destination_name: str,
    ) -> None:
        if (
            not _safe_member_path(source_name)
            or len(PurePosixPath(source_name).parts) != 1
            or not _safe_member_path(destination_name)
            or len(PurePosixPath(destination_name).parts) != 1
            or destination_parent.child_metadata(destination_name) is not None
        ):
            raise _PinnedFileError("publication target is unsafe or already exists")
        try:
            self._assert_identity()
            destination_parent._assert_identity()
            os.replace(
                source_name,
                destination_name,
                src_dir_fd=self._descriptor,
                dst_dir_fd=destination_parent._descriptor,
            )
            self.fsync()
            destination_parent.fsync()
        except (_PinnedFileError, OSError) as error:
            raise _PinnedFileError("directory publication failed") from error

    def _open_descendant_directory(self, relative_path: str) -> int:
        if relative_path and not _safe_member_path(relative_path):
            raise _PinnedFileError("directory path is unsafe")
        descriptor = os.dup(self._descriptor)
        try:
            root_metadata = os.fstat(descriptor)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._identity:
                raise _PinnedFileError("pinned root identity changed")
            for part in PurePosixPath(relative_path).parts if relative_path else ():
                next_descriptor = os.open(
                    part, _OPEN_DIRECTORY_FLAGS, dir_fd=descriptor
                )
                metadata = os.fstat(next_descriptor)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(next_descriptor)
                    raise _PinnedFileError("path component is not a directory")
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except _PinnedFileError:
            os.close(descriptor)
            raise
        except OSError as error:
            os.close(descriptor)
            raise _PinnedFileError("descendant directory cannot be opened") from error

    def read_file(self, relative_path: str) -> bytes:
        if not _safe_member_path(relative_path):
            raise _PinnedFileError("file path is unsafe")
        parts = PurePosixPath(relative_path).parts
        parent = self._open_descendant_directory("/".join(parts[:-1]))
        descriptor: int | None = None
        try:
            descriptor = os.open(parts[-1], _OPEN_BASE_FLAGS, dir_fd=parent)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise _PinnedFileError("file is not a single-link regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                _stable_file_identity(before) != _stable_file_identity(after)
                or after.st_nlink != 1
                or len(payload) != after.st_size
            ):
                raise _PinnedFileError("file changed during pinned read")
            return payload
        except _PinnedFileError:
            raise
        except OSError as error:
            raise _PinnedFileError("file cannot be read safely") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(parent)

    def tree(self, relative_path: str = "") -> tuple[set[str], set[str]]:
        start = self._open_descendant_directory(relative_path)
        files: set[str] = set()
        directories: set[str] = set()

        def visit(descriptor: int, prefix: str) -> None:
            before = os.fstat(descriptor)
            try:
                names = sorted(os.listdir(descriptor))
            except OSError as error:
                raise _PinnedFileError("directory cannot be enumerated") from error
            for name in names:
                child: int | None = None
                child_path = f"{prefix}/{name}" if prefix else name
                try:
                    child = os.open(name, _OPEN_BASE_FLAGS, dir_fd=descriptor)
                    metadata = os.fstat(child)
                    if stat.S_ISDIR(metadata.st_mode):
                        directories.add(child_path)
                        visit(child, child_path)
                    elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                        files.add(child_path)
                    else:
                        raise _PinnedFileError("tree entry is unsafe")
                except _PinnedFileError:
                    raise
                except OSError as error:
                    raise _PinnedFileError("tree entry cannot be opened") from error
                finally:
                    if child is not None:
                        os.close(child)
            after = os.fstat(descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise _PinnedFileError("directory changed during enumeration")

        try:
            visit(start, relative_path)
            return files, directories
        finally:
            os.close(start)


def _classify_member(name: str) -> tuple[str, Split, str, str] | None:
    parts = PurePosixPath(name).parts
    if len(parts) < 3:
        return None
    kind, split, filename = parts[-3:]
    if kind not in _KINDS or split not in {"val", "test"}:
        return None
    suffix = _KINDS[kind]
    if not filename.endswith(suffix) or filename == suffix:
        return None
    stem = filename[: -len(suffix)]
    return kind, split, stem, "/".join((kind, split, filename))


def _hash_open_stream(stream: object) -> str:
    digest = hashlib.sha256()
    stream.seek(0)  # type: ignore[attr-defined]
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):  # type: ignore[attr-defined]
        digest.update(chunk)
    return digest.hexdigest()


def _inspect_open_tar(
    stream: tarfile.TarFile,
) -> tuple[list[tarfile.TarInfo], list[_ArchiveMember]]:
    members: list[tarfile.TarInfo] = []
    classified: list[_ArchiveMember] = []
    seen_paths: set[str] = set()
    for member in stream.getmembers():
        if (
            not _safe_member_path(member.name)
            or member.issym()
            or member.islnk()
            or not (member.isfile() or member.isdir())
            or member.name in seen_paths
        ):
            raise DatasetVerificationError("ARCHIVE_PATH_UNSAFE")
        seen_paths.add(member.name)
        members.append(member)
        classification = _classify_member(member.name)
        if classification is None or not member.isfile():
            continue
        kind, split, stem, relative_path = classification
        extracted = stream.extractfile(member)
        if extracted is None:
            raise DatasetVerificationError("ARCHIVE_MEMBER_UNREADABLE")
        digest = hashlib.sha256()
        for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
            digest.update(chunk)
        classified.append(
            _ArchiveMember(
                member.name,
                relative_path,
                kind,
                split,
                stem,
                member.size,
                digest.hexdigest(),
            )
        )
    return members, classified


class _VerifiedArchiveSnapshot(AbstractContextManager["_VerifiedArchiveSnapshot"]):
    def __init__(self, archive: Path, expected_sha256: str) -> None:
        self.path = Path(archive)
        self.expected_sha256 = _require_sha256(
            expected_sha256, "DATASET_ARCHIVE_SHA256_INVALID"
        )
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
            if (
                not stat.S_ISREG(opened_stat.st_mode)
                or (opened_stat.st_dev, opened_stat.st_ino)
                != (path_stat.st_dev, path_stat.st_ino)
            ):
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
                or (path_stat.st_dev, path_stat.st_ino)
                != (self._stat.st_dev, self._stat.st_ino)
                or descriptor_stat.st_size != self._stat.st_size
                or descriptor_stat.st_mtime_ns != self._stat.st_mtime_ns
                or _hash_open_stream(self._file) != self.expected_sha256
            ):
                raise DatasetVerificationError(
                    "ARCHIVE_CHANGED_DURING_VERIFICATION"
                )
        except DatasetVerificationError:
            raise
        except OSError as error:
            raise DatasetVerificationError(
                "ARCHIVE_CHANGED_DURING_VERIFICATION"
            ) from error

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
    valid = (
        len(triplets) == expected_count
        and all(set(by_kind) == set(_KINDS) for by_kind in triplets.values())
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
        "archive_sha256": _require_sha256(
            archive_sha256, "DATASET_ARCHIVE_SHA256_INVALID"
        ),
        "members": [
            {
                "path": member.archive_path,
                "sha256": member.sha256,
                "size": member.size,
            }
            for member in test_members
        ],
    }


def _sealed_test_sha(
    classified: list[_ArchiveMember], archive_sha256: str
) -> str:
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
    if (
        grant.sealed_member_inventory_sha256 != current_sealed_sha
        or not _valid_grant_capability(grant)
    ):
        raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
    _validate_access_event(test_seal.access_log_path, grant)
    return grant


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
            _require_triplets(
                snapshot.classified, "test", _EXPECTED_SAMPLE_COUNT
            )
            sealed_document = _sealed_test_document(
                snapshot.classified, snapshot.expected_sha256
            )
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
        if split == "test" and (
            test_seal is None or test_seal.access_grant is None
        ):
            raise DatasetVerificationError("TEST_SEALED")
        if split == "val" and test_seal is not None and test_seal.access_grant is not None:
            raise DatasetVerificationError("VAL_TEST_SEAL_CONFLICT")
        _require_rasterizer_version()
        root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent)
        )
        try:
            with _VerifiedArchiveSnapshot(Path(archive), expected_sha256) as snapshot:
                triplets = _require_triplets(
                    snapshot.classified, split, _EXPECTED_SAMPLE_COUNT
                )
                seal_for_inventory = None
                if split == "test":
                    _validate_test_chain(
                        test_seal,
                        _sealed_test_sha(
                            snapshot.classified, snapshot.expected_sha256
                        ),
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
        if (
            not (set(images) == set(labels) == set(truths))
            or len(images) != _EXPECTED_SAMPLE_COUNT
        ):
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
            if label_polygons != truth_polygons:
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
            for index, record in enumerate(
                sorted(records, key=lambda item: item.image_sha256)
            )
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
        )


def _inventory_capability(inventory: DatasetInventory) -> str:
    return _capability_digest(
        "dataset-inventory",
        inventory.schema_version,
        inventory.split,
        inventory.archive_sha256,
        inventory.inventory_sha256,
        inventory.dataset_root.resolve(),
        inventory.sample_count,
        tuple(sorted(inventory.scenario_counts.items())),
        inventory.samples,
        inventory.test_access_event_sha256,
    )


def _issue_inventory(inventory: DatasetInventory) -> None:
    object.__setattr__(inventory, "_capability", _inventory_capability(inventory))


def _require_inventory_capability(inventory: DatasetInventory) -> None:
    if inventory._capability is None or not hmac.compare_digest(
        inventory._capability, _inventory_capability(inventory)
    ):
        raise DatasetVerificationError("INVENTORY_CAPABILITY_INVALID")


def _require_rasterizer_version() -> None:
    if PIL.__version__ != _RASTERIZER["version"]:
        raise DatasetVerificationError("RASTERIZER_VERSION_MISMATCH")


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def rasterize_polygon(
    polygon_xy: tuple[tuple[float, float], ...], width: int, height: int
) -> np.ndarray:
    _require_rasterizer_version()
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
        or len(polygon_xy) < 3
    ):
        raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
    pixels: list[tuple[int, int]] = []
    for point in polygon_xy:
        if len(point) != 2:
            raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
        x, y = point
        if not (math.isfinite(x) and math.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
        pixels.append(
            (
                min(width - 1, max(0, _round_half_up(x * (width - 1)))),
                min(height - 1, max(0, _round_half_up(y * (height - 1)))),
            )
        )
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=1)
    return np.asarray(image, dtype=bool)


def _read_truth_bytes(payload: bytes, split: Split) -> dict[str, object]:
    try:
        document = json.loads(payload, parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation) as error:
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID") from error
    if not isinstance(document, dict):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    scenario = document.get("scenario")
    instances = document.get("instances")
    visible_count = document.get("visible_instance_count")
    if (
        document.get("split") != split
        or scenario not in _EXPECTED_SCENARIO_COUNTS
        or not isinstance(instances, list)
        or isinstance(visible_count, bool)
        or not isinstance(visible_count, int)
        or visible_count != len(instances)
    ):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    expected_count = {
        "no_cup": 0,
        "one_cup_distractors": 1,
        "two_cups": 2,
        "cup_near_bottle": 1,
    }[scenario]
    if len(instances) != expected_count:
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    _truth_polygons(document)
    return document


def _truth_polygons(
    truth: Mapping[str, object],
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    instances = truth.get("instances")
    if not isinstance(instances, list):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    result: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for instance in instances:
        if not isinstance(instance, dict):
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        raw_polygon = instance.get("polygon_xy")
        if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        polygon: list[tuple[Decimal, Decimal]] = []
        for point in raw_polygon:
            if not isinstance(point, list) or len(point) != 2:
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            try:
                x, y = (Decimal(str(point[0])), Decimal(str(point[1])))
            except InvalidOperation as error:
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID") from error
            if not (x.is_finite() and y.is_finite() and 0 <= x <= 1 and 0 <= y <= 1):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            polygon.append((x, y))
        result.append(tuple(polygon))
    return tuple(result)


def _read_label_polygons_bytes(
    payload: bytes,
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise DatasetVerificationError("LABEL_DOCUMENT_INVALID") from error
    polygons: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for line in lines:
        fields = line.split()
        if len(fields) < 7 or len(fields) % 2 != 1 or fields[0] != "0":
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID")
        try:
            values = tuple(Decimal(value) for value in fields[1:])
        except InvalidOperation as error:
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID") from error
        if any(not value.is_finite() or not 0 <= value <= 1 for value in values):
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID")
        polygons.append(tuple(zip(values[::2], values[1::2], strict=True)))
    return tuple(polygons)


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
        if (
            not isinstance(raw_instances, list)
            or len(raw_instances) != sample_ref.truth_count
        ):
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        normalized_instances: list[dict[str, object]] = []
        for raw_instance in raw_instances:
            if not isinstance(raw_instance, dict):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            body_name = raw_instance.get("body_name")
            if not isinstance(body_name, str) or not body_name.startswith(
                "plastic_cup"
            ):
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
            relative_path = (
                Path("truth_masks")
                / split
                / f"{stem}-{instance_index:02d}.json"
            )
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
        core_files.update(
            (sample.image_relpath, sample.label_relpath, sample.truth_relpath)
        )
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

    _, mask_artifacts = _derive_truth_artifacts(
        inventory, inventory.split, truth_payloads
    )
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
            (decoded.shape[1], decoded.shape[0])
            != (mask_ref.image_width, mask_ref.image_height)
            or int(decoded.sum()) != mask_ref.pixel_count
            or decoded_sha != mask_ref.sha256
        ):
            raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")
    return frozenset(mask_files)


def _verify_truth_mask_refs(
    samples: tuple[TruthSample, ...], verified_paths: frozenset[str]
) -> None:
    referenced_paths = {
        instance.mask.relative_path
        for sample in samples
        for instance in sample.instances
    }
    if (
        referenced_paths != set(verified_paths)
        or any(not _safe_member_path(path) for path in referenced_paths)
    ):
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH")


def _validate_persisted_access(test_access: object, event_sha: str | None) -> None:
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
            _require_sha256(value, "INVENTORY_ACCESS_CHAIN_INVALID")
            for value in raw_locks
        )
        if locks[0] == locks[1] or persisted_event_sha != event_sha:
            raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
        granted_at = test_access["granted_at"]
        access_log_path = test_access["access_log_path"]
        if not isinstance(granted_at, str) or not isinstance(access_log_path, str):
            raise DatasetVerificationError("INVENTORY_ACCESS_CHAIN_INVALID")
        parsed_time = datetime.fromisoformat(granted_at)
        if (
            parsed_time.tzinfo is None
            or parsed_time.utcoffset() != timezone.utc.utcoffset(parsed_time)
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
        events = _parse_canonical_access_log(
            _read_pinned_absolute_file(Path(access_log_path))
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
        sidecar = _read_regular_bound_file(
            root_path, "inventory.sha256", pinned_root=active_pinned
        )
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
            document.get("test_access"), inventory.test_access_event_sha256
        )
    elif (
        inventory.test_access_event_sha256 is not None
        or document.get("test_access") is not None
    ):
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
            or {value[0] for value in classifications if value is not None}
            != set(_KINDS)
            or {value[1] for value in classifications if value is not None}
            != {split}
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
            or hashlib.sha256(label_payload).hexdigest()
            != raw_sample["label_sha256"]
            or hashlib.sha256(truth_payload).hexdigest()
            != raw_sample["truth_sha256"]
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
        if _read_label_polygons_bytes(label_payload) != truth_polygons:
            raise DatasetVerificationError("LABEL_TRUTH_POLYGON_MISMATCH")
        if (
            truth["scenario"] != sample.scenario
            or len(truth_polygons) != sample.truth_count
        ):
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        current_scenarios[sample.scenario] += 1
        truth_payloads[sample.truth_relpath] = truth_payload
    if (
        dict(current_scenarios) != _EXPECTED_SCENARIO_COUNTS
        or dict(current_scenarios) != dict(inventory.scenario_counts)
    ):
        raise DatasetVerificationError("SCENARIO_COUNTS_INVALID")
    return truth_payloads


def load_dataset_inventory(
    dataset_root: Path,
    *,
    expected_split: Split,
    expected_archive_sha256: str,
    expected_inventory_sha256: str,
    expected_test_access_event_sha256: str | None = None,
    expected_sealed_member_inventory_sha256: str | None = None,
    expected_threshold_lock_sha256s: tuple[str, str] | None = None,
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
            )
        ):
            raise DatasetVerificationError("VAL_EXTERNAL_TEST_ANCHOR_CONFLICT")
        normalized_event_sha = None
        normalized_sealed_sha = None
        normalized_locks = None
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
        sidecar = _read_regular_bound_file(
            root, "inventory.sha256", pinned_root=pinned_root
        )
        if sidecar != f"{inventory_sha}  inventory.json\n".encode("ascii"):
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")

        split = document.get("split")
        if split not in {"val", "test"}:
            raise DatasetVerificationError("SPLIT_INVALID")
        if split != expected_split:
            raise DatasetVerificationError("TRUTH_INVENTORY_MISMATCH")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise DatasetVerificationError("INVENTORY_INTEGRITY_INVALID")
        archive_sha = _require_sha256(
            document.get("archive_sha256"), "INVENTORY_INTEGRITY_INVALID"
        )
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
                type(value) is not int
                or value != _EXPECTED_SCENARIO_COUNTS[key]
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
                _require_sha256(
                    raw_sample.get(name), "INVENTORY_INTEGRITY_INVALID"
                )
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
        if (
            [sample.image_sha256 for sample in samples]
            != sorted(sample.image_sha256 for sample in samples)
            or len({sample.image_sha256 for sample in samples}) != len(samples)
        ):
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
                _require_sha256(value, "INVENTORY_ACCESS_CHAIN_INVALID")
                for value in raw_locks
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


def _publish_truth_masks(
    pinned_root: _PinnedDirectory,
    split: Split,
    inventory: DatasetInventory,
    truth_payloads: Mapping[str, bytes],
    samples: tuple[TruthSample, ...],
    mask_artifacts: tuple[tuple[Path, dict[str, object], MaskRef], ...],
) -> None:
    parent_created = False
    try:
        parent_metadata = pinned_root.child_metadata("truth_masks")
        if parent_metadata is None:
            pinned_root.mkdir_child("truth_masks")
            parent_created = True
        elif not stat.S_ISDIR(parent_metadata.st_mode):
            raise _PinnedFileError("truth_masks parent is not a real directory")
        mask_parent = pinned_root.open_child_directory("truth_masks")
    except _PinnedFileError as error:
        raise DatasetVerificationError("INVENTORY_TREE_MISMATCH") from error

    with mask_parent:
        try:
            target_metadata = mask_parent.child_metadata(split)
            if target_metadata is not None:
                _verify_complete_truth_mask_tree(
                    pinned_root,
                    inventory,
                    truth_payloads,
                    samples,
                )
                return
            if mask_parent.child_names():
                raise _PinnedFileError("truth_masks parent contains unknown entries")
            staging_name = f".truth-masks-{split}-{secrets.token_hex(16)}"
            pinned_root.mkdir_child(staging_name)
            staging = pinned_root.open_child_directory(staging_name)
        except _PinnedFileError as error:
            raise DatasetVerificationError("INVENTORY_TREE_MISMATCH") from error

        created_files: list[tuple[str, tuple[int, int]]] = []
        published = False
        try:
            for relative_path, document, _ in mask_artifacts:
                filename = relative_path.name
                identity = staging.write_new_file(
                    filename, canonical_json_bytes(document)
                )
                created_files.append((filename, identity))
            staging.fsync()
            if mask_parent.child_metadata(split) is not None:
                raise _PinnedFileError("truth mask split appeared during publication")
            pinned_root.replace_child_into(staging_name, mask_parent, split)
            published = True
        except _PinnedFileError as error:
            raise DatasetVerificationError("TRUTH_MASK_PUBLISH_FAILED") from error
        finally:
            if not published:
                for filename, identity in reversed(created_files):
                    try:
                        staging.unlink_owned_file(filename, identity)
                    except _PinnedFileError:
                        pass
            staging_identity = staging._identity
            staging.close()
            if not published:
                try:
                    pinned_root.rmdir_owned_child(staging_name, staging_identity)
                except _PinnedFileError:
                    pass

        _verify_complete_truth_mask_tree(
            pinned_root,
            inventory,
            truth_payloads,
            samples,
        )
        if parent_created:
            pinned_root.fsync()


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
        samples, mask_artifacts = _derive_truth_artifacts(
            inventory, split, truth_payloads
        )
        _publish_truth_masks(
            pinned_root,
            split,
            inventory,
            truth_payloads,
            samples,
            mask_artifacts,
        )
        return samples
