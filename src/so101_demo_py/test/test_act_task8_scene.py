"""Task 8 Planning Scene uses the actual same-step MuJoCo cup pose."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.core.task_geometry import load_task_geometry
from so101_demo.adapters.act.task8_scene import Task8SceneError, task8_scene_geometry


def _geometry():
    path = Path(__file__).parents[1] / "assets/common/geometry-manifest.yaml"
    return load_task_geometry(path)


def _readback(*, session="session-1", epoch=2, world_step=11, scene_step=11,
              contact_step=11, paused=False, body="plastic_cup",
              position=(-0.08, -0.28, 0.165), orientation=(0.0, 0.0, 0.0, 1.0)):
    world = SimpleNamespace(
        simulation_session_id=session, reset_epoch=epoch,
        simulation_step=world_step, paused=paused,
        object_state=SimpleNamespace(body=body, position_world=position,
                                     orientation_xyzw=orientation),
    )
    return {
        "world": world,
        "scene": {"simulation_session_id": session, "reset_epoch": epoch,
                  "simulation_step": scene_step, "paused": paused},
        "contact": {"simulation_session_id": session, "reset_epoch": epoch,
                    "physics_step": contact_step},
    }


def test_search_scene_moves_only_cup_to_authoritative_physical_pose():
    base = _geometry()
    original = base.object("plastic_cup").pose.values
    derived = task8_scene_geometry(base, _readback(), session_id="session-1", reset_epoch=2)
    assert derived.object("plastic_cup").pose.values == (
        -0.08, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0,
    )
    assert base.object("plastic_cup").pose.values == original
    for name in ("table", "pedestal"):
        assert derived.object(name) == base.object(name)
    assert derived.object("plastic_cup").primitives == base.object("plastic_cup").primitives
    assert derived.object("plastic_cup").color_rgba == base.object("plastic_cup").color_rgba


@pytest.mark.parametrize("changes", [
    {"session": "foreign"}, {"epoch": 3}, {"world_step": 10},
    {"scene_step": 12}, {"contact_step": 10}, {"paused": True},
    {"body": "other_object"}, {"orientation": (0.0, 0.0, 0.0, 0.5)},
    {"position": (float("nan"), -0.28, 0.165)},
])
def test_search_scene_refuses_unbound_or_malformed_physical_pose(changes):
    with pytest.raises(Task8SceneError):
        task8_scene_geometry(_geometry(), _readback(**changes),
                             session_id="session-1", reset_epoch=2)
