"""Authenticated Web-to-fixed-Coordinator control; no Worker execution authority.

The endpoint acknowledges the Coordinator's existing durable stop transition.
Acknowledgement is not a recovery or batch cleanup receipt. The production
composition remains responsible for controller/Worker/Broker containment.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import sys
import threading

from so101_demo.runtime.parallel_ipc import IpcError, encode_frame, receive_frame
from so101_demo.runtime.unix_address import (
    DARWIN_SUN_PATH_CAPACITY_BYTES,
    LINUX_SUN_PATH_CAPACITY_BYTES,
)

from .contracts import BatchKindV2, BatchRequest, BatchRequestV2


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_UNSIGNED_FIELDS = {
    "schema_version", "command_id", "campaign_id", "batch_id",
    "coordinator_epoch", "operation",
}
_REQUEST_FIELDS = _UNSIGNED_FIELDS | {"request_sha256", "control_token"}


#: ``sun_path`` capacity including the terminating NUL; see ``runtime.unix_address``.
_SUN_PATH_CAPACITY_BYTES = (
    DARWIN_SUN_PATH_CAPACITY_BYTES if sys.platform == "darwin" else LINUX_SUN_PATH_CAPACITY_BYTES
)

#: The Linux indirection that pins a bound socket's parent directory. Darwin has no ``bindat`` and
#: ``/dev/fd/<dirfd>/<name>`` returns ENOENT there (proved in the retained probe recorded as
#: CP-UQ226), so the endpoint must be bound by its own path instead.
_PROC_FD_DIRECTORY = Path("/proc/self/fd")


def _bind_target(path: Path, parent_fd: int) -> str:
    """The address to bind, or a refusal when this platform cannot address it.

    A path that does not fit ``sun_path`` is refused by name rather than truncated: binding a
    truncated path would create the endpoint somewhere else entirely while reporting success.
    """
    if _PROC_FD_DIRECTORY.is_dir():
        return f"{_PROC_FD_DIRECTORY}/{parent_fd}/{path.name}"
    if len(os.fsencode(path)) >= _SUN_PATH_CAPACITY_BYTES:
        raise WebControlError("CONTROL_SOCKET_PATH_TOO_LONG")
    return str(path)


#: Darwin's peer-credential request: ``getsockopt(SOL_LOCAL, LOCAL_PEERCRED, struct xucred)``.
#: Probed on this host: the call returns 76 bytes, ``cr_version`` 0 at offset 0 and ``cr_uid`` at
#: offset 4. Linux's ``SO_PEERCRED`` does not exist here at all, so the check has to be written per
#: platform instead of assuming one.
_DARWIN_SOL_LOCAL = 0
_DARWIN_LOCAL_PEERCRED = 1
_DARWIN_XUCRED_BYTES = 76
_DARWIN_XUCRED_VERSION = 0
_DARWIN_XUCRED_UID_OFFSET = 4


def _peer_uid(connection: socket.socket) -> int:
    """The uid of the connected peer, or a refusal - never a skipped check."""
    if sys.platform == "darwin":
        raw = connection.getsockopt(
            _DARWIN_SOL_LOCAL, _DARWIN_LOCAL_PEERCRED, _DARWIN_XUCRED_BYTES
        )
        if len(raw) < _DARWIN_XUCRED_UID_OFFSET + 4:
            raise WebControlError("CONTROL_PEER_UID")
        if struct.unpack_from("<I", raw, 0)[0] != _DARWIN_XUCRED_VERSION:
            raise WebControlError("CONTROL_PEER_UID")
        return struct.unpack_from("<I", raw, _DARWIN_XUCRED_UID_OFFSET)[0]
    if sys.platform.startswith("linux"):
        _, uid, _ = struct.unpack(
            "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        return uid
    raise WebControlError("CONTROL_PEER_UID_UNSUPPORTED")


class WebControlError(RuntimeError):
    """A peer or endpoint violates the fixed authenticated control contract."""


class FixedCoordinatorControlServer:
    """Own one private Unix endpoint bound to a live upstream Coordinator epoch."""

    def __init__(self, *, coordinator, campaign_id: str, control_token: str, path: Path):
        # The closed schema-1 wire serves both the retained v1 execution contract and
        # legitimate v2 fixed batches. Adaptive pools keep their own control path.
        request = coordinator.request
        if isinstance(request, BatchRequestV2):
            if request.batch_kind not in {BatchKindV2.FIRST_PASS, BatchKindV2.FULL_RESTART_RETRY}:
                raise WebControlError("FIXED_COORDINATOR_REQUEST_REQUIRED")
        elif not isinstance(request, BatchRequest):
            raise WebControlError("FIXED_COORDINATOR_REQUEST_REQUIRED")
        if not isinstance(campaign_id, str) or _IDENTIFIER.fullmatch(campaign_id) is None:
            raise WebControlError("CAMPAIGN_ID_INVALID")
        if not isinstance(control_token, str) or _TOKEN.fullmatch(control_token) is None:
            raise WebControlError("CONTROL_TOKEN_INVALID")
        self.coordinator = coordinator
        self.campaign_id = campaign_id
        self.batch_id = coordinator.request.batch_id
        self.coordinator_epoch = coordinator.journal.coordinator_epoch
        self.path = Path(path)
        root = coordinator.request.evidence_root
        if (
            not self.path.is_absolute()
            or self.path != self.path.resolve(strict=False)
            or not self.path.is_relative_to(root)
        ):
            raise WebControlError("CONTROL_SOCKET_OUTSIDE_BATCH_ROOT")
        self._token = control_token
        self._closed = threading.Event()
        self._thread = None
        self._commands = {}
        self._failure = None
        self._parent_fd = os.open(
            self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._bound_identity = None
        try:
            parent = os.fstat(self._parent_fd)
            if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
                raise WebControlError("CONTROL_SOCKET_DIRECTORY_MODE")
            # bind never unlinks an existing endpoint or accepts an alias root.
            self._socket.bind(_bind_target(self.path, self._parent_fd))
            value = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
            self._bound_identity = (value.st_dev, value.st_ino)
            os.chmod(self.path.name, 0o600, dir_fd=self._parent_fd)
            self._socket.listen(8)
            self._socket.settimeout(0.1)
        except BaseException:
            self.close()
            raise

    def start(self) -> None:
        if self._thread is not None or self._closed.is_set():
            raise WebControlError("CONTROL_SERVER_ALREADY_STARTED_OR_CLOSED")
        self._thread = threading.Thread(
            target=self._serve, name="fixed-coordinator-web-control", daemon=True
        )
        self._thread.start()

    def check_health(self) -> None:
        if self._failure is not None:
            raise WebControlError("CONTROL_SERVER_FAILED") from self._failure

    def _validate(self, request: dict) -> None:
        if set(request) != _REQUEST_FIELDS:
            raise WebControlError("CONTROL_REQUEST_SCHEMA")
        expected = {
            "schema_version": 1, "campaign_id": self.campaign_id,
            "batch_id": self.batch_id, "coordinator_epoch": self.coordinator_epoch,
        }
        for name, value in expected.items():
            if type(request[name]) is not type(value) or request[name] != value:
                raise WebControlError("CONTROL_REQUEST_IDENTITY")
        command_id = request["command_id"]
        if not isinstance(command_id, str) or _IDENTIFIER.fullmatch(command_id) is None:
            raise WebControlError("COMMAND_ID_INVALID")
        if (
            not isinstance(request["operation"], str)
            or request["operation"] not in {"STATUS", "CANCEL_BATCH"}
        ):
            raise WebControlError("CONTROL_OPERATION_INVALID")
        token = request["control_token"]
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            raise WebControlError("CONTROL_AUTHENTICATION_FAILED")
        if not secrets.compare_digest(token, self._token):
            raise WebControlError("CONTROL_AUTHENTICATION_FAILED")
        unsigned = {name: request[name] for name in _UNSIGNED_FIELDS}
        payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        if request["request_sha256"] != hashlib.sha256(payload).hexdigest():
            raise WebControlError("CONTROL_REQUEST_HASH")
        if self.coordinator.journal.coordinator_epoch != self.coordinator_epoch:
            raise WebControlError("CONTROL_COORDINATOR_EPOCH_CHANGED")
        previous = self._commands.get(command_id)
        if previous is not None and previous != request["request_sha256"]:
            raise WebControlError("CONTROL_COMMAND_ID_CONFLICT")
        if previous is None and len(self._commands) >= 4096:
            raise WebControlError("CONTROL_COMMAND_LIMIT")

    def _reply(self, request: dict) -> dict:
        self._validate(request)
        self._commands[request["command_id"]] = request["request_sha256"]
        if request["operation"] == "CANCEL_BATCH":
            # This public method fsyncs BATCH_STOPPING before acknowledgement.
            snapshot = self.coordinator.request_stop(reason="WEB_CANCEL_REQUESTED")
        else:
            snapshot = self.coordinator.snapshot()
        state = (
            "TERMINAL" if snapshot.summary.batch_terminal
            else "STOPPING" if snapshot.terminal_reason else "RUNNING"
        )
        return {
            **{name: request[name] for name in _UNSIGNED_FIELDS},
            "request_sha256": request["request_sha256"], "state": state,
            "batch_terminal": snapshot.summary.batch_terminal,
            "batch_cleanup_complete": snapshot.summary.batch_cleanup_complete,
            # Never derive physical/process/domain cleanup from stop or exit.
            "owned_descendants_gone": False,
            "assigned_ros_domains_clear": False,
            "cleanup_receipt_sha256": None,
        }

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                connection, _ = self._socket.accept()
            except TimeoutError:
                continue
            except OSError as error:
                if not self._closed.is_set():
                    self._failure = error
                return
            with connection:
                try:
                    if _peer_uid(connection) != os.getuid():
                        raise WebControlError("CONTROL_PEER_UID")
                    request = receive_frame(connection, deadline_s=0.5, max_frame_bytes=65536)
                    reply = self._reply(request)
                    connection.settimeout(0.5)
                    connection.sendall(encode_frame(reply, max_frame_bytes=65536))
                except (IpcError, WebControlError, ConnectionError, TimeoutError):
                    # Reject without reflecting credentials or granting an ACK.
                    continue
                except Exception as error:
                    self._failure = error
                    return

    def close(self) -> None:
        if self._parent_fd is None:
            return
        self._closed.set()
        self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            if self._thread.is_alive():
                raise WebControlError("CONTROL_SERVER_CLOSE_TIMEOUT")
        try:
            if self._bound_identity is not None:
                try:
                    value = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    value = None
                if value is not None and (value.st_dev, value.st_ino) == self._bound_identity:
                    os.unlink(self.path.name, dir_fd=self._parent_fd)
        finally:
            if self._parent_fd is not None:
                os.close(self._parent_fd)
                self._parent_fd = None
