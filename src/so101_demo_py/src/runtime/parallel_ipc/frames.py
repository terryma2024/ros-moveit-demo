"""Transport addresses, request field sets, canonical JSON and the frame codec."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
import time
from typing import Mapping


class IpcError(RuntimeError):
    """A frame, identity, authentication, or transport contract failed."""


# sun_path capacity in bytes, including the terminating NUL. Linux addresses the socket
# through a pinned parent descriptor. Darwin has no bindat/connectat equivalent, so it uses
# the verified canonical path and its smaller kernel capacity.
UNIX_SOCKADDR_CAPACITY_BYTES = 104 if sys.platform == "darwin" else 108


_PROC_FD_ROOT = Path("/proc/self/fd")


_TRANSPORT_PREFIX = "/proc/self/fd/"


_MAX_FD_DIGITS = 10


def require_proc_fd_transport(proc_root: Path | None = None) -> None:
    """Fail closed when the Linux dirfd transport is unavailable."""

    if proc_root is None and sys.platform == "darwin":
        return
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
    candidate = Path(path)
    name = candidate.name
    encoded = os.fsencode(name)
    if not encoded or name in {".", ".."} or b"\x00" in encoded:
        raise IpcError(f"UNIX_SOCKET_BASENAME_INVALID: {path}")
    if sys.platform == "darwin":
        if len(os.fsencode(candidate)) + 1 > UNIX_SOCKADDR_CAPACITY_BYTES:
            raise IpcError(f"UNIX_SOCKET_PATH_TOO_LONG: {path}")
        return
    # Conservative Linux reservation: unknown fd digits, separator and terminating NUL.
    reserved = len(_TRANSPORT_PREFIX.encode("ascii")) + _MAX_FD_DIGITS + 1 + 1
    if reserved + len(encoded) > UNIX_SOCKADDR_CAPACITY_BYTES:
        raise IpcError(f"UNIX_SOCKET_PATH_TOO_LONG: {path}")


def transport_address(path: object, parent_fd: int) -> str:
    """Exact short kernel address; rechecked once the owned parent descriptor exists."""

    if type(parent_fd) is not int or parent_fd < 0:
        raise IpcError("UNIX_TRANSPORT_DESCRIPTOR")
    candidate = Path(path)
    if sys.platform == "darwin":
        try:
            held = os.fstat(parent_fd)
            current = os.stat(candidate.parent, follow_symlinks=False)
        except OSError as error:
            raise IpcError("UNIX_TRANSPORT_DESCRIPTOR") from error
        if (
            not stat.S_ISDIR(current.st_mode)
            or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise IpcError("UNIX_TRANSPORT_PARENT")
        address = str(candidate)
        if len(os.fsencode(address)) + 1 > UNIX_SOCKADDR_CAPACITY_BYTES:
            raise IpcError(f"UNIX_SOCKET_PATH_TOO_LONG: {path}")
        return address
    address = f"{_TRANSPORT_PREFIX}{parent_fd}/{candidate.name}"
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
