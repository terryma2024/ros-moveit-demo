"""Shared-state-machine composition for perception-driven execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..core.domain import ActionResult, State
from ..core.dynamic_pick import DYNAMIC_MOTION_STATES, ResolvedMotionTargets
from ..core.runner import ExecutionContext, StateAction
from ..core.workflow import SO101_WORKFLOW
from ..ports.evidence import PoseEvidence


class DynamicExecutionPort(Protocol):
    def perform(self, state: State, target: PoseEvidence | None) -> ActionResult: ...


class MotionTargetProvider(Protocol):
    def target_for(self, state: State) -> PoseEvidence: ...


@dataclass(frozen=True, slots=True)
class DynamicStateAction(StateAction):
    state: State
    execution: DynamicExecutionPort
    targets: MotionTargetProvider

    def run(self, context: ExecutionContext) -> ActionResult:
        if context.state is not self.state:
            raise ValueError("dynamic action invoked for a different state")
        target = self.targets.target_for(self.state) if self.state in DYNAMIC_MOTION_STATES else None
        return self.execution.perform(self.state, target)


def build_dynamic_actions(
    execution: DynamicExecutionPort,
    targets: MotionTargetProvider | ResolvedMotionTargets,
) -> dict[State, StateAction]:
    """Bind dynamic targets to the repository's sole workflow definition."""

    return {
        state: DynamicStateAction(state, execution, targets)
        for state in SO101_WORKFLOW.action_states
    }
