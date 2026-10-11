"""Acknowledged requests, boundaries, registration and the start gate of the worker."""

from __future__ import annotations

import math
import threading

from so101_demo.parallel_batch.contracts.common import (
    RunMode,
    WorkerState,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.worker_parts.contracts import (
    WorkerError,
    _bounded_failure_message,
    _emit_diagnostic,
    _lease_key,
)


class WorkerProtocol:
    @staticmethod
    def _ack_matches(ack, lease: LeaseIdentity, state: WorkerState) -> bool:
        ack_lease = getattr(ack, "lease", None)
        return (
            getattr(ack, "state", None) is state
            and getattr(ack, "generation", None) == lease.worker_generation
            and isinstance(ack_lease, LeaseIdentity)
            and _lease_key(ack_lease) == _lease_key(lease)
        )

    def _call_before(self, call, deadline, reason):
        """Return one synchronous port response only if it finished before deadline."""
        if self._now() >= deadline:
            raise WorkerError(reason)
        completed = threading.Event()
        response = {}

        def invoke():
            try:
                response["value"] = call()
            except Exception as error:
                response["error"] = error
            finally:
                completed.set()

        threading.Thread(
            target=invoke,
            name=f"parallel-worker-rpc-{self._worker_id}",
            daemon=True,
        ).start()
        while not completed.wait(0.01):
            if self._now() >= deadline:
                raise WorkerError(reason)
        if self._now() >= deadline:
            raise WorkerError(reason)
        if "error" in response:
            raise response["error"]
        return response.get("value")

    def _request_ack(self, call, lease, state, timeout, started):
        deadline = started + timeout

        def accept(ack):
            self._assert_running()
            if not self._ack_matches(ack, lease, state):
                raise WorkerError("ACK_MISSING_OR_STALE")
            if state is WorkerState.INITIALIZING:
                hook = getattr(self._runtime, "initializing_acknowledged", None)
            elif state is WorkerState.EXECUTING and self._mode is RunMode.EXECUTE:
                hook = getattr(self._runtime, "attempt_started_acknowledged", None)
            elif state is WorkerState.FINALIZING and self._mode is RunMode.EXECUTE:
                hook = getattr(self._runtime, "finalizing_acknowledged", None)
            else:
                hook = None
            if hook is not None and not self._channel_is_terminal(ack.lease):
                self._run_teacher_hook(hook, ack.lease)
                self._assert_running()
            if self._ordered_receipts and self._now()>=deadline:
                raise WorkerError("ACK_TIMEOUT")
            with self._lease_lock:
                self._active_lease = ack.lease
            return ack.lease

        if not self._ordered_receipts:
            return accept(self._call_before(call, deadline, "ACK_TIMEOUT"))

        def transaction():
            with self._coordinator_update_lock:
                self._assert_running()
                if self._now() >= deadline:
                    raise WorkerError("ACK_TIMEOUT")
                ack = call()
                self._assert_running()
                if self._now() >= deadline:
                    raise WorkerError("ACK_TIMEOUT")
                accepted = accept(ack)
                self._assert_running()
                if self._now() >= deadline:
                    raise WorkerError("ACK_TIMEOUT")
                return accepted

        return self._call_before(transaction, deadline, "ACK_TIMEOUT")

    def _diagnose_current(self, error, started) -> None:
        try:
            if self._current_diagnostics >= 20:
                return
            self._current_diagnostics += 1
            try:
                now = self._now()
            except Exception:
                now = None
            _emit_diagnostic("WORKER_CURRENT_HEARTBEAT_EXCEPTION", {
                "reason": "CURRENT_HEARTBEAT_EXCEPTION",
                "worker_id": self._worker_id,
                "elapsed_s": None if now is None else now - started,
                "now_s": now,
            }, error)
        except Exception:
            pass

    def _current(self) -> LeaseIdentity:
        self._assert_running()
        watchdog = self._watchdog
        if watchdog is not None and watchdog.faulted:
            raise WorkerError(watchdog.reason or "WATCHDOG_FAILED")
        with self._lease_lock:
            lease = self._active_lease
        if lease is None:
            raise WorkerError("NO_ACTIVE_LEASE")
        now = self._now()
        if now >= lease.lease_deadline_monotonic_s:
            raise WorkerError("LEASE_EXPIRED")
        deadline = min(
            now + self._config.heartbeat_timeout_s,
            lease.lease_deadline_monotonic_s,
        )
        try:
            ack = self._call_before(
                lambda: self._heartbeat_transaction(lease, deadline),
                deadline,
                "HEARTBEAT_ACK_TIMEOUT",
            )
            self._assert_running()
            if watchdog is not None and watchdog.faulted:
                raise WorkerError(watchdog.reason or "WATCHDOG_FAILED")
            if not self._ordered_receipts and not self._accept_heartbeat(ack, lease):
                raise WorkerError("LEASE_FENCED")
        except Exception as error:
            self._diagnose_current(error, now)
            raise
        if watchdog is not None and watchdog.faulted:
            raise WorkerError(watchdog.reason or "WATCHDOG_FAILED")
        return ack

    def _boundary(self, call):
        with self._execution_lock:
            self._assert_running()
            lease = self._current()
            result = call(lease)
            self._assert_running()
            self._current()
            return result

    def _teacher_boundary(self, call):
        """The boundary around the Teacher's expert execution.

        The lease is checked before the run exactly as at every boundary. After it, a lost Coordinator cannot
        replace the Teacher's own decision: the loss is recorded and the decision is returned. A user stop still
        fences the result.
        """
        with self._execution_lock:
            self._assert_running()
            lease = self._current()
            self._open_teacher_window(lease)
            # The runtime closes the Teacher-child window itself the moment the Teacher exits, before any data work
            # (the offline processing) runs inside this boundary; the `finally` below stays the backstop.
            bind = getattr(self._runtime, "bind_teacher_exit", None)
            if bind is not None:
                bind(self._close_teacher_child)
            try:
                result = call(lease)
            finally:
                self._close_teacher_child()
            self._assert_running()
            if self._coordinator_loss is None:
                try:
                    self._current()
                except Exception as error:
                    self._assert_running()
                    with self._teacher_lock:
                        self._coordinator_loss = _bounded_failure_message(error) or type(error).__name__
            return result

    def _register(self) -> bool:
        with self._execution_lock:
            return self._register_locked()

    def _register_locked(self) -> bool:
        self._assert_running()
        if self._registered:
            return True
        try:
            started = self._now()
            ack = self._call_before(
                lambda: self._coordinator.register_worker(
                    self._worker_id, generation=self._generation),
                started + self._config.heartbeat_timeout_s,
                "REGISTRATION_ACK_TIMEOUT",
            )
            self._assert_running()
            if (getattr(ack, "state", None) is not WorkerState.AVAILABLE
                    or getattr(ack, "generation", None) != self._generation
                    or getattr(ack, "stop_requested", False) is True):
                return False
            if self._mode is not RunMode.DRY_RUN and not self._runtime_started:
                self._runtime.start_physical_runtime()
                self._runtime_started = True
        except Exception:
            return False
        self._registered = True
        return True

    def _ready(self) -> bool:
        if self._ready_after_recovery:
            self._ready_after_recovery = False
            return True
        try:
            return self._runtime.worker_ready_gate() is True
        except Exception:
            return False

    def prepare_for_start(self) -> bool:
        """Register and prove runtime readiness without requesting a lease."""

        with self._execution_lock:
            if self._prepared_for_start:
                return True
            if self._stop_requested.is_set() or self._quarantined:
                return False
            if not self._register_locked() or not self._ready():
                return False
            self._prepared_for_start = True
            return True

    @staticmethod
    def _gate_summary(lease, reset, gate):
        identity = {
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "attempt_id": lease.attempt_id,
            "lease_generation": lease.lease_generation,
        }
        for evidence in (reset, gate):
            for field, expected in identity.items():
                actual = getattr(evidence, field, None)
                if type(actual) is not type(expected) or actual != expected:
                    raise WorkerError("POINT_INITIAL_GATE_IDENTITY")
        reset_epoch = getattr(reset, "reset_epoch", None)
        session_id = getattr(reset, "simulation_session_id", None)
        if (type(reset_epoch) is not str or not reset_epoch.strip()
                or type(session_id) is not str or not session_id.strip()
                or getattr(gate, "reset_epoch", None) != reset_epoch
                or getattr(gate, "simulation_session_id", None) != session_id):
            raise WorkerError("POINT_INITIAL_GATE_RESET_IDENTITY")
        reset_time = getattr(reset, "reset_completed_monotonic_s", None)
        source_time = getattr(gate, "source_frame_monotonic_s", None)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in (reset_time, source_time)):
            raise WorkerError("POINT_INITIAL_GATE_TIMESTAMP")
        if source_time <= reset_time:
            raise WorkerError("POINT_INITIAL_GATE_STALE")
        facts = {
            field: getattr(gate, field, None)
            for field in (
                "canonical_joints", "no_controller_goal", "no_attachment",
                "no_contact", "no_stale_node",
            )
        }
        if any(value is not True for value in facts.values()):
            raise WorkerError("POINT_INITIAL_GATE_FAILED")
        return {
            "schema_version": 1,
            "kind": "POINT_INITIAL_GATE",
            **identity,
            "reset_epoch": reset_epoch,
            "simulation_session_id": session_id,
            "reset_completed_monotonic_s": reset_time,
            "source_frame_monotonic_s": source_time,
            **facts,
        }

    @staticmethod
    def _dry_run_summary(lease):
        return {
            "schema_version": 1,
            "kind": "SCHEDULER_START",
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "attempt_id": lease.attempt_id,
            "lease_generation": lease.lease_generation,
            "point_gate_applicable": False,
            "physical_runtime_started": False,
            "scheduler_only": True,
        }
