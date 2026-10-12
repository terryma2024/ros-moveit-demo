"""Fenced orchestration for one isolated parallel-validation Worker slot.

The Worker owns ordering, never authority. Every reset, inference, planning or
motion boundary is bracketed by a current-lease heartbeat. The coordinator is
therefore still the source of truth for lease identity, phase and deadlines.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Mapping

from so101_demo.parallel_batch.contracts.common import (
    ExecutionKind,
    RunMode,
    TeacherPreMotionRefused,
    WorkerState,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.parallel_batch.contracts.linux_cuda import (
    ParallelRuntimeConfigLinuxCuda,
)
from so101_demo.parallel_batch.worker_parts.commit import WorkerCommit
from so101_demo.parallel_batch.worker_parts.contracts import (
    CoordinatorLostResultUncommitted,
    FaultInjectionAbort,
    LeaseGrantPaused,
    WorkerError,
    WorkerRunResult,
    _bounded_failure_message,
    _InputUnavailable,
    adaptive_result_is_infrastructure,
)
from so101_demo.parallel_batch.worker_parts.protocol import WorkerProtocol
from so101_demo.parallel_batch.worker_parts.revocation import WorkerRevocation


class ParallelWorker(WorkerRevocation, WorkerProtocol, WorkerCommit):
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
                failure_boundary = "act_collection"
                decision = self._workload.run_authorized(
                    lease, runtime=self._runtime, broker=self._broker,
                    boundary=self._boundary, teacher_boundary=self._teacher_boundary,
                    stop_before_motion=lambda current: self._safe_stop(current, action_may_have_started=False),
                    recorder_stopped=self._recorder_stopped, start_event_id=start_event_id,
                    start_event_type=start_event_type, reset_epoch=reset_epoch,
                )
                action_may_have_started = self._workload.action_may_have_started
                return decision, action_may_have_started, None
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
            if self._workload is not None:
                action_may_have_started = self._workload.action_may_have_started
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
