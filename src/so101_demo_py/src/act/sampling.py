"""Freeze independently checked ACT candidates before any collection dispatch.

The candidate port is the physical MoveIt/MuJoCo reachability boundary. This
module only accepts its closed gate result; a production manifest cannot be
generated from positions or caller-supplied booleans alone.
"""

from __future__ import annotations

import hashlib
import json
import math

from .contracts import finite, integer, sha256, validate_scenario, vector


SPLITS = ("train", "validation", "offline_test", "rollout_validation", "rollout_test")
COLLECTION_SPLITS = SPLITS[:3]
REACHABILITY_GATES = frozenset({
    "table_clear", "collision_free", "pregrasp_ik", "grasp_ik", "lift_ik",
    "place_ik", "retreat_ik", "pregrasp_plan", "grasp_plan", "lift_plan",
    "place_plan", "retreat_plan", "head_visible", "wrist_visible",
})
_CANDIDATE_KEYS = frozenset({"xy", "arm_q", "search_start_rad", "seed"})
_CONFIG_KEYS = frozenset({
    "schema_version", "config_sha256", "minimum_gap_m", "candidates", "candidate_port",
})
_MANIFEST_KEYS = frozenset({
    "schema_version", "status", "seed", "config_sha256", "minimum_gap_m",
    "scenarios", "verification", "non_collection_ids", "manifest_sha256",
})


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def assert_separated(a: list[tuple], b: list[tuple], gap_m: float) -> None:
    gap = finite(gap_m, nonnegative=True)
    first = [vector(point, 2) for point in a]
    second = [vector(point, 2) for point in b]
    if any(math.dist(left, right) < gap - 1e-12 for left in first for right in second):
        raise ValueError("SPLIT_DISTANCE_VIOLATION")


def make_manifest(config: dict, seed: int) -> dict:
    """Freeze candidates only after a physical port checks every actual point."""
    integer(seed)
    if not isinstance(config, dict) or set(config) != _CONFIG_KEYS or config["schema_version"] != 1:
        raise ValueError("SAMPLING_CONFIG_INVALID")
    config_sha = sha256(config["config_sha256"])
    gap = finite(config["minimum_gap_m"], nonnegative=True)
    if gap <= 0:
        raise ValueError("SPLIT_GAP_INVALID")
    entries = config["candidates"]
    if not isinstance(entries, dict) or set(entries) != set(SPLITS):
        raise ValueError("SPLIT_CANDIDATES_INVALID")
    verifier = getattr(config["candidate_port"], "verify", None)
    if not callable(verifier):
        raise ValueError("CANDIDATE_PORT_REQUIRED")
    scenarios = []
    proofs = []
    positions: dict[str, list[tuple]] = {name: [] for name in SPLITS}
    seen_seeds = set()
    seen_ids = set()
    for split in SPLITS:
        candidates = entries[split]
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("SPLIT_CANDIDATES_INVALID")
        for raw in candidates:
            if not isinstance(raw, dict) or set(raw) != _CANDIDATE_KEYS:
                raise ValueError("CANDIDATE_SCHEMA_INVALID")
            candidate = {
                "xy": vector(raw["xy"], 2), "arm_q": vector(raw["arm_q"], 6),
                "search_start_rad": finite(raw["search_start_rad"]),
                "seed": integer(raw["seed"]),
            }
            if candidate["seed"] in seen_seeds:
                raise ValueError("CANDIDATE_DUPLICATE_SEED")
            seen_seeds.add(candidate["seed"])
            identity = {"split": split, "candidate": candidate,
                        "config_sha256": config_sha, "manifest_seed": seed}
            scene_id = "act-" + _digest(identity)[:24]
            if scene_id in seen_ids:
                raise ValueError("CANDIDATE_DUPLICATE_ID")
            seen_ids.add(scene_id)
            # Verify the actual sampled point. A cell-center certificate cannot
            # stand in for a different point within that cell.
            gates = verifier(dict(candidate))
            if not isinstance(gates, dict) or set(gates) != REACHABILITY_GATES or any(
                gates[name] is not True for name in REACHABILITY_GATES
            ):
                raise ValueError("CANDIDATE_REACHABILITY_FAILED")
            row = validate_scenario({
                "scene_id": scene_id, "split": split, "xy": candidate["xy"],
                "arm_q": candidate["arm_q"], "search_start_rad": candidate["search_start_rad"],
                "seed": candidate["seed"], "config_sha256": config_sha,
            })
            scenarios.append(row)
            proofs.append({"scene_id": scene_id, "gates": gates})
            positions[split].append(row["xy"])
    for index, left in enumerate(SPLITS):
        for right in SPLITS[index + 1:]:
            assert_separated(positions[left], positions[right], gap)
    document = {
        "schema_version": 1, "status": "CANDIDATES_VERIFIED", "seed": seed,
        "config_sha256": config_sha, "minimum_gap_m": gap,
        "scenarios": scenarios, "verification": proofs,
        "non_collection_ids": [row["scene_id"] for row in scenarios
                               if row["split"] not in COLLECTION_SPLITS],
    }
    document["manifest_sha256"] = _digest(document)
    return document


def project_collection_manifest(split_manifest: dict) -> dict:
    """Project only expert-eligible splits from an intact frozen five-way list."""
    source = split_manifest
    if not isinstance(source, dict) or set(source) != _MANIFEST_KEYS:
        raise ValueError("SPLIT_MANIFEST_SCHEMA_INVALID")
    expected = _digest({key: value for key, value in source.items() if key != "manifest_sha256"})
    if source["manifest_sha256"] != expected:
        raise ValueError("SPLIT_MANIFEST_HASH_INVALID")
    if source["schema_version"] != 1 or source["status"] != "CANDIDATES_VERIFIED":
        raise ValueError("SPLIT_MANIFEST_STATUS_INVALID")
    rows = source["scenarios"]
    proofs = source["verification"]
    if (not isinstance(rows, list) or not isinstance(proofs, list) or len(rows) != len(proofs)):
        raise ValueError("SPLIT_MANIFEST_SCHEMA_INVALID")
    seen = set()
    for row, proof in zip(rows, proofs, strict=True):
        validate_scenario(row)
        if (row["scene_id"] in seen or not isinstance(proof, dict)
                or set(proof) != {"scene_id", "gates"}
                or proof["scene_id"] != row["scene_id"]
                or not isinstance(proof["gates"], dict)
                or set(proof["gates"]) != REACHABILITY_GATES
                or any(value is not True for value in proof["gates"].values())):
            raise ValueError("SPLIT_MANIFEST_PROOF_INVALID")
        seen.add(row["scene_id"])
    excluded = [row["scene_id"] for row in rows if row["split"] not in COLLECTION_SPLITS]
    if source["non_collection_ids"] != excluded:
        raise ValueError("SPLIT_MANIFEST_ELIGIBILITY_INVALID")
    document = {
        "schema_version": 1,
        "source_manifest_sha256": hashlib.sha256(_canonical(source)).hexdigest(),
        "scenarios": [row for row in rows if row["split"] in COLLECTION_SPLITS],
        "excluded_scene_ids": excluded,
    }
    document["collection_sha256"] = _digest(document)
    return document
