"""The contract error, run and status enums and the field validators."""

from __future__ import annotations

from enum import StrEnum
import math
from numbers import Real
from pathlib import Path, PurePosixPath
import re


class ContractError(ValueError):
    """A closed parallel-validation contract was violated."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


#: Broker refusals that end the Teacher's channel: the Teacher side's own terminal event, never a Coordinator problem.
TEACHER_CHANNEL_TERMINAL_CODES = frozenset({
    "TEACHER_CHANNEL_FENCED", "TEACHER_EPISODE_EXPIRED", "TEACHER_FENCE_CONTEXT_INVALID"})


class TeacherChannelTerminal(PermissionError):
    """The command broker fenced or retired the Teacher's channel (its phase proof refused, or its episode ended).

    Raised by the Teacher lifecycle when a renewal reaches a channel that is already terminal. The Worker treats it as the
    Teacher's own terminal event: it stops renewing on that channel, lets the child finish and seals the Teacher's
    decision. It is not a lost Coordinator.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TeacherPreMotionRefused(RuntimeError):
    """The Teacher's channel was fenced, or its motion enable failed terminally, after the actual start ACK and
    before any motion (before `execute_expert`).

    Raised by the Teacher lifecycle only after its start-ACK authority check passed, so the attempt did start. The
    Worker commits it as a Teacher attempt that did not pass (never as INVALID, which is not an attempt). `reason`
    is the bounded refusal that ended it; `diagnostics` holds only facts the Worker itself knows.
    """

    def __init__(self, reason: str, diagnostics: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.diagnostics = dict(diagnostics or {})


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    PLAN_ONLY = "plan_only"
    EXECUTE = "execute"


class ExecutionKind(StrEnum):
    ATTEMPT = "attempt"
    VALIDATION = "validation"


class PointStatus(StrEnum):
    UNRUN = "UNRUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class ValidationStatus(StrEnum):
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_INVALID = "VALIDATION_INVALID"


class AttemptStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    INDETERMINATE = "INDETERMINATE"


class WorkerState(StrEnum):
    STARTING = "STARTING"
    AVAILABLE = "AVAILABLE"
    LEASED = "LEASED"
    INITIALIZING = "INITIALIZING"
    EXECUTING = "EXECUTING"
    FINALIZING = "FINALIZING"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"
    STOPPED = "STOPPED"


class ModelOutcome(StrEnum):
    QUALIFIED = "QUALIFIED"
    NORMAL_REJECTION = "NORMAL_REJECTION"
    MODEL_ERROR = "MODEL_ERROR"
    INFRA_ERROR = "INFRA_ERROR"
    QUEUE_TIMEOUT = "QUEUE_TIMEOUT"
    INFERENCE_TIMEOUT = "INFERENCE_TIMEOUT"
    CANCELLED = "CANCELLED"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


_FROZEN_MAX_WORKER_COUNT = 8


def _require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"EMPTY_ID: {name}")
    if _IDENTIFIER.fullmatch(value) is None:
        raise ContractError(f"INVALID_IDENTIFIER: {name}")
    return value


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"POSITIVE_INTEGER: {name}")
    return value


def _require_finite(name: str, value: object, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ContractError(f"FINITE: {name}")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ContractError(f"FINITE: {name}")
    return result


def _require_probability(name: str, value: object) -> float:
    result = _require_finite(name, value)
    if result > 1.0:
        raise ContractError(f"PROBABILITY: {name}")
    return result


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"SHA256: {name}")
    return value


def _require_safe_relative_path(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "\\" in value
        or "\x00" in value
        or value.startswith("./")
        or value.endswith("/")
    ):
        raise ContractError(f"SAFE_RELATIVE_PATH: {name}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"SAFE_RELATIVE_PATH: {name}")
    return value


def _require_absolute_path(name: str, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ContractError(f"ABSOLUTE_EVIDENCE_ROOT: {name}")
    raw_path = str(value)
    path = Path(value)
    if (
        not path.is_absolute()
        or raw_path in {".", ".."}
        or "\x00" in raw_path
        or any(part in {".", ".."} for part in raw_path.split("/"))
    ):
        raise ContractError(f"ABSOLUTE_EVIDENCE_ROOT: {name}")
    return path


def _require_enum(name: str, value: object, enum_type: type[StrEnum]) -> StrEnum:
    if not isinstance(value, enum_type):
        raise ContractError(f"ENUM: {name}")
    return value
