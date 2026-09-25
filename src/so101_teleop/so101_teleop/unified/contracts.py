"""Pure contracts shared by the unified web service.

Every later module imports its types from here. This module must stay importable in an
environment without ROS: no rclpy, no FastAPI, no I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from enum import StrEnum
import math
from pathlib import Path
import re


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
class AdmittedCampaignContext:
    """Immutable owner record created once, before ACT children may be composed."""

    campaign_id: str
    operation_id: str
    workload_kind: str
    service_epoch: str
    execution_generation: int
    stable_host_id: str
    physical_gpu_uuid: str
    worker_count: int
    source_sha256: str
    manifest_sha256: str
    runtime_config_sha256: str
    collection_config_sha256: str
    contact_policy_fingerprint: str
    domain_session_map_sha256: str
    resource_binding_id: str
    evidence_root: str
    admitted_at_monotonic_s: float
    deadline_monotonic_s: float

    def __post_init__(self) -> None:
        for name in ("campaign_id", "operation_id", "workload_kind", "service_epoch", "stable_host_id", "physical_gpu_uuid", "resource_binding_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"CAMPAIGN_CONTEXT_IDENTITY: {name}")
        if type(self.execution_generation) is not int or self.execution_generation < 0:
            raise ValueError("CAMPAIGN_CONTEXT_GENERATION")
        if type(self.worker_count) is not int or self.worker_count < 1:
            raise ValueError("CAMPAIGN_CONTEXT_WORKER_COUNT")
        for name in (
            "source_sha256", "manifest_sha256", "runtime_config_sha256", "collection_config_sha256",
            "contact_policy_fingerprint", "domain_session_map_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError(f"CAMPAIGN_CONTEXT_HASH: {name}")
        if not isinstance(self.evidence_root, str) or not Path(self.evidence_root).is_absolute() or ".." in Path(self.evidence_root).parts:
            raise ValueError("CAMPAIGN_CONTEXT_EVIDENCE_ROOT")
        if not isinstance(self.admitted_at_monotonic_s, (int, float)) or not math.isfinite(self.admitted_at_monotonic_s) or self.admitted_at_monotonic_s < 0:
            raise ValueError("CAMPAIGN_CONTEXT_ADMISSION_TIME")
        if not isinstance(self.deadline_monotonic_s, (int, float)) or not math.isfinite(self.deadline_monotonic_s) or self.deadline_monotonic_s <= self.admitted_at_monotonic_s:
            raise ValueError("CAMPAIGN_CONTEXT_DEADLINE")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, document: dict) -> "AdmittedCampaignContext":
        if not isinstance(document, dict) or set(document) != {field.name for field in fields(cls)}:
            raise ValueError("CAMPAIGN_CONTEXT_SCHEMA")
        return cls(**document)


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
