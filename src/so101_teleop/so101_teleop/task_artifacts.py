"""Manifest-only task artifact registration and read sandbox."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid
from typing import Mapping


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_RENDER_BYTES = 10 * 1024 * 1024


class ArtifactAccessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactEntry:
    artifact_id: str
    relative_path: str
    media_type: str
    byte_size: int
    sha256: str
    capture_id: str | None = None
    run_id: str | None = None
    source_artifact_id: str | None = None
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class OpenedArtifact:
    path: Path
    media_type: str
    byte_size: int
    sha256: str


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class ManifestArtifactStore:
    def __init__(self, root: Path) -> None:
        root = Path(root)
        if not root.is_absolute() or root.is_symlink():
            raise ArtifactAccessError("ARTIFACT_ROOT_INVALID")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise ArtifactAccessError("ARTIFACT_ROOT_INVALID")
        self.root = root
        self.manifest_path = root / "task-manifest.json"
        if not self.manifest_path.exists():
            _atomic_json(
                self.manifest_path,
                {"schema_version": 1, "artifacts": []},
            )

    @staticmethod
    def _id(label: str, value: str | None) -> str | None:
        if value is not None and _SAFE_ID.fullmatch(value) is None:
            raise ArtifactAccessError(f"ARTIFACT_{label.upper()}_INVALID")
        return value

    def _entries(self) -> dict[str, ArtifactEntry]:
        if self.root.is_symlink() or self.manifest_path.is_symlink():
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID")
        try:
            self.manifest_path.resolve(strict=True).relative_to(
                self.root.resolve(strict=True)
            )
        except (OSError, ValueError) as error:
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID") from error
        try:
            document = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID") from error
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID")
        raw = document.get("artifacts")
        if not isinstance(raw, list):
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID")
        entries = {}
        try:
            for item in raw:
                entry = ArtifactEntry(**item)
                if entry.artifact_id in entries:
                    raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID")
                entries[entry.artifact_id] = entry
        except (TypeError, ValueError) as error:
            raise ArtifactAccessError("ARTIFACT_MANIFEST_INVALID") from error
        return entries

    def _write(self, entries: Mapping[str, ArtifactEntry]) -> None:
        _atomic_json(
            self.manifest_path,
            {
                "schema_version": 1,
                "artifacts": [
                    asdict(entries[key]) for key in sorted(entries)
                ],
            },
        )

    def _regular(self, path: Path) -> Path:
        absolute = path.absolute()
        try:
            relative = absolute.relative_to(self.root.absolute())
        except ValueError as error:
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID") from error
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
        try:
            resolved = absolute.resolve(strict=True)
            resolved.relative_to(self.root.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID") from error
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
        return resolved

    def register_file(
        self,
        path: Path,
        media_type: str,
        *,
        capture_id: str | None = None,
        run_id: str | None = None,
        source_artifact_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ArtifactEntry:
        capture_id = self._id("capture_id", capture_id)
        run_id = self._id("run_id", run_id)
        resolved = self._regular(Path(path))
        payload = resolved.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        relative = resolved.relative_to(self.root.resolve(strict=True)).as_posix()
        artifact_id = hashlib.sha256(f"{relative}\0{digest}".encode()).hexdigest()[:24]
        entry = ArtifactEntry(
            artifact_id,
            relative,
            media_type,
            len(payload),
            digest,
            capture_id,
            run_id,
            source_artifact_id,
            dict(metadata or {}),
        )
        entries = self._entries()
        existing = entries.get(artifact_id)
        if existing is not None and existing != entry:
            raise ArtifactAccessError("ARTIFACT_ID_COLLISION")
        entries[artifact_id] = entry
        self._write(entries)
        return entry

    def open(self, artifact_id: str) -> OpenedArtifact:
        entry = self._entries().get(artifact_id)
        if entry is None:
            raise ArtifactAccessError("ARTIFACT_NOT_FOUND")
        relative = PurePosixPath(entry.relative_path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
        resolved = self._regular(self.root.joinpath(*relative.parts))
        payload = resolved.read_bytes()
        if len(payload) != entry.byte_size or hashlib.sha256(payload).hexdigest() != entry.sha256:
            raise ArtifactAccessError("ARTIFACT_CHECKSUM_MISMATCH")
        return OpenedArtifact(resolved, entry.media_type, entry.byte_size, entry.sha256)

    def register_rendered_image(
        self,
        capture_id: str,
        source_artifact_id: str,
        png: bytes,
        metadata: Mapping[str, object],
    ) -> ArtifactEntry:
        capture_id = self._id("capture_id", capture_id)
        if not png.startswith(_PNG_MAGIC) or len(png) > _MAX_RENDER_BYTES:
            raise ArtifactAccessError("RENDER_PNG_INVALID")
        entries = self._entries()
        source = entries.get(source_artifact_id)
        if (
            source is None
            or source.capture_id != capture_id
            or Path(source.relative_path).suffix.lower() != ".ply"
        ):
            raise ArtifactAccessError("RENDER_SOURCE_INVALID")
        try:
            view = tuple(float(item) for item in metadata["view_matrix"])
            projection = tuple(float(item) for item in metadata["projection_matrix"])
            point_size = float(metadata["point_size"])
            width = int(metadata["viewport_width"])
            height = int(metadata["viewport_height"])
        except (KeyError, TypeError, ValueError) as error:
            raise ArtifactAccessError("RENDER_METADATA_INVALID") from error
        if (
            len(view) != 16
            or len(projection) != 16
            or not all(math.isfinite(item) for item in (*view, *projection, point_size))
            or point_size <= 0
            or width <= 0
            or height <= 0
        ):
            raise ArtifactAccessError("RENDER_METADATA_INVALID")
        directory = self.root / "captures" / capture_id
        if directory.is_symlink():
            raise ArtifactAccessError("ARTIFACT_PATH_INVALID")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "point-cloud-view.png"
        try:
            with target.open("xb") as stream:
                stream.write(png)
        except FileExistsError as error:
            raise ArtifactAccessError("RENDER_ALREADY_EXISTS") from error
        return self.register_file(
            target,
            "image/png",
            capture_id=capture_id,
            source_artifact_id=source_artifact_id,
            metadata=metadata,
        )
