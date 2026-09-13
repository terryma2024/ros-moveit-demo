"""Fenced orchestration for one isolated parallel-validation Worker slot.

The Worker owns ordering, never authority. Every reset, inference, planning or
motion boundary is bracketed by a current-lease heartbeat. The coordinator is
therefore still the source of truth for lease identity, phase and deadlines.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import threading
import time
from typing import Mapping

from .contracts import (
    AttemptStatus,
    ExecutionKind,
    LeaseIdentity,
    ParallelRuntimeConfig,
    RunMode,
    ValidationStatus,
    WorkerState,
)


class WorkerError(RuntimeError):
    """A Worker port or fencing contract failed closed."""


class LeaseGrantPaused(WorkerError):
    """The shared Broker is recovering; the Worker slot must remain alive."""


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


def _bounded_failure_message(error: Exception) -> str:
    normalized = " ".join(str(error).splitlines())
    payload = normalized.encode("utf-8", errors="replace")[:512]
    while payload:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            payload = payload[:-1]
    return ""


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

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._owner._stop_requested.is_set():
                return
            completed = threading.Event()
            response = {}

            def send_heartbeat():
                try:
                    response["ack"] = self._owner._coordinator.heartbeat(self._lease)
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
                        self._fail("HEARTBEAT_ACK_TIMEOUT")
                        return
                if "error" in response:
                    raise response["error"]
                finished = self._owner._now()
                if finished - started >= self._owner._config.heartbeat_timeout_s:
                    self._fail("HEARTBEAT_ACK_TIMEOUT")
                    return
                ack = response.get("ack")
                if not self._owner._accept_heartbeat(ack, self._lease):
                    self._fail("HEARTBEAT_ACK_INVALID")
                    return
                self._lease = ack
            except Exception:
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
        if (not isinstance(ports, Mapping)
                or set(ports) not in (required, required | {"fault_hook"})):
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
        if self._fault_hook is not None and not callable(self._fault_hook):
            raise WorkerError("FAULT_HOOK_CALLABLE")
        if type(self._config) is not ParallelRuntimeConfig:
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
        self._run_lock = threading.Lock()
        self._execution_lock = threading.RLock()
        self._stop_requested = threading.Event()
        self._clock_lock = threading.Lock()
        self._lease_lock = threading.Lock()
        self._last_clock = None
        self._active_lease = None
        self._watchdog = None
        self._registered = False
        self._runtime_started = False
        self._ready_after_recovery = False
        self._quarantined = False
        self._local_seals = {}
        self._lease_request_sequence = 0
        self._revocation_lock = threading.Lock()
        self._revocations = {}

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
        """Fence first, then stop an exact in-flight lease off the execution lock."""
        with self._lease_lock:
            current = self._active_lease
            if current is None or _lease_key(current) != _lease_key(lease):
                return
        self._stop_requested.set()
        self._record_revocation(lease, "WATCHDOG_REVOKED", reason=_reason)
        self._start_revocation(lease)

    def _record_revocation(self, lease, phase, **details) -> None:
        """Persist audit evidence without ever delaying the safety path on failure."""
        try:
            recorder = getattr(self._runtime, "record_revocation")
            recorder(lease, phase, **details)
        except Exception:
            pass

    def _start_revocation(self, lease):
        """Start at most one independent cancel-and-confirm path per exact lease."""
        key = _lease_key(lease)
        with self._revocation_lock:
            existing = self._revocations.get(key)
            if existing is not None:
                return existing
            record = {
                "event": threading.Event(),
                "fenced": False,
                "stopped": False,
                "confirmed": False,
            }
            self._revocations[key] = record

        def revoke():
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
                self._record_revocation(lease, "CANCEL_REQUESTED")
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
                self._record_revocation(
                    lease,
                    "CONTROLLER_CANCEL_RESULT",
                    motion_stopped=record["stopped"] is True,
                    controllers_confirmed=record["confirmed"] is True,
                )
            finally:
                if broker_thread.ident is not None:
                    broker_thread.join()
                self._record_revocation(
                    lease,
                    "CANCEL_RESULT",
                    broker_fenced=record["fenced"] is True,
                    motion_stopped=record["stopped"] is True,
                    controllers_confirmed=record["confirmed"] is True,
                )
                record["event"].set()

        threading.Thread(
            target=revoke,
            name=f"parallel-worker-revocation-{lease.worker_id}",
            daemon=True,
        ).start()
        return record

    def _assert_running(self) -> None:
        if self._stop_requested.is_set():
            raise WorkerError("STOP_REQUESTED")

    def _accept_heartbeat(self, ack, expected: LeaseIdentity) -> bool:
        if not isinstance(ack, LeaseIdentity) or _lease_key(ack) != _lease_key(expected):
            return False
        with self._lease_lock:
            current = self._active_lease
            if current is None or _lease_key(current) != _lease_key(expected):
                return False
            self._active_lease = ack
        return True

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
        ack = self._call_before(call, started + timeout, "ACK_TIMEOUT")
        self._assert_running()
        if not self._ack_matches(ack, lease, state):
            raise WorkerError("ACK_MISSING_OR_STALE")
        with self._lease_lock:
            self._active_lease = ack.lease
        return ack.lease

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
        ack = self._call_before(
            lambda: self._coordinator.heartbeat(lease),
            deadline,
            "HEARTBEAT_ACK_TIMEOUT",
        )
        self._assert_running()
        if watchdog is not None and watchdog.faulted:
            raise WorkerError(watchdog.reason or "WATCHDOG_FAILED")
        if not self._accept_heartbeat(ack, lease):
            raise WorkerError("LEASE_FENCED")
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

    def _safe_stop(self, lease, *, action_may_have_started):
        record = self._start_revocation(lease)
        record["event"].wait(self._config.heartbeat_timeout_s)
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
        if ack.get("status") is not decision.status or ack.get("location") != location:
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
        return lease, decision.status, recovery_deadline

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
                    decision = self._boundary(
                        lambda current: self._runtime.execute_expert(current, admitted))
                else:
                    failure_boundary = "plan_expert"
                    decision = self._boundary(
                        lambda current: self._runtime.plan_expert(current, admitted))
            return decision, action_may_have_started, (
                None if self._mode is RunMode.DRY_RUN else terminal_failure
            )
        except Exception as error:
            decision, _, _, _ = self._safe_stop(
                lease, action_may_have_started=action_may_have_started)
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
                return WorkerRunResult(None, None, False, "WORKER_NOT_READY")
            lease_wait_started = self._now()
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
            except Exception:
                with self._lease_lock:
                    self._active_lease = None
                self._quarantined = True
                return WorkerRunResult(
                    getattr(lease, "point_id", None), None, False, "LEASE_ACK_FAILED")

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
            except Exception:
                self._safe_stop(
                    lease, action_may_have_started=self._mode is RunMode.EXECUTE)
                self._quarantined = True
                self._stop_watchdog()
                return WorkerRunResult(lease.point_id, None, False, "TERMINAL_ACK_FAILED")
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
            if (
                result.stopped_reason not in {
                    "POINT_TERMINAL", "INITIAL_GATE_FAILED"
                }
                or not result.recovered
            ):
                break
        return tuple(results)
