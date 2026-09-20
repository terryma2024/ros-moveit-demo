"""Admission for every mutation entry point.

The gateway is the only way a mutation may reach execution resources. It verifies the
request's instance authority and live lease, classifies the operation, and only then takes
the global reservation. Read-only operations never take a reservation, and an unknown
operation is refused instead of inheriting a permissive default.
"""

from __future__ import annotations

from enum import StrEnum

import uuid

from .arbiter import GlobalMutationArbiter
from .contracts import (
    Domain,
    DispatchToken,
    LeaseIdentity,
    MutationError,
    OperationSpec,
    Reservation,
    RequestAuthority,
)
from .instances import InstanceRegistry

DEFAULT_DEADLINE_NS = 1 << 62


class MutationClass(StrEnum):
    MOTION = "motion"
    SHORT_WRITE = "short_write"
    READ = "read"
    SAFETY = "safety"


TELEOP_OPERATIONS: dict[str, MutationClass] = {
    "plan_joints": MutationClass.MOTION,
    "plan_tcp": MutationClass.MOTION,
    "execute": MutationClass.MOTION,
    "execute_plan": MutationClass.MOTION,
    "gripper": MutationClass.MOTION,
    "attachment_attach": MutationClass.MOTION,
    "attachment_detach": MutationClass.MOTION,
    "scene_repair": MutationClass.MOTION,
    "robot_home": MutationClass.MOTION,
    "simulation_reset": MutationClass.MOTION,
    "workflow_start": MutationClass.MOTION,
    "workflow_run": MutationClass.MOTION,
    "workflow_step": MutationClass.MOTION,
    "workflow_resume": MutationClass.MOTION,
    "workflow_force-continue": MutationClass.MOTION,
    "workflow_reset": MutationClass.MOTION,
    "camera_preset": MutationClass.SHORT_WRITE,
    "parameters": MutationClass.SHORT_WRITE,
    "screenshot": MutationClass.SHORT_WRITE,
    "workflow_stop": MutationClass.SAFETY,
    "cancel": MutationClass.SAFETY,
    "snapshot": MutationClass.READ,
    "telemetry": MutationClass.READ,
    "capabilities": MutationClass.READ,
    "health": MutationClass.READ,
    "camera_presets": MutationClass.READ,
}

TASKS_OPERATIONS: dict[str, MutationClass] = {
    "start": MutationClass.MOTION,
    "recovery": MutationClass.MOTION,
    "shutdown": MutationClass.MOTION,
    "cancel": MutationClass.SAFETY,
    "capture": MutationClass.SHORT_WRITE,
    "rendered_image": MutationClass.READ,
    "reachability": MutationClass.SHORT_WRITE,
    "presets": MutationClass.READ,
    "list_runs": MutationClass.READ,
    "status": MutationClass.READ,
}

VALIDATION_OPERATIONS: dict[str, MutationClass] = {
    "create_manifest": MutationClass.SHORT_WRITE,
    "preflight": MutationClass.SHORT_WRITE,
    "start": MutationClass.MOTION,
    "retry": MutationClass.MOTION,
    "cancel": MutationClass.SAFETY,
    "get_manifest": MutationClass.READ,
    "list_campaigns": MutationClass.READ,
    "get_campaign": MutationClass.READ,
    "capabilities": MutationClass.READ,
    "health": MutationClass.READ,
    "acquire_lease": MutationClass.SAFETY,
    "renew_lease": MutationClass.SAFETY,
    "release_lease": MutationClass.SAFETY,
}

OPERATION_TABLES: dict[str, dict[str, MutationClass]] = {
    "teleop": TELEOP_OPERATIONS,
    "tasks": TASKS_OPERATIONS,
    "validation": VALIDATION_OPERATIONS,
}


def classify(domain_table: str, operation: str) -> MutationClass:
    table = OPERATION_TABLES.get(domain_table)
    if table is None:
        raise MutationError(f"UNKNOWN_OPERATION_TABLE: {domain_table}")
    mutation_class = table.get(operation)
    if mutation_class is None:
        raise MutationError(f"UNKNOWN_OPERATION: {domain_table}/{operation} defaults to refused")
    return mutation_class


class AdmissionHook:
    """The single admission check every Teleop/Tasks entry point runs before dispatch.

    It returns a ``(code, message)`` refusal or ``None`` when the entry may proceed, so the
    calling service keeps ownership of its own DTO and error formatting.
    """

    def __init__(
        self,
        gateway: "AdmissionGateway",
        *,
        domain_table: str,
        runtime_id: str,
        authority_provider,
    ) -> None:
        self.gateway = gateway
        self.domain_table = domain_table
        self.runtime_id = runtime_id
        self.authority_provider = authority_provider

    def check(self, body: dict, operation: str) -> tuple[str, str] | None:
        try:
            authority, lease = self.authority_provider()
            reservation = self.gateway.admit_entry(
                domain_table=self.domain_table,
                operation=operation,
                body=body,
                authority=authority,
                lease=lease,
                runtime_id=self.runtime_id,
            )
        except MutationError as error:
            code, _, message = str(error).partition(": ")
            return code, message or str(error)
        if reservation is not None:
            self.gateway.arbiter.hold(reservation.operation_id)
        return None


class AdmissionGateway:
    def __init__(self, arbiter: GlobalMutationArbiter, instances: InstanceRegistry) -> None:
        self.arbiter = arbiter
        self.instances = instances

    def require_authority(
        self, authority: RequestAuthority | None, lease: LeaseIdentity | None, operation: str
    ) -> None:
        """Every mutation, including legacy entries, needs a live bound instance."""
        if authority is None or lease is None:
            raise MutationError(f"CONTROLLER_INSTANCE_REQUIRED: {operation} needs instance authority")
        self.instances.authorize(authority, lease)

    def begin(
        self,
        spec: OperationSpec,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
        *,
        domain_table: str | None = None,
    ) -> Reservation:
        table = domain_table or ("validation" if str(spec.domain) == "validation" else "teleop")
        mutation_class = classify(table, spec.kind)
        if mutation_class is MutationClass.READ:
            raise MutationError(f"ADMISSION_READ_OPERATION: {spec.kind} must not take a reservation")
        if mutation_class is MutationClass.SAFETY:
            raise MutationError(f"ADMISSION_SAFETY_OPERATION: {spec.kind} uses the safety lane")
        self.require_authority(authority, lease, spec.kind)
        return self.arbiter.begin(spec)

    def admit_entry(
        self,
        *,
        domain_table: str,
        operation: str,
        body: dict,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
        runtime_id: str,
    ) -> Reservation | None:
        """Admit one HTTP or internal entry point; returns None for read-only entries."""
        mutation_class = classify(domain_table, operation)
        if mutation_class is MutationClass.READ:
            return None
        if mutation_class is MutationClass.SAFETY:
            raise MutationError(
                f"ADMISSION_SAFETY_OPERATION: {operation} must use the safety lane, not a reservation"
            )
        self.require_authority(authority, lease, operation)
        assert authority is not None
        spec = OperationSpec(
            command_id=str(body.get("command_id") or f"{operation}-{uuid.uuid4().hex}"),
            domain=Domain.VALIDATION if domain_table == "validation" else Domain.TELEOP,
            kind=operation,
            payload=dict(body.get("payload") or {}),
            runtime_id=runtime_id,
            execution_generation=authority.execution_generation,
            deadline_ns=int(body.get("deadline_ns") or DEFAULT_DEADLINE_NS),
        )
        return self.arbiter.begin(spec)

    def resume(
        self,
        parent_id: str,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
        *,
        child_id: str = "workflow",
    ) -> DispatchToken:
        """Internal continuations only: a client cannot mint authority from a parent ID."""
        self.require_authority(authority, lease, "resume")
        self.arbiter.resume_parent(parent_id)
        return self.arbiter.prepare_child(parent_id, child_id)
