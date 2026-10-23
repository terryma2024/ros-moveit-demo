"""The worker token authority, the authenticated Unix server and the RPC client."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import threading
import time
from typing import Callable, Mapping

from so101_demo.runtime.parallel_ipc.frames import (
    _DEFAULT_MAX_FRAME,
    _KINDS,
    _LEASE_FIELDS,
    _REQUEST_FIELDS,
    _RESPONSE_FIELDS,
    IpcError,
    _dispatch_idempotently,
    _identifier,
    _positive_int,
    _ReplayEntry,
    canonical_json,
    encode_frame,
    receive_frame,
    transport_address,
)


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

    def close(self, *, preserve_socket: bool = False) -> None:
        if type(preserve_socket) is not bool:
            raise IpcError('SOCKET_RETENTION_INVALID')
        self.stop_accept()
        try:
            if self._executor is not None:
                self._executor.shutdown(wait=False)
        finally:
            try:
                if not preserve_socket:
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
