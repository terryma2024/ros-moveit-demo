"""Immutable inference input snapshots for the v4 data plane.

The v4 design (section 7.3) keeps raw RGB-D arrays out of the control frame. A Worker writes the
array into a task-owned input root under a temporary name, `fsync`s it, atomically renames it,
and publishes a descriptor. The Broker opens that descriptor *relative to its pinned root*,
re-verifies every declared fact against the bytes, reads, and closes immediately.

Two limits are enforced independently, because they protect different things:
``broker_max_frame_bytes`` bounds the control frame, and ``max_input_snapshot_bytes`` bounds the
data the descriptor points at. Neither can substitute for the other.

Snapshots are never deleted here. When a request completes, is cancelled, or is invalidated, the
snapshot becomes a reported *deletion candidate* and stays on disk until a human authorizes
removal.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

#: The lifecycle outcome for a released snapshot.
DELETION_CANDIDATE = "DELETION_CANDIDATE"

#: The only encoding supported. A shared-memory or raw-buffer variant would need its own design.
NPY_ENCODING = "npy"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SLOT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

#: The default ceiling: 64 MiB is far above any RGB-D frame and far below "an array in a frame".
DEFAULT_MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


class SnapshotError(RuntimeError):
    """An input snapshot contract failed. Every failure here is a refusal."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class MaxSnapshotExceeded(SnapshotError):
    """The snapshot is larger than ``max_input_snapshot_bytes``."""


@dataclass(frozen=True)
class SnapshotDescriptor:
    """The declared, immutable facts about one snapshot."""

    relative_path: str
    size_bytes: int
    sha256: str
    shape: tuple[int, ...]
    dtype: str
    encoding: str
    frame_timestamp_ns: int

    def __post_init__(self) -> None:
        path = validate_relative_path(self.relative_path)
        object.__setattr__(self, "relative_path", str(path))
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ValueError("size_bytes must be an int")
        if self.size_bytes <= 0:
            raise ValueError("size_bytes must be positive")
        if not isinstance(self.sha256, str) or not _SHA256.match(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        shape = tuple(self.shape)
        if not shape:
            raise ValueError("shape must be non-empty")
        for dimension in shape:
            if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
                raise ValueError(f"shape entry {dimension!r} must be a positive int")
        object.__setattr__(self, "shape", shape)
        if not isinstance(self.dtype, str) or not self.dtype:
            raise ValueError("dtype is required")
        if self.encoding != NPY_ENCODING:
            raise ValueError(f"encoding must be {NPY_ENCODING!r}")
        if isinstance(self.frame_timestamp_ns, bool) or not isinstance(
                self.frame_timestamp_ns, int):
            raise ValueError("frame_timestamp_ns must be an int")
        if self.frame_timestamp_ns < 0:
            raise ValueError("frame_timestamp_ns must not be negative")

    def to_document(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "shape": list(self.shape),
            "dtype": self.dtype,
            "encoding": self.encoding,
            "frame_timestamp_ns": self.frame_timestamp_ns,
        }

    @staticmethod
    def from_document(document: object) -> "SnapshotDescriptor":
        if not isinstance(document, Mapping):
            raise SnapshotError("SNAPSHOT_DESCRIPTOR", "descriptor is not a mapping")
        try:
            return SnapshotDescriptor(
                relative_path=document["relative_path"],
                size_bytes=document["size_bytes"],
                sha256=document["sha256"],
                shape=tuple(document["shape"]),
                dtype=document["dtype"],
                encoding=document["encoding"],
                frame_timestamp_ns=document["frame_timestamp_ns"],
            )
        except KeyError as error:
            raise SnapshotError("SNAPSHOT_DESCRIPTOR", f"missing field {error}") from error
        except (TypeError, ValueError) as error:
            raise SnapshotError("SNAPSHOT_DESCRIPTOR", str(error)) from error


def validate_relative_path(value: object) -> PurePosixPath:
    """A snapshot path must be a clean, relative, POSIX path with no traversal."""

    if not isinstance(value, str) or not value:
        raise SnapshotError("SNAPSHOT_PATH", "relative_path must be a non-empty string")
    if "\\" in value:
        raise SnapshotError("SNAPSHOT_PATH", "backslashes are not a path separator here")
    candidate = PurePosixPath(value)
    if candidate.is_absolute():
        raise SnapshotError("SNAPSHOT_PATH", "absolute paths are refused")
    if any(part in ("..", ".") for part in candidate.parts):
        raise SnapshotError("SNAPSHOT_PATH", f"traversal component in {value!r}")
    if not candidate.parts:
        raise SnapshotError("SNAPSHOT_PATH", "empty path")
    return candidate


@dataclass(frozen=True)
class SnapshotReadback:
    """What a read actually verified, for the evidence record."""

    relative_path: str
    size_bytes: int
    verified: bool


@dataclass(frozen=True)
class DeletionCandidate:
    """A released snapshot. Reported, never removed without authorization."""

    request_id: str
    descriptor: SnapshotDescriptor
    outcome: str = DELETION_CANDIDATE
    detail: str = ""


class SnapshotStore:
    """The pinned input root: the only place a snapshot may be written to or read from."""

    def __init__(self, *, root: Path, max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES
                 ) -> None:
        if isinstance(max_snapshot_bytes, bool) or not isinstance(max_snapshot_bytes, int):
            raise SnapshotError("MAX_INPUT_SNAPSHOT_BYTES", "limit must be an int")
        if max_snapshot_bytes <= 0:
            raise SnapshotError("MAX_INPUT_SNAPSHOT_BYTES", "limit must be positive")
        self.root = Path(root)
        self.max_snapshot_bytes = int(max_snapshot_bytes)
        self._pinned_root = self.root

    # -- writing -------------------------------------------------------------------------

    def write(self, array: object, *, slot: str, frame_timestamp_ns: int) -> SnapshotDescriptor:
        """Write one array immutably and return its descriptor."""

        import numpy as np

        if not isinstance(slot, str) or not _SLOT.match(slot):
            raise SnapshotError("SNAPSHOT_SLOT", f"{slot!r} is not a slot identifier")
        if not isinstance(array, np.ndarray):
            raise SnapshotError("SNAPSHOT_VALUE", f"{type(array).__name__} is not an ndarray")
        if isinstance(frame_timestamp_ns, bool) or not isinstance(frame_timestamp_ns, int) \
                or frame_timestamp_ns < 0:
            raise SnapshotError("SNAPSHOT_TIMESTAMP", repr(frame_timestamp_ns))

        self._ensure_root()
        directory = self.root / slot
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)

        name = f"frame-{frame_timestamp_ns:020d}-{os.getpid()}.npy"
        target = directory / name
        temporary = directory / f"{name}.part"
        buffer = io.BytesIO()
        np.save(buffer, array, allow_pickle=False)
        payload = buffer.getvalue()
        if len(payload) > self.max_snapshot_bytes:
            raise MaxSnapshotExceeded(
                "MAX_INPUT_SNAPSHOT_BYTES",
                f"{len(payload)} > {self.max_snapshot_bytes} bytes for {slot}",
            )

        descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        except OSError:  # pragma: no cover - not every filesystem allows directory fsync
            pass
        finally:
            os.close(directory_descriptor)
        # Immutable for the campaign: the owner write bit is removed after the rename.
        os.chmod(target, 0o400)

        return SnapshotDescriptor(
            relative_path=f"{slot}/{name}",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            shape=tuple(int(dimension) for dimension in array.shape),
            dtype=str(array.dtype),
            encoding=NPY_ENCODING,
            frame_timestamp_ns=frame_timestamp_ns,
        )

    def _ensure_root(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    # -- reading -------------------------------------------------------------------------

    def resolve(self, descriptor: SnapshotDescriptor) -> Path:
        """The absolute path of a descriptor, with the traversal checks re-applied."""

        if not isinstance(descriptor, SnapshotDescriptor):
            raise SnapshotError("SNAPSHOT_DESCRIPTOR", type(descriptor).__name__)
        relative = validate_relative_path(descriptor.relative_path)
        candidate = self._pinned_root.joinpath(*relative.parts)
        # Defence in depth: the joined path must still be under the pinned root.
        if not str(candidate).startswith(str(self._pinned_root) + os.sep):
            raise SnapshotError("SNAPSHOT_PATH", f"{candidate} escapes {self._pinned_root}")
        return candidate

    def read_document(self, document: object):
        """Validate a wire document and read it. The Broker's only entry point."""

        descriptor = SnapshotDescriptor.from_document(document)
        return self.read(descriptor)

    def read(self, descriptor: SnapshotDescriptor):
        """Open, verify, read and close one snapshot under the pinned root."""

        import numpy as np

        path = self.resolve(descriptor)
        try:
            metadata = os.lstat(path)
        except FileNotFoundError as error:
            raise SnapshotError("SNAPSHOT_MISSING", str(path)) from error
        except OSError as error:
            raise SnapshotError("SNAPSHOT_UNREADABLE", str(error)) from error
        if os.path.islink(path):
            raise SnapshotError("SNAPSHOT_SYMLINK", str(path))
        if not os.path.isfile(path):
            raise SnapshotError("SNAPSHOT_NOT_FILE", str(path))
        if metadata.st_size > self.max_snapshot_bytes:
            raise MaxSnapshotExceeded(
                "MAX_INPUT_SNAPSHOT_BYTES",
                f"{path} is {metadata.st_size} > {self.max_snapshot_bytes} bytes",
            )
        if metadata.st_size != descriptor.size_bytes:
            raise SnapshotError(
                "SNAPSHOT_SIZE", f"{path} is {metadata.st_size}, declared {descriptor.size_bytes}"
            )

        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != descriptor.sha256:
            raise SnapshotError("SNAPSHOT_SHA256", f"{path} digest mismatch")

        try:
            array = np.load(io.BytesIO(payload), allow_pickle=False)
        except (ValueError, OSError) as error:
            raise SnapshotError("SNAPSHOT_DECODE", str(error)) from error
        if tuple(int(dimension) for dimension in array.shape) != tuple(descriptor.shape):
            raise SnapshotError(
                "SNAPSHOT_SHAPE", f"{array.shape} != {descriptor.shape}"
            )
        if str(array.dtype) != descriptor.dtype:
            raise SnapshotError("SNAPSHOT_DTYPE", f"{array.dtype} != {descriptor.dtype}")
        return array, SnapshotReadback(relative_path=descriptor.relative_path,
                                       size_bytes=descriptor.size_bytes, verified=True)


class SnapshotRegistry:
    """Track live snapshots per request, and report released ones as deletion candidates."""

    def __init__(self, *, store: SnapshotStore) -> None:
        self._store = store
        self._live: dict[str, SnapshotDescriptor] = {}
        self._released: list[DeletionCandidate] = []

    @property
    def store(self) -> SnapshotStore:
        return self._store

    def register(self, *, request_id: str, slot: str, array: object,
                 frame_timestamp_ns: int) -> SnapshotDescriptor:
        if not isinstance(request_id, str) or not request_id:
            raise SnapshotError("SNAPSHOT_REQUEST", "request_id is required")
        if request_id in self._live or any(
                item.request_id == request_id for item in self._released):
            raise SnapshotError("SNAPSHOT_REQUEST_DUPLICATE", request_id)
        descriptor = self._store.write(array, slot=slot, frame_timestamp_ns=frame_timestamp_ns)
        self._live[request_id] = descriptor
        return descriptor

    def live(self, *, request_id: str) -> tuple[SnapshotDescriptor, ...]:
        descriptor = self._live.get(request_id)
        return () if descriptor is None else (descriptor,)

    def _release(self, request_id: str, detail: str) -> SnapshotDescriptor:
        descriptor = self._live.pop(request_id, None)
        if descriptor is None:
            raise SnapshotError("SNAPSHOT_REQUEST_UNKNOWN", request_id)
        self._released.append(DeletionCandidate(request_id=request_id, descriptor=descriptor,
                                                detail=detail))
        return descriptor

    def complete(self, *, request_id: str) -> SnapshotDescriptor:
        """The request finished: the snapshot is now a deletion candidate."""

        return self._release(request_id, "request completed")

    def cancel(self, *, request_id: str, reason: str) -> SnapshotDescriptor:
        """The request was cancelled: same lifecycle, different reason."""

        return self._release(request_id, f"request cancelled: {reason}")

    def invalidate_all(self, *, reason: str) -> tuple[SnapshotDescriptor, ...]:
        """Broker identity changed: every live snapshot is released at once."""

        released = tuple(
            self._release(request_id, f"invalidated: {reason}")
            for request_id in sorted(self._live)
        )
        return released

    def pending_deletion_candidates(self) -> tuple[DeletionCandidate, ...]:
        return tuple(self._released)

    def verify_still_readable(self, request_id: str) -> SnapshotReadback | None:
        """Re-read a released snapshot, so 'held until released' is a checkable claim."""

        for candidate in self._released:
            if candidate.request_id == request_id:
                _array, readback = self._store.read(candidate.descriptor)
                return readback
        return None
