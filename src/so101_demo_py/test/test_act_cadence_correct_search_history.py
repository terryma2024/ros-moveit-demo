"""SEARCH needs 51 original physics/contact steps, not 51 scene publishes."""

import copy
from dataclasses import replace

import pytest

from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk

from so101_demo.adapters.act.contact_evidence import RobotContactObserver
from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory
from so101_demo.adapters.act.scene_state import SceneStateObserver
from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source
from so101_demo.adapters.act.cadence_correct_search_history import (
    verify_cadence_correct_search_history,
)

from test_act_task8_search_port import observation


SESSION = "session-296"
MODEL_SHA = "a" * 64
NOW_NS = 10_000_000_000
SOURCE_BASE_NS = 9_500_000_000
STEP_NS = 2_000_000
QPOS = [0.] * 14
QVEL = [0.] * 12


def _sample(step):
    sample = PhysicsStepEvidence()
    sample.simulation_session_id = SESSION
    sample.reset_epoch = 2
    sample.physics_step = step
    sample.simulation_time_s = .9 + step * .002
    sample.clock_interval_begin_monotonic_ns = SOURCE_BASE_NS + step * STEP_NS
    sample.clock_interval_end_monotonic_ns = sample.clock_interval_begin_monotonic_ns + 200_000
    sample.model_qpos = QPOS
    sample.model_qvel = QVEL
    return sample


def _chunk(sequence, samples):
    chunk = PhysicsStepEvidenceChunk()
    chunk.simulation_session_id = SESSION
    chunk.reset_epoch = 2
    chunk.chunk_sequence = sequence
    chunk.first_physics_step = samples[0].physics_step
    chunk.last_physics_step = samples[-1].physics_step
    chunk.first_simulation_time_s = samples[0].simulation_time_s
    chunk.last_simulation_time_s = samples[-1].simulation_time_s
    chunk.samples = samples
    return chunk


def _fixture():
    now = [NOW_NS]
    history = PhysicsClockHistory(
        SESSION, nq=14, nv=12, max_age_s=.6,
        max_source_step_gap_ns=3_000_000, clock_ns=lambda: now[0])
    history.arm(2, source_floor_s=.9)
    samples = [_sample(step) for step in range(1, 151)]
    for sequence, offset in enumerate(range(0, len(samples), 25)):
        history.accept_chunk(_chunk(sequence, samples[offset:offset + 25]))

    scene = SceneStateObserver(
        model_sha256=MODEL_SHA, nq=14, nv=12, max_age_s=.6,
        monotonic=lambda: now[0] / 1e9)
    scene.reset(SESSION, 2, source_floor_s=.9)
    contact = RobotContactObserver(
        known_geoms={"arm", "table"}, allowed_pairs=set(), max_age_s=.6,
        max_sim_gap_s=.003, monotonic=lambda: now[0] / 1e9)
    contact.reset(SESSION, 2, source_floor_s=.9)
    for step in range(1, 151):
        contact.accept(dict(
            simulation_session_id=SESSION, reset_epoch=2, physics_step=step,
            simulation_time_s=.9 + step * .002, geom_a=[], geom_b=[],
            signed_distance_m=[], normal_force_n=[], truncated=False,
            evidence_loss=False))
    assert contact.safe()
    observed = observation()
    raw = copy.deepcopy(observed.physical_readback)
    raw["world"] = replace(raw["world"], simulation_step=150)
    raw["scene"] = {**raw["scene"], "simulation_step": 150,
                    "qpos": list(QPOS), "qvel": list(QVEL)}
    assert scene.accept(raw["scene"])
    raw["contact"] = contact.recent_frames()[149]
    marker_sample = samples[98]
    marker = dict(
        session_id=SESSION, reset_epoch=2, request_sequence=1,
        marked_physics_step=99, marked_simulation_time_s=1.098,
        request_sent_wall_s=9.69, ack_received_wall_s=9.699,
        request_sent_monotonic_ns=9_690_000_000,
        ack_received_monotonic_ns=9_699_000_000,
        clock_interval_begin_monotonic_ns=marker_sample.clock_interval_begin_monotonic_ns,
        clock_interval_end_monotonic_ns=marker_sample.clock_interval_end_monotonic_ns,
        marked_sample_clock_interval_begin_monotonic_ns=(
            marker_sample.clock_interval_begin_monotonic_ns),
        marked_sample_clock_interval_end_monotonic_ns=(
            marker_sample.clock_interval_end_monotonic_ns),
        model_qpos=tuple(QPOS), model_qvel=tuple(QVEL),
        command_authority=False)
    observed = replace(observed, physical_readback=raw, physics_step_fence=marker)
    selected = freeze_selected_search_source(observed, max_skew_s=.02)
    return observed, selected, history, scene, contact, now


def _verify(state):
    observed, selected, history, scene, contact, now = state
    return verify_cadence_correct_search_history(
        observed, selected, history, scene, contact,
        expected_model_sha256=MODEL_SHA, max_source_skew_s=.02,
        max_source_age_ns=600_000_000, allowed_contact_pairs=frozenset(),
        robot_dof_indices=tuple(range(7)), stop_velocity_rad_s=.0005,
        stopped_wall_s=9.68, clock_ns=lambda: now[0])


def test_cadence_correct_window_uses_51_physics_and_contact_steps_with_one_scene():
    state = _fixture()
    result = _verify(state)
    assert result["first_physics_step"] == 100
    assert result["selected_physics_step"] == 150
    assert result["interval_ns"] == 100_000_000
    assert len(result["physics_samples"]) == 51
    assert len(result["contact_frames"]) == 51
    assert result["selected_source_sha256"] == state[1]["observation_sha256"]
    assert result["command_authority"] is False
    assert result["eligible_for_collection"] is False
    result["physics_samples"][0].model_qpos[0] = 9.
    result["contact_frames"][0]["geom_a"].append("arm")
    assert tuple(state[2].step_at(100)["sample"].model_qpos) == tuple(QPOS)
    assert state[4].recent_frames()[99]["geom_a"] == []


@pytest.mark.parametrize("damage", [
    "physics_gap", "contact_gap", "contact_duplicate", "contact_time_1ns",
    "interior_qpos_drift", "interior_joint_speed", "post_ack_source",
    "chunk_boundary_clock_overlap", "stale_source_fresh_receipt",
    "marker_step", "marker_time", "marker_state", "marker_clock",
    "selected_pixel", "selected_receipt", "contact_hazard", "scene_reset",
    "physics_hazard",
])
def test_cadence_correct_window_rejects_corrupted_boundary(damage):
    observed, selected, history, scene, contact, now = _fixture()
    if damage == "physics_gap":
        history._history = type(history._history)(
            (item for item in history._history if item["sample"].physics_step != 125),
            maxlen=512)
    elif damage == "contact_gap":
        contact._history = type(contact._history)(
            (item for item in contact._history if item[0]["physics_step"] != 125),
            maxlen=512)
    elif damage == "contact_duplicate":
        contact._history.append(copy.deepcopy(contact._history[124]))
    elif damage == "contact_time_1ns":
        contact._history[124][0]["simulation_time_s"] += 1e-9
    elif damage == "interior_qpos_drift":
        history._history[124]["sample"].model_qpos[0] = .001
    elif damage == "interior_joint_speed":
        history._history[124]["sample"].model_qvel[0] = .001
    elif damage == "post_ack_source":
        observed.physics_step_fence["ack_received_monotonic_ns"] = 9_701_000_000
        observed.physics_step_fence["ack_received_wall_s"] = 9.701
    elif damage == "chunk_boundary_clock_overlap":
        history._history[125]["sample"].clock_interval_begin_monotonic_ns = (
            history._history[124]["sample"].clock_interval_end_monotonic_ns - 1)
    elif damage == "stale_source_fresh_receipt":
        now[0] += 700_000_000
        fresh = now[0] / 1e9
        observed.physical_readback["source_received_wall_s"] = dict.fromkeys(
            observed.physical_readback["source_received_wall_s"], fresh)
        scene.received = fresh
        scene._history[-1] = (scene._history[-1][0], fresh)
        contact.received = fresh
        contact._history = type(contact._history)(
            ((frame, fresh) for frame, _ in contact._history), maxlen=512)
        selected = freeze_selected_search_source(observed, max_skew_s=.02)
    elif damage == "marker_step":
        observed.physics_step_fence["marked_physics_step"] = 98
    elif damage == "marker_time":
        observed.physics_step_fence["marked_simulation_time_s"] += .001
    elif damage == "marker_state":
        observed.physics_step_fence["model_qpos"] = (.001,) + tuple(QPOS[1:])
    elif damage == "marker_clock":
        observed.physics_step_fence["marked_sample_clock_interval_end_monotonic_ns"] += 1
    elif damage == "selected_pixel":
        observed.physical_readback["observation"]["head"][0, 0, 0] = 1
    elif damage == "selected_receipt":
        observed.physical_readback["source_received_wall_s"]["scene"] -= .001
    elif damage == "contact_hazard":
        contact.latch("INJECTED_CONTACT_HAZARD")
    elif damage == "scene_reset":
        scene.reset(SESSION, 3, source_floor_s=1.2)
    else:
        history.hazard = "INJECTED_PHYSICS_HAZARD"
    with pytest.raises(ValueError, match="CADENCE_CORRECT_SEARCH_HISTORY_INVALID"):
        _verify((observed, selected, history, scene, contact, now))
