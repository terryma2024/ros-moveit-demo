"""Closed source replay for left and forward Task 6 contact diagnostics."""

from act_identity import ACT_MODEL_SHA256
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from so101_demo.act.alternate_anchor_grasp_contact_diagnostic import (
    alt_prefix_matches,
    build_alt_manifest,
    require_alt_sources,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
ANCHORS = PACKAGE / "config/act/task8-live-anchors.yaml"
PROFILE = PACKAGE / "config/mujoco/act/task6_alt_full_contact_v1.json"


class Pairs:
    model_sha256 = ACT_MODEL_SHA256
    fingerprint = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"

    def __init__(self, **kwargs):
        pass

    def for_phase(self, phase):
        assert phase == "CLOSE"
        return {("fixed_fingertip_pad_collision_006", "wall_near_collision")}


def manifest(tmp_path, anchor):
    proposal = tmp_path / "proposal.json"
    receipt = tmp_path / "receipt.json"
    proposal.write_text(json.dumps({"payload": {"thresholds": {
        "maximum_safe_force_n": 3.21}}}))
    receipt.write_text("{}")
    return build_alt_manifest(
        scene_path=SCENE, plugin_path=PLUGIN, anchors_path=ANCHORS,
        profile_path=PROFILE, proposal_path=proposal, receipt_path=receipt,
        anchor=anchor, session_id="alt-full-test", attempt_id="alt-full-attempt",
        pairs_factory=Pairs)


def prefix(value, sequence):
    width = value["segment_rows"]
    start = sequence * width
    prior = value["joint_start_rad"] if sequence == 0 else value["target_positions"][start - 1]
    return dict(session_id=value["session_id"], attempt_id=value["attempt_id"],
                sequence=sequence, observation_time_s=1.,
                first_target_delay_s=value["first_target_delay_s"],
                target_times_s=[1. + value["first_target_delay_s"] + .1 * index
                                for index in range(1, 11)],
                positions=[prior] + value["target_positions"][start:start + width])


@pytest.mark.parametrize("anchor,total,contact_start,segment_sha", [
    ("left", 168, 135, "4635154f83833542053d24d899f90b890a39fc49a019f81fde9a0fd351781901"),
    ("forward", 235, 198, "5c8128668043cb5b80d47d0fb869d1a2d9c61206b572120c2b50ef4a51d0dae1"),
])
def test_alt_manifest_replays_exact_measured_phases(tmp_path, anchor, total, contact_start, segment_sha):
    value = manifest(tmp_path, anchor)
    require_alt_sources(value, pairs_factory=Pairs)
    assert value["kind"] == "ACT_TASK6_ALT_FULL_CONTACT_DIAGNOSTIC"
    assert value["eligible_for_collection"] is False
    assert value["anchor"] == anchor
    assert len(value["segment_phases"]) == total
    assert value["contact_phase_start"] == contact_start
    assert value["candidate_segments_sha256"] == segment_sha
    assert value["first_target_delay_s"] == .1
    assert value["segment_phases"] == ["APPROACH"] * contact_start + ["CONTACT"] * (total - contact_start)
    for sequence in (0, contact_start - 1, contact_start, total - 1):
        assert alt_prefix_matches(prefix(value, sequence), value)
    assert not alt_prefix_matches(dict(prefix(value, total - 1), sequence=total - 2), value)
    assert not alt_prefix_matches({k: v for k, v in prefix(value, 0).items()
                                   if k != "first_target_delay_s"}, value)


def test_alt_manifest_rejects_tampered_role_phase_and_rows(tmp_path):
    value = manifest(tmp_path, "left")
    for changed in (
        dict(value, eligible_for_collection=True),
        dict(value, anchor="forward"),
        dict(value, segment_phases=["APPROACH"] * len(value["segment_phases"])),
        dict(value, target_positions=[[0.] * 6] + value["target_positions"][1:]),
        dict(value, candidate_segments_sha256="0" * 64),
        dict(value, first_target_delay_s=0.),
    ):
        with pytest.raises(ValueError):
            require_alt_sources(changed, pairs_factory=Pairs)


