"""Composite parent operations.

Execute All, home and workflow are single parents: the reservation is created once, the
arm and gripper steps are children of that parent, and the parent is only released after
every child reached a real terminal state and its cleanup proof converged. The window
between the arm terminal and the gripper dispatch never returns to ``IDLE``, so another
domain cannot slip in between the two steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from .arbiter import GlobalMutationArbiter
from .contracts import (
    UNKNOWN_OWNER,
    ActionKey,
    ActionTerminal,
    DispatchAck,
    DispatchToken,
    MutationError,
    OperationSpec,
    ParentProjection,
    PHASE_PAUSED,
    RequestAuthority,
)


@dataclass(frozen=True)
class WorkflowCheckpoint:
    run_id: str
    phase: str
    resumable: bool
    physical_terminal: bool
    cleanup_confirmed: bool


class WorkerPort(Protocol):
    """The restricted operations the web side may ask the owned child for."""

    def dispatch_arm(self, plan_id: str, token: DispatchToken) -> Awaitable[DispatchAck]: ...

    def dispatch_gripper(self, target: float, token: DispatchToken) -> Awaitable[DispatchAck]: ...

    def wait_terminal(self, ack: DispatchAck) -> Awaitable[ActionTerminal]: ...

    def plan_home(self) -> Awaitable[str]: ...

    def workflow(
        self, operation: str, run_id: str, token: DispatchToken
    ) -> Awaitable[WorkflowCheckpoint]: ...


class ParentSequencer:
    def __init__(
        self,
        worker: WorkerPort,
        arbiter: GlobalMutationArbiter,
        *,
        authority_guard: Callable[[RequestAuthority], Awaitable[None]],
    ) -> None:
        self.worker = worker
        self.arbiter = arbiter
        self.authority_guard = authority_guard

    async def execute_all(self, spec: OperationSpec, authority: RequestAuthority) -> ParentProjection:
        if "plan_id" not in spec.payload or "gripper_target" not in spec.payload:
            raise MutationError("EXECUTE_ALL_PAYLOAD_INCOMPLETE: plan_id and gripper_target required")
        repeated = self.arbiter.lookup_command(spec)
        if repeated is not None:
            return self.arbiter.projection(repeated.operation_id)
        parent = self.arbiter.begin(spec)
        try:
            await self.authority_guard(authority)
            arm_terminal = await self._step(
                parent.operation_id, "arm", spec.payload["plan_id"], spec.payload["gripper_target"]
            )
            if not arm_terminal.succeeded:
                # A failed arm never dispatches the gripper; the partial record is kept.
                return self.arbiter.settle(
                    parent.operation_id, cleanup_confirmed=arm_terminal.cleanup_confirmed
                )
            await self.authority_guard(authority)
            gripper_terminal = await self._step(
                parent.operation_id, "gripper", spec.payload["plan_id"], spec.payload["gripper_target"]
            )
            return self.arbiter.settle(
                parent.operation_id, cleanup_confirmed=gripper_terminal.cleanup_confirmed
            )
        except BaseException as error:
            self.arbiter.block(f"PARENT_NOT_CONVERGED: {type(error).__name__}: {error}")
            raise

    async def home(self, spec: OperationSpec, authority: RequestAuthority) -> ParentProjection:
        repeated = self.arbiter.lookup_command(spec)
        if repeated is not None:
            return self.arbiter.projection(repeated.operation_id)
        parent = self.arbiter.begin(spec)
        try:
            await self.authority_guard(authority)
            plan_id = await self.worker.plan_home()
            arm_terminal = await self._step(
                parent.operation_id, "arm", plan_id, float(spec.payload.get("gripper_target", 0.0))
            )
            if not arm_terminal.succeeded:
                return self.arbiter.settle(
                    parent.operation_id, cleanup_confirmed=arm_terminal.cleanup_confirmed
                )
            await self.authority_guard(authority)
            gripper_terminal = await self._step(
                parent.operation_id, "gripper", plan_id, float(spec.payload.get("gripper_target", 0.0))
            )
            return self.arbiter.settle(
                parent.operation_id, cleanup_confirmed=gripper_terminal.cleanup_confirmed
            )
        except BaseException as error:
            self.arbiter.block(f"PARENT_NOT_CONVERGED: {type(error).__name__}: {error}")
            raise

    async def workflow(self, spec: OperationSpec, authority: RequestAuthority) -> ParentProjection:
        repeated = self.arbiter.lookup_command(spec)
        if repeated is not None:
            return self.arbiter.projection(repeated.operation_id)
        parent = self.arbiter.begin(spec)
        try:
            await self.authority_guard(authority)
            token = self.arbiter.prepare_child(parent.operation_id, "workflow")
            checkpoint = await self.worker.workflow(spec.kind, str(spec.payload.get("run_id", "")), token)
            if checkpoint.physical_terminal and checkpoint.cleanup_confirmed:
                # A physically terminal workflow is the child's own terminal evidence.
                self.arbiter.record_terminal(
                    ActionTerminal(
                        key=ActionKey(
                            operation_id=parent.operation_id,
                            child_id="workflow",
                            goal_uuid=f"workflow:{checkpoint.run_id}",
                            owner=UNKNOWN_OWNER,
                            runtime_id=spec.runtime_id,
                            execution_generation=spec.execution_generation,
                        ),
                        succeeded=True,
                        stopped_confirmed=True,
                        cleanup_confirmed=True,
                    )
                )
                return self.arbiter.settle(parent.operation_id, cleanup_confirmed=True)
            # A resumable checkpoint is not a parent terminal state: keep the reservation.
            self.arbiter.pause(parent.operation_id)
            return self.arbiter.projection(parent.operation_id)
        except BaseException as error:
            self.arbiter.block(f"PARENT_NOT_CONVERGED: {type(error).__name__}: {error}")
            raise

    async def resume(
        self, operation_id: str, authority: RequestAuthority, *, operation: str
    ) -> DispatchToken:
        await self.authority_guard(authority)
        parent = self.arbiter.projection(operation_id)
        if parent.phase not in (PHASE_PAUSED, "ACTIVE"):
            raise MutationError(f"PARENT_NOT_RESUMABLE: {operation_id} is {parent.phase}")
        if parent.phase == PHASE_PAUSED:
            self.arbiter.resume_parent(operation_id)
        return self.arbiter.prepare_child(operation_id, "workflow")

    async def _step(
        self, operation_id: str, child_id: str, plan_id: str, gripper_target: float
    ) -> ActionTerminal:
        token = self.arbiter.prepare_child(operation_id, child_id)
        dispatch = (
            self.worker.dispatch_arm(plan_id, token)
            if child_id == "arm"
            else self.worker.dispatch_gripper(gripper_target, token)
        )
        ack = await dispatch
        self.arbiter.record_ack(token, ack)
        if not ack.accepted:
            raise MutationError(f"DISPATCH_REJECTED: {child_id} was refused by the owned child")
        terminal = await self.worker.wait_terminal(ack)
        self.arbiter.record_terminal(terminal)
        return terminal
