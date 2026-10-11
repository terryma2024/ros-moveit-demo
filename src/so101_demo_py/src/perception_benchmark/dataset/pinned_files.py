"""Pinned directory and file access: archive members, safe paths, atomic no-replace renames and stable identities."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import sys
import tarfile

from so101_demo.perception_benchmark.dataset.contracts import (
    _KINDS,
    DatasetVerificationError,
    Split,
)


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
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


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


_DARWIN_RENAME_EXCL = 0x00000004


_LINUX_RENAME_NOREPLACE = 0x00000001


def _rename_directory_noreplace(
    source_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
) -> None:
    """Atomically rename one directory without replacing the destination."""
    if (
        type(source_fd) is not int
        or source_fd < 0
        or type(destination_fd) is not int
        or destination_fd < 0
        or not _safe_member_path(source_name)
        or len(PurePosixPath(source_name).parts) != 1
        or not _safe_member_path(destination_name)
        or len(PurePosixPath(destination_name).parts) != 1
    ):
        raise OSError(errno.EINVAL, "unsafe no-replace rename input")

    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        flags = _DARWIN_RENAME_EXCL
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        flags = _LINUX_RENAME_NOREPLACE
    else:
        function = None
        flags = 0
    if function is None:
        raise OSError(errno.ENOSYS, "atomic no-replace rename is unavailable")

    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        source_fd,
        os.fsencode(source_name),
        destination_fd,
        os.fsencode(destination_name),
        flags,
    )
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        raise OSError(error_number, os.strerror(error_number))


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

    def __init__(self, path: Path, descriptor: int, identity: tuple[int, int]) -> None:
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
                or (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino)
                or (opened.st_dev, opened.st_ino) != (bound.st_dev, bound.st_ino)
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

    def create_pinned_child(
        self,
        name: str,
        mode: int = 0o700,
        *,
        fsync_parent: bool = True,
    ) -> "_PinnedDirectory":
        if not _safe_member_path(name) or len(PurePosixPath(name).parts) != 1:
            raise _PinnedFileError("child name is unsafe")
        descriptor: int | None = None
        try:
            self._assert_identity()
            os.mkdir(name, mode=mode, dir_fd=self._descriptor)
            observed = os.stat(name, dir_fd=self._descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(observed.st_mode):
                raise _PinnedFileError("new child is not a real directory")
            observed_identity = observed.st_dev, observed.st_ino
            descriptor = os.open(name, _OPEN_DIRECTORY_FLAGS, dir_fd=self._descriptor)
            opened = os.fstat(descriptor)
            after = os.stat(name, dir_fd=self._descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or observed_identity != (opened.st_dev, opened.st_ino)
                or observed_identity != (after.st_dev, after.st_ino)
            ):
                raise _PinnedFileError("new child changed while opening")
            if fsync_parent:
                self.fsync()
            child = _PinnedDirectory(
                self.path / name,
                descriptor,
                observed_identity,
            )
            descriptor = None
            return child
        except _PinnedFileError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise _PinnedFileError("child directory cannot be created") from error

    def create_random_pinned_child(self, prefix: str) -> tuple[str, "_PinnedDirectory"]:
        name = f"{prefix}{secrets.token_hex(16)}"
        return name, self.create_pinned_child(name, mode=0o700)

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
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
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
            raise
        except OSError as error:
            raise _PinnedFileError("new file cannot be persisted") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _open_descendant_directory(self, relative_path: str) -> int:
        if relative_path and not _safe_member_path(relative_path):
            raise _PinnedFileError("directory path is unsafe")
        descriptor = os.dup(self._descriptor)
        try:
            root_metadata = os.fstat(descriptor)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._identity:
                raise _PinnedFileError("pinned root identity changed")
            for part in PurePosixPath(relative_path).parts if relative_path else ():
                next_descriptor = os.open(part, _OPEN_DIRECTORY_FLAGS, dir_fd=descriptor)
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
