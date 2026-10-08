"""The held-cup route is source-bound before any controller permit exists."""

from act_identity import ACT_MODEL_SHA256
import copy
import json
from pathlib import Path

import pytest

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.held_cup_transfer_profile import (
    build_held_cup_transfer_segments, load_held_cup_transfer_profile,
)


PROFILE = (Path(__file__).resolve().parents[1] /
           "config/mujoco/act/held_cup_transfer_v2.json")
MODEL_SHA = ACT_MODEL_SHA256
POLICY_SHA = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"


def loaded():
    return load_held_cup_transfer_profile(
        PROFILE, expected_model_sha256=MODEL_SHA,
        expected_policy_fingerprint=POLICY_SHA,
    )


@pytest.mark.parametrize("anchor", ["default", "left", "forward"])
def test_transfer_profile_yields_bounded_controller_grid(anchor):
    profile = loaded()
    held = profile["anchors"][anchor]["held_q_rad"]
    segments = build_held_cup_transfer_segments(profile, anchor, held_q_rad=held)
    assert len(segments) == 11
    assert [phase for phase, _ in segments] == ["TRANSPORT"] * 6 + ["ALIGN"] * 5
    assert [len(rows) for _, rows in segments] == [600] + [500] * 9 + [600]
    previous = held
    for sequence, (_, rows) in enumerate(segments):
        prefix = {
            "session_id": "session", "attempt_id": "attempt", "sequence": sequence,
            "observation_time_s": 1.,
            "first_target_delay_s": .1,
            "target_interval_s": .002,
            "target_times_s": [1.1 + .002 * (index + 1)
                               for index in range(len(rows))],
            "positions": rows,
        }
        validate_action_prefix(prefix)
        assert max(abs(a - b) for a, b in zip(previous, rows[0])) < .25
        previous = rows[-1]
    assert previous == profile["anchors"][anchor]["endpoints"][-1]


def test_transfer_profile_rejects_changed_source_and_policy(tmp_path):
    profile = loaded()
    with pytest.raises(ValueError, match="TRANSFER_PROFILE_BINDING_INVALID"):
        load_held_cup_transfer_profile(
            PROFILE, expected_model_sha256="0" * 64,
            expected_policy_fingerprint=POLICY_SHA,
        )
    altered = copy.deepcopy(profile)
    altered["anchors"]["forward"]["endpoints"][0][0] += .001
    changed_path = tmp_path / "changed.json"
    changed_path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="TRANSFER_PROFILE_BINDING_INVALID"):
        load_held_cup_transfer_profile(
            changed_path, expected_model_sha256=MODEL_SHA,
            expected_policy_fingerprint=POLICY_SHA,
        )


def test_transfer_refuses_unmeasured_held_pose():
    profile = loaded()
    held = list(profile["anchors"]["default"]["held_q_rad"])
    held[2] += .002
    with pytest.raises(ValueError, match="TRANSFER_HELD_POSE_MISMATCH"):
        build_held_cup_transfer_segments(profile, "default", held_q_rad=held)
