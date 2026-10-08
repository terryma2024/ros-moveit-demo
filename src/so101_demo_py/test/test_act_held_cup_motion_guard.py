"""The sole motion guard must prove holding before an isolated lift goal."""

from act_identity import ACT_MODEL_SHA256
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import mujoco
import pytest

from so101_demo.act.task6_full_contact_diagnostic import build_full_manifest
from so101_demo.act.held_cup_micro_lift_candidate import build_lift_candidate_manifest
from so101_demo.act.held_cup_micro_lift_diagnostic import (
    build_held_cup_diagnostic_manifest, require_held_cup_diagnostic_sources,
)
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.act.ownership import Ownership


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
ROUTE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
CONTACT = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"
LIFT = PACKAGE / "config/mujoco/act/held_cup_micro_lift_candidates_v1.json"


class Pairs:
    model_sha256 = ACT_MODEL_SHA256
    fingerprint = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"

    def __init__(self, **kwargs):
        pass

    def for_phase(self, phase):
        assert phase in ("CLOSE", "MICRO_LIFT")
        return {("fixed_fingertip_pad_collision_006", "wall_near_collision")}


def manifest(tmp_path):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21, "minimum_bilateral_force_n": .1,
        "maximum_compression_distance_m": .0001}}}))
    receipt.write_text("{}")
    base = build_full_manifest(scene_path=SCENE, plugin_path=PLUGIN,
        route_profile_path=ROUTE, profile_path=CONTACT,
        proposal_path=proposal, receipt_path=receipt,
        session_id="held-guard", attempt_id="held-guard-attempt", pairs_factory=Pairs)
    candidate = build_lift_candidate_manifest(base, profile_path=LIFT,
                                               pairs_factory=Pairs)
    return build_held_cup_diagnostic_manifest(candidate, pairs_factory=Pairs)


def prefix(value, sequence):
    start = sequence * 9
    prior = value["joint_start_rad"] if start == 0 else value["target_positions"][start - 1]
    delay = value["first_target_delay_s"]
    return dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                sequence=sequence, observation_time_s=1.,
                first_target_delay_s=delay,
                target_times_s=[1. + delay + .1 * index for index in range(1, 11)],
                positions=[prior] + value["target_positions"][start:start + 9])


