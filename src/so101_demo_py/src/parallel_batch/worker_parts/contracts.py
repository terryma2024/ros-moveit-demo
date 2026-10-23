"""Worker errors, the run result and the small helpers of the worker."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    ValidationStatus,
)
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity


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
