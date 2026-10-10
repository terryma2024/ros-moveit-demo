"""D2: the post_release control is realisable on the cleaned ACT model, and nothing else in the collector moved.

With the cup joint's inherited frictionloss/armature gone, the cup no longer rides the scripted release: it stays against the
fixed pad, so the 'no fingertip contact' predicate was never met. The release now opens to the policy's release_q6 and then
retreats along the motion policy's own RECOVER_RETREAT waypoints (the Teacher's OPEN_GRIPPER -> RETREAT at the pick pose);
only phases after "hold" changed. GOLDEN holds sha256 of each other regime's complete sample window (frames without the
receipt clock, scenario, diagnostic result) produced by the collector BEFORE D2 on the same model.
"""
import hashlib
import json

import pytest
from paths import PACKAGE_ROOT

pytestmark = pytest.mark.fast
PACKAGE = PACKAGE_ROOT
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
MOTION = PACKAGE / "config/policies/light_cup_wall_pick/mujoco.yaml"
GOLDEN = {
    "no_contact:0": "bf4826ead84092ef0badacbb7776a2b8fd48f03edafc24881a872cb6b4b4307e",
    "no_contact:7": "cb2f4d7b5cf6408fcf04f5da347c5d50e3c85d145257c420e92266384a347e3d",
    "table_only:0": "f12b04e2163421007ee8884ea0ee7596edb5f8bb73e161887b53463a006747f1",
    "table_only:7": "261901d42b2bfbff587736cc9874b7e94c0433d38e55b14cadb6288246733943",
    "left_only:0": "f4470ad4a163f9d94104af2db7c68535366dd20ee567f5c4ab7fd6c9b762bf8b",
    "left_only:7": "e3056136d869fc3e341567ed124f118cef47949c4e5c54a1a7b3ccd3aaeb567c",
    "right_only:0": "abe79a18f6fd928ac75f2ef1d980861ad626735982ffb2a23718cb743d3fa494",
    "right_only:7": "cf28cbfb04a5e628ebd41fccfc2497fda642cbafe91e30f78b2b3e5247f25c15",
    "bilateral_touch:0": "2b368bdc07fe5e8d7f260a4f0edbb860c6bd59914f4059683ce061cdb645c771",
    "bilateral_touch:7": "70f9630e7b0082ccdb5fe1183753f00de1c1dd75795aa96683b8383027e1ec62",
    "over_compression:0": "2ae2725fe04c800ed3edf23f31a55eea1c051ddc0857d0654ff569ab38672ab9",
    "over_compression:7": "4767ebb508bde3900b0fcf97389b3a6dcac93156e6cb2408b79b77191a253126",
    "micro_lift_slip:0": "5b18b43da897b43ac49c6587d0985ffccd4cb2bc70078b250a64ab87f29181d4",
    "micro_lift_slip:7": "4b775fb8c99ca24723dab6ab63c7013a2428cd2fa7de6cc366833710ad2eaaa1",
    "stable_hold:0": "d88c68de4c0dec69df251a092adc35708b4bd75024720887082e115a350075c2",
    "stable_hold:7": "5efd43ed70755da56cb1253b22d159a3dca2eb6f47897b857388c4c4454e7a40",
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
