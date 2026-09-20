"""The macOS fixed-Coordinator control endpoint: one wire, one set of validators.

The Linux path serves this wire from :class:`parallel_batch.web_control.FixedCoordinatorControlServer`,
which is built around a `BatchRequest`/`BatchRequestV2` coordinator with a durable journal. The macOS
campaign is a v4-native composition with no such journal, so it needs its own endpoint - but not its
own *wire*. Everything that defines the contract is reused from ``web_control``: the request field
set, the identifier and token patterns, the unsigned-field list the request hash is taken over, the
frame codec, the peer-credential read and the bind rule. Two implementations of one wire is a real
drift risk, so a teleop-side parity test pins this module's fields and refusals against
``expert_validation.control``; what is genuinely new here is only *what the reply reports*.

That reply stays as modest as the Linux server's, for the same reason: an acknowledgement of a durable
stop transition is not a cleanup receipt. ``state``, ``batch_terminal`` and ``batch_cleanup_complete``
come from the campaign's own state provider. ``owned_descendants_gone``,
``assigned_ros_domains_clear`` and ``cleanup_receipt_sha256`` are reported as the campaign can prove
them and default to False/False/None - never derived from "the stop call returned".
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import threading
from typing import Callable, Mapping

from so101_demo.runtime.parallel_ipc import IpcError, encode_frame, receive_frame

from .web_control import (
    _IDENTIFIER,
    _REQUEST_FIELDS,
    _TOKEN,
    _UNSIGNED_FIELDS,
    WebControlError,
    _bind_target,
    _peer_uid,
)

#: The same closed frame limit both sides use.
MAX_FRAME_BYTES = 65_536

#: One command id may appear once; the table is bounded so a peer cannot grow it without limit.
MAX_COMMANDS = 4096


class MacosControlError(RuntimeError):
    """The endpoint or its peer violated the closed control contract."""


class MacosFixedControlEndpoint:
    """Serve the closed control wire for one macOS campaign, from that campaign's own state.

    ``state_provider`` is consulted for every reply and must return at least ``state``,
    ``batch_terminal`` and ``batch_cleanup_complete``. ``request_stop`` is called for
    ``CANCEL_BATCH`` and must not return before the campaign's stop transition is durable: the
    acknowledgement is what the service acts on.
    """

    def __init__(
        self,
        *,
        campaign_id: str,
        batch_id: str,
        coordinator_epoch: int,
        path: Path,
        control_token: str,
        state_provider: Callable[[], Mapping[str, object]],
        request_stop: Callable[[str], None],
    ) -> None:
        if not isinstance(campaign_id, str) or _IDENTIFIER.fullmatch(campaign_id) is None:
            raise MacosControlError("CAMPAIGN_ID_INVALID")
        if not isinstance(batch_id, str) or not batch_id:
            raise MacosControlError("BATCH_ID_INVALID")
        if type(coordinator_epoch) is not int or coordinator_epoch <= 0:
            raise MacosControlError("COORDINATOR_EPOCH_INVALID")
        if not isinstance(control_token, str) or _TOKEN.fullmatch(control_token) is None:
            raise MacosControlError("CONTROL_TOKEN_INVALID")
        if not callable(state_provider) or not callable(request_stop):
            raise MacosControlError("CONTROL_STATE_PROVIDER_REQUIRED")
        self.campaign_id = campaign_id
        self.batch_id = batch_id
        self.coordinator_epoch = coordinator_epoch
        self.path = Path(path)
        self._token = control_token
        self._state_provider = state_provider
        self._request_stop = request_stop
        self._commands: dict[str, str] = {}
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None
        self._parent_fd = -1
        self._socket: socket.socket | None = None
        self._bound_identity: tuple[int, int] | None = None

    # -- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None or self._closed.is_set():
            raise MacosControlError("CONTROL_SERVER_ALREADY_STARTED_OR_CLOSED")
        # The service names the endpoint inside the batch root and creates the batch root, not this
        # directory; the first live launch died here after the service had already recorded the start.
        # It is created private, and the checks below still verify ownership and mode rather than
        # trusting that mkdir did what was asked.
        if not self.path.parent.is_dir():
            self.path.parent.mkdir(mode=0o700, parents=True)
        self._parent_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            parent = os.fstat(self._parent_fd)
            if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
                raise MacosControlError("CONTROL_SOCKET_DIRECTORY_MODE")
            # Never replaces an existing endpoint: bind refuses a path that is already there.
            self._socket.bind(_bind_target(self.path, self._parent_fd))
            value = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
            self._bound_identity = (value.st_dev, value.st_ino)
            os.chmod(self.path.name, 0o600, dir_fd=self._parent_fd)
            self._socket.listen(8)
            self._socket.settimeout(0.1)
        except BaseException:
            self.close()
            raise
        self._thread = threading.Thread(target=self._serve, name="macos-fixed-control", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._parent_fd >= 0:
            # Only the socket this endpoint bound is unlinked, and only if it is still that socket.
            try:
                value = os.stat(self.path.name, dir_fd=self._parent_fd, follow_symlinks=False)
                if self._bound_identity is not None and (
                    value.st_dev, value.st_ino
                ) == self._bound_identity:
                    os.unlink(self.path.name, dir_fd=self._parent_fd)
            except (FileNotFoundError, OSError):
                pass
            os.close(self._parent_fd)
            self._parent_fd = -1

    def check_health(self) -> None:
        if self._failure is not None:
            raise MacosControlError("CONTROL_SERVER_FAILED") from self._failure

    def __enter__(self) -> "MacosFixedControlEndpoint":
        self.start()
        return self

    def __exit__(self, *_exception) -> None:
        self.close()

    # -- wire ----------------------------------------------------------------------------

    def _validate(self, request: dict) -> None:
        if set(request) != _REQUEST_FIELDS:
            raise MacosControlError("CONTROL_REQUEST_SCHEMA")
        expected = {
            "schema_version": 1,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "coordinator_epoch": self.coordinator_epoch,
        }
        for name, value in expected.items():
            if type(request[name]) is not type(value) or request[name] != value:
                raise MacosControlError("CONTROL_REQUEST_IDENTITY")
        if _IDENTIFIER.fullmatch(str(request["command_id"])) is None:
            raise MacosControlError("COMMAND_ID_INVALID")
        if request["operation"] not in {"STATUS", "CANCEL_BATCH"}:
            raise MacosControlError("CONTROL_OPERATION_INVALID")
        token = request["control_token"]
        if not isinstance(token, str) or _TOKEN.fullmatch(token) is None:
            raise MacosControlError("CONTROL_AUTHENTICATION_FAILED")
        if not secrets.compare_digest(token, self._token):
            raise MacosControlError("CONTROL_AUTHENTICATION_FAILED")
        unsigned = {name: request[name] for name in _UNSIGNED_FIELDS}
        payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        if request["request_sha256"] != hashlib.sha256(payload).hexdigest():
            raise MacosControlError("CONTROL_REQUEST_HASH")
        previous = self._commands.get(request["command_id"])
        if previous is not None and previous != request["request_sha256"]:
            raise MacosControlError("CONTROL_COMMAND_ID_CONFLICT")
        if previous is None and len(self._commands) >= MAX_COMMANDS:
            raise MacosControlError("CONTROL_COMMAND_LIMIT")

    def reply_for(self, request: dict) -> dict:
        """Validate one request and answer it; the whole reply shape is pinned by parity tests."""
        self._validate(request)
        self._commands[request["command_id"]] = request["request_sha256"]
        if request["operation"] == "CANCEL_BATCH":
            # The provider performs the durable stop and returns only once it is recorded.
            self._request_stop(str(request["command_id"]))
        state = dict(self._state_provider())
        for name in ("state", "batch_terminal", "batch_cleanup_complete"):
            if name not in state:
                raise MacosControlError("CONTROL_STATE_INCOMPLETE")
        return {
            **{name: request[name] for name in _UNSIGNED_FIELDS},
            "request_sha256": request["request_sha256"],
            "state": state["state"],
            "batch_terminal": bool(state["batch_terminal"]),
            "batch_cleanup_complete": bool(state["batch_cleanup_complete"]),
            # Only what the campaign can prove. A stop acknowledgement is never a cleanup receipt.
            "owned_descendants_gone": bool(state.get("owned_descendants_gone", False)),
            "assigned_ros_domains_clear": bool(state.get("assigned_ros_domains_clear", False)),
            "cleanup_receipt_sha256": state.get("cleanup_receipt_sha256"),
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
                        raise MacosControlError("CONTROL_PEER_UID")
                    request = receive_frame(
                        connection, deadline_s=0.5, max_frame_bytes=MAX_FRAME_BYTES
                    )
                    reply = self.reply_for(request)
                    connection.settimeout(0.5)
                    connection.sendall(encode_frame(reply, max_frame_bytes=MAX_FRAME_BYTES))
                except (IpcError, MacosControlError, WebControlError, ConnectionError, TimeoutError):
                    # Reject without reflecting credentials or granting an acknowledgement.
                    continue
                except Exception as error:  # noqa: BLE001 - recorded, then refused
                    self._failure = error
                    continue
