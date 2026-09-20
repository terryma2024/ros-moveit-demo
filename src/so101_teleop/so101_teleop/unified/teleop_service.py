"""Production web-side teleop service.

This class owns the web process half of Teleop: admission, global reservation, parent
sequencing and the safety lane. It never imports ROS. Every restricted operation is sent
to the owned child through ``WorkerPort``/``BridgeWorkerPort``; physical trajectories, goal
handles and action results belong to the child.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .admission import AdmissionGateway, MutationClass, classify
from .arbiter import GlobalMutationArbiter
from .contracts import (
    Domain,
    LeaseIdentity,
    MutationError,
    OperationSpec,
    ParentProjection,
    RequestAuthority,
)
from .parents import ParentSequencer, WorkflowCheckpoint, WorkerPort
from .safety import SafetyAuthority, SafetyLane


@dataclass(frozen=True)
class BackendView:
    """The approved backend identity and its live capability set."""

    backend: str
    owner_package: str
    owner_executable: str
    capabilities: dict[str, bool]


class ProductionTeleopService:
    def __init__(
        self,
        worker: WorkerPort,
        *,
        admission: AdmissionGateway,
        parents: ParentSequencer,
        safety: SafetyLane,
        arbiter: GlobalMutationArbiter,
        backend_view: BackendView,
        runtime_id: str,
        parameter_path: Path | None = None,
        service_epoch: str = "unified",
    ) -> None:
        self.worker = worker
        self.admission = admission
        self.parents = parents
        self.safety = safety
        self.arbiter = arbiter
        self.backend_view = backend_view
        self.runtime_id = runtime_id
        self.parameter_path = parameter_path
        self.service_epoch = service_epoch

    # -- read-only surface -------------------------------------------------------

    async def health(self) -> dict:
        snapshot = await self.worker.current_snapshot()
        return {
            "ok": True,
            "simulation_only": True,
            "mode": getattr(snapshot, "mode", None),
            "ros_worker": "restricted_child",
            "global_state": self.arbiter.state(),
            "blocked_reason": self.arbiter.blocked_reason(),
        }

    async def current_snapshot(self):
        return await self.worker.current_snapshot()

    async def capabilities(self) -> dict:
        return {
            "simulation_only": True,
            "backend": self.backend_view.backend,
            "owner_package": self.backend_view.owner_package,
            "owner_executable": self.backend_view.owner_executable,
            "capabilities": dict(self.backend_view.capabilities),
        }

    async def camera_presets(self) -> dict:
        if not self.backend_view.capabilities.get("camera_presets"):
            return {"presets": []}
        return await self.worker.camera_presets()

    # -- mutations ---------------------------------------------------------------

    async def command(
        self,
        name: str,
        body: dict,
        *,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
    ) -> dict:
        mutation_class = classify("teleop", name)
        if mutation_class is MutationClass.READ:
            return await self._read_operation(name, body)
        if mutation_class is MutationClass.SAFETY:
            return await self._safety_operation(name, body, authority)
        reservation = self.admission.admit_entry(
            domain_table="teleop",
            operation=name,
            body=body,
            authority=authority,
            lease=lease,
            runtime_id=self.runtime_id,
        )
        capability = self._required_capability(name)
        if capability is not None and not self.backend_view.capabilities.get(capability, False):
            if reservation is not None:
                self.arbiter.settle(reservation.operation_id, cleanup_confirmed=True)
            return {
                "command_id": body.get("command_id", ""),
                "accepted": False,
                "succeeded": False,
                "code": "BACKEND_CAPABILITY_UNAVAILABLE",
                "message": f"{capability} is unavailable for backend {self.backend_view.backend}",
            }
        if reservation is not None and mutation_class is MutationClass.SHORT_WRITE:
            # Short writes hold the reservation only across admission; the write itself
            # runs immediately afterwards under the command's own idempotency record.
            self.arbiter.settle(reservation.operation_id, cleanup_confirmed=True)
        return await self.worker.command(name, body, reservation)

    async def execute_plan(
        self, plan_id: str, body: dict, *, authority: RequestAuthority | None, lease: LeaseIdentity | None
    ) -> dict:
        return await self.command("execute", {**body, "plan_id": plan_id}, authority=authority, lease=lease)

    async def execute_all(
        self, body: dict, *, authority: RequestAuthority | None, lease: LeaseIdentity | None
    ) -> ParentProjection:
        self.admission.require_authority(authority, lease, "execute_all")
        spec = OperationSpec(
            command_id=body.get("command_id") or f"execute-all-{body.get('plan_id', '')}",
            domain=Domain.TELEOP,
            kind="execute_all",
            payload={"plan_id": body.get("plan_id"), "gripper_target": body.get("gripper_target", 0.0)},
            runtime_id=self.runtime_id,
            execution_generation=authority.execution_generation,
            deadline_ns=int(body.get("deadline_ns", 0)) or (1 << 62),
        )
        return await self.parents.execute_all(spec, authority)

    async def home(
        self, body: dict, *, authority: RequestAuthority | None, lease: LeaseIdentity | None
    ) -> ParentProjection:
        self.admission.require_authority(authority, lease, "robot_home")
        spec = OperationSpec(
            command_id=body.get("command_id") or "home-1",
            domain=Domain.TELEOP,
            kind="robot_home",
            payload={"gripper_target": body.get("gripper_target", 0.0)},
            runtime_id=self.runtime_id,
            execution_generation=authority.execution_generation,
            deadline_ns=int(body.get("deadline_ns", 0)) or (1 << 62),
        )
        return await self.parents.home(spec, authority)

    async def workflow(
        self, body: dict, *, authority: RequestAuthority | None, lease: LeaseIdentity | None
    ) -> ParentProjection:
        self.admission.require_authority(authority, lease, "workflow_run")
        spec = OperationSpec(
            command_id=body.get("command_id") or f"workflow-{body.get('run_id', '')}",
            domain=Domain.TELEOP,
            kind=body.get("operation", "workflow_run"),
            payload={"run_id": body.get("run_id", "")},
            runtime_id=self.runtime_id,
            execution_generation=authority.execution_generation,
            deadline_ns=int(body.get("deadline_ns", 0)) or (1 << 62),
        )
        return await self.parents.workflow(spec, authority)

    async def cancel(self, body: dict, *, authority: RequestAuthority | None, lease: LeaseIdentity | None):
        """Cancel reaches the safety lane directly and never enters the normal coordinator."""
        return await self._safety_operation("cancel", body, authority)

    # -- internals ---------------------------------------------------------------

    async def _read_operation(self, name: str, body: dict) -> dict:
        if name in ("snapshot", "telemetry"):
            return {"snapshot": await self.worker.current_snapshot()}
        if name == "capabilities":
            return await self.capabilities()
        if name == "camera_presets":
            return await self.camera_presets()
        return await self.health()

    async def _safety_operation(self, name: str, body: dict, authority: RequestAuthority | None) -> dict:
        operation_id = body.get("parent_id") or body.get("operation_id")
        if not operation_id:
            raise MutationError("SAFETY_TARGET_REQUIRED: a parent operation id is required")
        safety_authority = SafetyAuthority(
            kind="browser",
            domain=Domain.TELEOP,
            service_epoch=self.service_epoch,
            execution_generation=authority.execution_generation if authority else 0,
            instance=authority,
        )
        intent = self.arbiter.cancel_parent(operation_id)
        receipts = []
        for target in intent.targets:
            if self.safety._authorize_pending is None:  # noqa: SLF001 - explicit composition check
                continue
            receipts.append(await self.safety.revoke(target, safety_authority))
        return {
            "command_id": body.get("command_id", ""),
            "accepted": True,
            "succeeded": bool(receipts) and all(item.linearized for item in receipts),
            "code": "OK",
            "targets": [item.target.key.child_id for item in receipts],
        }

    @staticmethod
    def _required_capability(name: str) -> str | None:
        if name.startswith("workflow_"):
            return {
                "start": "workflow_start",
                "run": "workflow_run",
                "step": "workflow_resume",
                "resume": "workflow_resume",
                "force-continue": "workflow_resume",
                "reset": "workflow_resume",
                "stop": "workflow_stop",
            }.get(name.removeprefix("workflow_"))
        return {
            "simulation_reset": "reset_world",
            "scene_repair": "scene_operations",
            "attachment_attach": "scene_operations",
            "attachment_detach": "scene_operations",
            "plan_joints": "manual_joint_execute",
            "plan_tcp": "manual_tcp_execute",
            "gripper": "manual_joint_execute",
            "robot_home": "manual_joint_execute",
            "screenshot": "physical_observation",
            "camera_preset": "camera_presets",
        }.get(name)


__all__ = ["BackendView", "ProductionTeleopService", "WorkflowCheckpoint"]
