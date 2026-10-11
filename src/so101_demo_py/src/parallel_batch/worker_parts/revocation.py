"""Teacher windows, revocation and heartbeats of the worker."""

from __future__ import annotations

import threading
import time

from so101_demo.parallel_batch.contracts.common import (
    TeacherChannelTerminal,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.contracts.linux_cuda import (
    teacher_execution_bound_s,
)
from so101_demo.parallel_batch.worker_parts.contracts import (
    _COORDINATOR_LOSS_REASONS,
    WorkerError,
    _emit_diagnostic,
    _lease_key,
)
from so101_demo.parallel_batch.worker_parts.watchdog import _HeartbeatWatchdog


class WorkerRevocation:
    def _watchdog_revoked(self, lease, _reason) -> None:
        """Fence first, then stop an exact in-flight lease off the execution lock.

        A lost Coordinator is a coordination problem, not a reason to cancel a Teacher child that is still within
        its frozen execution deadline: while the Teacher window is open the loss is only recorded, no new attempt
        is scheduled, and the deadline guard (not the heartbeat) bounds the child. Outside that window, and for
        every other watchdog reason, the earlier fence-and-cancel behaviour is unchanged.
        """
        with self._lease_lock:
            current = self._active_lease
        if current is None or _lease_key(current) != _lease_key(lease):
            return
        with self._teacher_lock:
            window = self._teacher_window
            protected = (window is not None and window[0] == _lease_key(lease)
                         and _reason in _COORDINATOR_LOSS_REASONS and not self._stop_requested.is_set())
            if protected:
                self._coordinator_loss = _reason
                child_running = self._teacher_child_running
        if protected:
            _emit_diagnostic("WORKER_COORDINATOR_LOSS_TEACHER_CONTINUES", {
                "reason": _reason, "worker_id": self._worker_id, "attempt_id": lease.attempt_id,
                "child_running": child_running})
            if child_running:
                self._arm_teacher_deadline(lease)
            return
        self._stop_requested.set()
        self._start_revocation(lease, watchdog_reason=_reason)

    def _open_teacher_window(self, lease) -> None:
        with self._teacher_lock:
            self._teacher_window = (_lease_key(lease), self._now())
            self._teacher_child_running = True

    def _close_teacher_child(self) -> None:
        with self._teacher_lock:
            self._teacher_child_running = False
            stop, self._teacher_deadline_stop = self._teacher_deadline_stop, None
        if stop is not None:
            stop.set()

    def _clear_teacher_window(self) -> None:
        self._close_teacher_child()
        with self._teacher_lock:
            self._teacher_window = None

    def _arm_teacher_deadline(self, lease) -> None:
        """Bound the Teacher child by its frozen execution deadline once the Coordinator can no longer do it."""
        with self._teacher_lock:
            if self._teacher_deadline_stop is not None or self._teacher_window is None:
                return
            deadline = self._teacher_window[1] + teacher_execution_bound_s(self._config)
            stop = self._teacher_deadline_stop = threading.Event()

        def guard():
            while not stop.wait(0.01):
                try:
                    expired = self._now() >= deadline
                except Exception:
                    expired = True
                if expired:
                    self._start_revocation(lease, watchdog_reason="TEACHER_EXECUTION_DEADLINE")
                    return

        threading.Thread(target=guard, name=f"parallel-worker-teacher-deadline-{lease.worker_id}",
                         daemon=True).start()

    def _record_revocation(self, lease, phase, **details) -> None:
        """Persist audit evidence without ever delaying the safety path on failure."""
        try:
            recorder = getattr(self._runtime, "record_revocation")
            recorder(lease, phase, **details)
        except Exception:
            pass

    def _start_revocation(self, lease, *, watchdog_reason=None):
        """Start at most one independent cancel-and-confirm path per exact lease."""
        key = _lease_key(lease)
        with self._revocation_lock:
            existing = self._revocations.get(key)
            if existing is not None:
                return existing
            record = {
                "event": threading.Event(),
                "audit_event": threading.Event(),
                "fenced": False,
                "stopped": False,
                "confirmed": False,
            }
            self._revocations[key] = record

        def revoke():
            audit = []

            def note(phase, **details):
                audit.append((
                    phase,
                    {
                        "recorded_wall_time_ns": time.time_ns(),
                        "recorded_monotonic_ns": time.monotonic_ns(),
                        **details,
                    },
                ))

            def fence_broker():
                try:
                    record["fenced"] = self._broker.cancel_generation(
                        lease.worker_id, lease.worker_generation
                    ) is True
                except Exception:
                    pass

            broker_thread = threading.Thread(
                target=fence_broker,
                name=f"parallel-worker-broker-fence-{lease.worker_id}",
                daemon=True,
            )
            try:
                if watchdog_reason is not None:
                    note("WATCHDOG_REVOKED", reason=watchdog_reason)
                note("CANCEL_REQUESTED")
                broker_thread.start()
                try:
                    record["stopped"] = self._runtime.cancel_motion(lease) is True
                except Exception:
                    pass
                try:
                    record["confirmed"] = (
                        self._runtime.confirm_no_controller_goal(lease) is True
                    )
                except Exception:
                    pass
                note(
                    "CONTROLLER_CANCEL_RESULT",
                    motion_stopped=record["stopped"] is True,
                    controllers_confirmed=record["confirmed"] is True,
                )
            finally:
                if broker_thread.ident is not None:
                    broker_thread.join()
                note(
                    "CANCEL_RESULT",
                    broker_fenced=record["fenced"] is True,
                    motion_stopped=record["stopped"] is True,
                    controllers_confirmed=record["confirmed"] is True,
                )
                # Safety completion is observable before any durable audit I/O.
                # Missing audit receipts fail later evidence gates closed, but a
                # blocked recorder can never delay controller cancellation.
                record["event"].set()
                try:
                    for phase, details in audit:
                        self._record_revocation(lease, phase, **details)
                finally:
                    record["audit_event"].set()

        threading.Thread(
            target=revoke,
            name=f"parallel-worker-revocation-{lease.worker_id}",
            daemon=True,
        ).start()
        return record

    def _assert_running(self) -> None:
        if self._stop_requested.is_set():
            raise WorkerError("STOP_REQUESTED")

    def _accept_heartbeat(self, ack, expected: LeaseIdentity, *, deadline=None) -> bool:
        self._assert_running()
        if not isinstance(ack, LeaseIdentity) or _lease_key(ack) != _lease_key(expected):
            return False
        with self._lease_lock:
            current = self._active_lease
            if current is None or _lease_key(current) != _lease_key(expected):
                return False
        accepted = getattr(self._runtime, "heartbeat_acknowledged", None)
        if accepted is not None and not self._channel_is_terminal(ack):
            self._run_teacher_hook(accepted, ack)
            self._assert_running()
        if deadline is not None and self._now()>=deadline:
            raise WorkerError("HEARTBEAT_ACK_TIMEOUT")
        with self._lease_lock:
            current = self._active_lease
            if current is None or _lease_key(current) != _lease_key(expected):
                return False
            self._active_lease = ack
        return True

    def _channel_is_terminal(self, lease) -> bool:
        with self._teacher_lock:
            terminal = self._teacher_channel_terminal
        return terminal is not None and terminal[0] == _lease_key(lease)

    def _run_teacher_hook(self, hook, lease) -> None:
        """Run one Teacher-lifecycle acknowledgement hook.

        A renewal that reaches a channel the broker already fenced is the Teacher's own terminal event. It is recorded, the
        Worker stops renewing on that channel, and the Coordinator heartbeat that carried it stands: the lease stays alive so
        the Teacher's decision can be sealed and committed. Any other failure of the hook keeps failing closed.
        """
        try:
            hook(lease)
        except TeacherChannelTerminal as terminal:
            with self._teacher_lock:
                first = self._teacher_channel_terminal is None
                self._teacher_channel_terminal = (_lease_key(lease), terminal.code)
            if first:
                _emit_diagnostic("WORKER_TEACHER_CHANNEL_TERMINAL", {
                    "code": terminal.code, "worker_id": self._worker_id, "attempt_id": lease.attempt_id,
                    "committed_by": "teacher_decision"}, terminal)

    def _heartbeat_transaction(self, lease, deadline):
        if not self._ordered_receipts:
            return self._coordinator.heartbeat(lease)
        with self._coordinator_update_lock:
            self._assert_running()
            if self._now() >= deadline:
                raise WorkerError("HEARTBEAT_ACK_TIMEOUT")
            ack = self._coordinator.heartbeat(lease)
            self._assert_running()
            if self._now() >= deadline:
                raise WorkerError("HEARTBEAT_ACK_TIMEOUT")
            if not self._accept_heartbeat(ack, lease, deadline=deadline):
                raise WorkerError("LEASE_FENCED")
            return ack

    def _start_watchdog(self, lease) -> None:
        with self._execution_lock:
            self._assert_running()
            self._watchdog = _HeartbeatWatchdog(self, lease)
            self._watchdog.start()

    def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None
