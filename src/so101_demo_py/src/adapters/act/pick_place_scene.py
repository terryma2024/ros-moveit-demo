"""Bind the pick-place validation Planning Scene cup pose to accepted MuJoCo truth."""

from __future__ import annotations

from dataclasses import replace

from so101_demo.act.contracts import identifier
from so101_demo.core.task_geometry import Pose7, TaskGeometry


class PickPlaceSceneError(RuntimeError):
    """Physical readback cannot safely define a Planning Scene cup pose."""


def pick_place_scene_geometry(base: TaskGeometry, readback: dict, *,
                         session_id: str, reset_epoch: int) -> TaskGeometry:
    """Preserve fixed task geometry and move only the cup to its physical pose."""
    try:
        identifier(session_id)
        if type(reset_epoch) is not int or reset_epoch < 1:
            raise ValueError("reset epoch")
        if (not isinstance(base, TaskGeometry) or base.frame_id != "world"
                or base.object_ids != ("table", "pedestal", "plastic_cup")
                or not isinstance(readback, dict)):
            raise ValueError("task geometry")
        world, scene, contact = (readback[name] for name in ("world", "scene", "contact"))
        scope = (session_id, reset_epoch)
        if ((world.simulation_session_id, world.reset_epoch) != scope
                or (scene["simulation_session_id"], scene["reset_epoch"]) != scope
                or (contact["simulation_session_id"], contact["reset_epoch"]) != scope
                or type(world.simulation_step) is not int or world.simulation_step < 1
                or type(scene["simulation_step"]) is not int
                or type(contact["physics_step"]) is not int
                or world.simulation_step != scene["simulation_step"]
                or world.simulation_step != contact["physics_step"]
                or world.paused is not False or scene["paused"] is not False
                or world.object_state.body != "plastic_cup"):
            raise ValueError("readback scope")
        pose = Pose7.parse(
            list(world.object_state.position_world) +
            list(world.object_state.orientation_xyzw), "task8.physical_cup_pose",
        )
        cup = replace(base.object("plastic_cup"), pose=pose)
        return replace(base, objects=(*base.objects[:2], cup))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise PickPlaceSceneError("TASK8_SCENE_PHYSICAL_READBACK_INVALID") from error


# Legacy Python API for version-one pick-place callers.
Task8SceneError = PickPlaceSceneError
task8_scene_geometry = pick_place_scene_geometry
