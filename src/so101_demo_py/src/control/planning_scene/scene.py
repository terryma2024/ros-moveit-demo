"""Convergent Planning Scene collision-shadow boundary."""

import time
from dataclasses import dataclass
from typing import Any, Callable

from ...core.domain import ActionResult, ActionStatus, Failure, FailureCategory


@dataclass(frozen=True, slots=True)
class Pose3D:
    values: tuple[float, float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class SceneObservation:
    world_objects: frozenset[str]
    attached_object: str | None
    attached_link: str | None
    world_pose: Pose3D | None = None

    def required_world_objects_present(self, names: tuple[str, ...]) -> bool:
        return set(names) <= self.world_objects


class MoveItSceneClient:
    """Mutate only Planning Scene membership; never simulator physics."""

    def __init__(
        self,
        backend: Any,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._backend = backend
        self._monotonic = monotonic
        self._wait = wait

    def _converge(self, predicate: Callable[[Any], bool], timeout_s: float) -> ActionResult:
        deadline = self._monotonic() + timeout_s
        while self._monotonic() < deadline:
            if predicate(self._backend.observe()):
                return ActionResult(ActionStatus.SUCCEEDED)
            self._wait(0.001)
        return ActionResult(
            ActionStatus.TIMED_OUT,
            Failure(
                FailureCategory.MOVEIT_SCENE,
                "MOVEIT_SCENE_CONVERGENCE_TIMEOUT",
                "scene did not converge",
            ),
        )

    def attach_task_object(
        self,
        object_id: str,
        link_name: str,
        touch_links: tuple[str, ...],
        timeout_s: float = 2.0,
    ) -> ActionResult:
        if link_name != "gripper" or touch_links != ("gripper", "jaw"):
            return ActionResult(
                ActionStatus.FAILED,
                Failure(
                    FailureCategory.MOVEIT_SCENE,
                    "MOVEIT_SCENE_ATTACHMENT_CONTRACT",
                    "invalid attachment links",
                ),
            )
        if not self._backend.apply(("attach", object_id, link_name, touch_links)):
            return ActionResult(
                ActionStatus.FAILED,
                Failure(
                    FailureCategory.MOVEIT_SCENE,
                    "MOVEIT_SCENE_APPLY_FAILED",
                    "apply failed",
                ),
            )
        return self._converge(
            lambda value: value.attached_object == object_id and value.attached_link == link_name,
            timeout_s,
        )

    def detach_task_object(
        self, object_id: str, world_pose: Pose3D, timeout_s: float = 2.0
    ) -> ActionResult:
        if not self._backend.apply(("detach", object_id, world_pose)):
            return ActionResult(
                ActionStatus.FAILED,
                Failure(
                    FailureCategory.MOVEIT_SCENE,
                    "MOVEIT_SCENE_APPLY_FAILED",
                    "apply failed",
                ),
            )
        return self._converge(
            lambda value: (
                object_id in value.world_objects
                and value.attached_object is None
                and value.world_pose == world_pose
            ),
            timeout_s,
        )

    def observe(self, timeout_s: float) -> SceneObservation:
        del timeout_s
        return self._backend.observe()
