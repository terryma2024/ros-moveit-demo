"""Bounded, single-owner file evidence for one Head run.

``HeadRunEvidence.create`` takes ownership of a new directory. ``append`` and
``add_artifact`` only copy bounded work into memory and never wait for disk I/O.
The one writer thread assigns a global sequence and owns all event/artifact
writes. Call ``finish`` only after every event producer has stopped.

``fault_callback`` has the signature ``callback(fault: HeadRunEvidenceFault)``.
It is invoked once when the writer latches its first capacity or I/O fault.
Callbacks should return promptly; the writer never grants motion authority.
``add_artifact`` is the explicit raw-byte API. It creates a content-addressed
path under ``artifacts/`` and returns the exact reference to pass to append.
The same bytes/suffix are stored only once.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import queue
import re
import stat
import threading
import time
from typing import Any


DEFAULT_CAPACITIES = {
    "event_queue_capacity": 4096,
    "artifact_queue_capacity": 8,
    "max_event_bytes": 1024 * 1024,
    "max_artifact_bytes": 16 * 1024 * 1024,
    "max_queue_bytes": 64 * 1024 * 1024,
    "close_timeout_s": 5.0,
}
_FORBIDDEN_OS_COMPLETION_KEYS = {
    "os_return_code", "process_return_code", "actual_exit_code",
    "exit_code", "returncode", "return_code", "process_rc", "os_rc",
    "actual_return_code",
}


class HeadRunEvidenceFault(RuntimeError):
    """Sticky writer fault delivered to the optional local callback."""

    def __init__(self, reason: str, error: BaseException | None = None):
        super().__init__(reason)
        self.reason = reason
        self.error = error


def _encode_json(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                           separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f"HEAD_RUN_EVIDENCE_JSON_INVALID: {error}") from error


def _encode_bounded_json(value: Any, limit: int) -> bytes:
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                              separators=(",", ":"), sort_keys=True)
    output = bytearray()
    try:
        for fragment in encoder.iterencode(value):
            # JSONEncoder emits a whole string value as one fragment. Reject it
            # before UTF-8 allocation when even its character count exceeds the
            # remaining byte budget (UTF-8 bytes cannot be fewer than chars).
            if len(fragment) > limit - len(output):
                raise BufferError("HEAD_RUN_EVIDENCE_CAPACITY")
            encoded = fragment.encode("utf-8", "strict")
            if len(encoded) > limit - len(output):
                raise BufferError("HEAD_RUN_EVIDENCE_CAPACITY")
            output.extend(encoded)
        output.extend(b"\n")
    except BufferError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f"HEAD_RUN_EVIDENCE_JSON_INVALID: {error}") from error
    if len(output) > limit:
        raise BufferError("HEAD_RUN_EVIDENCE_CAPACITY")
    return bytes(output)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync_file(path: Path) -> float:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        return _fsync_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _fsync_descriptor(descriptor: int) -> float:
    started = time.monotonic_ns()
    os.fsync(descriptor)
    return (time.monotonic_ns() - started) / 1_000_000


def _fsync_directory(path: Path) -> float:
    started = time.monotonic_ns()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return (time.monotonic_ns() - started) / 1_000_000


def _assert_no_symlink_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError(f"HEAD_RUN_EVIDENCE_SYMLINK_PATH: {current}")


def _mkdir_durable(path: Path, mode: int = 0o700) -> None:
    _assert_no_symlink_components(path)
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    if not current.is_dir():
        raise NotADirectoryError(current)
    for directory in reversed(missing):
        directory.mkdir(mode=mode)
        _fsync_directory(directory.parent)


def _atomic_replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _write_completion(root: Path, data: bytes) -> float:
    target = root / "completion.json"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            return _fsync_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="strict"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _verify_readback(root: Path, event_count: int,
                     known_artifacts: Mapping[str, Mapping[str, Any]],
                     original_digests: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    _assert_no_symlink_components(root)
    artifacts_root = root / "artifacts"
    if artifacts_root.is_symlink() or not artifacts_root.is_dir():
        raise ValueError("HEAD_RUN_EVIDENCE_ARTIFACT_DIRECTORY_INVALID")
    events_path = root / "events.jsonl"
    event_digest = hashlib.sha256()
    event_size = 0
    line_count = 0
    with events_path.open("rb") as stream:
        for line_count, line in enumerate(stream, 1):
            if not line.endswith(b"\n"):
                raise ValueError("HEAD_RUN_EVIDENCE_TORN_EVENT_TAIL")
            event_digest.update(line)
            event_size += len(line)
            event = json.loads(line.decode("utf-8", "strict"),
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            if not isinstance(event, dict) or event.get("sequence") != line_count:
                raise ValueError("HEAD_RUN_EVIDENCE_SEQUENCE_MISMATCH")
            for ref in event.get("artifact_refs", []):
                if not isinstance(ref, dict) or ref != known_artifacts.get(ref.get("path")):
                    raise ValueError("HEAD_RUN_EVIDENCE_ARTIFACT_REFERENCE_UNKNOWN")
    if line_count != event_count:
        raise ValueError("HEAD_RUN_EVIDENCE_EVENT_COUNT_MISMATCH")
    event_expected = original_digests["events.jsonl"]
    if event_size != event_expected["size"] or event_digest.hexdigest() != event_expected["sha256"]:
        raise ValueError("HEAD_RUN_EVIDENCE_EVENT_READBACK_MISMATCH")
    for filename in ("manifest.json", "completion.json"):
        content = (root / filename).read_bytes()
        expected = original_digests[filename]
        if len(content) != expected["size"] or hashlib.sha256(content).hexdigest() != expected["sha256"]:
            raise ValueError(f"HEAD_RUN_EVIDENCE_{filename.upper().replace('.', '_')}_READBACK_MISMATCH")
        json.loads(content.decode("utf-8", "strict"),
                   parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    for path_key, ref in known_artifacts.items():
        relative = PurePosixPath(path_key)
        if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "artifacts" or ".." in relative.parts:
            raise ValueError("HEAD_RUN_EVIDENCE_ARTIFACT_PATH_INVALID")
        path = root / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size != ref["size"] or _sha256(path) != ref["sha256"]:
            raise ValueError("HEAD_RUN_EVIDENCE_ARTIFACT_READBACK_MISMATCH")
    actual_artifacts = set()
    for path in artifacts_root.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("HEAD_RUN_EVIDENCE_SYMLINK_IN_RUN_ROOT")
        actual_artifacts.add(path.relative_to(root).as_posix())
    if actual_artifacts != set(known_artifacts):
        raise ValueError("HEAD_RUN_EVIDENCE_ARTIFACT_INVENTORY_MISMATCH")
    paths = [root / "manifest.json", events_path,
             *(root / PurePosixPath(key) for key in sorted(known_artifacts)),
             root / "completion.json"]
    inventory = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("HEAD_RUN_EVIDENCE_FILE_MISSING_OR_SYMLINK")
        inventory.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": _sha256(path)})
    return inventory


class HeadRunEvidence:
    """Asynchronous bounded JSONL writer and atomic completion sealer."""

    @classmethod
    def create(cls, run_root: str | os.PathLike[str], manifest: Mapping[str, Any],
               capacities: Mapping[str, Any] | None = None, *, fault_callback=None) -> "HeadRunEvidence":
        if not isinstance(manifest, Mapping):
            raise TypeError("manifest must be a mapping")
        root = Path(run_root).absolute()
        if root.exists() or root.is_symlink():
            raise FileExistsError(f"run root must be new: {root}")
        supplied = dict(capacities or {})
        unknown = set(supplied) - set(DEFAULT_CAPACITIES)
        if unknown:
            raise ValueError(f"unknown capacities: {sorted(unknown)}")
        limits = {**DEFAULT_CAPACITIES, **supplied}
        for name in ("event_queue_capacity", "artifact_queue_capacity", "max_event_bytes",
                     "max_artifact_bytes", "max_queue_bytes"):
            if isinstance(limits[name], bool) or not isinstance(limits[name], int) or limits[name] < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(limits["close_timeout_s"], (int, float)) or limits["close_timeout_s"] <= 0:
            raise ValueError("close_timeout_s must be positive")
        manifest_value = dict(manifest)
        version = manifest_value.setdefault("file_protocol_version", 1)
        if version != 1:
            raise ValueError("unsupported file_protocol_version")
        manifest_value["writer_capacities"] = limits.copy()
        encoded_manifest = _encode_json(manifest_value)

        _mkdir_durable(root.parent)
        root.mkdir(mode=0o700)
        try:
            initial_fsync_ms = _fsync_directory(root.parent)
            (root / "artifacts").mkdir(mode=0o700)
            initial_fsync_ms += _fsync_directory(root)
            descriptor = os.open(root / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(encoded_manifest)
                    stream.flush()
                    initial_fsync_ms += _fsync_descriptor(descriptor)
            finally:
                os.close(descriptor)
            initial_fsync_ms += _fsync_directory(root)
            return cls(root, limits, fault_callback=fault_callback,
                       initial_fsync_ms=initial_fsync_ms,
                       manifest_digest={"size": len(encoded_manifest),
                                        "sha256": hashlib.sha256(encoded_manifest).hexdigest()})
        except BaseException:
            # Keep the incomplete owned directory for forensic inspection; never
            # manufacture completion or silently reuse it.
            raise

    def __init__(self, root: Path, limits: Mapping[str, Any], *, fault_callback=None,
                 initial_fsync_ms: float = 0.0,
                 manifest_digest: Mapping[str, Any] | None = None):
        if fault_callback is not None and not callable(fault_callback):
            raise TypeError("fault_callback must be callable")
        self.root = root
        self._limits = dict(limits)
        self._fault_callback = fault_callback
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[str, Any] | None] = queue.Queue(
            maxsize=self._limits["event_queue_capacity"] + self._limits["artifact_queue_capacity"])
        self._closed = False
        self._failed = False
        self._fault_notified = False
        self._fault_callback_error: str | None = None
        self._seal_result: dict[str, Any] | None = None
        self._sequence = 0
        self._pending_events = 0
        self._pending_artifacts = 0
        self._pending_bytes = 0
        self._known_artifacts: dict[str, dict[str, Any]] = {}
        self._event_digest = hashlib.sha256()
        self._event_size = 0
        self._original_digests = {
            "manifest.json": dict(manifest_digest or {"size": 0, "sha256": hashlib.sha256(b"").hexdigest()}),
            "events.jsonl": {"size": 0, "sha256": hashlib.sha256(b"").hexdigest()},
        }
        self._event_count = 0
        self._artifact_count = 0
        self._write_ms_total = 0.0
        self._write_ms_max = 0.0
        self._enqueue_ms_total = 0.0
        self._enqueue_ms_max = 0.0
        self._fsync_ms_total = initial_fsync_ms
        self._fsync_ms_max = initial_fsync_ms
        self._event_high_water = 0
        self._artifact_high_water = 0
        self._byte_high_water = 0
        self._drops = 0
        self._events = (root / "events.jsonl").open("xb", buffering=0)
        self._thread = threading.Thread(target=self._run, name="head-run-evidence-writer", daemon=True)
        try:
            self._thread.start()
        except BaseException:
            self._events.close()
            raise

    def _stats_locked(self) -> dict[str, Any]:
        return {
            "event_capacity": self._limits["event_queue_capacity"],
            "artifact_capacity": self._limits["artifact_queue_capacity"],
            "max_event_bytes": self._limits["max_event_bytes"],
            "max_artifact_bytes": self._limits["max_artifact_bytes"],
            "max_queue_bytes": self._limits["max_queue_bytes"],
            "event_high_water": self._event_high_water,
            "artifact_high_water": self._artifact_high_water,
            "queue_bytes_high_water": self._byte_high_water,
            "event_count": self._event_count,
            "artifact_count": self._artifact_count,
            "drop_count": self._drops,
            "fault_count": int(self._failed),
            "write_ms_total": self._write_ms_total,
            "write_ms_max": self._write_ms_max,
            "enqueue_ms_total": self._enqueue_ms_total,
            "enqueue_ms_max": self._enqueue_ms_max,
            "fsync_ms_total": self._fsync_ms_total,
            "fsync_ms_max": self._fsync_ms_max,
            "fault_callback_error": self._fault_callback_error,
        }

    def _latch_fault(self, reason: str, error: BaseException | None = None) -> None:
        callback = None
        with self._lock:
            if not self._failed:
                self._failed = True
                if reason in {"HEAD_RUN_EVIDENCE_OVERFLOW", "HEAD_RUN_EVIDENCE_CAPACITY"}:
                    self._drops += 1
            if not self._fault_notified:
                self._fault_notified = True
                callback = self._fault_callback
        if callback is not None:
            try:
                callback(HeadRunEvidenceFault(reason, error))
            except BaseException as callback_error:
                with self._lock:
                    self._fault_callback_error = f"{type(callback_error).__name__}: {callback_error}"

    @staticmethod
    def _clock(value: int | None, field: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field} must be an integer nanosecond timestamp or None")
        return value

    def append(self, kind: str, record: Any, *, source_stamp_ns: int | None,
               observed_mono_ns: int | None, occurrence_mono_ns: int | None,
               artifact_refs=()) -> int:
        if not isinstance(kind, str) or not kind:
            raise ValueError("kind must be a non-empty string")
        source_stamp_ns = self._clock(source_stamp_ns, "source_stamp_ns")
        observed_mono_ns = self._clock(observed_mono_ns, "observed_mono_ns")
        occurrence_mono_ns = self._clock(occurrence_mono_ns, "occurrence_mono_ns")
        if not isinstance(artifact_refs, (tuple, list)) or len(artifact_refs) > 64:
            raise ValueError("artifact_refs must be a tuple/list of at most 64 references")
        refs = tuple(dict(ref) for ref in artifact_refs)
        if len(kind) > self._limits["max_event_bytes"]:
            self._latch_fault("HEAD_RUN_EVIDENCE_CAPACITY")
            raise BufferError("HEAD_RUN_EVIDENCE_CAPACITY")
        started_ns = time.monotonic_ns()
        with self._lock:
            if self._closed:
                raise PermissionError("HEAD_RUN_EVIDENCE_CLOSED")
            if self._failed:
                raise PermissionError("HEAD_RUN_EVIDENCE_FAULTED")
            for ref in refs:
                if not isinstance(ref, dict) or ref != self._known_artifacts.get(ref.get("path")):
                    raise ValueError("artifact_refs must be returned by add_artifact for this run")
            sequence = self._sequence + 1
            event = {"sequence": sequence, "kind": kind, "record": record,
                     "source_stamp_ns": source_stamp_ns,
                     "observed_mono_ns": observed_mono_ns,
                     "occurrence_mono_ns": occurrence_mono_ns,
                     "artifact_refs": list(refs)}
            reason = None
            invalid_record_error = None
            try:
                encoded = _encode_bounded_json(event, self._limits["max_event_bytes"])
            except BufferError:
                reason = "HEAD_RUN_EVIDENCE_CAPACITY"
                encoded = b""
            except (TypeError, ValueError, UnicodeError) as error:
                reason = "HEAD_RUN_EVIDENCE_INVALID_RECORD"
                invalid_record_error = error
                encoded = b""
            if reason:
                pass
            elif len(encoded) > self._limits["max_event_bytes"]:
                reason = "HEAD_RUN_EVIDENCE_CAPACITY"
            elif self._pending_events >= self._limits["event_queue_capacity"] or \
                    self._pending_bytes + len(encoded) > self._limits["max_queue_bytes"]:
                reason = "HEAD_RUN_EVIDENCE_OVERFLOW"
            else:
                try:
                    self._queue.put_nowait(("event", encoded))
                except queue.Full:
                    reason = "HEAD_RUN_EVIDENCE_OVERFLOW"
                else:
                    self._sequence = sequence
                    self._pending_events += 1
                    self._pending_bytes += len(encoded)
                    self._event_high_water = max(self._event_high_water, self._pending_events)
                    self._byte_high_water = max(self._byte_high_water, self._pending_bytes)
        if reason:
            self._latch_fault(reason)
            if invalid_record_error is not None:
                raise ValueError(f"HEAD_RUN_EVIDENCE_JSON_INVALID: {invalid_record_error}") from invalid_record_error
            raise BufferError(reason)
        elapsed = (time.monotonic_ns() - started_ns) / 1_000_000
        with self._lock:
            self._enqueue_ms_total += elapsed
            self._enqueue_ms_max = max(self._enqueue_ms_max, elapsed)
        return sequence

    def add_artifact(self, data: bytes | bytearray | memoryview, *, media_type: str, suffix: str) -> dict[str, Any]:
        if not isinstance(media_type, str) or not media_type or "\n" in media_type:
            raise ValueError("media_type must be non-empty text")
        if not isinstance(suffix, str) or not re.fullmatch(r"[A-Za-z0-9]{1,12}", suffix):
            raise ValueError("suffix must be 1-12 alphanumeric characters")
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("artifact data must be bytes-like")
        raw_size = data.nbytes if isinstance(data, memoryview) else len(data)
        if raw_size <= 0:
            raise ValueError("artifact data must not be empty")
        if raw_size > self._limits["max_artifact_bytes"]:
            self._latch_fault("HEAD_RUN_EVIDENCE_CAPACITY")
            raise BufferError("HEAD_RUN_EVIDENCE_CAPACITY")
        raw = bytes(data)
        if len(raw) != raw_size:
            self._latch_fault("HEAD_RUN_EVIDENCE_CAPACITY")
            raise BufferError("HEAD_RUN_EVIDENCE_CAPACITY")
        digest = hashlib.sha256(raw).hexdigest()
        started_ns = time.monotonic_ns()
        ref = {"path": f"artifacts/{digest}.{suffix.lower()}", "size": len(raw),
               "sha256": digest, "media_type": media_type}
        encoded_size = len(raw)
        with self._lock:
            if self._closed:
                raise PermissionError("HEAD_RUN_EVIDENCE_CLOSED")
            if self._failed:
                raise PermissionError("HEAD_RUN_EVIDENCE_FAULTED")
            existing = self._known_artifacts.get(ref["path"])
            if existing is not None:
                if existing["sha256"] != digest or existing["size"] != len(raw):
                    raise FileExistsError("content-addressed artifact collision")
                return dict(existing)
            reason = None
            if self._pending_artifacts >= self._limits["artifact_queue_capacity"] or \
                    self._pending_bytes + encoded_size > self._limits["max_queue_bytes"]:
                reason = "HEAD_RUN_EVIDENCE_OVERFLOW"
            else:
                try:
                    self._queue.put_nowait(("artifact", (ref, raw)))
                except queue.Full:
                    reason = "HEAD_RUN_EVIDENCE_OVERFLOW"
                else:
                    self._known_artifacts[ref["path"]] = dict(ref)
                    self._pending_artifacts += 1
                    self._pending_bytes += encoded_size
                    self._artifact_high_water = max(self._artifact_high_water, self._pending_artifacts)
                    self._byte_high_water = max(self._byte_high_water, self._pending_bytes)
        if reason:
            self._latch_fault(reason)
            raise BufferError(reason)
        elapsed = (time.monotonic_ns() - started_ns) / 1_000_000
        with self._lock:
            self._enqueue_ms_total += elapsed
            self._enqueue_ms_max = max(self._enqueue_ms_max, elapsed)
        return dict(ref)

    def _write_event(self, encoded: bytes) -> None:
        view = memoryview(encoded)
        offset = 0
        while offset < len(view):
            offset += self._events.write(view[offset:])
        self._event_digest.update(encoded)
        self._event_size += len(encoded)
        with self._lock:
            self._event_count += 1

    def _write_artifact(self, item: tuple[dict[str, Any], bytes]) -> None:
        ref, raw = item
        relative = PurePosixPath(ref["path"])
        if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "artifacts" or ".." in relative.parts:
            raise ValueError("artifact path escaped run root")
        _assert_no_symlink_components(self.root)
        artifacts_root = self.root / "artifacts"
        if artifacts_root.is_symlink() or not artifacts_root.is_dir():
            raise ValueError("HEAD_RUN_EVIDENCE_ARTIFACT_DIRECTORY_INVALID")
        path = self.root / relative
        if path.is_symlink() or path.exists():
            raise FileExistsError(f"artifact destination already exists: {relative}")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                offset += os.write(descriptor, view[offset:])
            elapsed = _fsync_descriptor(descriptor)
            with self._lock:
                self._fsync_ms_total += elapsed
                self._fsync_ms_max = max(self._fsync_ms_max, elapsed)
                self._artifact_count += 1
        finally:
            os.close(descriptor)
        elapsed = _fsync_directory(artifacts_root)
        with self._lock:
            self._fsync_ms_total += elapsed
            self._fsync_ms_max = max(self._fsync_ms_max, elapsed)

    def _run(self) -> None:
        try:
            while True:
                try:
                    task = self._queue.get(timeout=0.05)
                except queue.Empty:
                    with self._lock:
                        cancelled = self._closed and self._failed
                    if cancelled:
                        self._drain_queue()
                        break
                    continue
                if task is None:
                    self._queue.task_done()
                    break
                kind, item = task
                if kind == "finish":
                    try:
                        with self._lock:
                            failed = self._failed
                        if not failed:
                            self._seal_result = self._seal(item)
                    finally:
                        self._queue.task_done()
                    break
                started = time.monotonic_ns()
                try:
                    if kind == "event":
                        self._write_event(item)
                    elif kind == "artifact":
                        self._write_artifact(item)
                    else:
                        raise RuntimeError("unknown writer task")
                finally:
                    elapsed = (time.monotonic_ns() - started) / 1_000_000
                    with self._lock:
                        self._write_ms_total += elapsed
                        self._write_ms_max = max(self._write_ms_max, elapsed)
                        if kind == "event":
                            self._pending_events -= 1
                            self._pending_bytes -= len(item)
                        elif kind == "artifact":
                            self._pending_artifacts -= 1
                            self._pending_bytes -= len(item[1])
                    self._queue.task_done()
        except BaseException as error:
            self._latch_fault("HEAD_RUN_EVIDENCE_IO_FAILED", error)
            self._drain_queue()
        finally:
            try:
                if not self._events.closed:
                    self._events.flush()
                    self._events.close()
            except BaseException as error:
                self._latch_fault("HEAD_RUN_EVIDENCE_IO_FAILED", error)

    def _drain_queue(self) -> None:
        while True:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                return
            if task is not None:
                kind, item = task
                with self._lock:
                    if kind == "event":
                        self._pending_events -= 1
                        self._pending_bytes -= len(item)
                        self._drops += 1
                    elif kind == "artifact":
                        self._pending_artifacts -= 1
                        self._pending_bytes -= len(item[1])
                        self._drops += 1
            self._queue.task_done()

    def _close_handles_if_worker_stopped(self) -> None:
        if not self._thread.is_alive() and not self._events.closed:
            try:
                self._events.close()
            except OSError as error:
                self._latch_fault("HEAD_RUN_EVIDENCE_IO_FAILED", error)

    def _seal(self, completion: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(completion, Mapping):
            raise TypeError("completion must be a mapping")
        if set(completion) & _FORBIDDEN_OS_COMPLETION_KEYS:
            raise ValueError("completion must not claim the process OS return code")
        completion_bytes = _encode_json(dict(completion))
        self._events.flush()
        elapsed = _fsync_descriptor(self._events.fileno())
        with self._lock:
            if self._failed:
                raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED_DURING_SEAL")
            self._fsync_ms_total += elapsed
            self._fsync_ms_max = max(self._fsync_ms_max, elapsed)
        elapsed = _write_completion(self.root, completion_bytes)
        with self._lock:
            if self._failed:
                raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED_DURING_SEAL")
            self._fsync_ms_total += elapsed
            self._fsync_ms_max = max(self._fsync_ms_max, elapsed)
            event_count = self._event_count
            known = {key: dict(value) for key, value in self._known_artifacts.items()}
            stats = self._stats_locked()
            original_digests = dict(self._original_digests)
            original_digests["events.jsonl"] = {
                "size": self._event_size,
                "sha256": self._event_digest.hexdigest(),
            }
            original_digests["completion.json"] = {
                "size": len(completion_bytes),
                "sha256": hashlib.sha256(completion_bytes).hexdigest(),
            }
        inventory = _verify_readback(self.root, event_count, known, original_digests)
        with self._lock:
            if self._failed:
                raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED_DURING_SEAL")
        seal_value = {"file_protocol_version": 1, "event_count": event_count,
                      "artifact_count": len(known), "counters": stats, "files": inventory}
        seal_bytes = _encode_json(seal_value)
        temporary = self.root / ".seal.json.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(seal_bytes)
                stream.flush()
                elapsed = _fsync_descriptor(descriptor)
                with self._lock:
                    self._fsync_ms_total += elapsed
                    self._fsync_ms_max = max(self._fsync_ms_max, elapsed)
        finally:
            os.close(descriptor)
        with self._lock:
            if self._failed:
                raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED_DURING_SEAL")
        _atomic_replace(temporary, self.root / "seal.json")
        elapsed = _fsync_directory(self.root)
        with self._lock:
            if self._failed:
                raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED_DURING_SEAL")
            self._fsync_ms_total += elapsed
            self._fsync_ms_max = max(self._fsync_ms_max, elapsed)
        return seal_value

    def finish(self, completion: Mapping[str, Any], *, timeout_s: float | None = None) -> dict[str, Any]:
        timeout = self._limits["close_timeout_s"] if timeout_s is None else timeout_s
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or \
                not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout_s must be finite and positive")
        deadline = time.monotonic() + timeout
        with self._lock:
            if self._closed:
                raise PermissionError("HEAD_RUN_EVIDENCE_ALREADY_FINISHED")
            self._closed = True
        worker_started = self._thread.ident is not None
        if not worker_started:
            self._latch_fault("HEAD_RUN_EVIDENCE_WORKER_NOT_STARTED")
            self._close_handles_if_worker_stopped()
            raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED; no seal written")
        if not self._thread.is_alive():
            with self._lock:
                failed = self._failed
            if not failed:
                self._latch_fault("HEAD_RUN_EVIDENCE_WORKER_EXITED")
            self._close_handles_if_worker_stopped()
            raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED; no seal written")
        try:
            self._queue.put(("finish", dict(completion)), timeout=max(0.0, deadline - time.monotonic()))
        except queue.Full as error:
            self._latch_fault("HEAD_RUN_EVIDENCE_CLOSE_TIMEOUT", error)
            raise RuntimeError("HEAD_RUN_EVIDENCE_CLOSE_TIMEOUT") from error
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if self._thread.is_alive():
            self._latch_fault("HEAD_RUN_EVIDENCE_CLOSE_TIMEOUT")
            raise RuntimeError("HEAD_RUN_EVIDENCE_CLOSE_TIMEOUT")
        with self._lock:
            failed = self._failed
        if failed or self._seal_result is None:
            self._close_handles_if_worker_stopped()
            raise RuntimeError("HEAD_RUN_EVIDENCE_FAULTED; no seal written")
        return self._seal_result
