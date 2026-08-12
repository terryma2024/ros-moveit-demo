"""Audited PlanningScenePort implementation over a narrow scene backend."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...ports.evidence import PoseEvidence
from ...ports.planning_scene import SceneResult, WorldObjectRequest


@dataclass(slots=True)
class AuditedSceneLease:
    pair: tuple[str, str]
    acquired: bool
    _restore: Callable[[tuple[str, str]], bool]
    released: bool = False

    def release(self) -> SceneResult:
        if not self.acquired:
            return SceneResult(False, error_code="COLLISION_LEASE_NOT_ACQUIRED")
        if self.released:
            return SceneResult(False, error_code="COLLISION_LEASE_ALREADY_RELEASED")
        restored = bool(self._restore(self.pair))
        if restored:
            self.released = True
        return SceneResult(restored, error_code=None if restored else "COLLISION_RESTORE_FAILED")


class PlanningSceneAdapter:
    """Mutate only MoveIt shadow state; never claim simulator-world effects."""

    def __init__(self, backend: object) -> None:
        self._backend = backend

    def _apply(self, operation: tuple[object, ...], error_code: str) -> SceneResult:
        applied = bool(self._backend.apply(operation))
        return SceneResult(applied, error_code=None if applied else error_code)

    def add_world_object(self, request: WorldObjectRequest) -> SceneResult:
        return self._apply(
            ("add_world_object", request.object_id, request.pose, request.geometry_id),
            "WORLD_OBJECT_APPLY_FAILED",
        )

    def attach_shadow(self, object_id: str, link_name: str) -> SceneResult:
        if not object_id or not link_name:
            return SceneResult(False, error_code="ATTACHMENT_IDENTITY_INVALID")
        return self._apply(("attach_shadow", object_id, link_name), "ATTACH_SHADOW_FAILED")

    def detach_shadow(self, object_id: str) -> SceneResult:
        return self._apply(("detach_shadow", object_id), "DETACH_SHADOW_FAILED")

    def synchronize_object_pose(self, object_id: str, pose: PoseEvidence) -> SceneResult:
        return self._apply(("synchronize_pose", object_id, pose), "POSE_SYNC_FAILED")

    def temporary_allow_collision(self, pair: tuple[str, str]) -> AuditedSceneLease:
        if len(pair) != 2 or not all(pair) or pair[0] == pair[1]:
            raise ValueError("collision lease requires two distinct non-empty names")
        acquired = bool(self._backend.apply(("allow_collision", *pair)))
        return AuditedSceneLease(pair, acquired, self._restore_collision)

    def _restore_collision(self, pair: tuple[str, str]) -> bool:
        return bool(self._backend.apply(("restore_collision", *pair)))
