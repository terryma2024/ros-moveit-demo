"""Exclusive, path-safe evidence allocation and artifact registration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ArtifactRegistryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    relative_path: str
    media_type: str
    byte_size: int
    sha256: str
    producing_process: str
    simulation_session_id: str
    reset_epoch: int | None
    captured_at: str


def _validate_id(label: str, value: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ArtifactRegistryError(f"unsafe {label}: {value!r}")
    return value


def fsync_directory(path: Path) -> None:
    """Persist directory entries without following a substituted symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, document: Mapping[str, object]) -> None:
    """Fsync a complete JSON document before atomically replacing ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class TaskArtifactRegistry:
    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if root.exists() and root.is_symlink():
            raise ArtifactRegistryError("evidence root must not be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self._clock = clock
        self._batches = self.root / "batches"
        if self._batches.exists() and self._batches.is_symlink():
            raise ArtifactRegistryError("batches directory must not be a symlink")
        self._batches.mkdir(exist_ok=True)

    def allocate_batch(self, batch_id: str) -> Path:
        _validate_id("batch id", batch_id)
        result = self._batches / batch_id
        try:
            result.mkdir()
            (result / "points").mkdir()
        except FileExistsError as error:
            raise ArtifactRegistryError(f"batch already exists: {batch_id}") from error
        return result

    def allocate_point(self, batch: Path, index: int, point_id: str) -> Path:
        _validate_id("point id", point_id)
        if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
            raise ArtifactRegistryError("point index must be a positive integer")
        if batch.is_symlink() or not batch.is_dir():
            raise ArtifactRegistryError("point allocation requires an owned batch")
        try:
            relative = batch.resolve(strict=True).relative_to(self._batches)
        except (OSError, ValueError) as error:
            raise ArtifactRegistryError("point allocation requires an owned batch") from error
        if len(relative.parts) != 1 or batch.parent.resolve() != self._batches:
            raise ArtifactRegistryError("point allocation requires an owned batch")
        points = batch / "points"
        if points.is_symlink() or not points.is_dir():
            raise ArtifactRegistryError("point allocation requires an owned batch")
        result = points / f"{index:02d}-{point_id}"
        try:
            result.mkdir()
        except FileExistsError as error:
            raise ArtifactRegistryError(
                f"point already exists: {index:02d}-{point_id}"
            ) from error
        return result

    def _regular_file(self, path: Path) -> Path:
        absolute = path.absolute()
        try:
            lexical_relative = absolute.relative_to(self.root)
        except ValueError as error:
            raise ArtifactRegistryError("artifact path is outside evidence root") from error
        current = self.root
        for part in lexical_relative.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactRegistryError("artifact path contains a symlink")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, ValueError) as error:
            raise ArtifactRegistryError("artifact path is outside evidence root") from error
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise ArtifactRegistryError("artifact must be a regular file")
        return resolved

    def register_file(
        self,
        producing_process: str,
        path: Path,
        media_type: str,
        simulation_session_id: str,
        reset_epoch: int | None,
    ) -> ArtifactRecord:
        _validate_id("producing process", producing_process)
        if not media_type or any(character.isspace() for character in media_type):
            raise ArtifactRegistryError("media type must be non-empty without whitespace")
        if not simulation_session_id:
            raise ArtifactRegistryError("simulation session id must be non-empty")
        if reset_epoch is not None and (
            isinstance(reset_epoch, bool)
            or not isinstance(reset_epoch, int)
            or reset_epoch < 0
        ):
            raise ArtifactRegistryError("reset epoch must be a non-negative integer")
        resolved = self._regular_file(path)
        payload = resolved.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        relative = resolved.relative_to(self.root).as_posix()
        artifact_id = hashlib.sha256(f"{relative}\0{digest}".encode()).hexdigest()[:24]
        captured = self._clock()
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise ArtifactRegistryError("artifact clock must return a timezone-aware value")
        return ArtifactRecord(
            artifact_id=artifact_id,
            relative_path=relative,
            media_type=media_type,
            byte_size=len(payload),
            sha256=digest,
            producing_process=producing_process,
            simulation_session_id=simulation_session_id,
            reset_epoch=reset_epoch,
            captured_at=captured.astimezone(UTC).isoformat(),
        )
