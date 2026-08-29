from dataclasses import dataclass

import pytest

from so101_demo.application.planner_chain import PlannerChain
from so101_demo.ports.task_planner import PlannerCandidate, PlannerMetadata, PlannerProviderError


@dataclass
class StubPlanner:
    provider: str
    outcome: object
    calls: int = 0

    def plan(self, instruction: str) -> PlannerCandidate:
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return PlannerCandidate(
            self.outcome,
            PlannerMetadata(self.provider, "model", 1, 3, 5, None, False),
        )


def test_primary_success_never_calls_fallback() -> None:
    primary = StubPlanner("deepseek", {"target_object": "plastic_cup", "action": "pick", "constraints": {}})
    fallback = StubPlanner("ollama", {})
    result = PlannerChain(primary, fallback).plan("帮我拿杯子")
    assert result.metadata.provider == "deepseek"
    assert (primary.calls, fallback.calls) == (1, 0)


def test_semantically_invalid_primary_candidate_is_not_repaired_by_fallback() -> None:
    primary = StubPlanner("deepseek", {"target_object": "plastic_cup", "action": "place", "constraints": {}})
    fallback = StubPlanner("ollama", {"target_object": "plastic_cup", "action": "pick", "constraints": {}})
    result = PlannerChain(primary, fallback).plan("帮我拿杯子再放下")
    assert result.value["action"] == "place"
    assert (primary.calls, fallback.calls) == (1, 0)


def test_provider_failure_calls_fallback_once() -> None:
    primary = StubPlanner("deepseek", PlannerProviderError("DEEPSEEK_TIMEOUT"))
    fallback = StubPlanner("ollama", {"target_object": "plastic_cup", "action": "pick", "constraints": {}})
    result = PlannerChain(primary, fallback).plan("帮我拿杯子")
    assert result.metadata.fallback_used is True
    assert (primary.calls, fallback.calls) == (1, 1)


def test_both_provider_failures_stop_after_two_attempts() -> None:
    primary = StubPlanner("deepseek", PlannerProviderError("DEEPSEEK_TIMEOUT"))
    fallback = StubPlanner("ollama", PlannerProviderError("OLLAMA_UNAVAILABLE"))
    with pytest.raises(PlannerProviderError, match="PLANNER_CHAIN_FAILED"):
        PlannerChain(primary, fallback).plan("帮我拿杯子")
    assert (primary.calls, fallback.calls) == (1, 1)
