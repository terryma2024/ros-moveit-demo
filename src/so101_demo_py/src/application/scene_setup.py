"""Backend-neutral Planning Scene setup orchestration."""

from collections.abc import Iterable

from ..ports.planning_scene import PlanningScenePort, SceneResult, WorldObjectRequest


def configure_world(
    scene: PlanningScenePort, requests: Iterable[WorldObjectRequest]
) -> tuple[SceneResult, ...]:
    """Apply deterministic world shadows while leaving physical-world proof separate."""

    return tuple(scene.add_world_object(request) for request in requests)
