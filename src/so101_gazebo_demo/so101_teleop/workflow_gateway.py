"""Serialized adapter for the C++ checkpointed state machine; never contains a transition table."""

from __future__ import annotations

import time
import uuid
from typing import Protocol

from .models import OverrideAudit, WorkflowSnapshot


class WorkflowRejected(RuntimeError):
    pass


class WorkflowRunner(Protocol):
    async def start(self, run_id: str, session_id: str) -> WorkflowSnapshot: ...
    async def step(self, run_id: str, override: bool = False) -> WorkflowSnapshot: ...


class WorkflowGateway:
    def __init__(self, runner: WorkflowRunner) -> None:
        self._runner = runner
        self._snapshot = WorkflowSnapshot()
        self._snapshot_revision: int | None = None
        self._override_consumed = False

    async def start(self, run_id: str | None, session_id: str) -> WorkflowSnapshot:
        self._snapshot = await self._runner.start(run_id or str(uuid.uuid4()), session_id)
        self._snapshot_revision = None
        self._override_consumed = False
        return self._snapshot

    async def step(self, run_id: str, snapshot_revision: int) -> WorkflowSnapshot:
        self._require_run(run_id)
        self._require_revision(snapshot_revision)
        if self._snapshot.current_state == "VALIDATION_FAILED":
            raise WorkflowRejected("VALIDATION_FAILED")
        self._snapshot = await self._runner.step(run_id, override=False)
        self._snapshot_revision = snapshot_revision
        return self._snapshot

    async def force_continue(self, command_id: str, run_id: str, snapshot_revision: int,
                             operator_confirmation: str) -> WorkflowSnapshot:
        self._require_run(run_id)
        self._require_revision(snapshot_revision)
        validation = self._snapshot.validation
        blocked_prefixes = ("ACTION_", "CONTROLLER_", "LEASE_", "READINESS_", "CHECKPOINT_",
                            "SESSION_", "STALE_", "FINAL_PLACEMENT_", "PLANNING_SHADOW_")
        if (self._override_consumed or self._snapshot.current_state != "VALIDATION_FAILED" or
                not self._snapshot.checkpoint_fresh or validation is None or validation.passed or
                not validation.failure_code or not validation.failure_code.startswith("PHYSICAL_GRASP_") or
                validation.failure_code.startswith(blocked_prefixes) or
                operator_confirmation != "FORCE CONTINUE"):
            raise WorkflowRejected("OVERRIDE_NOT_ALLOWED")
        audit = OverrideAudit(command_id=command_id, workflow_run_id=run_id,
                              state=self._snapshot.next_state or "", snapshot_revision=snapshot_revision,
                              failure_code=validation.failure_code, evidence=validation,
                              operator_confirmation=operator_confirmation, confirmed_at=time.time())
        advanced = await self._runner.step(run_id, override=True)
        self._override_consumed = True
        self._snapshot = advanced.copy(update={"override_audit": [*advanced.override_audit, audit]})
        return self._snapshot

    def _require_run(self, run_id: str) -> None:
        if self._snapshot.run_id != run_id:
            raise WorkflowRejected("WORKFLOW_RUN_MISMATCH")

    def _require_revision(self, revision: int) -> None:
        if self._snapshot_revision is not None and revision != self._snapshot_revision:
            raise WorkflowRejected("CHECKPOINT_STALE")
