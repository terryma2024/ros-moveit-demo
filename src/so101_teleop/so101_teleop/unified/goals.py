"""Registry of owned arm and gripper goals.

The registry is the only place that knows the real ROS goal identity of an accepted
action. Cancellation and observation are plain callables so the safety lane can run them
without taking any ordinary mutation lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .contracts import ActionKey, ActionTerminal, MutationError


@dataclass(frozen=True)
class OwnedGoal:
    key: ActionKey
    cancel: Callable[[], Awaitable[bool]]
    observe: Callable[[], Awaitable[ActionTerminal]]


class GoalRegistry:
    def __init__(self) -> None:
        self._goals: dict[tuple[str, str, str], OwnedGoal] = {}

    @staticmethod
    def _ident(key: ActionKey) -> tuple[str, str, str]:
        return (key.operation_id, key.child_id, key.goal_uuid)

    def register(
        self,
        key: ActionKey,
        *,
        cancel: Callable[[], Awaitable[bool]],
        observe: Callable[[], Awaitable[ActionTerminal]],
    ) -> None:
        self._goals[self._ident(key)] = OwnedGoal(key=key, cancel=cancel, observe=observe)

    def require(self, key: ActionKey) -> OwnedGoal:
        goal = self._goals.get(self._ident(key))
        if goal is None:
            raise MutationError(
                f"UNKNOWN_GOAL: {key.operation_id}/{key.child_id}/{key.goal_uuid}"
            )
        return goal

    def known(self) -> tuple[ActionKey, ...]:
        return tuple(goal.key for goal in self._goals.values())

    def forget(self, key: ActionKey) -> None:
        self._goals.pop(self._ident(key), None)
