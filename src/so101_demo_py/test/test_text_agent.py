from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field
import json
from pathlib import Path
import pytest

from so101_demo.application.task_dispatch import TaskDispatcher
from so101_demo.application.text_agent import (
    AgentRequest,
    AgentStatus,
    TextAgent,
    build_confirmation_digest,
)
from so101_demo.core.task_command import TaskCommand
from so101_demo.ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    ExecutorDispatchError,
    RuntimeDispatchResult,
)
from so101_demo.ports.task_planner import (
    PlannerCandidate,
    PlannerMetadata,
    PlannerProviderError,
)
from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
from so101_demo.profiling.session import build_profiler
from so101_demo.profiling.wrappers import profile_executor


VALID_CANDIDATE = {
    "target_object": "plastic_cup",
    "action": "pick",
    "constraints": {},
}
VALID_OUTCOME = {"outcome": "supported", "command": VALID_CANDIDATE}
METADATA = PlannerMetadata(
    provider="deepseek",
    model="deepseek-v4-flash",
    latency_ms=2,
    input_tokens=5,
    output_tokens=6,
    cache_hit_tokens=0,
    fallback_used=False,
)


class StubPlanner:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[str] = []

    def plan(self, instruction: str) -> PlannerCandidate:
        self.calls.append(instruction)
        if isinstance(self.value, Exception):
            raise self.value
        return PlannerCandidate(value=self.value, metadata=METADATA)


@dataclass
class FakeExecutor:
    exit_code: int = 0
    session_id: str = "runtime-001"
    calls: list[DynamicCupPickPlaceRequest] = field(default_factory=list)

    def dispatch(self, request: DynamicCupPickPlaceRequest) -> RuntimeDispatchResult:
        self.calls.append(request)
        return RuntimeDispatchResult(
            exit_code=self.exit_code,
            runtime_session_id=self.session_id,
        )


@dataclass
class RaisingExecutor:
    error: Exception
    calls: list[DynamicCupPickPlaceRequest] = field(default_factory=list)

    def dispatch(self, request: DynamicCupPickPlaceRequest) -> RuntimeDispatchResult:
        self.calls.append(request)
        raise self.error


@dataclass
class MalformedResultExecutor:
    result: object
    calls: list[DynamicCupPickPlaceRequest] = field(default_factory=list)

    def dispatch(self, request: DynamicCupPickPlaceRequest) -> RuntimeDispatchResult:
        self.calls.append(request)
        return self.result  # type: ignore[return-value]


def make_request(**changes: object) -> AgentRequest:
    values: dict[str, object] = {
        "request_id": "req-001",
        "instruction": "帮我拿杯子",
        "mode": "preview",
        "execute": False,
        "backend": "mujoco",
        "confirmation_digest": None,
    }
    values.update(changes)
    if (
        values["mode"] == "execute"
        and values["execute"] is True
        and "confirmation_digest" not in changes
        and isinstance(values["instruction"], str)
    ):
        values["confirmation_digest"] = build_confirmation_digest(
            values["instruction"].strip(),
            TaskCommand("plastic_cup", "pick", ()),
            "dynamic_cup_pick_place",
            METADATA,
        )
    return AgentRequest(**values)  # type: ignore[arg-type]


def make_agent(
    planner_value: object = VALID_OUTCOME,
    executor: FakeExecutor | None = None,
) -> tuple[TextAgent, StubPlanner, FakeExecutor]:
    actual_executor = executor or FakeExecutor()
    planner = StubPlanner(planner_value)
    return TextAgent(planner, actual_executor), planner, actual_executor


def assert_terminal_only(result_status: AgentStatus, trace: tuple[AgentStatus, ...]) -> None:
    assert trace == (result_status,)


def test_malformed_request_id_uses_safe_result_sentinel_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(request_id=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.request_id == ""
    assert result.reason_code == "INPUT_INVALID"
    assert result.to_dict() == {
        "request_id": "",
        "status": "COMMAND_INVALID",
        "dispatch": False,
        "state_trace": ["COMMAND_INVALID"],
        "reason_code": "INPUT_INVALID",
    }
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_truthy_integer_execute_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(execute=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_truthy_integer_skip_confirmation_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(skip_confirmation=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_nonstring_instruction_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(instruction=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_nonstring_mode_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(mode=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_nonstring_backend_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(backend=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_empty_request_id_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(request_id="   "))

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "REQUEST_ID_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_invalid_instruction_never_calls_planner_or_executor() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(instruction="   "))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == []
    assert executor.calls == []


def test_provider_failure_never_dispatches() -> None:
    agent, planner, executor = make_agent(PlannerProviderError("PLANNER_CHAIN_FAILED"))

    result = agent.handle(make_request())

    assert result.status is AgentStatus.PLANNER_FAILED
    assert result.reason_code == "PLANNER_CHAIN_FAILED"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_generic_planner_exception_propagates_without_dispatch() -> None:
    agent, planner, executor = make_agent(RuntimeError("unexpected planner failure"))

    with pytest.raises(RuntimeError, match="unexpected planner failure"):
        agent.handle(make_request())

    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_semantically_invalid_candidate_never_dispatches() -> None:
    candidate = {
        "target_object": "plastic_cup",
        "action": "place",
        "constraints": {},
    }
    agent, planner, executor = make_agent(
        {"outcome": "supported", "command": candidate}
    )

    result = agent.handle(make_request())

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "COMMAND_INVALID"
    assert result.metadata is METADATA
    assert result.command is None
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_nonempty_constraint_is_rejected_without_dispatch() -> None:
    candidate = {**VALID_CANDIDATE, "constraints": {"speed": "slow"}}
    agent, planner, executor = make_agent(
        {"outcome": "supported", "command": candidate}
    )

    result = agent.handle(make_request())

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "CONSTRAINT_UNCONSUMED"
    assert result.command is not None
    assert result.command.to_dict() == candidate
    assert result.capability is None
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_preview_returns_normalized_command_without_dispatch() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request())

    assert result.status is AgentStatus.DISPATCH_PREVIEW
    assert result.reason_code is None
    assert result.command is not None
    assert result.command.to_dict() == VALID_CANDIDATE
    assert result.capability == "dynamic_cup_pick_place"
    assert result.dispatch is False
    assert result.runtime_session_id is None
    assert result.confirmation_digest == build_confirmation_digest(
        "帮我拿杯子",
        TaskCommand("plastic_cup", "pick", ()),
        "dynamic_cup_pick_place",
        METADATA,
    )
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_mode_flag_mismatch_is_rejected_after_capability_resolution() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(mode="execute", execute=False))

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "EXPLICIT_EXECUTE_REQUIRED"
    assert result.capability == "dynamic_cup_pick_place"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_preview_mode_with_execute_flag_is_rejected() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(mode="preview", execute=True))

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "EXPLICIT_EXECUTE_REQUIRED"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == []


def test_wrong_backend_is_rejected_before_claim_or_dispatch() -> None:
    agent, planner, executor = make_agent()
    request = make_request(mode="execute", execute=True, backend="gazebo")

    result = agent.handle(request)
    retry = agent.handle(request)

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "BACKEND_NOT_QUALIFIED"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert retry.reason_code == "BACKEND_NOT_QUALIFIED"
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert executor.calls == []


def test_success_dispatches_once_with_exact_runtime_trace() -> None:
    agent, planner, executor = make_agent()
    request = make_request(mode="execute", execute=True)

    result = agent.handle(request)

    assert result.status is AgentStatus.RUNTIME_COMPLETED
    assert result.reason_code is None
    assert result.dispatch is True
    assert result.runtime_session_id == "runtime-001"
    assert result.state_trace == (
        AgentStatus.RUNTIME_STARTED,
        AgentStatus.RUNTIME_COMPLETED,
    )
    assert planner.calls == ["帮我拿杯子"]
    assert executor.calls == [
        DynamicCupPickPlaceRequest(
            request_id="req-001",
            capability="dynamic_cup_pick_place",
            backend="mujoco",
            scene_source="observe_only",
            target_object="plastic_cup",
            action="pick",
        )
    ]


def test_duplicate_request_is_rejected_without_second_dispatch() -> None:
    agent, planner, executor = make_agent()
    request = make_request(mode="execute", execute=True)

    agent.handle(request)
    result = agent.handle(request)

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "DUPLICATE_REQUEST_ID"
    assert result.dispatch is False
    assert_terminal_only(result.status, result.state_trace)
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert len(executor.calls) == 1


def test_nonzero_runtime_result_claims_request_id() -> None:
    executor = FakeExecutor(exit_code=9, session_id="runtime-009")
    agent, planner, _ = make_agent(executor=executor)
    request = make_request(mode="execute", execute=True)

    result = agent.handle(request)
    retry = agent.handle(request)

    assert result.status is AgentStatus.RUNTIME_FAILED
    assert result.reason_code == "RUNTIME_FAILED"
    assert result.dispatch is True
    assert result.runtime_session_id == "runtime-009"
    assert result.state_trace == (
        AgentStatus.RUNTIME_STARTED,
        AgentStatus.RUNTIME_FAILED,
    )
    assert result.confirmation_mode == "digest"
    assert retry.status is AgentStatus.DISPATCH_REJECTED
    assert retry.reason_code == "DUPLICATE_REQUEST_ID"
    assert_terminal_only(retry.status, retry.state_trace)
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert len(executor.calls) == 1


def test_executor_domain_error_is_terminal_and_claims_request_id() -> None:
    executor = RaisingExecutor(ExecutorDispatchError("EXECUTOR_UNAVAILABLE"))
    agent, planner, _ = make_agent(executor=executor)  # type: ignore[arg-type]
    request = make_request(mode="execute", execute=True)

    result = agent.handle(request)
    retry = agent.handle(request)

    assert result.status is AgentStatus.RUNTIME_FAILED
    assert result.reason_code == "EXECUTOR_UNAVAILABLE"
    assert result.dispatch is True
    assert result.runtime_session_id is None
    assert result.state_trace == (
        AgentStatus.RUNTIME_STARTED,
        AgentStatus.RUNTIME_FAILED,
    )
    assert result.confirmation_mode == "digest"
    assert retry.status is AgentStatus.DISPATCH_REJECTED
    assert retry.reason_code == "DUPLICATE_REQUEST_ID"
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert len(executor.calls) == 1


def test_malformed_executor_result_is_terminal_and_claims_request_id() -> None:
    executor = MalformedResultExecutor(
        RuntimeDispatchResult(exit_code="0", runtime_session_id="runtime-001"),  # type: ignore[arg-type]
    )
    agent, planner, _ = make_agent(executor=executor)  # type: ignore[arg-type]
    request = make_request(mode="execute", execute=True)

    result = agent.handle(request)
    retry = agent.handle(request)

    assert result.status is AgentStatus.RUNTIME_FAILED
    assert result.reason_code == "EXECUTOR_RESULT_INVALID"
    assert result.dispatch is True
    assert result.runtime_session_id is None
    assert result.state_trace == (
        AgentStatus.RUNTIME_STARTED,
        AgentStatus.RUNTIME_FAILED,
    )
    assert result.confirmation_mode == "digest"
    assert retry.status is AgentStatus.DISPATCH_REJECTED
    assert retry.reason_code == "DUPLICATE_REQUEST_ID"
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert len(executor.calls) == 1


def test_profiled_malformed_executor_object_preserves_stable_terminal_result(
    tmp_path: Path,
) -> None:
    malformed = MalformedResultExecutor(object())
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="text-agent",
            request_id="req-001",
        )
    )
    assert profiler is not None
    planner = StubPlanner(VALID_OUTCOME)
    agent = TextAgent(planner, profile_executor(malformed, profiler))

    result = agent.handle(make_request(mode="execute", execute=True))
    profiler.close()

    assert result.status is AgentStatus.RUNTIME_FAILED
    assert result.reason_code == "EXECUTOR_RESULT_INVALID"
    assert result.dispatch is True
    assert result.runtime_session_id is None


def test_generic_executor_exception_propagates_after_claim() -> None:
    executor = RaisingExecutor(RuntimeError("programmer error"))
    agent, planner, _ = make_agent(executor=executor)  # type: ignore[arg-type]
    request = make_request(mode="execute", execute=True)

    with pytest.raises(RuntimeError, match="programmer error"):
        agent.handle(request)

    retry = agent.handle(request)
    assert retry.status is AgentStatus.DISPATCH_REJECTED
    assert retry.reason_code == "DUPLICATE_REQUEST_ID"
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert len(executor.calls) == 1


def test_dispatcher_exposes_stable_constraint_and_capability_codes() -> None:
    dispatcher = TaskDispatcher()
    constrained = TaskCommand("plastic_cup", "pick", (("speed", "slow"),))
    unsupported = TaskCommand("plastic_cup", "place", ())  # type: ignore[arg-type]

    with pytest.raises(ValueError) as constrained_error:
        dispatcher.resolve(constrained, "req-001")
    with pytest.raises(ValueError) as unsupported_error:
        dispatcher.resolve(unsupported, "req-001")

    assert constrained_error.value.code == "CONSTRAINT_UNCONSUMED"  # type: ignore[attr-defined]
    assert unsupported_error.value.code == "CAPABILITY_UNSUPPORTED"  # type: ignore[attr-defined]


def test_to_dict_projects_only_approved_planner_and_trace_fields() -> None:
    agent, _, _ = make_agent()

    result = agent.handle(make_request())

    assert result.to_dict() == {
        "request_id": "req-001",
        "status": "DISPATCH_PREVIEW",
        "dispatch": False,
        "state_trace": ["DISPATCH_PREVIEW"],
        "planner": {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "latency_ms": 2,
            "input_tokens": 5,
            "output_tokens": 6,
            "cache_hit_tokens": 0,
            "fallback_used": False,
        },
        "planner_outcome": "supported",
        "command": VALID_CANDIDATE,
        "capability": "dynamic_cup_pick_place",
        "confirmation_digest": build_confirmation_digest(
            "帮我拿杯子",
            TaskCommand("plastic_cup", "pick", ()),
            "dynamic_cup_pick_place",
            METADATA,
        ),
    }


def test_to_dict_does_not_expose_mutable_command_state() -> None:
    agent, _, _ = make_agent()

    result = agent.handle(make_request())
    assert result.command is not None
    assert result.command.to_dict() == VALID_CANDIDATE
    with pytest.raises(FrozenInstanceError):
        result.command.constraints = (("speed", "slow"),)

    first_serialized = result.to_dict()
    second_serialized = result.to_dict()
    first_command = first_serialized["command"]

    assert isinstance(first_command, dict)
    first_command["constraints"]["speed"] = "slow"
    assert second_serialized["command"] == VALID_CANDIDATE
    assert result.command.to_dict() == VALID_CANDIDATE


def test_profiled_agent_preserves_result_and_records_internal_stages(
    tmp_path: Path,
) -> None:
    baseline, _, _ = make_agent()
    baseline_result = baseline.handle(make_request())
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="text-agent",
            request_id="req-001",
        )
    )
    assert profiler is not None
    planner = StubPlanner(VALID_OUTCOME)
    profiled = TextAgent(planner, FakeExecutor(), profiler=profiler)

    profiled_result = profiled.handle(make_request())
    profiler.close()

    assert profiled_result == baseline_result
    complete_events = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/text-agent.events.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if '"event_type":"span_complete"' in line
    ]
    assert [event["name"] for event in complete_events] == [
        "agent.validate_input",
        "agent.validate_command",
        "agent.total",
    ]
    assert complete_events[0]["outcome"] == "accepted"
    assert complete_events[1]["attributes"] == {"planner_outcome": "supported"}
    assert complete_events[2]["attributes"] == {
        "reason_code": None,
        "status": "DISPATCH_PREVIEW",
    }
