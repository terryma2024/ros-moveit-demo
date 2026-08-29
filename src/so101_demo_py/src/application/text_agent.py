from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.task_command import (
    CommandValidationError,
    TaskCommand,
    validate_instruction,
    validate_task_command,
)
from ..ports.pick_place_executor import (
    ExecutorDispatchError,
    PickPlaceExecutorPort,
    RuntimeDispatchResult,
)
from ..ports.task_planner import PlannerMetadata, PlannerPort, PlannerProviderError
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
        if self.command is not None:
            result["command"] = self.command.to_dict()
        if self.capability is not None:
            result["capability"] = self.capability
        if self.runtime_session_id is not None:
            result["runtime_session_id"] = self.runtime_session_id
        return result


class TextAgent:
    def __init__(
        self,
        planner: PlannerPort,
        executor: PickPlaceExecutorPort,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._dispatcher = dispatcher or TaskDispatcher()
        self._claimed_request_ids: set[str] = set()

    def handle(self, request: AgentRequest) -> AgentResult:
        if not self._has_strict_input_types(request):
            return self._terminal_result(
                request,
                AgentStatus.COMMAND_INVALID,
                "INPUT_INVALID",
            )
        if not request.request_id.strip():
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "REQUEST_ID_INVALID",
            )
        try:
            instruction = validate_instruction(request.instruction)
        except CommandValidationError:
            return self._terminal_result(
                request,
                AgentStatus.COMMAND_INVALID,
                "INPUT_INVALID",
            )
        try:
            planned = self._planner.plan(instruction)
        except PlannerProviderError:
            return self._terminal_result(
                request,
                AgentStatus.PLANNER_FAILED,
                "PLANNER_CHAIN_FAILED",
            )
        try:
            command = validate_task_command(planned.value)
        except CommandValidationError:
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
            )
        if request.mode == "preview" and not request.execute:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_PREVIEW,
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
            )
        if request.mode != "execute" or not request.execute:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "EXPLICIT_EXECUTE_REQUIRED",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
            )
        if request.backend != dispatch_request.backend:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "BACKEND_NOT_QUALIFIED",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
            )
        if request.request_id in self._claimed_request_ids:
            return self._terminal_result(
                request,
                AgentStatus.DISPATCH_REJECTED,
                "DUPLICATE_REQUEST_ID",
                metadata=planned.metadata,
                command=command,
                capability=dispatch_request.capability,
            )

        self._claimed_request_ids.add(request.request_id)
        try:
            runtime = self._executor.dispatch(dispatch_request)
        except ExecutorDispatchError as error:
            return self._runtime_failure_result(
                request,
                planned.metadata,
                command,
                dispatch_request.capability,
                error.code,
            )
        if not self._is_valid_runtime_result(runtime):
            return self._runtime_failure_result(
                request,
                planned.metadata,
                command,
                dispatch_request.capability,
                "EXECUTOR_RESULT_INVALID",
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
        )

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
        )

    @staticmethod
    def _has_strict_input_types(request: AgentRequest) -> bool:
        return (
            isinstance(request.request_id, str)
            and isinstance(request.instruction, str)
            and isinstance(request.mode, str)
            and type(request.execute) is bool
            and isinstance(request.backend, str)
        )

    @staticmethod
    def _terminal_result(
        request: AgentRequest,
        status: AgentStatus,
        reason_code: str | None = None,
        metadata: PlannerMetadata | None = None,
        command: TaskCommand | None = None,
        capability: str | None = None,
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
        )

    @staticmethod
    def _safe_request_id(request: AgentRequest) -> str:
        if isinstance(request.request_id, str):
            return request.request_id
        return ""
