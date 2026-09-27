"""Selected physical SEARCH can prepare only a noncollecting exact prefix."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import mujoco
import pytest

from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source
from so101_demo.adapters.act.selected_approach_candidate import SelectedApproachCandidate

from test_act_task8_search_port import observation


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
CONFIG = PACKAGE / "config/mujoco/act"


@pytest.fixture(scope="module")
def producer():
    return SelectedApproachCandidate(
        scene_path=SCENE,
        plugin_path=CONFIG / "task6_route_plugins.yaml",
        source_profile_path=CONFIG / "task6_visible_approach_v1.json",
        candidate_profile_path=CONFIG / "visible_approach_candidate_v1.json",
        session_id="session-296", attempt_id="attempt-296",
        max_skew_s=.02, max_source_age_s=.2,
        joint_tolerance_rad=.002, cup_tolerance_m=.002,
        stop_velocity_rad_s=.002,
        monotonic=lambda: 10.1,
    )


def selected_observation(producer):
    observed = observation()
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    start = producer.manifest["segments"][0]["prior"]
    for joint_name, value in zip(("1", "2", "3", "4", "5", "6"), start, strict=True):
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        data.qpos[model.jnt_qposadr[joint]] = value
    cup_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    cup_address = model.jnt_qposadr[cup_joint]
    data.qpos[cup_address:cup_address + 3] = (.02, -.28, .165)
    data.qpos[cup_address + 3:cup_address + 7] = (1., 0., 0., 0.)
    raw = dict(observed.physical_readback)
    raw["scene"] = {**raw["scene"], "model_sha256": producer.manifest["model_sha256"],
                    "qpos": data.qpos.tolist(), "qvel": data.qvel.tolist()}
    raw["observation"] = {**raw["observation"], "state": tuple(start) + (0., 1.)}
    raw["reference"] = {**raw["reference"], "positions": tuple(start)}
    original_world = observed.physical_readback["world"]
    raw["world"] = replace(original_world, object_state=replace(
        original_world.object_state, position_world=(.02, -.28, .165)))
    return replace(observed, physical_readback=raw)


def test_selected_search_prepares_exact_prefix_without_authority(producer):
    observed = selected_observation(producer)
    source = freeze_selected_search_source(observed, max_skew_s=.02)
    prepared = producer.prepare(observed, selected_source=source)
    prefix = prepared["prefix"]
    assert prepared["command_authority"] is False
    assert prepared["eligible_for_collection"] is False
    assert prepared["selected_source"] == source
    assert prepared["selected_source"]["source_received_wall_s"] == (
        observed.physical_readback["source_received_wall_s"])
    assert prefix["sequence"] == 0
    assert prefix["observation_time_s"] == source["simulation_time_s"]
    assert prefix["target_interval_s"] == .002
    assert len(prefix["positions"]) == 600
    digest = hashlib.sha256(json.dumps(prefix["positions"],
                                       separators=(",", ":"), allow_nan=False).encode())
    assert digest.hexdigest() == producer.manifest["segments"][0]["rows_sha256"]


def test_selected_source_drift_and_wrong_start_refuse(producer):
    observed = selected_observation(producer)
    source = freeze_selected_search_source(observed, max_skew_s=.02)
    changed = selected_observation(producer)
    changed.physical_readback["observation"]["wrist"][0, 0, 0] = 1
    with pytest.raises(ValueError, match="SELECTED_APPROACH_SOURCE_CHANGED"):
        producer.prepare(changed, selected_source=source)
    changed = selected_observation(producer)
    changed.physical_readback["scene"]["qpos"][0] += .01
    with pytest.raises(ValueError, match="SELECTED_APPROACH_START_INVALID"):
        producer.prepare(changed, selected_source=freeze_selected_search_source(
            changed, max_skew_s=.02))
    changed = selected_observation(producer)
    changed.physical_readback["scene"]["qvel"][0] = .01
    with pytest.raises(ValueError, match="SELECTED_APPROACH_START_INVALID"):
        producer.prepare(changed, selected_source=freeze_selected_search_source(
            changed, max_skew_s=.02))
    changed = selected_observation(producer)
    changed.physical_readback["world"] = replace(
        changed.physical_readback["world"], reset_epoch=3)
    with pytest.raises(ValueError):
        producer.prepare(changed, selected_source=source)
    original_clock = producer.monotonic
    producer.monotonic = lambda: 10.3
    try:
        with pytest.raises(ValueError, match="SELECTED_APPROACH_SOURCE_STALE"):
            producer.prepare(observed, selected_source=source)
    finally:
        producer.monotonic = original_clock
