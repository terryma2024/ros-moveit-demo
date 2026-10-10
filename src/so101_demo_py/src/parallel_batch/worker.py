"""Fenced orchestration for one isolated parallel-validation Worker slot.

The Worker owns ordering, never authority. Every reset, inference, planning or
motion boundary is bracketed by a current-lease heartbeat. The coordinator is
therefore still the source of truth for lease identity, phase and deadlines.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import sys
import threading
import time
from typing import Mapping

from .contracts import (
    teacher_execution_bound_s,
    ParallelRuntimeConfigLinuxCuda,
    AttemptStatus,
    ExecutionKind,
    LeaseIdentity,
    RunMode,
    TeacherChannelTerminal,
    TeacherPreMotionRefused,
    ValidationStatus,
    WorkerState,
)
from .perception import PerceptionError


class WorkerError(RuntimeError):
    """A Worker port or fencing contract failed closed."""


class LeaseGrantPaused(WorkerError):
    """The shared Broker is recovering; the Worker slot must remain alive."""


class CoordinatorLostResultUncommitted(WorkerError):
    """The Coordinator was lost while the Teacher ran; its result is sealed locally and cannot be committed."""

    def __init__(self, message, *, teacher_status, location):
        super().__init__(message)
        self.teacher_status = teacher_status
        self.location = location

# The watchdog reasons that mean "the Coordinator is gone" (as opposed to a lease or stop decision).
_COORDINATOR_LOSS_REASONS = frozenset({"HEARTBEAT_ACK_TIMEOUT", "COORDINATOR_LOST", "HEARTBEAT_ACK_INVALID"})


class FaultInjectionAbort(BaseException):
    """Escape normal recovery handlers to emulate abrupt process termination."""


@dataclass(frozen=True)
class WorkerRunResult:
    """One scheduler pass without promoting validation to physical evidence."""

    point_id: str | None
    terminal_status: AttemptStatus | ValidationStatus | None
    recovered: bool
    stopped_reason: str
    failure_boundary: str | None = None
    failure_type: str | None = None
    failure_message: str | None = None
    #: the type of the original input refusal when `failure_type` is `TeacherPreMotionRefused` (design 2026-10-10 section 1);
    #: written to worker-run-results.json only when set, so readers of older files and writers are unaffected
    failure_origin_type: str | None = None


def adaptive_result_is_infrastructure(result: WorkerRunResult) -> bool:
    """Classify one adaptive result without treating queue exhaustion as failure."""

    stopped_reason = getattr(result, "stopped_reason", None)
    if stopped_reason in {"NO_POINT", "STOP_REQUESTED"}:
        return False
    terminal_status = getattr(result, "terminal_status", None)
    if terminal_status in {
        AttemptStatus.INVALID,
        AttemptStatus.INDETERMINATE,
        ValidationStatus.VALIDATION_INVALID,
    }:
        return True
    if stopped_reason in {
        "INITIAL_GATE_FAILED",
        "WORKER_NOT_READY",
        "LEASE_ACK_FAILED",
        "START_ACK_FAILED",
        "TERMINAL_ACK_FAILED",
        "COORDINATOR_LOST_RESULT_UNCOMMITTED",
        "PORT_FAILURE",
        "REENTRANT_CALL_REJECTED",
    }:
        return True
    if (
        getattr(result, "point_id", None)
        and stopped_reason == "POINT_TERMINAL"
        and getattr(result, "recovered", None) is not True
    ):
        return True
    return stopped_reason != "POINT_TERMINAL"


class _InputUnavailable(Exception):
    """A perception-terminal decision that `request_model` returned (not raised), carried to the refusal classification."""

    def __init__(self, message: str, *, origin_type: str, failure_message: str) -> None:
        super().__init__(message)
        self.origin_type = origin_type
        self.failure_message = failure_message


#: The closed input-availability allowlist (design 2026-10-10 section 1.2): the only request_model outcomes that are committed as a
#: pre-motion input refusal. Everything else (other PerceptionErrors, other BROKER_* codes, RUNNING_EVIDENCE_UNAVAILABLE, arbitrary
#: exceptions) keeps the generic path.
INPUT_REFUSAL_PREFIXES = ("STALE_RGBD:", "STALE_RGBD_OR_TF:")
INPUT_REFUSAL_BROKER_CODE = "BROKER_CANDIDATE_AMBIGUOUS"


def _bounded_failure_message(error: Exception) -> str:
    normalized = " ".join(str(error).splitlines())
    payload = normalized.encode("utf-8", errors="replace")[:512]
    while payload:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            payload = payload[:-1]
    return ""


def _emit_diagnostic(tag, fields, error=None):
    """Write one bounded observation-only stderr line; never raise."""

    try:
        payload = dict(fields)
        if error is not None:
            payload["error_type"] = type(error).__name__
            try:
                message = " ".join(str(error).splitlines())
            except Exception:
                message = "<unprintable>"
            payload["error_message"] = message[:300]
            import traceback

            payload["frames"] = [
                f"{os.path.basename(frame.filename)}:{frame.lineno}:{frame.name}"[:160]
                for frame in traceback.extract_tb(error.__traceback__)[-12:]
            ]
        line = f"{tag} {json.dumps(payload, sort_keys=True)}"
        if len(line) >= 4000:
            payload.pop("frames", None)
            line = f"{tag} {json.dumps(payload, sort_keys=True)}"[:3999]
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _lease_key(lease: LeaseIdentity) -> tuple:
    return (
        lease.batch_id,
        lease.coordinator_epoch,
        lease.worker_id,
        lease.worker_generation,
        lease.point_id,
        lease.attempt_id,
        lease.lease_generation,
    )


class _HeartbeatWatchdog:
    """Send heartbeats outside the execution thread and latch the first fault."""

    def __init__(self, owner: "ParallelWorker", lease: LeaseIdentity):
        self._owner = owner
        self._lease = lease
        self._stop = threading.Event()
        self._fault = threading.Event()
        self._reason = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"parallel-worker-heartbeat-{lease.worker_id}",
            daemon=True,
        )

    @property
    def faulted(self) -> bool:
        return self._fault.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.2)

    def _fail(self, reason: str) -> None:
        if not self._fault.is_set():
            self._reason = reason
            self._fault.set()
            self._owner._watchdog_revoked(self._lease, reason)

    def _diagnose(self, reason, started, error=None) -> None:
        try:
            try:
                now = self._owner._now()
            except Exception:
                now = None
            _emit_diagnostic("WORKER_WATCHDOG_EXCEPTION", {
                "reason": reason,
                "worker_id": self._lease.worker_id,
                "elapsed_s": None if started is None or now is None else now - started,
                "now_s": now,
            }, error)
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._owner._stop_requested.is_set():
                return
            started = None
            completed = threading.Event()
            response = {}

            def send_heartbeat():
                try:
                    response["ack"] = self._owner._heartbeat_transaction(
                        self._lease, started + self._owner._config.heartbeat_timeout_s)
                except Exception as error:
                    response["error"] = error
                finally:
                    completed.set()

            try:
                started = self._owner._now()
                threading.Thread(
                    target=send_heartbeat,
                    name=f"parallel-worker-heartbeat-rpc-{self._lease.worker_id}",
                    daemon=True,
                ).start()
                while not completed.wait(0.01):
                    if self._stop.is_set():
                        return
                    if self._owner._now() - started >= self._owner._config.heartbeat_timeout_s:
                        self._diagnose("HEARTBEAT_ACK_TIMEOUT", started)
                        self._fail("HEARTBEAT_ACK_TIMEOUT")
                        return
                if "error" in response:
                    raise response["error"]
                finished = self._owner._now()
                if finished - started >= self._owner._config.heartbeat_timeout_s:
                    self._diagnose("HEARTBEAT_ACK_TIMEOUT", started)
                    self._fail("HEARTBEAT_ACK_TIMEOUT")
                    return
                ack = response.get("ack")
                if not self._owner._ordered_receipts and not self._owner._accept_heartbeat(ack, self._lease):
                    self._diagnose("HEARTBEAT_ACK_INVALID", started)
                    self._fail("HEARTBEAT_ACK_INVALID")
                    return
                self._lease = ack
            except Exception as error:
                self._diagnose("COORDINATOR_LOST", started, error)
                self._fail("COORDINATOR_LOST")
                return
            if self._stop.wait(self._owner._config.heartbeat_interval_s):
                return


class ParallelWorker:
    """Run a stable Worker slot through lease, terminal seal and recovery."""

    def __init__(self, ports: Mapping[str, object]):
        required = {
            "coordinator", "broker", "runtime", "results", "clock", "config",
            "worker_id", "generation",
        }
        optional = {"fault_hook", "adaptive_workers", "workload"}
        if (
            not isinstance(ports, Mapping)
            or not required.issubset(ports)
            or not set(ports).issubset(required | optional)
        ):
            raise WorkerError("WORKER_PORTS_REQUIRED")
        self._coordinator = ports["coordinator"]
        self._broker = ports["broker"]
        self._runtime = ports["runtime"]
        self._results = ports["results"]
        self._clock = ports["clock"]
        self._config = ports["config"]
        self._worker_id = ports["worker_id"]
        self._generation = ports["generation"]
        self._fault_hook = ports.get("fault_hook")
        self._adaptive_workers = ports.get("adaptive_workers", False)
        if self._fault_hook is not None and not callable(self._fault_hook):
            raise WorkerError("FAULT_HOOK_CALLABLE")
        if type(self._adaptive_workers) is not bool:
            raise WorkerError("ADAPTIVE_WORKERS_BOOLEAN")
        if not isinstance(self._config, ParallelRuntimeConfigLinuxCuda):
            raise WorkerError("FROZEN_CONFIG_REQUIRED")
        if not isinstance(self._worker_id, str) or not self._worker_id:
            raise WorkerError("WORKER_ID_REQUIRED")
        if (isinstance(self._generation, bool)
                or not isinstance(self._generation, int)
                or self._generation <= 0):
            raise WorkerError("WORKER_GENERATION_REQUIRED")
        request = getattr(self._coordinator, "request", None)
        self._mode = getattr(self._coordinator, "mode", getattr(request, "run_mode", None))
        if not isinstance(self._mode, RunMode):
            raise WorkerError("RUN_MODE_REQUIRED")
        self._workload = ports.get("workload")
        if self._workload is not None:
            from so101_demo.act.parallel_collection import ActFixedCollectionWorkload

            # exact type only: an ACT workload is the fixed collection port, and it may run only in EXECUTE mode
            if type(self._workload) is not ActFixedCollectionWorkload or self._mode is not RunMode.EXECUTE:
                raise WorkerError("WORKLOAD_PORT_INVALID")
        self._run_lock = threading.Lock()
        self._execution_lock = threading.RLock()
        self._stop_requested = threading.Event()
        self._clock_lock = threading.Lock()
        self._lease_lock = threading.Lock()
        # Original Coordinator frames must reach OWNER before another phase
        # transition may be requested. Stop/revocation never takes this lock.
        self._coordinator_update_lock = threading.Lock()
        self._ordered_receipts = getattr(self._runtime, "requires_ordered_coordinator_receipts", False)
        if type(self._ordered_receipts) is not bool or self._ordered_receipts and self._mode is not RunMode.EXECUTE:
            raise WorkerError("COORDINATOR_RECEIPT_ORDERING_INVALID")
        self._last_clock = None
        self._active_lease = None
        self._watchdog = None
        self._current_diagnostics = 0
        self._registered = False
        self._prepared_for_start = False
        self._runtime_started = False
        self._ready_after_recovery = False
        self._quarantined = False
        self._local_seals = {}
        self._lease_request_sequence = 0
        self._revocation_lock = threading.Lock()
        self._revocations = {}
        # The Teacher window: from the start of expert execution until its result is sealed locally. The first
        # element is the exact lease key; the second is when the Teacher run started (Worker clock).
        self._teacher_lock = threading.Lock()
        self._teacher_window = None
        self._teacher_child_running = False
        self._teacher_deadline_stop = None
        self._coordinator_loss = None
        # The Teacher's channel was fenced or retired by the broker: (lease key, code). Not a Coordinator problem.
        self._teacher_channel_terminal = None

    def _fault(self, boundary, phase):
        if self._fault_hook is not None:
            try:
                self._fault_hook(boundary, phase)
            except BaseException as error:
                raise FaultInjectionAbort(
                    f"FAULT_INJECTED: {boundary}:{phase}") from error

    def _now(self) -> float:
        with self._clock_lock:
            value = self._clock()
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise WorkerError("MONOTONIC_CLOCK_INVALID")
            value = float(value)
            if not math.isfinite(value):
                raise WorkerError("MONOTONIC_CLOCK_INVALID")
            if self._last_clock is not None and value < self._last_clock:
                raise WorkerError("MONOTONIC_CLOCK_REGRESSION")
            self._last_clock = value
            return value

    def request_stop(self) -> None:
        """Atomically fence all later lease renewal and execution boundaries."""
        self._stop_requested.set()
        with self._lease_lock:
            lease = self._active_lease
        if lease is not None:
            self._start_revocation(lease)
        self._stop_watchdog()

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
            # CP-3457: the runtime closes the Teacher-child window itself the moment the Teacher exits, before any data work
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

    def _start_watchdog(self, lease) -> None:
        with self._execution_lock:
            self._assert_running()
            self._watchdog = _HeartbeatWatchdog(self, lease)
            self._watchdog.start()

    def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None

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

    def _run_authorized(
        self,
        lease,
        *,
        start_event_id=None,
        start_event_type=None,
        reset_epoch=None,
    ):
        action_may_have_started = False
        failure_boundary = "scheduler_trace"
        try:
            if self._workload is not None:
                action_may_have_started = True
                failure_boundary = "act_collection"
                decision = self._workload.run_authorized(
                    lease, runtime=self._runtime, broker=self._broker,
                    boundary=self._boundary, start_event_id=start_event_id,
                    start_event_type=start_event_type, reset_epoch=reset_epoch,
                )
                return decision, True, None
            if self._mode is RunMode.DRY_RUN:
                decision = self._boundary(
                    lambda current: self._runtime.scheduler_trace(current))
            else:
                failure_boundary = "inference_snapshot"
                snapshot = self._boundary(
                    lambda current: self._runtime.inference_snapshot(current))
                failure_boundary = "request_model"
                chain = self._boundary(
                    lambda current: self._broker.request_model(
                        current,
                        ExecutionKind.ATTEMPT if self._mode is RunMode.EXECUTE
                        else ExecutionKind.VALIDATION,
                        snapshot=snapshot,
                        start_event_id=start_event_id,
                        start_event_type=start_event_type,
                        reset_epoch=reset_epoch,
                    ))
                if self._mode is RunMode.EXECUTE and getattr(chain, "perception_terminal", False) is True:
                    # the perception-terminal decision is an input refusal before motion: intercepted before admit_pose
                    disposition = getattr(chain, "disposition", None) or "UNKNOWN"
                    terminal_reason = getattr(chain, "reason", None) or "UNKNOWN"
                    origin = getattr(chain, "failure_type", None)
                    detail = getattr(chain, "failure_message", None)
                    raise _InputUnavailable(
                        f"PERCEPTION_TERMINAL:{disposition} {terminal_reason}",
                        origin_type=(origin if isinstance(origin, str) and origin else "PerceptionTerminal")[:128],
                        failure_message=(detail if isinstance(detail, str) and detail
                                         else f"PERCEPTION_TERMINAL:{disposition} {terminal_reason}"))
                terminal_failure = None
                if getattr(chain, "perception_terminal", False) is True:
                    failure_type = getattr(chain, "failure_type", None)
                    failure_message = getattr(chain, "failure_message", None)
                    if (
                        isinstance(failure_type, str)
                        and failure_type
                        and isinstance(failure_message, str)
                        and failure_message
                    ):
                        terminal_failure = {
                            "failure_boundary": "request_model",
                            "failure_type": failure_type[:128],
                            "failure_message": _bounded_failure_message(
                                RuntimeError(failure_message)
                            ),
                        }
                failure_boundary = "admit_pose"
                admitted = self._boundary(
                    lambda current: self._runtime.admit_pose(current, chain))
                if self._mode is RunMode.EXECUTE:
                    action_may_have_started = True
                    failure_boundary = "execute_expert"
                    decision = self._teacher_boundary(
                        lambda current: self._runtime.execute_expert(current, admitted))
                else:
                    failure_boundary = "plan_expert"
                    decision = self._boundary(
                        lambda current: self._runtime.plan_expert(current, admitted))
            return decision, action_may_have_started, (
                None if self._mode is RunMode.DRY_RUN else terminal_failure
            )
        except Exception as error:
            decision, _, stopped, confirmed = self._safe_stop(
                lease, action_may_have_started=action_may_have_started)
            refusal = (self._input_refusal(error)
                       if self._mode is RunMode.EXECUTE and not action_may_have_started and failure_boundary == "request_model"
                       else None)
            if refusal is not None:
                reason_message, origin_type, failure_message = refusal
                if stopped and confirmed and self._recorder_stopped(lease):
                    # the stop is proven and the recorder is proven stopped: commit the manifest-free D8f form
                    refused = TeacherPreMotionRefused(f"INPUT_UNAVAILABLE {failure_boundary} {reason_message}")
                    return self._pre_motion_decision(refused, decision), action_may_have_started, {
                        "failure_boundary": failure_boundary,
                        "failure_type": "TeacherPreMotionRefused",
                        "failure_origin_type": origin_type[:128],
                        "failure_message": _bounded_failure_message(RuntimeError(failure_message)),
                    }
                # not proven: today's unsealed path, and the worker is quarantined (a live bag must never write into a sealed result)
                self._quarantined = True
                return decision, action_may_have_started, {
                    "failure_boundary": failure_boundary,
                    "failure_type": origin_type[:128],
                    "failure_message": _bounded_failure_message(RuntimeError(failure_message)),
                }
            if (self._mode is RunMode.EXECUTE and isinstance(error, TeacherPreMotionRefused)
                    and not action_may_have_started):
                # D8f: the start ACK exists and the Teacher was fenced (or its enable failed terminally)
                # before any motion. That is a started Teacher attempt that did not pass, not INVALID.
                decision = self._pre_motion_decision(error, decision)
            return decision, action_may_have_started, {
                "failure_boundary": failure_boundary,
                "failure_type": type(error).__name__[:128],
                "failure_message": _bounded_failure_message(error),
            }

    def run_one(self) -> WorkerRunResult:
        """Run at most one global point, including its separate recovery receipt."""
        if not self._run_lock.acquire(blocking=False):
            return WorkerRunResult(None, None, False, "REENTRANT_CALL_REJECTED")
        lease = None
        try:
            if self._stop_requested.is_set():
                return WorkerRunResult(None, None, False, "STOP_REQUESTED")
            if self._quarantined or not self._register() or not self._ready():
                reason = getattr(self._runtime, "ready_failure", lambda: None)()
                if isinstance(reason, str) and reason:
                    # the readiness probe's own reason travels in the result instead of staying in a log
                    return WorkerRunResult(None, None, False, "WORKER_NOT_READY", "ready_probe",
                                           "ReadyProbeFailed", reason[:300])
                return WorkerRunResult(None, None, False, "WORKER_NOT_READY")
            lease_wait_started = self._now()
            failure_boundary = "lease_grant"
            try:
                self._lease_request_sequence += 1
                lease = self._call_before(
                    lambda: self._coordinator.grant_lease(
                        self._worker_id,
                        generation=self._generation,
                        request_key=(
                            f"lease-{self._worker_id}-{self._generation}-"
                            f"{self._lease_request_sequence}"
                        ),
                    ),
                    lease_wait_started + self._config.lease_ack_timeout_s,
                    "LEASE_GRANT_ACK_TIMEOUT",
                )
                self._assert_running()
                if lease is None:
                    return WorkerRunResult(None, None, False, "NO_POINT")
                if not isinstance(lease, LeaseIdentity):
                    raise WorkerError("LEASE_ACK_INVALID")
                if (lease.worker_id != self._worker_id
                        or lease.worker_generation != self._generation):
                    raise WorkerError("LEASE_ACK_STALE")
                with self._lease_lock:
                    self._active_lease = lease
                failure_boundary = "lease_initializing_ack"
                lease = self._request_ack(
                    lambda: self._coordinator.ack_lease(
                        lease, request_key=f"lease-ack-{lease.attempt_id}"),
                    lease,
                    WorkerState.INITIALIZING,
                    self._config.lease_ack_timeout_s,
                    lease_wait_started,
                )
            except LeaseGrantPaused:
                with self._lease_lock:
                    self._active_lease = None
                return WorkerRunResult(
                    None, None, False, "LEASE_GRANT_PAUSED"
                )
            except Exception as error:
                with self._lease_lock:
                    self._active_lease = None
                self._quarantined = True
                return WorkerRunResult(
                    getattr(lease, "point_id", None), None, False, "LEASE_ACK_FAILED",
                    failure_boundary=failure_boundary,failure_type=type(error).__name__[:128],
                    failure_message=_bounded_failure_message(error))

            self._start_watchdog(lease)
            authorized = False
            gate_summary = self._dry_run_summary(lease)
            if self._mode is not RunMode.DRY_RUN:
                failure_boundary = "reset_point"
                try:
                    reset = self._boundary(lambda current: self._runtime.reset_point(current))
                    failure_boundary = "point_initial_gate"
                    gate = self._boundary(
                        lambda current: self._runtime.point_initial_gate(current, reset))
                    gate_summary = self._gate_summary(lease, reset, gate)
                except Exception as error:
                    decision, _, _, _ = self._safe_stop(
                        lease, action_may_have_started=False)
                    failure = {
                        "failure_boundary": failure_boundary,
                        "failure_type": type(error).__name__[:128],
                        "failure_message": _bounded_failure_message(error),
                    }
                    try:
                        lease, status, recovery_deadline = self._seal_and_commit(
                            lease, decision, authorized=False)
                    except Exception:
                        self._quarantined = True
                        self._stop_watchdog()
                        return WorkerRunResult(
                            lease.point_id,
                            None,
                            False,
                            "INITIAL_GATE_FAILED",
                            **failure,
                        )
                    return WorkerRunResult(
                        lease.point_id, status,
                        self._recover(
                            lease,
                            recovery_deadline,
                            physical_action_proven_absent=(
                                decision.physical_action_proven_absent is True
                            ),
                        ),
                        "INITIAL_GATE_FAILED",
                        **failure,
                    )

            start_wait_started = self._now()
            try:
                if self._mode is RunMode.EXECUTE:
                    start_event_id = f"attempt-start-{lease.attempt_id}"
                    start_event_type = "ATTEMPT_STARTED"
                    start_call = lambda: self._coordinator.ack_attempt_started(
                        lease,
                        request_key=start_event_id,
                        gate_summary=gate_summary,
                    )
                else:
                    start_event_id = f"validation-start-{lease.attempt_id}"
                    start_event_type = "VALIDATION_STARTED"
                    start_call = lambda: self._coordinator.ack_validation_started(
                        lease,
                        request_key=start_event_id,
                        gate_summary=gate_summary,
                    )
                lease = self._request_ack(
                    start_call,
                    lease,
                    WorkerState.EXECUTING,
                    self._config.attempt_start_ack_timeout_s,
                    start_wait_started,
                )
                authorized = True
            except Exception:
                self._quarantined = True
                self._stop_watchdog()
                with self._lease_lock:
                    self._active_lease = None
                return WorkerRunResult(lease.point_id, None, False, "START_ACK_FAILED")

            decision, _, failure = self._run_authorized(
                lease,
                start_event_id=start_event_id,
                start_event_type=start_event_type,
                reset_epoch=gate_summary.get("reset_epoch"),
            )
            try:
                lease, status, recovery_deadline = self._seal_and_commit(
                    lease, decision, authorized=authorized)
            except CoordinatorLostResultUncommitted as error:
                # The Teacher result is sealed locally and unchanged; only the commit is lost. Cancel whatever may
                # still hold the controllers (nothing is expected), then stop scheduling.
                self._safe_stop(
                    lease, action_may_have_started=self._mode is RunMode.EXECUTE)
                self._quarantined = True
                self._clear_teacher_window()
                self._stop_watchdog()
                return WorkerRunResult(lease.point_id, None, False, "COORDINATOR_LOST_RESULT_UNCOMMITTED",
                    failure_boundary="result_commit", failure_type=type(error).__name__[:128],
                    failure_message=_bounded_failure_message(error))
            except Exception as error:
                # A failed seal/ACK must not erase an earlier execution refusal.
                # Keep the existing closed result fields and bounded first cause.
                first_failure = failure if failure is not None else {
                    "failure_boundary": "seal_and_commit",
                    "failure_type": type(error).__name__[:128],
                    "failure_message": _bounded_failure_message(error),
                }
                self._safe_stop(
                    lease, action_may_have_started=self._mode is RunMode.EXECUTE)
                self._quarantined = True
                self._stop_watchdog()
                return WorkerRunResult(lease.point_id, None, False, "TERMINAL_ACK_FAILED",
                    **first_failure)
            return WorkerRunResult(
                lease.point_id, status,
                self._recover(
                    lease,
                    recovery_deadline,
                    physical_action_proven_absent=(
                        decision.physical_action_proven_absent is True
                    ),
                ),
                "POINT_TERMINAL",
                **({} if failure is None else failure),
            )
        except Exception:
            if lease is not None:
                self._safe_stop(
                    lease, action_may_have_started=self._mode is RunMode.EXECUTE)
                self._quarantined = True
            self._stop_watchdog()
            return WorkerRunResult(
                getattr(lease, "point_id", None), None, False, "PORT_FAILURE")
        finally:
            self._clear_teacher_window()
            self._run_lock.release()

    def run(self) -> tuple[WorkerRunResult, ...]:
        """Consume global points until the coordinator has none or this slot is fenced."""
        results = []
        while not self._quarantined:
            if self._stop_requested.is_set():
                results.append(WorkerRunResult(None, None, False, "STOP_REQUESTED"))
                break
            result = self.run_one()
            if result.stopped_reason == "LEASE_GRANT_PAUSED":
                time.sleep(0.01)
                continue
            results.append(result)
            if self._adaptive_workers and adaptive_result_is_infrastructure(result):
                self._quarantined = True
                break
            if (
                result.stopped_reason not in {
                    "POINT_TERMINAL", "INITIAL_GATE_FAILED"
                }
                or not result.recovered
            ):
                break
        return tuple(results)
