"""The contact transition stays exact, source pinned and noncollecting."""

from act_identity import ACT_MODEL_SHA256
import hashlib
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from so101_demo.act.grasp_contact_transition_diagnostic import (
    build_transition_manifest, build_transition_segments,
    prefix_matches_transition, require_transition_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
ROUTE_PROFILE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
PROFILE = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"


def manifest(tmp_path):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21}}}))
    receipt.write_text("{}")

    class Pairs:
        model_sha256 = ACT_MODEL_SHA256
        fingerprint = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"

        def __init__(self, **kwargs):
            pass

        def for_phase(self, phase):
            assert phase == "CLOSE"
            return {("fixed_fingertip_pad_collision_006", "wall_near_collision")}

    value = build_transition_manifest(
        scene_path=SCENE, route_profile_path=ROUTE_PROFILE,
        profile_path=PROFILE, plugin_path=PLUGIN, proposal_path=proposal,
        receipt_path=receipt, session_id="contact-transition-test",
        attempt_id="contact-transition-attempt", pairs_factory=Pairs)
    return value, Pairs


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


def test_transition_manifest_replays_sources_and_rejects_phase_or_row_tamper(tmp_path):
    value, pairs = manifest(tmp_path)
    require_transition_sources(value, pairs_factory=pairs)
    assert value["eligible_for_collection"] is False
    assert value["segment_phases"] == ["APPROACH"] + ["CONTACT"] * 33
    assert value["allowed_contact_pairs_by_phase"]["APPROACH"] == []
    first = dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                 sequence=0, observation_time_s=1.,
                 target_times_s=[1. + .1 * index for index in range(1, 11)],
                 positions=[value["joint_start_rad"]] + value["target_positions"][:9])
    assert prefix_matches_transition(first, value)
    assert not prefix_matches_transition(dict(first, sequence=1), value)
    for key, changed in (("segment_phases", ["CONTACT"] * 34),
                         ("target_positions", [[0.] * 6] + value["target_positions"][1:]),
                         ("eligible_for_collection", True)):
        bad = dict(value, **{key: changed})
        with pytest.raises(ValueError):
            require_transition_sources(bad, pairs_factory=pairs)


