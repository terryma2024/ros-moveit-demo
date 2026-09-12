#!/usr/bin/env python3
"""Inject one narrowly-scoped SO-101 parallel validation process fault."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import stat
import sys


TASK_EVIDENCE_ROOT = Path(
    "/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1"
)
TARGETS = {"worker-01", "worker-02", "worker-03", "broker"}
MANIFEST_FIELDS = {"schema_version", "batch_id", "processes"}
PROCESS_FIELDS = {"batch_id", "role", "pid", "pgid", "cmdline", "start_time"}
MAX_IDENTITY_DOCUMENT_BYTES = 1024 * 1024


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("MANIFEST_DUPLICATE_KEY")
        result[key] = value
    return result


def _no_symlink_path(path: Path, *, directory=False) -> Path:
    if not path.is_absolute():
        raise ValueError("EVIDENCE_ROOT_ABSOLUTE")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError as error:
            raise ValueError("EVIDENCE_PATH_MISSING") from error
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("EVIDENCE_PATH_SYMLINK")
    resolved = path.resolve(strict=True)
    if directory and not resolved.is_dir():
        raise ValueError("EVIDENCE_ROOT_DIRECTORY")
    return resolved


def _read_json(path: Path):
    path = _no_symlink_path(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_size > MAX_IDENTITY_DOCUMENT_BYTES):
                raise ValueError("MANIFEST_FILE_IDENTITY")
            value = json.load(stream, object_pairs_hook=_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("MANIFEST_INVALID") from error
    return value


def _manifest(root: Path):
    value = _read_json(root / "owned-processes.json")
    if (type(value) is not dict or set(value) != MANIFEST_FIELDS
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or not isinstance(value["batch_id"], str)
            or not value["batch_id"]
            or type(value["processes"]) is not list):
        raise ValueError("MANIFEST_INVALID")
    normalized = []
    for item in value["processes"]:
        if (type(item) is not dict or set(item) != PROCESS_FIELDS
                or item["batch_id"] != value["batch_id"]
                or item["role"] not in {"worker", "broker"}
                or type(item["pid"]) is not int or item["pid"] <= 0
                or type(item["pgid"]) is not int or item["pgid"] <= 0
                or type(item["start_time"]) is not int or item["start_time"] <= 0
                or type(item["cmdline"]) is not list or not item["cmdline"]
                or any(not isinstance(arg, str) or not arg for arg in item["cmdline"])):
            if type(item) is dict and item.get("batch_id") != value["batch_id"]:
                raise ValueError("BATCH_MISMATCH")
            raise ValueError("MANIFEST_INVALID")
        if item["pid"] != item["pgid"]:
            raise ValueError("UNOWNED_PGID")
        normalized.append(item | {"cmdline": tuple(item["cmdline"])})
    return value["batch_id"], normalized


def _worker_target(root: Path, item) -> str | None:
    command = item["cmdline"]
    try:
        marker = command.index("--internal-worker")
        if marker + 2 != len(command):
            return None
        spec_path = Path(command[marker + 1])
    except (ValueError, IndexError):
        return None
    try:
        expected_parent = root / "workers"
        spec_path = _no_symlink_path(spec_path)
        if spec_path.parent.parent != expected_parent or spec_path.name != "worker-spec.json":
            return None
        document = _read_json(spec_path)
        if (type(document) is not dict
                or document.get("schema_version") != 1
                or document.get("batch_id") != item["batch_id"]
                or type(document.get("resources")) is not dict):
            return None
        worker_id = document["resources"].get("worker_id")
        if worker_id != spec_path.parent.name or worker_id not in TARGETS - {"broker"}:
            return None
        return worker_id
    except (OSError, ValueError):
        return None


def _broker_target(root: Path, item) -> str | None:
    if item["role"] != "broker":
        return None
    required_mount = f"{root / 'ipc/broker'}:/runtime:rw"
    for argument in item["cmdline"]:
        if argument == required_mount:
            document = _read_json(root / "ipc/broker/broker-spec.json")
            if (type(document) is not dict
                    or document.get("schema_version") != 1
                    or document.get("kind") != "so101_parallel_broker_runtime"):
                raise ValueError("MANIFEST_INVALID")
            if document.get("batch_id") != item["batch_id"]:
                raise ValueError("BATCH_MISMATCH")
            return "broker"
    return None


def _target_identity(root: Path, item) -> str | None:
    if item["role"] == "worker":
        return _worker_target(root, item)
    return _broker_target(root, item)


def _proc_start_time(raw: str) -> int:
    """Return field 22 without splitting spaces inside the parenthesized comm."""
    closing_parenthesis = raw.rfind(")")
    if closing_parenthesis < 0:
        raise ValueError("PROC_STAT_INVALID")
    fields_after_comm = raw[closing_parenthesis + 1:].split()
    if len(fields_after_comm) < 20:
        raise ValueError("PROC_STAT_INVALID")
    return int(fields_after_comm[19])


def _read_proc(pid: int):
    process = Path("/proc") / str(pid)
    try:
        info = process.stat()
        process_stat = (process / "stat").read_text(encoding="ascii")
        command = tuple(
            part.decode("utf-8", errors="strict")
            for part in (process / "cmdline").read_bytes().split(b"\0")
            if part
        )
        return {
            "pid": pid,
            "pgid": os.getpgid(pid),
            "cmdline": command,
            "start_time": _proc_start_time(process_stat),
            "session_id": os.getsid(pid),
            "uid": info.st_uid,
        }
    except (OSError, UnicodeError, ValueError, IndexError):
        return None


def _validate_proc(expected, actual):
    if type(actual) is not dict:
        raise ValueError("PROCESS_ABSENT")
    required = {"pid", "pgid", "cmdline", "start_time", "session_id", "uid"}
    if set(actual) != required:
        raise ValueError("PROCESS_IDENTITY_INCOMPLETE")
    for field, label in (
        ("pid", "PID"),
        ("pgid", "PGID"),
        ("cmdline", "CMDLINE"),
        ("start_time", "START_TIME"),
    ):
        if actual[field] != expected[field]:
            raise ValueError(f"{label}_IDENTITY_DRIFT")
    if actual["uid"] != os.getuid():
        raise ValueError("UID_MISMATCH")
    if (expected["pid"] != expected["pgid"]
            or actual["session_id"] != expected["pgid"]):
        raise ValueError("UNOWNED_PGID")
    return tuple(
        actual[field] if field != "cmdline" else tuple(actual[field])
        for field in ("pid", "pgid", "cmdline", "start_time", "session_id", "uid")
    )


def inject_fault(argv, *, proc_reader=None, signal_group=None):
    """Validate an owned target twice before delivering exactly SIGTERM."""
    if (not isinstance(argv, (list, tuple)) or len(argv) != 3
            or any(not isinstance(value, str) or not value for value in argv)):
        raise ValueError("ARGUMENT_VECTOR_INVALID")
    evidence_root, target, requested_signal = argv
    raw_root = Path(evidence_root)
    root = _no_symlink_path(raw_root, directory=True)
    root_info = root.stat()
    root_identity = (root_info.st_dev, root_info.st_ino, root_info.st_uid)
    task_root = _no_symlink_path(TASK_EVIDENCE_ROOT, directory=True)
    if root != task_root and task_root not in root.parents:
        raise ValueError("EVIDENCE_ROOT_OUT_OF_TASK")
    if target not in TARGETS:
        raise ValueError("TARGET_NOT_ALLOWED")
    if requested_signal != "TERM":
        raise ValueError("SIGNAL_NOT_ALLOWED")
    batch_id, processes = _manifest(root)
    identified = [
        item for item in processes if _target_identity(root, item) == target
    ]
    if len(identified) != 1:
        # Preserve a more useful role mismatch when the exact worker spec binds
        # the target but the supervisor role was altered.
        role_candidates = [
            item for item in processes
            if target != "broker"
            and any(target in part for part in item["cmdline"])
        ]
        if len(role_candidates) == 1 and role_candidates[0]["role"] != "worker":
            raise ValueError("ROLE_MISMATCH")
        raise ValueError("TARGET_COUNT_INVALID")
    expected = identified[0]
    required_role = "broker" if target == "broker" else "worker"
    if expected["role"] != required_role:
        raise ValueError("ROLE_MISMATCH")
    if expected["batch_id"] != batch_id:
        raise ValueError("BATCH_MISMATCH")
    reader = _read_proc if proc_reader is None else proc_reader
    sender = os.killpg if signal_group is None else signal_group
    first = reader(expected["pid"])
    fingerprint = _validate_proc(expected, first)
    root_after = _no_symlink_path(root, directory=True)
    info_after = root_after.stat()
    if (info_after.st_dev, info_after.st_ino, info_after.st_uid) != root_identity:
        raise ValueError("EVIDENCE_ROOT_DRIFT")
    fresh_batch_id, fresh_processes = _manifest(root_after)
    if fresh_batch_id != batch_id or fresh_processes != processes:
        raise ValueError("MANIFEST_DRIFT")
    fresh_identified = [
        item for item in fresh_processes if _target_identity(root_after, item) == target
    ]
    if fresh_identified != [expected]:
        raise ValueError("MANIFEST_DRIFT")
    second = reader(expected["pid"])
    try:
        second_fingerprint = _validate_proc(expected, second)
    except ValueError as error:
        raise ValueError("IDENTITY_DRIFT") from error
    if second_fingerprint != fingerprint:
        raise ValueError("IDENTITY_DRIFT")
    sender(expected["pgid"], signal.SIGTERM)
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "target": target,
        "signal": "TERM",
        "pid": expected["pid"],
        "pgid": expected["pgid"],
        "cmdline": list(expected["cmdline"]),
        "start_time": expected["start_time"],
    }


def main(argv=None):
    """Command-line entry point."""
    try:
        result = inject_fault(sys.argv[1:] if argv is None else argv)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
