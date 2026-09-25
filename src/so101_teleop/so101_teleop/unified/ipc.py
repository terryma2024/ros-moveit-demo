"""Closed, versioned IPC protocol between the web process and the ROS child.

The protocol accepts only allowlisted operations with strongly typed payloads. Requests
never carry a shell command, an executable path, a Python expression, or a ROS method
name. Oversized, expired, unknown-version, unknown-operation and non-finite documents are
refused before any payload is dispatched.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

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
ACT_OPERATIONS = ("task8_phase", "task8_full", "act_collection_start", "act_collection_resume", "cancel")
ALLOWED_OPERATIONS = OBSERVE_OPERATIONS + MOTION_OPERATIONS + ACT_OPERATIONS
#: Operations that must carry a dispatch token; observe-only reads must not.
TOKEN_REQUIRED_OPERATIONS = MOTION_OPERATIONS + ACT_OPERATIONS


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


class _ActPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _StackOwner(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pid: int = Field(gt=0, strict=True)
    pgid: int = Field(gt=0, strict=True)
    started_ticks: int = Field(gt=0, strict=True)
    argv_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _isolated(self):
        if self.pgid != self.pid:
            raise ValueError("IPC_STACK_OWNER_GROUP_INVALID")
        return self


class _Task8Base(_ActPayload):
    scenario_id: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contact_policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stack_owner: _StackOwner


class _Task8Phase(_Task8Base):
    stop_after: Literal[
        "SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN",
        "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK",
    ]


class _CollectionStart(_Task8Base):
    collection_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _CollectionResume(_CollectionStart):
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _ActCancel(_ActPayload):
    reason: str = Field(min_length=1, max_length=200)


ACT_PAYLOADS = {
    "task8_phase": _Task8Phase,
    "task8_full": _Task8Base,
    "act_collection_start": _CollectionStart,
    "act_collection_resume": _CollectionResume,
    "cancel": _ActCancel,
}


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
        "task8_phase",
        "task8_full",
        "act_collection_start",
        "act_collection_resume",
        "cancel",
    ]
    command_id: str = Field(min_length=1, max_length=200)
    deadline_ns: int = Field(ge=1)
    service_epoch: str = Field(min_length=1, max_length=200)
    runtime_id: str = Field(min_length=1, max_length=200)
    service_token: str = Field(min_length=1, max_length=512)
    campaign_id: str | None = Field(default=None, min_length=1, max_length=200)
    worker_id: str | None = Field(default=None, min_length=1, max_length=100)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)
    attempt_id: str | None = Field(default=None, min_length=1, max_length=200)
    execution_generation: int | None = Field(default=None, ge=0)
    token: DispatchTokenModel | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _payload_is_finite(cls, value: dict[str, Any]) -> dict[str, Any]:
        for item in _walk(value):
            if isinstance(item, float) and (item != item or item in (float("inf"), float("-inf"))):
                raise ValueError("IPC_PAYLOAD_NOT_FINITE")
        return value

    @model_validator(mode="after")
    def _act_identity_and_payload(self):
        if self.operation not in ACT_PAYLOADS:
            if any(getattr(self, name) is not None for name in (
                "campaign_id", "worker_id", "session_id", "attempt_id", "execution_generation",
            )):
                raise ValueError("IPC_LEGACY_IDENTITY_UNEXPECTED")
            return self
        if any(getattr(self, name) is None for name in (
            "campaign_id", "worker_id", "session_id", "attempt_id", "execution_generation",
        )):
            raise ValueError("IPC_ACT_IDENTITY_REQUIRED")
        if self.token is None:
            raise ValueError("IPC_TOKEN_REQUIRED")
        if self.token.child_id != self.worker_id:
            raise ValueError("IPC_WORKER_MISMATCH")
        if self.token.execution_generation != self.execution_generation:
            raise ValueError("IPC_GENERATION_MISMATCH")
        if self.token.deadline_ns != self.deadline_ns:
            raise ValueError("IPC_DEADLINE_MISMATCH")
        ACT_PAYLOADS[self.operation].model_validate(self.payload)
        return self


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
