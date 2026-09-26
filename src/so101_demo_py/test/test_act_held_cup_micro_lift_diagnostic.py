"""Only a separate source-replayed calibration manifest may use held-cup rows."""

import copy
import json
from pathlib import Path

import pytest

from so101_demo.act.task6_full_contact_diagnostic import build_full_manifest
from so101_demo.act.task6_alt_full_contact_diagnostic import build_alt_manifest
from so101_demo.act.held_cup_micro_lift_candidate import build_lift_candidate_manifest
from so101_demo.act.held_cup_micro_lift_diagnostic import (
    build_held_cup_diagnostic_manifest, held_cup_diagnostic_prefix_matches,
    require_held_cup_diagnostic_sources,
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


def diagnostic(tmp_path, anchor):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21,
        "minimum_bilateral_force_n": .1,
        "maximum_compression_distance_m": .0001}}}))
    receipt.write_text("{}")
    common = dict(scene_path=SCENE, plugin_path=PLUGIN, proposal_path=proposal,
                  receipt_path=receipt, session_id="held-diagnostic",
                  attempt_id="held-attempt", pairs_factory=Pairs)
    if anchor == "default":
        base = build_full_manifest(route_profile_path=ROUTE, profile_path=CONTACT, **common)
    else:
        base = build_alt_manifest(anchors_path=ANCHORS, profile_path=ALT,
                                  anchor=anchor, **common)
    candidate = build_lift_candidate_manifest(base, profile_path=LIFT, pairs_factory=Pairs)
    return build_held_cup_diagnostic_manifest(candidate, pairs_factory=Pairs)


def prefix(value, sequence):
    start = sequence * 9
    prior = value["joint_start_rad"] if start == 0 else value["target_positions"][start - 1]
    delay = value.get("first_target_delay_s", 0.)
    result = dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                  sequence=sequence, observation_time_s=1.,
                  target_times_s=[1. + delay + .1 * part for part in range(1, 11)],
                  positions=[prior] + value["target_positions"][start:start + 9])
    if "first_target_delay_s" in value:
        result["first_target_delay_s"] = delay
    return result


@pytest.mark.parametrize("anchor,last,contact", [
    ("default", 281, 248), ("left", 168, 135), ("forward", 235, 198),
])
def test_diagnostic_binds_every_phase_and_activated_limits(tmp_path, anchor, last, contact):
    value = diagnostic(tmp_path, anchor)
    require_held_cup_diagnostic_sources(value, pairs_factory=Pairs)
    assert value["kind"] == "ACT_HELD_CUP_MICRO_LIFT_DIAGNOSTIC"
    assert value["command_authority"] == "ISOLATED_CALIBRATION"
    assert value["eligible_for_collection"] is False
    assert value["formal_episode_eligible"] is False
    assert value["held_contact_limits"] == {
        "minimum_bilateral_force_n": .1,
        "maximum_compression_distance_m": .0001}
    assert value["segment_phases"][last] == "LIFT"
    for sequence in (0, contact - 1, contact, last - 1, last):
        assert held_cup_diagnostic_prefix_matches(prefix(value, sequence), value)
    assert not held_cup_diagnostic_prefix_matches(
        dict(prefix(value, last), sequence=last - 1), value)


def test_diagnostic_rejects_authority_policy_rows_and_threshold_tamper(tmp_path):
    value = diagnostic(tmp_path, "default")
    changes = (
        ("eligible_for_collection", True),
        ("command_authority", "FORMAL"),
        ("formal_episode_eligible", True),
        ("source_candidate_manifest_sha256", "0" * 64),
        ("policy_fingerprint", "0" * 64),
        ("anchor", "left"),
        ("segment_phases", value["segment_phases"][:-1] + ["CONTACT"]),
        ("target_positions", value["target_positions"][:-1] + [[0.] * 6]),
        ("held_contact_limits", dict(value["held_contact_limits"],
                                      minimum_bilateral_force_n=0.)),
    )
    for key, changed in changes:
        forged = copy.deepcopy(value)
        forged[key] = changed
        with pytest.raises(ValueError):
            require_held_cup_diagnostic_sources(forged, pairs_factory=Pairs)
