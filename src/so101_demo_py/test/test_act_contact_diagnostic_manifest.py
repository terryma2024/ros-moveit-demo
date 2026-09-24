"""Physical diagnostic motions are frozen before any live command authority."""

from pathlib import Path
import hashlib
import json

import pytest
import mujoco

from so101_demo.act.contact_diagnostic import (
    build_contact_diagnostic_manifest, require_contact_diagnostic_manifest,
    require_contact_diagnostic_sources, prefix_matches_diagnostic,
)
from so101_demo.act.joints import ACT_JOINTS
from so101_demo.adapters.act.physics import MujocoPathChecker


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
MOTION = PACKAGE / "config/policies/light_cup_wall_pick/v1/mujoco.yaml"
PLUGIN = PACKAGE / "config/mujoco/act/mujoco_plugins.yaml"


def _manifest(regime="stable_hold"):
    return build_contact_diagnostic_manifest(
        scene_path=SCENE, motion_policy_path=MOTION, plugin_path=PLUGIN,
        regime=regime, seed=0, session_id="contact-live-one",
        attempt_id="contact-attempt-one",
    )


@pytest.mark.parametrize("regime,rows", [
    ("no_contact", 5), ("bilateral_touch", 45),
    ("over_compression", 50), ("micro_lift_slip", 45),
    ("stable_hold", 50), ("table_only", 5),
    ("post_release", 75), ("left_only", 1), ("right_only", 25),
])
def test_diagnostic_regimes_freeze_real_model_and_controller_grid(regime, rows):
    manifest = _manifest(regime)
    require_contact_diagnostic_manifest(manifest)
    assert manifest["eligible_for_collection"] is False
    assert manifest["backend"] == "mujoco"
    assert manifest["mujoco_version"] == "3.12.0"
    assert manifest["model_sha256"] == "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
    assert manifest["path_step_s"] == .02
    assert manifest["path_clearance_m"] == .002
    assert manifest["velocity_limit_rad_s"] == [.5] * 6
    assert manifest["acceleration_limit_rad_s2"] == [16.] * 6
    assert len(manifest["target_positions"]) == rows
    assert any("fixed_fingertip_pad_collision_006" in pair for pair in manifest["allowed_contact_pairs"])
    prefix = {
        "session_id": manifest["session_id"], "attempt_id": manifest["attempt_id"],
        "sequence": 0, "observation_time_s": 10.0,
        "target_times_s": [round(10.0 + .1 * (index + 1), 9) for index in range(rows)],
        "positions": manifest["target_positions"],
    }
    assert prefix_matches_diagnostic(prefix, manifest)
    prefix["positions"] = [list(row) for row in prefix["positions"]]
    prefix["positions"][-1][-1] += .001
    assert not prefix_matches_diagnostic(prefix, manifest)


def test_diagnostic_manifest_rejects_gazebo_and_source_drift():
    manifest = _manifest()
    with pytest.raises(ValueError):
        require_contact_diagnostic_manifest({**manifest, "backend": "gazebo"})
    with pytest.raises(ValueError):
        require_contact_diagnostic_manifest({**manifest, "eligible_for_collection": True})
    with pytest.raises(ValueError):
        build_contact_diagnostic_manifest(
            scene_path=SCENE, motion_policy_path=MOTION, plugin_path=PLUGIN,
            regime="invalid", seed=0, session_id="contact-live-one",
            attempt_id="contact-attempt-one",
        )


def test_diagnostic_manifest_source_replay_rejects_self_consistent_tamper():
    manifest = _manifest()
    require_contact_diagnostic_sources(manifest)
    altered = {**manifest, "target_positions": [row[:] for row in manifest["target_positions"]]}
    altered["target_positions"][-1][5] += .001
    altered["manifest_sha256"] = hashlib.sha256(json.dumps(
        {key: value for key, value in altered.items() if key != "manifest_sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    require_contact_diagnostic_manifest(altered)
    with pytest.raises(ValueError, match="replay"):
        require_contact_diagnostic_sources(altered)


@pytest.mark.parametrize("regime", [
    "no_contact", "bilateral_touch", "over_compression", "micro_lift_slip",
    "stable_hold", "table_only", "post_release", "left_only", "right_only",
])
def test_diagnostic_route_passes_independent_pinned_path_checker(regime):
    manifest = _manifest(regime)
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    for name, position in zip(
        ACT_JOINTS, (*manifest["joint_start_rad"], manifest["neck_start_rad"]), strict=True
    ):
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[model.jnt_qposadr[joint]] = position
    cup = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    address = model.jnt_qposadr[cup]
    data.qpos[address:address + 3] = manifest["cup_start_m"]
    data.qpos[address + 3:address + 7] = [1., 0., 0., 0.]
    mujoco.mj_forward(model, data)
    checker = MujocoPathChecker(
        model_path=SCENE, protected_roots=("base",), cup_joint="cup_free_joint",
        gripper_body="gripper", path_step_s=manifest["path_step_s"],
        path_clearance_m=manifest["path_clearance_m"],
        velocity_limit_rad_s=manifest["velocity_limit_rad_s"],
        acceleration_limit_rad_s2=manifest["acceleration_limit_rad_s2"],
        allowed_pairs_by_phase={
            "APPROACH": {tuple(pair) for pair in manifest["allowed_contact_pairs"]}
        },
    )
    rows = manifest["target_positions"]
    prefix = {
        "session_id": manifest["session_id"], "attempt_id": manifest["attempt_id"],
        "sequence": 0, "observation_time_s": 0.,
        "target_times_s": [round(.1 * (i + 1), 9) for i in range(len(rows))],
        "positions": rows,
    }
    snapshot = {
        "model_qpos": data.qpos.tolist(), "model_sha256": checker.model_sha256,
        "phase": "APPROACH", "holding_state": "EMPTY", "sim_time_s": 0.,
        "controller_bridge": {
            "time_s": 0., "point": {"positions": manifest["joint_start_rad"],
                                    "velocities": [0.] * 6, "accelerations": []}},
        "controller_start_time_s": manifest["submit_lead_s"],
        "controller_start_positions": manifest["joint_start_rad"],
        "controller_start_velocities": [0.] * 6,
        "cup_in_gripper_transform": None,
    }
    assert checker.check_path(prefix, snapshot), checker.last_check
