"""Frozen ACT candidate identities and collection projection."""

import hashlib
import json

import pytest

from so101_demo.act.sampling import assert_separated, make_manifest, project_collection_manifest


SPLITS = ("train", "validation", "offline_test", "rollout_validation", "rollout_test")


def candidate(x, seed):
    return {"xy": [x, 0.0], "arm_q": [0.0] * 6, "search_start_rad": 0.1,
            "seed": seed}


class Checked:
    def __init__(self, rejected=()):
        self.rejected = set(rejected)
        self.calls = []

    def verify(self, item):
        self.calls.append(item["seed"])
        return {name: item["seed"] not in self.rejected for name in (
            "table_clear", "collision_free", "pregrasp_ik", "grasp_ik", "lift_ik",
            "place_ik", "retreat_ik", "pregrasp_plan", "grasp_plan", "lift_plan",
            "place_plan", "retreat_plan", "head_visible", "wrist_visible")}


def config(port, *, swap=False):
    entries = {split: [candidate(index * 0.1, index + 1)]
               for index, split in enumerate(SPLITS)}
    if swap:
        entries["train"] = list(reversed(entries["train"]))
    return {"schema_version": 1, "config_sha256": "a" * 64,
            "minimum_gap_m": 0.02, "candidates": entries,
            "candidate_port": port}


def test_labels_do_not_hide_near_duplicate_positions():
    with pytest.raises(ValueError, match="SPLIT_DISTANCE_VIOLATION"):
        assert_separated([(0., 0.)], [(.001, 0.)], .01)
    assert_separated([(0., 0.)], [(.01, 0.)], .01)


def test_manifest_freezes_verified_candidates_and_collection_projection():
    port = Checked()
    frozen = make_manifest(config(port), seed=42)
    assert port.calls == [1, 2, 3, 4, 5]
    assert frozen["status"] == "CANDIDATES_VERIFIED"
    assert len(frozen["scenarios"]) == 5
    assert len({row["scene_id"] for row in frozen["scenarios"]}) == 5
    assert frozen["non_collection_ids"] == [row["scene_id"] for row in frozen["scenarios"]
                                            if row["split"].startswith("rollout_")]
    projected = project_collection_manifest(frozen)
    assert [row["split"] for row in projected["scenarios"]] == list(SPLITS[:3])
    assert projected["source_manifest_sha256"] == hashlib.sha256(
        json.dumps(frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert make_manifest(config(Checked()), seed=42) == frozen


def test_rejection_or_missing_verifier_does_not_freeze_success_claim():
    with pytest.raises(ValueError, match="CANDIDATE_PORT_REQUIRED"):
        make_manifest({**config(Checked()), "candidate_port": None}, seed=42)
    with pytest.raises(ValueError, match="CANDIDATE_REACHABILITY_FAILED"):
        make_manifest(config(Checked({3})), seed=42)


def test_cross_split_gap_and_seed_reuse_are_refused():
    near = config(Checked())
    near["candidates"]["validation"][0]["xy"] = [0.01, 0.0]
    with pytest.raises(ValueError, match="SPLIT_DISTANCE_VIOLATION"):
        make_manifest(near, seed=42)
    repeated = config(Checked())
    repeated["candidates"]["validation"][0]["seed"] = 1
    with pytest.raises(ValueError, match="CANDIDATE_DUPLICATE_SEED"):
        make_manifest(repeated, seed=42)


def test_collection_projection_rejects_tampered_source_and_rollout():
    frozen = make_manifest(config(Checked()), seed=42)
    frozen["scenarios"][0]["xy"] = [99.0, 0.0]
    with pytest.raises(ValueError, match="SPLIT_MANIFEST_HASH_INVALID"):
        project_collection_manifest(frozen)
