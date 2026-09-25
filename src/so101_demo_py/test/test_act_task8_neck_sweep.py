"""SEARCH neck paths must be clear between endpoints in the actual model."""

from pathlib import Path

import mujoco
import pytest

from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_neck_sweep import MujocoNeckSweepChecker


@pytest.fixture
def scene(tmp_path: Path) -> Path:
    path = tmp_path / "scene.xml"
    path.write_text("""
<mujoco>
  <option gravity="0 0 0"/>
  <worldbody>
    <body name="base">
      <body name="neck">
        <joint name="neck_yaw_joint" type="hinge" axis="0 0 1"/>
        <geom name="head_collision" type="capsule" fromto=".1 0 0 .8 0 0" size=".03"/>
      </body>
    </body>
    <body name="obstacle_body" pos="0 .5 0">
      <geom name="obstacle_collision" size=".06"/>
    </body>
  </worldbody>
</mujoco>
""")
    return path


def checker(scene: Path, *, allowed=()):
    model = mujoco.MjModel.from_xml_path(str(scene))
    return MujocoNeckSweepChecker(
        scene, expected_model_sha256=model_sha256(model),
        protected_roots=("base",), allowed_pairs=allowed,
        path_step_s=0.001, path_clearance_m=0.002, max_samples=1000,
    )


def test_clear_endpoints_cannot_hide_interior_neck_collision(scene):
    sweep = checker(scene)
    qpos = (0.0,)
    assert sweep.check(qpos, current_rad=0.0, target_rad=0.0, duration_s=0.1)
    assert sweep.check(qpos, current_rad=0.0, target_rad=3.141592653589793,
                       duration_s=0.1) is False
    assert sweep.last_check["reason"] == "NECK_SWEEP_CONTACT"
    assert sweep.last_check["contact_pair"] == (
        "head_collision", "obstacle_collision")
    assert 0 < sweep.last_check["sample_time_s"] < 0.1
    assert qpos == (0.0,)


def test_neck_sweep_refuses_wrong_qpos_model_and_unbounded_samples(scene):
    sweep = checker(scene)
    assert sweep.check((1.0,), current_rad=0.0, target_rad=0.1,
                       duration_s=0.1) is False
    assert sweep.last_check["reason"] == "NECK_SWEEP_START_MISMATCH"
    assert sweep.check((0.0,), current_rad=0.0, target_rad=0.1,
                       duration_s=2.0) is False
    assert sweep.last_check["reason"] == "NECK_SWEEP_SAMPLE_BUDGET"
    with pytest.raises(ValueError, match="NECK_SWEEP_MODEL_MISMATCH"):
        MujocoNeckSweepChecker(
            scene, expected_model_sha256="0" * 64, protected_roots=("base",),
            allowed_pairs=(), path_step_s=0.001, path_clearance_m=0.002,
        )


def test_only_exact_named_contact_exception_can_allow_sweep(scene):
    sweep = checker(scene, allowed=(("head_collision", "obstacle_collision"),))
    assert sweep.check((0.0,), current_rad=0.0,
                       target_rad=3.141592653589793, duration_s=0.1)
    with pytest.raises(ValueError, match="NECK_SWEEP_CONTACT_CONFIG_INVALID"):
        checker(scene, allowed=(("head_collision", "unknown"),))
