"""The recording receipt: what phase 1 of the two-phase collection leaves for phase 2 to trust.

Written under `<attempt>/raw/recording-receipt.json` after the bag is closed. It holds the attempt's lease identity, the sha256 and
size of every file under `raw/` (the bag, scene reads, record stats, pilot result, ready.json, lease.json) and of the documents the
offline processor reads: the Teacher manifest, the recorder orchestration record (which carries any deferred diagnostic fault), the inputs manifest, the scope
and the lease. Hashing reads the bag back through the
page cache; nothing here fsyncs the bag. The receipt itself is written atomically (temporary file, rename).

All paths of files inside the attempt are relative to the attempt directory, so they survive the rename of the working directory to
`sealed/`. The inputs manifest and the scope are shared run files: only their hashes are bound (the host compares them with the
task result's own references).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

RECEIPT_KIND = "ACT_RECORDING_RECEIPT"
RECEIPT_SCHEMA_VERSION = 1
RECEIPT_RELATIVE = Path("raw") / "recording-receipt.json"
TEACHER_MANIFEST_RELATIVE = Path("dynamic") / "dynamic-execute-manifest.json"
LEASE_RELATIVE = Path("raw") / "lease.json"
ORCHESTRATION_RELATIVE = Path("recorder-orchestration.json")
EXTERNAL_DOCUMENTS = ("inputs_manifest", "scope")
_CHUNK = 4 * 1024 * 1024
_LEASE_FIELDS = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id", "attempt_id", "lease_generation",
                 "lease_issued_monotonic_s", "lease_deadline_monotonic_s")


def hash_regular_file(path) -> tuple[str, int]:
    """(sha256, size) of a regular file, read without following symlinks."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("RECORDING_RECEIPT_NOT_A_REGULAR_FILE")
        digest, size = hashlib.sha256(), 0
        buffer = bytearray(_CHUNK)
        view = memoryview(buffer)
        while True:
            count = os.readv(descriptor, [buffer])
            if count == 0:
                break
            digest.update(view[:count])
            size += count
        return digest.hexdigest(), size
    finally:
        os.close(descriptor)


def _entry(path: str, source) -> dict:
    sha256, size = hash_regular_file(source)
    return {"path": path, "sha256": sha256, "size": size}


def _raw_files(root: Path) -> list[Path]:
    raw = root / "raw"
    found = []
    for directory, names, files in os.walk(raw, followlinks=False):
        for name in names:
            if (Path(directory) / name).is_symlink():
                raise ValueError("RECORDING_RECEIPT_SYMLINK")
        for name in files:
            path = Path(directory) / name
            if path.relative_to(root) == RECEIPT_RELATIVE or (path.parent == raw and path.name.endswith(".tmp")):
                continue
            found.append(path)
    return sorted(found)


def write_recording_receipt(attempt_root, *, lease_identity: dict, identity: dict, inputs_manifest, scope, orchestration_record=None,
                            teacher_manifest=None) -> dict:
    """Hash everything and write `raw/recording-receipt.json` atomically; returns the facts the caller records
    (`path`, `sha256`, `files`, `bytes`). `lease.json` must already be under `raw/`. `teacher_manifest` defaults to
    `<attempt>/dynamic/dynamic-execute-manifest.json`. Raises on a missing or unreadable file."""
    root = Path(attempt_root)
    raw_files = [_entry(path.relative_to(root).as_posix(), path) for path in _raw_files(root)]
    by_path = {item["path"]: item for item in raw_files}
    if LEASE_RELATIVE.as_posix() not in by_path:
        raise ValueError("RECORDING_RECEIPT_LEASE_MISSING")
    documents = {
        "teacher_manifest": _entry(TEACHER_MANIFEST_RELATIVE.as_posix(),
                                  root / TEACHER_MANIFEST_RELATIVE if teacher_manifest is None else teacher_manifest),
        "lease": dict(by_path[LEASE_RELATIVE.as_posix()]),
        # carries `fault_deferred_to_processing`, which decides how phase 2 treats the bag: bound like the Teacher manifest
        "recorder_orchestration": _entry(ORCHESTRATION_RELATIVE.as_posix(),
                                         root / ORCHESTRATION_RELATIVE if orchestration_record is None else orchestration_record),
    }
    for name, source in (("inputs_manifest", inputs_manifest), ("scope", scope)):
        sha256, size = hash_regular_file(source)
        documents[name] = {"sha256": sha256, "size": size}
    receipt = {"kind": RECEIPT_KIND, "schema_version": RECEIPT_SCHEMA_VERSION,
               "lease_identity": {name: lease_identity[name] for name in _LEASE_FIELDS}, "identity": dict(identity),
               "raw_files": raw_files, "documents": documents}
    payload = json.dumps(receipt, sort_keys=True, allow_nan=False).encode() + b"\n"
    target = root / RECEIPT_RELATIVE
    staged = target.with_name(target.name + ".tmp")
    with open(staged, "xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, target)
    return {"path": RECEIPT_RELATIVE.as_posix(), "sha256": hashlib.sha256(payload).hexdigest(), "files": len(raw_files),
            "bytes": sum(item["size"] for item in raw_files)}


def verify_recording_receipt(attempt_root, *, lease_identity: dict | None = None, identity: dict | None = None,
                             external: dict | None = None) -> dict:
    """Re-hash every file the receipt lists and compare; refuses an unlisted file under `raw/`, a missing or changed file, a lease
    identity other than `lease_identity` and external document hashes other than `external` (`{name: sha256}`).

    Returns `{sha256, files, bytes}` of the receipt. Every refusal is a ValueError whose message starts `RECORDING_RECEIPT_`."""
    root = Path(attempt_root)
    try:
        payload = _read_receipt_bytes(root / RECEIPT_RELATIVE)
        receipt = json.loads(payload)
    except (OSError, ValueError) as error:
        raise ValueError("RECORDING_RECEIPT_UNREADABLE") from error
    if (type(receipt) is not dict or set(receipt) != {"kind", "schema_version", "lease_identity", "identity", "raw_files", "documents"}
            or receipt["kind"] != RECEIPT_KIND or receipt["schema_version"] != RECEIPT_SCHEMA_VERSION
            or type(receipt["raw_files"]) is not list or type(receipt["documents"]) is not dict
            or set(receipt["documents"]) != {"teacher_manifest", "inputs_manifest", "scope", "lease",
                                                       "recorder_orchestration"}):
        raise ValueError("RECORDING_RECEIPT_SHAPE_INVALID")
    if lease_identity is not None and receipt["lease_identity"] != {name: lease_identity[name] for name in _LEASE_FIELDS}:
        raise ValueError("RECORDING_RECEIPT_LEASE_MISMATCH")
    if identity is not None and receipt["identity"] != identity:
        raise ValueError("RECORDING_RECEIPT_IDENTITY_MISMATCH")
    listed = set()
    total = 0
    for item in receipt["raw_files"]:
        if type(item) is not dict or set(item) != {"path", "sha256", "size"} or type(item["path"]) is not str:
            raise ValueError("RECORDING_RECEIPT_SHAPE_INVALID")
        _check_entry(root, item)
        listed.add(item["path"])
        total += item["size"]
    if len(listed) != len(receipt["raw_files"]):
        raise ValueError("RECORDING_RECEIPT_SHAPE_INVALID")
    try:
        present = {path.relative_to(root).as_posix() for path in _raw_files(root)}
    except OSError as error:
        raise ValueError("RECORDING_RECEIPT_FILE_MISSING") from error
    if present - listed:
        raise ValueError("RECORDING_RECEIPT_UNLISTED_FILE")
    documents = receipt["documents"]
    if documents["lease"] not in receipt["raw_files"] or documents["lease"]["path"] != LEASE_RELATIVE.as_posix():
        raise ValueError("RECORDING_RECEIPT_DOCUMENT_MISMATCH")
    _check_entry(root, documents["teacher_manifest"])
    if documents["teacher_manifest"]["path"] != TEACHER_MANIFEST_RELATIVE.as_posix():
        raise ValueError("RECORDING_RECEIPT_DOCUMENT_MISMATCH")
    _check_entry(root, documents["recorder_orchestration"])
    if documents["recorder_orchestration"]["path"] != ORCHESTRATION_RELATIVE.as_posix():
        raise ValueError("RECORDING_RECEIPT_DOCUMENT_MISMATCH")
    for name in EXTERNAL_DOCUMENTS:
        item = documents[name]
        if (type(item) is not dict or set(item) != {"sha256", "size"}
                or (external is not None and name in external and item["sha256"] != external[name])):
            raise ValueError("RECORDING_RECEIPT_DOCUMENT_MISMATCH")
    return {"sha256": hashlib.sha256(payload).hexdigest(), "files": len(listed), "bytes": total}


def _read_receipt_bytes(path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("RECORDING_RECEIPT_NOT_A_REGULAR_FILE")
        return stream.read()


def _check_entry(root: Path, item: dict) -> None:
    if (type(item) is not dict or type(item.get("path")) is not str or type(item.get("sha256")) is not str
            or type(item.get("size")) is not int):
        raise ValueError("RECORDING_RECEIPT_SHAPE_INVALID")
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("RECORDING_RECEIPT_SHAPE_INVALID")
    try:
        sha256, size = hash_regular_file(root / relative)
    except FileNotFoundError as error:
        raise ValueError("RECORDING_RECEIPT_FILE_MISSING") from error
    except OSError as error:
        raise ValueError("RECORDING_RECEIPT_FILE_UNREADABLE") from error
    if sha256 != item["sha256"] or size != item["size"]:
        raise ValueError("RECORDING_RECEIPT_FILE_CHANGED")
