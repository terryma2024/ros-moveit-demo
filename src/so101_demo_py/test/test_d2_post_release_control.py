"""D2: the post_release control is realisable on the cleaned ACT model, and nothing else in the collector moved.

With the cup joint's inherited frictionloss/armature gone, the cup no longer rides the scripted release: it stays against the
fixed pad, so the 'no fingertip contact' predicate was never met. The release now opens to the policy's release_q6 and then
retreats along the motion policy's own RECOVER_RETREAT waypoints (the Teacher's OPEN_GRIPPER -> RETREAT at the pick pose);
only phases after "hold" changed. GOLDEN holds sha256 of each other regime's complete sample window (frames without the
receipt clock, scenario, diagnostic result) produced by the collector BEFORE D2 on the same model.
"""
import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast
PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
MOTION = PACKAGE / "config/policies/light_cup_wall_pick/v1/mujoco.yaml"
GOLDEN = {
    "no_contact:0": "520cc6dcd81ef646f54ab99607ca7d24f72f4927b75f11393520e57625e874b0",
    "no_contact:7": "cb79bc31a65e12b3bc8f1bf373b74ba284398fc25f4fd8b3a7f5e4dd9a9c36f3",
    "table_only:0": "bc0026a363986059367fc6c296ca4f8ab9ffecf7ca5e68fc3948c3cfee29dc72",
    "table_only:7": "b1de41d787fb958ca8c1d7cd3075ef06e07840331fdc37d45d9bb23700b41d4e",
    "left_only:0": "b1a5702f9fee3eeb2530cca04204f175761cf5beaded92c32d8cd81e3b308ef4",
    "left_only:7": "7cc9c0ebdb4fc280bad042a79d8567f5ff017f3492c851dfea60345907fa8428",
    "right_only:0": "5ab7fd5be8d03e41b67976e25a0e3236a385af1e935714c09d3687e80f27125b",
    "right_only:7": "333be6a6213ac22092ad22eb39fb68816cd7e1e959e10d4b556218567d2e66e6",
    "bilateral_touch:0": "4214347c8c64c7b8927e01731386ede979c7775c60cb34f927090fa968019e2f",
    "bilateral_touch:7": "f8cfe7a79c78e6f6331adb3b7174a302617061eb49fd31064fcc35b0ff02193a",
    "over_compression:0": "4aba4aac70efc8c96612a8db2b8ef86613730cf25b6e7e92c7abb32f47f57eeb",
    "over_compression:7": "5bf2778ebbde0e39d19e29ec45bcb7b037882f3411696799f9881cc92ba438f8",
    "micro_lift_slip:0": "e0e06aee6229bc619d0b74b075c6079c327a03cc629ca3974f4d38a7d1621816",
    "micro_lift_slip:7": "6a5086afdd5b43fc68e4c1fc37255ffeb79b6938226983a7bcb37c227a8f28e5",
    "stable_hold:0": "7b5c6d08d65ea22f5c54f82ad590fe0db78f7034d6df826e8df89f59f1b0b6df",
    "stable_hold:7": "3feed5ab83a3218bdcb56e22ba56385a2519b9e3a3473d7c46e7c56b95c7f632",
}


def collect(regime, seed):
    from so101_demo.act.contact_collector import collect_offline_sample
    return collect_offline_sample(SCENE, MOTION, regime=regime, seed=seed, sample_id=f"d2-{regime}-{seed}",
                                  config_sha256="f" * 64)


def digest(sample):
    frames = [{key: value for key, value in frame.items() if key != "received_monotonic_s"} for frame in sample["frames"]]
    return hashlib.sha256(json.dumps({"regime": sample["regime"], "scenario": sample["scenario"], "frames": frames,
                                      "diag": sample["diagnostic_result"]}, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_post_release_is_realisable_on_the_cleaned_model(seed):
    sample = collect("post_release", seed)
    final = sample["frames"][-1]
    assert len(sample["frames"]) == 6
    assert final["released"] and final["table_supported"]
    assert {item["robot_geom"] for item in final["other_contacts"]} == {"table_collision"}
    assert all(not frame["left_contacts"] and not frame["right_contacts"] for frame in sample["frames"])


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_the_other_eight_regimes_have_identical_windows_before_and_after(key):
    regime, seed = key.split(":")
    assert digest(collect(regime, int(seed))) == GOLDEN[key]


def test_scenarios_predicates_close_values_and_hard_limits_are_unchanged():
    text = (PACKAGE / "src/act/contact_collector.py").read_text()
    assert "_MAX_FORCE_N = 11.6" in text and "_MAX_DISPLACEMENT_M = .03" in text
    assert '"post_release": ("settle_after_release", 6)' in text
    assert 'return step >= 3550 and frame["released"] and table and not left and not right' in text
    assert 'close = -.049 if regime == "over_compression" else policy["gripper_actions"]["grasp_close_q6"]' in text
    assert hashlib.sha256(MOTION.read_bytes()).hexdigest() == "aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356"
