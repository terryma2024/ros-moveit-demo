"""Only same-step lossless bilateral evidence establishes a held cup."""

import copy
from pathlib import Path

import mujoco
import pytest

from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.held_cup_state import held_cup_attachment
from so101_demo.adapters.act.scene_state import SceneStateObserver
from so101_demo.act.contact_live import LivePhysicsStream


SCENE = Path(__file__).resolve().parents[1] / "assets/mujoco/act/scene.xml"


def evidence():
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_KEY, "task_start"))
    cup = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    address = int(model.jnt_qposadr[cup])
    data.qpos[address:address + 7] = (.02, -.28, .165, 1., 0., 0., 0.)
    mujoco.mj_forward(model, data)
    digest = model_sha256(model)
    scene = dict(simulation_session_id="held-source", reset_epoch=3,
                 simulation_step=24, simulation_time_s=1.048, paused=False,
                 model_sha256=digest, qpos=data.qpos.tolist(), qvel=data.qvel.tolist())
    left = dict(robot_geom="fixed_fingertip_pad_collision_006", object_body="plastic_cup",
                normal_force_n=.22, signed_distance_m=-.00003)
    right = dict(robot_geom="moving_fingertip_pad_collision_000", object_body="plastic_cup",
                 normal_force_n=.23, signed_distance_m=-.00003)
    step = dict(simulation_session_id="held-source", reset_epoch=3,
                physics_step=24, simulation_time_s=1.048, model_sha256=digest,
                model_qpos=data.qpos.tolist(), model_qvel=data.qvel.tolist(),
                cup_position_m=data.qpos[address:address + 3].tolist(),
                received_monotonic_s=100., left_contacts=[left], right_contacts=[right],
                released=False)
    return model, scene, step


def test_held_attachment_is_rigid_and_scope_bound():
    model, scene, step = evidence()
    transform = held_cup_attachment(model, scene, step, scene_received_monotonic_s=100.,
                                    now_monotonic_s=100.05,
                                    max_age_s=.2, minimum_bilateral_force_n=.1)
    assert len(transform) == 4 and all(len(row) == 4 for row in transform)
    assert transform[3] == [0., 0., 0., 1.]


@pytest.mark.parametrize("field,changed", [
    ("physics_step", 23), ("reset_epoch", 2),
    ("simulation_time_s", 1.046), ("model_sha256", "0" * 64),
    ("released", True),
])
def test_held_attachment_rejects_wrong_physics_identity(field, changed):
    model, scene, step = evidence()
    step[field] = changed
    with pytest.raises(ValueError):
        held_cup_attachment(model, scene, step, scene_received_monotonic_s=100.,
                            now_monotonic_s=100.05,
                            max_age_s=.2, minimum_bilateral_force_n=.1)


def test_held_attachment_rejects_stale_weak_or_inconsistent_state():
    model, scene, step = evidence()
    cases = []
    changed = copy.deepcopy(step)
    changed["right_contacts"][0]["normal_force_n"] = .01
    cases.append((scene, changed, 100.05))
    changed = copy.deepcopy(step)
    changed["model_qpos"][0] += .001
    cases.append((scene, changed, 100.05))
    changed = copy.deepcopy(step)
    changed["model_qvel"][0] += .001
    cases.append((scene, changed, 100.05))
    changed = copy.deepcopy(scene)
    changed["paused"] = True
    cases.append((changed, step, 100.05))
    cases.append((scene, step, 100.25))
    for frame, physics, now in cases:
        with pytest.raises(ValueError):
            held_cup_attachment(model, frame, physics, scene_received_monotonic_s=100.,
                                now_monotonic_s=now,
                                max_age_s=.2, minimum_bilateral_force_n=.1)


def test_lossless_step_lookup_is_bounded_immutable_and_fails_closed(tmp_path):
    recorder = LivePhysicsStream(session_id="held-source", reset_epoch=3,
        model_sha256="a" * 64, model_nq=3, model_nv=3,
        cup_qpos_address=0, cup_qvel_address=0,
        diagnostic_limits=dict(maximum_force_n=3., maximum_displacement_m=.03,
                               maximum_ros_skew_s=.02, maximum_receipt_age_s=.2),
        output_path=tmp_path / "physics.ndjson", monotonic=lambda: 100.)
    with pytest.raises(ValueError):
        recorder.validated_step(1, now_monotonic_s=100., max_age_s=.2)
    step = dict(simulation_session_id="held-source", reset_epoch=3, physics_step=1,
                simulation_time_s=.002, model_qpos=[.02, -.28, .165], model_qvel=[0.] * 3,
                cup_position_m=[.02, -.28, .165], cup_velocity_m_s=[0.] * 3,
                left_contacts=[], right_contacts=[], other_contacts=[], truncated=False,
                diagnostic_hazard_breached=False)
    chunk = dict(chunk_sequence=1, simulation_session_id="held-source", reset_epoch=3,
                 first_physics_step=1, last_physics_step=1,
                 first_simulation_time_s=.002, last_simulation_time_s=.002,
                 failed_publish_attempts=0, evidence_loss=False, samples=[step])
    recorder.accept_chunk(chunk, ros_time_s=.002)
    first = recorder.validated_step(1, now_monotonic_s=100.05, max_age_s=.2)
    first["model_qpos"][0] = 99.
    assert recorder.validated_step(1, now_monotonic_s=100.05,
                                   max_age_s=.2)["model_qpos"][0] == .02
    for number, now in ((2, 100.05), (1, 100.25)):
        with pytest.raises(ValueError):
            recorder.validated_step(number, now_monotonic_s=now, max_age_s=.2)
    recorder.close()


def test_scene_snapshot_keeps_frame_and_receipt_atomic():
    model, scene, _ = evidence()
    clock = [100.]
    observer = SceneStateObserver(model_sha256=model_sha256(model), nq=model.nq,
                                  nv=model.nv, max_age_s=.2,
                                  monotonic=lambda: clock[0])
    observer.reset("held-source", 3, source_floor_s=1.)
    assert observer.accept(scene)
    frame, received = observer.snapshot_with_receipt()
    assert received == 100. and frame == scene
    frame["qpos"][0] += 1.
    assert observer.snapshot()["qpos"][0] == scene["qpos"][0]
    clock[0] = 100.25
    with pytest.raises(ValueError, match="SCENE_STATE_STALE"):
        observer.snapshot_with_receipt()
