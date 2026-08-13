"""Backend-independent ordering for the normal Gazebo pick-place workflow."""

from __future__ import annotations

from typing import Any, Protocol

from ...application.backend_execute import ExecuteBoundary
from ...core.domain import ActionResult, ActionStatus


class GazeboWorkflowOperations(Protocol):
    def arm(self, phase: str, state: Any) -> ActionResult: ...

    def gripper(self, phase: str, target: float) -> ActionResult: ...

    def physical(self, phase: str, attach: bool) -> ActionResult: ...

    def scene(self, phase: str, attach: bool) -> ActionResult: ...


def execute_gazebo_workflow(policy: Any, operations: GazeboWorkflowOperations) -> ExecuteBoundary:
    """Run each normal phase once and return the real terminal boundary."""

    ordered = (
        (
            "PREPARE_OPEN_GRIPPER",
            lambda: operations.gripper(
                "PREPARE_OPEN_GRIPPER", policy.gripper.preopen_q6
            ),
        ),
        (
            "MOVE_ABOVE_OBJECT",
            lambda: operations.arm(
                "MOVE_ABOVE_OBJECT", policy.states["MOVE_ABOVE_OBJECT"]
            ),
        ),
        ("DESCEND", lambda: operations.arm("DESCEND", policy.states["DESCEND"])),
        (
            "GRASP_CLOSE",
            lambda: operations.gripper("GRASP_CLOSE", policy.gripper.grasp_close_q6),
        ),
        (
            "ATTACH_PHYSICAL",
            lambda: operations.physical("ATTACH_PHYSICAL", True),
        ),
        ("ATTACH_MOVEIT", lambda: operations.scene("ATTACH_MOVEIT", True)),
        ("LIFT", lambda: operations.arm("LIFT", policy.states["LIFT"])),
        (
            "MOVE_ABOVE_PLACE",
            lambda: operations.arm(
                "MOVE_ABOVE_PLACE", policy.states["MOVE_ABOVE_PLACE"]
            ),
        ),
        (
            "DESCEND_TO_PLACE",
            lambda: operations.arm(
                "DESCEND_TO_PLACE", policy.states["DESCEND_TO_PLACE"]
            ),
        ),
        (
            "RELEASE_OPEN",
            lambda: operations.gripper("RELEASE_OPEN", policy.gripper.release_q6),
        ),
        (
            "DETACH_PHYSICAL",
            lambda: operations.physical("DETACH_PHYSICAL", False),
        ),
        ("DETACH_MOVEIT", lambda: operations.scene("DETACH_MOVEIT", False)),
        ("RETREAT", lambda: operations.arm("RETREAT", policy.states["RETREAT"])),
    )
    last = "NOT_STARTED"
    for phase, operation in ordered:
        last = phase
        action = operation()
        if action.status is not ActionStatus.SUCCEEDED:
            return ExecuteBoundary(phase, action, True)
    return ExecuteBoundary(last, ActionResult(ActionStatus.SUCCEEDED), True)
