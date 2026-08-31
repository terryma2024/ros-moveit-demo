from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from ..core.planner_outcome import (
    PlannerOutcomeKind,
    validate_planner_outcome,
)
from ..core.task_command import (
    CommandValidationError,
    TaskCommand,
    validate_instruction,
)
from ..ports.pick_place_executor import (
    ExecutionProvenance,
    ExecutorDispatchError,
    PickPlaceExecutorPort,
    RuntimeDispatchResult,
)
from ..ports.task_planner import PlannerMetadata, PlannerPort, PlannerProviderError
from ..profiling.session import SemanticProfiler
from .task_dispatch import DispatchRejectedError, TaskDispatcher


class AgentStatus(str, Enum):
    PLANNER_FAILED = "PLANNER_FAILED"
    COMMAND_INVALID = "COMMAND_INVALID"
    DISPATCH_REJECTED = "DISPATCH_REJECTED"
    DISPATCH_PREVIEW = "DISPATCH_PREVIEW"
    RUNTIME_STARTED = "RUNTIME_STARTED"
    RUNTIME_FAILED = "RUNTIME_FAILED"
    RUNTIME_COMPLETED = "RUNTIME_COMPLETED"


@dataclass(frozen=True, slots=True)
class AgentRequest:
    request_id: str
    instruction: str
    mode: str
    execute: bool
    backend: str
    confirmation_digest: str | None = None
    execution_provenance: ExecutionProvenance | None = None
    skip_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class AgentResult:
    request_id: str
    status: AgentStatus
    reason_code: str | None
    metadata: PlannerMetadata | None
    command: TaskCommand | None
    capability: str | None
    dispatch: bool
    runtime_session_id: str | None
    state_trace: tuple[AgentStatus, ...]
    planner_outcome: PlannerOutcomeKind | None = None
    confirmation_digest: str | None = None
    execution_provenance: ExecutionProvenance | None = None
    confirmation_mode: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "request_id": self.request_id,
            "status": self.status.value,
            "dispatch": self.dispatch,
            "state_trace": [status.value for status in self.state_trace],
        }
        if self.reason_code is not None:
            result["reason_code"] = self.reason_code
        if self.metadata is not None:
            result["planner"] = {
                "provider": self.metadata.provider,
                "model": self.metadata.model,
                "latency_ms": self.metadata.latency_ms,
                "input_tokens": self.metadata.input_tokens,
                "output_tokens": self.metadata.output_tokens,
                "cache_hit_tokens": self.metadata.cache_hit_tokens,
                "fallback_used": self.metadata.fallback_used,
            }
        if self.planner_outcome is not None:
            result["planner_outcome"] = self.planner_outcome.value
        if self.command is not None:
            result["command"] = self.command.to_dict()
        if self.capability is not None:
            result["capability"] = self.capability
        if self.confirmation_digest is not None:
            result["confirmation_digest"] = self.confirmation_digest
        if self.confirmation_mode is not None:
            result["confirmation_mode"] = self.confirmation_mode
        if self.runtime_session_id is not None:
            result["runtime_session_id"] = self.runtime_session_id
        if self.execution_provenance is not None:
            result["execution_provenance"] = self.execution_provenance.to_dict()
        return result


_CONFIRMATION_PATTERN = re.compile(r"sha256:v1:[0-9a-f]{64}\Z")


def build_confirmation_digest(
    instruction: str,
    command: TaskCommand,
    capability: str,
    metadata: PlannerMetadata,
) -> str:
    canonical = {
        "schema_version": 1,
        "instruction": instruction,
        "command": command.to_dict(),
        "capability": capability,
        "provider": metadata.provider,
        "model": metadata.model,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:v1:{hashlib.sha256(encoded).hexdigest()}"


class TextAgent:
    def __init__(
        self,
        planner: PlannerPort,
        executor: PickPlaceExecutorPort,
        dispatcher: TaskDispatcher | None = None,
        profiler: SemanticProfiler | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._dispatcher = dispatcher or TaskDispatcher()
        self._profiler = profiler
        self._claimed_request_ids: set[str] = set()
        self._request_claim_lock = Lock()

    def handle(self, request: AgentRequest) -> AgentResult:
        if self._profiler is None:
            return self._handle(request)
        token = self._profiler.start_span(
            "agent.total",
            {"request_id": TextAgent._safe_request_id(request)},
        )
        try:
            result = self._handle(request)
        except Exception as error:
            self._profiler.finish_span(
                token,
                outcome="error",
                attributes={"error_class": type(error).__name__},
            )
            raise
        self._profiler.finish_span(
            token,
            outcome=result.status.value,
            attributes={
                "status": result.status.value,
                "reason_code": result.reason_code,
            },
        )
        return result

    def _handle(self, request: AgentRequest) -> AgentResult:
        instruction, input_rejection = self._validate_request_input(request)
        if input_rejection is not None:
            return input_rejection
        assert instruction is not None
        try:
            planned = self._planner.plan(instruction)
        except PlannerProviderError:
            return self._terminal_result(
                request,
                AgentStatus.PLANNER_FAILED,
                "PLANNER_CHAIN_FAILED",
            )
        validation_token = (
            self._profiler.start_span("agent.validate_command")
            if self._profiler is not None
            else None
        )
        try:
            outcome = validate_planner_outcome(planned.value)
        except CommandValidationError:
            if validation_token is not None:
                self._profiler.finish_span(
                    validation_token,
                    outcome="rejected",
                    attributes={"reason_code": "COMMAND_INVALID"},
                )
            return self._terminal_result(
                request,
                AgentStatus.COMMAND_INVALID,
                "COMMAND_INVALID",
                metadata=planned.metadata,
            )
        if validation_token is not None:
            self._profiler.finish_span(
                validation_token,
                outcome="accepted",
                attributes={"planner_outcome": outcome.kind.value},
            )
        if outcome.kind is PlannerOutcomeKind.UNSUPPORTED:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "PLANNER_OUTCOME_UNSUPPORTED",
                metadata=planned.metadata,
                planner_outcome=outcome.kind,
            )
        if outcome.kind is PlannerOutcomeKind.AMBIGUOUS:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "PLANNER_OUTCOME_AMBIGUOUS",
                metadata=planned.metadata,
                planner_outcome=outcome.kind,
            )
        command = outcome.command
        if command is None:
            return self._terminal_result(
                request,
                AgentStatus.COMMAND_INVALID,
                "COMMAND_INVALID",
                metadata=planned.metadata,
            )
        try:
            dispatch_request = self._dispatcher.resolve(command, request.request_id)
        except DispatchRejectedError as error:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                error.code,
                metadata=planned.metadata,
                command=command,
                planner_outcome=outcome.kind,
            )
        confirmation_digest = build_confirmation_digest(
            instruction,
            command,
            dispatch_request.capability,
            planned.metadata,
        )
        if request.mode == "preview" and not request.execute:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_PREVIEW,
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
                confirmation_digest=confirmation_digest,
            )
        if request.mode != "execute" or not request.execute:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "EXPLICIT_EXECUTE_REQUIRED",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
            )
        if request.backend != dispatch_request.backend:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "BACKEND_NOT_QUALIFIED",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
            )
        if (
            not request.skip_confirmation
            and (
                request.confirmation_digest is None
                or not request.confirmation_digest.strip()
            )
        ):
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "CONFIRMATION_DIGEST_REQUIRED",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
            )
        if (
            not request.skip_confirmation
            and _CONFIRMATION_PATTERN.fullmatch(request.confirmation_digest) is None
        ):
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "CONFIRMATION_DIGEST_INVALID",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
            )
        if not request.skip_confirmation and not hmac.compare_digest(
            request.confirmation_digest, confirmation_digest
        ):
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "CONFIRMATION_DIGEST_MISMATCH",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
            )
        with self._request_claim_lock:
            if request.request_id in self._claimed_request_ids:
                duplicate = True
            else:
                self._claimed_request_ids.add(request.request_id)
                duplicate = False
        if duplicate:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "DUPLICATE_REQUEST_ID",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
                planner_outcome=outcome.kind,
            )

        try:
            runtime = self._executor.dispatch(dispatch_request)
        except ExecutorDispatchError as error:
            return self._runtime_failure_result(
                request,
                planned.metadata,
                command,
                dispatch_request.capability,
                error.code,
                outcome.kind,
            )
        if not self._is_valid_runtime_result(runtime):
            return self._runtime_failure_result(
                request,
                planned.metadata,
                command,
                dispatch_request.capability,
                "EXECUTOR_RESULT_INVALID",
                outcome.kind,
            )
        status = (
            AgentStatus.RUNTIME_COMPLETED
            if runtime.exit_code == 0
            else AgentStatus.RUNTIME_FAILED
        )
        return AgentResult(
            request_id=request.request_id,
            status=status,
            reason_code=None if runtime.exit_code == 0 else "RUNTIME_FAILED",
            metadata=planned.metadata,
            command=command,
            capability=dispatch_request.capability,
            dispatch=True,
            runtime_session_id=runtime.runtime_session_id,
            state_trace=(AgentStatus.RUNTIME_STARTED, status),
            planner_outcome=outcome.kind,
            confirmation_mode=("skipped" if request.skip_confirmation else "digest"),
            execution_provenance=request.execution_provenance,
        )

    def _validate_request_input(
        self,
        request: AgentRequest,
    ) -> tuple[str | None, AgentResult | None]:
        token = (
            self._profiler.start_span("agent.validate_input")
            if self._profiler is not None
            else None
        )

        def reject(status: AgentStatus, reason_code: str) -> tuple[None, AgentResult]:
            if token is not None:
                self._profiler.finish_span(
                    token,
                    outcome="rejected",
                    attributes={"reason_code": reason_code},
                )
            return None, self._terminal_result(request, status, reason_code)

        if not self._has_strict_input_types(request):
            return reject(AgentStatus.COMMAND_INVALID, "INPUT_INVALID")
        if not request.request_id.strip():
            return reject(AgentStatus.DISPATCH_REJECTED, "REQUEST_ID_INVALID")
        if request.skip_confirmation and (
            request.mode != "execute" or not request.execute
        ):
            return reject(
                AgentStatus.DISPATCH_REJECTED,
                "CONFIRMATION_BYPASS_REQUIRES_EXECUTE",
            )
        if request.skip_confirmation and request.confirmation_digest is not None:
            return reject(AgentStatus.DISPATCH_REJECTED, "CONFIRMATION_MODE_CONFLICT")
        try:
            instruction = validate_instruction(request.instruction)
        except CommandValidationError:
            return reject(AgentStatus.COMMAND_INVALID, "INPUT_INVALID")
        if token is not None:
            self._profiler.finish_span(token, outcome="accepted")
        return instruction, None

    @staticmethod
    def _is_valid_runtime_result(value: object) -> bool:
        return (
            isinstance(value, RuntimeDispatchResult)
            and type(value.exit_code) is int
            and isinstance(value.runtime_session_id, str)
        )

    @staticmethod
    def _runtime_failure_result(
        request: AgentRequest,
        metadata: PlannerMetadata,
        command: TaskCommand,
        capability: str,
        reason_code: str,
        planner_outcome: PlannerOutcomeKind,
    ) -> AgentResult:
        return AgentResult(
            request_id=request.request_id,
            status=AgentStatus.RUNTIME_FAILED,
            reason_code=reason_code,
            metadata=metadata,
            command=command,
            capability=capability,
            dispatch=True,
            runtime_session_id=None,
            state_trace=(AgentStatus.RUNTIME_STARTED, AgentStatus.RUNTIME_FAILED),
            planner_outcome=planner_outcome,
            confirmation_mode=("skipped" if request.skip_confirmation else "digest"),
            execution_provenance=request.execution_provenance,
        )

    @staticmethod
    def _has_strict_input_types(request: AgentRequest) -> bool:
        return (
            isinstance(request.request_id, str)
            and isinstance(request.instruction, str)
            and isinstance(request.mode, str)
            and type(request.execute) is bool
            and type(request.skip_confirmation) is bool
            and isinstance(request.backend, str)
            and (
                request.confirmation_digest is None
                or isinstance(request.confirmation_digest, str)
            )
            and (
                request.execution_provenance is None
                or isinstance(request.execution_provenance, ExecutionProvenance)
            )
        )

    @staticmethod
    def _terminal_result(
        request: AgentRequest,
        status: AgentStatus,
        reason_code: str | None = None,
        metadata: PlannerMetadata | None = None,
        command: TaskCommand | None = None,
        capability: str | None = None,
        planner_outcome: PlannerOutcomeKind | None = None,
        confirmation_digest: str | None = None,
    ) -> AgentResult:
        return AgentResult(
            request_id=TextAgent._safe_request_id(request),
            status=status,
            reason_code=reason_code,
            metadata=metadata,
            command=command,
            capability=capability,
            dispatch=False,
            runtime_session_id=None,
            state_trace=(status,),
            planner_outcome=planner_outcome,
            confirmation_digest=confirmation_digest,
        )

    @staticmethod
    def _safe_request_id(request: AgentRequest) -> str:
        if isinstance(request.request_id, str):
            return request.request_id
        return ""
