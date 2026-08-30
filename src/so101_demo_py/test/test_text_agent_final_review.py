from __future__ import annotations

from dataclasses import dataclass, field
from threading import Barrier, BrokenBarrierError, Event, Lock, Thread

import pytest

from so101_demo.application.text_agent import AgentStatus, TextAgent
from so101_demo.ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    RuntimeDispatchResult,
)
from so101_demo.ports.task_planner import PlannerCandidate, PlannerMetadata


SUPPORTED_COMMAND = {
    "target_object": "plastic_cup",
    "action": "pick",
    "constraints": {},
}
SUPPORTED_OUTCOME = {"outcome": "supported", "command": SUPPORTED_COMMAND}
DEEPSEEK_METADATA = PlannerMetadata(
    provider="deepseek",
    model="deepseek-v4-flash",
    latency_ms=99,
    input_tokens=11,
    output_tokens=7,
    cache_hit_tokens=2,
    fallback_used=False,
)
EXPECTED_PREVIEW_DIGEST = (
    "sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb"
)


@dataclass(frozen=True)
class ConfirmedRequest:
    request_id: str = "req-final-review"
    instruction: str = "Pick the plastic cup."
    mode: str = "preview"
    execute: bool = False
    backend: str = "mujoco"
    confirmation_digest: object = None
    skip_confirmation: object = False
    execution_provenance: object = None


class ScriptedPlanner:
    def __init__(
        self,
        values: list[object],
        metadata: list[PlannerMetadata] | None = None,
    ) -> None:
        self._values = iter(values)
        self._metadata = iter(metadata or [DEEPSEEK_METADATA] * len(values))
        self.calls: list[str] = []

    def plan(self, instruction: str) -> PlannerCandidate:
        self.calls.append(instruction)
        return PlannerCandidate(next(self._values), next(self._metadata))


@dataclass
class RecordingExecutor:
    calls: list[DynamicCupPickPlaceRequest] = field(default_factory=list)

    def dispatch(self, request: DynamicCupPickPlaceRequest) -> RuntimeDispatchResult:
        self.calls.append(request)
        return RuntimeDispatchResult(0, "runtime-final-review")


class RejectingDispatcher:
    def resolve(self, *_args: object) -> DynamicCupPickPlaceRequest:
        raise AssertionError("unsupported and ambiguous outcomes must not reach Dispatcher")


def _preview(
    planner: ScriptedPlanner,
    executor: RecordingExecutor | None = None,
    *,
    dispatcher: object | None = None,
    instruction: str = "Pick the plastic cup.",
):
    actual_executor = executor or RecordingExecutor()
    agent = TextAgent(planner, actual_executor, dispatcher=dispatcher)
    result = agent.handle(ConfirmedRequest(instruction=instruction))  # type: ignore[arg-type]
    return agent, actual_executor, result


def test_supported_outcome_preview_emits_hand_derived_versioned_digest() -> None:
    """Catches accepting a command without binding the human preview to exact semantics."""

    _agent, executor, result = _preview(ScriptedPlanner([SUPPORTED_OUTCOME]))

    assert result.status is AgentStatus.DISPATCH_PREVIEW
    assert result.to_dict()["planner_outcome"] == "supported"
    assert result.to_dict()["confirmation_digest"] == EXPECTED_PREVIEW_DIGEST
    assert executor.calls == []


@pytest.mark.parametrize(
    ("outcome", "reason_code"),
    [
        ({"outcome": "unsupported"}, "PLANNER_OUTCOME_UNSUPPORTED"),
        ({"outcome": "ambiguous"}, "PLANNER_OUTCOME_AMBIGUOUS"),
    ],
)
def test_non_supported_outcome_terminates_before_dispatcher_and_executor(
    outcome: dict[str, object], reason_code: str
) -> None:
    """Catches routing a representable non-supported planner branch as a TaskCommand."""

    executor = RecordingExecutor()
    _agent, _executor, result = _preview(
        ScriptedPlanner([outcome]),
        executor,
        dispatcher=RejectingDispatcher(),
    )

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == reason_code
    assert result.to_dict()["planner_outcome"] == outcome["outcome"]
    assert executor.calls == []


@pytest.mark.parametrize(
    "instruction",
    [
        "Do not pick the plastic cup.",
        "Pick the plastic cup and do not pick it.",
        "Maybe pick it, or perhaps leave it alone.",
        "Pick the metal bottle.",
    ],
)
def test_valid_looking_command_for_risky_instruction_cannot_execute_without_confirmation(
    instruction: str,
) -> None:
    """Catches an untrusted planner coercing risky text into the sole executable command."""

    planner = ScriptedPlanner([SUPPORTED_OUTCOME])
    executor = RecordingExecutor()
    agent = TextAgent(planner, executor)

    result = agent.handle(  # type: ignore[arg-type]
        ConfirmedRequest(instruction=instruction, mode="execute", execute=True)
    )

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == "CONFIRMATION_DIGEST_REQUIRED"
    assert result.dispatch is False
    assert executor.calls == []


@pytest.mark.parametrize(
    ("confirmation_digest", "reason_code"),
    [
        ("", "CONFIRMATION_DIGEST_REQUIRED"),
        ("not-a-digest", "CONFIRMATION_DIGEST_INVALID"),
        ("sha256:v1:" + "0" * 64, "CONFIRMATION_DIGEST_MISMATCH"),
    ],
)
def test_execute_rejects_absent_malformed_and_mismatched_confirmation_before_claim(
    confirmation_digest: str, reason_code: str
) -> None:
    """Catches confirmation syntax or equality checks occurring after request claiming."""

    planner = ScriptedPlanner([SUPPORTED_OUTCOME, SUPPORTED_OUTCOME])
    executor = RecordingExecutor()
    agent = TextAgent(planner, executor)
    rejected = agent.handle(  # type: ignore[arg-type]
        ConfirmedRequest(
            mode="execute",
            execute=True,
            confirmation_digest=confirmation_digest,
        )
    )
    preview_after_rejection = agent.handle(  # type: ignore[arg-type]
        ConfirmedRequest(mode="preview", execute=False)
    )

    assert rejected.status is AgentStatus.DISPATCH_REJECTED
    assert rejected.reason_code == reason_code
    assert rejected.dispatch is False
    assert preview_after_rejection.status is AgentStatus.DISPATCH_PREVIEW
    assert executor.calls == []


def test_execute_can_explicitly_skip_confirmation_without_a_preview_digest() -> None:
    """Catches a requested confirmation bypass still being blocked by the digest gate."""

    planner = ScriptedPlanner([SUPPORTED_OUTCOME])
    executor = RecordingExecutor()
    agent = TextAgent(planner, executor)

    result = agent.handle(  # type: ignore[arg-type]
        ConfirmedRequest(
            mode="execute",
            execute=True,
            confirmation_digest=None,
            skip_confirmation=True,
        )
    )

    assert result.status is AgentStatus.RUNTIME_COMPLETED
    assert result.dispatch is True
    assert result.to_dict()["confirmation_mode"] == "skipped"
    assert len(executor.calls) == 1


@pytest.mark.parametrize(
    ("agent_request", "reason_code"),
    [
        (
            ConfirmedRequest(skip_confirmation=True),
            "CONFIRMATION_BYPASS_REQUIRES_EXECUTE",
        ),
        (
            ConfirmedRequest(
                mode="execute",
                execute=True,
                confirmation_digest=EXPECTED_PREVIEW_DIGEST,
                skip_confirmation=True,
            ),
            "CONFIRMATION_MODE_CONFLICT",
        ),
    ],
)
def test_invalid_confirmation_bypass_configuration_rejects_before_planning(
    agent_request: ConfirmedRequest,
    reason_code: str,
) -> None:
    """Catches ambiguous or non-execute bypass requests reaching the provider."""

    planner = ScriptedPlanner([SUPPORTED_OUTCOME])
    executor = RecordingExecutor()
    agent = TextAgent(planner, executor)

    result = agent.handle(agent_request)  # type: ignore[arg-type]

    assert result.status is AgentStatus.DISPATCH_REJECTED
    assert result.reason_code == reason_code
    assert result.dispatch is False
    assert planner.calls == []
    assert executor.calls == []


@pytest.mark.parametrize("mutation", ["instruction", "command", "provider", "model"])
def test_preview_digest_rejects_execute_candidate_mutation(mutation: str) -> None:
    """Catches a preview digest that omits any immutable semantic/provider field."""

    preview_value = SUPPORTED_OUTCOME
    execute_value: object = SUPPORTED_OUTCOME
    preview_metadata = DEEPSEEK_METADATA
    execute_metadata = DEEPSEEK_METADATA
    execute_instruction = "Pick the plastic cup."
    dispatcher = None
    if mutation == "instruction":
        execute_instruction = "Pick the plastic cup now."
    elif mutation == "command":
        execute_value = {
            "outcome": "supported",
            "command": {
                **SUPPORTED_COMMAND,
                "constraints": {"speed": "slow"},
            },
        }
        dispatcher = ConstraintAcceptingDispatcher()
    elif mutation == "provider":
        execute_metadata = PlannerMetadata(
            "ollama", "deepseek-v4-flash", 99, 11, 7, 2, False
        )
    elif mutation == "model":
        execute_metadata = PlannerMetadata(
            "deepseek", "other-model", 99, 11, 7, 2, False
        )

    planner = ScriptedPlanner(
        [preview_value, execute_value],
        [preview_metadata, execute_metadata],
    )
    executor = RecordingExecutor()
    agent = TextAgent(planner, executor, dispatcher=dispatcher)
    preview = agent.handle(ConfirmedRequest())  # type: ignore[arg-type]
    execute = agent.handle(  # type: ignore[arg-type]
        ConfirmedRequest(
            instruction=execute_instruction,
            mode="execute",
            execute=True,
            confirmation_digest=preview.to_dict()["confirmation_digest"],
        )
    )

    assert execute.status is AgentStatus.DISPATCH_REJECTED
    assert execute.reason_code == "CONFIRMATION_DIGEST_MISMATCH"
    assert execute.dispatch is False
    assert executor.calls == []


class ConstraintAcceptingDispatcher:
    def resolve(self, command, request_id: str) -> DynamicCupPickPlaceRequest:
        return DynamicCupPickPlaceRequest(
            request_id=request_id,
            capability="dynamic_cup_pick_place",
            backend="mujoco",
            scene_source="observe_only",
            target_object=command.target_object,
            action=command.action,
        )


class BarrierClaims(set[str]):
    """Forces both unlocked membership checks to observe the pre-claim state."""

    def __init__(self) -> None:
        super().__init__()
        self.membership_barrier = Barrier(2)

    def __contains__(self, value: object) -> bool:
        try:
            self.membership_barrier.wait(timeout=0.25)
        except BrokenBarrierError:
            pass
        return super().__contains__(value)


@dataclass
class BlockingExecutor:
    calls: list[DynamicCupPickPlaceRequest] = field(default_factory=list)
    call_lock: Lock = field(default_factory=Lock)
    entered: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)

    def dispatch(self, request: DynamicCupPickPlaceRequest) -> RuntimeDispatchResult:
        with self.call_lock:
            self.calls.append(request)
        self.entered.set()
        assert self.release.wait(timeout=2)
        return RuntimeDispatchResult(0, "runtime-concurrent")


def test_concurrent_same_request_id_is_claimed_atomically_before_blocking_executor() -> None:
    """Catches separate unlocked membership and add operations under concurrent callers."""

    planner = ScriptedPlanner([SUPPORTED_OUTCOME, SUPPORTED_OUTCOME, SUPPORTED_OUTCOME])
    executor = BlockingExecutor()
    agent = TextAgent(planner, executor)
    preview = agent.handle(ConfirmedRequest())  # type: ignore[arg-type]
    digest = preview.to_dict()["confirmation_digest"]
    agent._claimed_request_ids = BarrierClaims()  # type: ignore[attr-defined]
    start = Barrier(3)
    results: list[object] = []

    def invoke() -> None:
        start.wait()
        results.append(
            agent.handle(  # type: ignore[arg-type]
                ConfirmedRequest(
                    mode="execute",
                    execute=True,
                    confirmation_digest=digest,
                )
            )
        )

    workers = [Thread(target=invoke), Thread(target=invoke)]
    for worker in workers:
        worker.start()
    start.wait()
    assert executor.entered.wait(timeout=2)
    executor.release.set()
    for worker in workers:
        worker.join(timeout=2)
        assert not worker.is_alive()

    assert len(executor.calls) == 1
    assert sorted(result.status.value for result in results) == [
        "DISPATCH_REJECTED",
        "RUNTIME_COMPLETED",
    ]
    assert sorted(result.reason_code or "NONE" for result in results) == [
        "DUPLICATE_REQUEST_ID",
        "NONE",
    ]
