"""Reviewed attempt artifacts for the Worker and the check of its recovery receipts (shared by the ACT container campaigns)."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import time
from typing import Mapping

from so101_demo.cli.mujoco_batch.common import CliError, _identity
from so101_demo.parallel_batch.artifacts import (
    AttemptWorkspace,
    ValidationWorkspace,
    write_recovery_receipt,
)
from so101_demo.parallel_batch.contracts.common import RunMode, ValidationStatus


class _ArtifactResults:
    """Produce reviewed artifacts for the Worker and verify recovery receipts."""

    def __init__(self, worker_roots: Mapping[str, Path], mode: RunMode, *,
                 collection_scope=None, collection_inputs_manifest=None, clock=time.monotonic):
        self.worker_roots = {key: Path(value) for key, value in worker_roots.items()}
        self.mode = mode
        self._workspaces = {}
        self._act_stores = {}
        self._collection_scope = None
        self._collection_inputs_manifest = collection_inputs_manifest
        if collection_inputs_manifest is not None and collection_scope is None:
            raise ValueError('RESULT_QC_ORIGINAL_BINDING_REQUIRED')
        self._clock = clock
        if collection_scope is not None:
            from so101_demo.act.collection_scope import read_collection_scope
            if mode is not RunMode.EXECUTE:
                raise ValueError("ACT_RESULT_EXECUTE_REQUIRED")
            if not callable(clock):
                raise ValueError("RESULT_CLOCK_INVALID")
            self._collection_scope = Path(collection_scope)
            read_collection_scope(self._collection_scope)

    @staticmethod
    def _key(lease):
        return tuple(getattr(lease, name) for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        ))

    def reserve_workspace(self, lease, reset_receipt):
        if self.mode is RunMode.DRY_RUN:
            raise CliError("DRY_RUN_WORKSPACE_RESERVATION")
        if self._collection_scope is not None:
            from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
            from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
            if type(lease) is not LeaseIdentity or type(reset_receipt) is not ResetBoundaryReceipt:
                raise ValueError("ACT_RESET_RECEIPT_SCHEMA")
            if not lease.lease_issued_monotonic_s < reset_receipt.reset_completed_monotonic_s < lease.lease_deadline_monotonic_s:
                raise ValueError("ACT_RESET_TIME_INVALID")
        reset_epoch = getattr(reset_receipt, "reset_epoch", None)
        completed = getattr(reset_receipt, "reset_completed_monotonic_s", None)
        session = getattr(reset_receipt, "simulation_session_id", None)
        simulation_time = getattr(reset_receipt, "simulation_time_s", None)
        if (not isinstance(reset_epoch, str) or not reset_epoch
                or isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not isinstance(session, str) or not session
                or isinstance(simulation_time, bool)
                or not isinstance(simulation_time, (int, float))):
            raise CliError("WORKSPACE_RESET_RECEIPT")
        identity = _identity(lease, self.mode)
        cls = AttemptWorkspace if self.mode is RunMode.EXECUTE else ValidationWorkspace
        workspace = cls.create(
            self.worker_roots[lease.worker_id], identity,
            reset_epoch=reset_epoch,
            source_stamp={
                "reset_completed_monotonic_s": float(completed),
                "simulation_session_id": session,
                "simulation_time_s": float(simulation_time),
            },
            run_mode=self.mode,
        )
        key = self._key(lease)
        prior = self._workspaces.setdefault(key, workspace)
        if prior.path != workspace.path or prior._metadata != workspace._metadata:
            raise CliError("WORKSPACE_IDENTITY_MISMATCH")
        if self._collection_scope is not None:
            from so101_demo.act.result_store import ActCollectionResultStore
            if key in self._act_stores:
                raise ValueError("ACT_WORKSPACE_ALREADY_RESERVED")
            self._act_stores[key] = ActCollectionResultStore(workspace.path.parent, lease,
                clock=self._clock, audit_manifest=workspace.path / "episode/audit/audit-manifest.json",
                scope=self._collection_scope, expected_session_id=session,
                inputs_manifest=self._collection_inputs_manifest, trust_independent_qc_memo=True,
                expected_reset_epoch=reset_receipt.reset_epoch_value, reserved_workspace=workspace)
        return True

    def workspace(self, lease):
        try:
            return self._workspaces[self._key(lease)]
        except KeyError as error:
            raise CliError("WORKSPACE_NOT_RESERVED") from error

    def _seal(self, lease, decision):
        if self._collection_scope is not None:
            try:
                store = self._act_stores[self._key(lease)]
            except KeyError as error:
                raise ValueError("ACT_WORKSPACE_NOT_RESERVED") from error
            return store.seal_attempt(lease, decision)
        identity = _identity(lease, self.mode)
        if self.mode is RunMode.DRY_RUN:
            workspace = ValidationWorkspace.create(
                self.worker_roots[lease.worker_id], identity,
                reset_epoch="scheduler-only",
                source_stamp={"coordinator_epoch": lease.coordinator_epoch},
                run_mode=self.mode,
            )
        else:
            try:
                workspace = self._workspaces[self._key(lease)]
            except KeyError as error:
                raise CliError("WORKSPACE_NOT_RESERVED") from error
        if (
            self.mode is RunMode.PLAN_ONLY
            and decision.status is ValidationStatus.VALIDATION_PASSED
        ):
            segments = getattr(decision, "segment_receipts", None)
            if not isinstance(segments, tuple) or not segments:
                raise CliError("PLANNING_EVIDENCE_MISSING")
            workspace.write_json(
                "planning/segment-receipts.json",
                {
                    "schema_version": 1,
                    "segment_count": len(segments),
                    "segments": [
                        {
                            "state": getattr(
                                getattr(segment, "state", None),
                                "value",
                                str(getattr(segment, "state", "")),
                            ),
                            "start_state_present": getattr(
                                segment, "start_state", None
                            ) is not None,
                            "terminal_state_present": getattr(
                                segment, "terminal_state", None
                            ) is not None,
                            "plan_present": getattr(segment, "plan", None) is not None,
                            "before_scene_present": getattr(
                                segment, "before_scene", None
                            ) is not None,
                            "after_scene_present": getattr(
                                segment, "after_scene", None
                            ) is not None,
                        }
                        for segment in segments
                    ],
                },
            )
        name = "attempt-result.json" if self.mode is RunMode.EXECUTE else "validation-result.json"
        workspace.write_json(
            name,
            {
                "status": decision.status.value,
                "reason": decision.reason,
                "physical_action_proven_absent": decision.physical_action_proven_absent,
            },
        )
        return str(workspace.seal().path)

    def seal_attempt(self, lease, decision):
        if self.mode is not RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def seal_validation(self, lease, decision):
        if self.mode is RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def write_recovery_receipt(self, lease, *, succeeded, generation, **_kwargs):
        if generation != lease.worker_generation:
            raise CliError("RECOVERY_GENERATION")
        return write_recovery_receipt(
            self.worker_roots[lease.worker_id], _identity(lease, self.mode), succeeded=succeeded
        )

    def verify_recovery_receipt(self, location, lease, *, succeeded, generation, **_kwargs):
        try:
            path = Path(location)
            path.relative_to(self.worker_roots[lease.worker_id])
            document = json.loads(path.read_text(encoding="utf-8"))
            return (
                path.is_file()
                and not path.is_symlink()
                and document["identity"] == asdict(_identity(lease, self.mode))
                and document["succeeded"] is succeeded
                and generation == lease.worker_generation
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False
