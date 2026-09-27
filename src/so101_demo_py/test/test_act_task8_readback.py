"""A phase readback must join actual physics, contact, RGB and controller sources."""

import numpy as np
import pytest
import mujoco
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from ament_index_python.packages import get_package_share_directory

from so101_demo.act.synchronizer import RgbObservationSynchronizer
from so101_demo.adapters.act.contact_evidence import RobotContactObserver
from so101_demo.adapters.act.scene_state import SceneStateObserver
from so101_demo.core.simulation.types import (
    ObjectState, ReceivedSimulationEvidence, SimulationEvidence,
)
from so101_demo.adapters.act.task8_readback import (
    Task8PhysicalReadback, Task8ReadbackError, compiled_qpos_mapping,
)


MODEL_SHA256 = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"


@lru_cache(maxsize=1)
def loaded_model():
    path = Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"
    return mujoco.MjModel.from_xml_path(str(path))


@pytest.fixture(scope="module")
def compiled_model():
    return loaded_model()


def test_compiled_act_model_derives_seven_hinges_and_cup_free_joint(compiled_model):
    assert compiled_qpos_mapping(compiled_model, expected_model_sha256=MODEL_SHA256,
                                 expected_mujoco_version="3.12.0") == (
        (0, 1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12, 13),
    )


def test_compiled_mapping_refuses_wrong_model_hash(compiled_model):
    with pytest.raises(ValueError, match="TASK8_MODEL_HASH_MISMATCH"):
        compiled_qpos_mapping(compiled_model, expected_model_sha256="2" * 64,
                               expected_mujoco_version="3.12.0")


def test_compiled_mapping_refuses_wrong_mujoco_version(compiled_model):
    with pytest.raises(ValueError, match="TASK8_MUJOCO_VERSION_MISMATCH"):
        compiled_qpos_mapping(compiled_model, expected_model_sha256=MODEL_SHA256,
                               expected_mujoco_version="3.4.0")


def sources(*, cup_shift=0.0, scene_step=1, world_epoch=1, rgb_stamp=1.01,
            expected_model_sha256=MODEL_SHA256, reference_shift=0.0):
    now = [10.0]
    object_state = ObjectState(
        body_id=1, body="cup", position_world=(0.1, -0.2, 0.15),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        linear_velocity_world=(0.0, 0.0, 0.0),
        angular_velocity_world=(0.0, 0.0, 0.0),
    )
    world_evidence = SimulationEvidence(
        simulation_time_s=1.01, frame_id="world", publisher_sequence=1,
        simulation_step=1, reset_epoch=world_epoch, simulation_session_id="s",
        paused=False, object_state=object_state, has_contact=False,
        minimum_signed_distance_m=0.0, maximum_normal_force_n=0.0,
        truncated=False, left_fingertip_contacts=(), right_fingertip_contacts=(),
        other_object_contacts=(),
    )

    class World:
        def __init__(self):
            self.entries = [ReceivedSimulationEvidence(world_evidence, 10.0)]

        def snapshot_with_receipt(self):
            return self.entries[-1]

        def recent_with_receipts(self):
            return tuple(self.entries)

    scene = SceneStateObserver(model_sha256="1" * 64, nq=14, nv=12,
                               max_age_s=0.15, monotonic=lambda: now[0])
    scene.reset("s", 1, source_floor_s=1.0)
    qpos = [0.1] * 6 + [0.05, 0.1 + cup_shift, -0.2, 0.15, 1.0, 0.0, 0.0, 0.0]
    assert scene.accept(dict(
        simulation_session_id="s", reset_epoch=1, simulation_step=scene_step,
        paused=False, simulation_time_s=1.01, model_sha256="1" * 64,
        qpos=qpos, qvel=[0.0] * 12,
    ))
    contacts = RobotContactObserver(
        known_geoms={"arm", "table"}, allowed_pairs=set(), max_age_s=0.15,
        max_sim_gap_s=0.02, monotonic=lambda: now[0],
    )
    contacts.reset("s", 1, source_floor_s=1.0)
    contacts.accept(dict(
        simulation_session_id="s", reset_epoch=1, physics_step=1,
        simulation_time_s=1.01, geom_a=[], geom_b=[], signed_distance_m=[],
        normal_force_n=[], truncated=False, evidence_loss=False,
    ))
    rgb = RgbObservationSynchronizer(max_age_s=0.03, max_skew_s=0.005,
                                     monotonic=lambda: now[0])
    rgb.reset("s")
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    rgb.push("head", "s", rgb_stamp, pixels)
    rgb.push("wrist", "s", rgb_stamp, pixels)
    rgb.push("arm", "s", 1.01, (0.1,) * 6)
    rgb.push("neck", "s", 1.01, 0.05)

    class Broker:
        enabled = True

        def reference_state(self, when):
            if not self.enabled:
                raise RuntimeError("reference temporarily unavailable")
            return dict(positions=(0.1 + reference_shift,) * 6, velocities=(0.0,) * 6,
                        accelerations=(0.0,) * 6, requested_sim_time_s=when)

    readback = Task8PhysicalReadback(
        World(), scene, contacts, rgb, Broker(),
        model=loaded_model(), expected_model_sha256=expected_model_sha256,
        expected_mujoco_version="3.12.0",
        max_source_skew_s=0.005, max_wall_age_s=0.15,
        joint_tolerance_rad=0.001, cup_pose_tolerance_m=0.001,
        cup_orientation_tolerance=0.001, monotonic=lambda: now[0],
    )
    return readback, scene, contacts, now


def test_readback_constructor_rejects_a_model_outside_activated_policy():
    with pytest.raises(ValueError, match="TASK8_MODEL_HASH_MISMATCH"):
        sources(expected_model_sha256="2" * 64)


def test_one_physics_step_joins_cup_pose_qpos_rgb_contact_and_reference():
    readback, _, _, _ = sources()
    proof = readback.capture("s", "attempt-1", 1)
    assert proof["world"].simulation_step == proof["scene"]["simulation_step"] == proof["contact"]["physics_step"] == 1
    assert proof["observation"]["state"][:6] == (0.1,) * 6
    assert proof["reference"]["requested_sim_time_s"] == 1.01
    assert proof["source_received_wall_s"] == {
        key: 10.0 for key in ("world", "scene", "contact", "head", "wrist", "arm", "neck")}


def test_old_selected_camera_receipt_cannot_be_relabelled_at_capture():
    readback, _, _, _ = sources()
    stamp, pixels, _ = readback.rgb.buffers["head"][-1]
    readback.rgb.buffers["head"][-1] = (stamp, pixels, 9.0)
    with pytest.raises(Task8ReadbackError, match="SOURCE_RECEIPT_INVALID"):
        readback.capture("s", "attempt-1", 1)


def test_readback_uses_the_observation_and_receipts_from_one_atomic_sample():
    readback, _, _, _ = sources()
    original = readback.rgb

    class AtomicRgb:
        def sample_with_audit(self, *args):
            return original.sample_with_audit(*args)

        @property
        def last_audit(self):
            raise AssertionError("separate audit lookup")

    readback.rgb = AtomicRgb()
    assert readback.capture("s", "attempt-1", 1)["source_received_wall_s"]["head"] == 10.0


def test_duplicate_world_step_cannot_refresh_an_old_observation_receipt():
    readback, _, _, now = sources()
    old = readback.world.entries[-1]
    readback.world.entries.append(ReceivedSimulationEvidence(old.evidence, 10.01))
    now[0] = 10.02
    with pytest.raises(Task8ReadbackError, match="WORLD_READBACK_UNAVAILABLE"):
        readback.capture("s", "attempt-1", 1)


def test_same_step_controller_reference_disagreement_denies_readback():
    readback, _, _, _ = sources(reference_shift=0.01)
    with pytest.raises(Task8ReadbackError, match="REFERENCE_JOINT_DIVERGED"):
        readback.capture("s", "attempt-1", 1)


def test_actual_cup_pose_disagreement_with_same_step_qpos_is_rejected():
    readback, _, _, _ = sources(cup_shift=0.01)
    with pytest.raises(Task8ReadbackError, match="CUP_QPOS_DIVERGED"):
        readback.capture("s", "attempt-1", 1)


@pytest.mark.parametrize("changes, reason", [
    ({"scene_step": 2}, "SOURCE_STEP_MISMATCH"),
    ({"world_epoch": 2}, "SOURCE_SCOPE_MISMATCH"),
    ({"rgb_stamp": 0.9}, "RGB_READBACK_UNAVAILABLE"),
])
def test_cross_source_mismatch_or_stale_rgb_denies_phase_readback(changes, reason):
    readback, _, _, _ = sources(**changes)
    with pytest.raises(Task8ReadbackError, match=reason):
        readback.capture("s", "attempt-1", 1)


def test_contact_gap_or_wall_staleness_denies_phase_readback():
    readback, _, contacts, now = sources()
    contacts.accept(dict(
        simulation_session_id="s", reset_epoch=1, physics_step=3,
        simulation_time_s=1.03, geom_a=[], geom_b=[], signed_distance_m=[],
        normal_force_n=[], truncated=False, evidence_loss=False,
    ))
    with pytest.raises(Task8ReadbackError, match="CONTACT_READBACK_UNAVAILABLE"):
        readback.capture("s", "attempt-1", 1)
    readback, _, _, now = sources()
    now[0] = 10.2
    with pytest.raises(Task8ReadbackError, match="WORLD_READBACK_UNAVAILABLE"):
        readback.capture("s", "attempt-1", 1)


def test_async_latest_frames_join_the_previous_common_physics_step():
    readback, _, contacts, _ = sources()
    newest = readback.world.entries[-1]
    readback.world.entries.append(ReceivedSimulationEvidence(
        replace(newest.evidence, simulation_step=2, publisher_sequence=2,
                simulation_time_s=1.02), 10.0,
    ))
    contacts.accept(dict(
        simulation_session_id="s", reset_epoch=1, physics_step=2,
        simulation_time_s=1.02, geom_a=[], geom_b=[], signed_distance_m=[],
        normal_force_n=[], truncated=False, evidence_loss=False,
    ))
    proof = readback.capture("s", "attempt-1", 1)
    assert proof["world"].simulation_step == proof["scene"]["simulation_step"] == proof["contact"]["physics_step"] == 1


def test_step_cursor_waits_for_a_new_common_step_without_consuming_rgb():
    readback, scene, contacts, _ = sources()
    assert readback.capture("s", "attempt-1", 1)["world"].simulation_step == 1
    with pytest.raises(Task8ReadbackError, match="SOURCE_STEP_NOT_ADVANCED"):
        readback.capture("s", "attempt-1", 1, after_step=1)

    latest = readback.world.entries[-1]
    readback.world.entries.append(ReceivedSimulationEvidence(
        replace(latest.evidence, simulation_step=2, publisher_sequence=2,
                simulation_time_s=1.02), 10.0,
    ))
    next_scene = scene.snapshot()
    assert scene.accept({**next_scene, "simulation_step": 2, "simulation_time_s": 1.02})
    contacts.accept(dict(
        simulation_session_id="s", reset_epoch=1, physics_step=2,
        simulation_time_s=1.02, geom_a=[], geom_b=[], signed_distance_m=[],
        normal_force_n=[], truncated=False, evidence_loss=False,
    ))
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    for stream, value in (("head", pixels), ("wrist", pixels),
                          ("arm", (0.1,) * 6), ("neck", 0.05)):
        readback.rgb.push(stream, "s", 1.02, value)
    assert readback.capture("s", "attempt-1", 1, after_step=1)["world"].simulation_step == 2


@pytest.mark.parametrize("cursor", [-1, True, 1.0])
def test_step_cursor_refuses_noninteger_or_negative_values(cursor):
    readback, _, _, _ = sources()
    with pytest.raises(Task8ReadbackError, match="SOURCE_STEP_CURSOR_INVALID"):
        readback.capture("s", "attempt-1", 1, after_step=cursor)


def test_failed_broker_lookup_does_not_consume_rgb_decision_time():
    readback, _, _, _ = sources()
    readback.broker.enabled = False
    with pytest.raises(Task8ReadbackError, match="REFERENCE_READBACK_UNAVAILABLE"):
        readback.capture("s", "attempt-1", 1)
    readback.broker.enabled = True
    assert readback.capture("s", "attempt-1", 1)["observation"]["sim_time_s"] == 1.01


def test_world_history_is_bounded_and_cleared_on_reset(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module

    readback, _, _, now = sources()
    example = readback.world.entries[0].evidence
    monkeypatch.setattr(world_module, "convert_message", lambda value: value)

    class Node:
        def create_subscription(self, *_args):
            return None

    world = world_module.MujocoWorldObserver(Node(), "s", max_age_s=0.15,
                                              monotonic=lambda: now[0])
    for step in range(1, 301):
        world.accept(replace(example, simulation_step=step, publisher_sequence=step,
                             simulation_time_s=1.0 + step * 0.01), received_at_s=10.0)
    recent = world.recent_with_receipts()
    assert len(recent) == 256
    assert recent[0].evidence.simulation_step == 45
    world.accept(replace(example, reset_epoch=2, simulation_step=0,
                         publisher_sequence=301, paused=True,
                         simulation_time_s=4.1), received_at_s=10.0)
    assert [entry.evidence.reset_epoch for entry in world.recent_with_receipts()] == [2]


def test_task8_world_history_latches_rejected_or_missing_atomic_frames(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module

    readback, _, _, now = sources()
    example = readback.world.entries[0].evidence
    monkeypatch.setattr(world_module, "convert_message", lambda value: value)

    class Node:
        def create_subscription(self, *_args):
            return None

    world = world_module.MujocoWorldObserver(Node(), "s", monotonic=lambda: now[0])
    world._callback(example)
    world._callback(replace(example, publisher_sequence=2, simulation_step=2,
                            simulation_time_s=1.02, truncated=True))
    with pytest.raises(world_module.EvidenceRejected, match="truncated"):
        world.recent_with_receipts()
    world.accept(replace(example, reset_epoch=2, simulation_step=0, paused=True,
                         publisher_sequence=3), received_at_s=10.0)
    assert len(world.recent_with_receipts()) == 1
    world.accept(replace(example, reset_epoch=2, simulation_step=1,
                         publisher_sequence=5), received_at_s=10.0)
    with pytest.raises(world_module.EvidenceRejected, match="sequence gap"):
        world.recent_with_receipts()


def test_scene_and_contact_histories_are_bounded_reset_scoped_and_hazard_fenced():
    readback, scene, contacts, _ = sources()
    scene_seed = scene.snapshot()
    contact_seed = contacts.snapshot()
    for step in range(2, 515):
        scene.accept({**scene_seed, "simulation_step": step,
                      "simulation_time_s": 1.01 + (step - 1) * 0.001})
        contacts.accept({**contact_seed, "physics_step": step,
                         "simulation_time_s": 1.01 + (step - 1) * 0.001})
    assert len(scene.recent_frames()) == 256
    assert len(contacts.recent_frames()) == 512
    assert scene.recent_frames()[0]["simulation_step"] == 259
    assert contacts.recent_frames()[0]["physics_step"] == 3
    contacts.accept({**contact_seed, "physics_step": 515,
                     "simulation_time_s": 1.524, "geom_a": ["arm"],
                     "geom_b": ["table"], "signed_distance_m": [-0.001],
                     "normal_force_n": [1.0]})
    with pytest.raises(ValueError, match="ROBOT_CONTACT_HAZARD"):
        contacts.recent_frames()
    scene.reset("s", 2, source_floor_s=2.0)
    contacts.reset("s", 2, source_floor_s=2.0)
    with pytest.raises(ValueError, match="SCENE_STATE_UNAVAILABLE"):
        scene.recent_frames()
    with pytest.raises(ValueError, match="CONTACT_UNAVAILABLE"):
        contacts.recent_frames()
