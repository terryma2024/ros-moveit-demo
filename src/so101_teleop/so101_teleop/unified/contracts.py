"""Pure contracts shared by the unified web service.

Every later module imports its types from here. This module must stay importable in an
environment without ROS: no rclpy, no FastAPI, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Domain(StrEnum):
    TELEOP = "teleop"
    VALIDATION = "validation"


@dataclass(frozen=True)
class InstanceProof:
    instance_id: str
    proof: str
    domain: "Domain"


@dataclass(frozen=True)
class ChannelBinding:
    instance_id: str
    revision: int
    domain: "Domain"


@dataclass(frozen=True)
class RequestAuthority:
    domain: Domain
    instance_id: str
    proof: str
    channel_revision: int
    execution_generation: int


@dataclass(frozen=True)
class LeaseIdentity:
    lease_id: str
    service_session_id: str
    lease_generation: int
    expires_monotonic_ns: int


@dataclass(frozen=True)
class OwnerKey:
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str


@dataclass(frozen=True)
class OperationSpec:
    command_id: str
    domain: Domain
    kind: str
    payload: dict
    runtime_id: str
    execution_generation: int
    deadline_ns: int


@dataclass(frozen=True)
class ActionKey:
    operation_id: str
    child_id: str
    goal_uuid: str
    owner: OwnerKey
    runtime_id: str
    execution_generation: int


@dataclass(frozen=True)
class ActionTerminal:
    key: ActionKey
    succeeded: bool
    stopped_confirmed: bool
    cleanup_confirmed: bool


@dataclass(frozen=True)
class DispatchAck:
    key: ActionKey
    accepted: bool


@dataclass(frozen=True)
class Reservation:
    operation_id: str
    spec: OperationSpec
    phase: str
    cancel_requested: bool


@dataclass(frozen=True)
class PendingChildKey:
    operation_id: str
    child_id: str
    runtime_id: str
    execution_generation: int


@dataclass(frozen=True)
class DispatchToken:
    operation_id: str
    child_id: str
    runtime_id: str
    execution_generation: int
    deadline_ns: int
    revocation_revision: int


@dataclass(frozen=True)
class RevokeTarget:
    key: PendingChildKey
    revocation_revision: int


@dataclass(frozen=True)
class CancelIntent:
    operation_id: str
    targets: tuple[RevokeTarget, ...]


@dataclass(frozen=True)
class CancelReceipt:
    key: "ActionKey"
    accepted: bool
    terminal: "ActionTerminal | None"
    blocked_reason: str | None


@dataclass(frozen=True)
class IntentCancelReceipt:
    target: "RevokeTarget"
    linearized: bool
    submitted: bool
    terminal: "ActionTerminal | None"
    blocked_reason: str | None


@dataclass(frozen=True)
class ParentProjection:
    operation_id: str
    phase: str
    children: tuple[ActionTerminal, ...]
    blocked_reason: str | None


@dataclass(frozen=True)
class QualificationView:
    """Read-only worker qualification for one exact N, owned by the budget provider."""

    selected_n: int
    status: str
    reasons: tuple[str, ...]
    runtime_identity: str
    contract_version: int
    profile_sha256: str | None
    approval_sha256: str | None


class MutationError(RuntimeError):
    """A refused mutation. ``str(error)`` starts with a stable machine-readable code."""

    @property
    def code(self) -> str:
        return str(self)


#: Placeholder owner used when a child is known to the reservation but no dispatch
#: acknowledgement has been recorded yet, so no real process identity exists.
UNKNOWN_OWNER = OwnerKey(0, 0, 0, "", "")

IDLE = "IDLE"
BLOCKED = "BLOCKED"
TELEOP_ACTIVE = "TELEOP_ACTIVE"
TASK_ACTIVE = "TASK_ACTIVE"
VALIDATION_ACTIVE = "VALIDATION_ACTIVE"
CLEANING = "CLEANING"

PHASE_ACTIVE = "ACTIVE"
PHASE_PAUSED = "PAUSED"
PHASE_COMPLETE = "COMPLETE"
PHASE_CANCELLED = "CANCELLED"
PHASE_BLOCKED = "BLOCKED"

CHILD_PREPARED = "PREPARED"
CHILD_ACKED = "ACKED"
CHILD_REJECTED = "REJECTED"
CHILD_TERMINAL = "TERMINAL"

RESERVING_STATES = (TELEOP_ACTIVE, TASK_ACTIVE, VALIDATION_ACTIVE, CLEANING)
