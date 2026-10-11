"""Decisions, safe stop, sealing, commit and recovery of the worker."""

from __future__ import annotations

import json
import math

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    RunMode,
    ValidationStatus,
    WorkerState,
)
from so101_demo.parallel_batch.perception import PerceptionError
from so101_demo.parallel_batch.worker_parts.contracts import (
    INPUT_REFUSAL_BROKER_CODE,
    INPUT_REFUSAL_PREFIXES,
    CoordinatorLostResultUncommitted,
    WorkerError,
    _bounded_failure_message,
    _InputUnavailable,
    _lease_key,
)


class WorkerCommit:
    @staticmethod
    def _decision(status, reason, *, absent=True):
        class Decision:
            pass
        decision = Decision()
        decision.status = status
        decision.reason = reason
        decision.physical_action_proven_absent = absent
        return decision

    def _pre_motion_decision(self, error, stopped):
        """Teacher result for an attempt fenced after the start ACK and before motion.

        Fields: status INDETERMINATE (from `teacher_attempt_status`), teacher_execution_status
        INDETERMINATE, teacher_task_result UNCONFIRMED (the contract's manifest-free form: the Teacher
        produced no observation and no motion), act_data_status INVALID, act_data_reason carrying the
        bounded fence reason. `physical_action_proven_absent` follows the safe-stop evidence.
        """
        reason = "TEACHER_FENCED_BEFORE_MOTION:" + (_bounded_failure_message(error) or error.reason)[:160]
        decision = self._decision(AttemptStatus.INDETERMINATE, reason,
                                  absent=stopped.physical_action_proven_absent is True)
        decision.teacher_execution_status = "INDETERMINATE"
        decision.teacher_task_result = "UNCONFIRMED"
        decision.act_data_status = "INVALID"
        decision.act_data_reason = reason
        return decision

    @staticmethod
    def _input_refusal(error):
        """(reason message, origin type, failure message) when `error` is on the closed allowlist, else None."""
        if isinstance(error, _InputUnavailable):
            return str(error), error.origin_type, error.failure_message
        text = str(error)
        if isinstance(error, PerceptionError) and text.startswith(INPUT_REFUSAL_PREFIXES):
            return text, type(error).__name__, text
        if isinstance(error, RuntimeError) and text.startswith(INPUT_REFUSAL_BROKER_CODE):
            return text, type(error).__name__, text
        return None

    def _recorder_stopped(self, lease) -> bool:
        """The recorder is proven stopped (process exited, stop stats written). A runtime without a recorder has nothing to prove."""
        check = getattr(self._runtime, "recorder_stop_proven", None)
        if check is None:
            return True
        try:
            return check(lease) is True
        except Exception:
            return False

    def _safe_stop(self, lease, *, action_may_have_started):
        record = self._start_revocation(lease)
        record["event"].wait(self._config.heartbeat_timeout_s)
        record["audit_event"].wait(self._config.heartbeat_timeout_s)
        fenced = record["fenced"] is True
        stopped = record["stopped"] is True
        confirmed = record["confirmed"] is True
        absence_proven = not action_may_have_started
        if action_may_have_started:
            try:
                absence_proven = (
                    self._runtime.prove_no_physical_action(lease) is True)
            except Exception:
                absence_proven = False
        if self._mode is RunMode.EXECUTE:
            status = (AttemptStatus.INDETERMINATE
                      if not absence_proven else AttemptStatus.INVALID)
        else:
            status = ValidationStatus.VALIDATION_INVALID
        return (
            self._decision(
                status,
                "AUTHORIZATION_OR_PORT_FAILURE",
                absent=absence_proven,
            ),
            fenced,
            stopped,
            confirmed,
        )

    def _seal_and_commit(self, lease, decision, *, authorized):
        expected_type = AttemptStatus if self._mode is RunMode.EXECUTE else ValidationStatus
        if not isinstance(getattr(decision, "status", None), expected_type):
            raise WorkerError("MODE_RESULT_TYPE_MISMATCH")
        authorization_lost = False
        if authorized:
            try:
                lease = self._current()
            except Exception:
                with self._teacher_lock:
                    loss = self._coordinator_loss
                    window = self._teacher_window
                if (loss is not None and window is not None and window[0] == _lease_key(lease)
                        and not self._stop_requested.is_set()):
                    # The Coordinator is gone but the Teacher finished: keep its decision, seal it locally and
                    # report the missing commit as a coordination problem.
                    return self._seal_locally_after_coordinator_loss(lease, decision, loss)
                decision, _, _, _ = self._safe_stop(
                    lease, action_may_have_started=self._mode is RunMode.EXECUTE)
                authorization_lost = True
        key = _lease_key(lease)
        if key in self._local_seals:
            prior_status, location = self._local_seals[key]
            if prior_status is not decision.status:
                raise WorkerError("LOCAL_TERMINAL_ALREADY_SEALED")
        elif self._mode is RunMode.EXECUTE:
            self._fault("RESULT_SEAL", "before")
            location = self._results.seal_attempt(lease, decision)
            self._local_seals[key] = (decision.status, location)
            self._fault("RESULT_SEAL", "after")
        else:
            self._fault("RESULT_SEAL", "before")
            location = self._results.seal_validation(lease, decision)
            self._local_seals[key] = (decision.status, location)
            self._fault("RESULT_SEAL", "after")

        if authorization_lost:
            raise WorkerError("AUTHORIZATION_LOST_AFTER_LOCAL_SEAL")

        started = self._now()
        if authorized:
            lease = self._request_ack(
                lambda: self._coordinator.begin_finalizing(
                    lease, request_key=f"finalize-{lease.attempt_id}"),
                lease,
                WorkerState.FINALIZING,
                self._config.result_ack_timeout_s,
                started,
            )
        if self._mode is RunMode.EXECUTE:
            commit = lambda: self._coordinator.commit_result(
                lease, location, request_key=f"result-{lease.attempt_id}")
        else:
            commit = lambda: self._coordinator.commit_validation(
                lease, location, request_key=f"validation-{lease.attempt_id}")
        ack = self._call_before(
            commit,
            started + self._config.result_ack_timeout_s,
            "RESULT_ACK_TIMEOUT",
        )
        if not isinstance(ack, dict):
            raise WorkerError("RESULT_ACK_TIMEOUT")
        # The committed status is the Teacher's own and must equal the decision this Worker sealed: no later
        # verdict (QC included) may change it.
        committed_status = ack.get('status')
        if committed_status is not decision.status or ack.get("location") != location:
            raise WorkerError("RESULT_ACK_MISMATCH")
        recovery_deadline = ack.get("recovery_deadline_monotonic_s")
        if (isinstance(recovery_deadline, bool)
                or not isinstance(recovery_deadline, (int, float))
                or not math.isfinite(recovery_deadline)
                or self._now() >= recovery_deadline):
            raise WorkerError("RECOVERY_DEADLINE_INVALID")
        recovery_deadline = float(recovery_deadline)
        with self._lease_lock:
            self._active_lease = None
        return lease, committed_status, recovery_deadline

    def _seal_locally_after_coordinator_loss(self, lease, decision, loss):
        key = _lease_key(lease)
        if key in self._local_seals:
            prior_status, location = self._local_seals[key]
            if prior_status is not decision.status:
                raise WorkerError("LOCAL_TERMINAL_ALREADY_SEALED")
        else:
            self._fault("RESULT_SEAL", "before")
            location = self._results.seal_attempt(lease, decision)
            self._local_seals[key] = (decision.status, location)
            self._fault("RESULT_SEAL", "after")
        status = getattr(decision.status, "value", str(decision.status))
        raise CoordinatorLostResultUncommitted(
            f"COORDINATOR_LOST: {loss}; teacher_status={status}; local_result={location}",
            teacher_status=decision.status, location=location)

    def _recover(
        self,
        lease,
        deadline,
        *,
        physical_action_proven_absent: bool,
    ) -> bool:
        self._stop_watchdog()
        if (isinstance(deadline, bool)
                or not isinstance(deadline, (int, float))
                or not math.isfinite(deadline)
                or self._now() >= deadline):
            self._quarantined = True
            return False
        deadline = float(deadline)
        fenced = stopped = confirmed = recovered = ready = receipt = False
        try:
            fenced = self._call_before(
                lambda: self._broker.cancel_generation(
                    self._worker_id, lease.worker_generation),
                deadline, "RECOVERY_DEADLINE") is True
        except Exception:
            pass
        try:
            stopped = self._call_before(
                lambda: self._runtime.cancel_motion(lease),
                deadline, "RECOVERY_DEADLINE") is True
        except Exception:
            pass
        try:
            confirmed = self._call_before(
                lambda: self._runtime.confirm_no_controller_goal(lease),
                deadline, "RECOVERY_DEADLINE") is True
        except Exception:
            pass
        if physical_action_proven_absent is True:
            stopped = True
            confirmed = True
        try:
            recovered = self._call_before(
                lambda: self._runtime.recover(
                    self._worker_id, lease.worker_generation, deadline),
                deadline, "RECOVERY_DEADLINE") is True
        except Exception:
            recovered = False
        try:
            if recovered:
                ready = self._call_before(
                    self._runtime.worker_ready_gate,
                    deadline, "RECOVERY_DEADLINE") is True
        except Exception:
            ready = False
        succeeded = all((fenced, stopped, confirmed, recovered, ready))
        print(json.dumps({
            "kind": "RECOVERY_GATES",
            "worker_id": self._worker_id,
            "worker_generation": lease.worker_generation,
            "fenced": fenced,
            "stopped": stopped,
            "confirmed": confirmed,
            "recovered": recovered,
            "ready": ready,
            "physical_action_proven_absent": physical_action_proven_absent,
        }, sort_keys=True, separators=(",", ":")), flush=True)
        try:
            self._fault("RECOVERY_RECEIPT", "before")
            location = self._call_before(
                lambda: self._results.write_recovery_receipt(
                    lease,
                    succeeded=succeeded,
                    generation=lease.worker_generation,
                    deadline_monotonic_s=deadline,
                    clock=self._clock,
                ),
                deadline,
                "RECOVERY_RECEIPT_DEADLINE",
            )
            receipt = self._call_before(
                lambda: self._results.verify_recovery_receipt(
                    location,
                    lease,
                    succeeded=succeeded,
                    generation=lease.worker_generation,
                    deadline_monotonic_s=deadline,
                    clock=self._clock,
                ),
                deadline,
                "RECOVERY_RECEIPT_READBACK_DEADLINE",
            ) is True
            self._fault("RECOVERY_RECEIPT", "after")
        except Exception:
            succeeded = False
        if not receipt:
            succeeded = False
        if not succeeded:
            try:
                self._call_before(
                    lambda: self._coordinator.record_recovery(
                        self._worker_id,
                        generation=lease.worker_generation,
                        succeeded=False,
                        fenced=fenced,
                        owned_processes_stopped=stopped and recovered,
                        controllers_stopped=confirmed,
                        readmitted=ready,
                        recovery_deadline_monotonic_s=deadline,
                    ),
                    deadline,
                    "RECOVERY_RECORD_ACK_TIMEOUT",
                )
            except Exception:
                pass
            self._quarantined = True
            return False
        next_generation = lease.worker_generation + 1
        try:
            ack = self._call_before(
                lambda: self._coordinator.register_worker(
                    self._worker_id,
                    generation=next_generation,
                    recovery_deadline_monotonic_s=deadline,
                ),
                deadline,
                "READMISSION_ACK_TIMEOUT",
            )
            if (getattr(ack, "state", None) is not WorkerState.RECOVERING
                    or getattr(ack, "generation", None) != next_generation):
                raise WorkerError("READMISSION_ACK_INVALID")
            final = self._call_before(
                lambda: self._coordinator.record_recovery(
                    self._worker_id,
                    generation=next_generation,
                    succeeded=True,
                    fenced=fenced,
                    owned_processes_stopped=stopped and recovered,
                    controllers_stopped=confirmed,
                    readmitted=ready,
                    recovery_deadline_monotonic_s=deadline,
                ),
                deadline,
                "RECOVERY_RECORD_ACK_TIMEOUT",
            )
            if (getattr(final, "state", None) is not WorkerState.AVAILABLE
                    or getattr(final, "generation", None) != next_generation):
                raise WorkerError("RECOVERY_ACK_INVALID")
        except Exception:
            self._quarantined = True
            return False
        self._generation = next_generation
        self._ready_after_recovery = True
        return True
