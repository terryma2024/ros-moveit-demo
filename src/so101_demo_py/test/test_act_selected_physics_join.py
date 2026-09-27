"""One selected 100 Hz frame must retain its exact 500 Hz measured state."""

import copy
from dataclasses import replace

import pytest

from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk

from so101_demo.adapters.act.contact_evidence import RobotContactObserver
from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory
from so101_demo.adapters.act.scene_state import SceneStateObserver
from so101_demo.core.simulation.types import ObjectState, SimulationEvidence

from so101_demo.adapters.act.selected_physics_join import join_selected_physics_sample


SESSION = "selected-physics"
MODEL_SHA = "a" * 64
NOW_NS = 10_000_000_000
SOURCE_BASE_NS = 9_900_000_000
STEP_NS = 2_000_000


def _sample(step):
    sample = PhysicsStepEvidence()
    sample.simulation_session_id = SESSION
    sample.reset_epoch = 1
    sample.physics_step = step
    sample.simulation_time_s = step * .002
    sample.clock_interval_begin_monotonic_ns = SOURCE_BASE_NS + step * STEP_NS
    sample.clock_interval_end_monotonic_ns = sample.clock_interval_begin_monotonic_ns + 200_000
    sample.model_qpos = [.1, .2]
    sample.model_qvel = [.3]
    return sample


def _chunk(samples):
    chunk = PhysicsStepEvidenceChunk()
    chunk.simulation_session_id = SESSION
    chunk.reset_epoch = 1
    chunk.chunk_sequence = 0
    chunk.first_physics_step = 1
    chunk.last_physics_step = len(samples)
    chunk.first_simulation_time_s = samples[0].simulation_time_s
    chunk.last_simulation_time_s = samples[-1].simulation_time_s
    chunk.samples = samples
    return chunk


def _fixture():
    now = [9_950_000_000]
    history = PhysicsClockHistory(
        SESSION, nq=2, nv=1, max_age_s=.2,
        max_source_step_gap_ns=3_000_000, clock_ns=lambda: now[0])
    history.arm(1, source_floor_s=0.0)

    scene_observer = SceneStateObserver(
        model_sha256=MODEL_SHA, nq=2, nv=1, max_age_s=.2,
        monotonic=lambda: now[0] / 1e9)
    scene_observer.reset(SESSION, 1, source_floor_s=0.0)
    scene = dict(
        simulation_session_id=SESSION, reset_epoch=1, simulation_step=5,
        simulation_time_s=.010, paused=False, model_sha256=MODEL_SHA,
        qpos=[.1, .2], qvel=[.3],
        clock_interval_begin_monotonic_ns=9_930_000_000,
        clock_interval_end_monotonic_ns=9_930_100_000)
    assert scene_observer.accept(scene)

    contact_observer = RobotContactObserver(
        known_geoms={"arm", "table"}, allowed_pairs=set(), max_age_s=.2,
        max_sim_gap_s=.003, monotonic=lambda: now[0] / 1e9)
    contact_observer.reset(SESSION, 1, source_floor_s=0.0)
    for step in range(1, 11):
        contact_observer.accept(dict(
            simulation_session_id=SESSION, reset_epoch=1, physics_step=step,
            simulation_time_s=step * .002, geom_a=[], geom_b=[],
            signed_distance_m=[], normal_force_n=[], truncated=False,
            evidence_loss=False))
    now[0] = NOW_NS
    history.accept_chunk(_chunk([_sample(step) for step in range(1, 11)]))
    assert contact_observer.safe()

    # World pose is legitimately cached and need not equal post-step qpos.
    world = SimulationEvidence(
        simulation_time_s=.010, frame_id="world", publisher_sequence=2,
        simulation_step=5, reset_epoch=1, simulation_session_id=SESSION,
        paused=False, object_state=ObjectState(
            body_id=1, body="cup", position_world=(4., 5., 6.),
            orientation_xyzw=(0., 0., 0., 1.),
            linear_velocity_world=(0., 0., 0.),
            angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0.,
        maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(),
        other_object_contacts=())
    raw = dict(
        world=world, scene=copy.deepcopy(scene),
        contact=contact_observer.recent_frames()[4],
        observation={}, reference={}, source_stamps_s={},
        source_received_wall_s=dict.fromkeys(
            ("world", "scene", "contact", "head", "wrist", "arm", "neck"), 9.95))
    return raw, history, scene_observer, contact_observer, now


def _join(raw, history, scene, contacts, now):
    return join_selected_physics_sample(
        raw, history, scene, contacts, expected_model_sha256=MODEL_SHA,
        max_source_age_ns=200_000_000, clock_ns=lambda: now[0])


def test_selected_frame_joins_sparse_world_to_exact_physics_and_copies():
    raw, history, scene, contacts, now = _fixture()
    # The history already contains later 500 Hz steps; this must retain step 5.
    result = _join(raw, history, scene, contacts, now)
    assert result["physics_sample"].physics_step == 5
    assert result["physics_received_monotonic_ns"] == NOW_NS
    assert result["readback"]["world"].object_state.position_world == (4., 5., 6.)
    assert result["readback"]["source_received_wall_s"] == raw["source_received_wall_s"]
    assert result["command_authority"] is False
    result["physics_sample"].model_qpos[0] = 9.
    result["readback"]["scene"]["qvel"][0] = 9.
    assert tuple(history.step_at(5)["sample"].model_qpos) == (.1, .2)
    assert raw["scene"]["qvel"] == [.3]


@pytest.mark.parametrize("damage", [
    "world_session", "world_epoch", "world_step", "scene_step", "contact_epoch",
    "world_time", "scene_time", "contact_time", "qpos", "qvel", "model_hash",
    "scene_clock_before_physics", "stale_scene_source", "scene_future",
    "scene_paused", "contact_loss", "missing_sample", "scene_duplicate",
    "contact_duplicate", "scene_reset", "contact_hazard", "physics_hazard",
])
def test_selected_frame_rejects_one_corrupted_boundary(damage):
    raw, history, scene, contacts, now = _fixture()
    if damage == "world_session":
        raw["world"] = replace(raw["world"], simulation_session_id="other")
    elif damage == "world_epoch":
        raw["world"] = replace(raw["world"], reset_epoch=2)
    elif damage == "world_step":
        raw["world"] = replace(raw["world"], simulation_step=6)
    elif damage == "scene_step":
        raw["scene"]["simulation_step"] = 6
    elif damage == "contact_epoch":
        raw["contact"]["reset_epoch"] = 2
    elif damage == "world_time":
        raw["world"] = replace(raw["world"], simulation_time_s=.011)
    elif damage == "scene_time":
        raw["scene"]["simulation_time_s"] = .011
    elif damage == "contact_time":
        raw["contact"]["simulation_time_s"] = .011
    elif damage == "qpos":
        raw["scene"]["qpos"][0] += .001
    elif damage == "qvel":
        raw["scene"]["qvel"][0] += .001
    elif damage == "model_hash":
        raw["scene"]["model_sha256"] = "b" * 64
    elif damage == "scene_clock_before_physics":
        raw["scene"]["clock_interval_begin_monotonic_ns"] = 9_909_000_000
    elif damage == "stale_scene_source":
        now[0] += 201_000_000
        fresh_receipt = now[0] / 1e9
        raw["source_received_wall_s"] = dict.fromkeys(
            raw["source_received_wall_s"], fresh_receipt)
        scene.received = fresh_receipt
        scene._history[-1] = (scene._history[-1][0], fresh_receipt)
        contacts.received = fresh_receipt
        contacts._history = type(contacts._history)(
            ((frame, fresh_receipt) for frame, _ in contacts._history), maxlen=512)
    elif damage == "scene_future":
        raw["scene"]["clock_interval_end_monotonic_ns"] = NOW_NS + 1
    elif damage == "scene_paused":
        raw["scene"]["paused"] = True
    elif damage == "contact_loss":
        raw["contact"]["evidence_loss"] = True
    elif damage == "missing_sample":
        history._history = type(history._history)(
            (item for item in history._history if item["sample"].physics_step != 5),
            maxlen=512)
    elif damage == "scene_duplicate":
        scene._history.append(copy.deepcopy(scene._history[-1]))
    elif damage == "contact_duplicate":
        contacts._history.append(copy.deepcopy(contacts._history[4]))
    elif damage == "scene_reset":
        scene.reset(SESSION, 2, source_floor_s=.010)
    elif damage == "contact_hazard":
        contacts.latch("CONTACT_INJECTED_HAZARD")
    else:
        history.hazard = "PHYSICS_INJECTED_HAZARD"
    if damage in {"scene_time", "qpos", "qvel", "model_hash",
                  "scene_clock_before_physics", "scene_future", "scene_paused"}:
        frame, receipt = scene._history[-1]
        scene._history[-1] = (copy.deepcopy(raw["scene"]), receipt)
    if damage in {"contact_time", "contact_loss"}:
        frame, receipt = contacts._history[4]
        contacts._history[4] = (copy.deepcopy(raw["contact"]), receipt)
    with pytest.raises(ValueError, match="SELECTED_PHYSICS_JOIN_INVALID"):
        _join(raw, history, scene, contacts, now)
