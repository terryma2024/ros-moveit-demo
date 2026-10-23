"""The frozen anchor's neck start follows the rig: a rig with a neck pins it (0.1 rad), a rig without one has none."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from paths import REPOSITORY

from so101_demo.act.diagnostic_episode_inputs import (
    ANCHOR_FILE,
    anchor_identity_from_bytes,
    freeze_inputs,
    read_inputs_manifest,
)
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG, dump_rig_profile

import test_act_diagnostic_episode_scope as scope

NO_NECK_ANCHOR = (b"schema_version: 1\nanchors:\n  default:\n    cup_start_m: [0.02, -0.28, 0.165]\n")
ODD_NECK_ANCHOR = scope.ANCHOR_YAML.replace(b"neck_start_rad: 0.1", b"neck_start_rad: 0.7")


def test_the_head_wrist_identity_is_what_it_always_was():
    identity = anchor_identity_from_bytes(scope.ANCHOR_YAML)
    assert identity == anchor_identity_from_bytes(scope.ANCHOR_YAML, HEAD_WRIST_RIG)
    assert identity == anchor_identity_from_bytes(scope.ANCHOR_YAML, "head-wrist")
    assert identity == scope._derived_anchor_identity(scope.ANCHOR_YAML)
    assert identity["neck_start_rad"] == 0.1


@pytest.mark.parametrize("payload", [NO_NECK_ANCHOR, ODD_NECK_ANCHOR])
def test_a_rig_with_a_neck_still_requires_the_pinned_neck_start(payload):
    for rig in (None, HEAD_WRIST_RIG, "head-wrist"):
        with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
            anchor_identity_from_bytes(payload, rig)


@pytest.mark.parametrize("payload", [scope.ANCHOR_YAML, NO_NECK_ANCHOR, ODD_NECK_ANCHOR])
def test_a_rig_without_a_neck_has_no_neck_start_whatever_the_file_says(payload):
    for rig in (SIDE_WRIST_RIG, "side-wrist"):
        identity = anchor_identity_from_bytes(payload, rig)
        assert "neck_start_rad" not in identity
        assert identity == {"scene_id": "default", "seed": 0, "cup_start_m": [0.02, -0.28, 0.165],
                            "anchor_file_sha256": hashlib.sha256(payload).hexdigest()}


def test_the_cup_start_is_still_pinned_for_a_rig_without_a_neck():
    moved = NO_NECK_ANCHOR.replace(b"0.02", b"0.03")
    with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
        anchor_identity_from_bytes(moved, SIDE_WRIST_RIG)


def test_the_production_anchor_file_serves_both_rigs_with_the_same_digest():
    payload = (REPOSITORY / ANCHOR_FILE).read_bytes()
    head = anchor_identity_from_bytes(payload, HEAD_WRIST_RIG)
    side = anchor_identity_from_bytes(payload, SIDE_WRIST_RIG)
    assert head["anchor_file_sha256"] == side["anchor_file_sha256"]
    assert head["neck_start_rad"] == 0.1 and "neck_start_rad" not in side


def test_a_side_wrist_freeze_binds_an_anchor_without_a_neck_start(tmp_path):
    registry = scope._registry(tmp_path)
    entry = registry["roles"]["anchor_scene"]["selected"]
    Path(entry["path"]).write_bytes(NO_NECK_ANCHOR)
    entry["sha256"] = hashlib.sha256(NO_NECK_ANCHOR).hexdigest()
    registry["roles"]["anchor_scene"]["candidates"] = [dict(entry)]
    registry["roles"]["anchor_scene"]["identity"] = anchor_identity_from_bytes(NO_NECK_ANCHOR, SIDE_WRIST_RIG)
    candidates = scope._write_registry(tmp_path, registry)
    rig = dump_rig_profile(SIDE_WRIST_RIG)
    manifest = read_inputs_manifest(freeze_inputs(candidates, tmp_path / "inputs", rig_profile=rig))
    assert "neck_start_rad" not in manifest["roles"]["anchor_scene"]["identity"]
    assert manifest["rig_profile"]["values"]["rig"] == "side-wrist"
    # the same registry under the head+wrist rig (or no rig) is an anchor the bytes do not describe
    for kwargs in ({}, {"rig_profile": dump_rig_profile(HEAD_WRIST_RIG)}):
        with pytest.raises(ValueError, match="NONHEAD_INPUT_BINDING_REQUIRED"):
            freeze_inputs(candidates, tmp_path / ("refused-" + str(len(kwargs))), **kwargs)


def test_a_head_wrist_freeze_of_the_same_anchor_keeps_its_neck_start(tmp_path):
    registry = scope._registry(tmp_path)
    candidates = scope._write_registry(tmp_path, registry)
    manifest = read_inputs_manifest(freeze_inputs(
        candidates, tmp_path / "inputs", rig_profile=dump_rig_profile(HEAD_WRIST_RIG)))
    assert manifest["roles"]["anchor_scene"]["identity"]["neck_start_rad"] == 0.1
