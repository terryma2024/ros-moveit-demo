"""Sequential recovery execution."""

from typing import Callable, Mapping

from ..domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from ..simulation.protocols import WorldReset


class WorldResetAction:
    """Recovery boundary that depends only on the Task 5 reset protocol."""

    def __init__(self, reset: WorldReset, keyframe: str = "task_start") -> None:
        self._reset = reset
        self._keyframe = keyframe

    def run(self) -> ActionResult:
        try:
            self._reset.reset(self._keyframe)
        except Exception as error:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.WORLD_INCONSISTENCY, "WORLD_RESET_FAILED", str(error)),
            )
        return ActionResult(ActionStatus.SUCCEEDED)


class RecoveryCoordinator:
    def __init__(self, actions: Mapping[State, Callable[[], ActionResult]]) -> None:
        self.actions = actions

    def execute(self, path: tuple[State, ...]) -> ActionResult:
        for state in path:
            result = self.actions[state]()
            if result.status is not ActionStatus.SUCCEEDED:
                return result
        return ActionResult(ActionStatus.SUCCEEDED)
