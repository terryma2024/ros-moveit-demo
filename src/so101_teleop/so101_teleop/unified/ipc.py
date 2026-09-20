"""Closed, versioned IPC protocol between the web process and the ROS child.

The protocol accepts only allowlisted operations with strongly typed payloads. Requests
never carry a shell command, an executable path, a Python expression, or a ROS method
name. Oversized, expired, unknown-version, unknown-operation and non-finite documents are
refused before any payload is dispatched.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PROTOCOL_VERSION = 1
DEFAULT_MAX_BYTES = 64 * 1024

MOTION_OPERATIONS = (
    "execute_arm",
    "gripper",
    "home",
    "attachment",
    "scene_repair",
    "simulation_reset",
    "camera_preset",
    "parameters",
    "workflow",
)
OBSERVE_OPERATIONS = ("observe", "plan_joints", "plan_tcp")
ALLOWED_OPERATIONS = OBSERVE_OPERATIONS + MOTION_OPERATIONS
#: Operations that must carry a dispatch token; observe-only reads must not.
TOKEN_REQUIRED_OPERATIONS = MOTION_OPERATIONS


class IpcProtocolError(ValueError):
    """Raised when a document is outside the frozen protocol."""


class DispatchTokenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=1)
    child_id: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)
    execution_generation: int = Field(ge=0)
    deadline_ns: int = Field(ge=0)
    revocation_revision: int = Field(ge=0)


class IpcRequest(BaseModel):
    """One allowlisted request. ``extra='forbid'`` closes the schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    operation: Literal[
        "observe",
        "plan_joints",
        "plan_tcp",
        "execute_arm",
        "gripper",
        "home",
        "attachment",
        "scene_repair",
        "simulation_reset",
        "camera_preset",
        "parameters",
        "workflow",
    ]
    command_id: str = Field(min_length=1, max_length=200)
    deadline_ns: int = Field(ge=1)
    service_epoch: str = Field(min_length=1, max_length=200)
    runtime_id: str = Field(min_length=1, max_length=200)
    service_token: str = Field(min_length=1, max_length=512)
    token: DispatchTokenModel | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _payload_is_finite(cls, value: dict[str, Any]) -> dict[str, Any]:
        for item in _walk(value):
            if isinstance(item, float) and (item != item or item in (float("inf"), float("-inf"))):
                raise ValueError("IPC_PAYLOAD_NOT_FINITE")
        return value


class IpcReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    code: str = "OK"
    ack: dict[str, Any] | None = None
    terminal: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class SafetyPacket(BaseModel):
    """The independent cancellation channel's own closed schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = PROTOCOL_VERSION
    operation: Literal["revoke"]
    service_epoch: str = Field(min_length=1)
    owner: dict[str, Any]
    claim: str = Field(min_length=1, max_length=512)
    target: dict[str, Any]
    reason: str = "browser_cancel"


def _walk(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def decode_request(raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES, now_ns: int) -> IpcRequest:
    """Decode one request document, refusing everything outside the frozen schema."""
    if len(raw) > max_bytes:
        raise IpcProtocolError(f"IPC_OVERSIZE: {len(raw)} > {max_bytes}")
    try:
        document = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except UnicodeDecodeError as error:
        raise IpcProtocolError(f"IPC_NOT_UTF8: {error}") from error
    except json.JSONDecodeError as error:
        raise IpcProtocolError(f"IPC_NOT_JSON: {error}") from error
    if not isinstance(document, dict):
        raise IpcProtocolError("IPC_NOT_AN_OBJECT")
    version = document.get("version")
    if version != PROTOCOL_VERSION:
        raise IpcProtocolError(f"IPC_VERSION_UNSUPPORTED: {version!r}")
    try:
        request = IpcRequest(**document)
    except ValidationError as error:
        raise IpcProtocolError(f"IPC_SCHEMA_REJECTED: {error.errors()[:1]}") from error
    if request.deadline_ns <= now_ns:
        raise IpcProtocolError(f"IPC_DEADLINE_EXPIRED: {request.deadline_ns} <= {now_ns}")
    if request.operation in TOKEN_REQUIRED_OPERATIONS and request.token is None:
        raise IpcProtocolError(f"IPC_TOKEN_REQUIRED: {request.operation}")
    if request.token is not None and request.token.runtime_id != request.runtime_id:
        raise IpcProtocolError("IPC_RUNTIME_MISMATCH")
    return request


def decode_safety_packet(raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> SafetyPacket:
    if len(raw) > max_bytes:
        raise IpcProtocolError(f"IPC_OVERSIZE: {len(raw)} > {max_bytes}")
    try:
        document = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IpcProtocolError(f"IPC_SAFETY_NOT_JSON: {error}") from error
    if not isinstance(document, dict):
        raise IpcProtocolError("IPC_NOT_AN_OBJECT")
    if document.get("version") != PROTOCOL_VERSION:
        raise IpcProtocolError(f"IPC_VERSION_UNSUPPORTED: {document.get('version')!r}")
    try:
        return SafetyPacket(**document)
    except ValidationError as error:
        raise IpcProtocolError(f"IPC_SAFETY_SCHEMA_REJECTED: {error.errors()[:1]}") from error


def _reject_constant(name: str):
    raise IpcProtocolError(f"IPC_NOT_FINITE: {name}")


def encode(document: BaseModel) -> bytes:
    return (document.model_dump_json() + "\n").encode("utf-8")
