"""A phase readback must join actual physics, contact, RGB and controller sources."""

import numpy as np
import pytest
import mujoco
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
            expected_model_sha256=MODEL_SHA256):
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
        def snapshot_with_receipt(self):
            return ReceivedSimulationEvidence(world_evidence, 10.0)

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
    rgb = RgbObservationSynchronizer(max_age_s=0.03, max_skew_s=0.005)
    rgb.reset("s")
    pixels = np.zeros((480, 640, 3), dtype=np.uint8)
    rgb.push("head", "s", rgb_stamp, pixels)
    rgb.push("wrist", "s", rgb_stamp, pixels)
    rgb.push("arm", "s", 1.01, (0.1,) * 6)
    rgb.push("neck", "s", 1.01, 0.05)

    class Broker:
        def reference_state(self, when):
            return dict(positions=(0.1,) * 6, velocities=(0.0,) * 6,
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
