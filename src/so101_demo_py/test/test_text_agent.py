from __future__ import annotations

from dataclasses import dataclass, field
import pytest

from so101_demo.application.text_agent import AgentRequest, AgentStatus, TextAgent
from so101_demo.ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    RuntimeDispatchResult,
)
from so101_demo.ports.task_planner import (
    PlannerCandidate,
    PlannerMetadata,
    PlannerProviderError,
)


VALID_CANDIDATE = {
    "target_object": "plastic_cup",
    "action": "pick",
    "constraints": {},
}
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


def make_request(**changes: object) -> AgentRequest:
    values: dict[str, object] = {
        "request_id": "req-001",
        "instruction": "帮我拿杯子",
        "mode": "preview",
        "execute": False,
        "backend": "mujoco",
    }
    values.update(changes)
    return AgentRequest(**values)  # type: ignore[arg-type]


def make_agent(
    planner_value: object = VALID_CANDIDATE,
    executor: FakeExecutor | None = None,
) -> tuple[TextAgent, StubPlanner, FakeExecutor]:
    actual_executor = executor or FakeExecutor()
    planner = StubPlanner(planner_value)
    return TextAgent(planner, actual_executor), planner, actual_executor


def assert_terminal_only(result_status: AgentStatus, trace: tuple[AgentStatus, ...]) -> None:
    assert trace == (result_status,)


def test_malformed_request_id_is_rejected_before_planning() -> None:
    agent, planner, executor = make_agent()

    result = agent.handle(make_request(request_id=1))

    assert result.status is AgentStatus.COMMAND_INVALID
    assert result.reason_code == "INPUT_INVALID"
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
    agent, planner, executor = make_agent(candidate)

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
    agent, planner, executor = make_agent(candidate)

    result = agent.handle(make_request())

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "CONSTRAINT_UNCONSUMED"
    assert result.command == candidate
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
    assert result.command == VALID_CANDIDATE
    assert result.capability == "dynamic_cup_pick_place"
    assert result.dispatch is False
    assert result.runtime_session_id is None
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
    assert retry.status is AgentStatus.DISPATCH_REJECTED
    assert retry.reason_code == "DUPLICATE_REQUEST_ID"
    assert_terminal_only(retry.status, retry.state_trace)
    assert planner.calls == ["帮我拿杯子", "帮我拿杯子"]
    assert len(executor.calls) == 1


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
        "command": VALID_CANDIDATE,
        "capability": "dynamic_cup_pick_place",
    }


def test_to_dict_does_not_expose_mutable_command_state() -> None:
    agent, _, _ = make_agent()

    result = agent.handle(make_request())
    serialized = result.to_dict()
    command = serialized["command"]

    assert isinstance(command, dict)
    command["constraints"]["speed"] = "slow"
    assert result.command == VALID_CANDIDATE
