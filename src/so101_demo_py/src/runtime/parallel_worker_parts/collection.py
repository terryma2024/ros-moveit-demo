"""The recorder first collection around a point."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Any, Callable

from so101_demo.runtime.parallel_worker_parts.receipts import RuntimeDecision
from so101_demo.runtime.task_stack import (
    StackProcessSpec,
)


class CollectionRecorder:
    _recorder_stopped_callback: Callable[[], None] | None = None

    def bind_recorder_stopped(self, callback: Callable[[], None] | None) -> None:
        """The owner's callback for the moment this runtime's bag recorder has stopped (status data; it never decides a result)."""
        self._recorder_stopped_callback = callback

    def _offline_identity(self, lease: Any, reset_epoch: object) -> dict:
        return {"session_id": self.resources.session_id, "reset_epoch": self._reset_epoch_integer(reset_epoch),
                "attempt_id": lease.attempt_id}

    def _start_recorder_first(self, lease: Any, reset_receipt: Any) -> None:
        """Start the record-only bag recorder before the Teacher and wait a bounded time for RECORDING. A refusal of the collection
        request raises (before any Teacher start); every other defect is data INVALID and never reaches the Teacher."""
        if self._collection is None or not self._collection.enabled:
            return
        from so101_demo.act.offline.orchestration import OfflineCollection

        key = self._lease_key(lease)
        _point_key, point_root = self._point_root(lease)
        identity = self._offline_identity(lease, getattr(reset_receipt, "reset_epoch", None))
        collection = OfflineCollection(
            processes=self._processes, point_root=point_root, sandbox_root=self._collection.sandbox_root,
            fault=self._collection.fault, environment=dict(self.resources.environment),
            spec_factory=lambda role, argv: StackProcessSpec(role, tuple(argv)),
            inputs_manifest=self.episode_inputs_manifest, scope=self.episode_scope_path, identity=identity,
            policy=self._recorder_policy, clock=self._recorder_clock, sleep=self._recorder_sleep,
            on_recorder_stopped=self._recorder_stopped_callback)
        self._recorders[key] = collection
        collection.start_before_teacher()

    def _recorder_teacher_started(self, lease: Any) -> None:
        """The Teacher is running. `recorder_late` starts its bag from a side thread once the Teacher has produced its setup
        evidence; nothing here blocks the Teacher."""
        collection = self._recorders.get(self._lease_key(lease))
        if collection is None:
            return
        collection.teacher_started_now()
        _key, point_root = self._point_root(lease)
        collection.arm_late_start(point_root / "dynamic" / "reachability-observed.json")

    def _finish_collection(self, lease: Any, decision: RuntimeDecision) -> RuntimeDecision:
        """After the Teacher ended (phase 1): close the bag and bind it in the recording receipt. Returns the decision with the data
        status (PENDING_QC, or INVALID with its reason), the receipt path; the Teacher fields are never touched."""
        key = self._lease_key(lease)
        collection = self._recorders.pop(key, None)
        if self._collection is None:
            return decision  # a run that never asked for collection: the decision is the Teacher's and nothing more
        if not self._collection.enabled:
            return replace(decision, act_data_status="DISABLED", act_data_reason=None)
        if collection is None:
            if decision.act_data_status == "INVALID":
                return decision   # a verdict already made (a timed-out Teacher retires its collection) keeps its own reason
            return replace(decision, act_data_status="INVALID", act_data_reason="RECORDER_NEVER_ORCHESTRATED")
        _key, point_root = self._point_root(lease)
        skip = None
        if decision.act_data_status == "INVALID":
            skip = decision.act_data_reason or "TEACHER_MANIFEST_UNVERIFIABLE"
        from so101_demo.act.offline.orchestration import LEASE_FIELDS

        outcome = collection.finish(lease={name: getattr(lease, name) for name in LEASE_FIELDS}, skip_processing=skip,
                                    deadline_s=float(lease.lease_deadline_monotonic_s))
        status, reason = outcome.data_status, outcome.reason
        qc_path = receipt_path = None
        if status == "VALID":
            qc_path = Path(outcome.facts["qc_report_path"])
        elif status == "PENDING_QC":
            receipt_path = Path(point_root) / outcome.facts["recording_receipt"]["path"]
        outcome.facts["act_data_status"] = status
        self._write_collection_record(point_root, outcome.facts, reason)
        return replace(decision, act_data_status=status, act_data_reason=reason, qc_report_path=qc_path,
                       recording_receipt_path=receipt_path)

    @staticmethod
    def _write_collection_record(point_root: Path, facts: dict, reason) -> None:
        from so101_demo.act.offline.orchestration import write_orchestration_record

        # A PENDING_QC attempt's record was written before its receipt (which hashes it); it is never rewritten.
        write_orchestration_record(point_root, facts, reason)

    @staticmethod
    def _reset_epoch_integer(value):
        if (
            not isinstance(value, str)
            or not value.startswith("reset-")
            or not value[6:].isascii()
            or not value[6:].isdecimal()
        ):
            raise RuntimeError("execute consumer reset epoch is not canonical")
        return int(value[6:])

    def bind_teacher_exit(self, callback: Callable[[], None] | None) -> None:
        """The Worker's callback that closes the Teacher-child window (and stops the Teacher deadline guard)."""
        self._teacher_exit_callback = callback

    def _teacher_has_exited(self) -> None:
        """The Teacher child ended: tell the Worker before any data work, so processing never runs inside the Teacher's window."""
        callback = self._teacher_exit_callback
        if callback is not None:
            try:
                callback()
            except Exception:   # noqa: BLE001 - the data side never decides control's result
                pass

    def _retire_recorder(self, key) -> None:
        """A cancelled attempt ends its bag recorder too, best effort: the data side never decides control's result."""
        collection = self._recorders.pop(key, None)
        if collection is not None:
            proven = False
            try:
                proven = collection.retire() is True
            except Exception:   # noqa: BLE001 - the data side never decides control's result
                proven = False
            self._recorder_stop_proofs[key] = proven

    def recorder_stop_proven(self, lease: Any) -> bool:
        """Whether this attempt's bag recorder is proven stopped (process exited, stop stats written). A run without a recorder has
        nothing to prove; a recorder that is still registered, or whose stop was not proven, is not proven."""
        key = self._lease_key(lease)
        if key in self._recorder_stop_proofs:
            return self._recorder_stop_proofs[key]
        return key not in self._recorders
