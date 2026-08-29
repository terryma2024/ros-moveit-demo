from __future__ import annotations

from ..core.task_command import TaskCommand
from ..ports.pick_place_executor import DynamicCupPickPlaceRequest


class DispatchRejectedError(ValueError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class TaskDispatcher:
    def resolve(
        self,
        command: TaskCommand,
        request_id: str,
    ) -> DynamicCupPickPlaceRequest:
        if command.constraints:
            raise DispatchRejectedError(
                "CONSTRAINT_UNCONSUMED",
                "constraint has no V5-T003 consumer",
            )
        if (command.target_object, command.action) != ("plastic_cup", "pick"):
            raise DispatchRejectedError(
                "CAPABILITY_UNSUPPORTED",
                "capability is unsupported",
            )
        return DynamicCupPickPlaceRequest(
            request_id=request_id,
            capability="dynamic_cup_pick_place",
            backend="mujoco",
            scene_source="observe_only",
            target_object="plastic_cup",
            action="pick",
        )
