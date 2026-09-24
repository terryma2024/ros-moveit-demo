"""Physical offline collector checks against the pinned ACT MuJoCo scene."""

import hashlib
from pathlib import Path

import pytest


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
MOTION = PACKAGE / "config/policies/light_cup_wall_pick/v1/mujoco.yaml"


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
