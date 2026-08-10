"""Verified Gazebo/MoveIt scene transactions; neither layer is treated as a proxy for the other."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol


@dataclass(frozen=True)
class SceneResult:
    succeeded: bool
    code: str
    layers: Dict[str, str]


class SceneBackend(Protocol):
    async def gazebo_attach(self, object_name: str) -> bool: ...
    async def gazebo_detach(self, object_name: str) -> bool: ...
    async def gazebo_attached(self, object_name: str) -> bool: ...
    async def moveit_attach(self, object_name: str) -> bool: ...
    async def moveit_detach_to_world(self, object_name: str, pose) -> bool: ...
    async def object_pose(self, object_name: str): ...
    async def wait_stationary(self, object_name: str) -> bool: ...
    async def reset_world(self) -> bool: ...
    async def verify_reset(self) -> bool: ...


class SceneGateway:
    def __init__(self, backend: SceneBackend) -> None:
        self._backend = backend

    async def attach(self, object_name: str) -> SceneResult:
        if not await self._backend.gazebo_attach(object_name):
            return SceneResult(False, "GAZEBO_ATTACH_FAILED", {"gazebo": "detached", "moveit": "world"})
        if not await self._backend.gazebo_attached(object_name):
            return SceneResult(False, "GAZEBO_ATTACH_UNVERIFIED", {"gazebo": "unknown", "moveit": "world"})
        if await self._backend.moveit_attach(object_name):
            return SceneResult(True, "OK", {"gazebo": "attached", "moveit": "attached"})
        detached = await self._backend.gazebo_detach(object_name)
        verified_detached = detached and not await self._backend.gazebo_attached(object_name)
        return SceneResult(False, "MOVEIT_ATTACH_FAILED", {
            "gazebo": "detached" if verified_detached else "unknown",
            "moveit": "world",
        })

    async def detach(self, object_name: str) -> SceneResult:
        if not await self._backend.gazebo_detach(object_name):
            return SceneResult(False, "GAZEBO_DETACH_FAILED", {"gazebo": "attached", "moveit": "attached"})
        if await self._backend.gazebo_attached(object_name):
            return SceneResult(False, "GAZEBO_DETACH_UNVERIFIED", {"gazebo": "unknown", "moveit": "attached"})
        if not await self._backend.wait_stationary(object_name):
            return SceneResult(False, "OBJECT_NOT_STATIONARY", {"gazebo": "detached", "moveit": "attached"})
        pose = await self._backend.object_pose(object_name)
        if pose is None or not await self._backend.moveit_detach_to_world(object_name, pose):
            return SceneResult(False, "MOVEIT_DETACH_FAILED", {"gazebo": "detached", "moveit": "unknown"})
        return SceneResult(True, "OK", {"gazebo": "detached", "moveit": "world"})

    async def reset_simulation(self) -> SceneResult:
        if not await self._backend.reset_world():
            return SceneResult(False, "RESET_WORLD_FAILED", {"reset": "failed"})
        if not await self._backend.verify_reset():
            return SceneResult(False, "RESET_INCOMPLETE", {"reset": "unconverged"})
        return SceneResult(True, "OK", {"reset": "verified"})
