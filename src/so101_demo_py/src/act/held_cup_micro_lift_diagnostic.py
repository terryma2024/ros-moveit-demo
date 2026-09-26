"""One isolated calibration authority for source-bound held-cup motion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.act.contracts import finite, validate_action_prefix
from so101_demo.act.held_cup_micro_lift_candidate import (
    require_lift_candidate_manifest, require_lift_candidate_sources,
)
from so101_demo.adapters.act.task8_contact_pairs import Task8ContactPairs


_CANDIDATE_KIND = "ACT_HELD_CUP_MICRO_LIFT_CANDIDATE"
_DIAGNOSTIC_KIND = "ACT_HELD_CUP_MICRO_LIFT_DIAGNOSTIC"
_EXTRA_KEYS = frozenset({
    "formal_episode_eligible", "held_contact_limits",
    "source_candidate_manifest_sha256", "source_submit_lead_s",
    "first_target_delay_s",
})


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _candidate_from_diagnostic(value: dict) -> dict:
    candidate = {key: item for key, item in value.items() if key not in _EXTRA_KEYS}
    candidate["submit_lead_s"] = value["source_submit_lead_s"]
    if value["anchor"] != "default":
        candidate["first_target_delay_s"] = value["first_target_delay_s"]
    candidate["kind"] = _CANDIDATE_KIND
    candidate["command_authority"] = False
    candidate["manifest_sha256"] = value["source_candidate_manifest_sha256"]
    return candidate


def build_held_cup_diagnostic_manifest(
    candidate_manifest: dict, *, pairs_factory=Task8ContactPairs,
) -> dict:
    """Promote only the exact candidate to a noncollecting diagnostic role."""
    require_lift_candidate_sources(candidate_manifest, pairs_factory=pairs_factory)
    if candidate_manifest["submit_lead_s"] != .05:
        raise ValueError("HELD_CUP_SOURCE_SUBMIT_LEAD_INVALID")
    proposal = json.loads(Path(candidate_manifest["proposal_path"]).read_bytes())
    try:
        thresholds = proposal["payload"]["thresholds"]
        minimum = finite(thresholds["minimum_bilateral_force_n"])
        compression = finite(thresholds["maximum_compression_distance_m"])
        force = finite(thresholds["maximum_safe_force_n"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("HELD_CUP_POLICY_THRESHOLDS_INVALID") from error
    if not 0 < minimum < force or not 0 < compression:
        raise ValueError("HELD_CUP_POLICY_THRESHOLDS_INVALID")
    result = dict(candidate_manifest)
    result.update(
        kind=_DIAGNOSTIC_KIND,
        command_authority="ISOLATED_CALIBRATION",
        formal_episode_eligible=False,
        held_contact_limits={
            "minimum_bilateral_force_n": minimum,
            "maximum_compression_distance_m": compression,
        },
        source_candidate_manifest_sha256=candidate_manifest["manifest_sha256"],
        source_submit_lead_s=candidate_manifest["submit_lead_s"],
        submit_lead_s=.1,
        first_target_delay_s=.1,
    )
    del result["manifest_sha256"]
    result["manifest_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    require_held_cup_diagnostic_manifest(result)
    return result


def require_held_cup_diagnostic_manifest(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("HELD_CUP_DIAGNOSTIC_MANIFEST_INVALID")
    if (value.get("kind") != _DIAGNOSTIC_KIND
            or value.get("command_authority") != "ISOLATED_CALIBRATION"
            or value.get("eligible_for_collection") is not False
            or value.get("formal_episode_eligible") is not False
            or value.get("source_submit_lead_s") != .05
            or value.get("submit_lead_s") != .1
            or value.get("first_target_delay_s") != .1
            or not isinstance(value.get("held_contact_limits"), dict)
            or set(value["held_contact_limits"]) != {
                "minimum_bilateral_force_n", "maximum_compression_distance_m"}
            or not isinstance(value.get("source_candidate_manifest_sha256"), str)
            or not isinstance(value.get("manifest_sha256"), str)):
        raise ValueError("HELD_CUP_DIAGNOSTIC_ROLE_INVALID")
    candidate = _candidate_from_diagnostic(value)
    require_lift_candidate_manifest(candidate)
    minimum = finite(value["held_contact_limits"]["minimum_bilateral_force_n"])
    compression = finite(value["held_contact_limits"]["maximum_compression_distance_m"])
    force = finite(value["diagnostic_limits"]["maximum_force_n"])
    if (set(value) != set(candidate) | _EXTRA_KEYS
            or not 0 < minimum < force or not 0 < compression
            or value["source_candidate_manifest_sha256"] != candidate["manifest_sha256"]
            or value["manifest_sha256"] != hashlib.sha256(_canonical(
                {key: item for key, item in value.items()
                 if key != "manifest_sha256"})).hexdigest()):
        raise ValueError("HELD_CUP_DIAGNOSTIC_CONTENT_INVALID")
    return value


def require_held_cup_diagnostic_sources(
    value: dict, *, pairs_factory=Task8ContactPairs,
) -> dict:
    require_held_cup_diagnostic_manifest(value)
    rebuilt = build_held_cup_diagnostic_manifest(
        _candidate_from_diagnostic(value), pairs_factory=pairs_factory)
    if _canonical(rebuilt) != _canonical(value):
        raise ValueError("HELD_CUP_DIAGNOSTIC_SOURCE_REPLAY_MISMATCH")
    return value


def held_cup_diagnostic_prefix_matches(prefix: object, manifest: dict) -> bool:
    try:
        require_held_cup_diagnostic_manifest(manifest)
        checked = validate_action_prefix(prefix)
        sequence = checked["sequence"]
        if (type(sequence) is not int
                or not 0 <= sequence < len(manifest["segment_phases"])):
            return False
        start = sequence * 9
        prior = (manifest["joint_start_rad"] if start == 0
                 else manifest["target_positions"][start - 1])
        expected = [prior] + manifest["target_positions"][start:start + 9]
        return (checked["session_id"] == manifest["session_id"]
                and checked["attempt_id"] == manifest["attempt_id"]
                and checked.get("first_target_delay_s") ==
                    manifest["first_target_delay_s"]
                and len(checked["positions"]) == len(expected)
                and all(all(abs(a - b) <= 1e-10
                            for a, b in zip(row, frozen, strict=True))
                        for row, frozen in zip(checked["positions"], expected, strict=True)))
    except (KeyError, TypeError, ValueError):
        return False
