"""Constants, the capability key, the inventory, grant and seal records and the access log checks of the dataset."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
from types import MappingProxyType
from typing import Literal

from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
)

Split = Literal["val", "test"]


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


_EXPECTED_SAMPLE_COUNT = 200


_EXPECTED_IMAGE_SIZE = (640, 480)


_LABEL_COORDINATE_FORMAT = ".9f"


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
            event_sha = _require_sha256(self.event_sha256, "TEST_ACCESS_GRANT_INVALID")
            sealed_sha = _require_sha256(
                self.sealed_member_inventory_sha256,
                "TEST_ACCESS_GRANT_INVALID",
            )
            locks = tuple(self.threshold_lock_sha256s)
            if len(locks) != 2:
                raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
            normalized_locks = tuple(
                _require_sha256(value, "TEST_ACCESS_GRANT_INVALID") for value in locks
            )
            if normalized_locks[0] == normalized_locks[1]:
                raise DatasetVerificationError("TEST_ACCESS_GRANT_INVALID")
            granted_at = datetime.fromisoformat(self.granted_at)
            if granted_at.tzinfo is None or granted_at.utcoffset() != timezone.utc.utcoffset(
                granted_at
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
    access_log_path: Path | None = field(default=None, repr=False, compare=False)
    _capability: str | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_root", Path(self.dataset_root))
        object.__setattr__(self, "scenario_counts", MappingProxyType(dict(self.scenario_counts)))
        object.__setattr__(self, "samples", tuple(self.samples))
        if self.access_log_path is not None:
            access_log_path = Path(self.access_log_path)
            if not access_log_path.is_absolute():
                raise ValueError("access_log_path must be absolute")
            object.__setattr__(self, "access_log_path", access_log_path)


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
                _require_sha256(verify_lock(Path(yolo_lock_path)), "THRESHOLD_LOCK_SHA256_INVALID"),
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
        _require_sha256(value, "THRESHOLD_LOCK_SHA256_INVALID") for value in threshold_lock_sha256s
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
