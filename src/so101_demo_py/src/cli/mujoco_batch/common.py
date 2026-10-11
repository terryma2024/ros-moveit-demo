"""Error type and small helpers shared by the MuJoCo parallel batch modules."""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Mapping

from so101_demo.parallel_batch.contracts import (
    AttemptIdentity,
    RunMode,
    ValidationIdentity,
)


class CliError(RuntimeError):
    """Startup or batch composition failed closed."""


def _integer(name: str, value: str) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise CliError(f"MALFORMED_INTEGER: {name}")
    result = int(value)
    if result <= 0:
        raise CliError(f"MALFORMED_INTEGER: {name}")
    return result


def _positive_float(name: str, value: str) -> float:
    if not isinstance(value, str) or not value.isascii():
        raise CliError(f"MALFORMED_NUMBER: {name}")
    try:
        result = float(value)
    except ValueError as error:
        raise CliError(f"MALFORMED_NUMBER: {name}") from error
    if not (result > 0.0 and result < float("inf")):
        raise CliError(f"MALFORMED_NUMBER: {name}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise CliError(f"PROVENANCE_READ_FAILED: {path}") from error
    return digest.hexdigest()


def _absolute(name: str, path: Path) -> Path:
    raw = str(path)
    if not path.is_absolute() or "\0" in raw or any(part in {".", ".."} for part in raw.split("/")):
        raise CliError(f"ABSOLUTE_PATH_REQUIRED: {name}")
    return path


def _read_existing_json(path: Path, *, label: str) -> Mapping[str, object]:
    """Read one bounded owner-controlled recovery authority without following links."""
    try:
        before = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise CliError(f"RECOVERY_{label}_MISSING") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or before.st_uid != os.getuid()
            or opened.st_uid != os.getuid()
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_size <= 0
            or opened.st_size > 8 * 1024 * 1024
        ):
            raise CliError(f"RECOVERY_{label}_INVALID")
        payload = os.read(descriptor, opened.st_size + 1)
        after = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise CliError(f"RECOVERY_{label}_CHANGED")
        document = json.loads(payload.decode("utf-8", errors="strict"))
        if type(document) is not dict:
            raise CliError(f"RECOVERY_{label}_INVALID")
        return document
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliError(f"RECOVERY_{label}_INVALID") from error
    finally:
        os.close(descriptor)


def _identity(lease, mode):
    value = {
        "batch_id": lease.batch_id,
        "coordinator_epoch": lease.coordinator_epoch,
        "worker_id": lease.worker_id,
        "worker_generation": lease.worker_generation,
        "point_id": lease.point_id,
        "lease_generation": lease.lease_generation,
    }
    if mode is RunMode.EXECUTE:
        return AttemptIdentity(**value, attempt_id=lease.attempt_id)
    return ValidationIdentity(**value, validation_id=lease.attempt_id)


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _lease_wire(lease):
    if lease is None:
        return None
    return {
        name: getattr(lease, name)
        for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        )
    }


def _write_json(path: Path, document: Mapping[str, object]) -> None:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
