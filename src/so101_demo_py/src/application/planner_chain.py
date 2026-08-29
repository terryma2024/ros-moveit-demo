from dataclasses import replace

from ..ports.task_planner import PlannerCandidate, PlannerPort, PlannerProviderError


class PlannerChain:
    def __init__(self, primary: PlannerPort, fallback: PlannerPort) -> None:
        self._primary = primary
        self._fallback = fallback

    def plan(self, instruction: str) -> PlannerCandidate:
        try:
            return self._primary.plan(instruction)
        except PlannerProviderError:
            try:
                candidate = self._fallback.plan(instruction)
            except PlannerProviderError as fallback_error:
                raise PlannerProviderError("PLANNER_CHAIN_FAILED") from fallback_error
            return replace(candidate, metadata=replace(candidate.metadata, fallback_used=True))
