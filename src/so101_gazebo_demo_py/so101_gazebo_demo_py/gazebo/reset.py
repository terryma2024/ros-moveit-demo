"""Deterministic world-reset sequence with postcondition proof."""

from typing import Callable
from ..domain import ActionResult, ActionStatus


class WorldResetCoordinator:
    def __init__(self, detach_gazebo: Callable[[],ActionResult], set_object_pose: Callable[[],ActionResult],
                 restore_scene: Callable[[],ActionResult], home_arm: Callable[[],ActionResult],
                 home_gripper: Callable[[],ActionResult], prove_convergence: Callable[[],ActionResult]) -> None:
        self._steps=(detach_gazebo,set_object_pose,restore_scene,home_arm,home_gripper,prove_convergence)

    def reset(self) -> ActionResult:
        for step in self._steps:
            result=step()
            if result.status is not ActionStatus.SUCCEEDED: return result
        return ActionResult(ActionStatus.SUCCEEDED)
