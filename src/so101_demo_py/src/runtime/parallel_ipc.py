"""Strict authenticated Unix-socket transport for parallel Workers."""

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
from dataclasses import asdict
from typing import Callable, Mapping


class IpcError(RuntimeError):
    """A frame, identity, authentication, or transport contract failed."""


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
        try:
            self.ipc_root.relative_to(self.root / "ipc")
        except ValueError as error:
            raise IpcError("IPC_ROOT_OUTSIDE_EVIDENCE") from error
        if self.ipc_root.exists():
            info = self.ipc_root.lstat()
            if not stat.S_ISDIR(info.st_mode) or self.ipc_root.is_symlink():
                raise IpcError("IPC_DIRECTORY_TYPE")
            os.chmod(self.ipc_root, 0o700)
        else:
            self.ipc_root.mkdir(parents=True, mode=0o700)
        if stat.S_IMODE(self.ipc_root.stat().st_mode) != 0o700:
            raise IpcError("IPC_DIRECTORY_MODE")
        self._tokens: dict[tuple[str, int], bytes] = {}
        self._retired_tokens: dict[tuple[str, int], bytes] = {}
        self._leases: dict[tuple[str, int], dict] = {}
        self._replays: dict[tuple[str, int, str], tuple[str, bytes]] = {}
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
                    if replay is None or replay[0] != digest:
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
                "authenticate_broker_message", "authorize_inference",
                "broker_health_down", "health",
                "stop", "cancel_motion", "confirm_no_controller_goal", "recover",
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
        with self._lock:
            prior = self._replays.get(key)
            if prior is not None:
                if prior[0] != digest:
                    raise IpcError("IDEMPOTENCY_CONFLICT")
                return _decode_payload(prior[1])
            result = mutation(authenticated)
            detached = canonical_json(result)
            self._replays[key] = (digest, detached)
            return _decode_payload(detached)


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

    def __init__(self, path, authority, handler, *, deadline_s=5.0, max_frame_bytes=_DEFAULT_MAX_FRAME):
        self.path = Path(path)
        if self.path.parent != authority.ipc_root:
            raise IpcError("SOCKET_OUTSIDE_IPC_ROOT")
        if self.path.exists() or self.path.is_symlink():
            raise IpcError("SOCKET_EXISTS")
        self.authority = authority
        self.handler = handler
        self.deadline_s = float(deadline_s)
        self.max_frame_bytes = max_frame_bytes
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._parent_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._address = f"/proc/self/fd/{self._parent_fd}/{self.path.name}"
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
        deadline = time.monotonic() + self.deadline_s
        self._socket.settimeout(self.deadline_s)
        try:
            connection, _ = self._socket.accept()
        except (TimeoutError, socket.timeout) as error:
            raise IpcError("ACCEPT_DEADLINE") from error
        with connection:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IpcError("DEADLINE_EXCEEDED")
            message = receive_frame(
                connection,
                deadline_s=remaining,
                max_frame_bytes=self.max_frame_bytes,
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
                    raise IpcError("HANDLER_DEADLINE_EXCEEDED")
                if "error" in result:
                    raise result["error"]
                payload = result["payload"]
                reply = _response(message, payload=payload)
            except IpcError as error:
                reply = _response(message, error=str(error))
            except Exception as error:
                reply = _response(message, error=f"HANDLER_REJECTED: {error}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            connection.settimeout(remaining)
            try:
                connection.sendall(
                    encode_frame(reply, max_frame_bytes=self.max_frame_bytes)
                )
            except (BrokenPipeError, ConnectionResetError):
                # A Worker can disappear after its authenticated request was
                # handled.  Its reply channel is request-local and must not
                # take down the shared Broker/coordinator service loop.
                return

    def close(self) -> None:
        self._closed.set()
        try:
            self._socket.close()
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
                if self._closed.is_set() or "ACCEPT_DEADLINE" in str(error):
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
                connection.connect(f"/proc/self/fd/{parent_fd}/{self.path.name}")
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

    if type(document) is not dict or set(document) != {
        "shape",
        "source_stamp_ns",
        "source_frame_id",
        "start_event_id",
        "start_event_type",
        "start_identity",
        "query_class_id",
    }:
        raise IpcError("SNAPSHOT_FIELDS")
    identity = document["start_identity"]
    if type(identity) is not dict:
        raise IpcError("SNAPSHOT_IDENTITY")
    try:
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
        for name in ("source_frame_id", "start_event_id", "start_event_type", "query_class_id"):
            if not isinstance(document[name], str) or not document[name]:
                raise ValueError(name)
        return Snapshot(
            tuple(shape),
            document["source_stamp_ns"],
            document["source_frame_id"],
            document["start_event_id"],
            document["start_event_type"],
            start_identity,
            document["query_class_id"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IpcError("SNAPSHOT_INVALID") from error


def _broker_response(response):
    from so101_demo.parallel_batch.broker import BrokerResponse

    if type(response) is not BrokerResponse:
        raise IpcError("BROKER_RESPONSE_REQUIRED")
    return {
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


class _CoordinatorBackedBrokerAuthority:
    """Authenticate every Worker request at the parent Coordinator boundary."""

    def __init__(self, ipc_root, authority_call):
        self.ipc_root = Path(ipc_root)
        self._authority_call = authority_call
        self._replays = {}
        self._lock = threading.RLock()

    def dispatch(self, message, mutation):
        if type(message) is not dict:
            raise IpcError("REQUEST_FIELDS")
        self._authority_call("authenticate_broker_message", {"message": message})
        try:
            key = (
                message["worker_id"],
                message["worker_generation"],
                message["idempotency_key"],
            )
        except KeyError as error:
            raise IpcError("REQUEST_FIELDS") from error
        digest = hashlib.sha256(canonical_json(message)).hexdigest()
        with self._lock:
            prior = self._replays.get(key)
            if prior is not None:
                if prior[0] != digest:
                    raise IpcError("IDEMPOTENCY_CONFLICT")
                return _decode_payload(prior[1])
            result = mutation(message)
            detached = canonical_json(result)
            self._replays[key] = (digest, detached)
            return _decode_payload(detached)


class BrokerTransport:
    """Task 11 authenticated transport around the existing Task 7 service seam."""

    def __init__(
        self, *, ipc_root, config, generation, authority_call, deadline_s,
        runtime_identity=None,
    ):
        self.ipc_root = Path(ipc_root)
        if not self.ipc_root.is_dir() or self.ipc_root.is_symlink():
            raise IpcError("IPC_DIRECTORY_TYPE")
        self.config = config
        self.generation = _positive_int("BROKER_GENERATION", generation)
        if not callable(authority_call):
            raise IpcError("AUTHORITY_CALL")
        self._authority_call = authority_call
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

    def authorize(self, request, snapshot=None):
        payload = {"request": self.serialize_request(request)}
        if snapshot is not None:
            payload["snapshot"] = self.serialize_snapshot(snapshot)
        return self._authority_call("authorize_inference", payload) is True

    def report_health_down(self, event):
        """Publish one authenticated health-losing result for this generation."""
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
        return self._authority_call("broker_health_down", event) is True

    @staticmethod
    def serialize_request(request):
        from so101_demo.parallel_batch.contracts import InferenceRequest

        if type(request) is not InferenceRequest:
            raise IpcError("INFERENCE_REQUEST_REQUIRED")
        value = asdict(request)
        value["execution_kind"] = request.execution_kind.value
        return value

    @staticmethod
    def serialize_snapshot(snapshot):
        from so101_demo.runtime.parallel_perception_runtime import Snapshot

        if type(snapshot) is not Snapshot:
            raise IpcError("SNAPSHOT_REQUIRED")
        value = asdict(snapshot)
        value["shape"] = list(snapshot.shape)
        value["start_identity"]["execution_kind"] = (
            snapshot.start_identity.execution_kind.value
        )
        return value

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
            if self.authorize(request, snapshot) is not True:
                raise IpcError("START_EVENT_NOT_AUTHORIZED")
            submission = service.submit(request, snapshot)
            response = submission.response
            if response is None and submission.accepted:
                response = service.run_next()
            if response is None:
                response = service.poll_response(request)
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
        authority = _CoordinatorBackedBrokerAuthority(
            self.ipc_root, self._authority_call
        )
        return AuthenticatedUnixServer(
            endpoint,
            authority,
            lambda message: self._handler(service, message),
            deadline_s=self.deadline_s,
            max_frame_bytes=self.max_frame_bytes,
        )

    def serve(self, runtime, *, endpoint):
        from so101_demo.runtime.parallel_perception_runtime import PerceptionService

        service = PerceptionService(
            runtime,
            self.config,
            generation=self.generation,
            health_down=self.report_health_down,
        )
        service.start()
        server = self.server(service, endpoint=endpoint)
        try:
            server.serve_forever()
        finally:
            server.close()


class _BrokerCoordinatorClient:
    def __init__(
        self,
        endpoint,
        token_path,
        *,
        coordinator_epoch,
        generation,
        deadline_s,
        max_frame_bytes,
    ):
        self.client = UnixRpcClient(
            endpoint,
            deadline_s=deadline_s,
            max_frame_bytes=max_frame_bytes,
        )
        token_path = Path(token_path)
        if (
            not token_path.is_file()
            or token_path.is_symlink()
            or stat.S_IMODE(token_path.stat().st_mode) != 0o600
        ):
            raise IpcError("TOKEN_PATH")
        self.token = token_path.read_text(encoding="ascii")
        if len(self.token) != 64:
            raise IpcError("TOKEN_TYPE")
        self.coordinator_epoch = _positive_int("EPOCH", coordinator_epoch)
        self.generation = _positive_int("GENERATION", generation)
        self._sequence = 0
        self._lock = threading.Lock()

    def __call__(self, operation, payload):
        operation = _identifier("OPERATION", operation)
        if type(payload) is not dict:
            raise IpcError("PAYLOAD_TYPE")
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        key = f"broker-authority-{sequence}"
        message = {
            "schema_version": 1,
            "kind": "coordinator_call",
            "coordinator_epoch": self.coordinator_epoch,
            "worker_id": "broker",
            "worker_generation": self.generation,
            "lease": None,
            "request_id": key,
            "idempotency_key": key,
            "token": self.token,
            "payload": {"operation": operation, **payload},
        }
        try:
            reply = self.client.call(message)
        except (OSError, IpcError):
            reply = self.client.call(message)
        result = reply["payload"]
        expected = {
            "authenticate_broker_message": "authenticated",
            "authorize_inference": "authorized",
            "broker_health_down": "accepted",
        }.get(operation)
        if (
            type(result) is not dict
            or set(result) != {expected}
            or type(result[expected]) is not bool
        ):
            raise IpcError("BROKER_AUTHORITY_RESPONSE")
        return result[expected]


def build_broker_transport(runtime_spec):
    """Load the exact mounted Task 11 authority/config contract in the Broker."""

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
        "authority_endpoint",
        "authority_token_path",
        "request_deadline_s",
        "max_frame_bytes",
    }
    if (
        set(document) != fields
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["kind"] != "so101_parallel_broker_runtime"
    ):
        raise IpcError("BROKER_SPEC_FIELDS")
    _identifier("BATCH_ID", document["batch_id"])
    _positive_int("EPOCH", document["coordinator_epoch"])
    generation = _positive_int("BROKER_GENERATION", document["broker_generation"])
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
    endpoint = Path(document["authority_endpoint"])
    token_path = Path(document["authority_token_path"])
    if not all(path.is_absolute() for path in (config_path, endpoint, token_path)):
        raise IpcError("BROKER_SPEC_PATH")
    ipc_root = endpoint.parent
    if config_path.parent != ipc_root or token_path.parent != ipc_root:
        raise IpcError("BROKER_SPEC_PATH")
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
    authority_call = _BrokerCoordinatorClient(
        endpoint,
        token_path,
        coordinator_epoch=document["coordinator_epoch"],
        generation=generation,
        deadline_s=float(deadline),
        max_frame_bytes=max_frame_bytes,
    )
    return BrokerTransport(
        ipc_root=ipc_root,
        config=config,
        generation=generation,
        authority_call=authority_call,
        deadline_s=float(deadline),
        runtime_identity=document,
    )
