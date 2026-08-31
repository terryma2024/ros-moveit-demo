import json
from pathlib import Path

import pytest

from so101_demo.application.task_dispatch import TaskDispatcher
from so101_demo.core.domain import ActionResult, ActionStatus, RunRequest, State
from so101_demo.core.runner import ExecutionContext
from so101_demo.ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    RuntimeDispatchResult,
)
from so101_demo.ports.task_planner import PlannerCandidate, PlannerMetadata
from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
from so101_demo.profiling.session import build_profiler
from so101_demo.profiling.wrappers import (
    profile_actions,
    profile_dispatcher,
    profile_executor,
    profile_planner,
)


class _Planner:
    def plan(self, instruction: str) -> PlannerCandidate:
        return PlannerCandidate(
            {"outcome": "unsupported"},
            PlannerMetadata("ollama", "qwen", 12, 3, 4, 0, False),
        )


class _Executor:
    def dispatch(self, request: DynamicCupPickPlaceRequest) -> RuntimeDispatchResult:
        return RuntimeDispatchResult(0, "runtime-session")


class _Action:
    def run(self, context: ExecutionContext) -> ActionResult:
        return ActionResult(ActionStatus.SUCCEEDED)


def _profiler(tmp_path: Path):
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="text-agent",
        )
    )
    assert profiler is not None
    return profiler


def _complete_events(tmp_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/text-agent.events.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if '"event_type":"span_complete"' in line
    ]


def test_disabled_wrapper_factories_return_original_objects_by_identity() -> None:
    planner = _Planner()
    dispatcher = TaskDispatcher()
    executor = _Executor()
    action = _Action()
    actions = {State.PREPARE_OPEN_GRIPPER: action}

    assert profile_planner(planner, None, provider="ollama", model="qwen") is planner
    assert profile_dispatcher(dispatcher, None) is dispatcher
    assert profile_executor(executor, None) is executor
    assert profile_actions(actions, None) is actions
    assert profile_actions(actions, None)[State.PREPARE_OPEN_GRIPPER] is action


def test_enabled_wrappers_preserve_results_and_record_stable_spans(
    tmp_path: Path,
) -> None:
    profiler = _profiler(tmp_path)
    planner = profile_planner(_Planner(), profiler, provider="ollama", model="qwen")
    executor = profile_executor(_Executor(), profiler)
    actions = profile_actions(
        {State.PREPARE_OPEN_GRIPPER: _Action()},
        profiler,
    )

    candidate = planner.plan("pick the cup")
    request = DynamicCupPickPlaceRequest(
        request_id="request-1",
        capability="dynamic_cup_pick_place",
        backend="mujoco",
        scene_source="observe_only",
        target_object="plastic_cup",
        action="pick",
    )
    dispatch_result = executor.dispatch(request)
    action_result = actions[State.PREPARE_OPEN_GRIPPER].run(
        ExecutionContext(RunRequest(), State.PREPARE_OPEN_GRIPPER, 0)
    )
    profiler.close()

    assert candidate.metadata.provider == "ollama"
    assert dispatch_result == RuntimeDispatchResult(0, "runtime-session")
    assert action_result == ActionResult(ActionStatus.SUCCEEDED)
    events = _complete_events(tmp_path)
    assert [event["name"] for event in events] == [
        "agent.plan",
        "runtime.total",
        "runtime.state.PREPARE_OPEN_GRIPPER",
    ]
    assert [event["outcome"] for event in events] == ["ok", "ok", "SUCCEEDED"]
    assert events[0]["attributes"] == {
        "fallback": False,
        "model": "qwen",
        "provider": "ollama",
    }


def test_wrapper_reraises_the_same_exception_and_records_error(tmp_path: Path) -> None:
    failure = RuntimeError("provider failed")

    class FailingPlanner:
        def plan(self, instruction: str) -> PlannerCandidate:
            raise failure

    profiler = _profiler(tmp_path)
    planner = profile_planner(
        FailingPlanner(),
        profiler,
        provider="deepseek",
        model="chat",
    )

    with pytest.raises(RuntimeError) as raised:
        planner.plan("pick")
    profiler.close()

    assert raised.value is failure
    events = _complete_events(tmp_path)
    assert events[0]["name"] == "agent.plan"
    assert events[0]["outcome"] == "error"
    assert events[0]["attributes"] == {"error_class": "RuntimeError"}
