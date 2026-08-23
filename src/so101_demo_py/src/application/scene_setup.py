"""Backend-neutral Planning Scene setup orchestration."""

from collections.abc import Iterable

from ..ports.planning_scene import (
    PlanningScenePort,
    SceneCommandReceipt,
    SceneResult,
    TaskScenePort,
    WorldObjectRequest,
)


def configure_world(
    scene: PlanningScenePort, requests: Iterable[WorldObjectRequest]
) -> tuple[SceneResult, ...]:
    """Apply deterministic world shadows while leaving physical-world proof separate."""

    return tuple(scene.add_world_object(request) for request in requests)


def execute_task_scene_operation(
    scene: TaskScenePort,
    geometry,
    operation: str,
) -> SceneCommandReceipt:
    """Execute one public scene operation and verify its postcondition."""

    if operation in {"setup", "upsert"}:
        applied = scene.apply_task_scene(geometry)
        if not applied.success:
            return applied
        return scene.observe_task_scene(geometry, expected_cup_attachment=None)
    if operation == "observe":
        return scene.observe_task_scene(geometry, expected_cup_attachment=None)
    if operation == "attach":
        attached = scene.attach_task_object(geometry, "plastic_cup", "gripper")
        if not attached.success:
            return attached
        return scene.observe_task_scene(geometry, expected_cup_attachment="gripper")
    if operation == "detach":
        detached = scene.detach_task_object(geometry, "plastic_cup")
        if not detached.success:
            return detached
        return scene.observe_task_scene(geometry, expected_cup_attachment=None)
    raise ValueError(f"unsupported scene operation: {operation}")
