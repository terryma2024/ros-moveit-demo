"""Planning Scene shadow and reversible collision-lease boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .evidence import PoseEvidence


@dataclass(frozen=True, slots=True)
class WorldObjectRequest:
    object_id: str
    pose: PoseEvidence
    geometry_id: str

    def __post_init__(self) -> None:
        if not self.object_id or not self.geometry_id:
            raise ValueError("world object identifiers must be non-empty")


@dataclass(frozen=True, slots=True)
class SceneResult:
    scene_applied: bool
    physical_grasp_proved: bool = False
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.physical_grasp_proved:
            raise ValueError("Planning Scene state cannot prove a physical grasp")


class SceneLease(Protocol):
    pair: tuple[str, str]
    acquired: bool
    released: bool

    def release(self) -> SceneResult: ...


@runtime_checkable
class PlanningScenePort(Protocol):
    def add_world_object(self, request: WorldObjectRequest) -> SceneResult: ...

    def attach_shadow(self, object_id: str, link_name: str) -> SceneResult: ...

    def detach_shadow(self, object_id: str) -> SceneResult: ...

    def synchronize_object_pose(self, object_id: str, pose: PoseEvidence) -> SceneResult: ...

    def temporary_allow_collision(self, pair: tuple[str, str]) -> SceneLease: ...
