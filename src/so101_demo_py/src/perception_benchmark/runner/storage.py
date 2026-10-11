"""JSON and file storage helpers of the benchmark run: atomic writes, canonical reads and sample documents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import tempfile
from types import MappingProxyType

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    PredictionRecord,
)
from so101_demo.perception_benchmark.dataset.contracts import DatasetSampleRef
from so101_demo.perception_benchmark.dataset.pinned_files import _PinnedDirectory, _PinnedFileError
from so101_demo.perception_benchmark.runner.contracts import (
    _SHA256,
    RunIntegrityError,
    RunManifest,
)


@dataclass(frozen=True, slots=True)
class LoadedRunEvidence:
    """Immutable typed and extended documents from one verified terminal run."""

    manifest: RunManifest
    evidence_root: Path
    records: tuple[PredictionRecord, ...]
    extended_record_documents: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_root", Path(self.evidence_root))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(
            self,
            "extended_record_documents",
            tuple(_freeze_document(item) for item in self.extended_record_documents),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RunIntegrityError(code)
    return value


def _jsonable(value: object) -> object:
    """Explicitly serialize the closed evidence vocabulary."""

    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise RunIntegrityError("NONFINITE_DOCUMENT_VALUE")
        return format(value, "f")
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _jsonable(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RunIntegrityError("DOCUMENT_MAPPING_KEY_INVALID")
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RunIntegrityError("NONFINITE_DOCUMENT_VALUE")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise RunIntegrityError("DOCUMENT_VALUE_UNSUPPORTED")


def _freeze_document(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_document(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_document(item) for item in value)
    return value


def _document_bytes(document: object) -> bytes:
    return canonical_json_bytes(_jsonable(document))


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags)


def _fsync_directory(path: Path) -> None:
    descriptor = _open_directory(path)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_directory(path: Path, code: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise RunIntegrityError(code)
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise RunIntegrityError(code) from error


def _create_directory(path: Path, root: Path) -> None:
    parent = _require_directory(path.parent, "OUTPUT_DIRECTORY_INVALID")
    if not parent.is_relative_to(root) and parent != root:
        raise RunIntegrityError("OUTPUT_DIRECTORY_ESCAPE")
    descriptor = _open_directory(parent)
    try:
        try:
            os.mkdir(path.name, 0o700, dir_fd=descriptor)
        except FileExistsError:
            pass
        os.fsync(descriptor)
    except OSError as error:
        raise RunIntegrityError("OUTPUT_DIRECTORY_CREATE_FAILED") from error
    finally:
        os.close(descriptor)
    _require_directory(path, "OUTPUT_DIRECTORY_INVALID")
    _fsync_directory(path)


def _atomic_write_new_json(path: Path, document: object) -> str:
    """Publish a new canonical record atomically without overwrite."""

    parent = _require_directory(path.parent, "RECORDS_DIRECTORY_INVALID")
    if path.exists() or path.is_symlink():
        raise RunIntegrityError("RECORD_ALREADY_EXISTS")
    payload = _document_bytes(document)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        temporary = None
        _fsync_directory(parent)
    except FileExistsError as error:
        raise RunIntegrityError("RECORD_ALREADY_EXISTS") from error
    except OSError as error:
        raise RunIntegrityError("RECORD_WRITE_FAILED") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return _sha256(payload)


def _atomic_write_new_bytes(path: Path, payload: bytes, code: str) -> None:
    parent = _require_directory(path.parent, "MASK_DIRECTORY_INVALID")
    if path.exists() or path.is_symlink():
        raise RunIntegrityError("MASK_ALREADY_EXISTS")
    descriptor = _open_directory(parent)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(path.name, flags, 0o600, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(descriptor)
    except FileExistsError as error:
        raise RunIntegrityError("MASK_ALREADY_EXISTS") from error
    except OSError as error:
        raise RunIntegrityError(code) from error
    finally:
        os.close(descriptor)
    _fsync_directory(parent)


def _atomic_replace_json(path: Path, document: object, code: str) -> str:
    parent = _require_directory(path.parent, "OUTPUT_DIRECTORY_INVALID")
    if path.is_symlink():
        raise RunIntegrityError(code)
    payload = _document_bytes(document)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    except OSError as error:
        raise RunIntegrityError(code) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return _sha256(payload)


def _safe_relative_path(root: Path, relative_path: str, code: str) -> Path:
    if not isinstance(relative_path, str) or "\\" in relative_path:
        raise RunIntegrityError(code)
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RunIntegrityError(code)
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise RunIntegrityError(code)
    target = root.joinpath(*relative.parts)
    if target.is_symlink() or not target.is_file():
        raise RunIntegrityError(code)
    try:
        target.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise RunIntegrityError(code) from error
    return target


def _create_new_directory(path: Path, root: Path, code: str) -> Path:
    if path.exists() or path.is_symlink():
        raise RunIntegrityError(code)
    parent = _require_directory(path.parent, "MASK_DIRECTORY_INVALID")
    if parent != root and not parent.is_relative_to(root):
        raise RunIntegrityError("OUTPUT_DIRECTORY_ESCAPE")
    descriptor = _open_directory(parent)
    try:
        os.mkdir(path.name, 0o700, dir_fd=descriptor)
        os.fsync(descriptor)
    except FileExistsError as error:
        raise RunIntegrityError(code) from error
    except OSError as error:
        raise RunIntegrityError("MASK_DIRECTORY_CREATE_FAILED") from error
    finally:
        os.close(descriptor)
    return _require_directory(path, "MASK_DIRECTORY_INVALID")


def _decode_canonical_json(
    payload: bytes, code: str
) -> tuple[dict[str, object], bytes]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunIntegrityError(code) from error
    if not isinstance(document, dict):
        raise RunIntegrityError(code)
    try:
        canonical = canonical_json_bytes(document)
    except (TypeError, ValueError) as error:
        raise RunIntegrityError(code) from error
    if canonical != payload:
        raise RunIntegrityError(code)
    return document, payload


def _read_canonical_json(path: Path, code: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink() or not path.is_file():
        raise RunIntegrityError(code)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise RunIntegrityError(code) from error
    return _decode_canonical_json(payload, code)


def _read_pinned_canonical_json(
    pinned_root: _PinnedDirectory,
    relative_path: str,
    code: str,
) -> tuple[dict[str, object], bytes]:
    try:
        payload = pinned_root.read_file(relative_path)
    except _PinnedFileError as error:
        raise RunIntegrityError("RUN_EVIDENCE_FILE_UNSAFE") from error
    return _decode_canonical_json(payload, code)


def _sample_document_matches(
    document: object, sample: DatasetSampleRef
) -> bool:
    if not isinstance(document, Mapping):
        return False
    expected = {
        "formal_sample_index": sample.formal_sample_index,
        "split": sample.split,
        "scenario": sample.scenario,
        "image_relpath": sample.image_relpath,
        "label_relpath": sample.label_relpath,
        "truth_relpath": sample.truth_relpath,
        "image_sha256": sample.image_sha256,
        "truth_count": sample.truth_count,
    }
    return all(document.get(name) == value for name, value in expected.items())
