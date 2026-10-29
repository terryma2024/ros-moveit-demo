"""Physical offline collector checks against the pinned ACT MuJoCo scene."""

import hashlib

import pytest
from paths import PACKAGE_ROOT


PACKAGE = PACKAGE_ROOT
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
MOTION = PACKAGE / "config/policies/light_cup_wall_pick/mujoco.yaml"


def _pinned():
    mujoco = pytest.importorskip("mujoco")
    if mujoco.mj_versionString() != "3.12.0":
        pytest.skip("physical collector requires plugin-linked MuJoCo 3.12.0")


@pytest.mark.parametrize("regime", [
    "no_contact", "table_only", "bilateral_touch", "over_compression",
    "micro_lift_slip", "stable_hold",
    "post_release", "left_only", "right_only",
])
def test_offline_collector_records_real_contacts_and_state(regime):
    _pinned()
    from so101_demo.act.contact_collector import collect_offline_sample
    sample = collect_offline_sample(
        SCENE, MOTION, regime=regime, seed=0,
        sample_id=f"offline-{regime}-000", config_sha256="f" * 64,
    )
    assert sample["source"] == "offline"
    assert sample["regime"] == regime
    assert sample["scene_sha256"] == hashlib.sha256(SCENE.read_bytes()).hexdigest()
    assert sample["motion_policy_sha256"] == hashlib.sha256(MOTION.read_bytes()).hexdigest()
    assert len(sample["frames"]) >= 2
    assert all(frame["model_qpos"] and frame["model_qvel"] for frame in sample["frames"])
    assert sample["diagnostic_result"]["status"] == "PASS"
    final = sample["frames"][-1]
    if regime == "left_only":
        assert final["left_contacts"] and not final["right_contacts"]
    elif regime == "right_only":
        assert final["right_contacts"] and not final["left_contacts"]
    elif regime == "post_release":
        assert final["table_supported"] and final["released"]
        assert not final["left_contacts"] and not final["right_contacts"]
    elif regime in {"no_contact", "table_only"}:
        assert final["table_supported"]
        assert not final["left_contacts"] and not final["right_contacts"]
    else:
        assert final["left_contacts"] and final["right_contacts"]


def test_offline_collector_replays_same_physical_state_for_seed():
    _pinned()
    from so101_demo.act.contact_collector import collect_offline_sample
    first = collect_offline_sample(
        SCENE, MOTION, regime="bilateral_touch", seed=7,
        sample_id="offline-touch-007", config_sha256="f" * 64,
    )
    second = collect_offline_sample(
        SCENE, MOTION, regime="bilateral_touch", seed=7,
        sample_id="offline-touch-007", config_sha256="f" * 64,
    )
    assert first["scenario_sha256"] == second["scenario_sha256"]
    for a, b in zip(first["frames"], second["frames"], strict=True):
        for key in ("physics_step", "simulation_time_s", "left_contacts", "right_contacts",
                    "other_contacts", "cup_position_m", "cup_velocity_m_s", "model_qpos", "model_qvel"):
            assert a[key] == b[key]


SIDE_WRIST_SCENE = PACKAGE / "assets/mujoco/act/scene_side_wrist.xml"
SIDE_WRIST_PROFILE = PACKAGE / "config/act/rig-v2.yaml"


@pytest.mark.parametrize("rig,scene", [("head-wrist", SCENE), ("side-wrist", SIDE_WRIST_SCENE),
                                       ("side-wrist-indoor", SIDE_WRIST_SCENE.with_name("scene_side_wrist_indoor.xml"))])
def test_every_rig_pin_is_the_recompiled_identity(rig, scene):
    mujoco = pytest.importorskip("mujoco")
    from so101_demo.act.contact_collector import RIG_IDENTITIES, rig_identity
    from so101_demo.adapters.act.physics import model_sha256
    assert set(RIG_IDENTITIES) == {"head-wrist", "side-wrist", "side-wrist-indoor"}
    assert rig_identity(rig) == (hashlib.sha256(scene.read_bytes()).hexdigest(),
                                 model_sha256(mujoco.MjModel.from_xml_path(str(scene))))


def test_the_head_wrist_pins_are_unchanged_and_the_side_wrist_ones_are_its_own():
    from so101_demo.act import contact_collector as c
    assert c._SCENE_SHA256 == "ea7e18df15dd67e8beddcc35d66eab6fda128145a7877b578fc641d282c114cb"
    assert c._MODEL_SHA256 == "17c415d9541be3c13ce43d8650a0879b5b2d7f62177cca7601500fd94d3d878e"
    assert c.rig_identity(None) == c.rig_identity("head-wrist") == (c._SCENE_SHA256, c._MODEL_SHA256)
    assert c.rig_identity("side-wrist") == (
        "611ed1e4645248d6fa3620ad95194993fd09915351fbe34fae30074ddf35c383",
        "9f16f382839c80fc2a0a26a59bf7723e6d920b730febd864f13a391d3179350c")
    with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
        c.rig_identity("no-such-rig")


@pytest.mark.parametrize("regime", ["no_contact", "bilateral_touch", "stable_hold", "post_release"])
def test_offline_collector_accepts_the_side_wrist_scene_under_its_rig(regime):
    _pinned()
    from so101_demo.act.contact_collector import collect_offline_sample, rig_identity
    sample = collect_offline_sample(
        SIDE_WRIST_SCENE, MOTION, regime=regime, seed=0, sample_id=f"offline-{regime}-000",
        config_sha256="f" * 64, rig="side-wrist",
    )
    scene_pin, model_pin = rig_identity("side-wrist")
    assert (sample["scene_sha256"], sample["model_sha256"]) == (scene_pin, model_pin)
    assert sample["diagnostic_result"]["status"] == "PASS"


@pytest.mark.parametrize("scene,rig", [(SCENE, "side-wrist"), (SIDE_WRIST_SCENE, "head-wrist"), (SIDE_WRIST_SCENE, None)])
def test_offline_collector_refuses_a_scene_of_another_rig(scene, rig):
    _pinned()
    from so101_demo.act.contact_collector import collect_offline_sample
    with pytest.raises(ValueError, match="hash mismatch"):
        collect_offline_sample(scene, MOTION, regime="no_contact", seed=0, sample_id="offline-no_contact-000",
                               config_sha256="f" * 64, rig=rig)


def test_the_calibration_cli_takes_the_rig_and_refuses_another_rigs_scene(tmp_path):
    _pinned()
    from so101_demo.cli.act_collect_contact_calibration import main
    root = tmp_path / "cohort"
    with pytest.raises(ValueError, match="not the scene of rig side-wrist"):
        main(["--mode", "offline", "--scene", str(SCENE), "--motion-policy", str(MOTION),
              "--output-root", str(root), "--rig-profile", str(SIDE_WRIST_PROFILE)])
    with pytest.raises(ValueError, match="not the scene of rig head-wrist"):
        main(["--mode", "offline", "--scene", str(SIDE_WRIST_SCENE), "--motion-policy", str(MOTION),
              "--output-root", str(root)])
    assert not root.exists()
