"""Strict Unix-socket transports for control and stateless inference."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Callable, Mapping


class IpcError(RuntimeError):
    """A frame, identity, authentication, or transport contract failed."""


# Linux sun_path capacity in bytes, including the terminating NUL. The kernel sees the
# sockaddr string, not the durable canonical path, so the dirfd transport below keeps
# the kernel address short while manifests/audits keep the absolute durable path.
UNIX_SOCKADDR_CAPACITY_BYTES = 108
_PROC_FD_ROOT = Path("/proc/self/fd")
_TRANSPORT_PREFIX = "/proc/self/fd/"
_MAX_FD_DIGITS = 10


def require_proc_fd_transport(proc_root: Path | None = None) -> None:
    """Fail closed when the Linux dirfd transport is unavailable."""

    target = _PROC_FD_ROOT if proc_root is None else Path(proc_root)
    try:
        metadata = target.stat()
    except OSError as error:
        raise IpcError("UNIX_TRANSPORT_UNAVAILABLE") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise IpcError("UNIX_TRANSPORT_UNAVAILABLE")


def require_transport_basename(path: object) -> None:
    """Preflight without touching the parent: the basename must fit the kernel budget."""

    require_proc_fd_transport()
    name = Path(path).name
    encoded = os.fsencode(name)
    if not encoded or name in {".", ".."} or b"\x00" in encoded:
        raise IpcError(f"UNIX_SOCKET_BASENAME_INVALID: {path}")
    # Conservative reservation: unknown fd digits, the separator and the terminating NUL.
    reserved = len(_TRANSPORT_PREFIX.encode("ascii")) + _MAX_FD_DIGITS + 1 + 1
    if reserved + len(encoded) > UNIX_SOCKADDR_CAPACITY_BYTES:
        raise IpcError(f"UNIX_SOCKET_PATH_TOO_LONG: {path}")


def transport_address(path: object, parent_fd: int) -> str:
    """Exact short kernel address; rechecked once the owned parent descriptor exists."""

    if type(parent_fd) is not int or parent_fd < 0:
        raise IpcError("UNIX_TRANSPORT_DESCRIPTOR")
    address = f"{_TRANSPORT_PREFIX}{parent_fd}/{Path(path).name}"
    if len(os.fsencode(address)) + 1 > UNIX_SOCKADDR_CAPACITY_BYTES:
        raise IpcError(f"UNIX_SOCKET_PATH_TOO_LONG: {path}")
    return address


_REQUEST_FIELDS = {
    "schema_version",
    "kind",
    "coordinator_epoch",
    "worker_id",
    "worker_generation",
    "lease",
    "request_id",
    "idempotency_key",
    "token",
    "payload",
}
_BROKER_REQUEST_FIELDS = {
    "schema_version",
    "kind",
    "request_id",
    "idempotency_key",
    "payload",
}
_BROKER_COMPATIBILITY_FIELDS = {
    "coordinator_epoch",
    "worker_id",
    "worker_generation",
    "lease",
    "token",
}
_LEASE_FIELDS = {
    "batch_id",
    "coordinator_epoch",
    "worker_id",
    "worker_generation",
    "point_id",
    "attempt_id",
    "lease_generation",
}
_RESPONSE_FIELDS = {
    "schema_version",
    "kind",
    "request_id",
    "idempotency_key",
    "ok",
    "payload",
    "error",
}
_KINDS = {"coordinator_call", "broker_call", "worker_call"}
_DEFAULT_MAX_FRAME = 8 * 1024 * 1024


@dataclass
class _ReplayEntry:
    digest: str
    completed: threading.Event
    state: str = "PENDING"
    payload: bytes | None = None
    error: str | None = None


class _BrokerMetrics:
    """Bounded, payload-free timing and concurrency evidence for one Broker."""

    def __init__(self):
        self._lock = threading.RLock()
        self._events = []
        self._next_connection = 0
        self._pending_connections = 0
        self._pending_peak = 0
        self._queue_depth = {}
        self._queue_peak = 0
        self._active = {}
        self._active_peak = {}
        self._request_state = {}
        self._logical_inference_keys = set()
        self._transport_errors = {}
        self._connection_by_inference = {}
        self._phase = {}

    def _record(self, event, *, connection_id=None, message=None, error=None):
        value = {"event": event, "monotonic_s": time.monotonic()}
        if connection_id is not None:
            value["connection_id"] = connection_id
        if type(message) is dict:
            for name in ("request_id", "idempotency_key"):
                if isinstance(message.get(name), str):
                    value[name] = message[name]
        if error is not None:
            value["error"] = str(error)
        if len(self._events) < 10000:
            self._events.append(value)

    def connection_accepted(self):
        with self._lock:
            self._next_connection += 1
            connection_id = self._next_connection
            self._pending_connections += 1
            self._pending_peak = max(
                self._pending_peak, self._pending_connections
            )
            self._record("accepted", connection_id=connection_id)
            self._phase[connection_id] = ("accepted", time.monotonic())
            return connection_id

    def connection_event(self, connection_id, event, message=None, error=None):
        with self._lock:
            self._phase[connection_id] = (event, time.monotonic())
            if event == "received" and type(message) is dict:
                inference = message.get("payload", {}).get("request", {})
                if type(inference) is dict and isinstance(
                    inference.get("request_id"), str
                ):
                    self._connection_by_inference[inference["request_id"]] = (
                        connection_id
                    )
            self._record(
                event,
                connection_id=connection_id,
                message=message,
                error=error,
            )
            if error is not None:
                key = str(error)
                self._transport_errors[key] = self._transport_errors.get(key, 0) + 1

    def connection_closed(self, connection_id):
        with self._lock:
            self._pending_connections -= 1
            self._record("closed", connection_id=connection_id)

    def validated(self, message):
        with self._lock:
            connection_id = self._connection_for_message(message)
            self._phase[connection_id] = ("validated", time.monotonic())
            self._record("validated", connection_id=connection_id, message=message)
            if message.get("payload", {}).get("operation") == "infer":
                inference = message["payload"].get("request", {})
                inference_request_id = (
                    inference.get("request_id")
                    if isinstance(inference.get("request_id"), str)
                    else message["request_id"]
                )
                self._logical_inference_keys.add(inference_request_id)

    def _connection_for_message(self, message):
        payload = message.get("payload", {}) if type(message) is dict else {}
        inference = payload.get("request", {}) if type(payload) is dict else {}
        if type(inference) is dict:
            return self._connection_by_inference.get(inference.get("request_id"))
        return None

    def _request_connection(self, request):
        return self._connection_by_inference.get(request.request_id)

    def queued(self, request):
        with self._lock:
            key = request.request_id
            if key in self._request_state:
                return
            self._request_state[key] = (request.model_id, "QUEUED")
            self._queue_depth[request.model_id] = (
                self._queue_depth.get(request.model_id, 0) + 1
            )
            self._queue_peak = max(
                self._queue_peak, sum(self._queue_depth.values())
            )
            connection_id = self._request_connection(request)
            self._phase[connection_id] = ("queued", time.monotonic())
            self._record(
                "queued", connection_id=connection_id,
                message={"request_id": key},
            )

    def started(self, request, executor_index):
        with self._lock:
            key = request.request_id
            prior = self._request_state.get(key)
            if prior == (request.model_id, "QUEUED"):
                self._queue_depth[request.model_id] -= 1
            self._request_state[key] = (request.model_id, "RUNNING")
            self._active[request.model_id] = self._active.get(request.model_id, 0) + 1
            self._active_peak[request.model_id] = max(
                self._active_peak.get(request.model_id, 0),
                self._active[request.model_id],
            )
            self._record(
                "model_started",
                connection_id=self._request_connection(request),
                message={"request_id": key},
            )
            self._events[-1]["executor_index"] = executor_index

    def model_completed(self, request, outcome):
        with self._lock:
            connection_id = self._request_connection(request)
            self._phase[connection_id] = ("model_completed", time.monotonic())
            self._record(
                "model_completed", connection_id=connection_id,
                message={"request_id": request.request_id},
            )
            self._events[-1]["outcome"] = outcome

    def handler_timeout(self, connection_id, message):
        with self._lock:
            phase, phase_started = self._phase.get(
                connection_id, ("unknown", time.monotonic())
            )
            self._record(
                "handler_timeout", connection_id=connection_id, message=message,
                error="HANDLER_DEADLINE_EXCEEDED",
            )
            self._events[-1].update(
                timeout_phase=phase,
                phase_started_monotonic_s=phase_started,
            )

    def completed(self, request):
        with self._lock:
            key = request.request_id
            prior = self._request_state.pop(key, None)
            if prior == (request.model_id, "QUEUED"):
                self._queue_depth[request.model_id] -= 1
            elif prior == (request.model_id, "RUNNING"):
                self._active[request.model_id] -= 1
            if prior is not None:
                self._record("completed", message={"request_id": key})

    def snapshot(self):
        with self._lock:
            return json.loads(canonical_json({
                "pending_rpc_peak": self._pending_peak,
                "queue_depth_peak": self._queue_peak,
                "model_active_peak": self._active_peak,
                "logical_inference_count": len(self._logical_inference_keys),
                "logical_inference_keys": sorted(self._logical_inference_keys),
                "transport_errors": self._transport_errors,
                "events": self._events,
            }))


def _dispatch_idempotently(
    replays, lock, key, digest, message, mutation, *, observer=None
):
    with lock:
        entry = replays.get(key)
        if entry is None:
            entry = _ReplayEntry(digest=digest, completed=threading.Event())
            replays[key] = entry
            owns_mutation = True
        else:
            if entry.digest != digest:
                raise IpcError("IDEMPOTENCY_CONFLICT")
            owns_mutation = False

    if observer is not None:
        observer(message, "OWNER" if owns_mutation else "REPLAY")

    if owns_mutation:
        try:
            payload = canonical_json(mutation(message))
        except BaseException as error:
            normalized = (
                str(error)
                if isinstance(error, IpcError)
                else f"HANDLER_REJECTED: {error}"
            )
            with lock:
                entry.error = normalized
                entry.state = "FAILED"
                entry.completed.set()
            raise
        with lock:
            entry.payload = payload
            entry.state = "DONE"
            entry.completed.set()
    else:
        entry.completed.wait()

    with lock:
        if entry.state == "FAILED":
            raise IpcError(entry.error or "HANDLER_REJECTED")
        if entry.state != "DONE" or entry.payload is None:
            raise IpcError("IDEMPOTENCY_STATE")
        return _decode_payload(entry.payload)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IpcError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise IpcError("JSON_NOT_CANONICAL") from error


def _decode_payload(payload: bytes) -> dict:
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(IpcError("JSON_CONSTANT")),
        )
    except IpcError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IpcError("INVALID_JSON") from error
    if type(value) is not dict:
        raise IpcError("JSON_OBJECT_REQUIRED")
    if canonical_json(value) != payload:
        raise IpcError("NON_CANONICAL_JSON")
    return value


def encode_frame(value: Mapping[str, object], *, max_frame_bytes: int = _DEFAULT_MAX_FRAME) -> bytes:
    if type(max_frame_bytes) is not int or max_frame_bytes <= 0:
        raise IpcError("FRAME_LIMIT")
    payload = canonical_json(value)
    if not payload or len(payload) > max_frame_bytes:
        raise IpcError("FRAME_SIZE")
    return struct.pack(">I", len(payload)) + payload


def decode_frame(frame: bytes, *, max_frame_bytes: int = _DEFAULT_MAX_FRAME) -> dict:
    if not isinstance(frame, bytes) or len(frame) < 4:
        raise IpcError("INCOMPLETE_PREFIX")
    size = struct.unpack(">I", frame[:4])[0]
    if size == 0 or size > max_frame_bytes:
        raise IpcError("FRAME_SIZE")
    if len(frame) != size + 4:
        raise IpcError("TRUNCATED_OR_OVERLONG_FRAME")
    return _decode_payload(frame[4:])


def _recv_exact(connection: socket.socket, size: int, deadline: float) -> bytes:
    result = bytearray()
    while len(result) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise IpcError("DEADLINE_EXCEEDED")
        connection.settimeout(remaining)
        try:
            part = connection.recv(size - len(result))
        except (TimeoutError, socket.timeout) as error:
            raise IpcError("DEADLINE_EXCEEDED") from error
        if not part:
            raise IpcError("TRUNCATED_FRAME")
        result.extend(part)
    return bytes(result)


def receive_frame(
    connection: socket.socket,
    *,
    deadline_s: float,
    max_frame_bytes: int = _DEFAULT_MAX_FRAME,
) -> dict:
    if isinstance(deadline_s, bool) or not isinstance(deadline_s, (int, float)) or deadline_s <= 0:
        raise IpcError("DEADLINE")
    deadline = time.monotonic() + float(deadline_s)
    prefix = _recv_exact(connection, 4, deadline)
    size = struct.unpack(">I", prefix)[0]
    if size == 0 or size > max_frame_bytes:
        raise IpcError("FRAME_SIZE")
    payload = _recv_exact(connection, size, deadline)
    try:
        extra = connection.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
    except BlockingIOError:
        extra = b""
    if extra:
        raise IpcError("OVERLONG_FRAME")
    return _decode_payload(payload)


def _positive_int(name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise IpcError(f"{name}_TYPE")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or not all(
        character.isalnum() or character in "_-" for character in value
    ):
        raise IpcError(f"{name}_TYPE")
    return value


class WorkerTokenAuthority:
    """Coordinator-owned Worker tokens, active leases, and replay responses."""

    def __init__(
        self, evidence_root: Path, *, coordinator_epoch: int,
        ipc_root: Path | None = None,
    ):
        self.root = Path(evidence_root)
        self.coordinator_epoch = _positive_int("EPOCH", coordinator_epoch)
        self.ipc_root = self.root / "ipc" if ipc_root is None else Path(ipc_root)
        if (
            not self.ipc_root.is_absolute()
            or self.ipc_root != self.ipc_root.absolute()
            or self.ipc_root.is_symlink()
        ):
            raise IpcError("IPC_ROOT_INVALID")
        if self.ipc_root.exists():
            info = self.ipc_root.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise IpcError("IPC_DIRECTORY_TYPE")
            os.chmod(self.ipc_root, 0o700)
        else:
            self.ipc_root.mkdir(parents=True, mode=0o700)
        if stat.S_IMODE(self.ipc_root.stat().st_mode) != 0o700:
            raise IpcError("IPC_DIRECTORY_MODE")
        self._tokens: dict[tuple[str, int], bytes] = {}
        self._retired_tokens: dict[tuple[str, int], bytes] = {}
        self._leases: dict[tuple[str, int], dict] = {}
        self._replays: dict[tuple[str, int, str], _ReplayEntry] = {}
        self._lock = threading.RLock()

    def issue(self, worker_id: str, generation: int) -> Path:
        return self.install_token(worker_id, generation, secrets.token_bytes(32))

    def install_token(self, worker_id: str, generation: int, token: bytes) -> Path:
        worker_id = _identifier("WORKER_ID", worker_id)
        generation = _positive_int("GENERATION", generation)
        if not isinstance(token, bytes) or len(token) != 32:
            raise IpcError("TOKEN_SIZE")
        key = (worker_id, generation)
        with self._lock:
            if key in self._tokens:
                raise IpcError("TOKEN_ALREADY_ISSUED")
            path = self.ipc_root / f"{worker_id}-g{generation}.token"
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            try:
                os.write(descriptor, token.hex().encode("ascii"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise IpcError("TOKEN_MODE")
            self._tokens[key] = token
            return path

    def load_token(self, worker_id: str, generation: int, path: Path) -> None:
        """Load an existing private token without creating or replacing its inode."""

        worker_id = _identifier("WORKER_ID", worker_id)
        generation = _positive_int("GENERATION", generation)
        path = Path(path)
        if (
            path.parent != self.ipc_root
            or path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or path.stat().st_uid != os.getuid()
        ):
            raise IpcError("TOKEN_PATH")
        try:
            token = bytes.fromhex(path.read_text(encoding="ascii"))
        except (OSError, UnicodeError, ValueError) as error:
            raise IpcError("TOKEN_TYPE") from error
        if len(token) != 32:
            raise IpcError("TOKEN_SIZE")
        key = (worker_id, generation)
        with self._lock:
            if key in self._tokens:
                raise IpcError("TOKEN_ALREADY_ISSUED")
            self._tokens[key] = token

    def bind_lease(self, worker_id: str, generation: int, lease: Mapping[str, object]) -> None:
        key = (_identifier("WORKER_ID", worker_id), _positive_int("GENERATION", generation))
        normalized = self._validate_lease(lease, worker_id=key[0], generation=key[1])
        with self._lock:
            if key not in self._tokens:
                raise IpcError("TOKEN_MISSING")
            self._leases[key] = normalized

    def advance_generation(self, worker_id: str, old_generation: int, new_generation: int) -> None:
        """Move one stable Worker's private token to its coordinator-approved generation."""
        worker_id = _identifier("WORKER_ID", worker_id)
        old = (worker_id, _positive_int("GENERATION", old_generation))
        new = (worker_id, _positive_int("GENERATION", new_generation))
        if new[1] != old[1] + 1:
            raise IpcError("GENERATION_SEQUENCE")
        with self._lock:
            if old not in self._tokens or new in self._tokens:
                raise IpcError("GENERATION_AUTHORITY")
            token = self._tokens.pop(old)
            self._tokens[new] = token
            self._retired_tokens[old] = token
            self._leases.pop(old, None)

    def _validate_lease(self, lease, *, worker_id, generation):
        if type(lease) is not dict or set(lease) != _LEASE_FIELDS:
            raise IpcError("LEASE_FIELDS")
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            _identifier(name.upper(), lease[name])
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            _positive_int(name.upper(), lease[name])
        if lease["coordinator_epoch"] != self.coordinator_epoch:
            raise IpcError("STALE_EPOCH")
        if lease["worker_id"] != worker_id or lease["worker_generation"] != generation:
            raise IpcError("STALE_GENERATION")
        return json.loads(canonical_json(lease))

    def authenticate(self, message: Mapping[str, object]) -> dict:
        if type(message) is not dict or set(message) != _REQUEST_FIELDS:
            raise IpcError("REQUEST_FIELDS")
        if type(message["schema_version"]) is not int or message["schema_version"] != 1:
            raise IpcError("SCHEMA_VERSION")
        if type(message["kind"]) is not str or message["kind"] not in _KINDS:
            raise IpcError("UNKNOWN_MESSAGE_KIND")
        worker_id = _identifier("WORKER_ID", message["worker_id"])
        generation = _positive_int("GENERATION", message["worker_generation"])
        epoch = _positive_int("EPOCH", message["coordinator_epoch"])
        if epoch != self.coordinator_epoch:
            raise IpcError("STALE_EPOCH")
        request_id = _identifier("REQUEST_ID", message["request_id"])
        _identifier("IDEMPOTENCY_KEY", message["idempotency_key"])
        if type(message["payload"]) is not dict:
            raise IpcError("PAYLOAD_TYPE")
        token = message["token"]
        if not isinstance(token, str) or len(token) != 64:
            raise IpcError("TOKEN_TYPE")
        try:
            supplied = bytes.fromhex(token)
        except ValueError as error:
            raise IpcError("TOKEN_TYPE") from error
        key = (worker_id, generation)
        with self._lock:
            expected = self._tokens.get(key)
            if expected is None:
                retired = self._retired_tokens.get(key)
                if retired is not None:
                    if not hmac.compare_digest(retired, supplied):
                        raise IpcError("TOKEN_MISMATCH")
                    replay = self._replays.get(
                        (worker_id, generation, message["idempotency_key"])
                    )
                    digest = hashlib.sha256(canonical_json(message)).hexdigest()
                    if replay is None or replay.digest != digest:
                        raise IpcError("STALE_GENERATION")
                    return json.loads(canonical_json(message))
                if any(candidate[0] == worker_id for candidate in self._tokens):
                    raise IpcError("STALE_GENERATION")
                raise IpcError("TOKEN_MISSING")
            if not hmac.compare_digest(expected, supplied):
                raise IpcError("TOKEN_MISMATCH")
            operation = message["payload"].get("operation")
            lease_optional = operation in {
                "register_worker", "grant_lease", "record_recovery",
                "cancel_generation", "replace_resources",
                "health",
                "stop", "cancel_motion", "confirm_no_controller_goal", "recover",
                "readiness", "release_start", "startup_broker",
            }
            if message["lease"] is None:
                if not lease_optional:
                    raise IpcError("LEASE_REQUIRED")
            else:
                lease = self._validate_lease(
                    message["lease"], worker_id=worker_id, generation=generation
                )
                if self._leases.get(key) != lease:
                    raise IpcError("STALE_LEASE")
        normalized = json.loads(canonical_json(message))
        normalized["request_id"] = request_id
        return normalized

    def dispatch(self, message: Mapping[str, object], mutation: Callable[[dict], object]):
        authenticated = self.authenticate(message)
        key = (
            authenticated["worker_id"],
            authenticated["worker_generation"],
            authenticated["idempotency_key"],
        )
        digest = hashlib.sha256(canonical_json(authenticated)).hexdigest()
        return _dispatch_idempotently(
            self._replays,
            self._lock,
            key,
            digest,
            authenticated,
            mutation,
        )


def _response(message: Mapping[str, object], *, payload=None, error=None) -> dict:
    value = {
        "schema_version": 1,
        "kind": "response",
        "request_id": message.get("request_id", "rejected"),
        "idempotency_key": message.get("idempotency_key", "rejected"),
        "ok": error is None,
        "payload": payload if error is None else None,
        "error": error,
    }
    if set(value) != _RESPONSE_FIELDS:
        raise AssertionError("response schema")
    return value


class AuthenticatedUnixServer:
    """One strict request/response endpoint; callers control its service loop."""

    def __init__(
        self,
        path,
        authority,
        handler,
        *,
        deadline_s=5.0,
        max_frame_bytes=_DEFAULT_MAX_FRAME,
        accept_poll_s=0.25,
        error_reply_timeout_s=1.0,
        max_concurrent_connections=1,
        metrics=None,
    ):
        self.path = Path(path)
        if self.path.parent != authority.ipc_root:
            raise IpcError("SOCKET_OUTSIDE_IPC_ROOT")
        if self.path.exists() or self.path.is_symlink():
            raise IpcError("SOCKET_EXISTS")
        self.authority = authority
        self.handler = handler
        self.deadline_s = float(deadline_s)
        self.max_frame_bytes = max_frame_bytes
        self.accept_poll_s = float(accept_poll_s)
        self.error_reply_timeout_s = float(error_reply_timeout_s)
        self.metrics = metrics
        self.max_concurrent_connections = _positive_int(
            "MAX_CONCURRENT_CONNECTIONS", max_concurrent_connections
        )
        if self.max_concurrent_connections > 16:
            raise IpcError("MAX_CONCURRENT_CONNECTIONS_LIMIT")
        self._executor = (
            None
            if self.max_concurrent_connections == 1
            else ThreadPoolExecutor(
                max_workers=self.max_concurrent_connections,
                thread_name_prefix="authenticated-unix",
            )
        )
        self._handler_slots = (
            None
            if self._executor is None
            else threading.BoundedSemaphore(self.max_concurrent_connections)
        )
        self._handlers = set()
        self._handlers_condition = threading.Condition()
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._parent_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._address = transport_address(self.path, self._parent_fd)
        try:
            self._socket.bind(self._address)
        except BaseException:
            os.close(self._parent_fd)
            raise
        os.chmod(self.path, 0o600)
        self.bound_mode = stat.S_IMODE(self.path.stat().st_mode)
        if self.bound_mode != 0o600:
            self.close()
            raise IpcError("SOCKET_MODE")
        self._socket.listen(16)
        self._closed = threading.Event()

    def serve_once(self) -> None:
        if self._handler_slots is not None and not self._handler_slots.acquire(
            timeout=self.accept_poll_s
        ):
            raise IpcError("HANDLER_POLL")
        self._socket.settimeout(self.accept_poll_s)
        try:
            connection, _ = self._socket.accept()
        except (TimeoutError, socket.timeout) as error:
            if self._handler_slots is not None:
                self._handler_slots.release()
            raise IpcError("ACCEPT_POLL") from error
        except BaseException:
            if self._handler_slots is not None:
                self._handler_slots.release()
            raise
        connection_id = (
            None if self.metrics is None else self.metrics.connection_accepted()
        )
        if self._executor is None:
            self._serve_connection(connection, connection_id)
            return
        try:
            future = self._executor.submit(
                self._serve_connection, connection, connection_id
            )
        except BaseException:
            connection.close()
            self._handler_slots.release()
            raise
        with self._handlers_condition:
            self._handlers.add(future)
        future.add_done_callback(self._handler_finished)

    def _handler_finished(self, future) -> None:
        try:
            future.exception()
        except BaseException:
            pass
        with self._handlers_condition:
            self._handlers.discard(future)
            self._handlers_condition.notify_all()
        self._handler_slots.release()

    def wait_handlers(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + float(timeout_s)
        with self._handlers_condition:
            while self._handlers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._handlers_condition.wait(remaining)
        return True

    def _serve_connection(self, connection, connection_id=None) -> None:
        message = None
        try:
            deadline = time.monotonic() + self.deadline_s
            with connection:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise IpcError("DEADLINE_EXCEEDED")
                message = receive_frame(
                    connection,
                    deadline_s=remaining,
                    max_frame_bytes=self.max_frame_bytes,
                )
                if self.metrics is not None:
                    self.metrics.connection_event(
                        connection_id, "received", message
                    )
                try:
                    completed = threading.Event()
                    result = {}

                    def invoke():
                        try:
                            result["payload"] = self.authority.dispatch(message, self.handler)
                        except BaseException as error:
                            result["error"] = error
                        finally:
                            completed.set()

                    threading.Thread(target=invoke, daemon=True).start()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not completed.wait(remaining):
                        if self.metrics is not None:
                            self.metrics.handler_timeout(connection_id, message)
                        raise IpcError("HANDLER_DEADLINE_EXCEEDED")
                    if "error" in result:
                        raise result["error"]
                    payload = result["payload"]
                    reply = _response(message, payload=payload)
                except IpcError as error:
                    reply = _response(message, error=str(error))
                except Exception as error:
                    reply = _response(message, error=f"HANDLER_REJECTED: {error}")
                frame = encode_frame(reply, max_frame_bytes=self.max_frame_bytes)
                if self.metrics is not None:
                    self.metrics.connection_event(
                        connection_id, "serialized", message
                    )
                connection.settimeout(self.error_reply_timeout_s)
                try:
                    connection.sendall(frame)
                    if self.metrics is not None:
                        self.metrics.connection_event(
                            connection_id, "sent", message
                        )
                except (BrokenPipeError, ConnectionResetError) as error:
                    if self.metrics is not None:
                        self.metrics.connection_event(
                            connection_id, "send_failed", message, error
                        )
                    return
        except BaseException as error:
            if self.metrics is not None:
                self.metrics.connection_event(
                    connection_id, "transport_error", message, error
                )
            raise
        finally:
            if self.metrics is not None:
                self.metrics.connection_closed(connection_id)

    def stop_accept(self) -> None:
        self._closed.set()
        self._socket.close()

    def close(self) -> None:
        self.stop_accept()
        try:
            if self._executor is not None:
                self._executor.shutdown(wait=False)
        finally:
            try:
                os.unlink(self.path.name, dir_fd=self._parent_fd)
            except FileNotFoundError:
                pass
            try:
                os.close(self._parent_fd)
            except OSError:
                pass

    def serve_forever(self) -> None:
        while not self._closed.is_set():
            try:
                self.serve_once()
            except IpcError as error:
                if self._closed.is_set() or any(
                    marker in str(error) for marker in ("ACCEPT_POLL", "HANDLER_POLL")
                ):
                    continue
            except OSError:
                if not self._closed.is_set():
                    raise


class UnixRpcClient:
    def __init__(self, path, *, deadline_s=5.0, max_frame_bytes=_DEFAULT_MAX_FRAME):
        self.path = Path(path)
        self.deadline_s = float(deadline_s)
        self.max_frame_bytes = max_frame_bytes

    def call(self, message: Mapping[str, object]) -> dict:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.deadline_s)
            parent_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                connection.connect(transport_address(self.path, parent_fd))
            finally:
                os.close(parent_fd)
            connection.sendall(encode_frame(message, max_frame_bytes=self.max_frame_bytes))
            connection.shutdown(socket.SHUT_WR)
            reply = receive_frame(
                connection,
                deadline_s=self.deadline_s,
                max_frame_bytes=self.max_frame_bytes,
            )
        if type(reply) is not dict or set(reply) != _RESPONSE_FIELDS:
            raise IpcError("RESPONSE_FIELDS")
        if type(reply["schema_version"]) is not int or reply["schema_version"] != 1:
            raise IpcError("RESPONSE_SCHEMA")
        if type(reply["kind"]) is not str or reply["kind"] != "response":
            raise IpcError("RESPONSE_KIND")
        if reply["request_id"] != message["request_id"] or reply["idempotency_key"] != message["idempotency_key"]:
            raise IpcError("RESPONSE_IDENTITY")
        if type(reply["ok"]) is not bool:
            raise IpcError("RESPONSE_TYPE")
        if not reply["ok"]:
            if reply["payload"] is not None or not isinstance(reply["error"], str) or not reply["error"]:
                raise IpcError("RESPONSE_TYPE")
            raise IpcError(str(reply["error"]))
        if reply["error"] is not None:
            raise IpcError("RESPONSE_TYPE")
        return reply


def _inference_request(document):
    from so101_demo.parallel_batch.contracts import ExecutionKind, InferenceRequest

    if type(document) is not dict:
        raise IpcError("INFERENCE_REQUEST_TYPE")
    try:
        values = dict(document)
        if values.get("execution_kind") is not None:
            values["execution_kind"] = ExecutionKind(values["execution_kind"])
        return InferenceRequest(**values)
    except (KeyError, TypeError, ValueError) as error:
        raise IpcError("INFERENCE_REQUEST_INVALID") from error


def _snapshot(document):
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        NormalizedInferenceResponseIdentity,
    )
    from so101_demo.runtime.parallel_perception_runtime import Snapshot

    required = {"shape", "source_stamp_ns", "source_frame_id", "query_class_id"}
    compatibility = {"start_event_id", "start_event_type", "start_identity"}
    if (
        type(document) is not dict
        or not required.issubset(document)
        or not set(document).issubset(required | compatibility)
    ):
        raise IpcError("SNAPSHOT_FIELDS")
    try:
        start_identity = None
        identity = document.get("start_identity")
        if identity is not None:
            if type(identity) is not dict:
                raise ValueError("start identity")
            identity_values = dict(identity)
            identity_values["execution_kind"] = ExecutionKind(
                identity_values["execution_kind"]
            )
            start_identity = NormalizedInferenceResponseIdentity(**identity_values)
        shape = document["shape"]
        if (
            type(shape) is not list
            or len(shape) != 3
            or any(type(value) is not int or value <= 0 for value in shape)
        ):
            raise ValueError("shape")
        if type(document["source_stamp_ns"]) is not int or document["source_stamp_ns"] <= 0:
            raise ValueError("source stamp")
        for name in ("source_frame_id", "query_class_id"):
            if not isinstance(document[name], str) or not document[name]:
                raise ValueError(name)
        for name in ("start_event_id", "start_event_type"):
            if name in document and document[name] is not None and (
                not isinstance(document[name], str) or not document[name]
            ):
                raise ValueError(name)
        return Snapshot(
            shape=tuple(shape),
            source_stamp_ns=document["source_stamp_ns"],
            source_frame_id=document["source_frame_id"],
            query_class_id=document["query_class_id"],
            start_event_id=document.get("start_event_id"),
            start_event_type=document.get("start_event_type"),
            start_identity=start_identity,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IpcError("SNAPSHOT_INVALID") from error


def _broker_response(response):
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts import ParallelRuntimeConfig
    from so101_demo.runtime.parallel_perception_runtime import GROUNDED_ID, YOLO_ID

    if type(response) is not BrokerResponse:
        raise IpcError("BROKER_RESPONSE_REQUIRED")
    return {
        "request_id": response.request.request_id,
        "model_id": response.request.model_id,
        "model_version": (
            response.candidate.get("weights_sha256")
            if isinstance(response.candidate, dict)
            and isinstance(response.candidate.get("weights_sha256"), str)
            else {
                YOLO_ID: ParallelRuntimeConfig.FROZEN_YOLO_WEIGHTS_SHA256,
                GROUNDED_ID:
                    ParallelRuntimeConfig.FROZEN_GROUNDED_SAM_MANIFEST_SHA256,
            }[response.request.model_id]
        ),
        "broker_generation": response.broker_generation,
        "outcome": response.outcome.value,
        "candidate": response.candidate,
        "reason": response.reason,
        "queued_monotonic_s": response.queued_monotonic_s,
        "queue_deadline_monotonic_s": response.queue_deadline_monotonic_s,
        "started_monotonic_s": response.started_monotonic_s,
        "inference_deadline_monotonic_s": response.inference_deadline_monotonic_s,
        "completed_monotonic_s": response.completed_monotonic_s,
    }


class _StatelessBrokerDispatcher:
    """Validate one inference envelope locally without scheduling authority."""

    def __init__(self, ipc_root, metrics=None):
        self.ipc_root = Path(ipc_root)
        self._metrics = metrics

    def dispatch(self, message, mutation):
        if type(message) is not dict:
            raise IpcError("REQUEST_FIELDS")
        fields = set(message)
        if (
            not _BROKER_REQUEST_FIELDS.issubset(fields)
            or not fields.issubset(
                _BROKER_REQUEST_FIELDS | _BROKER_COMPATIBILITY_FIELDS
            )
        ):
            raise IpcError("REQUEST_FIELDS")
        if message["schema_version"] != 1 or type(message["schema_version"]) is not int:
            raise IpcError("SCHEMA_VERSION")
        if message["kind"] != "broker_call":
            raise IpcError("UNKNOWN_MESSAGE_KIND")
        _identifier("REQUEST_ID", message["request_id"])
        _identifier("IDEMPOTENCY_KEY", message["idempotency_key"])
        if type(message["payload"]) is not dict:
            raise IpcError("PAYLOAD_TYPE")
        if self._metrics is not None:
            self._metrics.validated(message)
        return mutation(message)


class BrokerTransport:
    """Bounded request/response transport for the stateless Broker seam."""

    def __init__(
        self, *, ipc_root, config, generation, deadline_s,
        runtime_identity=None,
    ):
        self.ipc_root = Path(ipc_root)
        if not self.ipc_root.is_dir() or self.ipc_root.is_symlink():
            raise IpcError("IPC_DIRECTORY_TYPE")
        self.config = config
        self.generation = _positive_int("BROKER_GENERATION", generation)
        self.deadline_s = float(deadline_s)
        if self.deadline_s <= 0:
            raise IpcError("DEADLINE")
        self.max_frame_bytes = _positive_int(
            "FRAME_LIMIT", getattr(config, "broker_max_frame_bytes", None)
        )
        self._runtime_identity = (
            None if runtime_identity is None else canonical_json(runtime_identity)
        )
        self._ready_identity = None
        self._metrics = _BrokerMetrics()

    @property
    def runtime_identity(self):
        return (
            None
            if self._runtime_identity is None
            else _decode_payload(self._runtime_identity)
        )

    def bind_ready_identity(self, receipt) -> str:
        """Freeze the exact durable ready receipt served by health checks."""
        if type(receipt) is not dict:
            raise IpcError("BROKER_READY_IDENTITY")
        encoded = canonical_json(receipt)
        self._ready_identity = encoded
        return hashlib.sha256(encoded).hexdigest()

    def report_health_down(self, event):
        """Validate a local health event; Workers own control-plane reporting."""
        if type(event) is not dict or set(event) != {
            "outcome", "request_id", "reason"
        }:
            raise IpcError("BROKER_HEALTH_DOWN_FIELDS")
        if event["outcome"] not in {
            "INFRA_ERROR", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT"
        }:
            raise IpcError("BROKER_HEALTH_DOWN_OUTCOME")
        for name in ("request_id", "reason"):
            if not isinstance(event[name], str) or not event[name]:
                raise IpcError("BROKER_HEALTH_DOWN_TYPE")
        return True

    @staticmethod
    def serialize_request(request):
        from so101_demo.parallel_batch.contracts import InferenceRequest

        if type(request) is not InferenceRequest:
            raise IpcError("INFERENCE_REQUEST_REQUIRED")
        value = asdict(request)
        value["execution_kind"] = (
            None if request.execution_kind is None else request.execution_kind.value
        )
        return value

    @staticmethod
    def serialize_snapshot(snapshot):
        from so101_demo.runtime.parallel_perception_runtime import Snapshot

        if type(snapshot) is not Snapshot:
            raise IpcError("SNAPSHOT_REQUIRED")
        value = asdict(snapshot)
        value["shape"] = list(snapshot.shape)
        if snapshot.start_identity is not None:
            value["start_identity"]["execution_kind"] = (
                snapshot.start_identity.execution_kind.value
            )
        return {name: item for name, item in value.items() if item is not None}

    def _handler(self, service, message):
        payload = message.get("payload")
        if type(payload) is not dict:
            raise IpcError("PAYLOAD_TYPE")
        operation = payload.get("operation")
        if operation == "health":
            if set(payload) != {"operation", "ready_sha256"}:
                raise IpcError("BROKER_HEALTH_FIELDS")
            if self._ready_identity is None:
                raise IpcError("BROKER_NOT_READY")
            digest = hashlib.sha256(self._ready_identity).hexdigest()
            if payload["ready_sha256"] != digest:
                raise IpcError("BROKER_READY_IDENTITY_MISMATCH")
            return {
                "ready": _decode_payload(self._ready_identity),
                "ready_sha256": digest,
            }
        if operation == "infer":
            if set(payload) != {"operation", "request", "snapshot"}:
                raise IpcError("BROKER_INFER_FIELDS")
            request = _inference_request(payload["request"])
            snapshot = _snapshot(payload["snapshot"])
            submission = service.submit(request, snapshot)
            response = submission.response
            if response is None and submission.accepted:
                response = service.wait_response(
                    request, timeout_s=self.deadline_s
                )
            if response is None:
                raise IpcError("BROKER_RESPONSE_PENDING")
            return _broker_response(response)
        if operation == "cancel_generation":
            if set(payload) != {"operation", "worker_id", "worker_generation"}:
                raise IpcError("BROKER_CANCEL_FIELDS")
            service.broker.cancel_generation(
                _identifier("WORKER_ID", payload["worker_id"]),
                _positive_int("GENERATION", payload["worker_generation"]),
            )
            return {"cancelled": True}
        raise IpcError("UNKNOWN_BROKER_OPERATION")

    def server(self, service, *, endpoint):
        authority = _StatelessBrokerDispatcher(self.ipc_root, self._metrics)
        set_metrics = getattr(service, "set_metrics", None)
        if callable(set_metrics):
            set_metrics(self._metrics)
        return AuthenticatedUnixServer(
            endpoint,
            authority,
            lambda message: self._handler(service, message),
            deadline_s=self.deadline_s,
            max_frame_bytes=self.max_frame_bytes,
            max_concurrent_connections=(self.runtime_identity or {}).get(
                "connection_handler_count", 1
            ),
            metrics=self._metrics,
        )

    def metrics_snapshot(self):
        return self._metrics.snapshot()

    def persist_metrics_summary(self):
        """Atomically retain payload-free Broker phase evidence."""
        document = {
            "schema_version": 1,
            "kind": "broker_concurrency_summary",
            **self.metrics_snapshot(),
        }
        payload = canonical_json(document)
        temporary = self.ipc_root / (
            f".broker-concurrency-summary-{os.getpid()}-{threading.get_ident()}.tmp"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        target = self.ipc_root / "broker-concurrency-summary.json"
        os.replace(temporary, target)
        parent = os.open(self.ipc_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return target

    def serve(self, runtime, *, endpoint):
        from so101_demo.runtime.parallel_perception_runtime import PerceptionService

        service = PerceptionService(
            runtime,
            self.config,
            generation=self.generation,
            health_down=self.report_health_down,
            queue_capacity_per_model=(self.runtime_identity or {}).get(
                "queue_capacity_per_model"
            ),
        )
        server = None
        try:
            service.start()
            server = self.server(service, endpoint=endpoint)
            server.serve_forever()
        finally:
            if server is not None:
                server.stop_accept()
            service_closed = service.close(timeout_s=self.deadline_s)
            handlers_closed = (
                True
                if server is None
                else server.wait_handlers(timeout_s=self.deadline_s)
            )
            if server is not None:
                server.close()
            summary_path = self.persist_metrics_summary()
            print(summary_path.read_text(encoding="utf-8"), file=os.sys.stderr, flush=True)
            if not service_closed or not handlers_closed:
                raise IpcError("BROKER_SHUTDOWN_TIMEOUT")


def build_broker_transport(runtime_spec):
    """Load the mounted stateless Broker runtime/config contract."""

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config

    runtime_spec = Path(runtime_spec)
    try:
        raw = runtime_spec.read_bytes()
        document = _decode_payload(raw)
    except (OSError, IpcError) as error:
        raise IpcError("BROKER_SPEC_INVALID") from error
    fields = {
        "schema_version",
        "kind",
        "batch_id",
        "coordinator_epoch",
        "broker_generation",
        "run_mode",
        "image_id",
        "yolo_weights_sha256",
        "grounded_manifest_sha256",
        "config_path",
        "request_deadline_s",
        "max_frame_bytes",
    }
    adaptive_fields = {
        "queue_capacity_per_model",
        "connection_handler_count",
        "yolo_executor_count",
        "grounded_sam_executor_count",
    }
    if (
        set(document) not in (fields, fields | adaptive_fields)
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["kind"] != "so101_parallel_broker_runtime"
    ):
        raise IpcError("BROKER_SPEC_FIELDS")
    _identifier("BATCH_ID", document["batch_id"])
    _positive_int("EPOCH", document["coordinator_epoch"])
    generation = _positive_int("BROKER_GENERATION", document["broker_generation"])
    if adaptive_fields.issubset(document):
        capacity = _positive_int(
            "QUEUE_CAPACITY", document["queue_capacity_per_model"]
        )
        if capacity > 16:
            raise IpcError("BROKER_QUEUE_CAPACITY")
        handlers = _positive_int(
            "CONNECTION_HANDLER_COUNT", document["connection_handler_count"]
        )
        if handlers > 16:
            raise IpcError("BROKER_CONNECTION_HANDLER_COUNT")
        yolo_executors = _positive_int(
            "YOLO_EXECUTOR_COUNT", document["yolo_executor_count"]
        )
        if yolo_executors not in {1, 2, 4}:
            raise IpcError("BROKER_YOLO_EXECUTOR_COUNT")
        if (
            document["grounded_sam_executor_count"] != 1
            or type(document["grounded_sam_executor_count"]) is not int
        ):
            raise IpcError("BROKER_GROUNDED_SAM_EXECUTOR_COUNT")
    if document["run_mode"] not in {"plan_only", "execute"}:
        raise IpcError("BROKER_RUN_MODE")
    if (
        not isinstance(document["image_id"], str)
        or len(document["image_id"]) != 71
        or not document["image_id"].startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in document["image_id"][7:]
        )
    ):
        raise IpcError("BROKER_IMAGE_ID")
    for name in ("yolo_weights_sha256", "grounded_manifest_sha256"):
        value = document[name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise IpcError("BROKER_MODEL_HASH")
    config_path = Path(document["config_path"])
    if not config_path.is_absolute():
        raise IpcError("BROKER_SPEC_PATH")
    ipc_root = config_path.parent
    config = load_parallel_runtime_config(config_path)
    if (
        document["yolo_weights_sha256"] != config.yolo_weights_sha256
        or document["grounded_manifest_sha256"]
        != config.grounded_sam_manifest_sha256
    ):
        raise IpcError("BROKER_MODEL_HASH_MISMATCH")
    max_frame_bytes = _positive_int("FRAME_LIMIT", document["max_frame_bytes"])
    if max_frame_bytes != config.broker_max_frame_bytes:
        raise IpcError("BROKER_FRAME_LIMIT_MISMATCH")
    deadline = document["request_deadline_s"]
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or deadline <= 0
        or deadline > config.batch_hard_timeout_s
    ):
        raise IpcError("BROKER_DEADLINE")
    if adaptive_fields.issubset(document):
        expected_deadline = max(
            config.yolo_queue_timeout_s + config.yolo_inference_timeout_s,
            config.grounded_sam_queue_timeout_s
            + config.grounded_sam_inference_timeout_s,
        ) + config.heartbeat_timeout_s
        if (
            capacity != handlers
            or yolo_executors > handlers
            or float(deadline) != expected_deadline
        ):
            raise IpcError("BROKER_ADAPTIVE_CONCURRENCY")
    return BrokerTransport(
        ipc_root=ipc_root,
        config=config,
        generation=generation,
        deadline_s=float(deadline),
        runtime_identity=document,
    )
