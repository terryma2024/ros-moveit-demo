"""One closed noncollecting route through Task 6 approach and contact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.execution import bounded_positions
from so101_demo.act.task6_route_diagnostic import build_route_manifest
from so101_demo.act.task6_contact_transition import (
    _MANIFEST_KEYS, _PATH_LIMITS, _rows_between, build_transition_manifest,
)
from so101_demo.adapters.act.task8_contact_pairs import Task8ContactPairs


_BRIDGE_SHA = "172ee8fe80388093a56045e5eea030f474c7ecd854fc08dd1683a59321ab051a"
_FULL_KEYS = _MANIFEST_KEYS | {
    "route_segment_count", "contact_phase_start", "bridge_rows_sha256",
    "source_route_manifest_sha256", "source_contact_manifest_sha256",
}


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def build_full_manifest(
    *, scene_path: Path, plugin_path: Path, route_profile_path: Path,
    profile_path: Path, proposal_path: Path, receipt_path: Path,
    session_id: str, attempt_id: str, pairs_factory=Task8ContactPairs,
) -> dict:
    """Rebuild all rows and activated pairs from the two immutable source routes."""
    route = build_route_manifest(
        scene_path=scene_path, plugin_path=plugin_path,
        profile_path=route_profile_path, session_id=session_id,
        attempt_id=attempt_id)
    contact = build_transition_manifest(
        scene_path=scene_path, route_profile_path=route_profile_path,
        profile_path=profile_path, plugin_path=plugin_path,
        proposal_path=proposal_path, receipt_path=receipt_path,
        session_id=session_id, attempt_id=attempt_id,
        pairs_factory=pairs_factory)
    route_segments = len(route["target_positions"]) // 9
    if (route_segments != 246 or route["model_sha256"] != contact["model_sha256"]
            or route["cup_start_m"] != contact["cup_start_m"]
            or any(route[key] != contact[key] for key in _PATH_LIMITS
                   if key != "stop_max_age_s")
            or route["stop_max_age_s"] != contact["stop_max_age_s"]):
        raise ValueError("Task 6 full contact source limit drift")
    first = route["handoff_positions"]
    last = contact["joint_start_rad"]
    if max(abs(a - b) for a, b in zip(first, last, strict=True)) > .002:
        raise ValueError("Task 6 full contact bridge too large")
    bridge = _rows_between(first, last)
    raw = json.dumps(bridge, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    bridge_sha = hashlib.sha256(raw).hexdigest()
    if bridge_sha != _BRIDGE_SHA:
        raise ValueError("Task 6 full contact bridge drift")
    value = dict(contact)
    value.update(
        kind="ACT_TASK6_FULL_CONTACT_DIAGNOSTIC",
        joint_start_rad=route["joint_start_rad"],
        target_positions=route["target_positions"] + bridge + contact["target_positions"],
        segment_phases=["APPROACH"] * (route_segments + 2) + ["CONTACT"] * 33,
        route_segment_count=route_segments,
        contact_phase_start=route_segments + 2,
        bridge_rows_sha256=bridge_sha,
        source_route_manifest_sha256=route["manifest_sha256"],
        source_contact_manifest_sha256=contact["manifest_sha256"],
    )
    del value["manifest_sha256"]
    value["manifest_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    require_full_manifest(value)
    return value


def require_full_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _FULL_KEYS:
        raise ValueError("Task 6 full contact manifest schema invalid")
    if (value["schema_version"] != 1
            or value["kind"] != "ACT_TASK6_FULL_CONTACT_DIAGNOSTIC"
            or value["eligible_for_collection"] is not False
            or value["backend"] != "mujoco"
            or value["mujoco_version"] != "3.12.0"
            or value["segment_rows"] != 9
            or value["route_segment_count"] != 246
            or value["contact_phase_start"] != 248
            or value["bridge_rows_sha256"] != _BRIDGE_SHA
            or value["segment_phases"] != ["APPROACH"] * 248 + ["CONTACT"] * 33
            or any(value[key] != expected for key, expected in _PATH_LIMITS.items())
            or not isinstance(value["target_positions"], list)
            or len(value["target_positions"]) != 281 * 9):
        raise ValueError("Task 6 full contact role/trajectory invalid")
    for row in value["target_positions"]:
        bounded_positions(row)
    bounded_positions(value["joint_start_rad"])
    if (not isinstance(value["allowed_contact_pairs_by_phase"], dict)
            or set(value["allowed_contact_pairs_by_phase"]) != {"APPROACH", "CONTACT"}
            or value["allowed_contact_pairs_by_phase"]["APPROACH"] != []
            or not value["allowed_contact_pairs_by_phase"]["CONTACT"]):
        raise ValueError("Task 6 full contact phase policy invalid")
    for key in ("scene_path", "route_profile_path", "profile_path", "plugin_path",
                "proposal_path", "receipt_path"):
        if not isinstance(value[key], str) or not Path(value[key]).is_absolute():
            raise ValueError("Task 6 full contact source path invalid")
    for key in ("source_route_manifest_sha256", "source_contact_manifest_sha256"):
        if not isinstance(value[key], str) or len(value[key]) != 64:
            raise ValueError("Task 6 full contact source hash invalid")
    if value["manifest_sha256"] != hashlib.sha256(_canonical(
            {key: item for key, item in value.items()
             if key != "manifest_sha256"})).hexdigest():
        raise ValueError("Task 6 full contact manifest hash invalid")
    return value


def require_full_sources(manifest: dict, *, pairs_factory=Task8ContactPairs) -> dict:
    require_full_manifest(manifest)
    expected = build_full_manifest(
        scene_path=Path(manifest["scene_path"]),
        plugin_path=Path(manifest["plugin_path"]),
        route_profile_path=Path(manifest["route_profile_path"]),
        profile_path=Path(manifest["profile_path"]),
        proposal_path=Path(manifest["proposal_path"]),
        receipt_path=Path(manifest["receipt_path"]),
        session_id=manifest["session_id"], attempt_id=manifest["attempt_id"],
        pairs_factory=pairs_factory)
    if _canonical(expected) != _canonical(manifest):
        raise ValueError("Task 6 full contact source replay mismatch")
    return manifest


def full_prefix_matches(prefix: object, manifest: dict) -> bool:
    try:
        require_full_manifest(manifest)
        checked = validate_action_prefix(prefix)
        start = checked["sequence"] * 9
        prior = (manifest["joint_start_rad"] if start == 0 else
                 manifest["target_positions"][start - 1])
        expected = [prior] + manifest["target_positions"][start:start + 9]
        if (checked["session_id"] != manifest["session_id"]
                or checked["attempt_id"] != manifest["attempt_id"]
                or start >= len(manifest["target_positions"])
                or len(checked["positions"]) != len(expected)):
            return False
        return all(all(abs(a - b) <= 1e-10 for a, b in zip(row, frozen, strict=True))
                   for row, frozen in zip(checked["positions"], expected, strict=True))
    except (KeyError, TypeError, ValueError):
        return False
