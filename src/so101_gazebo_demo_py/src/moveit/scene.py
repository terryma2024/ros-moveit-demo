"""Convergent Planning Scene attachment and world membership boundary."""

from dataclasses import dataclass
import time
from typing import Any

from ..domain import ActionResult, ActionStatus, Failure, FailureCategory
from ..policy_config import Pose3D


@dataclass(frozen=True, slots=True)
class SceneObservation:
    world_objects: frozenset[str]
    attached_object: str | None
    attached_link: str | None
    world_pose: Pose3D | None = None

    def required_world_objects_present(self, names: tuple[str, ...]) -> bool:
        return set(names) <= self.world_objects


class MoveItSceneClient:
    def __init__(self, backend: Any) -> None: self._backend=backend

    def _converge(self, predicate, timeout_s: float) -> ActionResult:
        deadline=time.monotonic()+timeout_s
        while time.monotonic()<deadline:
            if predicate(self._backend.observe()): return ActionResult(ActionStatus.SUCCEEDED)
            time.sleep(.001)
        return ActionResult(ActionStatus.TIMED_OUT, Failure(FailureCategory.MOVEIT_SCENE,"MOVEIT_SCENE_CONVERGENCE_TIMEOUT","scene did not converge"))

    def attach_task_object(self, object_id: str, link_name: str, touch_links: tuple[str,...], timeout_s: float=2.) -> ActionResult:
        if link_name != "gripper" or touch_links != ("gripper","jaw"):
            return ActionResult(ActionStatus.FAILED, Failure(FailureCategory.MOVEIT_SCENE,"MOVEIT_SCENE_ATTACHMENT_CONTRACT","invalid attachment links"))
        if not self._backend.apply(("attach",object_id,link_name,touch_links)):
            return ActionResult(ActionStatus.FAILED, Failure(FailureCategory.MOVEIT_SCENE,"MOVEIT_SCENE_APPLY_FAILED","apply failed"))
        return self._converge(lambda value: value.attached_object==object_id and value.attached_link==link_name, timeout_s)

    def detach_task_object(self, object_id: str, world_pose: Pose3D, timeout_s: float=2.) -> ActionResult:
        if not self._backend.apply(("detach",object_id,world_pose)):
            return ActionResult(ActionStatus.FAILED, Failure(FailureCategory.MOVEIT_SCENE,"MOVEIT_SCENE_APPLY_FAILED","apply failed"))
        return self._converge(lambda value: object_id in value.world_objects and value.attached_object is None and value.world_pose==world_pose, timeout_s)

    def observe(self, timeout_s: float) -> SceneObservation:
        del timeout_s
        return self._backend.observe()
