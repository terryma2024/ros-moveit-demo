"""Low-intrusion profiling wrappers for existing application boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from so101_demo.application.task_dispatch import TaskDispatcher
from so101_demo.core.domain import State
from so101_demo.core.runner import ExecutionContext, StateAction
from so101_demo.core.task_command import TaskCommand
from so101_demo.ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    PickPlaceExecutorPort,
    RuntimeDispatchResult,
)
from so101_demo.ports.task_planner import PlannerCandidate, PlannerPort

from .session import SemanticProfiler


def profile_planner(
    planner: PlannerPort,
    profiler: SemanticProfiler | None,
    *,
    provider: str,
    model: str,
) -> PlannerPort:
    if profiler is None:
        return planner
    return _ProfiledPlanner(planner, profiler, provider, model)


def profile_dispatcher(
    dispatcher: TaskDispatcher,
    profiler: SemanticProfiler | None,
) -> TaskDispatcher:
    if profiler is None:
        return dispatcher
    return _ProfiledDispatcher(dispatcher, profiler)


def profile_executor(
    executor: PickPlaceExecutorPort,
    profiler: SemanticProfiler | None,
) -> PickPlaceExecutorPort:
    if profiler is None:
        return executor
    return _ProfiledExecutor(executor, profiler)


def profile_actions(
    actions: Mapping[State, StateAction],
    profiler: SemanticProfiler | None,
) -> Mapping[State, StateAction]:
    if profiler is None:
        return actions
    return {
        state: _ProfiledStateAction(state, action, profiler)
        for state, action in actions.items()
    }


@dataclass(frozen=True, slots=True)
class _ProfiledPlanner:
    delegate: PlannerPort
    profiler: SemanticProfiler
    provider: str
    model: str

    def plan(self, instruction: str) -> PlannerCandidate:
        token = self.profiler.start_span(
            "agent.plan",
            {"provider": self.provider, "model": self.model},
        )
        try:
            candidate = self.delegate.plan(instruction)
        except Exception as error:
            self.profiler.finish_span(
                token,
                outcome="error",
                attributes={"error_class": type(error).__name__},
            )
            raise
        self.profiler.finish_span(
            token,
            outcome="ok",
            attributes={
                "provider": candidate.metadata.provider,
                "model": candidate.metadata.model,
                "fallback": candidate.metadata.fallback_used,
            },
        )
        return candidate


class _ProfiledDispatcher(TaskDispatcher):
    def __init__(self, delegate: TaskDispatcher, profiler: SemanticProfiler) -> None:
        self._delegate = delegate
        self._profiler = profiler

    def resolve(
        self,
        command: TaskCommand,
        request_id: str,
    ) -> DynamicCupPickPlaceRequest:
        token = self._profiler.start_span("agent.dispatch")
        try:
            request = self._delegate.resolve(command, request_id)
        except Exception as error:
            self._profiler.finish_span(
                token,
                outcome="rejected",
                attributes={
                    "reason_code": str(getattr(error, "code", type(error).__name__))
                },
            )
            raise
        self._profiler.finish_span(
            token,
            outcome="execute",
            attributes={"backend": request.backend},
        )
        return request


@dataclass(frozen=True, slots=True)
class _ProfiledExecutor:
    delegate: PickPlaceExecutorPort
    profiler: SemanticProfiler

    def dispatch(
        self,
        request: DynamicCupPickPlaceRequest,
    ) -> RuntimeDispatchResult:
        token = self.profiler.start_span(
            "runtime.total",
            {"backend": request.backend},
        )
        try:
            result = self.delegate.dispatch(request)
        except Exception as error:
            self.profiler.finish_span(
                token,
                outcome="error",
                attributes={
                    "reason_code": str(getattr(error, "code", type(error).__name__))
                },
            )
            raise
        self.profiler.finish_span(
            token,
            outcome="ok" if result.exit_code == 0 else "error",
            attributes={
                "exit_code": result.exit_code,
                "session_id": result.runtime_session_id,
            },
        )
        return result


@dataclass(frozen=True, slots=True)
class _ProfiledStateAction:
    state: State
    delegate: StateAction
    profiler: SemanticProfiler

    def run(self, context: ExecutionContext):
        token = self.profiler.start_span(
            f"runtime.state.{self.state.value}",
            {"state": self.state.value},
        )
        try:
            result = self.delegate.run(context)
        except Exception as error:
            self.profiler.finish_span(
                token,
                outcome="error",
                attributes={"error_class": type(error).__name__},
            )
            raise
        attributes: dict[str, object] = {"state": self.state.value}
        if result.failure is not None:
            attributes["failure_category"] = result.failure.category.value
            attributes["reason_code"] = result.failure.code
        self.profiler.finish_span(
            token,
            outcome=result.status.value,
            attributes=attributes,
        )
        return result
