"""Source-only admission for the measured ACT broker-grid lift rows."""

import copy
import json
from pathlib import Path

import pytest

from so101_demo.act.task6_full_contact_diagnostic import build_full_manifest
from so101_demo.act.task6_alt_full_contact_diagnostic import build_alt_manifest
from so101_demo.act.held_cup_micro_lift_candidate import (
    build_lift_candidate_manifest, lift_prefix_matches, require_lift_candidate_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
ROUTE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
CONTACT = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"
ANCHORS = PACKAGE / "config/act/task8-live-anchors.yaml"
ALT = PACKAGE / "config/mujoco/act/task6_alt_full_contact_v1.json"
LIFT = PACKAGE / "config/mujoco/act/held_cup_micro_lift_candidates_v1.json"


class Pairs:
    model_sha256 = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
    fingerprint = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"

    def __init__(self, **kwargs):
        pass

    def for_phase(self, phase):
        assert phase in ("CLOSE", "MICRO_LIFT")
        return {("fixed_fingertip_pad_collision_006", "wall_near_collision")}


def source(tmp_path, anchor):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21}}}))
    receipt.write_text("{}")
    common = dict(scene_path=SCENE, plugin_path=PLUGIN, proposal_path=proposal,
                  receipt_path=receipt, session_id="lift-test", attempt_id="lift-attempt",
                  pairs_factory=Pairs)
    if anchor == "default":
        base = build_full_manifest(route_profile_path=ROUTE, profile_path=CONTACT, **common)
    else:
        base = build_alt_manifest(anchors_path=ANCHORS, profile_path=ALT,
                                  anchor=anchor, **common)
    return build_lift_candidate_manifest(base, profile_path=LIFT, pairs_factory=Pairs)


def prefix(value, sequence):
    start = sequence * 9
    before = value["joint_start_rad"] if start == 0 else value["target_positions"][start - 1]
    result = dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                  sequence=sequence, observation_time_s=1.,
                  target_times_s=[1. + value.get("first_target_delay_s", 0.)
                                  + .1 * index for index in range(1, 11)],
                  positions=[before] + value["target_positions"][start:start + 9])
    if "first_target_delay_s" in value:
        result["first_target_delay_s"] = value["first_target_delay_s"]
    return result


@pytest.mark.parametrize("anchor,base_count", [
    ("default", 281), ("left", 168), ("forward", 235),
])
def test_candidate_is_exact_closed_noncollecting_source(tmp_path, anchor, base_count):
    value = source(tmp_path, anchor)
    require_lift_candidate_sources(value, pairs_factory=Pairs)
    assert value["kind"] == "ACT_HELD_CUP_MICRO_LIFT_CANDIDATE"
    assert value["anchor"] == anchor
    assert value["eligible_for_collection"] is False
    assert value["command_authority"] is False
    assert value["lift_phase_start"] == base_count
    assert len(value["segment_phases"]) == base_count + 1
    assert value["segment_phases"][-1] == "LIFT"
    assert set(value["allowed_contact_pairs_by_phase"]) == {"APPROACH", "CONTACT", "LIFT"}
    assert lift_prefix_matches(prefix(value, base_count), value)
    assert not lift_prefix_matches(dict(prefix(value, base_count), sequence=0), value)


def test_candidate_rejects_modified_source_and_rows(tmp_path):
    value = source(tmp_path, "default")
    for key, changed in (
        ("eligible_for_collection", True),
        ("command_authority", True),
        ("anchor", "left"),
        ("policy_fingerprint", "0" * 64),
        ("lift_profile_sha256", "0" * 64),
        ("segment_phases", value["segment_phases"][:-1] + ["CONTACT"]),
        ("target_positions", value["target_positions"][:-1] + [[0.] * 6]),
    ):
        forged = copy.deepcopy(value)
        forged[key] = changed
        with pytest.raises(ValueError):
            require_lift_candidate_sources(forged, pairs_factory=Pairs)
    tampered = copy.deepcopy(value)
    tampered["target_positions"][-1][0] += 1e-6
    assert not lift_prefix_matches(prefix(tampered, len(tampered["segment_phases"]) - 1), value)
