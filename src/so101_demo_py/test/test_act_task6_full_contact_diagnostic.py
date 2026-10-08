"""The full Task 6 contact probe has one exact source-bound command path."""

from act_identity import ACT_MODEL_SHA256
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from so101_demo.act.approach_grasp_contact_diagnostic import (
    build_full_manifest, full_prefix_matches, require_full_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
ROUTE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
CONTACT = PACKAGE / "config/mujoco/act/task6_contact_transition_v1.json"


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

    result = build_full_manifest(
        scene_path=SCENE, plugin_path=PLUGIN, route_profile_path=ROUTE,
        profile_path=CONTACT, proposal_path=proposal, receipt_path=receipt,
        session_id="full-contact-test", attempt_id="full-contact-attempt",
        pairs_factory=Pairs)
    return result, Pairs


def prefix(value, sequence):
    width = value["segment_rows"]
    start = sequence * width
    prior = value["joint_start_rad"] if sequence == 0 else value["target_positions"][start - 1]
    return dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                sequence=sequence, observation_time_s=1.,
                target_times_s=[1. + .1 * index for index in range(1, 11)],
                positions=[prior] + value["target_positions"][start:start + width])


def test_full_manifest_preserves_route_bridge_and_exact_contact_phases(tmp_path):
    value, pairs = manifest(tmp_path)
    require_full_sources(value, pairs_factory=pairs)
    assert value["eligible_for_collection"] is False
    assert len(value["segment_phases"]) == 281
    assert value["segment_phases"] == ["APPROACH"] * 248 + ["CONTACT"] * 33
    assert value["route_segment_count"] == 246
    assert value["contact_phase_start"] == 248
    assert value["bridge_rows_sha256"] == (
        "172ee8fe80388093a56045e5eea030f474c7ecd854fc08dd1683a59321ab051a")
    for sequence in (0, 245, 246, 247, 248, 280):
        assert full_prefix_matches(prefix(value, sequence), value)
    assert not full_prefix_matches(dict(prefix(value, 248), sequence=247), value)


def test_full_manifest_refuses_phase_row_and_collection_tamper(tmp_path):
    value, pairs = manifest(tmp_path)
    for key, changed in (
        ("segment_phases", ["APPROACH"] * 281),
        ("target_positions", [[0.] * 6] + value["target_positions"][1:]),
        ("bridge_rows_sha256", "0" * 64),
        ("eligible_for_collection", True),
    ):
        with pytest.raises(ValueError):
            require_full_sources(dict(value, **{key: changed}), pairs_factory=pairs)


