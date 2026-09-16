"""Authenticated fixed and adaptive execution-control projections."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import socket
import stat
from typing import Callable, Literal, Mapping

from .coordinator import CoordinatorBinding
from .process_owner import ExecutionProcessOwner, OwnedAdaptiveWrapper


_SHA256_LENGTH = 64
_REQUEST_FIELDS = {
    "schema_version",
    "command_id",
    "campaign_id",
    "batch_id",
    "coordinator_epoch",
    "operation",
}
_REPLY_FIELDS = _REQUEST_FIELDS | {
    "request_sha256",
    "state",
    "batch_terminal",
    "batch_cleanup_complete",
    "owned_descendants_gone",
    "assigned_ros_domains_clear",
    "cleanup_receipt_sha256",
}


class ControlProtocolError(RuntimeError):
    """A control peer violated the closed framing or identity contract."""


class CleanupNotAuthorized(RuntimeError):
    """Upstream cleanup evidence is insufficient for a lifecycle transition."""


def _canonical_bytes(document: Mapping) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(document: Mapping) -> str:
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def encode_frame(document: Mapping, *, max_frame_bytes: int = 65_536) -> bytes:
    payload = _canonical_bytes(document)
    if len(payload) > max_frame_bytes:
        raise ControlProtocolError("FRAME_TOO_LARGE")
    return len(payload).to_bytes(4, "big") + payload


def decode_frame(frame: bytes, *, max_frame_bytes: int = 65_536) -> dict:
    if len(frame) < 4:
        raise ControlProtocolError("PARTIAL_FRAME")
    length = int.from_bytes(frame[:4], "big")
    if length > max_frame_bytes:
        raise ControlProtocolError("FRAME_TOO_LARGE")
    if len(frame) != length + 4:
        raise ControlProtocolError("PARTIAL_FRAME")
    try:
        document = json.loads(frame[4:].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlProtocolError("FRAME_JSON_INVALID") from error
    if not isinstance(document, dict):
        raise ControlProtocolError("FRAME_MAPPING_REQUIRED")
    return document


@dataclass(frozen=True, slots=True)
class CoordinatorControlRequest:
    schema_version: int
    command_id: str
    campaign_id: str
    batch_id: str
    coordinator_epoch: int
    operation: Literal["STATUS", "CANCEL_BATCH"]
    request_sha256: str


@dataclass(frozen=True, slots=True)
class FixedControlStatus:
    command_id: str
    campaign_id: str
    batch_id: str
    coordinator_epoch: int
    operation: str
    state: str
    batch_terminal: bool
    batch_cleanup_complete: bool
    owned_descendants_gone: bool
    assigned_ros_domains_clear: bool
    cleanup_receipt_sha256: str | None


@dataclass(frozen=True, slots=True)
class BatchCleanupAuthorization:
    batch_id: str
    coordinator_epoch: int
    batch_cleanup_complete: bool
    owned_descendants_gone: bool
    assigned_ros_domains_clear: bool
    receipt_sha256: str


def _recv_exact(peer: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = peer.recv(length - len(chunks))
        if not chunk:
            raise ControlProtocolError("PARTIAL_FRAME")
        chunks.extend(chunk)
    return bytes(chunks)


class CoordinatorControlClient:
    def __init__(
        self,
        *,
        transport: Callable[[CoordinatorBinding, dict, float], dict] | None = None,
        timeout_s: float = 2.0,
        max_frame_bytes: int = 65_536,
    ) -> None:
        self._transport = transport or self._socket_transport
        self._timeout_s = timeout_s
        self._max_frame_bytes = max_frame_bytes

    def status(self, *, command_id: str, binding: CoordinatorBinding) -> FixedControlStatus:
        return self._request("STATUS", command_id, binding)

    def cancel(self, *, command_id: str, binding: CoordinatorBinding) -> FixedControlStatus:
        return self._request("CANCEL_BATCH", command_id, binding)

    def _request(
        self, operation: Literal["STATUS", "CANCEL_BATCH"], command_id: str, binding: CoordinatorBinding
    ) -> FixedControlStatus:
        if not isinstance(command_id, str) or not command_id:
            raise ControlProtocolError("COMMAND_ID_INVALID")
        unsigned = {
            "schema_version": 1,
            "command_id": command_id,
            "campaign_id": binding.campaign_id,
            "batch_id": binding.batch_id,
            "coordinator_epoch": binding.coordinator_epoch,
            "operation": operation,
        }
        request_hash = _sha256(unsigned)
        wire_request = {**unsigned, "request_sha256": request_hash}
        reply = self._transport(binding, wire_request, self._timeout_s)
        return self._validate_reply(reply, wire_request)

    def _validate_reply(self, reply: object, request: dict) -> FixedControlStatus:
        if not isinstance(reply, dict) or set(reply) != _REPLY_FIELDS:
            raise ControlProtocolError("CONTROL_REPLY_SCHEMA")
        checks = (
            (
                type(reply["schema_version"]) is int and reply["schema_version"] == 1,
                "CONTROL_SCHEMA_VERSION",
            ),
            (reply["command_id"] == request["command_id"], "COMMAND_ID_MISMATCH"),
            (reply["campaign_id"] == request["campaign_id"], "CAMPAIGN_ID_MISMATCH"),
            (reply["batch_id"] == request["batch_id"], "BATCH_ID_MISMATCH"),
            (
                type(reply["coordinator_epoch"]) is int
                and reply["coordinator_epoch"] == request["coordinator_epoch"],
                "COORDINATOR_EPOCH_MISMATCH",
            ),
            (reply["operation"] == request["operation"], "CONTROL_OPERATION_MISMATCH"),
            (reply["request_sha256"] == request["request_sha256"], "REQUEST_HASH_MISMATCH"),
        )
        for valid, message in checks:
            if not valid:
                raise ControlProtocolError(message)
        for field in (
            "batch_terminal",
            "batch_cleanup_complete",
            "owned_descendants_gone",
            "assigned_ros_domains_clear",
        ):
            if not isinstance(reply[field], bool):
                raise ControlProtocolError("CONTROL_REPLY_SCHEMA")
        if not isinstance(reply["state"], str) or not reply["state"]:
            raise ControlProtocolError("CONTROL_REPLY_SCHEMA")
        receipt = reply["cleanup_receipt_sha256"]
        if receipt is not None and (
            not isinstance(receipt, str)
            or len(receipt) != _SHA256_LENGTH
            or any(character not in "0123456789abcdef" for character in receipt)
        ):
            raise ControlProtocolError("CLEANUP_RECEIPT_INVALID")
        return FixedControlStatus(
            command_id=reply["command_id"],
            campaign_id=reply["campaign_id"],
            batch_id=reply["batch_id"],
            coordinator_epoch=reply["coordinator_epoch"],
            operation=reply["operation"],
            state=reply["state"],
            batch_terminal=reply["batch_terminal"],
            batch_cleanup_complete=reply["batch_cleanup_complete"],
            owned_descendants_gone=reply["owned_descendants_gone"],
            assigned_ros_domains_clear=reply["assigned_ros_domains_clear"],
            cleanup_receipt_sha256=receipt,
        )

    def _socket_transport(
        self, binding: CoordinatorBinding, request: dict, timeout_s: float
    ) -> dict:
        wire = {**request, "control_token": binding.control_token}
        frame = encode_frame(wire, max_frame_bytes=self._max_frame_bytes)
        try:
            parent_fd = os.open(
                binding.control_socket.parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as error:
            raise ControlProtocolError("COORDINATOR_SOCKET_UNAVAILABLE") from error
        try:
            directory_mode = stat.S_IMODE(os.fstat(parent_fd).st_mode)
            try:
                socket_stat = os.stat(
                    binding.control_socket.name, dir_fd=parent_fd, follow_symlinks=False
                )
            except OSError as error:
                raise ControlProtocolError("COORDINATOR_SOCKET_UNAVAILABLE") from error
            if (
                directory_mode != 0o700
                or not stat.S_ISSOCK(socket_stat.st_mode)
                or stat.S_IMODE(socket_stat.st_mode) != 0o600
            ):
                raise ControlProtocolError("COORDINATOR_SOCKET_MODE")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.settimeout(timeout_s)
                # Pin the actual bound parent, as upstream parallel IPC does.
                # The socket remains inside batch_root even beyond sun_path.
                peer.connect(f"/proc/self/fd/{parent_fd}/{binding.control_socket.name}")
                peer.sendall(frame)
                # The upstream frame reader checks EOF for a one-request frame.
                peer.shutdown(socket.SHUT_WR)
                header = _recv_exact(peer, 4)
                length = int.from_bytes(header, "big")
                if length > self._max_frame_bytes:
                    raise ControlProtocolError("FRAME_TOO_LARGE")
                payload = _recv_exact(peer, length)
        except TimeoutError as error:
            raise ControlProtocolError("CONTROL_ACK_TIMEOUT") from error
        except OSError as error:
            raise ControlProtocolError("COORDINATOR_SOCKET_DISCONNECTED") from error
        finally:
            os.close(parent_fd)
        return decode_frame(header + payload, max_frame_bytes=self._max_frame_bytes)


def authorize_coordinator_stop(
    status: FixedControlStatus, binding: CoordinatorBinding
) -> BatchCleanupAuthorization:
    if status.batch_id != binding.batch_id or status.coordinator_epoch != binding.coordinator_epoch:
        raise CleanupNotAuthorized("CONTROL_BINDING_MISMATCH")
    if not status.batch_terminal:
        raise CleanupNotAuthorized("BATCH_NOT_TERMINAL")
    if not status.batch_cleanup_complete:
        raise CleanupNotAuthorized("BATCH_CLEANUP_INCOMPLETE")
    if not status.owned_descendants_gone:
        raise CleanupNotAuthorized("OWNED_DESCENDANTS_REMAIN")
    if not status.assigned_ros_domains_clear:
        raise CleanupNotAuthorized("ROS_DOMAINS_NOT_CLEAR")
    if status.cleanup_receipt_sha256 is None:
        raise CleanupNotAuthorized("CLEANUP_RECEIPT_INVALID")
    return BatchCleanupAuthorization(
        batch_id=status.batch_id,
        coordinator_epoch=status.coordinator_epoch,
        batch_cleanup_complete=True,
        owned_descendants_gone=True,
        assigned_ros_domains_clear=True,
        receipt_sha256=status.cleanup_receipt_sha256,
    )


@dataclass(frozen=True, slots=True)
class AdaptiveStatus:
    wrapper_pid: int
    wrapper_started_ticks: int
    runner_pid: int | None
    batch_id: str
    state: str
    generation_cleanup_complete: bool
    batch_terminal: bool
    batch_cleanup_complete: bool


class AdaptiveWrapperControl:
    def __init__(
        self,
        owner: ExecutionProcessOwner,
        status_reader: Callable[[], AdaptiveStatus],
    ) -> None:
        self._owner = owner
        self._status_reader = status_reader

    def status(self, owned: OwnedAdaptiveWrapper) -> AdaptiveStatus:
        status = self._status_reader()
        if not isinstance(status, AdaptiveStatus):
            raise ControlProtocolError("ADAPTIVE_STATUS_SCHEMA")
        if (
            status.wrapper_pid != owned.pid
            or status.wrapper_started_ticks != owned.started_ticks
            or status.batch_id != owned.batch_id
            or status.runner_pid != owned.runner_pid
        ):
            raise ControlProtocolError("ADAPTIVE_WRAPPER_IDENTITY_MISMATCH")
        return status

    def cancel(self, owned: OwnedAdaptiveWrapper) -> None:
        self.status(owned)
        self._owner.request_cancel(owned)

    def await_next_generation(self, owned: OwnedAdaptiveWrapper) -> AdaptiveStatus:
        status = self.status(owned)
        if status.state != "DEGRADING":
            raise CleanupNotAuthorized("ADAPTIVE_NOT_DEGRADING")
        if not status.generation_cleanup_complete:
            raise CleanupNotAuthorized("GENERATION_CLEANUP_INCOMPLETE")
        return status

    def authorize_terminal(self, owned: OwnedAdaptiveWrapper) -> AdaptiveStatus:
        status = self.status(owned)
        if not status.batch_terminal or not status.batch_cleanup_complete:
            raise CleanupNotAuthorized("ADAPTIVE_BATCH_CLEANUP_INCOMPLETE")
        return status
