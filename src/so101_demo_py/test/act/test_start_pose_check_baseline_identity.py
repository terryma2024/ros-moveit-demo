"""R3-a review fix 6: the collision baseline is taken at the reset keyframe (not at qpos0), and the check names the model it ran on
(scene sha256, compiled model sha256, physics fingerprints) so the start pose record can be verified against the frozen inputs."""

import hashlib

import pytest

from so101_demo.act import teacher_diversity as td
from paths import PACKAGE_ROOT

mujoco = pytest.importorskip("mujoco")

# qpos0 puts the cup inside the arm link (a contact the keyframe does not have); the keyframe puts it clear of the arm
XML = """
<mujoco>
  <compiler angle="radian"/>
  <worldbody>
    <geom name="table_collision" type="box" size="1 1 0.05" pos="0 0 -0.05"/>
    <body name="base" pos="0 0 0.03">
      <inertial pos="0 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>
      <joint name="1" type="hinge" axis="0 0 1" range="-3 3"/>
      <body name="link" pos="0 0 0">
        <inertial pos="0.1 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>
        <joint name="2" type="hinge" axis="0 1 0" range="-1.7 1.7"/>
        <geom name="arm_link" type="capsule" fromto="0 0 0 0.25 0 0" size="0.02"/>
      </body>
    </body>
    <body name="plastic_cup" pos="0.12 0 0.05">
      <freejoint name="cup_free_joint"/>
      <geom name="cup_collision" type="cylinder" size="0.03 0.05"/>
    </body>
  </worldbody>
  <keyframe><key name="task_start" qpos="0 0 0.6 0.6 0.05 1 0 0 0"/></keyframe>
</mujoco>
"""


def test_the_baseline_is_the_keyframe_not_qpos0():
    checker = td.StartPoseCollisionCheck.from_xml_string(XML, cup_body="plastic_cup", joint_names=("1", "2"))
    assert checker.check((0.0, 0.0)) == (True, "")                                    # keyframe cup is clear of the arm
    # the cup placed in the arm is a collision. A baseline taken at qpos0 (the cup inside the arm) would have excused it
    accepted, reason = checker.check((0.0, 0.0), cup_position=(0.12, 0.0, 0.05))
    assert accepted is False and "cup_collision" in reason


def test_a_model_whose_keyframe_already_has_a_contact_excuses_exactly_that_contact():
    clash = XML.replace('qpos="0 0 0.6 0.6 0.05 1 0 0 0"', 'qpos="0 0 0.12 0 0.05 1 0 0 0"')
    checker = td.StartPoseCollisionCheck.from_xml_string(clash, cup_body="plastic_cup", joint_names=("1", "2"))
    assert checker.check((0.0, 0.0)) == (True, "")


def test_the_check_names_the_model_it_ran_on(tmp_path):
    path = tmp_path / "scene.xml"
    path.write_text(XML)
    checker = td.StartPoseCollisionCheck.from_path(path, cup_body="plastic_cup", joint_names=("1", "2"))
    identity = checker.identity()
    assert identity["scene_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    model = mujoco.MjModel.from_xml_path(str(path))
    from so101_demo.act.physics_fingerprint import physics_fingerprint, stripped_physics_fingerprint_of_file

    assert identity["physics_fingerprint"] == physics_fingerprint(model)
    assert identity["physics_fingerprint_v2"] == stripped_physics_fingerprint_of_file(path)
    assert len(identity["model_sha256"]) == 64 and identity["mujoco_version"] == mujoco.__version__
    assert checker.identity() == identity


def test_the_identity_of_the_real_rig_scene_matches_its_compiled_model_hash():
    scene = PACKAGE_ROOT / "assets/mujoco/act/scene_side_wrist.xml"
    checker = td.StartPoseCollisionCheck.from_path(scene, cup_body="plastic_cup", joint_names=("1", "2", "3", "4", "5", "6"))
    identity = checker.identity()
    model = mujoco.MjModel.from_xml_path(str(scene))
    buffer = __import__("numpy").empty(mujoco.mj_sizeModel(model), dtype="uint8")
    mujoco.mj_saveModel(model, None, buffer)
    assert identity["model_sha256"] == hashlib.sha256(buffer.tobytes()).hexdigest()     # the recipe of the execution snapshot's model_sha256
    assert identity["scene_sha256"] == hashlib.sha256(scene.read_bytes()).hexdigest()
