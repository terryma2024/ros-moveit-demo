"""Sequential recovery execution."""

from typing import Callable, Mapping
from ..domain import ActionResult, ActionStatus, State


class RecoveryCoordinator:
    def __init__(self, actions: Mapping[State,Callable[[],ActionResult]]) -> None: self.actions=actions
    def execute(self, path: tuple[State,...]) -> ActionResult:
        for state in path:
            result=self.actions[state]()
            if result.status is not ActionStatus.SUCCEEDED: return result
        return ActionResult(ActionStatus.SUCCEEDED)
