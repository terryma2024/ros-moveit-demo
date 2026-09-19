"""Schema-v4 permission-only RPC over the private Darwin Unix path.

The approved design (2026-09-19, sections 7.2 and 8) deliberately narrows the v4 trust model:
the caller is not authenticated. Being able to reach the mode-0600 socket inside a mode-0700
directory *is* the access check. So the v4 envelope carries only routing, deadline and payload:

    request : request_id, operation, deadline_monotonic_ns, payload
    response: request_id, status, output_descriptor | error, timing

No token, no generation, no lease, and no endpoint receipt, inode, `stat()` or peer-credential
check on the hot path. What is still checked is what protects the *server* from a malformed or
hostile frame: the fixed frame cap, a closed schema, an operation allowlist, the deadline, and a
bounded queue. The Coordinator still owns the robot-safety state machine, one-time result
consumption and controller conditions; none of that is relaxed here.

This module is additive. The v3 authenticated transport in :mod:`parallel_ipc` is untouched.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from .unix_address import (
    CampaignIpcRoot,
    DarwinPrivatePathUnixAddress,
    RegisteredEndpoint,
)

#: The closed v4 operation allowlist. An unknown operation is refused, never defaulted.
V4_OPERATIONS: frozenset[str] = frozenset({
    "broker.infer",
    "worker.progress",
    "worker.result",
    "coordinator.register_request",
    "coordinator.consume_result",
    "coordinator.cancel_request",
    "control.ready",
    "control.shutdown",
})

#: The only fields a v4 request may carry.
V4_REQUEST_FIELDS = ("request_id", "operation", "deadline_monotonic_ns", "payload")

#: The only fields a v4 response may carry. `output_descriptor` and `error` are exclusive.
V4_RESPONSE_FIELDS = ("request_id", "status", "error", "output_descriptor", "timing")

#: Stable error codes. The client may switch on these without parsing prose.
MALFORMED = "MALFORMED_FRAME"
OVERSIZED = "OVERSIZED_FRAME"
UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
EXPIRED = "DEADLINE_EXPIRED"
QUEUE_FULL = "QUEUE_FULL"
INVALID_REQUEST = "INVALID_REQUEST"
UNKNOWN_REQUEST = "UNKNOWN_REQUEST"
INTERNAL = "INTERNAL_ERROR"

OK = "OK"

DEFAULT_MAX_FRAME_BYTES = 8 * 1024 * 1024
DEFAULT_QUEUE_CAPACITY = 8

#: Fields that must never appear in a v4 frame. Their presence is itself a protocol error, which
#: is what makes "the design removed them" a testable fact rather than a comment.
FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "token", "generation", "lease", "lease_id", "lease_epoch", "endpoint_receipt",
    "peer_credentials", "inode", "receipt",
})


class V4IpcError(RuntimeError):
    """A v4 frame or transport contract failed. Carries the stable error code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------------------
# frames
# --------------------------------------------------------------------------------------


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _decode_object(payload: bytes) -> dict:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError) as error:
        raise V4IpcError(MALFORMED, str(error)) from error
    if type(value) is not dict:
        raise V4IpcError(MALFORMED, "frame payload must be a JSON object")
    return value


def encode_v4_frame(value: Mapping[str, object], *,
                    max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> bytes:
    if type(max_frame_bytes) is not int or max_frame_bytes <= 0:
        raise V4IpcError(OVERSIZED, "frame limit must be positive")
    payload = _canonical(value)
    if not payload or len(payload) > max_frame_bytes:
        raise V4IpcError(OVERSIZED, f"{len(payload)} bytes > {max_frame_bytes}")
    return struct.pack(">I", len(payload)) + payload


def decode_v4_frame(frame: bytes, *,
                    max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> dict:
    if not isinstance(frame, (bytes, bytearray)) or len(frame) < 4:
        raise V4IpcError(MALFORMED, "missing length prefix")
    size = struct.unpack(">I", frame[:4])[0]
    if size == 0 or size > max_frame_bytes:
        raise V4IpcError(OVERSIZED, f"declared size {size}")
    if len(frame) != size + 4:
        raise V4IpcError(MALFORMED, f"declared {size}, carried {len(frame) - 4}")
    return _decode_object(frame[4:])


def _check_no_forbidden_fields(document: Mapping[str, object], *, where: str) -> None:
    present = sorted(set(document) & FORBIDDEN_FIELDS)
    if present:
        raise V4IpcError(INVALID_REQUEST, f"{where} carries retired field(s) {present}")


@dataclass(frozen=True)
class V4Request:
    """A validated v4 request. Only these four fields exist."""

    request_id: str
    operation: str
    deadline_monotonic_ns: int
    payload: Mapping[str, object] = field(default_factory=dict)

    def to_document(self) -> dict:
        return {
            "request_id": self.request_id,
            "operation": self.operation,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "payload": dict(self.payload),
        }

    @staticmethod
    def from_document(document: object, *, now_monotonic_ns: int | None = None) -> "V4Request":
        if type(document) is not dict:
            raise V4IpcError(MALFORMED, "request must be a JSON object")
        _check_no_forbidden_fields(document, where="request")
        unknown = sorted(set(document) - set(V4_REQUEST_FIELDS))
        missing = sorted(set(V4_REQUEST_FIELDS) - set(document))
        if unknown:
            raise V4IpcError(INVALID_REQUEST, f"unknown request field(s) {unknown}")
        if missing:
            raise V4IpcError(INVALID_REQUEST, f"missing request field(s) {missing}")
        request_id = document["request_id"]
        if not isinstance(request_id, str) or not request_id:
            raise V4IpcError(INVALID_REQUEST, "request_id must be a non-empty string")
        operation = document["operation"]
        if operation not in V4_OPERATIONS:
            raise V4IpcError(UNKNOWN_OPERATION, str(operation))
        deadline = document["deadline_monotonic_ns"]
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise V4IpcError(INVALID_REQUEST, "deadline_monotonic_ns must be an int")
        payload = document["payload"]
        if type(payload) is not dict:
            raise V4IpcError(INVALID_REQUEST, "payload must be a JSON object")
        now = time.monotonic_ns() if now_monotonic_ns is None else int(now_monotonic_ns)
        if deadline <= now:
            raise V4IpcError(EXPIRED, f"deadline {deadline} <= now {now}")
        return V4Request(request_id=request_id, operation=operation,
                         deadline_monotonic_ns=deadline, payload=payload)


@dataclass(frozen=True)
class V4Response:
    """A validated v4 response: status plus exactly one of descriptor or error."""

    request_id: str
    status: str
    output_descriptor: Mapping[str, object] | None
    error: Mapping[str, object] | None
    timing: Mapping[str, object]

    @property
    def ok(self) -> bool:
        return self.status == OK

    def to_document(self) -> dict:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "error": None if self.error is None else dict(self.error),
            "output_descriptor": (None if self.output_descriptor is None
                                  else dict(self.output_descriptor)),
            "timing": dict(self.timing),
        }

    @staticmethod
    def from_document(document: object) -> "V4Response":
        if type(document) is not dict:
            raise V4IpcError(MALFORMED, "response must be a JSON object")
        _check_no_forbidden_fields(document, where="response")
        unknown = sorted(set(document) - set(V4_RESPONSE_FIELDS))
        missing = sorted(set(V4_RESPONSE_FIELDS) - set(document))
        if unknown:
            raise V4IpcError(INVALID_REQUEST, f"unknown response field(s) {unknown}")
        if missing:
            raise V4IpcError(INVALID_REQUEST, f"missing response field(s) {missing}")
        descriptor = document["output_descriptor"]
        error = document["error"]
        if (descriptor is None) == (error is None):
            raise V4IpcError(INVALID_REQUEST,
                             "exactly one of output_descriptor and error is required")
        return V4Response(
            request_id=str(document["request_id"]),
            status=str(document["status"]),
            output_descriptor=(None if descriptor is None else dict(descriptor)),
            error=(None if error is None else dict(error)),
            timing=dict(document["timing"]),
        )


def error_response(request_id: str, code: str, detail: str = "",
                   *, started_ns: int | None = None) -> V4Response:
    now = time.monotonic_ns()
    return V4Response(
        request_id=request_id, status=code,
        output_descriptor=None, error={"code": code, "detail": detail},
        timing={"started_monotonic_ns": now if started_ns is None else int(started_ns),
                "completed_monotonic_ns": now},
    )


# --------------------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------------------


class V4PermissionOnlyServer:
    """A bounded, permission-only v4 server on one registered private endpoint.

    The handler receives a validated :class:`V4Request` and returns either an output descriptor
    mapping or an "error" mapping. Anything else is turned into a stable error response, so a
    handler bug can never put an unbounded or off-schema frame on the wire.
    """

    def __init__(self, *, endpoint_path, handler: Callable[[V4Request], object],
                 max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES,
                 queue_capacity: int = DEFAULT_QUEUE_CAPACITY,
                 accept_timeout_s: float = 0.2) -> None:
        if type(max_frame_bytes) is not int or max_frame_bytes <= 0:
            raise V4IpcError(OVERSIZED, "max_frame_bytes must be positive")
        if type(queue_capacity) is not int or queue_capacity <= 0:
            raise V4IpcError(QUEUE_FULL, "queue_capacity must be positive")
        self.endpoint_path = str(endpoint_path)
        self._handler = handler
        self.max_frame_bytes = int(max_frame_bytes)
        self.queue_capacity = int(queue_capacity)
        self.accept_timeout_s = float(accept_timeout_s)
        self._queue: "queue.Queue[socket.socket]" = queue.Queue(maxsize=self.queue_capacity)
        self._sock: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._dispatch_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._workers_lock = threading.Lock()
        self.rejections: list[str] = []
        self.refused_connects = 0
        #: Peak queue occupancy, so an evidence record can show the bound was exercised.
        self.peak_queue_depth = 0

    # -- lifecycle -----------------------------------------------------------------------

    def bind(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Bind under a restrictive umask and then set the mode explicitly: the socket must be
        # unreachable by group and other before anything can connect to it.
        previous_umask = os.umask(0o177)
        try:
            sock.bind(self.endpoint_path)
        except OSError as error:
            sock.close()
            raise V4IpcError(MALFORMED, f"bind failed: {error}") from error
        finally:
            os.umask(previous_umask)
        os.chmod(self.endpoint_path, 0o600)
        sock.listen(self.queue_capacity)
        sock.settimeout(self.accept_timeout_s)
        self._sock = sock
        return sock

    def start(self, *, address: DarwinPrivatePathUnixAddress | None = None,
              root: CampaignIpcRoot | None = None, role: str = "broker",
              owner_pid: int = 0, owner_birth_identity: int = 0) -> RegisteredEndpoint:
        """Bind, register, then run the accept loop and the bounded dispatcher."""

        sock = self.bind()
        if address is None or root is None:
            raise V4IpcError(MALFORMED, "an address strategy and campaign root are required")
        endpoint = address.register_endpoint(sock.getsockname(), role=role,
                                             owner_pid=owner_pid,
                                             owner_birth_identity=owner_birth_identity)
        self._accept_thread = threading.Thread(target=self._accept_loop, name="v4-ipc-accept",
                                               daemon=True)
        self._accept_thread.start()
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop,
                                                 name="v4-ipc-dispatch", daemon=True)
        self._dispatch_thread.start()
        return endpoint

    def _accept_loop(self) -> None:
        """Accept connections and hand them to the bounded queue, or refuse them."""

        assert self._sock is not None
        while not self._stop.is_set():
            try:
                connection, _ = self._sock.accept()
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                self._queue.put_nowait(connection)
            except queue.Full:
                self.refused_connects += 1
                self.rejections.append(QUEUE_FULL)
                self._send_error(connection, "", QUEUE_FULL, "queue capacity reached")
                try:
                    connection.close()
                except OSError:
                    pass
            else:
                self.peak_queue_depth = max(self.peak_queue_depth, self._queue.qsize())

    def _dispatch_loop(self) -> None:
        """Take one queued connection at a time and run it on its own short-lived thread.

        Dequeuing is what frees queue capacity: the queue bounds *pending* work, while the
        handler threads are what let two Workers be in flight at once.
        """

        while not self._stop.is_set():
            try:
                connection = self._queue.get(timeout=self.accept_timeout_s)
            except queue.Empty:
                continue
            worker = threading.Thread(target=self._run_connection, args=(connection,),
                                      name="v4-ipc-handler", daemon=True)
            with self._workers_lock:
                self._workers = [item for item in self._workers if item.is_alive()]
                self._workers.append(worker)
            worker.start()

    def _run_connection(self, connection: socket.socket) -> None:
        try:
            self.handle_connection(connection)
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def join_workers(self, timeout_s: float = 5.0) -> None:
        """Wait for in-flight handlers, so a stop is not a race against an open response."""

        with self._workers_lock:
            workers = list(self._workers)
        deadline = time.monotonic() + timeout_s
        for worker in workers:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))

    def _send_error(self, connection: socket.socket, request_id: str, code: str,
                    detail: str) -> None:
        try:
            payload = encode_v4_frame(error_response(request_id, code, detail).to_document(),
                                      max_frame_bytes=self.max_frame_bytes)
            connection.sendall(payload)
        except (OSError, V4IpcError):
            pass

    def handle_connection(self, connection: socket.socket) -> None:
        """Read one frame, validate it, dispatch it, and answer with one frame."""

        try:
            request = self._read_request(connection)
        except V4IpcError as error:
            self.rejections.append(error.code)
            self._send_error(connection, "", error.code, error.detail)
            return
        started = time.monotonic_ns()
        try:
            outcome = self._handler(request)
        except Exception as error:  # noqa: BLE001 - a handler bug is a stable error, not a crash
            self._send_error(connection, request.request_id, INTERNAL,
                             f"{type(error).__name__}: {error}")
            return
        if isinstance(outcome, Mapping) and "error" in outcome:
            error_body = dict(outcome["error"])
            response = V4Response(
                request_id=request.request_id,
                status=str(error_body.get("code", INTERNAL)),
                output_descriptor=None,
                error=error_body,
                timing={"started_monotonic_ns": started,
                        "completed_monotonic_ns": time.monotonic_ns()},
            )
        elif isinstance(outcome, Mapping):
            response = V4Response(
                request_id=request.request_id, status=OK,
                output_descriptor=dict(outcome), error=None,
                timing={"started_monotonic_ns": started,
                        "completed_monotonic_ns": time.monotonic_ns()},
            )
        else:
            self._send_error(connection, request.request_id, INTERNAL,
                             f"handler returned {type(outcome).__name__}")
            return
        try:
            connection.sendall(encode_v4_frame(response.to_document(),
                                               max_frame_bytes=self.max_frame_bytes))
        except (OSError, V4IpcError):
            pass

    def _read_request(self, connection: socket.socket) -> V4Request:
        connection.settimeout(2.0)
        prefix = self._recv_exact(connection, 4)
        size = struct.unpack(">I", prefix)[0]
        if size == 0 or size > self.max_frame_bytes:
            raise V4IpcError(OVERSIZED, f"declared size {size}")
        body = self._recv_exact(connection, size)
        document = _decode_object(body)
        return V4Request.from_document(document)

    @staticmethod
    def _recv_exact(connection: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            part = connection.recv(size - len(result))
            if not part:
                raise V4IpcError(MALFORMED, "connection closed mid-frame")
            result.extend(part)
        return bytes(result)

    def stop(self) -> None:
        self._stop.set()
        for thread in (self._accept_thread, self._dispatch_thread):
            if thread is not None:
                thread.join(timeout=3.0)
        self.join_workers(timeout_s=3.0)
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


# --------------------------------------------------------------------------------------
# client
# --------------------------------------------------------------------------------------


class V4PermissionOnlyClient:
    """A v4 client that connects and sends. It performs no endpoint authentication.

    There is deliberately no `stat()`, no inode comparison, no endpoint receipt, no peer
    credential read and no replacement check: the design removed them, and the tests assert
    their absence rather than merely omitting them.
    """

    def __init__(self, *, endpoint_path, max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES,
                 connect_timeout_s: float = 5.0, io_timeout_s: float = 30.0) -> None:
        self.endpoint_path = str(endpoint_path)
        self.max_frame_bytes = int(max_frame_bytes)
        self.connect_timeout_s = float(connect_timeout_s)
        self.io_timeout_s = float(io_timeout_s)
        self._counter = 0
        self._lock = threading.Lock()

    def next_request_id(self, prefix: str = "r") -> str:
        with self._lock:
            self._counter += 1
            return f"{prefix}-{self._counter:04d}"

    def call(self, operation: str, payload: Mapping[str, object] | None = None, *,
             request_id: str | None = None, timeout_s: float | None = None,
             deadline_monotonic_ns: int | None = None) -> V4Response:
        if operation not in V4_OPERATIONS:
            raise V4IpcError(UNKNOWN_OPERATION, operation)
        budget = self.io_timeout_s if timeout_s is None else float(timeout_s)
        deadline = (time.monotonic_ns() + int(budget * 1_000_000_000)
                    if deadline_monotonic_ns is None else int(deadline_monotonic_ns))
        request = V4Request(
            request_id=request_id or self.next_request_id(),
            operation=operation,
            deadline_monotonic_ns=deadline,
            payload=dict(payload or {}),
        )
        connection = self._connect()
        try:
            connection.sendall(encode_v4_frame(request.to_document(),
                                               max_frame_bytes=self.max_frame_bytes))
            return self._read_response(connection, expected_request_id=request.request_id)
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def _connect(self) -> socket.socket:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.connect_timeout_s)
        try:
            connection.connect(self.endpoint_path)
        except OSError as error:
            connection.close()
            raise V4IpcError(MALFORMED, f"connect failed: {error}") from error
        connection.settimeout(self.io_timeout_s)
        return connection

    def _read_response(self, connection: socket.socket,
                       *, expected_request_id: str) -> V4Response:
        prefix = self._recv_exact(connection, 4)
        size = struct.unpack(">I", prefix)[0]
        if size == 0 or size > self.max_frame_bytes:
            raise V4IpcError(OVERSIZED, f"declared size {size}")
        document = _decode_object(self._recv_exact(connection, size))
        response = V4Response.from_document(document)
        if response.request_id and response.request_id != expected_request_id:
            raise V4IpcError(INVALID_REQUEST, "response request_id does not match")
        return response

    @staticmethod
    def _recv_exact(connection: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            part = connection.recv(size - len(result))
            if not part:
                raise V4IpcError(MALFORMED, "connection closed mid-frame")
            result.extend(part)
        return bytes(result)

    def send_raw(self, payload: bytes, *, timeout_s: float = 5.0) -> V4Response | None:
        """Send raw bytes, for the negative protocol tests. Returns None when the peer refuses."""

        connection = self._connect()
        try:
            connection.settimeout(timeout_s)
            connection.sendall(payload)
            try:
                return self._read_response(connection, expected_request_id="")
            except V4IpcError:
                return None
        except OSError:
            return None
        finally:
            try:
                connection.close()
            except OSError:
                pass


def serialize_operations() -> Sequence[str]:
    """The allowlist as a stable sequence, for manifests and evidence."""

    return tuple(sorted(V4_OPERATIONS))
