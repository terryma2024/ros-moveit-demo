"""The contact transition stays exact, source pinned and noncollecting."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.task6_contact_transition import build_transition_segments


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
ROUTE_PROFILE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
PROFILE = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"


def segments(profile=PROFILE):
    return build_transition_segments(
        scene_path=SCENE, route_profile_path=ROUTE_PROFILE, profile_path=profile)


def test_transition_is_exact_phased_noncollecting_candidate():
    value = segments()
    profile = json.loads(PROFILE.read_text())
    assert profile["eligible_for_collection"] is False
    assert len(value) == 34
    assert value[0][0] == "APPROACH"
    assert all(phase == "CONTACT" for phase, _ in value[1:])
    assert all(len(rows) == 9 for _, rows in value)
    assert value[0][1][0] == profile["joint_start_rad"]
    assert value[-1][1][-1][5] == profile["close_q6_rad"]
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    assert hashlib.sha256(raw).hexdigest() == (
        "0e1be85eca2716ea31101b3fdfdd73bb72e4133067c10c0c9799ec288edb98bd")


def test_transition_profile_drift_refuses_before_target(tmp_path):
    changed = tmp_path / "changed.json"
    content = json.loads(PROFILE.read_text())
    content["eligible_for_collection"] = True
    changed.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="drift"):
        segments(changed)
