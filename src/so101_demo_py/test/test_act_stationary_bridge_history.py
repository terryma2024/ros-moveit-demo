"""Historical physics alone cannot authorize an approach controller goal."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import copy

import mujoco
import pytest

from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.stationary_bridge_history import (
    verify_stationary_physics_history,
)

from test_act_task8_search_port import observation


SCENE = Path(__file__).resolve().parents[1] / "assets/mujoco/act/scene.xml"


def history():
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    observed = observation()
    raw = dict(observed.physical_readback)
    raw["scene"] = {**raw["scene"], "model_sha256": model_sha256(model),
                    "qpos": data.qpos.tolist(),
                    "qvel": data.qvel.tolist()}
    world = raw["world"]
    raw["world"] = replace(world, simulation_step=150, publisher_sequence=150,
                           object_state=replace(world.object_state,
                                                position_world=(.02, -.28, .165)))
    raw["scene"]["simulation_step"] = 150
    raw["contact"] = {**raw["contact"], "physics_step": 150}
    raw["source_received_wall_s"] = {
        **raw["source_received_wall_s"],
        "world": 10.1, "scene": 10.1, "contact": 10.1,
    }
    observed = replace(observed, physical_readback=raw)
    source = freeze_selected_search_source(observed, max_skew_s=.02)
    worlds = []
    scenes = []
    contacts = []
    for index in range(51):
        step = 100 + index
        stamp = round(1.1 + index * .002, 9)
        receipt = round(10.0 + index * .002, 9)
        worlds.append(SimpleNamespace(
            evidence=replace(raw["world"], simulation_step=step,
                             simulation_time_s=stamp,
                             publisher_sequence=step),
            received_monotonic_s=receipt,
        ))
        scenes.append(({**raw["scene"], "simulation_step": step,
                        "simulation_time_s": stamp}, receipt))
        contacts.append(({**raw["contact"], "physics_step": step,
                          "simulation_time_s": stamp}, receipt))
    return model, observed, source, worlds, scenes, contacts


def verify(model, observed, source, worlds, scenes, contacts, *, now=10.11):
    return verify_stationary_physics_history(
        observed=observed, selected_source=source,
        world_history=worlds, scene_history=scenes,
        contact_history=contacts, model=model,
        model_sha256=observed.physical_readback["scene"]["model_sha256"],
        max_source_skew_s=.02, max_wall_age_s=.2,
        allowed_contact_pairs=frozenset(),
        stop_velocity_rad_s=.002, monotonic=lambda: now,
    )


def test_exact_51_frame_history_is_physical_only():
    model, observed, source, worlds, scenes, contacts = history()
    result = verify(model, observed, source, worlds, scenes, contacts)
    assert result["first_physics_step"] == 100
    assert result["selected_physics_step"] == 150
    assert result["bridge_sim_time_s"] == pytest.approx(1.1)
    assert result["selected_sim_time_s"] == pytest.approx(1.2)
    assert result["interval_ns"] == 100_000_000
    assert len(result["model_qpos"]) == model.nq
    assert len(result["model_qvel"]) == model.nv
    assert result["controller_interval_proof_required"] is True
    assert result["command_authority"] is False
    assert result["eligible_for_collection"] is False


def test_gap_state_contact_source_and_receipt_changes_refuse():
    model, observed, source, worlds, scenes, contacts = history()
    with pytest.raises(ValueError):
        verify(model, observed, source, worlds, scenes[:25] + scenes[26:], contacts)
    altered = copy.deepcopy(scenes)
    altered[25][0]["qpos"][0] += .001
    with pytest.raises(ValueError):
        verify(model, observed, source, worlds, altered, contacts)
    altered = copy.deepcopy(contacts)
    altered[25][0]["geom_a"] = ["arm"]
    altered[25][0]["geom_b"] = ["table"]
    altered[25][0]["signed_distance_m"] = [-.001]
    altered[25][0]["normal_force_n"] = [1.]
    with pytest.raises(ValueError):
        verify(model, observed, source, worlds, scenes, altered)
    changed = copy.deepcopy(observed)
    changed.physical_readback["observation"]["head"][0, 0, 0] = 1
    with pytest.raises(ValueError):
        verify(model, changed, source, worlds, scenes, contacts)
    with pytest.raises(ValueError):
        verify(model, observed, source, worlds, scenes, contacts, now=10.3)
